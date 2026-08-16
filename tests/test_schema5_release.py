from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from builder.cli import app
from builder.commands.package import create_schema5_svdata_package, package_existing_output
from builder.pipeline.schema5_release import validate_regression_budget
from tests.complete_fixture import add_required_entity_baseline, enrich_fixture_entries

runner = CliRunner()


def complete_unpacked_fixture(tmp_path: Path) -> Path:
    unpacked = tmp_path / "Content (unpacked)"
    unpacked.mkdir()
    source = Path("tests/fixtures/game-data/Content (unpacked)")
    for child in source.iterdir():
        target = unpacked / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            target.write_bytes(child.read_bytes())
    add_required_entity_baseline(unpacked)
    enrich_fixture_entries(unpacked)
    return unpacked


def test_coverage_regression_budget_blocks_core_slot_deterioration(tmp_path: Path) -> None:
    previous = tmp_path / "candidate"
    previous.mkdir()
    (previous / "manifest.json").write_text(
        json.dumps(
            {
                "coverage": {
                    "release": {
                        "core": {
                            "bySlot": {
                                "crop:sell_price": {
                                    "answeredRate": 1.0,
                                    "notCollectedRate": 0.0,
                                }
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="回答率回归"):
        validate_regression_budget(
            previous,
            {
                "core": {
                    "bySlot": {
                        "crop:sell_price": {
                            "answeredRate": 0.98,
                            "notCollectedRate": 0.02,
                        }
                    }
                }
            },
        )


def test_regression_budget_ignores_legacy_manifest_without_coverage(tmp_path: Path) -> None:
    previous = tmp_path / "candidate"
    previous.mkdir()
    (previous / "manifest.json").write_text(
        json.dumps({"format": "legacy-v4", "schemaVersion": 4}), encoding="utf-8"
    )
    # 旧格式历史包不是 schema 5 基线：不得崩溃或阻塞构建。
    validate_regression_budget(
        previous,
        {"core": {"bySlot": {"crop:sell_price": {"answeredRate": 1.0, "notCollectedRate": 0.0}}}},
    )


def test_regression_budget_ignores_legacy_database_without_schema5_tables(
    tmp_path: Path,
) -> None:
    from builder.models import NormalizedEntity
    from builder.pipeline.schema5_projection import build_schema5_staging_package

    previous = tmp_path / "candidate"
    previous.mkdir()
    (previous / "manifest.json").write_text(
        json.dumps(
            {
                "coverage": {
                    "release": {
                        "core": {"bySlot": {"crop:sell_price": {
                            "answeredRate": 1.0, "notCollectedRate": 0.0,
                        }}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(previous / "stardew.db") as connection:
        connection.execute("CREATE TABLE entities (id TEXT PRIMARY KEY)")
    package = build_schema5_staging_package(
        [
            NormalizedEntity(
                id="object:24",
                entity_type="object",
                game_id="24",
                internal_name=None,
                name_zh="防风草",
                name_en=None,
                description_zh=None,
                description_en=None,
                category=None,
                extra_json={"Price": 35},
                source_file="Data/Objects.json",
            )
        ],
        tmp_path,
        game_version="1.6.15",
    )
    # 旧格式数据库缺少 fact_slots 等 schema 5 表：不得崩溃。
    validate_regression_budget(
        previous,
        {"core": {"bySlot": {"crop:sell_price": {"answeredRate": 1.0, "notCollectedRate": 0.0}}}},
        current_package=package,
    )


def test_formal_schema5_candidate_writes_publishable_package_and_typed_database(
    tmp_path: Path,
) -> None:
    output = tmp_path / "candidate"
    result = runner.invoke(
        app,
        [
            "build",
            "--unpacked-dir",
            str(complete_unpacked_fixture(tmp_path)),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifestVersion"] == 2
    assert manifest["schemaVersion"] == 5
    assert manifest["contentContract"] == "player-facts-v1"
    assert manifest["publishable"] is True
    assert not (output / ".release-blocked.json").exists()
    assert (output / "schema5-conformance.json").exists()
    assert (output / "stardew-zh-cn.svdata").exists()
    diagnostics = json.loads(
        (output / "reports" / "shop-price-diagnostics.json").read_text(encoding="utf-8")
    )
    assert diagnostics == [
        {
            "shopId": "SeedShop",
            "offerKey": "shop:SeedShop:offer:parsnip-seeds",
            "entityId": "crop:24",
            "scopeId": "offer:shop:SeedShop:offer:parsnip-seeds",
            "currency": "金币",
            "conditioned": False,
            "kind": "coin",
            "value": 20,
            "inputClaimId": None,
            "reason": "static-official-shop-price",
            "profitMargin": False,
            "appliedShopModifiers": 0,
            "appliedItemModifiers": 0,
        },
        {
            "shopId": "SeedShop",
            "offerKey": "shop:SeedShop:offer:parsnip-seeds",
            "entityId": "object:24",
            "scopeId": "offer:shop:SeedShop:offer:parsnip-seeds",
            "currency": "金币",
            "conditioned": False,
            "kind": "coin",
            "value": 20,
            "inputClaimId": None,
            "reason": "static-official-shop-price",
            "profitMargin": False,
            "appliedShopModifiers": 0,
            "appliedItemModifiers": 0,
        },
    ]
    with sqlite3.connect(output / "stardew.db") as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT COUNT(*) FROM fact_slots WHERE status = 'not_collected'"
        ).fetchone()[0] == 0
        assert "extra_json" not in {
            row[1] for row in connection.execute("PRAGMA table_info(entities)")
        }

    with zipfile.ZipFile(output / "stardew-zh-cn.svdata") as archive:
        assert "schema5-conformance.json" in archive.namelist()
        assert "stardew.db" in archive.namelist()


def test_candidate_packaging_revalidates_persisted_database(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    result = runner.invoke(
        app,
        [
            "build",
            "--unpacked-dir",
            str(complete_unpacked_fixture(tmp_path)),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    with sqlite3.connect(output / "stardew.db") as connection:
        connection.execute("UPDATE entities SET name_zh = '篡改'")
        connection.commit()
    with pytest.raises(ValueError, match="校验和|schema|元数据"):
        create_schema5_svdata_package(
            output,
            "zh-CN",
            json.loads((output / "manifest.json").read_text(encoding="utf-8"))["generatedAt"],
            output / "stardew.db",
            output / "manifest.json",
            output / "reports",
            output / "schema5-conformance.json",
        )


def test_failed_candidate_is_removed_after_next_successful_build(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    unpacked = complete_unpacked_fixture(tmp_path)
    initial = runner.invoke(
        app,
        ["build", "--unpacked-dir", str(unpacked), "--output", str(output)],
    )
    assert initial.exit_code == 0, initial.stdout
    for path in (unpacked / "Data").glob("Objects.*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload["entries"]:
            entry.pop("Price", None)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    failed = runner.invoke(
        app,
        ["build", "--unpacked-dir", str(unpacked), "--output", str(output)],
    )
    assert failed.exit_code == 1
    assert not output.exists()
    assert (tmp_path / "candidate.previous").is_dir()
    failed_output = tmp_path / "candidate.failed"
    assert (failed_output / ".release-blocked.json").exists()
    assert (failed_output / "reports" / "shop-price-diagnostics.json").exists()

    enrich_fixture_entries(unpacked)
    succeeded = runner.invoke(
        app,
        ["build", "--unpacked-dir", str(unpacked), "--output", str(output)],
    )
    assert succeeded.exit_code == 0, succeeded.stdout
    assert output.is_dir()
    assert not (tmp_path / "candidate.failed").exists()


def test_package_command_revalidates_existing_schema5_output(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    result = runner.invoke(
        app,
        [
            "build-schema5",
            "--unpacked-dir",
            str(complete_unpacked_fixture(tmp_path)),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    (output / "stardew-zh-cn.svdata").unlink()

    package = package_existing_output(output, "zh-CN")

    assert package == output / "stardew-zh-cn.svdata"
    assert package.is_file()
