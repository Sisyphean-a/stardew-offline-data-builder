from __future__ import annotations

from pathlib import Path

import typer

from builder import __version__
from builder.commands.build import build_command, build_fixture_command, build_legacy_command
from builder.commands.doctor import doctor_command
from builder.commands.inspect import inspect_command
from builder.commands.package import package_existing_output
from builder.commands.schema5_candidate import build_schema5_candidate_command
from builder.commands.schema5_fixture import (
    build_schema5_b2_fixture_command,
    build_schema5_fixture_command,
)
from builder.commands.schema5_staging import build_schema5_staging_command
from builder.commands.unpack import unpack_command
from builder.config import EXIT_PACKAGE
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
def build_fixture(
    output: str = typer.Option(".\\dist", help="输出目录；仅供开发验证，不能打包。"),
) -> None:
    build_fixture_command(output)


@app.command("build-schema5-fixture")
def build_schema5_fixture(
    output: str = typer.Option(
        ".\\build\\schema5-fixture", help="schema 5 conformance fixture 输出目录。"
    ),
) -> None:
    build_schema5_fixture_command(output)


@app.command("build-schema5-b2-fixture")
def build_schema5_b2_fixture(
    output: str = typer.Option(
        ".\\build\\schema5-b2-fixture", help="schema 5 B2 typed fixture 输出目录。"
    ),
) -> None:
    build_schema5_b2_fixture_command(output)


@app.command("build-schema5")
def build_schema5(
    game_dir: str | None = typer.Option(None, help="游戏目录；省略时自动发现。"),
    output: str = typer.Option(".\\dist", help="schema 5 候选输出目录。"),
    unpacked_dir: str | None = typer.Option(None, help="已解包目录。"),
    xnb_hack: str | None = typer.Option(None, help="StardewXnbHack 路径。"),
    force: bool = typer.Option(False, help="缺少解包数据时强制重新解包。"),
) -> None:
    build_schema5_candidate_command(game_dir, output, unpacked_dir, xnb_hack, force)


@app.command("build-schema5-staging")
def build_schema5_staging(
    game_dir: str | None = typer.Option(None, help="游戏目录；省略时自动发现。"),
    output: str = typer.Option(".\\build\\schema5-staging", help="schema 5 staging 输出目录。"),
    unpacked_dir: str | None = typer.Option(None, help="已解包目录。"),
    xnb_hack: str | None = typer.Option(None, help="StardewXnbHack 路径。"),
    force: bool = typer.Option(False, help="缺少解包数据时强制重新解包。"),
) -> None:
    build_schema5_staging_command(game_dir, output, unpacked_dir, xnb_hack, force)


@app.command("build-v4-legacy")
def build_v4_legacy(
    game_dir: str | None = typer.Option(
        None,
        help="游戏目录；省略时自动从本机 Steam 发现（仅迁移基线）。",
    ),
    output: str = typer.Option(".\\dist-v4-legacy", help="旧 schema 4 恢复输出目录。"),
    unpacked_dir: str | None = typer.Option(None, help="已解包目录。"),
    xnb_hack: str | None = typer.Option(None, help="StardewXnbHack 路径。"),
    force: bool = typer.Option(False, help="缺少解包数据时强制重新解包。"),
) -> None:
    build_legacy_command(
        game_dir=game_dir,
        output=output,
        unpacked_dir=unpacked_dir,
        xnb_hack=xnb_hack,
        force=force,
    )


@app.command("build")
def build(
    game_dir: str | None = typer.Option(
        None,
        help="游戏目录；省略时自动从本机 Steam 发现（仅 Windows）。",
    ),
    output: str = typer.Option(".\\dist", help="schema 5 正式候选输出目录。"),
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
    game_dir: str | None = typer.Option(
        None,
        help="游戏目录；省略时自动从本机 Steam 发现（仅 Windows）。",
    ),
    xnb_hack: str | None = typer.Option(None, help="StardewXnbHack 路径。"),
) -> None:
    doctor_command(game_dir=game_dir, xnb_hack=xnb_hack)


@app.command("unpack")
def unpack(
    game_dir: str | None = typer.Option(
        None,
        help="游戏目录；省略时自动从本机 Steam 发现（仅 Windows）。",
    ),
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
    try:
        package_existing_output(output_dir=output_dir, locale=locale)
    except (OSError, ValueError) as exc:
        typer.echo(f"✗ {exc}")
        raise typer.Exit(code=EXIT_PACKAGE) from exc
