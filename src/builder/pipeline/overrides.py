from __future__ import annotations

from typing import Any

from builder.models import NormalizedEntity

EDITABLE_FIELDS = {
    "name_zh",
    "name_en",
    "description_zh",
    "description_en",
    "category",
    "image_path",
    "aliases",
    "keywords",
}


def apply_entity_overrides(
    entities: list[NormalizedEntity], overrides: dict[str, dict[str, object]]
) -> tuple[list[NormalizedEntity], list[str]]:
    known_ids = {entity.id for entity in entities}
    updated = [apply_override(entity, overrides.get(entity.id)) for entity in entities]
    return updated, sorted(set(overrides) - known_ids)


def apply_override(
    entity: NormalizedEntity, override: dict[str, object] | None
) -> NormalizedEntity:
    if not override:
        return entity
    updates = {key: value for key, value in override.items() if key in EDITABLE_FIELDS}
    extra_json = merge_extra_json(entity.extra_json, override.get("extra_json"))
    provenance = dict(extra_json.get("_provenance", {}))
    provenance["manual_override"] = ["data/overrides.zh-CN.json"]
    extra_json["_provenance"] = provenance
    updates["extra_json"] = extra_json
    if updates.get("name_zh"):
        updates["translation_status"] = "complete"
    return entity.model_copy(update=updates)


def merge_extra_json(
    current: dict[str, Any], override: object
) -> dict[str, Any]:
    extra_json = dict(current)
    if isinstance(override, dict):
        extra_json.update(override)
    return extra_json
