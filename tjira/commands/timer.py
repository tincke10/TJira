"""`tjira timer` subcommand group — start/stop/status/cancel a worklog timer.

Stop semantics (design decision 6, in exact order):
    1. Load store. No active timer → UserError exit 1.
    2. Cross-profile check (decision 7) — NOT bypassed by --force.
    3. Overlap pre-check via find_overlap, unless --force.
    4. client.add_worklog() — APIError propagates (exit 2).
    5. store.clear() — ONLY after successful POST.
    6. Emit success envelope on stdout.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import typer

from tjira.client import JiraClient
from tjira.config import resolve_profile
from tjira.errors import OverlapError, TjiraError, UserError, fail
from tjira.formatters import emit, log
from tjira.overlap import find_overlap, format_time_spent, worklog_interval
from tjira.timer import TimerStore
from tjira.tz import get_timezone, to_jira_datetime

# Jira issue key pattern: one or more uppercase letters, a dash, one or more digits.
_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-[0-9]+$")


def _validate_issue_key(key: str) -> None:
    if not key or not _ISSUE_KEY_RE.match(key):
        raise UserError(
            f"Invalid issue key: {key!r}. Expected format: PROJ-123",
            payload={"issue_key": key},
        )


def _now() -> datetime:
    return datetime.now(tz=get_timezone())


def register(app: typer.Typer) -> None:
    timer_app = typer.Typer(
        name="timer",
        help="Time tracking — start/stop/status/cancel a worklog timer.",
        no_args_is_help=True,
    )

    # ------------------------------------------------------------------ start

    @timer_app.command("start", help="Start a timer for an issue")
    def start_cmd(
        issue: str = typer.Argument(..., help="Issue key (e.g. PROJ-123)"),
        comment: Optional[str] = typer.Option(
            None, "--comment", "-c", help="Worklog comment (stored; applied on stop)"
        ),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            _validate_issue_key(issue)
            profile = resolve_profile()
            store = TimerStore.load()
            now = _now()
            state = store.start(issue, comment=comment, profile=profile.name, now=now)
            emit(
                {
                    "issue_key": state.issue_key,
                    "started_at": to_jira_datetime(state.started_at),
                    "comment": state.comment,
                    "profile": state.profile,
                },
                as_json=json_out,
                human_fn=lambda d: print(
                    f"Timer started for {d['issue_key']} at {d['started_at']}"
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    # ------------------------------------------------------------------ status

    @timer_app.command("status", help="Show the active timer (if any)")
    def status_cmd(
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            store = TimerStore.load()
            now = _now()
            result = store.status(now=now)
            if result is None:
                emit(None, as_json=json_out, human_fn=lambda _: print("No active timer"))
                return
            state, elapsed = result
            elapsed_str = format_time_spent(elapsed)
            data = {
                "issue_key": state.issue_key,
                "started_at": to_jira_datetime(state.started_at),
                "elapsed": elapsed_str,
                "comment": state.comment,
                "profile": state.profile,
            }
            emit(
                data,
                as_json=json_out,
                human_fn=lambda d: print(
                    f"Timer running: {d['issue_key']} for {d['elapsed']} "
                    f"(started {d['started_at']})"
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    # ------------------------------------------------------------------ cancel

    @timer_app.command("cancel", help="Cancel the active timer (no worklog posted)")
    def cancel_cmd(
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            store = TimerStore.load()
            now = _now()
            status = store.status(now=now)
            if status is None:
                emit(
                    {"cancelled": False},
                    as_json=json_out,
                    human_fn=lambda _: print("No active timer to cancel"),
                )
                return
            state, elapsed = status
            elapsed_str = format_time_spent(elapsed)
            store.cancel()
            emit(
                {
                    "cancelled": True,
                    "issue_key": state.issue_key,
                    "elapsed": elapsed_str,
                },
                as_json=json_out,
                human_fn=lambda d: print(
                    f"Timer cancelled for {d['issue_key']} (was running {d['elapsed']})"
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    # ------------------------------------------------------------------ stop

    @timer_app.command("stop", help="Stop the timer and post a worklog to Jira")
    def stop_cmd(
        force: bool = typer.Option(
            False,
            "--force",
            help="Skip the overlap pre-check (does NOT bypass cross-profile safeguard)",
        ),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            # Step 1: load store; no active timer → UserError
            store = TimerStore.load()
            if not store.is_active:
                raise UserError("No active timer")

            # Resolve active profile now (may raise UserError)
            active_profile = resolve_profile()
            now = _now()

            # Step 2: cross-profile check (NOT bypassed by --force)
            if store.state.profile != active_profile.name:
                raise UserError(
                    f"Timer was started with profile '{store.state.profile}' "
                    f"but active profile is '{active_profile.name}'. "
                    f"Run 'tjira switch {store.state.profile}' or 'tjira timer cancel'.",
                    payload={
                        "stored_profile": store.state.profile,
                        "active_profile": active_profile.name,
                    },
                )

            # In-memory stop (no disk change yet)
            state, elapsed = store.stop(now=now)
            elapsed_str = format_time_spent(elapsed)
            started_iso = to_jira_datetime(state.started_at)
            target_end = state.started_at + elapsed

            # Step 3: overlap pre-check (skipped when --force)
            if not force:
                client = JiraClient()
                day = state.started_at.date()
                existing = client.search_user_worklogs(day, day)
                conflict = find_overlap(state.started_at, target_end, existing)
                if conflict is not None:
                    _, conflict_end = worklog_interval(conflict)
                    raise OverlapError(
                        "Worklog overlap with an existing entry — "
                        f"issue {conflict.get('_issue_key')}",
                        payload={
                            "conflict": {
                                "issue": conflict.get("_issue_key"),
                                "worklog_id": conflict.get("id"),
                                "started": conflict.get("started"),
                                "time_spent": conflict.get("timeSpent"),
                            },
                            "suggested_start": to_jira_datetime(conflict_end),
                            "requested": {
                                "issue": state.issue_key,
                                "started": started_iso,
                                "time_spent": elapsed_str,
                            },
                        },
                    )
            else:
                client = JiraClient()

            log(f"Logging {elapsed_str} on {state.issue_key}...")

            # Step 4: POST worklog — APIError propagates
            result = client.add_worklog(
                state.issue_key, elapsed_str, started_iso, comment=state.comment
            )

            # Step 5: clear state ONLY after successful POST
            store.clear()

            # Step 6: emit success
            worklog_id = result.get("id", "?")
            emit(
                {
                    "issue_key": state.issue_key,
                    "worklog_id": worklog_id,
                    "time_spent": elapsed_str,
                    "started_at": started_iso,
                },
                as_json=json_out,
                human_fn=lambda d: print(
                    f"OK: Timer stopped. Worklog {d['worklog_id']} posted "
                    f"({d['time_spent']}) on {d['issue_key']}"
                ),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)

    app.add_typer(timer_app, name="timer")
