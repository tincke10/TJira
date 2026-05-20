"""Tests for error types and the `fail` helper."""

from __future__ import annotations

import json

import pytest

from tjira.errors import (
    APIError,
    EXIT_API_ERROR,
    EXIT_OVERLAP,
    EXIT_USER_ERROR,
    OverlapError,
    UserError,
    fail,
)


def test_user_error_exit_code_is_1():
    err = UserError("bad args")
    assert err.exit_code == EXIT_USER_ERROR == 1


def test_api_error_exit_code_is_2():
    err = APIError("500 from jira")
    assert err.exit_code == EXIT_API_ERROR == 2


def test_overlap_error_exit_code_is_3():
    err = OverlapError("solape")
    assert err.exit_code == EXIT_OVERLAP == 3


def test_overlap_error_carries_structured_payload():
    err = OverlapError(
        "solape detectado",
        payload={
            "conflict": {"issue": "PROJ-1", "worklog_id": "42"},
            "suggested_start": "2026-04-20T10:30:00.000+0000",
        },
    )
    assert err.payload["conflict"]["issue"] == "PROJ-1"
    assert err.payload["suggested_start"].startswith("2026-04-20T10:30")


def test_fail_overlap_exits_3(capsys: pytest.CaptureFixture[str]):
    err = OverlapError(
        "Worklog overlap",
        payload={"conflict": {"issue": "PROJ-9"}, "suggested_start": "2026-04-20T11:00:00.000+0000"},
    )
    with pytest.raises(SystemExit) as exc_info:
        fail(err, as_json=True)
    assert exc_info.value.code == 3

    captured = capsys.readouterr()
    envelope = json.loads(captured.err)
    assert envelope["ok"] is False
    assert envelope["conflict"]["issue"] == "PROJ-9"
    assert envelope["suggested_start"].startswith("2026-04-20T11:00")


def test_error_payload_defaults_to_empty_dict():
    err = UserError("nothing")
    assert err.payload == {}


def test_error_carries_payload():
    err = APIError("boom", payload={"status": 500, "endpoint": "issue"})
    assert err.payload == {"status": 500, "endpoint": "issue"}


def test_fail_json_writes_envelope_to_stderr(capsys: pytest.CaptureFixture[str]):
    err = UserError("missing env", payload={"missing": ["JIRA_DOMAIN"]})
    with pytest.raises(SystemExit) as exc_info:
        fail(err, as_json=True)
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""  # stdout is not polluted
    envelope = json.loads(captured.err)
    assert envelope == {"ok": False, "error": "missing env", "missing": ["JIRA_DOMAIN"]}


def test_fail_human_writes_plain_message(capsys: pytest.CaptureFixture[str]):
    err = APIError("network down", payload={"endpoint": "issue/PROJ-1"})
    with pytest.raises(SystemExit) as exc_info:
        fail(err, as_json=False)
    assert exc_info.value.code == 2

    captured = capsys.readouterr()
    assert "Error: network down" in captured.err
    assert "endpoint: issue/PROJ-1" in captured.err
    assert captured.out == ""
