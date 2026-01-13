#!/usr/bin/env python3
"""
Script para registrar horas (worklogs) en Jira.

Uso:
    python log_hours.py TGFDEV-123 2h                    # Log 2 horas ahora
    python log_hours.py TGFDEV-123 2h "2025-01-05"      # Log 2 horas en fecha específica
    python log_hours.py TGFDEV-123 2h "2025-01-05 09:00" # Log con hora específica
"""

import sys
from datetime import datetime
from jira_client import JiraClient


def parse_datetime(date_str: str) -> str:
    """Convierte fecha/hora a formato ISO 8601 para Jira."""
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y"
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if ":" not in date_str:
                dt = dt.replace(hour=9, minute=0)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000+0100")
        except ValueError:
            continue

    raise ValueError(f"Formato de fecha no reconocido: {date_str}")


def main():
    if len(sys.argv) < 3:
        print("Uso: python log_hours.py <ISSUE_KEY> <TIME_SPENT> [FECHA]")
        print()
        print("Ejemplos:")
        print("  python log_hours.py TGFDEV-123 2h")
        print("  python log_hours.py TGFDEV-123 '1h 30m' '2025-01-05'")
        print("  python log_hours.py TGFDEV-123 30m '2025-01-05 14:00'")
        sys.exit(1)

    issue_key = sys.argv[1]
    time_spent = sys.argv[2]
    started = None

    if len(sys.argv) > 3:
        started = parse_datetime(sys.argv[3])

    client = JiraClient()

    print(f"Registrando {time_spent} en {issue_key}...")

    success, result = client.add_worklog(issue_key, time_spent, started)

    if success:
        print(f"OK: Worklog registrado (ID: {result.get('id')})")
    else:
        print(f"Error: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
