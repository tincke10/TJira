"""Tests for `tjira/validation.py` — ISSUE_KEY_RE and validate_issue_key.

Covers REQ-VAL-1..4 (TDD Wave 1).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner


# ==================== REQ-VAL-1 — module exports both names ====================


def test_validation_module_exports_issue_key_re_and_validate():
    """REQ-VAL-1: both names importable without error."""
    from tjira.validation import ISSUE_KEY_RE, validate_issue_key  # noqa: F401

    assert ISSUE_KEY_RE is not None
    assert callable(validate_issue_key)


# ==================== REQ-VAL-2 — valid keys pass ====================


@pytest.mark.parametrize(
    "key",
    ["PROJ-1", "AB-999", "A-0", "MYPROJECT-12345"],
)
def test_valid_issue_keys_do_not_raise(key: str) -> None:
    """REQ-VAL-2: known-good keys must never raise."""
    from tjira.validation import validate_issue_key

    validate_issue_key(key)  # must not raise


# ==================== REQ-VAL-3 — invalid keys raise UserError exit 1 ====================


@pytest.mark.parametrize(
    "bad_key",
    ["", "not-an-issue", "PROJ", "123-ABC", "proj-1", "PROJ-"],
)
def test_invalid_issue_keys_raise_user_error(bad_key: str) -> None:
    """REQ-VAL-3: malformed keys raise UserError(exit_code=1) with message."""
    from tjira.errors import UserError
    from tjira.validation import validate_issue_key

    with pytest.raises(UserError) as exc_info:
        validate_issue_key(bad_key)

    err = exc_info.value
    assert err.exit_code == 1
    assert "Invalid issue key" in err.message
    assert bad_key in err.message


# ==================== REQ-VAL-4 — timer regression ====================


def test_timer_start_invalid_key_still_raises_user_error(configured_profile) -> None:
    """REQ-VAL-4: after refactor, timer start rejects bad keys the same as before."""
    from tjira.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["timer", "start", "not-an-issue", "--json"])

    assert result.exit_code == 1
    # stderr carries the error JSON/message
    assert "Invalid issue key" in (result.output + (result.stderr if hasattr(result, "stderr") else ""))
