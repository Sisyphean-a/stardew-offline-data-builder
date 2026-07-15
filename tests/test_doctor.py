from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from builder.cli import app
from builder.utils.paths import default_xnb_hack_path

runner = CliRunner()


def test_doctor_succeeds_with_space_and_chinese_paths(tmp_path: Path) -> None:
    game_dir = tmp_path / "中文 空格 游戏"
    content_dir = game_dir / "Content"
    community_dir = tmp_path / "社区 数据"
    content_dir.mkdir(parents=True)
    community_dir.mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    (game_dir / "StardewXnbHack.py").write_text("print('ok')", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "doctor",
            "--game-dir",
            str(game_dir),
            "--community-data",
            str(community_dir),
        ],
    )

    assert result.exit_code == 0
    assert "环境检查通过" in result.stdout


def test_doctor_reports_missing_xnb(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    community_dir = tmp_path / "community"
    community_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "doctor",
            "--game-dir",
            str(game_dir),
            "--community-data",
            str(community_dir),
        ],
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
