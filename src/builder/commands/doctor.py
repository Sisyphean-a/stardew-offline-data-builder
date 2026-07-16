from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from builder.config import EXIT_GAME_DIR, EXIT_UNPACK_TOOL
from builder.database.validator import sqlite_supports_fts4
from builder.utils.paths import (
    default_xnb_hack_path,
    ensure_content_directory,
    ensure_game_directory,
    ensure_game_dll,
    ensure_xnb_hack_path,
)

console = Console()


def doctor_command(
    game_dir: str | None,
    xnb_hack: str | None,
) -> None:
    try:
        resolved_game_dir = ensure_game_directory(Path(game_dir) if game_dir else None)
        ensure_content_directory(resolved_game_dir)
        ensure_game_dll(resolved_game_dir)
    except FileNotFoundError as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_GAME_DIR) from exc

    xnb_candidate = Path(xnb_hack) if xnb_hack else default_xnb_hack_path(resolved_game_dir)
    try:
        ensure_xnb_hack_path(xnb_candidate)
    except FileNotFoundError as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_UNPACK_TOOL) from exc

    checks = [
        "✓ Python 环境正常",
        "✓ 找到游戏目录",
        "✓ 找到 Content 目录",
        "✓ 找到 Stardew Valley.dll",
        "✓ 找到 StardewXnbHack",
    ]
    for line in checks:
        console.print(line)

    if sqlite_supports_fts4():
        console.print("✓ SQLite 支持 FTS4")
        console.print("\n环境检查通过")
        return

    console.print("✗ SQLite 不支持 FTS4")
    raise typer.Exit(code=EXIT_GAME_DIR)
