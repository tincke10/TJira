"""Dual formatters: human (table/plain text) vs structured JSON.

Golden rule:
    - stdout = data (human or JSON) -> parseable
    - stderr = progress/logs -> never pollutes output

The JSON formatters return stable, documented structures so an agent (Claude,
GPT, any script) can consume them reliably. The human formatters are
best-effort for terminal display.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Iterable


def emit(data: Any, *, as_json: bool, human_fn=None) -> None:
    """Print to stdout in the requested format.

    Args:
        data: Already-normalized structure ready to serialize as JSON.
        as_json: If True, print JSON; if False, invoke `human_fn(data)`.
        human_fn: Callable that receives `data` and prints the human version.
    """
    if as_json:
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, indent=2))
        return
    if human_fn is None:
        print(data)
        return
    human_fn(data)


def log(message: str) -> None:
    """Progress message on stderr (never pollutes stdout)."""
    print(message, file=sys.stderr)


# ==================== NORMALIZERS ====================
# Convert raw Jira responses into stable dicts/lists.

def normalize_issue(issue: dict) -> dict:
    """Flatten a Jira issue into a predictable dict."""
    fields = issue.get("fields", {}) or {}
    assignee = fields.get("assignee") or {}
    status = fields.get("status") or {}
    issuetype = fields.get("issuetype") or {}
    priority = fields.get("priority") or {}

    return {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "summary": fields.get("summary"),
        "type": issuetype.get("name"),
        "status": status.get("name"),
        "priority": priority.get("name"),
        "assignee": {
            "account_id": assignee.get("accountId"),
            "display_name": assignee.get("displayName"),
            "email": assignee.get("emailAddress"),
        } if assignee else None,
        "description": _extract_adf_text(fields.get("description")),
        "attachments": [
            {"id": a.get("id"), "filename": a.get("filename"), "size": a.get("size")}
            for a in (fields.get("attachment") or [])
        ],
    }


def normalize_worklog(worklog: dict) -> dict:
    """Flatten a worklog into a predictable dict."""
    author = worklog.get("author") or {}
    return {
        "id": worklog.get("id"),
        "issue_id": worklog.get("issueId"),
        "time_spent": worklog.get("timeSpent"),
        "time_spent_seconds": worklog.get("timeSpentSeconds"),
        "started": worklog.get("started"),
        "author": {
            "account_id": author.get("accountId"),
            "display_name": author.get("displayName"),
            "email": author.get("emailAddress"),
        } if author else None,
    }


def normalize_board(board: dict) -> dict:
    return {
        "id": board.get("id"),
        "name": board.get("name"),
        "type": board.get("type"),
    }


def normalize_sprint(sprint: dict) -> dict:
    return {
        "id": sprint.get("id"),
        "name": sprint.get("name"),
        "state": sprint.get("state"),
        "start_date": sprint.get("startDate"),
        "end_date": sprint.get("endDate"),
    }


def normalize_filter(flt: dict) -> dict:
    return {
        "id": flt.get("id"),
        "name": flt.get("name"),
        "jql": flt.get("jql"),
        "owner": (flt.get("owner") or {}).get("displayName"),
    }


def normalize_transition(transition: dict) -> dict:
    return {
        "id": transition.get("id"),
        "name": transition.get("name"),
        "to": (transition.get("to") or {}).get("name"),
    }


def _extract_adf_text(adf: dict | None) -> str | None:
    """Extract plain text from an ADF (Atlassian Document Format) document."""
    if not adf or not isinstance(adf, dict):
        return None
    chunks: list[str] = []
    for block in adf.get("content", []) or []:
        for item in block.get("content", []) or []:
            if item.get("type") == "text":
                chunks.append(item.get("text", ""))
        chunks.append("\n")
    text = "".join(chunks).strip()
    return text or None


# ==================== HUMAN PRINTERS ====================

def print_issues_table(issues: Iterable[dict]) -> None:
    issues = list(issues)
    if not issues:
        print("No issues found")
        return
    print(f"{'KEY':<15} {'TYPE':<10} {'STATUS':<15} {'SUMMARY'}")
    print("-" * 80)
    for it in issues:
        key = (it.get("key") or "-")[:15]
        type_ = (it.get("type") or "-")[:10]
        status = (it.get("status") or "-")[:15]
        summary = (it.get("summary") or "-")[:45]
        print(f"{key:<15} {type_:<10} {status:<15} {summary}")
    print(f"\nTotal: {len(issues)} issues")


def print_issue_detail(issue: dict) -> None:
    print(f"Issue: {issue.get('key')}")
    print(f"  Summary: {issue.get('summary')}")
    print(f"  Type: {issue.get('type')}")
    print(f"  Status: {issue.get('status')}")
    assignee = issue.get("assignee")
    print(f"  Assignee: {assignee['display_name'] if assignee else 'Unassigned'}")
    desc = issue.get("description")
    if desc:
        print("  Description:")
        for line in desc.splitlines():
            print(f"    {line}")
    attachments = issue.get("attachments") or []
    if attachments:
        print(f"  Attachments ({len(attachments)}):")
        for a in attachments:
            size_kb = (a.get("size") or 0) // 1024
            print(f"    - {a.get('filename')} ({size_kb}KB)")


def print_boards_table(boards: Iterable[dict]) -> None:
    boards = list(boards)
    if not boards:
        print("No boards found")
        return
    print(f"{'ID':<8} {'TYPE':<10} {'NAME'}")
    print("-" * 60)
    for b in boards:
        print(f"{str(b.get('id') or '-'):<8} {(b.get('type') or '-'):<10} {b.get('name') or '-'}")
    print(f"\nTotal: {len(boards)} boards")


def print_sprints_table(sprints: Iterable[dict]) -> None:
    sprints = list(sprints)
    if not sprints:
        print("No sprints found")
        return
    print(f"{'ID':<8} {'STATE':<10} {'NAME'}")
    print("-" * 60)
    for s in sprints:
        print(f"{str(s.get('id') or '-'):<8} {(s.get('state') or '-'):<10} {s.get('name') or '-'}")
    print(f"\nTotal: {len(sprints)} sprints")


def print_filters_table(filters_: Iterable[dict]) -> None:
    filters_ = list(filters_)
    if not filters_:
        print("No filters found")
        return
    print(f"{'ID':<8} {'NAME':<35} {'JQL'}")
    print("-" * 100)
    for f in filters_:
        name = (f.get("name") or "-")[:35]
        jql = (f.get("jql") or "-")[:50]
        print(f"{str(f.get('id') or '-'):<8} {name:<35} {jql}")
    print(f"\nTotal: {len(filters_)} filters")


def print_transitions_table(transitions: Iterable[dict]) -> None:
    transitions = list(transitions)
    if not transitions:
        print("No transitions available")
        return
    print("Available transitions:")
    for t in transitions:
        to = t.get("to") or "-"
        print(f"  [{t.get('id')}] {t.get('name')} -> {to}")
