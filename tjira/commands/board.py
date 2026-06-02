"""`tjira board` subcommand group — move issues between boards by label swap."""

from __future__ import annotations

import re

import typer

from tjira.client import JiraClient
from tjira.errors import APIError, TjiraError, UserError, fail
from tjira.formatters import emit
from tjira.validation import validate_issue_key


def register(app: typer.Typer) -> None:
    board_app = typer.Typer(
        name="board",
        help="Board membership — move issues between same-project boards by label swap.",
        no_args_is_help=True,
    )

    @board_app.command("move", help="Move issues between boards by swapping a label")
    def move_cmd(
        issues: list[str] = typer.Argument(..., help="Issue keys (e.g. PROJ-123)"),
        from_label: str = typer.Option(..., "--from", help="Source board's label (removed)"),
        to_label: str = typer.Option(..., "--to", help="Destination board's label (added)"),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            # Step 1: Validate issue key formats
            for key in issues:
                validate_issue_key(key)

            # Step 2: Validate labels — no whitespace
            for label, flag in ((from_label, "--from"), (to_label, "--to")):
                if re.search(r"\s", label):
                    raise UserError(
                        f"Labels cannot contain whitespace: {label!r} (given via {flag})",
                        payload={"label": label, "flag": flag},
                    )

            # Step 3: --from must differ from --to (case-sensitive)
            if from_label == to_label:
                raise UserError(
                    f"--from and --to are identical ({from_label!r}); nothing to move.",
                    payload={"from": from_label, "to": to_label},
                )

            # Step 4: Per-issue loop — attempt ALL, collect results
            client = JiraClient()
            moved: list[str] = []
            failed: list[dict] = []

            for key in issues:
                try:
                    client.move_issue_labels(key, add=to_label, remove=from_label)
                    moved.append(key)
                except APIError as exc:
                    failed.append({"issue": key, "error": exc.message, **exc.payload})

            # Step 5: Report
            if failed:
                n_failed = len(failed)
                n_total = len(issues)
                raise APIError(
                    f"{n_failed} of {n_total} issue(s) failed to move",
                    payload={
                        "moved": moved,
                        "failed": failed,
                        "from": from_label,
                        "to": to_label,
                    },
                )

            data = {
                "from": from_label,
                "to": to_label,
                "moved": moved,
                "failed": [],
                "count": len(moved),
            }

            def _human(d: dict) -> None:
                print(f"OK: Moved {d['count']} issue(s) from {d['from']!r} to {d['to']!r}")
                for k in d["moved"]:
                    print(f"  {k}")

            emit(data, as_json=json_out, human_fn=_human)

        except TjiraError as err:
            fail(err, as_json=json_out)

    app.add_typer(board_app, name="board")
