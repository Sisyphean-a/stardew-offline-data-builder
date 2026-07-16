from __future__ import annotations

import re
from typing import Any

QUALIFIED_ITEM_ID = re.compile(r"^\(([A-Z]+)\)(.+)$")
OBJECT_ENTITY_TYPES = ("object", "mineral", "ring", "fish")


def entity_ids_for_item(value: object) -> tuple[str, ...]:
    item_id = text(value)
    if not item_id:
        return ()
    if item_id.startswith("FLAVORED_ITEM "):
        parts = item_id.split(maxsplit=2)
        return entity_ids_for_item(parts[1]) if len(parts) > 1 else ()
    match = QUALIFIED_ITEM_ID.match(item_id)
    if match is None:
        return tuple(f"{entity_type}:{item_id}" for entity_type in OBJECT_ENTITY_TYPES)
    prefix, source_id = match.groups()
    mapping = {
        "B": ("footwear",),
        "BC": ("big_craftable",),
        "F": ("furniture",),
        "O": OBJECT_ENTITY_TYPES,
        "T": ("tool",),
        "TR": ("trinket",),
        "W": ("weapon",),
    }
    return tuple(f"{entity_type}:{source_id}" for entity_type in mapping.get(prefix, ()))


def item_category(value: object) -> int | None:
    item_id = text(value)
    if not item_id or QUALIFIED_ITEM_ID.match(item_id):
        return None
    parsed = parse_int(item_id)
    return parsed if parsed is not None and parsed < 0 else None


def unqualified_item_id(value: object) -> str | None:
    item_id = text(value)
    if not item_id:
        return None
    match = QUALIFIED_ITEM_ID.match(item_id)
    return match.group(2) if match else item_id


def parse_ingredients(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, str):
        return None
    parts = value.split()
    ingredients = []
    for index in range(0, len(parts) - 1, 2):
        quantity = parse_int(parts[index + 1])
        if quantity is not None:
            ingredients.append({"itemId": parts[index], "quantity": quantity})
    return ingredients or None


def parse_bundle_ingredients(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, str):
        return None
    parts = value.split()
    ingredients = []
    for index in range(0, len(parts) - 2, 3):
        quantity = parse_int(parts[index + 1])
        quality = parse_int(parts[index + 2])
        if quantity is not None:
            ingredients.append(
                {
                    "itemId": parts[index],
                    "quantity": quantity,
                    "quality": quality,
                }
            )
    return ingredients or None


def simplify_outputs(value: object) -> list[dict[str, object]] | None:
    outputs = [
        compact(
            {
                "itemId": item.get("ItemId"),
                "randomItemIds": item.get("RandomItemId"),
                "outputMethod": item.get("OutputMethod"),
                "minStack": item.get("MinStack"),
                "maxStack": item.get("MaxStack"),
                "quality": item.get("Quality"),
                "condition": item.get("Condition"),
            }
        )
        for item in dictionary_list(value)
    ]
    return outputs or None


def simplify_produced_items(value: object) -> list[dict[str, object]] | None:
    items = [
        compact(
            {
                "itemId": item.get("ItemId"),
                "requiredPopulation": item.get("RequiredPopulation"),
                "chance": item.get("Chance"),
                "minStack": item.get("MinStack"),
                "maxStack": item.get("MaxStack"),
                "condition": item.get("Condition"),
            }
        )
        for item in dictionary_list(value)
    ]
    return items or None


def compact(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != [] and item != {}
    }


def dictionary_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def integer_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int)]


def integer_list_at(values: list[object], index: int) -> list[int] | None:
    value = text_at(values, index)
    if value is None:
        return None
    parsed = [
        number
        for item in value.split()
        if (number := parse_int(item)) is not None
    ]
    return parsed or None


def integer_at(values: list[object], index: int) -> int | None:
    return parse_int(text_at(values, index))


def lower_text(value: object) -> str | None:
    resolved = text(value)
    return resolved.lower() if resolved else None


def lower_text_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    resolved = [str(item).lower() for item in value if str(item)]
    return resolved or None


def split_words_at(values: list[object], index: int) -> list[str] | None:
    value = text_at(values, index)
    return value.lower().split() if value else None


def string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item)}


def text_at(values: list[object], index: int) -> str | None:
    return text(values[index]) if len(values) > index else None


def text(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None


def parse_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
