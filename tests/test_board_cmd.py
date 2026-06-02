"""`tjira board move` command tests — BM-CMD-1..13.

Strict TDD: every scenario maps to a test. Uses Typer CliRunner + `responses`
library for HTTP mocking. Profile seeded via `configured_profile` fixture in
conftest.py (autouse `_isolate_profile_store` handles XDG isolation).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import responses as resp_lib
from typer.testing import CliRunner


# ==================== shared fixtures ====================


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def app(configured_profile):
    from tjira.cli import app as _app
    return _app


_DOMAIN = "https://example.atlassian.net"


def _issue_put_url(key: str) -> str:
    return f"{_DOMAIN}/rest/api/3/issue/{key}"


def _mock_put(key: str, status: int = 204) -> None:
    resp_lib.put(_issue_put_url(key), body=b"", status=status)


def _mock_put_error(key: str, status: int = 404) -> None:
    resp_lib.put(
        _issue_put_url(key),
        json={"errorMessages": [f"Issue {key} not found"]},
        status=status,
    )


def _last_json_line(stream: str) -> dict[str, Any]:
    for line in reversed(stream.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"No JSON found in stream: {stream!r}")


# ==================== BM-CMD-1 — happy path human ====================


@resp_lib.activate
def test_board_move_single_issue_human(runner, app) -> None:
    """BM-CMD-1: single issue, human output — exit 0, stdout has OK/key/from/to."""
    _mock_put("PROJ-1")

    result = runner.invoke(
        app, ["board", "move", "PROJ-1", "--from", "boardA", "--to", "boardB"]
    )
    assert result.exit_code == 0, result.output + result.stderr
    assert "OK" in result.stdout
    assert "PROJ-1" in result.stdout
    assert "boardA" in result.stdout
    assert "boardB" in result.stdout


# ==================== BM-CMD-2 — happy path --json ====================


@resp_lib.activate
def test_board_move_single_issue_json(runner, app) -> None:
    """BM-CMD-2: single issue + --json → exact envelope shape."""
    _mock_put("PROJ-1")

    result = runner.invoke(
        app,
        ["board", "move", "PROJ-1", "--from", "boardA", "--to", "boardB", "--json"],
    )
    assert result.exit_code == 0, result.output + result.stderr

    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["from"] == "boardA"
    assert data["to"] == "boardB"
    assert data["moved"] == ["PROJ-1"]
    assert data["failed"] == []
    assert data["count"] == 1


# ==================== BM-CMD-3 — multiple issues all succeed ====================


@resp_lib.activate
def test_board_move_multiple_issues_all_success(runner, app) -> None:
    """BM-CMD-3: 3 issues all succeed → exit 0, all in moved, failed empty."""
    for key in ("PROJ-1", "PROJ-2", "PROJ-3"):
        _mock_put(key)

    result = runner.invoke(
        app,
        ["board", "move", "PROJ-1", "PROJ-2", "PROJ-3", "--from", "A", "--to", "B", "--json"],
    )
    assert result.exit_code == 0, result.output + result.stderr

    data = json.loads(result.stdout)["data"]
    assert set(data["moved"]) == {"PROJ-1", "PROJ-2", "PROJ-3"}
    assert data["failed"] == []


# ==================== BM-CMD-4 — --from equals --to → exit 1 ====================


@resp_lib.activate
def test_board_move_identical_labels_exits_1(runner, app) -> None:
    """BM-CMD-4: --from boardA --to boardA → UserError exit 1."""
    result = runner.invoke(
        app, ["board", "move", "PROJ-1", "--from", "boardA", "--to", "boardA"]
    )
    assert result.exit_code == 1, result.output + result.stderr
    err = result.stderr.lower()
    assert "identical" in err or "nothing to move" in err
    assert len(resp_lib.calls) == 0


# ==================== BM-CMD-5 — whitespace in --from → exit 1 ====================


@resp_lib.activate
def test_board_move_whitespace_in_from_exits_1(runner, app) -> None:
    """BM-CMD-5: label with space in --from → UserError exit 1."""
    result = runner.invoke(
        app, ["board", "move", "PROJ-1", "--from", "board A", "--to", "boardB"]
    )
    assert result.exit_code == 1, result.output + result.stderr
    assert "whitespace" in result.stderr.lower()
    assert "board A" in result.stderr
    assert len(resp_lib.calls) == 0


# ==================== BM-CMD-6 — whitespace in --to → exit 1 ====================


@resp_lib.activate
def test_board_move_whitespace_in_to_exits_1(runner, app) -> None:
    """BM-CMD-6: label with space in --to → UserError exit 1."""
    result = runner.invoke(
        app, ["board", "move", "PROJ-1", "--from", "boardA", "--to", "board B"]
    )
    assert result.exit_code == 1, result.output + result.stderr
    assert "whitespace" in result.stderr.lower()
    assert "board B" in result.stderr
    assert len(resp_lib.calls) == 0


# ==================== BM-CMD-7 — invalid issue key → exit 1 ====================


@resp_lib.activate
def test_board_move_invalid_key_exits_1(runner, app) -> None:
    """BM-CMD-7: bad key format → UserError exit 1."""
    result = runner.invoke(
        app, ["board", "move", "not-a-key", "--from", "A", "--to", "B"]
    )
    assert result.exit_code == 1, result.output + result.stderr
    assert "Invalid issue key" in result.stderr
    assert len(resp_lib.calls) == 0


# ==================== BM-CMD-8 — partial failure (2 issues) → exit 2 ====================


@resp_lib.activate
def test_board_move_partial_failure_two_issues(runner, app) -> None:
    """BM-CMD-8: PROJ-1 succeeds, PROJ-9 404 → exit 2, BOTH PUTs attempted."""
    _mock_put("PROJ-1")
    _mock_put_error("PROJ-9", 404)

    result = runner.invoke(
        app,
        ["board", "move", "PROJ-1", "PROJ-9", "--from", "A", "--to", "B", "--json"],
    )
    assert result.exit_code == 2, result.output + result.stderr

    # stdout should be empty (error goes to stderr)
    assert result.stdout.strip() == ""

    # Both PUTs were attempted
    put_calls = [c for c in resp_lib.calls if c.request.method == "PUT"]
    assert len(put_calls) == 2

    err_data = _last_json_line(result.stderr)
    assert err_data["ok"] is False
    assert err_data["moved"] == ["PROJ-1"]
    failed = err_data["failed"]
    assert len(failed) == 1
    assert failed[0]["issue"] == "PROJ-9"


# ==================== BM-CMD-9 — partial failure (3 issues) → exit 2 ====================


@resp_lib.activate
def test_board_move_partial_failure_three_issues(runner, app) -> None:
    """BM-CMD-9: PROJ-1+PROJ-2 succeed, PROJ-3 → 500 → exit 2, full envelope."""
    _mock_put("PROJ-1")
    _mock_put("PROJ-2")
    _mock_put_error("PROJ-3", 500)

    result = runner.invoke(
        app,
        ["board", "move", "PROJ-1", "PROJ-2", "PROJ-3", "--from", "boardA", "--to", "boardB", "--json"],
    )
    assert result.exit_code == 2, result.output + result.stderr

    err_data = _last_json_line(result.stderr)
    assert err_data["ok"] is False
    assert err_data["moved"] == ["PROJ-1", "PROJ-2"]
    assert len(err_data["failed"]) == 1
    assert err_data["failed"][0]["issue"] == "PROJ-3"
    assert err_data["from"] == "boardA"
    assert err_data["to"] == "boardB"


# ==================== BM-CMD-10 — anti-clobber: body uses `update` not `fields` ====================


@resp_lib.activate
def test_board_move_body_uses_update_verb_not_fields(runner, app) -> None:
    """BM-CMD-10: captured PUT body has 'update' key and no 'fields' key."""
    _mock_put("PROJ-1")

    result = runner.invoke(
        app, ["board", "move", "PROJ-1", "--from", "A", "--to", "B"]
    )
    assert result.exit_code == 0, result.output + result.stderr

    put_calls = [c for c in resp_lib.calls if c.request.method == "PUT"]
    assert len(put_calls) == 1
    body = json.loads(put_calls[0].request.body)
    assert "update" in body
    assert "fields" not in body


# ==================== BM-CMD-11 — from/to mapping: --from→remove, --to→add ====================


@resp_lib.activate
def test_board_move_from_to_mapping(runner, app) -> None:
    """BM-CMD-11: body has remove=sourceBoard and add=destBoard in labels ops."""
    _mock_put("PROJ-1")

    result = runner.invoke(
        app,
        ["board", "move", "PROJ-1", "--from", "sourceBoard", "--to", "destBoard"],
    )
    assert result.exit_code == 0, result.output + result.stderr

    put_calls = [c for c in resp_lib.calls if c.request.method == "PUT"]
    body = json.loads(put_calls[0].request.body)
    labels_ops = body["update"]["labels"]
    assert {"remove": "sourceBoard"} in labels_ops
    assert {"add": "destBoard"} in labels_ops


# ==================== BM-CMD-12 — case sensitivity: "Bug" != "bug" ====================


@resp_lib.activate
def test_board_move_case_sensitive_labels_no_user_error(runner, app) -> None:
    """BM-CMD-12: --from Bug --to bug → NOT identical, exit 0."""
    _mock_put("PROJ-1")

    result = runner.invoke(
        app, ["board", "move", "PROJ-1", "--from", "Bug", "--to", "bug"]
    )
    assert result.exit_code == 0, result.output + result.stderr

    put_calls = [c for c in resp_lib.calls if c.request.method == "PUT"]
    assert len(put_calls) == 1
    body = json.loads(put_calls[0].request.body)
    labels_ops = body["update"]["labels"]
    assert {"remove": "Bug"} in labels_ops
    assert {"add": "bug"} in labels_ops


# ==================== BM-CMD-13 — help discoverability ====================


def test_board_help_contains_move(runner, app) -> None:
    """BM-CMD-13a: 'board --help' → exit 0, stdout has 'move'."""
    result = runner.invoke(app, ["board", "--help"])
    assert result.exit_code == 0
    assert "move" in result.stdout


def test_root_help_contains_board(runner, app) -> None:
    """BM-CMD-13b: '--help' → exit 0, stdout has 'board'."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "board" in result.stdout
