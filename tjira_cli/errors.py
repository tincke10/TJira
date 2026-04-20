"""Exit codes y excepciones tipadas para tjira-cli.

Convenciones:
    0 → OK
    1 → Error de usuario (args inválidos, archivo no encontrado, config faltante)
    2 → Error de API de Jira (4xx/5xx, red, timeout)
"""

from __future__ import annotations

import json
import sys
from typing import Any

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_API_ERROR = 2


class TjiraError(Exception):
    """Excepción base del CLI. Lleva exit_code y payload opcional."""

    exit_code: int = EXIT_USER_ERROR

    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload or {}


class UserError(TjiraError):
    """Argumentos inválidos, archivo no encontrado, config incompleta."""

    exit_code = EXIT_USER_ERROR


class APIError(TjiraError):
    """La API de Jira respondió con error o no se pudo contactar."""

    exit_code = EXIT_API_ERROR


def fail(err: TjiraError, *, as_json: bool) -> None:
    """Emite el error por stderr y sale con el exit code correspondiente.

    En modo JSON, stderr recibe un objeto `{"error": ..., "detail": ...}`.
    En modo humano, un mensaje plano con prefijo `Error:`.
    """
    if as_json:
        envelope = {"ok": False, "error": err.message, **err.payload}
        print(json.dumps(envelope, ensure_ascii=False), file=sys.stderr)
    else:
        print(f"Error: {err.message}", file=sys.stderr)
        if err.payload:
            for key, value in err.payload.items():
                print(f"  {key}: {value}", file=sys.stderr)
    sys.exit(err.exit_code)
