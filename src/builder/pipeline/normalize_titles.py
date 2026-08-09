from __future__ import annotations

import re

from builder.models import NormalizedEntity
from builder.pipeline.normalize_images import copy_avatar_metadata, inherit_harvest_item_image
from builder.pipeline.normalize_schedule import (
    display_villager_name,
    referenced_villager,
    resolve_schedule_title,
)
from builder.pipeline.normalize_support import (
    displayable_entity_name,
    drop_record_id,
    humanize_identifier,
    item_key_value,
    reference_key,
    technical_name,
)
from builder.pipeline.provenance import merge_provenance


def apply_contextual_display_data(
    entity: NormalizedEntity,
    villagers: dict[str, NormalizedEntity],
    items: dict[str, NormalizedEntity],
    monsters: dict[str, NormalizedEntity],
) -> NormalizedEntity:
    if entity.entity_type == "crop":
        return inherit_harvest_item_image(entity, items)
    if entity.entity_type == "drop":
        return resolve_drop_title(entity, items, monsters)
    if entity.entity_type == "npc_schedule":
        return resolve_schedule_title(entity, villagers)
    if entity.entity_type == "villager_gift":
        return resolve_gift_title(entity, villagers)
    title_builders = {
        "shop": lambda: shop_title(entity),
        "tailoring_recipe": lambda: tailoring_title(entity, items),
        "ginger_island": lambda: ginger_island_title(entity),
    }
    builder = title_builders.get(entity.entity_type)
    if builder is None:
        return entity
    return entity.model_copy(update={"name_zh": builder(), "name_en": None})


def resolve_gift_title(
    entity: NormalizedEntity, villagers: dict[str, NormalizedEntity]
) -> NormalizedEntity:
    key = (entity.game_id or entity.internal_name or "").strip()
    if key.casefold().startswith("universal_"):
        preference = {
            "dislike": "不喜欢",
            "hate": "厌恶",
            "like": "喜欢",
            "love": "最爱",
            "neutral": "一般",
        }.get(key.rsplit("_", maxsplit=1)[-1].casefold())
        title = f"通用礼物偏好：{preference or '未分类'}"
    else:
        npc = referenced_villager(entity, villagers)
        title = f"{display_villager_name(npc, entity)}的礼物偏好"
    npc = referenced_villager(entity, villagers)
    extra_json = (
        copy_avatar_metadata(entity.extra_json, npc.extra_json)
        if npc
        else merge_provenance(entity.extra_json)
    )
    return entity.model_copy(
        update={"name_zh": title, "name_en": None, "extra_json": extra_json}
    )


def resolve_drop_title(
    entity: NormalizedEntity,
    items: dict[str, NormalizedEntity],
    monsters: dict[str, NormalizedEntity],
) -> NormalizedEntity:
    item_id = entity.extra_json.get("itemId")
    monster_id = entity.extra_json.get("monsterId")
    item = items.get(item_key_value(item_id))
    monster = monsters.get(reference_key(monster_id))
    item_name = displayable_entity_name(item, item_id, "物品")
    monster_name = displayable_entity_name(monster, monster_id, "怪物")
    title = f"{monster_name}掉落：{item_name}（记录{drop_record_id(entity)}）"
    return entity.model_copy(update={"name_zh": title, "name_en": None})


def shop_title(entity: NormalizedEntity) -> str:
    identifier = entity.game_id or entity.internal_name or ""
    name = humanize_identifier(identifier)
    return f"商店：{name}" if name else "商店：未命名（编号未知）"


def tailoring_title(
    entity: NormalizedEntity, items: dict[str, NormalizedEntity]
) -> str:
    output = entity.extra_json.get("CraftedItemId")
    outputs = entity.extra_json.get("CraftedItemIds")
    if output is None and isinstance(outputs, list) and outputs:
        output = outputs[0]
    output_text = str(output or "").strip()
    item = (
        items.get(item_key_value(output))
        if output_text[:3].casefold() not in {"(h)", "(p)", "(s)"}
        else None
    )
    if item is not None:
        output_name = displayable_entity_name(item, output, "产物")
    else:
        output_name = tailoring_source_title(entity)
        if not output_name:
            value = output_text or str(entity.game_id or "").strip()
            output_name = f"编号：{tailoring_fallback_identifier(value)}"
    return f"裁缝配方：{output_name}"


def tailoring_source_title(entity: NormalizedEntity) -> str:
    source_key = (entity.game_id or entity.internal_name or "").strip()
    if not source_key or "/" in source_key or "\\" in source_key:
        return ""
    match = re.fullmatch(
        r"(?P<subject>[A-Za-z][A-Za-z0-9]*?)[_-]From(?P<variant>[A-Za-z0-9][A-Za-z0-9_()\-]*)",
        source_key,
    )
    if match:
        subject = humanize_identifier(match.group("subject"))
        variant = humanize_identifier(match.group("variant"))
        return f"{subject}（材料：{variant}）" if subject and variant else subject
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z][A-Za-z0-9_()\-]*", source_key):
        subject, variant = source_key.split("_", maxsplit=1)
        subject_name = humanize_identifier(subject)
        variant_name = humanize_identifier(variant)
        if subject_name and variant_name:
            return f"{subject_name}（材料：{variant_name}）"
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", source_key):
        return humanize_identifier(source_key)
    return ""


def tailoring_fallback_identifier(value: str) -> str:
    qualified = re.fullmatch(r"\([HPS]\)(\d+)", value.strip(), re.IGNORECASE)
    return qualified.group(1) if qualified else humanize_identifier(value)


def ginger_island_title(entity: NormalizedEntity) -> str:
    source_id = entity.game_id or entity.internal_name or ""
    map_id, _, event_id = source_id.partition(":")
    map_name = {
        "islandhut": "姜岛小屋",
        "islandnorth": "姜岛北部",
        "islandsouth": "姜岛南部",
        "islandwest": "姜岛西部",
    }.get(map_id.casefold(), humanize_identifier(map_id))
    summary = "·".join(part for part in (map_name, ginger_event_name(event_id)) if part)
    return f"姜岛事件：{summary or '未命名（编号未知）'}"


def ginger_event_name(event_id: str) -> str:
    known_events = {
        "addedparrotboy": "鹦鹉男孩加入",
        "islanddepart": "离开姜岛",
        "leomoved": "里奥搬迁",
        "playerkilled": "玩家倒下",
    }
    tokens = [token for token in re.split(r"[/\\\s]+", event_id) if token]
    for token in reversed(tokens):
        marker = token.removeprefix("Hl-").casefold()
        if marker in known_events:
            return known_events[marker]
    friendly = humanize_identifier(tokens[0]) if tokens else ""
    return f"事件/条件：{friendly}" if friendly else "事件/条件：未知"


def fallback_name(primary: object, name: str | None) -> str:
    entity_type = primary.entity_type
    source_id = primary.source_id
    if entity_type in {"npc_schedule", "villager_gift"}:
        return name or "未命名"
    if entity_type in {"ginger_island", "shop", "tailoring_recipe"}:
        label = {
            "ginger_island": "姜岛数据",
            "shop": "商店",
            "tailoring_recipe": "裁缝规则",
        }[entity_type]
        return labelled_identifier(label, source_id)
    if entity_type == "drop":
        item_id = primary.attributes.get("itemId")
        if (
            name
            and name.strip()
            and not technical_name(name)
            and name.strip() != str(item_id or source_id).strip()
        ):
            return name.strip()
        return labelled_identifier("掉落物", item_id or source_id)
    if name and name.strip() and not technical_name(name):
        return name.strip()
    return labelled_identifier(entity_type.replace("_", " "), source_id)


def labelled_identifier(label: str, value: object) -> str:
    identifier = humanize_identifier(str(value).strip()) if value is not None else ""
    return f"{label}（未命名，编号：{identifier or '未知'}）"
