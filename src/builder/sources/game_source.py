from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from builder.models import DiscoveredJsonFile, RawEntity
from builder.parsers.localization import load_localization_tables, localize_official_entities
from builder.parsers.official import parse_official_file
from builder.parsers.official_assets import classify_official_json, uses_requested_locale
from builder.utils.json_io import load_json_file


@dataclass
class GameSourceLoad:
    entities: list[RawEntity] = field(default_factory=list)
    discovered: list[dict[str, object]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def discover_game_json_files(unpacked_dir: Path) -> list[DiscoveredJsonFile]:
    discovered: list[DiscoveredJsonFile] = []
    for json_file in game_json_candidates(unpacked_dir):
        payload = load_json_file(json_file)
        classified = classify_official_json(json_file, payload)
        if classified is not None:
            discovered.append(classified)
    return discovered


def load_game_data_from_unpacked_dir(unpacked_dir: Path) -> GameSourceLoad:
    result = GameSourceLoad()
    for json_file in game_json_candidates(unpacked_dir):
        load_game_json_file(unpacked_dir, json_file, result)
    result.entities = localize_official_entities(
        result.entities,
        load_localization_tables(unpacked_dir),
    )
    result.entities = enrich_linked_entities(result.entities)
    return result


def load_raw_entities_from_unpacked_dir(unpacked_dir: Path) -> list[RawEntity]:
    return load_game_data_from_unpacked_dir(unpacked_dir).entities


def game_json_candidates(unpacked_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(unpacked_dir.rglob("*.json"))
        if is_game_data_candidate(path.relative_to(unpacked_dir)) and uses_requested_locale(path)
    ]


def is_game_data_candidate(relative_path: Path) -> bool:
    parts = tuple(part.lower() for part in relative_path.parts)
    if not parts:
        return False
    if parts[0] == "data":
        return True
    return parts[0] == "characters" and "schedules" in parts


def load_game_json_file(unpacked_dir: Path, path: Path, result: GameSourceLoad) -> None:
    relative_path = path.relative_to(unpacked_dir).as_posix()
    try:
        payload = load_json_file(path)
    except Exception as exc:
        result.errors.append(source_error(relative_path, "读取 JSON 失败", exc))
        return

    discovered = classify_official_json(path, payload)
    if discovered is None:
        result.discovered.append({"path": relative_path, "status": "unrecognized"})
        return

    try:
        entities = parse_official_file(discovered, payload)
    except Exception as exc:
        result.errors.append(source_error(relative_path, "解析官方数据失败", exc))
        return

    result.entities.extend(
        entity.model_copy(update={"source_file": relative_path}) for entity in entities
    )
    result.discovered.append(
        {
            "path": relative_path,
            "status": "parsed",
            "entityType": discovered.entity_type,
            "locale": discovered.locale,
            "entities": len(entities),
        }
    )


def enrich_linked_entities(entities: list[RawEntity]) -> list[RawEntity]:
    objects = {
        (entity.source_id, entity.locale): entity
        for entity in entities
        if entity.entity_type == "object"
    }
    enriched = [enrich_linked_entity(entity, objects) for entity in entities]
    existing = {(entity.entity_type, entity.source_id, entity.locale) for entity in enriched}
    for entity in entities:
        if entity.entity_type not in {"crop", "drop"}:
            continue
        linked_id = linked_object_id(entity)
        chinese_object = objects.get((linked_id, "zh-CN"))
        key = (entity.entity_type, entity.source_id, "zh-CN")
        if chinese_object is not None and key not in existing:
            enriched.append(
                enrich_linked_entity(entity.model_copy(update={"locale": "zh-CN"}), objects)
            )
            existing.add(key)
    return enriched


def enrich_linked_entity(
    entity: RawEntity,
    objects: dict[tuple[str, str | None], RawEntity],
) -> RawEntity:
    if entity.entity_type not in {"crop", "drop", "fish"}:
        return entity
    object_entity = objects.get((linked_object_id(entity), entity.locale))
    if object_entity is None:
        return entity
    attributes = dict(entity.attributes)
    for key in ("imageSource", "spriteIndex", "imageRect", "imageMode"):
        if key not in attributes and key in object_entity.attributes:
            attributes[key] = object_entity.attributes[key]
    return entity.model_copy(
        update={
            "internal_name": entity.internal_name or object_entity.internal_name,
            "name": entity.name or object_entity.name,
            "description": entity.description or object_entity.description,
            "attributes": attributes,
        }
    )


def linked_object_id(entity: RawEntity) -> str:
    if entity.entity_type == "drop":
        item_id = entity.attributes.get("itemId")
        if isinstance(item_id, str):
            return item_id
    return entity.source_id


def source_error(path: str, reason: str, exc: Exception) -> dict[str, str]:
    return {"source": "official", "source_file": path, "reason": reason, "detail": str(exc)}
