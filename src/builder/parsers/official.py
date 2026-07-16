from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from builder.models import DiscoveredJsonFile, RawEntity
from builder.parsers.localization import build_raw_entities_from_entries, optional_text
from builder.parsers.official_assets import LOCALE_SUFFIX, unwrap_content


def parse_official_file(
    discovered: DiscoveredJsonFile,
    payload: object,
) -> list[RawEntity]:
    path = Path(discovered.path)
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return build_raw_entities_from_entries(
            path,
            payload,
            discovered.locale,
            entity_type=discovered.entity_type,
            source="official",
        )
    content = unwrap_content(payload)
    if isinstance(content, dict):
        return list(parse_mapping(path, content, discovered))
    if isinstance(content, list):
        return list(parse_list(path, content, discovered))
    raise ValueError(f"不支持的官方数据根结构：{path}")


def parse_mapping(
    path: Path,
    payload: dict[object, object],
    discovered: DiscoveredJsonFile,
) -> Iterable[RawEntity]:
    for key, value in payload.items():
        source_id = namespaced_source_id(discovered.entity_type, path, str(key))
        if isinstance(value, dict):
            entity = build_mapping_entity(path, source_id, value, discovered)
            yield entity
            yield from build_object_specializations(entity)
        elif isinstance(value, str):
            entity = build_legacy_entity(path, source_id, value, discovered)
            yield entity
            if discovered.entity_type == "monster":
                yield from build_monster_drops(path, source_id, value, discovered)


def parse_list(
    path: Path,
    payload: list[object],
    discovered: DiscoveredJsonFile,
) -> Iterable[RawEntity]:
    for index, value in enumerate(payload):
        if not isinstance(value, dict):
            continue
        source_id = select_record_id(value, str(index), discovered.entity_type)
        source_id = namespaced_source_id(discovered.entity_type, path, source_id)
        yield build_mapping_entity(path, source_id, value, discovered)


def build_mapping_entity(
    path: Path,
    fallback_id: str,
    value: dict[object, object],
    discovered: DiscoveredJsonFile,
) -> RawEntity:
    attributes = {str(key): item for key, item in value.items()}
    if discovered.entity_type == "crop":
        attributes["SeedItemId"] = fallback_id
    source_id = select_record_id(attributes, fallback_id, discovered.entity_type)
    internal_name = select_internal_name(attributes, discovered.entity_type, source_id)
    name = first_text(
        attributes,
        ("DisplayName", "displayName", "Title", "title", "Name", "name"),
    )
    if discovered.entity_type == "bundle":
        name = name or optional_text(attributes.get("AreaName"))
    description = first_text(attributes, ("Description", "description", "Text", "text"))
    apply_image_metadata(attributes, discovered.entity_type, internal_name)
    return RawEntity(
        source="official",
        entity_type=discovered.entity_type,
        source_id=source_id,
        internal_name=internal_name,
        name=name,
        description=description,
        locale=discovered.locale,
        attributes=attributes,
        source_file=str(path),
    )


def build_legacy_entity(
    path: Path,
    source_id: str,
    value: str,
    discovered: DiscoveredJsonFile,
) -> RawEntity:
    fields = value.split("/")
    internal_name = legacy_internal_name(discovered.entity_type, source_id, fields)
    explicit_display_name = legacy_recipe_display_name(discovered.entity_type, fields)
    name = explicit_display_name or legacy_display_name(
        discovered.entity_type, fields, internal_name
    )
    attributes: dict[str, Any] = {"legacyFields": fields, "legacyValue": value}
    if explicit_display_name:
        attributes["hasExplicitDisplayName"] = True
    add_recipe_output_metadata(attributes, discovered.entity_type, fields)
    if discovered.entity_type == "crop" and len(fields) > 3:
        attributes["HarvestItemId"] = fields[3]
        source_id = fields[3] or source_id
    apply_image_metadata(attributes, discovered.entity_type, internal_name)
    return RawEntity(
        source="official",
        entity_type=discovered.entity_type,
        source_id=source_id,
        internal_name=internal_name,
        name=name,
        description=legacy_description(discovered.entity_type, fields),
        locale=discovered.locale,
        attributes=attributes,
        source_file=str(path),
    )


def add_recipe_output_metadata(
    attributes: dict[str, Any], entity_type: str, fields: list[str]
) -> None:
    if entity_type not in {"cooking_recipe", "crafting_recipe"} or len(fields) < 3:
        return
    output_parts = fields[2].split()
    if not output_parts:
        return
    attributes["outputItemId"] = output_parts[0]
    if entity_type == "crafting_recipe" and len(fields) > 3 and fields[3].lower() == "true":
        attributes["outputEntityType"] = "big_craftable"
    else:
        attributes["outputEntityType"] = "object"


def build_object_specializations(entity: RawEntity) -> Iterable[RawEntity]:
    if entity.entity_type != "object":
        return []
    value_type = entity.attributes.get("Type")
    if value_type == "Minerals":
        return [entity.model_copy(update={"entity_type": "mineral"})]
    if value_type == "Ring":
        return [entity.model_copy(update={"entity_type": "ring"})]
    return []


def build_monster_drops(
    path: Path,
    monster_id: str,
    value: str,
    discovered: DiscoveredJsonFile,
) -> Iterable[RawEntity]:
    fields = value.split("/")
    if len(fields) <= 6:
        return []
    drops = fields[6].split()
    entities: list[RawEntity] = []
    for index in range(0, len(drops) - 1, 2):
        item_id, chance = drops[index : index + 2]
        entities.append(
            RawEntity(
                source="official",
                entity_type="drop",
                source_id=f"{monster_id}:{index // 2}",
                internal_name=f"{monster_id}:{item_id}",
                name=None,
                description=None,
                locale=discovered.locale,
                attributes={"monsterId": monster_id, "itemId": item_id, "chance": chance},
                source_file=str(path),
            )
        )
    return entities


def select_record_id(
    value: dict[str, object], fallback_id: str, entity_type: str
) -> str:
    if entity_type == "crop":
        harvest_item_id = value.get("HarvestItemId")
        if harvest_item_id is not None and str(harvest_item_id):
            return str(harvest_item_id)
    for key in ("Id", "id", "ItemId", "itemId", "Key"):
        candidate = value.get(key)
        if candidate is not None and str(candidate):
            return str(candidate)
    return fallback_id


def namespaced_source_id(entity_type: str, path: Path, source_id: str) -> str:
    if entity_type not in {"npc_schedule", "ginger_island"}:
        return source_id
    asset_name = LOCALE_SUFFIX.sub("", path.stem)
    return f"{asset_name}:{source_id}"


def first_text(value: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        candidate = optional_text(value.get(key))
        if candidate:
            return candidate
    return None


def select_internal_name(
    value: dict[str, object], entity_type: str, source_id: str
) -> str | None:
    if entity_type == "special_order":
        return source_id
    if entity_type == "crop":
        return first_text(value, ("SeedName", "Name", "name"))
    return first_text(value, ("InternalName", "Name", "name", "Id", "id")) or source_id


def legacy_internal_name(entity_type: str, source_id: str, fields: list[str]) -> str:
    if entity_type in {"fish", "furniture"} and fields and fields[0]:
        return fields[0]
    return source_id


def legacy_display_name(entity_type: str, fields: list[str], fallback: str) -> str:
    if entity_type == "quest" and len(fields) > 1 and fields[1]:
        return fields[1]
    if entity_type == "bundle" and fields and fields[-1]:
        return fields[-1]
    if entity_type == "object" and len(fields) > 4 and fields[4]:
        return fields[4]
    if entity_type == "furniture" and len(fields) > 7 and fields[7]:
        return fields[7]
    if entity_type == "fish" and fields and fields[0]:
        return fields[0]
    return fallback


def legacy_recipe_display_name(entity_type: str, fields: list[str]) -> str | None:
    if entity_type not in {"cooking_recipe", "crafting_recipe"}:
        return None
    for field in fields:
        if field.startswith("[LocalizedText "):
            return field
    return None


def legacy_description(entity_type: str, fields: list[str]) -> str | None:
    if entity_type == "quest" and len(fields) > 2 and fields[2]:
        return fields[2]
    return None


def apply_image_metadata(
    attributes: dict[str, Any], entity_type: str, internal_name: str | None
) -> None:
    texture = attributes.get("Texture") or attributes.get("TextureName")
    if entity_type == "villager":
        apply_villager_image_metadata(attributes, texture, internal_name)
    elif isinstance(texture, str) and texture:
        attributes["imageSource"] = texture.replace("\\", "/") + ".png"
    elif entity_type == "object":
        attributes["imageSource"] = "Maps/springobjects.png"
    if isinstance(attributes.get("SpriteIndex"), int):
        attributes["spriteIndex"] = attributes["SpriteIndex"]


def apply_villager_image_metadata(
    attributes: dict[str, Any], texture: object, internal_name: str | None
) -> None:
    if isinstance(texture, str) and texture:
        normalized_texture = texture.replace("\\", "/")
        texture_name = Path(normalized_texture).name
        attributes["imageSource"] = f"Portraits/{texture_name}.png"
        attributes["imageFallbackSources"] = [
            f"Characters/{normalized_texture}.png",
            f"{normalized_texture}.png",
        ]
    elif internal_name:
        attributes["imageSource"] = f"Portraits/{internal_name}.png"
    attributes["imageMode"] = "full"
