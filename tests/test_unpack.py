from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from builder.cli import app
from builder.commands import unpack as unpack_module
from builder.sources import steam_discovery
from builder.sources.steam_discovery import ResolvedGameDirectory

runner = CliRunner()


def test_unpack_skips_existing_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "game"
    unpacked = game_dir / "Content (unpacked)" / "Data"
    unpacked.mkdir(parents=True)
    (game_dir / "Content").mkdir()
    (unpacked / "Objects.zh-CN.json").write_text("{}", encoding="utf-8")
    (game_dir / "StardewXnbHack.py").write_text("raise SystemExit(9)", encoding="utf-8")
    monkeypatch.setattr(
        steam_discovery,
        "discover_installed_stardew_game_directories",
        lambda: pytest.fail("不应探测 Steam"),
    )

    result = runner.invoke(app, ["unpack", "--game-dir", str(game_dir)])

    assert result.exit_code == 0
    assert "已跳过解包" in result.stdout
    assert "自动发现游戏目录" not in result.stdout


def test_unpack_uses_automatic_game_directory_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "game"
    unpacked = game_dir / "Content (unpacked)" / "Data"
    unpacked.mkdir(parents=True)
    (game_dir / "Content").mkdir()
    (game_dir / "StardewXnbHack.py").write_text("raise SystemExit(9)", encoding="utf-8")
    (unpacked / "Objects.zh-CN.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        unpack_module,
        "resolve_game_directory",
        lambda _: ResolvedGameDirectory(path=game_dir, origin="auto"),
        raising=False,
    )

    result = runner.invoke(app, ["unpack"])

    assert result.exit_code == 0
    assert result.stdout.count("自动发现游戏目录") == 1


def test_unpack_treats_empty_game_dir_as_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "game"
    unpacked = game_dir / "Content (unpacked)" / "Data"
    unpacked.mkdir(parents=True)
    (game_dir / "Content").mkdir()
    (game_dir / "StardewXnbHack.py").write_text("raise SystemExit(9)", encoding="utf-8")
    (unpacked / "Objects.zh-CN.json").write_text("{}", encoding="utf-8")
    received: list[Path | None] = []

    def resolve(game_dir_arg: Path | None) -> ResolvedGameDirectory:
        received.append(game_dir_arg)
        return ResolvedGameDirectory(path=game_dir, origin="explicit")

    monkeypatch.setattr(unpack_module, "resolve_game_directory", resolve)
    result = runner.invoke(app, ["unpack", "--game-dir", ""])

    assert result.exit_code == 0
    assert received == [Path("")]


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
