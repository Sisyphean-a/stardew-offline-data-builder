from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from builder.models import DiscoveredJsonFile, RawEntity
from builder.parsers.localization import build_raw_entities_from_entries, optional_text
from builder.parsers.official_assets import LOCALE_SUFFIX, unwrap_content
from builder.parsers.official_visuals import apply_image_metadata
from builder.pipeline.official_values import (
    parse_bundle_ingredients,
    parse_ingredients,
    parse_int,
)


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
    apply_image_metadata(attributes, discovered.entity_type, internal_name, source_id)
    if discovered.entity_type == "tool":
        add_tool_upgrade_metadata(attributes)
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
    fields = value.split("^" if discovered.entity_type == "achievement" else "/")
    internal_name = legacy_internal_name(discovered.entity_type, source_id, fields)
    explicit_display_name = legacy_recipe_display_name(discovered.entity_type, fields)
    name = explicit_display_name or legacy_display_name(
        discovered.entity_type, fields, internal_name
    )
    # Keep the compact official record only in the explicit v4 payload while
    # exposing its typed build-time mapping separately.  The schema-5
    # candidate consumes ``source_attributes`` and never parses these fields.
    attributes: dict[str, Any] = {
        "legacyFields": fields,
        "legacyValue": value,
        "sourceFormat": "official_compact",
        "typedRecordKind": f"{discovered.entity_type}-v1",
    }
    if explicit_display_name:
        attributes["hasExplicitDisplayName"] = True
    add_recipe_output_metadata(attributes, discovered.entity_type, fields)
    add_legacy_structured_metadata(attributes, discovered.entity_type, fields)
    if discovered.entity_type == "crop" and len(fields) > 3:
        attributes["HarvestItemId"] = fields[3]
        source_id = fields[3] or source_id
    apply_image_metadata(
        attributes, discovered.entity_type, internal_name, source_id, fields
    )
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


def add_legacy_structured_metadata(
    attributes: dict[str, Any], entity_type: str, fields: list[str]
) -> None:
    if entity_type == "achievement":
        attributes.update(
            compact_typed_values(
                {
                    "achievementTitle": legacy_text(fields, 0),
                    "achievementDescription": legacy_text(fields, 1),
                    "achievementSecret": legacy_bool(fields, 2),
                    "achievementIconIndex": legacy_int(fields, 3),
                    "achievementSortOrder": legacy_int(fields, 4),
                }
            )
        )
    elif entity_type == "quest":
        attributes.update(
            compact_typed_values(
                {
                    "questType": legacy_text(fields, 0),
                    "questTitle": legacy_text(fields, 1),
                    "questDescription": legacy_text(fields, 2),
                    "questObjective": legacy_text(fields, 3),
                    "questLocation": legacy_text(fields, 4),
                    # 官方 Quests 记录：第 5 段是奖励物品 ID（-1 表示无），
                    # 第 6 段是金币奖励，第 8 段是是否可重复。
                    "questRewardItemId": legacy_text(fields, 5),
                    "questRewardGold": legacy_int(fields, 6),
                    "questRepeatable": legacy_bool(fields, 8),
                }
            )
        )
    elif entity_type == "furniture":
        attributes.update(
            compact_typed_values(
                {
                    "furnitureDisplayName": legacy_text(fields, 7),
                    "furnitureType": legacy_text(fields, 1),
                    "furniturePrice": legacy_int(fields, 5),
                }
            )
        )
    elif entity_type == "footwear":
        # Boots 旧格式：名称/描述/价格/防御/免疫/贴图索引/显示名。
        attributes.update(
            compact_typed_values(
                {
                    "footwearDescription": legacy_text(fields, 1),
                    "footwearPrice": legacy_int(fields, 2),
                    "footwearDefense": legacy_int(fields, 3),
                    "footwearImmunity": legacy_int(fields, 4),
                    "footwearDisplayName": legacy_text(fields, 6),
                }
            )
        )
    elif entity_type == "monster":
        attributes.update(
            compact_typed_values(
                {
                    "monsterHealth": legacy_int(fields, 0),
                    "monsterDamage": legacy_int(fields, 1),
                    "monsterCanFly": legacy_bool(fields, 4),
                    "monsterDropText": legacy_text(fields, 6),
                }
            )
        )
    elif entity_type == "ginger_island":
        attributes["eventKey"] = "/".join(fields)
    elif entity_type == "fish":
        if len(fields) < 14 or legacy_int(fields, 1) is None:
            attributes["CaptureMethod"] = "trap"
            return
        values: dict[str, Any] = {
            "Difficulty": legacy_int(fields, 1),
            "Behavior": legacy_text(fields, 2),
            "MinSize": legacy_int(fields, 3),
            "MaxSize": legacy_int(fields, 4),
            "FishingTime": legacy_text(fields, 5),
            "Seasons": split_words(fields, 6),
            "Weather": legacy_text(fields, 7),
        }
        attributes.update({key: value for key, value in values.items() if value is not None})
    elif entity_type in {"cooking_recipe", "crafting_recipe"}:
        ingredients = parse_ingredients(fields[0] if fields else None)
        if ingredients:
            attributes["Ingredients"] = ingredients
        if entity_type == "crafting_recipe" and len(fields) > 4:
            unlock = legacy_text(fields, 4)
            if unlock and unlock != "null":
                attributes["UnlockCondition"] = unlock
    elif entity_type == "bundle":
        ingredients = parse_bundle_ingredients(fields[2] if len(fields) > 2 else None)
        if ingredients:
            attributes["BundleIngredients"] = ingredients
        # 官方 Bundles 记录：第 1 段是奖励物品（"类型 ID 数量"，如 "O 465 20"）。
        rewards = parse_bundle_rewards(fields[1] if len(fields) > 1 else None)
        if rewards:
            attributes["BundleRewards"] = rewards
    elif entity_type == "villager_gift":
        # NPCGiftTastes 记录为「反应台词/物品列表」交错格式：台词占偶数位，
        # 物品列表按 喜爱/喜欢/一般/讨厌/不喜欢 顺序占奇数位 1/3/5/7/9
        # （与游戏 NPC.getGiftTasteForThisItem 的读取方式一致）。
        preferences = ("loved", "liked", "neutral", "disliked", "hated")
        attributes["GiftTastes"] = [
            {"preference": preference, "items": split_words(fields, index) or []}
            for preference, index in zip(preferences, (1, 3, 5, 7, 9), strict=False)
            if index < len(fields)
        ]
    elif entity_type == "npc_schedule":
        schedule = parse_legacy_schedule(fields)
        if schedule:
            attributes["ScheduleEntries"] = schedule


def parse_bundle_rewards(value: object) -> list[dict[str, object]] | None:
    """Bundle reward tokens: "O 465 20" / "BO 10 1" (type, id, quantity)."""
    if not isinstance(value, str):
        return None
    parts = value.split()
    if len(parts) != 3:
        return None
    quantity = parse_int(parts[2])
    if quantity is None:
        return None
    return [{"itemId": parts[1], "quantity": quantity}]


def parse_legacy_schedule(fields: list[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for field in fields:
        text = field.strip()
        if not text:
            continue
        parts = text.split()
        if len(parts) >= 2 and parts[0].isdigit():
            entries.append(
                {
                    "time": int(parts[0]),
                    "location": parts[1],
                    "route": parts[2:],
                }
            )
        else:
            # Commands such as GOTO, warp and friendship gates are still
            # official schedule rules. Preserve them as an explicit typed rule
            # instead of dropping them or forwarding legacyFields downstream.
            entries.append({"rule": text})
    return entries


def compact_typed_values(values: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


def legacy_text(fields: list[str], index: int) -> str | None:
    value = fields[index] if len(fields) > index else None
    return value.strip() or None if isinstance(value, str) else None


def legacy_bool(fields: list[str], index: int) -> bool | None:
    value = legacy_text(fields, index)
    if value is None:
        return None
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    return None


def legacy_int(fields: list[str], index: int) -> int | None:
    value = fields[index] if len(fields) > index else None
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def split_words(fields: list[str], index: int) -> list[str] | None:
    value = legacy_text(fields, index)
    return value.split() if value else None


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


def add_tool_upgrade_metadata(attributes: dict[str, Any]) -> None:
    upgrade_level = legacy_int_value(attributes.get("UpgradeLevel"))
    conventional = attributes.get("ConventionalUpgradeFrom")
    custom = attributes.get("UpgradeFrom")
    upgrades = custom if isinstance(custom, list) else []
    if isinstance(conventional, str) and conventional.strip():
        material_by_level = {1: "334", 2: "335", 3: "336", 4: "337"}
        price_by_level = {1: 2000, 2: 5000, 3: 10000, 4: 25000}
        attributes.update(
            compact_typed_values(
                {
                    "UpgradeRequireToolId": conventional,
                    "UpgradeMaterial": material_by_level.get(upgrade_level),
                    "UpgradeMaterialQuantity": 5,
                    "UpgradeCost": price_by_level.get(upgrade_level),
                }
            )
        )
        return
    if not upgrades:
        return
    first = upgrades[0] if isinstance(upgrades[0], dict) else {}
    if not isinstance(first, dict):
        return
    attributes.update(
        compact_typed_values(
            {
                "UpgradeCondition": first.get("Condition"),
                "UpgradeRequireToolId": first.get("RequireToolId"),
                "UpgradeMaterial": first.get("TradeItemId"),
                "UpgradeMaterialQuantity": legacy_int_value(first.get("TradeItemAmount")),
                "UpgradeCost": legacy_int_value(first.get("Price")),
            }
        )
    )


def legacy_int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
    seen: set[tuple[str, str]] = set()
    sequence = 0
    for index in range(0, len(drops) - 1, 2):
        item_id, chance = drops[index : index + 2]
        pair = (item_id, chance)
        if pair in seen:
            continue
        seen.add(pair)
        entities.append(
            RawEntity(
                source="official",
                entity_type="drop",
                source_id=f"{monster_id}:{sequence}",
                internal_name=f"{monster_id}:{item_id}",
                name=None,
                description=None,
                locale=discovered.locale,
                attributes={"monsterId": monster_id, "itemId": item_id, "chance": chance},
                source_file=str(path),
            )
        )
        sequence += 1
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
    if entity_type in {"fish", "furniture", "footwear"} and fields and fields[0]:
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
    if entity_type == "footwear" and len(fields) > 6 and fields[6]:
        return fields[6]
    if entity_type == "monster" and fields and fields[-1]:
        return fields[-1]
    if entity_type in {"achievement", "fish"} and fields and fields[0]:
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
    indexes = {"quest": 2, "achievement": 1, "footwear": 1}
    index = indexes.get(entity_type)
    if index is not None and len(fields) > index and fields[index]:
        return fields[index]
    return None
