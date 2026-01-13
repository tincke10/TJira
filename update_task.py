#!/usr/bin/env python3
"""
Script para actualizar tareas en Jira.

Uso:
    python update_task.py TGFDEV-123 --summary "Nuevo título"
    python update_task.py TGFDEV-123 --status "In Progress"
    python update_task.py TGFDEV-123 --assign me
"""

import sys
import argparse
from jira_client import JiraClient


def main():
    parser = argparse.ArgumentParser(description="Actualizar una tarea en Jira")
    parser.add_argument("issue", help="Clave de la issue (ej: TGFDEV-123)")
    parser.add_argument("--summary", "-s", help="Nuevo título")
    parser.add_argument("--status", help="Cambiar estado (ver transiciones disponibles)")
    parser.add_argument("--assign", "-a", help="Asignar a usuario (ID o 'me')")
    parser.add_argument("--transitions", action="store_true",
                        help="Mostrar transiciones disponibles")

    args = parser.parse_args()

    client = JiraClient()
    issue_key = args.issue

    # Mostrar transiciones disponibles
    if args.transitions:
        print(f"Transiciones disponibles para {issue_key}:")
        transitions = client.get_transitions(issue_key)
        for t in transitions:
            print(f"  [{t['id']}] {t['name']}")
        return

    # Actualizar campos
    if args.summary:
        success, msg = client.update_issue(issue_key, {"summary": args.summary})
        if success:
            print(f"OK: Título actualizado")
        else:
            print(f"Error actualizando título: {msg}")

    # Cambiar estado
    if args.status:
        transitions = client.get_transitions(issue_key)
        transition = next(
            (t for t in transitions if t["name"].lower() == args.status.lower()),
            None
        )

        if transition:
            success, msg = client.transition_issue(issue_key, transition["id"])
            if success:
                print(f"OK: Estado cambiado a '{args.status}'")
            else:
                print(f"Error cambiando estado: {msg}")
        else:
            print(f"Error: Transición '{args.status}' no disponible")
            print("Transiciones disponibles:")
            for t in transitions:
                print(f"  - {t['name']}")

    # Asignar usuario
    if args.assign:
        assignee_id = args.assign
        if args.assign.lower() == "me":
            me = client.get_myself()
            if me:
                assignee_id = me.get("accountId")
            else:
                print("Error: No se pudo obtener tu ID de usuario")
                sys.exit(1)

        success, msg = client.assign_issue(issue_key, assignee_id)
        if success:
            print(f"OK: Issue asignada")
        else:
            print(f"Error asignando: {msg}")

    # Si no se proporcionó ninguna acción, mostrar info de la issue
    if not any([args.summary, args.status, args.assign]):
        issue = client.get_issue(issue_key)
        if issue:
            fields = issue["fields"]
            print(f"Issue: {issue_key}")
            print(f"  Título: {fields.get('summary')}")
            print(f"  Tipo: {fields.get('issuetype', {}).get('name')}")
            print(f"  Estado: {fields.get('status', {}).get('name')}")
            assignee = fields.get('assignee')
            print(f"  Asignado: {assignee.get('displayName') if assignee else 'Sin asignar'}")
        else:
            print(f"Error: No se encontró la issue {issue_key}")


if __name__ == "__main__":
    main()
