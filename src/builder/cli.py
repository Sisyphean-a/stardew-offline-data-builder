from __future__ import annotations

from pathlib import Path

import typer

from builder import __version__
from builder.commands.build import build_command, build_fixture_command
from builder.commands.doctor import doctor_command
from builder.commands.inspect import inspect_command
from builder.commands.package import package_existing_output
from builder.commands.unpack import unpack_command
from builder.database.writer import inspect_database
from builder.models import BuildSummary
from builder.utils.console import configure_stdio

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
    configure_stdio()
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command("build-fixture")
def build_fixture(output: str = typer.Option(".\\dist", help="输出目录。")) -> None:
    build_fixture_command(output)


@app.command("build")
def build(
    game_dir: str = typer.Option(..., help="游戏目录。"),
    output: str = typer.Option(".\\dist", help="输出目录。"),
    unpacked_dir: str | None = typer.Option(None, help="已解包目录。"),
    xnb_hack: str | None = typer.Option(None, help="StardewXnbHack 路径。"),
    force: bool = typer.Option(False, help="缺少解包数据时强制重新解包。"),
) -> None:
    build_command(
        game_dir=game_dir,
        output=output,
        unpacked_dir=unpacked_dir,
        xnb_hack=xnb_hack,
        force=force,
    )


@app.command("doctor")
def doctor(
    game_dir: str | None = typer.Option(None, help="游戏目录。"),
    xnb_hack: str | None = typer.Option(None, help="StardewXnbHack 路径。"),
) -> None:
    doctor_command(game_dir=game_dir, xnb_hack=xnb_hack)


@app.command("unpack")
def unpack(
    game_dir: str = typer.Option(..., help="游戏目录。"),
    unpacked_dir: str | None = typer.Option(None, help="解包输出目录。"),
    xnb_hack: str | None = typer.Option(None, help="StardewXnbHack 路径。"),
    force: bool = typer.Option(False, help="强制重新解包。"),
) -> None:
    unpack_command(game_dir=game_dir, unpacked_dir=unpacked_dir, xnb_hack=xnb_hack, force=force)


@app.command("inspect")
def inspect(db_path: str = typer.Argument(..., help="SQLite 数据库路径。")) -> None:
    inspect_command(db_path)


@app.command("package")
def package(
    output: str = typer.Option(".\\dist", help="构建输出目录。"),
    locale: str = typer.Option("zh-CN", help="语言。"),
) -> None:
    output_dir = Path(output)
    inspected = inspect_database(output_dir / "stardew.db")
    summary = BuildSummary(
        entities=int(inspected["entities"]),
        missing_translations=int(inspected["missing_translations"]),
        counts_by_type={
            "object": int(inspected["objects"]),
            "crop": int(inspected["crops"]),
            "fish": int(inspected["fish"]),
            "villager": int(inspected["villagers"]),
        },
    )
    package_existing_output(output_dir=output_dir, locale=locale, summary=summary)
