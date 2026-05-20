"""Tests for normalizers and `emit` (stable JSON contract)."""

from __future__ import annotations

import json

import pytest

from tjira.formatters import (
    emit,
    normalize_board,
    normalize_field,
    normalize_filter,
    normalize_issue,
    normalize_issuetype,
    normalize_project,
    normalize_sprint,
    normalize_transition,
    normalize_user,
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


# ========== G2: new normalizers ==========

def test_normalize_project_maps_all_fields():
    raw = {"key": "PROJ", "name": "My Project", "projectTypeKey": "software", "style": "next-gen"}
    result = normalize_project(raw)
    assert result == {"key": "PROJ", "name": "My Project", "type": "software", "style": "next-gen"}


def test_normalize_project_defaults_missing_keys_to_none():
    result = normalize_project({"key": "PROJ"})
    assert result["name"] is None
    assert result["type"] is None
    assert result["style"] is None


def test_normalize_user_with_email():
    raw = {
        "accountId": "acc-1",
        "displayName": "John Doe",
        "emailAddress": "john@x.com",
        "active": True,
    }
    result = normalize_user(raw)
    assert result == {
        "account_id": "acc-1",
        "display_name": "John Doe",
        "email": "john@x.com",
        "active": True,
    }


def test_normalize_user_without_email_defaults_to_none():
    raw = {"accountId": "acc-2", "displayName": "Jane", "active": False}
    result = normalize_user(raw)
    assert result["email"] is None
    assert result["account_id"] == "acc-2"


def test_normalize_issuetype_maps_all_fields():
    raw = {"id": "10001", "name": "Task", "subtask": False, "description": "desc"}
    result = normalize_issuetype(raw)
    assert result == {"id": "10001", "name": "Task", "subtask": False, "description": "desc"}


def test_normalize_issuetype_subtask_stays_as_bool():
    result = normalize_issuetype({"id": "2", "name": "Sub-task", "subtask": True, "description": ""})
    assert result["subtask"] is True


def test_normalize_field_with_allowed_values():
    raw = {
        "name": "Priority",
        "key": "priority",
        "required": True,
        "schema": {"type": "priority"},
        "allowedValues": [
            {"name": "High"},
            {"value": "medium"},
            {"id": "low-id"},
        ],
    }
    result = normalize_field(raw)
    assert result["allowed_values"] == ["High", "medium", "low-id"]
    assert result["required"] is True
    assert result["type"] == "priority"
    assert result["key"] == "priority"


def test_normalize_field_without_allowed_values():
    raw = {"name": "Summary", "key": "summary", "required": True, "schema": {"type": "string"}}
    result = normalize_field(raw)
    assert result["allowed_values"] is None


def test_normalize_field_missing_schema_type_defaults_to_none():
    raw = {"name": "Custom", "key": "custom", "required": False}
    result = normalize_field(raw)
    assert result["type"] is None
    assert result["allowed_values"] is None
