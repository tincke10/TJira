#!/usr/bin/env python3
"""
Script para listar tareas de Jira.

Uso:
    python list_tasks.py                           # Mis tareas pendientes
    python list_tasks.py --project TGFDEV          # Tareas de un proyecto
    python list_tasks.py --jql "status = Done"     # Query JQL personalizado
    python list_tasks.py --boards                  # Listar boards disponibles
    python list_tasks.py --board 123               # Tareas de un board
    python list_tasks.py --board 123 --sprints     # Sprints de un board
    python list_tasks.py --sprint 456              # Tareas de un sprint
    python list_tasks.py --filter 789              # Tareas de un filtro guardado
    python list_tasks.py --filters                 # Listar filtros disponibles
    python list_tasks.py --dashboards              # Listar dashboards
"""

import argparse
from jira_client import JiraClient


def print_issues(issues):
    """Imprime una tabla de issues."""
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


def main():
    parser = argparse.ArgumentParser(description="Listar tareas de Jira")
    parser.add_argument("--project", "-p", help="Filtrar por proyecto")
    parser.add_argument("--status", "-s", help="Filtrar por estado")
    parser.add_argument("--assignee", "-a", default="currentUser()",
                        help="Filtrar por asignado (default: currentUser())")
    parser.add_argument("--jql", help="Query JQL personalizado (ignora otros filtros)")
    parser.add_argument("--limit", "-l", type=int, default=20,
                        help="Máximo de resultados (default: 20)")

    # Boards (Agile)
    parser.add_argument("--boards", action="store_true",
                        help="Listar boards disponibles")
    parser.add_argument("--board", type=int,
                        help="ID del board para listar sus tareas")
    parser.add_argument("--sprints", action="store_true",
                        help="Mostrar sprints del board (usar con --board)")
    parser.add_argument("--sprint", type=int,
                        help="ID del sprint para listar sus tareas")

    # Filtros
    parser.add_argument("--filters", action="store_true",
                        help="Listar filtros guardados disponibles")
    parser.add_argument("--filter", type=int,
                        help="ID del filtro para listar sus tareas")

    # Dashboards
    parser.add_argument("--dashboards", action="store_true",
                        help="Listar dashboards disponibles")

    args = parser.parse_args()

    client = JiraClient()

    # Listar boards
    if args.boards:
        boards = client.get_boards(project_key=args.project)
        if not boards:
            print("No se encontraron boards")
            return
        print(f"{'ID':<8} {'TIPO':<10} {'NOMBRE'}")
        print("-" * 60)
        for b in boards:
            print(f"{b['id']:<8} {b.get('type', '-'):<10} {b['name']}")
        print(f"\nTotal: {len(boards)} boards")
        return

    # Listar sprints de un board
    if args.sprints and args.board:
        for state in ["active", "future", "closed"]:
            sprints = client.get_board_sprints(args.board, state=state)
            if sprints:
                print(f"\nSprints ({state}):")
                print(f"  {'ID':<8} {'ESTADO':<10} {'NOMBRE'}")
                print(f"  {'-' * 50}")
                for s in sprints:
                    print(f"  {s['id']:<8} {s.get('state', '-'):<10} {s['name']}")
        return

    # Tareas de un sprint
    if args.sprint:
        print(f"Tareas del sprint {args.sprint}:\n")
        issues = client.get_sprint_issues(args.sprint, args.limit)
        print_issues(issues)
        return

    # Tareas de un board
    if args.board:
        print(f"Tareas del board {args.board}:\n")
        issues = client.get_board_issues(args.board, args.limit)
        print_issues(issues)
        return

    # Listar filtros
    if args.filters:
        filters = client.get_filters()
        if not filters:
            print("No se encontraron filtros")
            return
        print(f"{'ID':<8} {'NOMBRE':<35} {'JQL'}")
        print("-" * 80)
        for f in filters:
            jql = f.get("jql", "-")[:35]
            print(f"{f['id']:<8} {f['name'][:35]:<35} {jql}")
        print(f"\nTotal: {len(filters)} filtros")
        return

    # Tareas de un filtro
    if args.filter:
        filter_data = client.get_filter(args.filter)
        if filter_data:
            print(f"Filtro: {filter_data.get('name', 'N/A')}")
            print(f"JQL: {filter_data.get('jql', 'N/A')}\n")
        issues = client.get_filter_issues(args.filter, args.limit)
        print_issues(issues)
        return

    # Listar dashboards
    if args.dashboards:
        dashboards = client.get_dashboards()
        if not dashboards:
            print("No se encontraron dashboards")
            return
        print(f"{'ID':<8} {'NOMBRE'}")
        print("-" * 40)
        for d in dashboards:
            print(f"{d['id']:<8} {d['name']}")
        print(f"\nTotal: {len(dashboards)} dashboards")
        return

    # Búsqueda estándar con JQL
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
    print_issues(issues)


if __name__ == "__main__":
    main()
