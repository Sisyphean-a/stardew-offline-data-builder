from __future__ import annotations

import json
import shutil
from pathlib import Path
from zipfile import ZipFile

from typer.testing import CliRunner

from builder.cli import app
from builder.commands.package import package_entries
from builder.config import EXIT_PACKAGE
from builder.utils.hashing import sha256_file
from tests.complete_fixture import add_required_entity_baseline

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
    add_required_entity_baseline(game_dir / "Content (unpacked)")
    output_dir = tmp_path / "dist"
    monkeypatch.setattr("builder.commands.build_output.current_utc_iso", lambda: FIXED_TIME)
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
    manifest_path = output_dir / "manifest.json"
    package_path = output_dir / "stardew-zh-cn.svdata"
    assert manifest_path.exists()
    assert package_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["database"]["file"] == "stardew.db"
    assert manifest["content"]["entities"] == 25

    with ZipFile(package_path) as archive:
        assert sorted(archive.namelist()) == [
            "images/object-24.webp",
            "manifest.json",
            "reports/build-summary.json",
            "reports/coverage.json",
            "reports/errors.json",
            "reports/missing-translations.json",
            "reports/source-discovery.json",
            "stardew.db",
        ]


def test_build_packages_images_for_relative_output_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    entries = package_entries(
        Path("relative-output"),
        Path("stardew.db"),
        Path("manifest.json"),
        Path("reports"),
        [(tmp_path / "relative-output" / "images" / "object-24.webp").resolve()],
    )

    assert entries[-1][1] == "images/object-24.webp"


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
    add_required_entity_baseline(game_dir / "Content (unpacked)")
    output_a = tmp_path / "a"
    output_b = tmp_path / "b"
    monkeypatch.setattr("builder.commands.build_output.current_utc_iso", lambda: FIXED_TIME)

    first = runner.invoke(
        app,
        [
            "build",
            "--game-dir",
            str(game_dir),
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


def test_build_manifest_and_summary_include_extra_counts(tmp_path: Path, monkeypatch) -> None:
    game_dir = tmp_path / "phase7-game"
    unpacked_data_dir = game_dir / "Content (unpacked)" / "Data"
    unpacked_data_dir.mkdir(parents=True)
    (game_dir / "Content").mkdir(parents=True, exist_ok=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        game_dir / "Content (unpacked)",
        dirs_exist_ok=True,
    )
    add_required_entity_baseline(game_dir / "Content (unpacked)")
    extra_payload = {
        "entries": [
            {
                "id": "shadow-brute",
                "internalName": "ShadowBrute",
                "name": "暗影蛮兵",
                "description": "测试怪物",
            }
        ]
    }
    (unpacked_data_dir / "Monster.zh-CN.json").write_text(
        json.dumps(extra_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = tmp_path / "phase7-dist"
    monkeypatch.setattr("builder.commands.build_output.current_utc_iso", lambda: FIXED_TIME)
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
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads(
        (output_dir / "reports" / "build-summary.json").read_text(encoding="utf-8")
    )
    assert manifest["content"]["extraCounts"]["monster"] == 2
    assert summary["counts"]["extraCounts"]["monster"] == 2


def test_failed_standalone_package_preserves_previous_canonical(tmp_path: Path) -> None:
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
    output_dir = tmp_path / "output"
    initial = runner.invoke(
        app,
        ["build", "--game-dir", str(game_dir), "--output", str(output_dir)],
    )
    package_path = output_dir / "stardew-zh-cn.svdata"
    initial_hash = sha256_file(package_path)
    (output_dir / "reports" / "broken.json").mkdir()

    failed = runner.invoke(app, ["package", "--output", str(output_dir)])

    assert initial.exit_code == 0, initial.output
    assert failed.exit_code == EXIT_PACKAGE
    assert sha256_file(package_path) == initial_hash
    assert not list(output_dir.glob("*.tmp"))
