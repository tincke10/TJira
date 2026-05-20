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


def normalize_project(project: dict) -> dict:
    return {
        "key": project.get("key"),
        "name": project.get("name"),
        "type": project.get("projectTypeKey"),
        "style": project.get("style"),
    }


def normalize_user(user: dict) -> dict:
    email = user.get("emailAddress") or None
    return {
        "account_id": user.get("accountId"),
        "display_name": user.get("displayName"),
        "email": email,
        "active": user.get("active"),
    }


def normalize_issuetype(issuetype: dict) -> dict:
    return {
        "id": issuetype.get("id"),
        "name": issuetype.get("name"),
        "subtask": issuetype.get("subtask"),
        "description": issuetype.get("description"),
    }


def normalize_field(field: dict) -> dict:
    raw_av = field.get("allowedValues")
    if raw_av is None:
        allowed_values = None
    else:
        allowed_values = [
            next(v for v in (av.get("name"), av.get("value"), av.get("id")) if v is not None)
            for av in raw_av
        ]
    schema = field.get("schema") or {}
    return {
        "name": field.get("name"),
        "key": field.get("key"),
        "required": field.get("required"),
        "type": schema.get("type"),
        "allowed_values": allowed_values,
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


def print_projects_table(projects: Iterable[dict]) -> None:
    projects = list(projects)
    if not projects:
        print("No projects found")
        return
    print(f"{'KEY':<12} {'TYPE':<15} {'STYLE':<12} {'NAME'}")
    print("-" * 80)
    for p in projects:
        key = (p.get("key") or "-")[:12]
        type_ = (p.get("type") or "-")[:15]
        style = (p.get("style") or "-")[:12]
        name = (p.get("name") or "-")[:40]
        print(f"{key:<12} {type_:<15} {style:<12} {name}")
    print(f"\nTotal: {len(projects)} projects")


def print_users_table(users: Iterable[dict]) -> None:
    users = list(users)
    if not users:
        print("No users found")
        return
    print(f"{'ACCOUNT ID':<30} {'DISPLAY NAME':<25} {'EMAIL':<35} {'ACTIVE'}")
    print("-" * 100)
    for u in users:
        account_id = (u.get("account_id") or "-")[:30]
        display_name = (u.get("display_name") or "-")[:25]
        email = (u.get("email") or "-")[:35]
        active = "yes" if u.get("active") else "no"
        print(f"{account_id:<30} {display_name:<25} {email:<35} {active}")
    print(f"\nTotal: {len(users)} users")


def print_issuetypes_table(issuetypes: Iterable[dict]) -> None:
    issuetypes = list(issuetypes)
    if not issuetypes:
        print("No issue types found")
        return
    print(f"{'ID':<10} {'NAME':<20} {'SUBTASK':<10} {'DESCRIPTION'}")
    print("-" * 80)
    for it in issuetypes:
        id_ = (str(it.get("id") or "-"))[:10]
        name = (it.get("name") or "-")[:20]
        subtask = "yes" if it.get("subtask") else "no"
        desc = (it.get("description") or "-")[:40]
        print(f"{id_:<10} {name:<20} {subtask:<10} {desc}")
    print(f"\nTotal: {len(issuetypes)} issue types")


def print_fields_table(fields: Iterable[dict]) -> None:
    fields = list(fields)
    if not fields:
        log("No fields found")
        return
    print(f"{'NAME':<30} {'KEY':<25} {'REQUIRED':<10} {'TYPE'}")
    print("-" * 80)
    for f in fields:
        name = (f.get("name") or "-")[:30]
        key = (f.get("key") or "-")[:25]
        required = "yes" if f.get("required") else "no"
        type_ = (f.get("type") or "-")[:20]
        print(f"{name:<30} {key:<25} {required:<10} {type_}")
    print(f"\nTotal: {len(fields)} fields")
