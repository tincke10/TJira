"""`tjira sprint` subcommand group — add issues (and epic children) to a sprint."""

from __future__ import annotations

import typer

from tjira.client import JiraClient
from tjira.errors import TjiraError, UserError, fail
from tjira.formatters import emit, log
from tjira.validation import validate_issue_key


# ---------- helpers ----------


def _is_epic(issue: dict) -> bool:
    """Return True if the issue is an epic (or super-epic) by hierarchy level or name."""
    it = (issue.get("fields") or {}).get("issuetype") or {}
    level = it.get("hierarchyLevel")
    if isinstance(level, int) and level >= 1:
        return True
    return (it.get("name") or "") == "Epic"


def _expand_epics(
    client: JiraClient,
    issue_keys: list[str],
) -> tuple[list[str], dict[str, list[str]]]:
    """Expand any epic keys in *issue_keys* to their child issue keys.

    Returns:
        (final_keys, expanded_from_epics) where:
        - final_keys is deduplicated with first-seen order.
        - expanded_from_epics maps each epic key to the list of child keys found.
    """
    expanded_from_epics: dict[str, list[str]] = {}
    candidate_keys: list[str] = []

    for key in issue_keys:
        raw = client.get_issue(key)
        if _is_epic(raw):
            children = client.search_issues(f"parent = {key}")
            child_keys = [c["key"] for c in children]
            if not child_keys:
                log(f"Warning: Epic {key} has no children; skipping it")
            else:
                expanded_from_epics[key] = child_keys
                candidate_keys.extend(child_keys)
        else:
            candidate_keys.append(key)

    # Dedupe — set semantics, preserve first-seen order
    seen: dict[str, None] = {}
    for k in candidate_keys:
        seen.setdefault(k, None)
    final_keys = list(seen)

    return final_keys, expanded_from_epics


# ---------- command registration ----------


def register(app: typer.Typer) -> None:
    sprint_app = typer.Typer(
        name="sprint",
        help="Sprint membership — add issues (and epic children) to a sprint.",
        no_args_is_help=True,
    )

    @sprint_app.command("add", help="Add one or more issues to a sprint")
    def add_cmd(
        sprint_id: int = typer.Argument(..., help="Numeric sprint id"),
        issues: list[str] = typer.Argument(..., help="Issue keys (e.g. PROJ-123)"),
        children: bool = typer.Option(
            False,
            "--children",
            help="Expand epics to their child issues (epics cannot be in a sprint)",
        ),
        json_out: bool = typer.Option(False, "--json", help="JSON output to stdout"),
    ) -> None:
        try:
            # Step 1: validate all issue key formats up-front
            for key in issues:
                validate_issue_key(key)

            client = JiraClient()

            if children:
                # Step 2a: expand epics → children; dedupe
                final_keys, expanded_from_epics = _expand_epics(client, issues)
                if not final_keys:
                    raise UserError("Nothing to add to the sprint — all epics had no children")
            else:
                # Step 2b: check for epics; if any present, teach the user
                epics_found = []
                for key in issues:
                    raw = client.get_issue(key)
                    if _is_epic(raw):
                        epics_found.append(key)
                if epics_found:
                    epic_list = ", ".join(epics_found)
                    raise UserError(
                        f"Epic {epic_list} cannot be added to a sprint — epics span multiple "
                        f"sprints. Re-run with --children to add the epic's child issues instead.",
                        payload={"epics": epics_found},
                    )
                final_keys = list(issues)
                expanded_from_epics = {}

            # Step 3: add to sprint
            log(f"Adding {len(final_keys)} issue(s) to sprint {sprint_id}...")
            result = client.add_issues_to_sprint(sprint_id, final_keys)

            # Build annotation map: child key → epic key (for human output)
            child_to_epic: dict[str, str] = {}
            for epic_key, child_keys in expanded_from_epics.items():
                for ck in child_keys:
                    child_to_epic[ck] = epic_key

            data = {
                "sprint_id": sprint_id,
                "added": final_keys,
                "expanded_from_epics": expanded_from_epics,
                "chunks": result["chunks"],
                "count": len(final_keys),
            }

            def _human(d: dict) -> None:
                print(f"OK: Added {d['count']} issue(s) to sprint {d['sprint_id']}")
                for k in d["added"]:
                    if k in child_to_epic:
                        print(f"  {k} (from epic {child_to_epic[k]})")
                    else:
                        print(f"  {k}")

            emit(data, as_json=json_out, human_fn=_human)

        except TjiraError as err:
            fail(err, as_json=json_out)

    app.add_typer(sprint_app, name="sprint")
