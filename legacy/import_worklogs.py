#!/usr/bin/env python3
"""
Script para importar worklogs desde CSV a Jira.

Uso:
    python import_worklogs.py hotel_demand_worklogs.csv
    python import_worklogs.py hotel_demand_worklogs.csv --dry-run
"""

import sys
import csv
import argparse
from jira_client import JiraClient


def main():
    parser = argparse.ArgumentParser(description="Importar worklogs desde CSV")
    parser.add_argument("csv_file", help="Archivo CSV con los worklogs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría, sin ejecutar")

    args = parser.parse_args()

    client = JiraClient()

    print("=" * 70)
    print(f"Importando worklogs desde: {args.csv_file}")
    if args.dry_run:
        print("MODO DRY-RUN: No se realizarán cambios")
    print("=" * 70)

    success_count = 0
    error_count = 0
    errors = []

    with open(args.csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            issue_key = row["Jira Key"]
            time_spent = row["Time Spent"]
            started = row["Started"]
            summary = row.get("Summary", "")[:40]

            print(f"\n{issue_key}: {time_spent} - {started[:10]} - {summary}...")

            if args.dry_run:
                print("  [DRY-RUN] Se registraría worklog")
                success_count += 1
                continue

            success, result = client.add_worklog(issue_key, time_spent, started)

            if success:
                print(f"  OK (ID: {result.get('id')})")
                success_count += 1
            else:
                print(f"  ERROR: {result}")
                error_count += 1
                errors.append({"issue": issue_key, "error": result})

    print("\n" + "=" * 70)
    print(f"RESUMEN: {success_count} exitosos, {error_count} errores")
    print("=" * 70)

    if errors:
        print("\nErrores:")
        for e in errors:
            print(f"  - {e['issue']}: {e['error']}")


if __name__ == "__main__":
    main()
