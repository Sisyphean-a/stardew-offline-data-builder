from __future__ import annotations

from collections import Counter
from pathlib import Path

from builder.models import BuildSummary, NormalizedEntity, UnmatchedRecord
from builder.utils.json_io import dump_json_file


def summarize_entities(entities: list[NormalizedEntity]) -> BuildSummary:
    counts = Counter(entity.entity_type for entity in entities)
    missing = sum(1 for entity in entities if entity.translation_status == "missing")
    return BuildSummary(
        entities=len(entities),
        missing_translations=missing,
        counts_by_type=dict(counts),
    )


def write_build_reports(
    reports_dir: Path,
    summary: BuildSummary,
    unmatched: list[UnmatchedRecord],
    missing_translations: list[NormalizedEntity],
    errors: list[dict[str, str]],
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    dump_json_file(
        reports_dir / "build-summary.json",
        {
            "success": True,
            "counts": {
                "entities": summary.entities,
                "objects": summary.counts_by_type.get("object", 0),
                "crops": summary.counts_by_type.get("crop", 0),
                "fish": summary.counts_by_type.get("fish", 0),
                "villagers": summary.counts_by_type.get("villager", 0),
            },
            "warnings": {
                "missingTranslations": summary.missing_translations,
                "unmatched": len(unmatched),
                "duplicateIds": summary.duplicate_ids,
            },
        },
    )
    dump_json_file(
        reports_dir / "unmatched.json",
        [record.model_dump(mode="json") for record in unmatched],
    )
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
