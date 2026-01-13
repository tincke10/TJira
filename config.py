"""Configuración centralizada para Jira API."""

import os
from dotenv import load_dotenv

load_dotenv()

JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

def validate_config():
    """Valida que las credenciales estén configuradas."""
    missing = []
    if not JIRA_DOMAIN:
        missing.append("JIRA_DOMAIN")
    if not JIRA_EMAIL:
        missing.append("JIRA_EMAIL")
    if not JIRA_API_TOKEN:
        missing.append("JIRA_API_TOKEN")

    if missing:
        raise ValueError(f"Faltan variables de entorno: {', '.join(missing)}")

    return True
