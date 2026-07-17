from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from builder.cli import app
from builder.commands import doctor as doctor_module
from builder.sources import steam_discovery
from builder.sources.steam_discovery import ResolvedGameDirectory
from builder.utils.paths import default_xnb_hack_path

runner = CliRunner()


def test_doctor_succeeds_with_space_and_chinese_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "中文 空格 游戏"
    content_dir = game_dir / "Content"
    content_dir.mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    (game_dir / "StardewXnbHack.py").write_text("print('ok')", encoding="utf-8")
    monkeypatch.setattr(
        steam_discovery,
        "discover_installed_stardew_game_directories",
        lambda: pytest.fail("不应探测 Steam"),
    )

    result = runner.invoke(
        app,
        ["doctor", "--game-dir", str(game_dir)],
    )

    assert result.exit_code == 0
    assert "环境检查通过" in result.stdout
    assert "自动发现游戏目录" not in result.stdout


def test_doctor_uses_automatic_game_directory_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    (game_dir / "StardewXnbHack.py").write_text("print('ok')", encoding="utf-8")
    monkeypatch.setattr(
        doctor_module,
        "resolve_game_directory",
        lambda _: ResolvedGameDirectory(path=game_dir, origin="auto"),
        raising=False,
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert result.stdout.count("自动发现游戏目录") == 1


def test_doctor_treats_empty_game_dir_as_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    (game_dir / "StardewXnbHack.py").write_text("print('ok')", encoding="utf-8")
    received: list[Path | None] = []

    def resolve(game_dir_arg: Path | None) -> ResolvedGameDirectory:
        received.append(game_dir_arg)
        return ResolvedGameDirectory(path=game_dir, origin="explicit")

    monkeypatch.setattr(doctor_module, "resolve_game_directory", resolve)
    result = runner.invoke(app, ["doctor", "--game-dir", ""])

    assert result.exit_code == 0
    assert received == [Path("")]


def test_doctor_reports_missing_xnb(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    result = runner.invoke(
        app,
        ["doctor", "--game-dir", str(game_dir)],
    )

    assert result.exit_code == 4
    assert "未找到 StardewXnbHack" in result.stdout


def test_default_xnb_hack_path_prefers_exe(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    exe_path = game_dir / "StardewXnbHack.exe"
    py_path = game_dir / "StardewXnbHack.py"
    exe_path.write_text("", encoding="utf-8")
    py_path.write_text("", encoding="utf-8")

    resolved = default_xnb_hack_path(game_dir)

    assert resolved == exe_path
