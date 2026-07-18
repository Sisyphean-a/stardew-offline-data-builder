from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from builder.cli import app
from builder.commands.package import package_existing_output
from builder.config import EXIT_PACKAGE, SCHEMA_VERSION
from builder.database.writer import read_artifact_metadata, write_database
from builder.models import BuildSummary, NormalizedEntity
from builder.pipeline.artifact_metadata import build_artifact_metadata
from builder.pipeline.quality import quality_errors
from builder.pipeline.reports import build_summary_payload, summarize_entities

runner = CliRunner()
FIXED_TIME = "2026-07-18T12:00:00+00:00"


def test_artifact_metadata_lists_all_types_with_labels() -> None:
    summary = BuildSummary(
        entities=5,
        missing_translations=0,
        counts_by_type={
            "achievement": 1,
            "big_craftable": 1,
            "furniture": 1,
            "footwear": 1,
            "tool": 1,
        },
    )

    metadata = build_artifact_metadata(summary, "zh-CN", FIXED_TIME, "hash", "1.6")

    entity_types = metadata["content"]["entityTypes"]
    assert metadata["schemaVersion"] == SCHEMA_VERSION
    assert metadata["quality"]["status"] == "passed"
    assert {entry["id"]: entry["displayName"] for entry in entity_types} == {
        "achievement": "成就",
        "big_craftable": "大型可制作物",
        "footwear": "鞋类",
        "furniture": "家具",
        "tool": "工具",
    }


def test_invalid_translation_and_unknown_type_fail_quality() -> None:
    entity = normalized_entity("unknown:1", "unknown", translation_status="invalid")
    summary = summarize_entities([entity], data_errors=len(quality_errors([entity])))

    payload = build_summary_payload(summary, quality_errors([entity]))
    metadata = build_artifact_metadata(summary, "zh-CN", FIXED_TIME)

    assert payload["success"] is False
    assert payload["warnings"]["invalidTranslations"] == 1
    assert payload["quality"]["translations"]["unusable"] == 1
    assert metadata["quality"]["status"] == "failed"
    assert metadata["quality"]["unlabeledEntityTypes"] == ["unknown"]


def test_package_reads_persisted_metadata_without_recomputing(tmp_path: Path) -> None:
    output_dir = write_output(
        tmp_path,
        BuildSummary(
            entities=2,
            missing_translations=0,
            counts_by_type={"object": 1, "monster": 1},
        ),
        [normalized_entity("object:24", "object"), normalized_entity("monster:1", "monster")],
    )

    package_existing_output(output_dir, "zh-CN")
    metadata = read_artifact_metadata(output_dir / "stardew.db")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["generatedAt"] == FIXED_TIME
    assert manifest["gameVersion"] == "1.6.9"
    assert manifest["sourceHash"] == "official-hash"
    assert manifest["content"] == metadata["content"]
    assert manifest["quality"] == metadata["quality"]
    assert manifest["content"]["extraCounts"] == {"monster": 1}


def test_package_rejects_failed_or_wrong_locale_metadata(tmp_path: Path) -> None:
    output_dir = write_output(
        tmp_path,
        BuildSummary(
            entities=1,
            missing_translations=0,
            invalid_translations=1,
            counts_by_type={"object": 1},
        ),
        [normalized_entity("object:24", "object", translation_status="invalid")],
    )

    failed = runner.invoke(app, ["package", "--output", str(output_dir)])

    assert failed.exit_code == EXIT_PACKAGE
    assert "构建质量未通过" in failed.stdout
    assert not (output_dir / "stardew-zh-cn.svdata").exists()
    with pytest.raises(ValueError, match="语言"):
        package_existing_output(output_dir, "en")


def test_package_rejects_old_or_missing_metadata(tmp_path: Path) -> None:
    output_dir = write_output(
        tmp_path,
        BuildSummary(entities=1, missing_translations=0, counts_by_type={"object": 1}),
        [normalized_entity("object:24", "object")],
    )
    db_path = output_dir / "stardew.db"
    metadata = read_artifact_metadata(db_path)
    metadata["schemaVersion"] = SCHEMA_VERSION - 1
    update_metadata(db_path, json.dumps(metadata, ensure_ascii=False))

    with pytest.raises(ValueError, match="版本"):
        package_existing_output(output_dir, "zh-CN")

    delete_metadata(db_path)

    with pytest.raises(ValueError, match="缺少"):
        package_existing_output(output_dir, "zh-CN")


def write_output(
    tmp_path: Path,
    summary: BuildSummary,
    entities: list[NormalizedEntity],
) -> Path:
    output_dir = tmp_path / "output"
    write_database(
        output_dir / "stardew.db",
        entities,
        [],
        locale="zh-CN",
        summary=summary,
        generated_at=FIXED_TIME,
        source_hash="official-hash",
        game_version="1.6.9",
    )
    (output_dir / "reports").mkdir()
    return output_dir


def update_metadata(db_path: Path, metadata: str) -> None:
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE build_meta SET value = ? WHERE key = 'artifact_metadata'",
        (metadata,),
    )
    connection.commit()
    connection.close()


def delete_metadata(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    connection.execute("DELETE FROM build_meta WHERE key = 'artifact_metadata'")
    connection.commit()
    connection.close()


def normalized_entity(
    entity_id: str,
    entity_type: str,
    translation_status: str = "complete",
) -> NormalizedEntity:
    return NormalizedEntity(
        id=entity_id,
        entity_type=entity_type,
        game_id=entity_id.split(":", maxsplit=1)[1],
        internal_name="测试实体",
        name_zh="测试实体",
        name_en="Test entity",
        description_zh="测试描述",
        description_en="Test description",
        category=None,
        translation_status=translation_status,
        source_file="Data/Test.json",
    )
