from __future__ import annotations

from collections import Counter

from builder.models import BuildSummary, NormalizedEntity


def summarize_entities(entities: list[NormalizedEntity]) -> BuildSummary:
    counts = Counter(entity.entity_type for entity in entities)
    missing = sum(1 for entity in entities if entity.translation_status == "missing")
    return BuildSummary(
        entities=len(entities),
        missing_translations=missing,
        counts_by_type=dict(counts),
    )
