from __future__ import annotations

import re

from builder.models import NormalizedEntity


def humanize_identifier(value: str) -> str:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    spaced = re.sub(r"[_\-]+", " ", spaced)
    return " ".join(spaced.split())


def technical_name(value: str) -> bool:
    stripped = value.strip()
    return not stripped or stripped.startswith("[LocalizedText ") or "/" in stripped


def labelled_identifier(label: str, value: object) -> str:
    identifier = humanize_identifier(str(value).strip()) if value is not None else ""
    return f"{label}（未命名，编号：{identifier or '未知'}）"


def entity_type_label(entity_type: str) -> str:
    return humanize_identifier(entity_type.replace("_", " ")) or "实体"


def reference_key(value: object) -> str:
    key = str(value or "").strip().casefold()
    return {"leomainland": "leo"}.get(key, key)


def villager_key(entity: NormalizedEntity) -> str:
    return reference_key(entity.game_id or entity.internal_name)


def item_key(entity: NormalizedEntity) -> str:
    return item_key_value(entity.game_id)


def item_key_value(value: object) -> str:
    reference = str(value or "").strip()
    for prefix in ("(O)", "(BC)", "(B)", "(H)", "(F)", "(T)", "(W)", "(S)", "(P)"):
        if reference.casefold().startswith(prefix.casefold()):
            reference = reference[len(prefix) :]
            break
    return reference.casefold()


def displayable_entity_name(
    entity: NormalizedEntity | None, identifier: object, label: str
) -> str:
    if entity is not None:
        for candidate in (entity.name_zh, entity.name_en):
            if candidate and candidate.strip() and not technical_name(candidate):
                return candidate.strip()
    value = humanize_identifier(str(identifier or "").strip())
    return value or f"{label}（未知）"


def drop_record_id(entity: NormalizedEntity) -> str:
    source_id = (entity.game_id or entity.id).rsplit(":", maxsplit=1)[-1]
    return humanize_identifier(source_id) or "未知"


def percent_label(percent: float) -> str:
    """百分比文案：整数值不带小数（75 → 75%），极小值避免科学计数法。"""
    if abs(percent - round(percent)) < 1e-9:
        return f"{round(percent)}%"
    text = f"{percent:.10f}".rstrip("0").rstrip(".")
    return f"{text}%"


def drop_chance(entity: NormalizedEntity) -> str | None:
    """掉落概率的百分比文案（0.05 → 5%）。"""
    value = entity.extra_json.get("chance")
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return percent_label(value * 100)
