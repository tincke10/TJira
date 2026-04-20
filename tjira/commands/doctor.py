"""Subcomando `tjira doctor` — verificación de setup.

Corre chequeos de configuración y conectividad, y reporta en formato humano o
JSON. Útil para onboarding y para agentes (Claude, CI) que necesitan validar
que el entorno está listo antes de ejecutar comandos de negocio.

Checks:
    1. `.env` (o variables de entorno) con credenciales presentes
    2. `JIRA_DOMAIN` con forma plausible (host, sin esquema)
    3. `JIRA_TIMEZONE` es una zona IANA válida (si está seteada)
    4. Llamada real a `GET /myself` para validar credenciales

Exit codes:
    0 → todos los checks pasaron
    1 → al menos un check no pasó (config o credenciales)
"""

from __future__ import annotations

import os
from typing import Any

import typer

from tjira import __version__
from tjira.errors import APIError, TjiraError, UserError, fail
from tjira.formatters import emit

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment,misc]


CheckResult = dict[str, Any]


def register(app: typer.Typer) -> None:
    @app.command("doctor", help="Verificar configuración, credenciales y conectividad")
    def doctor_cmd(
        json_out: bool = typer.Option(False, "--json", help="Output JSON a stdout"),
    ) -> None:
        try:
            checks = _run_checks()
            data = {
                "version": __version__,
                "all_passed": all(c["passed"] for c in checks),
                "checks": checks,
            }
            emit(data, as_json=json_out, human_fn=_print_human)
            if not data["all_passed"]:
                raise UserError(
                    "Uno o más checks fallaron",
                    payload={"failed": [c["name"] for c in checks if not c["passed"]]},
                )
        except TjiraError as err:
            fail(err, as_json=json_out)


def _run_checks() -> list[CheckResult]:
    """Ejecuta los checks de forma independiente; no aborta en el primer fallo."""
    return [
        _check_env_vars(),
        _check_domain_shape(),
        _check_timezone(),
        _check_jira_connectivity(),
    ]


def _check_env_vars() -> CheckResult:
    required = ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        return {
            "name": "env_vars",
            "passed": False,
            "detail": f"Faltan variables: {', '.join(missing)}",
            "missing": missing,
        }
    return {
        "name": "env_vars",
        "passed": True,
        "detail": "Todas las variables requeridas están presentes",
    }


def _check_domain_shape() -> CheckResult:
    domain = os.getenv("JIRA_DOMAIN") or ""
    if not domain:
        return {
            "name": "domain_shape",
            "passed": False,
            "detail": "JIRA_DOMAIN no está seteado",
        }
    if domain.startswith(("http://", "https://")) or domain.endswith("/"):
        return {
            "name": "domain_shape",
            "passed": False,
            "detail": (
                "JIRA_DOMAIN debe ser solo el host, sin esquema ni slash final "
                "(ej: 'your-company.atlassian.net')"
            ),
            "value": domain,
        }
    return {
        "name": "domain_shape",
        "passed": True,
        "detail": f"Host: {domain}",
    }


def _check_timezone() -> CheckResult:
    tz_name = os.getenv("JIRA_TIMEZONE")
    if not tz_name:
        return {
            "name": "timezone",
            "passed": True,
            "detail": "JIRA_TIMEZONE no seteado — se usará el timezone local del sistema",
        }
    if ZoneInfo is None:
        return {
            "name": "timezone",
            "passed": False,
            "detail": "zoneinfo no disponible en esta versión de Python",
        }
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return {
            "name": "timezone",
            "passed": False,
            "detail": f"Timezone IANA inválida: '{tz_name}'",
            "value": tz_name,
        }
    return {
        "name": "timezone",
        "passed": True,
        "detail": f"Timezone válida: {tz_name}",
    }


def _check_jira_connectivity() -> CheckResult:
    # Import diferido: si faltan credenciales, `JiraClient()` explota al init.
    missing = [n for n in ("JIRA_DOMAIN", "JIRA_EMAIL", "JIRA_API_TOKEN") if not os.getenv(n)]
    if missing:
        return {
            "name": "jira_connectivity",
            "passed": False,
            "detail": "No se puede validar conectividad sin credenciales completas",
            "skipped_due_to": missing,
        }
    try:
        from tjira.client import JiraClient
        client = JiraClient()
        me = client.get_myself()
    except APIError as exc:
        return {
            "name": "jira_connectivity",
            "passed": False,
            "detail": f"API de Jira no respondió OK: {exc.message}",
            **exc.payload,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "name": "jira_connectivity",
            "passed": False,
            "detail": f"Error inesperado contactando a Jira: {exc}",
        }
    return {
        "name": "jira_connectivity",
        "passed": True,
        "detail": f"Autenticado como {me.get('displayName')} ({me.get('emailAddress')})",
        "account_id": me.get("accountId"),
    }


def _print_human(data: dict) -> None:
    print(f"tjira {data['version']} — health check\n")
    for check in data["checks"]:
        icon = "OK   " if check["passed"] else "FAIL "
        print(f"  [{icon}] {check['name']:<20} {check['detail']}")
    print()
    if data["all_passed"]:
        print("Todos los checks pasaron — tu setup está listo.")
    else:
        print("Uno o más checks fallaron. Revisá los detalles arriba.")
