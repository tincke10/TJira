"""`tjira worklog` subcommand — bulk import/delete from CSV."""

from __future__ import annotations

import csv
from pathlib import Path

import typer

from tjira.client import JiraClient
from tjira.errors import APIError, TjiraError, UserError, fail
from tjira.formatters import emit, log


def register(app: typer.Typer) -> None:
    worklog_app = typer.Typer(help="Bulk import/delete worklogs from CSV")
    app.add_typer(worklog_app, name="worklog")

    @worklog_app.command("import", help="Import worklogs from a CSV file")
    def worklog_import(
        csv_file: Path = typer.Argument(..., help="CSV file with the worklogs"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without executing"),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            if not csv_file.exists():
                raise UserError(f"CSV file not found: {csv_file}")

            client = None if dry_run else JiraClient()
            log(f"Importing worklogs from: {csv_file}")
            if dry_run:
                log("DRY-RUN MODE: no changes will be made")

            success: list[dict] = []
            errors: list[dict] = []

            with csv_file.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                required = {"Jira Key", "Time Spent", "Started"}
                missing = required - set(reader.fieldnames or [])
                if missing:
                    raise UserError(
                        f"CSV is missing required columns: {', '.join(sorted(missing))}",
                        payload={"missing_columns": sorted(missing)},
                    )

                for row in reader:
                    issue_key = row["Jira Key"]
                    time_spent = row["Time Spent"]
                    started = row["Started"]
                    summary = (row.get("Summary") or "")[:40]

                    log(f"  {issue_key}: {time_spent} - {started[:10]} - {summary}")

                    if dry_run:
                        success.append({"issue": issue_key, "time_spent": time_spent, "dry_run": True})
                        continue

                    try:
                        result = client.add_worklog(issue_key, time_spent, started)
                        success.append(
                            {
                                "issue": issue_key,
                                "time_spent": time_spent,
                                "worklog_id": result.get("id"),
                            }
                        )
                    except APIError as exc:
                        errors.append(
                            {"issue": issue_key, "error": exc.message, **exc.payload}
                        )

            data = {
                "dry_run": dry_run,
                "success_count": len(success),
                "error_count": len(errors),
                "success": success,
                "errors": errors,
            }

            def _human(d: dict) -> None:
                print(f"SUMMARY: {d['success_count']} succeeded, {d['error_count']} failed")
                if d["errors"]:
                    print("\nErrors:")
                    for e in d["errors"]:
                        print(f"  - {e.get('issue')}: {e.get('error')}")

            emit(data, as_json=json_out, human_fn=_human)
        except TjiraError as err:
            fail(err, as_json=json_out)

    @worklog_app.command("delete", help="Delete every worklog for the issues listed in a CSV")
    def worklog_delete(
        csv_file: Path = typer.Argument(..., help="CSV file with the issue keys"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without executing"),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            if not csv_file.exists():
                raise UserError(f"CSV file not found: {csv_file}")

            issues: set[str] = set()
            with csv_file.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if "Jira Key" not in (reader.fieldnames or []):
                    raise UserError("CSV is missing the 'Jira Key' column")
                for row in reader:
                    issues.add(row["Jira Key"])

            client = JiraClient()
            log(f"Deleting worklogs for {len(issues)} issues")
            if dry_run:
                log("DRY-RUN MODE: no changes will be made")

            deleted: list[dict] = []
            errors: list[dict] = []

            for issue_key in sorted(issues):
                try:
                    worklogs = client.get_worklogs(issue_key)
                except APIError as exc:
                    errors.append({"issue": issue_key, "error": exc.message})
                    continue

                if not worklogs:
                    log(f"  {issue_key}: no worklogs")
                    continue

                log(f"  {issue_key}: {len(worklogs)} worklog(s)")
                for wl in worklogs:
                    wl_id = wl["id"]
                    entry = {
                        "issue": issue_key,
                        "worklog_id": wl_id,
                        "time_spent": wl.get("timeSpent"),
                        "started": wl.get("started"),
                    }
                    if dry_run:
                        entry["dry_run"] = True
                        deleted.append(entry)
                        continue
                    try:
                        client.delete_worklog(issue_key, wl_id)
                        deleted.append(entry)
                    except APIError as exc:
                        errors.append({**entry, "error": exc.message})

            data = {
                "dry_run": dry_run,
                "deleted_count": len(deleted),
                "error_count": len(errors),
                "deleted": deleted,
                "errors": errors,
            }

            def _human(d: dict) -> None:
                print(f"SUMMARY: {d['deleted_count']} deleted, {d['error_count']} failed")
                if d["errors"]:
                    print("\nErrors:")
                    for e in d["errors"]:
                        print(f"  - {e.get('issue')}/{e.get('worklog_id')}: {e.get('error')}")

            emit(data, as_json=json_out, human_fn=_human)
        except TjiraError as err:
            fail(err, as_json=json_out)
