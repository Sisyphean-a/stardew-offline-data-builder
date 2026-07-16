from __future__ import annotations

import re
from pathlib import Path

from builder.models import DiscoveredJsonFile

ASSET_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("villager_gift", ("npcgifttastes", "universalgifts")),
    ("cooking_recipe", ("cookingrecipes", "cookingrecipe")),
    ("tailoring_recipe", ("tailoringrecipes", "tailoringrecipe")),
    ("crafting_recipe", ("craftingrecipes", "craftingrecipe")),
    ("special_order", ("specialorders", "specialorder")),
    ("drop", ("monsterloot", "drops")),
    ("villager", ("characters", "character", "npcdispositions")),
    ("big_craftable", ("bigcraftables", "bigcraftable")),
    ("furniture", ("furniture",)),
    ("object", ("objectinformation", "objects", "object")),
    ("crop", ("crops", "crop")),
    ("fish", ("fish",)),
    ("shop", ("shops", "shop", "lostitemsshop")),
    ("quest", ("quests", "quest", "monsterslayerquests")),
    ("bundle", ("bundles", "bundle", "randombundles")),
    ("monster", ("monsters", "monster")),
    ("mineral", ("minerals", "mineral")),
    ("weapon", ("weapons", "weapon")),
    ("ring", ("rings", "ring")),
    ("achievement", ("achievements", "achievement")),
    ("tool", ("tools", "tool")),
    ("trinket", ("trinkets", "trinket")),
    ("footwear", ("boots", "boot", "footwear")),
)
LOCALE_SUFFIX = re.compile(r"\.([a-z]{2}-[A-Z]{2})$")
SUPPORTING_ASSETS = {"fishponddata", "locations", "machines"}


def classify_official_json(path: Path, payload: object) -> DiscoveredJsonFile | None:
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        entity_type = payload.get("entityType")
        if isinstance(entity_type, str):
            return DiscoveredJsonFile(
                path=str(path), entity_type=entity_type, locale=infer_locale(path)
            )
    if normalized_stem(path) in SUPPORTING_ASSETS:
        return None
    entity_type = infer_entity_type(path)
    if entity_type is None or not is_supported_asset(payload):
        return None
    return DiscoveredJsonFile(path=str(path), entity_type=entity_type, locale=infer_locale(path))


def is_supporting_asset(path: Path) -> bool:
    return normalized_stem(path) in SUPPORTING_ASSETS


def infer_entity_type(path: Path) -> str | None:
    if "schedules" in {part.lower() for part in path.parts}:
        return "npc_schedule"
    normalized = normalized_stem(path)
    for entity_type, patterns in ASSET_TYPE_RULES:
        if normalized in patterns:
            return entity_type
    if normalized.startswith("island") and "events" in {part.lower() for part in path.parts}:
        return "ginger_island"
    return None


def normalized_stem(path: Path) -> str:
    stem = LOCALE_SUFFIX.sub("", path.stem)
    return stem.lower().replace("_", "").replace("-", "")


def infer_locale(path: Path) -> str:
    stem = path.stem.lower()
    if "zh-cn" in stem or "zh_cn" in stem:
        return "zh-CN"
    return "en"


def uses_requested_locale(path: Path) -> bool:
    match = LOCALE_SUFFIX.search(path.stem)
    return match is None or match.group(1) in {"en", "zh-CN"}


def is_supported_asset(payload: object) -> bool:
    return isinstance(unwrap_content(payload), dict | list)


def unwrap_content(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    for key in ("content", "Content", "$content"):
        value = payload.get(key)
        if isinstance(value, dict | list):
            return value
    return payload
