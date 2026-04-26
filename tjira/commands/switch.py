"""``tjira switch`` — change the active profile."""

from __future__ import annotations

import typer

from tjira.errors import TjiraError, fail
from tjira.formatters import emit
from tjira.profiles import ProfileStore


def register(app: typer.Typer) -> None:
    @app.command("switch", help="Change the active profile")
    def switch_cmd(
        name: str = typer.Argument(..., help="Profile name to activate"),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            store = ProfileStore.load()
            store.set_current(name)
            store.save()
            emit(
                {"current": name},
                as_json=json_out,
                human_fn=lambda d: print(f"Switched to profile '{d['current']}'."),
            )
        except TjiraError as err:
            fail(err, as_json=json_out)
