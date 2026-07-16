from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from builder.config import EXIT_GAME_DIR, EXIT_UNPACK_TOOL
from builder.utils.paths import (
    default_unpacked_dir,
    default_xnb_hack_path,
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
        target_dir, skipped = unpack_game_directory(
            Path(game_dir),
            Path(unpacked_dir) if unpacked_dir else None,
            Path(xnb_hack) if xnb_hack else None,
            force,
        )
    except FileNotFoundError as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_GAME_DIR) from exc
    except RuntimeError as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_UNPACK_TOOL) from exc

    action = "已跳过解包" if skipped else "解包完成"
    console.print(f"{action}：{target_dir}")


def unpack_game_directory(
    game_dir: Path,
    unpacked_dir: Path | None,
    xnb_hack: Path | None,
    force: bool,
) -> tuple[Path, bool]:
    resolved_game_dir = ensure_game_directory(game_dir)
    ensure_content_directory(resolved_game_dir)
    xnb_path = ensure_xnb_hack_path(xnb_hack or default_xnb_hack_path(resolved_game_dir))
    target_dir = unpacked_dir or default_unpacked_dir(resolved_game_dir)
    if target_dir.exists() and any(target_dir.rglob("*.json")) and not force:
        return target_dir, True

    target_dir.mkdir(parents=True, exist_ok=True)
    result = run_external_command(xnb_path, ["--clean"], cwd=resolved_game_dir)
    if result.returncode != 0:
        details = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(f"解包失败\n{details}".rstrip())
    try:
        ensure_json_output(target_dir)
    except FileNotFoundError as exc:
        raise RuntimeError(str(exc)) from exc
    return target_dir, False
