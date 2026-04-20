"""Tests para normalizadores y emit (contrato JSON estable)."""

from __future__ import annotations

import json

import pytest

from tjira.formatters import (
    emit,
    normalize_board,
    normalize_filter,
    normalize_issue,
    normalize_sprint,
    normalize_transition,
    normalize_worklog,
)


# ========== normalize_issue ==========

def test_normalize_issue_extracts_core_fields():
    raw = {
        "key": "PROJ-123",
        "id": "10001",
        "fields": {
            "summary": "Do the thing",
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "assignee": {
                "accountId": "abc",
                "displayName": "Alice",
                "emailAddress": "alice@example.com",
            },
            "description": None,
            "attachment": [],
        },
    }
    result = normalize_issue(raw)
    assert result["key"] == "PROJ-123"
    assert result["type"] == "Bug"
    assert result["status"] == "In Progress"
    assert result["priority"] == "High"
    assert result["assignee"]["display_name"] == "Alice"
    assert result["attachments"] == []


def test_normalize_issue_handles_missing_assignee():
    raw = {"key": "PROJ-1", "fields": {"summary": "x", "assignee": None}}
    result = normalize_issue(raw)
    assert result["assignee"] is None


def test_normalize_issue_extracts_adf_description():
    raw = {
        "key": "PROJ-1",
        "fields": {
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "hello"}]},
                ],
            }
        },
    }
    assert normalize_issue(raw)["description"] == "hello"


def test_normalize_issue_safe_on_totally_empty_input():
    assert normalize_issue({"key": "PROJ-1"})["status"] is None


# ========== other normalizers ==========

def test_normalize_worklog():
    raw = {
        "id": "100",
        "issueId": "10001",
        "timeSpent": "2h",
        "timeSpentSeconds": 7200,
        "started": "2026-04-20T09:00:00.000+0000",
        "author": {"accountId": "abc", "displayName": "Bob", "emailAddress": "b@ex.com"},
    }
    wl = normalize_worklog(raw)
    assert wl == {
        "id": "100",
        "issue_id": "10001",
        "time_spent": "2h",
        "time_spent_seconds": 7200,
        "started": "2026-04-20T09:00:00.000+0000",
        "author": {"account_id": "abc", "display_name": "Bob", "email": "b@ex.com"},
    }


def test_normalize_board():
    assert normalize_board({"id": 1, "name": "X", "type": "scrum"}) == {
        "id": 1,
        "name": "X",
        "type": "scrum",
    }


def test_normalize_sprint():
    raw = {"id": 9, "name": "Sprint 1", "state": "active",
           "startDate": "2026-04-01", "endDate": "2026-04-15"}
    assert normalize_sprint(raw) == {
        "id": 9, "name": "Sprint 1", "state": "active",
        "start_date": "2026-04-01", "end_date": "2026-04-15",
    }


def test_normalize_filter():
    raw = {"id": 10, "name": "F", "jql": "project = X", "owner": {"displayName": "me"}}
    assert normalize_filter(raw)["owner"] == "me"


def test_normalize_transition():
    raw = {"id": "31", "name": "Done", "to": {"name": "Done"}}
    assert normalize_transition(raw) == {"id": "31", "name": "Done", "to": "Done"}


# ========== emit contract ==========

def test_emit_json_wraps_in_envelope(capsys: pytest.CaptureFixture[str]):
    emit({"key": "PROJ-1"}, as_json=True)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == {"ok": True, "data": {"key": "PROJ-1"}}


def test_emit_human_invokes_human_fn(capsys: pytest.CaptureFixture[str]):
    called = {}

    def human(d):
        called["data"] = d
        print(f"KEY: {d['key']}")

    emit({"key": "PROJ-1"}, as_json=False, human_fn=human)
    out = capsys.readouterr().out
    assert called["data"] == {"key": "PROJ-1"}
    assert "KEY: PROJ-1" in out


def test_emit_human_without_fn_prints_data(capsys: pytest.CaptureFixture[str]):
    emit("hello", as_json=False)
    assert capsys.readouterr().out.strip() == "hello"
