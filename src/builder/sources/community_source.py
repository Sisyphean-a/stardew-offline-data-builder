from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from builder.models import RawEntity
from builder.parsers.localization import build_raw_entities_from_entries, optional_text
from builder.parsers.official_assets import infer_entity_type
from builder.utils.json_io import load_json_file

COMMUNITY_TYPE_RULES = {
    "achievements": "achievement",
    "bundles": "bundle",
    "cooking": "cooking_recipe",
    "crafting": "crafting_recipe",
    "crops": "crop",
    "fish": "fish",
    "monster-loot": "drop",
    "monsters": "monster",
    "quests": "quest",
    "rings": "ring",
    "special-orders": "special_order",
    "villagers": "villager",
    "weapons": "weapon",
}
OBJECT_DATASETS = {
    "artifacts",
    "artisan-goods",
    "bait",
    "forageables",
    "mixed-seeds",
    "rarecrows",
    "special-items",
    "tackle",
}


@dataclass
class CommunitySourceLoad:
    entities: list[RawEntity] = field(default_factory=list)
    discovered: list[dict[str, object]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def community_data_exists(path: Path) -> bool:
    return path.exists() and path.is_dir()


def load_community_data_from_dir(community_dir: Path) -> CommunitySourceLoad:
    result = CommunitySourceLoad()
    for json_file in sorted(community_dir.rglob("*.json")):
        load_community_json_file(community_dir, json_file, result)
    return result


def load_raw_entities_from_community_dir(community_dir: Path) -> list[RawEntity]:
    return load_community_data_from_dir(community_dir).entities


def load_community_json_file(
    community_dir: Path, path: Path, result: CommunitySourceLoad
) -> None:
    relative_path = path.relative_to(community_dir).as_posix()
    try:
        payload = load_json_file(path)
    except Exception as exc:
        result.errors.append(source_error(relative_path, "读取 JSON 失败", exc))
        return

    entity_type = community_entity_type(path, payload)
    if entity_type is None:
        result.discovered.append({"path": relative_path, "status": "unrecognized"})
        return
    try:
        entities = parse_community_payload(path, payload, entity_type)
    except Exception as exc:
        result.errors.append(source_error(relative_path, "解析社区数据失败", exc))
        return

    result.entities.extend(
        entity.model_copy(update={"source_file": relative_path}) for entity in entities
    )
    result.discovered.append(
        {
            "path": relative_path,
            "status": "parsed",
            "entityType": entity_type,
            "entities": len(entities),
        }
    )


def community_entity_type(path: Path, payload: object) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        entity_type = payload.get("entityType")
        return str(entity_type) if entity_type else None
    stem = path.stem.lower()
    if stem.endswith("-shop"):
        return "shop"
    if stem in OBJECT_DATASETS:
        return "object"
    if stem in COMMUNITY_TYPE_RULES:
        return COMMUNITY_TYPE_RULES[stem]
    return infer_entity_type(path)


def parse_community_payload(path: Path, payload: object, entity_type: str) -> list[RawEntity]:
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return build_raw_entities_from_entries(path, payload, "en", entity_type, "community")
    if isinstance(payload, list):
        return [
            build_community_entity(path, value, entity_type, index)
            for index, value in enumerate(payload)
            if isinstance(value, dict)
        ]
    if isinstance(payload, dict):
        return [
            build_community_entity(path, value, entity_type, str(key))
            for key, value in payload.items()
            if isinstance(value, dict)
        ]
    raise ValueError(f"不支持的社区数据根结构：{path}")


def build_community_entity(
    path: Path, value: dict[str, Any], entity_type: str, fallback_id: int | str
) -> RawEntity:
    source_id = first_value(value, ("id", "itemId", "item_id", "key")) or str(fallback_id)
    internal_name = first_value(value, ("internalName", "internal_name", "name"))
    name = first_value(value, ("name", "displayName", "title"))
    description = first_value(value, ("description", "text"))
    ignored_keys = {
        "id",
        "itemId",
        "item_id",
        "key",
        "internalName",
        "internal_name",
        "name",
        "description",
    }
    attributes = {
        key: item
        for key, item in value.items()
        if key not in ignored_keys
    }
    return RawEntity(
        source="community",
        entity_type=entity_type,
        source_id=source_id,
        internal_name=internal_name,
        name=name,
        description=description,
        locale="en",
        attributes=attributes,
        source_file=str(path),
    )


def first_value(value: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        candidate = optional_text(value.get(key))
        if candidate:
            return candidate
    return None


def source_error(path: str, reason: str, exc: Exception) -> dict[str, str]:
    return {"source": "community", "source_file": path, "reason": reason, "detail": str(exc)}
