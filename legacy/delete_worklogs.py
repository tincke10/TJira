#!/usr/bin/env python3
"""
Script para eliminar worklogs de las issues especificadas en un CSV.

Uso:
    python delete_worklogs.py hotel_demand_worklogs.csv
    python delete_worklogs.py hotel_demand_worklogs.csv --dry-run
"""

import sys
import csv
import argparse
from jira_client import JiraClient


def main():
    parser = argparse.ArgumentParser(description="Eliminar worklogs de issues en CSV")
    parser.add_argument("csv_file", help="Archivo CSV con las issues")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría, sin ejecutar")

    args = parser.parse_args()

    client = JiraClient()

    # Obtener issues únicas del CSV
    issues = set()
    with open(args.csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            issues.add(row["Jira Key"])

    print("=" * 70)
    print(f"Eliminando worklogs de {len(issues)} issues")
    if args.dry_run:
        print("MODO DRY-RUN: No se realizarán cambios")
    print("=" * 70)

    deleted_count = 0
    error_count = 0

    for issue_key in sorted(issues):
        worklogs = client.get_worklogs(issue_key)

        if not worklogs:
            print(f"\n{issue_key}: Sin worklogs")
            continue

        print(f"\n{issue_key}: {len(worklogs)} worklog(s)")

        for wl in worklogs:
            wl_id = wl["id"]
            time_spent = wl.get("timeSpent", "?")
            started = wl.get("started", "?")[:10]

            if args.dry_run:
                print(f"  [DRY-RUN] Eliminaría worklog {wl_id} ({time_spent} - {started})")
                deleted_count += 1
            else:
                if client.delete_worklog(issue_key, wl_id):
                    print(f"  Eliminado: {wl_id} ({time_spent} - {started})")
                    deleted_count += 1
                else:
                    print(f"  ERROR eliminando: {wl_id}")
                    error_count += 1

    print("\n" + "=" * 70)
    print(f"RESUMEN: {deleted_count} eliminados, {error_count} errores")
    print("=" * 70)


if __name__ == "__main__":
    main()
