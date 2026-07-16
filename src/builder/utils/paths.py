from __future__ import annotations

from pathlib import Path


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_game_directory(path: Path | None) -> Path:
    if path is None or not path.exists() or not path.is_dir():
        raise FileNotFoundError("未找到游戏目录")
    return path


def ensure_content_directory(game_dir: Path) -> Path:
    content_dir = game_dir / "Content"
    if not content_dir.exists():
        raise FileNotFoundError("未找到 Content 目录")
    return content_dir


def ensure_game_dll(game_dir: Path) -> Path:
    dll_path = game_dir / "Stardew Valley.dll"
    if not dll_path.exists():
        raise FileNotFoundError("未找到 Stardew Valley.dll")
    return dll_path


def ensure_xnb_hack_path(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError("未找到 StardewXnbHack")
    return path


def default_xnb_hack_path(game_dir: Path) -> Path:
    candidates = [
        game_dir / "StardewXnbHack.exe",
        game_dir / "StardewXnbHack.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def default_unpacked_dir(game_dir: Path) -> Path:
    return game_dir / "Content (unpacked)"


def ensure_json_output(path: Path) -> None:
    if not path.exists() or not any(path.rglob("*.json")):
        raise FileNotFoundError("解包后未发现 JSON 输出")
