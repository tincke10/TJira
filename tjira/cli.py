"""Entry point principal del CLI `tjira`.

Convenciones de output:
    - stdout = data (humano o JSON según --json)
    - stderr = progreso/logs/errores

Exit codes:
    0 → OK
    1 → Error de usuario (args, archivo, config)
    2 → Error de API de Jira (4xx/5xx, red, timeout)
"""

from __future__ import annotations

import typer

from tjira import __version__
from tjira.commands import issue as issue_cmd
from tjira.commands import list_cmd
from tjira.commands import log as log_cmd
from tjira.commands import worklog as worklog_cmd

app = typer.Typer(
    name="tjira",
    help="CLI unificado para gestionar Jira via REST con output JSON AI-friendly.",
    add_completion=True,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tjira {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Mostrar versión y salir",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Raíz del CLI — ver subcomandos con `tjira --help`."""


# Registrar subcomandos
log_cmd.register(app)
issue_cmd.register(app)
list_cmd.register(app)
worklog_cmd.register(app)


if __name__ == "__main__":
    app()
