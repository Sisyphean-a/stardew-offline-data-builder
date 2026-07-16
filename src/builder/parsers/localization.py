from __future__ import annotations

import re
from pathlib import Path

from builder.models import DiscoveredJsonFile, RawEntity
from builder.parsers.localization_values import resolve_bundle_area_name
from builder.utils.json_io import load_json_file

ENTITY_TYPE_KEYWORDS = {
    "object": ("object",),
    "crop": ("crop",),
    "fish": ("fish",),
    "villager": ("villager", "npc"),
    "villager_gift": ("gift",),
    "npc_schedule": ("schedule",),
    "cooking_recipe": ("cooking", "recipe-cooking"),
    "crafting_recipe": ("crafting", "recipe-crafting"),
    "tailoring_recipe": ("tailoring", "recipe-tailoring"),
    "shop": ("shop",),
    "quest": ("quest",),
    "bundle": ("bundle",),
    "monster": ("monster",),
    "drop": ("drop",),
    "mineral": ("mineral",),
    "weapon": ("weapon",),
    "ring": ("ring",),
    "achievement": ("achievement",),
    "special_order": ("special-order", "specialorder"),
    "ginger_island": ("ginger-island", "gingerisland"),
}

LOCALIZED_TEXT = re.compile(r"^\[LocalizedText\s+([^:]+):([^\]]+)\]$")
PLACEHOLDER_TEXT = re.compile(r"^\[([^\[\]]+)\]$")
LOCALE_SUFFIX = re.compile(r"\.([a-z]{2}-[A-Z]{2})$")
LOCALIZATION_ASSETS = {
    "object": ("strings/objects", "strings/bigcraftables"),
    "crop": ("strings/objects",),
    "fish": ("strings/objects",),
    "villager": ("strings/npcnames",),
    "weapon": ("strings/weapons", "strings/objects"),
    "footwear": ("strings/objects",),
    "ring": ("strings/objects",),
    "tool": ("strings/tools", "strings/objects"),
    "cooking_recipe": ("strings/objects",),
    "crafting_recipe": ("strings/objects",),
}
PLACEHOLDER_ASSETS = {"special_order": ("strings/specialorderstrings",)}


def classify_localized_json(path: Path, payload: object) -> DiscoveredJsonFile | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        return None

    entity_type = payload.get("entityType")
    locale = payload.get("locale")
    if not isinstance(entity_type, str):
        entity_type = infer_entity_type(path)
    if not isinstance(locale, str):
        locale = infer_locale(path)
    if entity_type is None:
        return None
    return DiscoveredJsonFile(path=str(path), entity_type=entity_type, locale=locale)


def infer_entity_type(path: Path) -> str | None:
    stem = path.stem.lower()
    for entity_type, keywords in ENTITY_TYPE_KEYWORDS.items():
        if any(keyword in stem for keyword in keywords):
            return entity_type
    return None


def infer_locale(path: Path) -> str:
    stem = path.stem
    for locale in ("zh-CN", "en"):
        if locale.lower() in stem.lower():
            return locale
    return "en"


def build_raw_entities_from_entries(
    path: Path,
    payload: object,
    locale: str | None,
    entity_type: str,
    source: str,
) -> list[RawEntity]:
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError(f"无法解析 JSON：{path}")

    entities: list[RawEntity] = []
    for entry in payload["entries"]:
        if not isinstance(entry, dict):
            raise ValueError(f"条目格式错误：{path}")
        source_id = str(entry["id"])
        required_keys = required_entry_keys()
        attributes = {key: value for key, value in entry.items() if key not in required_keys}
        entities.append(
            RawEntity(
                source=source,
                entity_type=entity_type,
                source_id=source_id,
                internal_name=optional_text(entry.get("internalName")),
                name=optional_text(entry.get("name")),
                description=optional_text(entry.get("description")),
                locale=locale,
                attributes=attributes,
                source_file=str(path),
            )
        )
    return entities


def parse_generic_localized_file(
    path: Path,
    payload: object,
    locale: str | None,
    entity_type: str,
) -> list[RawEntity]:
    return build_raw_entities_from_entries(
        path,
        payload,
        locale,
        entity_type=entity_type,
        source="official",
    )


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def required_entry_keys() -> set[str]:
    return {"id", "internalName", "name", "description"}


def load_localization_tables(unpacked_dir: Path) -> dict[str, dict[str, dict[str, str]]]:
    tables: dict[str, dict[str, dict[str, str]]] = {}
    strings_dir = unpacked_dir / "Strings"
    if not strings_dir.exists():
        return tables
    for path in sorted(strings_dir.rglob("*.json")):
        if not uses_requested_locale(path):
            continue
        payload = load_json_file(path)
        if not is_string_table(payload):
            continue
        locale = infer_locale(path)
        tables.setdefault(locale, {})[localization_asset_key(path, unpacked_dir)] = {
            str(key): str(value) for key, value in payload.items()
        }
    return tables


def localize_official_entities(
    entities: list[RawEntity], tables: dict[str, dict[str, dict[str, str]]]
) -> list[RawEntity]:
    localized: list[RawEntity] = []
    for entity in entities:
        localized.extend(localize_entity(entity, tables))
    return localized


def localize_entity(
    entity: RawEntity, tables: dict[str, dict[str, dict[str, str]]]
) -> list[RawEntity]:
    if entity.locale == "zh-CN":
        return [resolve_entity_locale(entity, "zh-CN", tables)]

    english = resolve_entity_locale(entity, "en", tables)
    chinese = resolve_entity_locale(entity, "zh-CN", tables)
    if chinese.name or chinese.description:
        return [english, chinese]
    return [english]


def resolve_entity_locale(
    entity: RawEntity,
    locale: str,
    tables: dict[str, dict[str, dict[str, str]]],
) -> RawEntity:
    name = resolve_source_text(entity.name, entity.locale, entity.entity_type, locale, tables)
    description = resolve_source_text(
        entity.description, entity.locale, entity.entity_type, locale, tables
    )
    fallback_name = lookup_localized_field(entity, "name", locale, tables)
    fallback_description = lookup_localized_field(entity, "description", locale, tables)
    return entity.model_copy(
        update={
            "locale": locale,
            "name": fallback_name or name,
            "description": fallback_description or description,
        }
    )


def resolve_source_text(
    value: str | None,
    source_locale: str | None,
    entity_type: str,
    locale: str,
    tables: dict[str, dict[str, dict[str, str]]],
) -> str | None:
    if value is None:
        return None
    if LOCALIZED_TEXT.match(value):
        return resolve_text(value, locale, tables)
    placeholder = PLACEHOLDER_TEXT.match(value)
    if placeholder is not None:
        return resolve_placeholder_text(entity_type, placeholder.group(1), locale, tables)
    if entity_type == "bundle":
        localized = resolve_bundle_area_name(value, source_locale, locale, tables)
        if localized:
            return localized
    if source_locale == locale:
        return value
    return None


def resolve_text(
    value: str | None,
    locale: str,
    tables: dict[str, dict[str, dict[str, str]]],
) -> str | None:
    if value is None:
        return None
    match = LOCALIZED_TEXT.match(value)
    if match is None:
        return value
    asset, key = match.groups()
    return tables.get(locale, {}).get(normalize_asset_key(asset), {}).get(key)


def resolve_placeholder_text(
    entity_type: str,
    key: str,
    locale: str,
    tables: dict[str, dict[str, dict[str, str]]],
) -> str | None:
    for asset in PLACEHOLDER_ASSETS.get(entity_type, ()):
        value = tables.get(locale, {}).get(asset, {}).get(key)
        if value:
            return value
    return None


def lookup_localized_field(
    entity: RawEntity,
    field: str,
    locale: str,
    tables: dict[str, dict[str, dict[str, str]]],
) -> str | None:
    internal_name = entity.internal_name or entity.source_id
    for asset in LOCALIZATION_ASSETS.get(entity.entity_type, ()):
        table = tables.get(locale, {}).get(asset, {})
        for key in localization_keys(entity.entity_type, internal_name, field):
            value = table.get(key)
            if value:
                return value
    return None


def localization_keys(entity_type: str, internal_name: str, field: str) -> tuple[str, ...]:
    if entity_type == "villager" and field == "name":
        return (internal_name,)
    suffix = "Name" if field == "name" else "Description"
    compact_name = internal_name.replace(" ", "")
    return (
        f"{internal_name}_{suffix}",
        f"{compact_name}_{suffix}",
        f"{entity_type.title().replace('_', '')}_{compact_name}",
    )


def is_string_table(payload: object) -> bool:
    return isinstance(payload, dict) and all(isinstance(value, str) for value in payload.values())


def localization_asset_key(path: Path, unpacked_dir: Path) -> str:
    relative = path.relative_to(unpacked_dir)
    stem = relative.stem
    for locale in ("zh-CN", "en"):
        suffix = f".{locale}"
        if stem.lower().endswith(suffix.lower()):
            stem = stem[: -len(suffix)]
            break
    return normalize_asset_key(str(relative.with_name(stem).with_suffix("")))


def normalize_asset_key(value: str) -> str:
    return re.sub(r"/+", "/", value.replace("\\", "/")).strip("/").lower()


def uses_requested_locale(path: Path) -> bool:
    match = LOCALE_SUFFIX.search(path.stem)
    return match is None or match.group(1) in {"en", "zh-CN"}
