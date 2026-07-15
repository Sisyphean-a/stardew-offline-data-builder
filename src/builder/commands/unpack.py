from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from builder.config import EXIT_GAME_DIR, EXIT_UNPACK_TOOL
from builder.utils.paths import (
    default_unpacked_dir,
    ensure_content_directory,
    ensure_game_directory,
    ensure_json_output,
    ensure_xnb_hack_path,
)
from builder.utils.subprocesses import run_external_command

console = Console()


def unpack_command(
    game_dir: str,
    unpacked_dir: str | None,
    xnb_hack: str | None,
    force: bool,
) -> None:
    try:
        resolved_game_dir = ensure_game_directory(Path(game_dir))
        ensure_content_directory(resolved_game_dir)
        xnb_candidate = Path(xnb_hack) if xnb_hack else resolved_game_dir / "StardewXnbHack.py"
        xnb_path = ensure_xnb_hack_path(xnb_candidate)
    except FileNotFoundError as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_GAME_DIR) from exc

    target_dir = Path(unpacked_dir) if unpacked_dir else default_unpacked_dir(resolved_game_dir)
    if target_dir.exists() and any(target_dir.rglob("*.json")) and not force:
        console.print(f"已跳过解包：{target_dir}")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    result = run_external_command(xnb_path, ["--clean"], cwd=resolved_game_dir)
    if result.returncode != 0:
        console.print("✗ 解包失败")
        if result.stdout:
            console.print(result.stdout)
        if result.stderr:
            console.print(result.stderr)
        raise typer.Exit(code=EXIT_UNPACK_TOOL)

    try:
        ensure_json_output(target_dir)
    except FileNotFoundError as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_UNPACK_TOOL) from exc

    console.print(f"解包完成：{target_dir}")
