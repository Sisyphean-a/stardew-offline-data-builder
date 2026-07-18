from __future__ import annotations

from collections import Counter
from pathlib import Path

import typer
from rich.console import Console

from builder.commands.package import create_svdata_package, write_manifest
from builder.config import BUILD_DB_FILENAME, DEFAULT_LOCALE, EXIT_QUALITY, REPORTS_DIRNAME
from builder.database.writer import write_database
from builder.models import BuildSummary, NormalizedEntity
from builder.pipeline.artifact_metadata import build_artifact_metadata
from builder.pipeline.quality import quality_errors, quality_status
from builder.pipeline.release_state import clear_release_block
from builder.pipeline.reports import summarize_entities, write_build_reports
from builder.pipeline.search_tokens import build_search_documents
from builder.sources.game_source import GameSourceLoad
from builder.utils.time import current_utc_iso


def write_build_output(
    output_dir: Path,
    entities: list[NormalizedEntity],
    official: GameSourceLoad,
    errors: list[dict[str, str]],
    input_hash: str,
    detected_game_version: str,
    console: Console,
) -> None:
    summary, db_path, reports_dir, manifest_path, generated_at = persist_build_artifacts(
        output_dir, entities, official, errors, input_hash, detected_game_version
    )
    if quality_status(summary) != "passed":
        console.print("✗ 构建质量未通过；已保留诊断产物，未生成数据包")
        raise typer.Exit(code=EXIT_QUALITY)
    clear_release_block(output_dir)
    package_path = create_svdata_package(
        output_dir, DEFAULT_LOCALE, generated_at, db_path, manifest_path, reports_dir
    )
    console.print(f"已完成构建：{db_path}")
    console.print(f"已生成数据包：{package_path}")


def persist_build_artifacts(
    output_dir: Path,
    entities: list[NormalizedEntity],
    official: GameSourceLoad,
    errors: list[dict[str, str]],
    input_hash: str,
    detected_game_version: str,
) -> tuple[BuildSummary, Path, Path, Path, str]:
    db_path = output_dir / BUILD_DB_FILENAME
    reports_dir = output_dir / REPORTS_DIRNAME
    generated_at = current_utc_iso()
    all_errors = [*errors, *quality_errors(entities)]
    summary = summarize_entities(entities, data_errors=len(all_errors))
    metadata = build_artifact_metadata(
        summary, DEFAULT_LOCALE, generated_at, input_hash, detected_game_version
    )
    write_database(
        db_path,
        entities,
        build_search_documents(entities),
        locale=DEFAULT_LOCALE,
        summary=summary,
        generated_at=generated_at,
        source_hash=input_hash,
        game_version=detected_game_version,
        artifact_metadata=metadata,
    )
    write_official_reports(reports_dir, summary, entities, official, all_errors)
    manifest_path = write_manifest(
        output_dir, DEFAULT_LOCALE, generated_at, db_path, artifact_metadata=metadata
    )
    return summary, db_path, reports_dir, manifest_path, generated_at


def write_official_reports(
    reports_dir: Path,
    summary: BuildSummary,
    entities: list[NormalizedEntity],
    official: GameSourceLoad,
    errors: list[dict[str, str]],
) -> None:
    write_build_reports(
        reports_dir=reports_dir,
        summary=summary,
        missing_translations=[
            entity for entity in entities if entity.translation_status in {"missing", "invalid"}
        ],
        errors=errors,
        source_discovery={"official": official.discovered},
        coverage=build_coverage(entities),
    )


def build_coverage(entities: list[NormalizedEntity]) -> dict[str, object]:
    official = Counter(entity.entity_type for entity in entities)
    enriched = Counter(
        entity.entity_type
        for entity in entities
        if isinstance(entity.extra_json.get("officialDerived"), dict)
    )
    return {
        "official": dict(official),
        "officialDerived": dict(enriched),
        "images": image_coverage(entities),
    }


def image_coverage(entities: list[NormalizedEntity]) -> dict[str, int]:
    expected = [entity for entity in entities if entity.extra_json.get("imageRequired")]
    return {
        "expected": len(expected),
        "materialized": sum(entity.image_path is not None for entity in expected),
        "missing": sum(entity.image_path is None for entity in expected),
        "notApplicable": sum(
            entity.extra_json.get("imageAvailability") == "not_applicable" for entity in entities
        ),
    }
