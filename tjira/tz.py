"""Manejo de timezone configurable.

La zona se resuelve en este orden:
    1. Variable de entorno `JIRA_TIMEZONE` (ej: `America/Argentina/Buenos_Aires`)
    2. Timezone local del sistema
    3. UTC como último recurso

Antes estaba hardcodeado en `+0100` (Europa/España), lo que rompía worklogs
para cualquier usuario fuera de ese huso horario.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[assignment]


def get_timezone():
    """Devuelve el tzinfo configurado."""
    tz_name = os.getenv("JIRA_TIMEZONE")
    if tz_name and ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass

    local = datetime.now().astimezone().tzinfo
    return local or timezone.utc


def to_jira_datetime(dt: datetime) -> str:
    """Convierte un datetime al formato ISO que Jira acepta para worklogs.

    Formato: `YYYY-MM-DDTHH:MM:SS.000±HHMM`
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_timezone())
    # Jira exige milisegundos con 3 dígitos y offset sin `:`
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    offset = dt.strftime("%z") or "+0000"
    return f"{base}.000{offset}"


def parse_user_datetime(date_str: str) -> datetime:
    """Parsea strings de fecha flexibles del usuario.

    Acepta: `YYYY-MM-DD HH:MM`, `YYYY-MM-DD`, `DD/MM/YYYY HH:MM`, `DD/MM/YYYY`.
    Si no trae hora, asume 09:00. Si no trae tz, usa la configurada.
    """
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
        except ValueError:
            continue
        if ":" not in date_str:
            dt = dt.replace(hour=9, minute=0)
        return dt.replace(tzinfo=get_timezone())

    raise ValueError(f"Formato de fecha no reconocido: {date_str}")
