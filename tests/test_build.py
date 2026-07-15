from __future__ import annotations

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
    connection.close()

    assert rows
    assert rows[0][0] == "object:24"


def test_build_fixture_is_repeatable(tmp_path: Path) -> None:
    output_dir = tmp_path / "repeat build"
    first = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])
    second = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert (output_dir / "stardew.db").exists()
