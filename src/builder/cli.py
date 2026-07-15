from __future__ import annotations

import typer

from builder import __version__

app = typer.Typer(
    add_completion=False,
    help="Stardew Valley offline data builder.",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the builder version and exit.",
        is_eager=True,
    ),
) -> None:
    """Root CLI entrypoint for phase 0."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
