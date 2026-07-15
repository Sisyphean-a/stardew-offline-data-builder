from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from builder.cli import app

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


def test_build_merges_community_data_and_writes_reports(tmp_path: Path) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Content (unpacked)").mkdir()
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        game_dir / "Content (unpacked)",
        dirs_exist_ok=True,
    )
    output_dir = tmp_path / "build-output"

    result = runner.invoke(
        app,
        [
            "build",
            "--game-dir",
            str(game_dir),
            "--community-data",
            str(Path("tests/fixtures/community-data")),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    db_path = output_dir / "stardew.db"
    reports_dir = output_dir / "reports"
    assert db_path.exists()
    assert (reports_dir / "build-summary.json").exists()
    assert (reports_dir / "unmatched.json").exists()

    connection = sqlite3.connect(db_path)
    row = connection.execute(
        "SELECT extra_json, image_path FROM entities WHERE id = 'object:24'"
    ).fetchone()
    connection.close()

    extra = json.loads(row[0])
    assert extra["price"] == 35
    assert extra["season"] == "spring"
    assert row[1] == "images/object-24.webp"
    assert (output_dir / "images" / "object-24.webp").exists()

    unmatched = json.loads((reports_dir / "unmatched.json").read_text(encoding="utf-8"))
    assert unmatched[0]["source_id"] == "999"
