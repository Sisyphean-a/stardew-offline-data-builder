from __future__ import annotations

from typing import Any

from builder.pipeline.official_item_index import ItemReferenceResolver
from builder.pipeline.official_values import compact, dictionary_list


def build_shop_index(
    index: dict[str, list[dict[str, object]]],
    shops: dict[str, dict[str, Any]],
    resolver: ItemReferenceResolver,
) -> None:
    for shop_id, shop in shops.items():
        for item in dictionary_list(shop.get("Items")):
            offer = shop_offer(shop_id, shop, item)
            entity_ids: set[str] = set()
            for item_id in shop_item_ids(item):
                entity_ids.update(resolver.resolve(item_id))
            for entity_id in sorted(entity_ids):
                index[entity_id].append(offer)


def shop_item_ids(item: dict[str, Any]) -> list[object]:
    item_ids: list[object] = []
    if item.get("ItemId") is not None:
        item_ids.append(item["ItemId"])
    random_ids = item.get("RandomItemId")
    if isinstance(random_ids, list):
        item_ids.extend(random_ids)
    elif random_ids is not None:
        item_ids.append(random_ids)
    return item_ids


def shop_offer(
    shop_id: str,
    shop: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, object]:
    return compact(
        {
            "_source": "Data/Shops.json",
            "shopId": shop_id,
            "offerId": item.get("Id"),
            "currency": shop.get("Currency"),
            "shopPriceModifiers": shop.get("PriceModifiers"),
            "itemId": item.get("ItemId"),
            "randomItemIds": item.get("RandomItemId"),
            "price": item.get("Price"),
            "priceModifiers": item.get("PriceModifiers"),
            "tradeItemId": item.get("TradeItemId"),
            "tradeItemAmount": item.get("TradeItemAmount"),
            "availableStock": item.get("AvailableStock"),
            "availableStockLimit": item.get("AvailableStockLimit"),
            "availableStockModifiers": item.get("AvailableStockModifiers"),
            "availableStockModifierMode": item.get("AvailableStockModifierMode"),
            "maxItems": item.get("MaxItems"),
            "minStack": item.get("MinStack"),
            "maxStack": item.get("MaxStack"),
            "quality": item.get("Quality"),
            "condition": item.get("Condition"),
            "perItemCondition": item.get("PerItemCondition"),
            "avoidRepeat": item.get("AvoidRepeat"),
            "isRecipe": item.get("IsRecipe"),
        }
    )
