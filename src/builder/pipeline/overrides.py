from __future__ import annotations

from typing import Any

from builder.models import NormalizedEntity
from builder.pipeline.normalize import is_displayable_translation

EDITABLE_FIELDS = {
    "name_zh",
    "name_en",
    "description_zh",
    "description_en",
    "category",
    "aliases",
    "keywords",
}
PROTECTED_IMAGE_FIELDS = {
    "imageSource",
    "imageFallbackSources",
    "imageRect",
    "spriteIndex",
    "imageGridCellSize",
    "imageSize",
    "imageMode",
    "imageRequired",
    "imageAvailability",
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
    reject_unsupported_override_fields(override)
    updates = {key: value for key, value in override.items() if key in EDITABLE_FIELDS}
    extra_json = merge_extra_json(entity.extra_json, override.get("extra_json"))
    provenance = dict(extra_json.get("_provenance", {}))
    provenance["manual_override"] = ["data/overrides.zh-CN.json"]
    extra_json["_provenance"] = provenance
    updates["extra_json"] = extra_json
    if "name_zh" in updates:
        updates["translation_status"] = overridden_translation_status(entity, updates["name_zh"])
    return entity.model_copy(update=updates)


def merge_extra_json(
    current: dict[str, Any], override: object
) -> dict[str, Any]:
    extra_json = dict(current)
    if override is None:
        return extra_json
    if not isinstance(override, dict):
        raise ValueError("extra_json 覆盖必须是对象")
    reject_required_image_override(current, override)
    extra_json.update(override)
    return extra_json


def reject_unsupported_override_fields(override: dict[str, object]) -> None:
    unsupported = sorted(set(override) - EDITABLE_FIELDS - {"extra_json"})
    if unsupported:
        raise ValueError(f"不支持的手工覆盖字段：{'、'.join(unsupported)}")


def overridden_translation_status(entity: NormalizedEntity, name_zh: object) -> str:
    if entity.translation_status == "not_applicable":
        return entity.translation_status
    if not isinstance(name_zh, str):
        raise ValueError("name_zh 覆盖必须是字符串")
    if not name_zh.strip():
        return "missing"
    return "complete" if is_displayable_translation(name_zh) else "invalid"


def reject_required_image_override(current: dict[str, Any], override: dict[str, object]) -> None:
    if not current.get("imageRequired"):
        return
    fields = sorted(PROTECTED_IMAGE_FIELDS.intersection(override))
    if fields:
        raise ValueError(f"必需图片元数据不可手工覆盖：{'、'.join(fields)}")
