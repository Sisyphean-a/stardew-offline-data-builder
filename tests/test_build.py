from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from builder.cli import app
from builder.commands import build as build_module
from builder.sources import steam_discovery
from builder.sources.steam_discovery import ResolvedGameDirectory
from tests.complete_fixture import add_required_entity_baseline

runner = CliRunner()


def test_build_fixture_creates_searchable_database(tmp_path: Path) -> None:
    output_dir = tmp_path / "输出 目录"
    result = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])

    assert result.exit_code == 0
    db_path = output_dir / "stardew.db"
    assert db_path.exists()

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        """
        SELECT entity_id FROM entity_search
        WHERE entity_search MATCH '防风草 OR parsnip OR \"fang feng cao\" OR ffc'
        """
    ).fetchall()
    image_path = connection.execute(
        "SELECT image_path FROM entities WHERE id = 'object:24'"
    ).fetchone()
    connection.close()

    assert rows
    assert rows[0][0] == "object:24"
    assert image_path == ("images/object-24.webp",)
    assert (output_dir / "images" / "object-24.webp").exists()


def test_build_fixture_is_repeatable(tmp_path: Path) -> None:
    output_dir = tmp_path / "repeat build"
    first = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])
    second = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert (output_dir / "stardew.db").exists()


def test_build_uses_official_data_and_writes_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Content (unpacked)").mkdir()
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        steam_discovery,
        "discover_installed_stardew_game_directories",
        lambda: pytest.fail("不应探测 Steam"),
    )
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        game_dir / "Content (unpacked)",
        dirs_exist_ok=True,
    )
    add_required_entity_baseline(game_dir / "Content (unpacked)")
    output_dir = tmp_path / "build-output"

    result = runner.invoke(
        app,
        [
            "build",
            "--game-dir",
            str(game_dir),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    db_path = output_dir / "stardew.db"
    reports_dir = output_dir / "reports"
    assert db_path.exists()
    assert (reports_dir / "build-summary.json").exists()
    assert not (reports_dir / "unmatched.json").exists()

    connection = sqlite3.connect(db_path)
    row = connection.execute(
        "SELECT extra_json, image_path FROM entities WHERE id = 'object:24'"
    ).fetchone()
    connection.close()

    extra = json.loads(row[0])
    assert extra["_provenance"] == {
        "official": ["Data/Objects.en.json", "Data/Objects.zh-CN.json"]
    }
    assert row[1] == "images/object-24.webp"
    assert (output_dir / "images" / "object-24.webp").exists()

    coverage = json.loads((reports_dir / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["official"]["object"] == 1
    assert "自动发现游戏目录" not in result.stdout


def test_build_uses_automatic_game_directory_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Content (unpacked)").mkdir()
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        game_dir / "Content (unpacked)",
        dirs_exist_ok=True,
    )
    add_required_entity_baseline(game_dir / "Content (unpacked)")
    monkeypatch.setattr(
        build_module,
        "resolve_game_directory",
        lambda _: ResolvedGameDirectory(path=game_dir, origin="auto"),
        raising=False,
    )

    result = runner.invoke(app, ["build", "--output", str(tmp_path / "output")])

    assert result.exit_code == 0, result.output
    assert result.stdout.count("自动发现游戏目录") == 1


def test_build_treats_empty_game_dir_as_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Content (unpacked)").mkdir()
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        game_dir / "Content (unpacked)",
        dirs_exist_ok=True,
    )
    add_required_entity_baseline(game_dir / "Content (unpacked)")
    received: list[Path | None] = []

    def resolve(game_dir_arg: Path | None) -> ResolvedGameDirectory:
        received.append(game_dir_arg)
        return ResolvedGameDirectory(path=game_dir, origin="explicit")

    monkeypatch.setattr(build_module, "resolve_game_directory", resolve)
    result = runner.invoke(app, ["build", "--game-dir", "", "--output", str(tmp_path / "output")])

    assert result.exit_code == 0, result.output
    assert received == [Path("")]
