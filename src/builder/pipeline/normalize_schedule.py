from __future__ import annotations

import re

from builder.models import NormalizedEntity
from builder.pipeline.normalize_support import (
    humanize_identifier,
)


def resolve_schedule_title(
    entity: NormalizedEntity, villagers: dict[str, NormalizedEntity]
) -> NormalizedEntity:
    schedule_key = entity.game_id.split(":", maxsplit=1)[-1] if entity.game_id else ""
    source_variant = (entity.game_id or "").split(":", maxsplit=1)[0].casefold()
    schedule_title = friendly_schedule_key(schedule_key)
    if schedule_key.casefold() == "template" or source_variant == "template":
        title = f"通用模板·{schedule_title}日程"
    else:
        npc = referenced_villager(entity, villagers)
        npc_name = display_villager_name(npc, entity)
        variant = "大陆版本·" if source_variant == "leomainland" else ""
        title = f"{npc_name}的{variant}{schedule_title}日程"
    return entity.model_copy(update={"name_zh": title, "name_en": None})


def referenced_villager(
    entity: NormalizedEntity, villagers: dict[str, NormalizedEntity]
) -> NormalizedEntity | None:
    candidates = [entity.game_id or "", entity.internal_name or ""]
    if entity.entity_type == "npc_schedule" and entity.game_id:
        candidates.insert(0, entity.game_id.split(":", maxsplit=1)[0])
    for candidate in candidates:
        villager = villagers.get(reference_key(candidate))
        if villager is not None:
            return villager
    return None


def reference_key(value: object) -> str:
    key = str(value or "").strip().casefold()
    return {"leomainland": "leo"}.get(key, key)


def display_villager_name(
    villager: NormalizedEntity | None, source: NormalizedEntity
) -> str:
    if villager is not None:
        candidate = villager.name_zh.strip()
        if candidate and candidate != "???":
            return candidate
        candidate = (villager.name_en or "").strip()
        if candidate and candidate != "???":
            return humanize_identifier(candidate)
    reference = (source.game_id or source.internal_name or "").split(":", maxsplit=1)[0]
    return f"未命名村民（编号：{reference or '未知'}）"


def friendly_schedule_key(value: str) -> str:
    key = value.strip()
    if key.isdigit():
        return f"第{key}天"
    parts = [part for part in re.split(r"[_\-\s]+", key) if part]
    compact_variant = re.fullmatch(
        r"(fall|spring|summer|winter|rain|greenrain)(\d+)", key, re.IGNORECASE
    )
    if compact_variant:
        parts = [compact_variant.group(1), compact_variant.group(2)]
    translated = schedule_tokens()
    if not parts:
        return "条件/变体：未知"
    numeric_indexes = [index for index, part in enumerate(parts) if part.isdigit()]
    if numeric_indexes:
        number_index = numeric_indexes[-1]
        number = parts[number_index]
        if len(parts) == 2 and number_index == 1 and parts[0].casefold() in {
            "fall",
            "spring",
            "summer",
            "winter",
        }:
            return f"{translated[parts[0].casefold()]}第{number}天"
        condition_parts = parts[:number_index]
        if condition_parts:
            condition_text, known = translate_schedule_parts(condition_parts, translated)
            condition = "·".join(condition_text)
            if known:
                return f"{condition}变体{number}"
            return f"条件/变体：{condition}（变体{number}）"
        return f"第{number}天"
    translated_parts, known = translate_schedule_parts(parts, translated)
    condition = "·".join(translated_parts)
    return condition if known else f"条件/变体：{condition}"


def schedule_tokens() -> dict[str, str]:
    return {
        "fall": "秋季",
        "friday": "周五",
        "greenrain": "绿雨天",
        "marriage": "婚后",
        "monday": "周一",
        "rain": "雨天",
        "spring": "春季",
        "summer": "夏季",
        "sunday": "周日",
        "thursday": "周四",
        "tuesday": "周二",
        "wednesday": "周三",
        "winter": "冬季",
        "desertfestival": "沙漠节",
        "community": "社区",
        "center": "中心",
        "replacement": "替代",
        "squid": "鱿鱼",
        "fest": "节",
        "squidfest": "鱿鱼节",
        "job": "工作",
        "marriagejob": "婚后工作",
        "joja": "乔家",
        "mart": "超市",
        "jojamart": "乔家超市",
        "no": "无",
        "bridge": "桥",
        "nobridge": "无桥",
        "communitycenter": "社区中心",
        "default": "默认",
        "normal": "普通",
        "bus": "巴士",
        "trout": "鳟鱼",
        "derby": "大赛",
        "troutderby": "鳟鱼大赛",
        "mon": "周一",
        "tue": "周二",
        "wed": "周三",
        "thu": "周四",
        "fri": "周五",
        "sat": "周六",
        "sun": "周日",
    }


SCHEDULE_PHRASES = {
    ("community", "center"): "社区中心",
    ("squid", "fest"): "鱿鱼节",
    ("marriage", "job"): "婚后工作",
    ("joja", "mart"): "乔家超市",
    ("no", "bridge"): "无桥",
    ("trout", "derby"): "鳟鱼大赛",
}


def translate_schedule_parts(
    parts: list[str], translated: dict[str, str]
) -> tuple[list[str], bool]:
    result: list[str] = []
    known = True
    index = 0
    while index < len(parts):
        pair = tuple(part.casefold() for part in parts[index : index + 2])
        if pair in SCHEDULE_PHRASES:
            result.append(SCHEDULE_PHRASES[pair])
            index += 2
            continue
        part = parts[index]
        value = translated.get(part.casefold())
        if value is None:
            known = False
            value = humanize_identifier(part)
        result.append(value)
        index += 1
    return result, known
