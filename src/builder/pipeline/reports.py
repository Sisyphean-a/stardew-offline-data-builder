from __future__ import annotations

from collections import Counter
from pathlib import Path

from builder.config import PRIMARY_ENTITY_TYPES
from builder.models import BuildSummary, NormalizedEntity
from builder.utils.json_io import dump_json_file


def summarize_entities(entities: list[NormalizedEntity]) -> BuildSummary:
    counts = Counter(entity.entity_type for entity in entities)
    missing = sum(1 for entity in entities if entity.translation_status == "missing")
    not_applicable = sum(
        1 for entity in entities if entity.translation_status == "not_applicable"
    )
    return BuildSummary(
        entities=len(entities),
        missing_translations=missing,
        not_applicable_translations=not_applicable,
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
    extra_counts = {
        entity_type: count
        for entity_type, count in summary.counts_by_type.items()
        if entity_type not in PRIMARY_ENTITY_TYPES
    }
    return {
        "success": True,
        "counts": {
            "entities": summary.entities,
            "objects": summary.counts_by_type.get("object", 0),
            "crops": summary.counts_by_type.get("crop", 0),
            "fish": summary.counts_by_type.get("fish", 0),
            "villagers": summary.counts_by_type.get("villager", 0),
            "extraCounts": extra_counts,
        },
        "warnings": {
            "missingTranslations": summary.missing_translations,
            "notApplicableTranslations": summary.not_applicable_translations,
            "duplicateIds": summary.duplicate_ids,
            "dataErrors": len(errors),
        },
    }


def remove_legacy_reports(reports_dir: Path) -> None:
    for filename in ("unmatched.json",):
        path = reports_dir / filename
        if path.exists():
            path.unlink()
