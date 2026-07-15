from __future__ import annotations

from pathlib import Path

from builder.models import DiscoveredJsonFile, RawEntity


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
    if "object" in stem:
        return "object"
    if "crop" in stem:
        return "crop"
    if "fish" in stem:
        return "fish"
    if "villager" in stem or "npc" in stem:
        return "villager"
    return None


def infer_locale(path: Path) -> str | None:
    stem = path.stem
    for locale in ("zh-CN", "en"):
        if locale.lower() in stem.lower():
            return locale
    return None


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


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def required_entry_keys() -> set[str]:
    return {"id", "internalName", "name", "description"}
