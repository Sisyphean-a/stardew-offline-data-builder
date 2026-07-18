from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from builder.cli import app
from builder.config import EXIT_PACKAGE, EXIT_QUALITY, EXIT_SOURCE_DATA
from tests.complete_fixture import add_required_entity_baseline

runner = CliRunner()


def test_failed_required_image_blocks_package_and_reports_failure(tmp_path: Path) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path)
    output_dir = tmp_path / "output"

    result = runner.invoke(
        app,
        ["build", "--game-dir", str(game_dir), "--output", str(output_dir)],
    )

    assert result.exit_code == EXIT_QUALITY
    summary = read_json(output_dir / "reports" / "build-summary.json")
    errors = read_json(output_dir / "reports" / "errors.json")
    manifest = read_json(output_dir / "manifest.json")
    assert summary["success"] is False
    assert summary["quality"]["status"] == "failed"
    assert manifest["quality"]["status"] == "failed"
    assert errors[0]["entity_id"] == "achievement:0"
    assert not (output_dir / "stardew-zh-cn.svdata").exists()


def test_failed_rebuild_quarantines_previous_package(tmp_path: Path) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path)
    output_dir = tmp_path / "output"
    achievements = game_dir / "Content (unpacked)" / "Data" / "Achievements.json"
    translated = achievements.with_name("Achievements.zh-CN.json")

    restore_fixture_achievement(game_dir / "Content (unpacked)")
    first = runner.invoke(app, ["build", "--game-dir", str(game_dir), "--output", str(output_dir)])
    achievements.write_text(
        json.dumps({"0": "Greenhorn^Earn 15,000g.^true^-1^18"}), encoding="utf-8"
    )
    translated.write_text(
        json.dumps({"0": "新手^赚取 15,000 金。^true^-1^18"}, ensure_ascii=False),
        encoding="utf-8",
    )
    second = runner.invoke(app, ["build", "--game-dir", str(game_dir), "--output", str(output_dir)])

    assert first.exit_code == 0, first.output
    assert second.exit_code == EXIT_QUALITY
    assert not (output_dir / "stardew-zh-cn.svdata").exists()
    assert (output_dir / "stardew-zh-cn.failed.svdata").is_file()


def test_missing_required_entity_type_blocks_build(tmp_path: Path) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path)
    output_dir = tmp_path / "output"
    data_dir = game_dir / "Content (unpacked)" / "Data"
    (data_dir / "Achievements.json").unlink()
    (data_dir / "Achievements.zh-CN.json").unlink()

    result = runner.invoke(app, ["build", "--game-dir", str(game_dir), "--output", str(output_dir)])

    assert result.exit_code == EXIT_SOURCE_DATA
    assert "achievement" in result.stdout
    assert not (output_dir / "stardew-zh-cn.svdata").exists()


def test_missing_nonvisual_extended_type_blocks_build(tmp_path: Path) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path)
    restore_fixture_achievement(game_dir / "Content (unpacked)")
    data_dir = game_dir / "Content (unpacked)" / "Data"
    for path in (data_dir / "fixture-monster.en.json", data_dir / "fixture-monster.zh-CN.json"):
        path.unlink()

    result = runner.invoke(
        app,
        ["build", "--game-dir", str(game_dir), "--output", str(tmp_path / "output")],
    )

    assert result.exit_code == EXIT_SOURCE_DATA
    assert "monster" in result.stdout


@pytest.mark.parametrize("name_zh", ["0", "   "])
def test_invalid_manual_name_override_blocks_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name_zh: str
) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path)
    restore_fixture_achievement(game_dir / "Content (unpacked)")
    overrides_path = tmp_path / "overrides.json"
    write_overrides(overrides_path, {"name_zh": name_zh})
    monkeypatch.setattr("builder.commands.build.OVERRIDES_PATH", overrides_path)

    output_dir = tmp_path / "output"
    result = runner.invoke(app, ["build", "--game-dir", str(game_dir), "--output", str(output_dir)])

    assert result.exit_code == EXIT_QUALITY
    assert not (output_dir / "stardew-zh-cn.svdata").exists()
    assert read_json(output_dir / "reports" / "build-summary.json")["quality"]["status"] == "failed"


@pytest.mark.parametrize(
    "override",
    [
        {"extra_json": {"imageRequired": False, "imageSource": None}},
        {"extra_json": {"imageRect": [0, 0, 1, 1]}},
        {"image_path": "images/manual.webp"},
    ],
)
def test_manual_override_cannot_disable_required_image_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: dict[str, object]
) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path)
    overrides_path = tmp_path / "overrides.json"
    write_overrides(overrides_path, override)
    monkeypatch.setattr("builder.commands.build.OVERRIDES_PATH", overrides_path)

    result = runner.invoke(
        app,
        ["build", "--game-dir", str(game_dir), "--output", str(tmp_path / "output")],
    )

    assert isinstance(result.exception, ValueError)
    assert not (tmp_path / "output" / "stardew-zh-cn.svdata").exists()


def test_early_source_failure_quarantines_previous_package(tmp_path: Path) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path)
    output_dir = tmp_path / "output"

    restore_fixture_achievement(game_dir / "Content (unpacked)")
    first = runner.invoke(app, ["build", "--game-dir", str(game_dir), "--output", str(output_dir)])
    data_dir = game_dir / "Content (unpacked)" / "Data"
    for fish_path in (data_dir / "Fish.en.json", data_dir / "Fish.zh-CN.json"):
        fish_path.unlink()
    second = runner.invoke(app, ["build", "--game-dir", str(game_dir), "--output", str(output_dir)])
    package = runner.invoke(app, ["package", "--output", str(output_dir)])

    assert first.exit_code == 0, first.output
    assert second.exit_code != 0
    assert not (output_dir / "stardew-zh-cn.svdata").exists()
    assert (output_dir / "stardew-zh-cn.failed.svdata").is_file()
    assert package.exit_code == EXIT_PACKAGE
    assert "最近一次构建未成功完成" in package.stdout


def test_failed_fixture_build_writes_unpackageable_metadata(tmp_path: Path, monkeypatch) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path / "previous")
    restore_fixture_achievement(game_dir / "Content (unpacked)")
    output_dir = tmp_path / "output"
    initial = runner.invoke(
        app,
        ["build", "--game-dir", str(game_dir), "--output", str(output_dir)],
    )

    fixture_root = tmp_path / "fixture"
    unpacked_dir = fixture_root / "Content (unpacked)"
    shutil.copytree(Path("tests/fixtures/game-data/Content (unpacked)"), unpacked_dir)
    write_missing_required_achievement(unpacked_dir)
    monkeypatch.setattr("builder.commands.build.DEFAULT_FIXTURE_ROOT", fixture_root)

    build = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])
    package = runner.invoke(app, ["package", "--output", str(output_dir)])

    assert initial.exit_code == 0, initial.output
    assert build.exit_code == EXIT_QUALITY
    assert package.exit_code == EXIT_PACKAGE
    assert "最近一次构建未成功完成" in package.stdout
    assert not (output_dir / "stardew-zh-cn.svdata").exists()
    assert (output_dir / "stardew-zh-cn.failed.svdata").is_file()


def test_successful_fixture_output_is_not_packageable(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    build = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])
    package = runner.invoke(app, ["package", "--output", str(output_dir)])

    assert build.exit_code == 0
    assert package.exit_code == EXIT_PACKAGE
    assert "fixture 构建仅供开发检查" in package.stdout


def test_successful_fixture_quarantines_existing_package(tmp_path: Path) -> None:
    game_dir = create_game_with_missing_required_image(tmp_path / "previous")
    restore_fixture_achievement(game_dir / "Content (unpacked)")
    output_dir = tmp_path / "output"

    initial = runner.invoke(
        app,
        ["build", "--game-dir", str(game_dir), "--output", str(output_dir)],
    )
    fixture = runner.invoke(app, ["build-fixture", "--output", str(output_dir)])
    package = runner.invoke(app, ["package", "--output", str(output_dir)])

    assert initial.exit_code == 0, initial.output
    assert fixture.exit_code == 0, fixture.output
    assert not (output_dir / "stardew-zh-cn.svdata").exists()
    assert (output_dir / "stardew-zh-cn.failed.svdata").is_file()
    assert package.exit_code == EXIT_PACKAGE
    assert "fixture 构建仅供开发检查" in package.stdout


def create_game_with_missing_required_image(tmp_path: Path) -> Path:
    game_dir = tmp_path / "game"
    unpacked_dir = game_dir / "Content (unpacked)"
    (game_dir / "Content").mkdir(parents=True)
    (game_dir / "Stardew Valley.dll").write_text("", encoding="utf-8")
    shutil.copytree(
        Path("tests/fixtures/game-data/Content (unpacked)"),
        unpacked_dir,
    )
    add_required_entity_baseline(unpacked_dir)
    write_missing_required_achievement(unpacked_dir)
    return game_dir


def write_missing_required_achievement(unpacked_dir: Path) -> None:
    data_dir = unpacked_dir / "Data"
    for filename in ("Achievements.en.json", "Achievements.zh-CN.json"):
        (data_dir / filename).unlink(missing_ok=True)
    (data_dir / "Achievements.json").write_text(
        json.dumps({"0": "Greenhorn^Earn 15,000g.^true^-1^18"}),
        encoding="utf-8",
    )
    (data_dir / "Achievements.zh-CN.json").write_text(
        json.dumps({"0": "新手^赚取 15,000 金。^true^-1^18"}, ensure_ascii=False),
        encoding="utf-8",
    )


def restore_fixture_achievement(unpacked_dir: Path) -> None:
    fixture_data = Path("tests/fixtures/game-data/Content (unpacked)/Data")
    data_dir = unpacked_dir / "Data"
    for filename in ("Achievements.json", "Achievements.zh-CN.json"):
        (data_dir / filename).unlink(missing_ok=True)
    for filename in ("Achievements.en.json", "Achievements.zh-CN.json"):
        shutil.copy2(fixture_data / filename, data_dir / filename)


def write_overrides(path: Path, override: dict[str, object]) -> None:
    payload = {"entity_overrides": {"achievement:0": override}}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> dict[str, object] | list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))
