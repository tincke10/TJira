"""`tjira worklog` subcommand — bulk import/delete from CSV.

Import auto-adjusts overlapping ``started`` timestamps in cascade. The first
overlapping row is pushed to the end of the conflicting worklog; subsequent
rows that would now overlap with the freshly-pushed row are pushed too. There
is no upper bound — see ``--no-adjust`` for the legacy behavior.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import typer

from tjira.client import JiraClient
from tjira.errors import APIError, TjiraError, UserError, fail
from tjira.formatters import emit, log
from tjira.overlap import (
    _parse_jira_started,
    find_overlap,
    parse_time_spent,
    worklog_interval,
)
from tjira.tz import to_jira_datetime


def register(app: typer.Typer) -> None:
    worklog_app = typer.Typer(help="Bulk import/delete worklogs from CSV")
    app.add_typer(worklog_app, name="worklog")

    @worklog_app.command("import", help="Import worklogs from a CSV file")
    def worklog_import(
        csv_file: Path = typer.Argument(..., help="CSV file with the worklogs"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without executing"),
        no_adjust: bool = typer.Option(
            False,
            "--no-adjust",
            help="Disable overlap auto-adjust (legacy behavior — POST as-is)",
        ),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            if not csv_file.exists():
                raise UserError(f"CSV file not found: {csv_file}")

            log(f"Importing worklogs from: {csv_file}")
            if dry_run:
                log("DRY-RUN MODE: no changes will be made")
            if no_adjust:
                log("NO-ADJUST MODE: overlap detection disabled")

            rows = _read_rows(csv_file)
            need_client = (not dry_run) or (not no_adjust)
            client = JiraClient() if need_client else None

            existing = _fetch_existing_window(client, rows) if (not no_adjust) else []

            processed_synth: list[dict] = []
            success: list[dict] = []
            errors: list[dict] = []
            adjusted_count = 0

            for row in rows:
                issue_key = row["Jira Key"]
                time_spent = row["Time Spent"]
                started_raw = row["Started"]
                summary = (row.get("Summary") or "")[:40]

                try:
                    started_dt = _parse_jira_started(started_raw)
                except ValueError as exc:
                    errors.append({"issue": issue_key, "error": f"bad Started: {exc}"})
                    continue

                try:
                    duration = parse_time_spent(time_spent)
                except ValueError as exc:
                    errors.append({"issue": issue_key, "error": f"bad Time Spent: {exc}"})
                    continue

                end_dt = started_dt + duration
                adjustments: list[dict] = []

                if not no_adjust:
                    candidates = existing + processed_synth
                    # Cascade: keep pushing until no overlap remains.
                    while True:
                        conflict = find_overlap(started_dt, end_dt, candidates)
                        if conflict is None:
                            break
                        _, conflict_end = worklog_interval(conflict)
                        adjustments.append({
                            "from": to_jira_datetime(started_dt),
                            "to": to_jira_datetime(conflict_end),
                            "displaced_by": {
                                "issue": conflict.get("_issue_key"),
                                "worklog_id": conflict.get("id"),
                            },
                        })
                        # Reset the cursor and recompute end with the original duration.
                        started_dt = conflict_end
                        end_dt = started_dt + duration

                if adjustments:
                    adjusted_count += 1

                started_iso = to_jira_datetime(started_dt)
                log(f"  {issue_key}: {time_spent} - {started_iso[:10]} - {summary}")

                # Synth a worklog dict so subsequent rows can detect overlap with this one.
                processed_synth.append({
                    "id": f"_pending_{len(processed_synth)}",
                    "_issue_key": issue_key,
                    "started": started_iso,
                    "timeSpent": time_spent,
                    "timeSpentSeconds": int(duration.total_seconds()),
                })

                entry = {
                    "issue": issue_key,
                    "time_spent": time_spent,
                    "started": started_iso,
                    "adjustments": adjustments,
                }

                if dry_run:
                    entry["dry_run"] = True
                    success.append(entry)
                    continue

                try:
                    result = client.add_worklog(issue_key, time_spent, started_iso)
                    entry["worklog_id"] = result.get("id")
                    success.append(entry)
                except APIError as exc:
                    errors.append(
                        {"issue": issue_key, "error": exc.message, **exc.payload}
                    )

            data = {
                "dry_run": dry_run,
                "no_adjust": no_adjust,
                "success_count": len(success),
                "error_count": len(errors),
                "adjusted_count": adjusted_count,
                "success": success,
                "errors": errors,
            }

            def _human(d: dict) -> None:
                print(
                    f"SUMMARY: {d['success_count']} succeeded, "
                    f"{d['error_count']} failed, {d['adjusted_count']} adjusted"
                )
                for s in d["success"]:
                    if s.get("adjustments"):
                        adj = s["adjustments"][-1]
                        print(
                            f"  ADJUSTED  {s['issue']}: {adj['from']} -> {adj['to']} "
                            f"(displaced by {adj['displaced_by'].get('issue')})"
                        )
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


def _read_rows(csv_file: Path) -> list[dict]:
    with csv_file.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"Jira Key", "Time Spent", "Started"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise UserError(
                f"CSV is missing required columns: {', '.join(sorted(missing))}",
                payload={"missing_columns": sorted(missing)},
            )
        return list(reader)


def _fetch_existing_window(client: JiraClient | None, rows: list[dict]) -> list[dict]:
    """Fetch user worklogs covering the date range spanned by the CSV.

    A row with an unparseable ``Started`` is skipped here — that row will fail
    later in the main loop with its own validation error.
    """
    if client is None or not rows:
        return []
    days: list[datetime] = []
    for row in rows:
        try:
            dt = _parse_jira_started(row["Started"])
        except (ValueError, KeyError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days.append(dt.astimezone(timezone.utc))
    if not days:
        return []
    return client.search_user_worklogs(min(days).date(), max(days).date())
