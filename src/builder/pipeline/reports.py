from __future__ import annotations

from collections import Counter
from pathlib import Path

from builder.models import BuildSummary, NormalizedEntity
from builder.pipeline.artifact_metadata import content_metadata
from builder.pipeline.quality import quality_payload
from builder.utils.json_io import dump_json_file


def summarize_entities(
    entities: list[NormalizedEntity],
    data_errors: int = 0,
) -> BuildSummary:
    counts = Counter(entity.entity_type for entity in entities)
    missing = sum(1 for entity in entities if entity.translation_status == "missing")
    invalid = sum(1 for entity in entities if entity.translation_status == "invalid")
    not_applicable = sum(
        1 for entity in entities if entity.translation_status == "not_applicable"
    )
    return BuildSummary(
        entities=len(entities),
        missing_translations=missing,
        not_applicable_translations=not_applicable,
        invalid_translations=invalid,
        data_errors=data_errors,
        counts_by_type=dict(counts),
    )


def write_build_reports(
    reports_dir: Path,
    summary: BuildSummary,
    missing_translations: list[NormalizedEntity],
    errors: list[dict[str, str]],
    source_discovery: dict[str, list[dict[str, object]]] | None = None,
    coverage: dict[str, object] | None = None,
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    remove_legacy_reports(reports_dir)
    dump_json_file(reports_dir / "build-summary.json", build_summary_payload(summary, errors))
    dump_json_file(
        reports_dir / "missing-translations.json",
        [
            {
                "id": entity.id,
                "name_zh": entity.name_zh,
                "name_en": entity.name_en,
            }
            for entity in missing_translations
        ],
    )
    dump_json_file(reports_dir / "errors.json", errors)
    if source_discovery is not None:
        dump_json_file(reports_dir / "source-discovery.json", source_discovery)
    if coverage is not None:
        dump_json_file(reports_dir / "coverage.json", coverage)


def build_summary_payload(
    summary: BuildSummary,
    errors: list[dict[str, str]],
) -> dict[str, object]:
    content = content_metadata(summary)
    quality = quality_payload(summary, data_errors=len(errors))
    return {
        "success": quality["status"] == "passed",
        "counts": {
            "entities": content["entities"],
            "objects": content["objects"],
            "crops": content["crops"],
            "fish": content["fish"],
            "villagers": content["villagers"],
            "extraCounts": content["extraCounts"],
            "entityTypes": content["entityTypes"],
        },
        "warnings": {
            "missingTranslations": summary.missing_translations,
            "invalidTranslations": summary.invalid_translations,
            "notApplicableTranslations": summary.not_applicable_translations,
            "duplicateIds": summary.duplicate_ids,
            "dataErrors": len(errors),
        },
        "quality": quality,
    }


def remove_legacy_reports(reports_dir: Path) -> None:
    for filename in ("unmatched.json",):
        path = reports_dir / filename
        if path.exists():
            path.unlink()
