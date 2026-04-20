"""Configuración centralizada del CLI.

Lee credenciales desde variables de entorno (o `.env` en cwd).
Timezone se maneja en `tjira.tz`.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from tjira.errors import UserError

load_dotenv()

JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")


def validate_config() -> None:
    """Verifica que las credenciales mínimas estén presentes.

    Raises:
        UserError: si falta alguna variable obligatoria. El payload incluye
            el listado de variables faltantes para que el agente pueda
            accionar sobre el error estructurado.
    """
    missing = [
        name
        for name, value in (
            ("JIRA_DOMAIN", JIRA_DOMAIN),
            ("JIRA_EMAIL", JIRA_EMAIL),
            ("JIRA_API_TOKEN", JIRA_API_TOKEN),
        )
        if not value
    ]
    if missing:
        raise UserError(
            f"Faltan variables de entorno: {', '.join(missing)}",
            payload={"missing": missing},
        )
