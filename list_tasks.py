#!/usr/bin/env python3
"""
Script para listar tareas de Jira.

Uso:
    python list_tasks.py                           # Mis tareas pendientes
    python list_tasks.py --project TGFDEV          # Tareas de un proyecto
    python list_tasks.py --jql "status = Done"     # Query JQL personalizado
"""

import argparse
from jira_client import JiraClient


def main():
    parser = argparse.ArgumentParser(description="Listar tareas de Jira")
    parser.add_argument("--project", "-p", help="Filtrar por proyecto")
    parser.add_argument("--status", "-s", help="Filtrar por estado")
    parser.add_argument("--assignee", "-a", default="currentUser()",
                        help="Filtrar por asignado (default: currentUser())")
    parser.add_argument("--jql", help="Query JQL personalizado (ignora otros filtros)")
    parser.add_argument("--limit", "-l", type=int, default=20,
                        help="Máximo de resultados (default: 20)")

    args = parser.parse_args()

    client = JiraClient()

    # Construir JQL
    if args.jql:
        jql = args.jql
    else:
        conditions = []

        if args.project:
            conditions.append(f"project = {args.project}")

        if args.status:
            conditions.append(f"status = '{args.status}'")
        else:
            conditions.append("status != Done")

        if args.assignee:
            conditions.append(f"assignee = {args.assignee}")

        jql = " AND ".join(conditions) + " ORDER BY updated DESC"

    print(f"Query: {jql}\n")

    issues = client.search_issues(jql, args.limit)

    if not issues:
        print("No se encontraron tareas")
        return

    print(f"{'KEY':<15} {'TIPO':<10} {'ESTADO':<15} {'TITULO'}")
    print("-" * 80)

    for issue in issues:
        key = issue["key"]
        fields = issue["fields"]
        issue_type = fields.get("issuetype", {}).get("name", "-")[:10]
        status = fields.get("status", {}).get("name", "-")[:15]
        summary = fields.get("summary", "-")[:45]

        print(f"{key:<15} {issue_type:<10} {status:<15} {summary}")

    print(f"\nTotal: {len(issues)} tareas")


if __name__ == "__main__":
    main()
