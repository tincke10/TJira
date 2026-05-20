"""Exit codes and typed exceptions for tjira.

Conventions:
    0 -> OK
    1 -> User error (invalid args, file not found, missing config)
    2 -> Jira API error (4xx/5xx, network, timeout)
    3 -> Worklog overlap (specific user error — IA can detect this code and
         retry with the suggested_start from the error payload)
"""

from __future__ import annotations

import json
import sys
from typing import Any

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_API_ERROR = 2
EXIT_OVERLAP = 3


class TjiraError(Exception):
    """Base CLI exception. Carries exit_code and optional payload."""

    exit_code: int = EXIT_USER_ERROR

    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload or {}


class UserError(TjiraError):
    """Invalid arguments, missing file, incomplete configuration."""

    exit_code = EXIT_USER_ERROR


class APIError(TjiraError):
    """Jira API returned an error or could not be reached."""

    exit_code = EXIT_API_ERROR


class OverlapError(TjiraError):
    """A worklog overlaps with an existing one for the same user.

    Payload SHOULD include ``conflict`` (the existing worklog dict) and
    ``suggested_start`` (ISO datetime where the new worklog could start
    without overlapping).
    """

    exit_code = EXIT_OVERLAP


def fail(err: TjiraError, *, as_json: bool) -> None:
    """Emit the error on stderr and exit with the proper exit code.

    In JSON mode, stderr receives an object `{"error": ..., "detail": ...}`.
    In human mode, a plain message prefixed with `Error:`.
    """
    if as_json:
        envelope = {"ok": False, "error": err.message, **err.payload}
        print(json.dumps(envelope, ensure_ascii=False), file=sys.stderr, flush=True)
    else:
        print(f"Error: {err.message}", file=sys.stderr, flush=True)
        if err.payload:
            for key, value in err.payload.items():
                print(f"  {key}: {value}", file=sys.stderr, flush=True)
    sys.exit(err.exit_code)
