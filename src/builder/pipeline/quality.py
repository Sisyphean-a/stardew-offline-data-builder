from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from builder.config import ENTITY_TYPE_LABELS
from builder.models import BuildSummary, NormalizedEntity

QUALITY_PASSED = "passed"
QUALITY_FAILED = "failed"


def quality_errors(entities: list[NormalizedEntity]) -> list[dict[str, str]]:
    counts = Counter(entity.entity_type for entity in entities)
    return [
        *invalid_translation_errors(entities),
        *missing_type_label_errors(counts),
    ]


def invalid_translation_errors(entities: list[NormalizedEntity]) -> list[dict[str, str]]:
    return [
        {
            "source": "translation",
            "source_file": entity.source_file,
            "entity_id": entity.id,
            "reason": "中文显示名称无效",
        }
        for entity in entities
        if entity.translation_status == "invalid"
    ]


def missing_type_label_errors(counts_by_type: Mapping[str, int]) -> list[dict[str, str]]:
    return [
        {
            "source": "quality",
            "entity_type": entity_type,
            "reason": "实体类型缺少中文显示名称",
        }
        for entity_type in unlabeled_entity_types(counts_by_type)
    ]


def unlabeled_entity_types(counts_by_type: Mapping[str, int]) -> list[str]:
    return sorted(
        entity_type
        for entity_type, count in counts_by_type.items()
        if count > 0 and not ENTITY_TYPE_LABELS.get(entity_type)
    )


def quality_payload(
    summary: BuildSummary,
    data_errors: int | None = None,
) -> dict[str, object]:
    error_count = summary.data_errors if data_errors is None else data_errors
    return {
        "status": quality_status(summary, error_count),
        "translations": translation_quality(summary),
        "dataErrors": error_count,
        "unlabeledEntityTypes": unlabeled_entity_types(summary.counts_by_type),
    }


def quality_status(summary: BuildSummary, data_errors: int | None = None) -> str:
    error_count = summary.data_errors if data_errors is None else data_errors
    if has_quality_failure(summary, error_count):
        return QUALITY_FAILED
    return QUALITY_PASSED


def has_quality_failure(summary: BuildSummary, data_errors: int) -> bool:
    return any(
        (
            summary.missing_translations,
            summary.invalid_translations,
            data_errors,
            unlabeled_entity_types(summary.counts_by_type),
        )
    )


def translation_quality(summary: BuildSummary) -> dict[str, int]:
    unusable = summary.missing_translations + summary.invalid_translations
    complete = summary.entities - unusable - summary.not_applicable_translations
    return {
        "complete": max(complete, 0),
        "missing": summary.missing_translations,
        "invalid": summary.invalid_translations,
        "notApplicable": summary.not_applicable_translations,
        "unusable": unusable,
    }
