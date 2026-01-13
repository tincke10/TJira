#!/usr/bin/env python3
"""
Script para crear tareas en Jira.

Uso:
    python create_task.py TGFDEV "Título de la tarea"
    python create_task.py TGFDEV "Título" --type Bug
    python create_task.py TGFDEV "Título" --desc "Descripción detallada"
"""

import sys
import argparse
from jira_client import JiraClient


def main():
    parser = argparse.ArgumentParser(description="Crear una tarea en Jira")
    parser.add_argument("project", help="Clave del proyecto (ej: TGFDEV)")
    parser.add_argument("summary", help="Título de la tarea")
    parser.add_argument("--type", "-t", default="Task",
                        help="Tipo de issue (Task, Bug, Story, Epic)")
    parser.add_argument("--desc", "-d", default=None,
                        help="Descripción de la tarea")
    parser.add_argument("--assign", "-a", default=None,
                        help="ID del usuario a asignar")

    args = parser.parse_args()

    client = JiraClient()

    print(f"Creando {args.type} en {args.project}...")

    success, result = client.create_issue(
        project_key=args.project,
        summary=args.summary,
        issue_type=args.type,
        description=args.desc,
        assignee_id=args.assign
    )

    if success:
        issue_key = result.get("key")
        print(f"OK: {issue_key} - {args.summary}")
        print(f"URL: https://{client.base_url.split('/rest')[0]}/browse/{issue_key}")
    else:
        print(f"Error: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
