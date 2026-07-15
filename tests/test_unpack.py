from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from builder.cli import app

runner = CliRunner()


def test_unpack_skips_existing_json(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    unpacked = game_dir / "Content (unpacked)" / "Data"
    unpacked.mkdir(parents=True)
    (game_dir / "Content").mkdir()
    (unpacked / "Objects.zh-CN.json").write_text("{}", encoding="utf-8")
    (game_dir / "StardewXnbHack.py").write_text("raise SystemExit(9)", encoding="utf-8")

    result = runner.invoke(app, ["unpack", "--game-dir", str(game_dir)])

    assert result.exit_code == 0
    assert "已跳过解包" in result.stdout


def test_unpack_force_runs_tool_and_validates_json(tmp_path: Path) -> None:
    game_dir = tmp_path / "game force"
    (game_dir / "Content").mkdir(parents=True)
    script = game_dir / "StardewXnbHack.py"
    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "root = Path.cwd() / 'Content (unpacked)' / 'Data'",
                "root.mkdir(parents=True, exist_ok=True)",
                "payload = '{\"entityType\":\"object\",\"locale\":\"zh-CN\",\"entries\":[]}'",
                "(root / 'Objects.zh-CN.json').write_text(payload, encoding='utf-8')",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["unpack", "--game-dir", str(game_dir), "--force"])

    assert result.exit_code == 0
    assert "解包完成" in result.stdout
    assert (game_dir / "Content (unpacked)" / "Data" / "Objects.zh-CN.json").exists()
