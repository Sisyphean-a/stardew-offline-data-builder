from __future__ import annotations

import json
import shutil
from pathlib import Path
from zipfile import ZipFile

from typer.testing import CliRunner

from builder.cli import app
from builder.utils.hashing import sha256_file

runner = CliRunner()
FIXED_TIME = "2026-07-15T00:00:00+00:00"


def test_build_writes_manifest_and_svdata(tmp_path: Path, monkeypatch) -> None:
    game_dir = tmp_path / "game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Content (unpacked)").mkdir()
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        game_dir / "Content (unpacked)",
        dirs_exist_ok=True,
    )
    output_dir = tmp_path / "dist"
    monkeypatch.setattr("builder.commands.build.current_utc_iso", lambda: FIXED_TIME)
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
    manifest_path = output_dir / "manifest.json"
    package_path = output_dir / "stardew-zh-cn.svdata"
    assert manifest_path.exists()
    assert package_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["database"]["file"] == "stardew.db"
    assert manifest["content"]["entities"] == 4

    with ZipFile(package_path) as archive:
        assert sorted(archive.namelist()) == [
            "manifest.json",
            "reports/build-summary.json",
            "reports/errors.json",
            "reports/missing-translations.json",
            "reports/unmatched.json",
            "stardew.db",
        ]


def test_build_is_repeatable_with_fixed_generated_at(tmp_path: Path, monkeypatch) -> None:
    game_dir = tmp_path / "repeat-game"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Content (unpacked)").mkdir()
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        game_dir / "Content (unpacked)",
        dirs_exist_ok=True,
    )
    output_a = tmp_path / "a"
    output_b = tmp_path / "b"
    monkeypatch.setattr("builder.commands.build.current_utc_iso", lambda: FIXED_TIME)

    first = runner.invoke(
        app,
        [
            "build",
            "--game-dir",
            str(game_dir),
            "--community-data",
            str(Path("tests/fixtures/community-data")),
            "--output",
            str(output_a),
        ],
    )
    second = runner.invoke(
        app,
        [
            "build",
            "--game-dir",
            str(game_dir),
            "--community-data",
            str(Path("tests/fixtures/community-data")),
            "--output",
            str(output_b),
        ],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert sha256_file(output_a / "stardew.db") == sha256_file(output_b / "stardew.db")
    assert sha256_file(output_a / "manifest.json") == sha256_file(output_b / "manifest.json")
    assert sha256_file(output_a / "stardew-zh-cn.svdata") == sha256_file(
        output_b / "stardew-zh-cn.svdata"
    )
