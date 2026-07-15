from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from builder.cli import app

runner = CliRunner()


def test_inspect_outputs_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "inspect"
    build = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])
    inspect = runner.invoke(app, ["inspect", str(output_dir / "stardew.db")])

    assert build.exit_code == 0
    assert inspect.exit_code == 0
    assert "实体总数：4" in inspect.stdout
    assert "物品：1" in inspect.stdout
    assert "作物：1" in inspect.stdout
    assert "鱼类：1" in inspect.stdout
    assert "村民：1" in inspect.stdout


def test_database_contains_aliases(tmp_path: Path) -> None:
    output_dir = tmp_path / "aliases"
    build = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])
    assert build.exit_code == 0

    connection = sqlite3.connect(output_dir / "stardew.db")
    aliases = connection.execute(
        "SELECT alias FROM entity_aliases WHERE entity_id = 'object:24' ORDER BY alias"
    ).fetchall()
    connection.close()

    assert [row[0] for row in aliases] == ["春季作物", "萝卜"]


def test_inspect_outputs_extra_type_counts(tmp_path: Path) -> None:
    game_dir = tmp_path / "extra-inspect-game"
    unpacked_data_dir = game_dir / "Content (unpacked)" / "Data"
    unpacked_data_dir.mkdir(parents=True)
    (game_dir / "Content").mkdir(parents=True, exist_ok=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        game_dir / "Content (unpacked)",
        dirs_exist_ok=True,
    )
    extra_payload = {
        "entries": [
            {
                "id": "rusty-sword",
                "internalName": "RustySword",
                "name": "生锈短剑",
                "description": "测试武器",
            }
        ]
    }
    (unpacked_data_dir / "Weapon.zh-CN.json").write_text(
        json.dumps(extra_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = tmp_path / "extra-inspect-dist"
    build = runner.invoke(
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
    inspect = runner.invoke(app, ["inspect", str(output_dir / "stardew.db")])

    assert build.exit_code == 0
    assert inspect.exit_code == 0
    assert "武器：1" in inspect.stdout
