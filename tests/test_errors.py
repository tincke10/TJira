"""Tests para tipos de error y el helper `fail`."""

from __future__ import annotations

import json

import pytest

from tjira.errors import (
    APIError,
    EXIT_API_ERROR,
    EXIT_USER_ERROR,
    UserError,
    fail,
)


def test_user_error_exit_code_is_1():
    err = UserError("bad args")
    assert err.exit_code == EXIT_USER_ERROR == 1


def test_api_error_exit_code_is_2():
    err = APIError("500 from jira")
    assert err.exit_code == EXIT_API_ERROR == 2


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
    assert captured.out == ""  # stdout no se contamina
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
