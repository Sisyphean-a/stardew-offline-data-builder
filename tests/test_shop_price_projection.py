from __future__ import annotations

from pathlib import Path

from builder.models import NormalizedEntity
from builder.pipeline.official_shop_references import shop_offer
from builder.pipeline.schema5_projection import build_schema5_staging_package
from builder.sources.official_support import OfficialSupportData


def entity(
    entity_id: str,
    entity_type: str,
    attributes: dict[str, object] | None = None,
) -> NormalizedEntity:
    return NormalizedEntity(
        id=entity_id,
        entity_type=entity_type,
        game_id=entity_id.partition(":")[2],
        internal_name=None,
        name_zh=entity_id,
        name_en=None,
        description_zh=None,
        description_en=None,
        category=None,
        source_file="Data/Objects.json",
        extra_json=attributes or {},
    )


def price_items(package: object, slot_id: str) -> list[object]:
    return [item for item in package.fact_items if item.slot_id == slot_id]


def test_shop_offer_retains_runtime_price_controls() -> None:
    offer = shop_offer(
        "Shop",
        {"PriceModifiers": [], "PriceModifierMode": "Maximum", "ApplyProfitMargins": False},
        {
            "ItemId": "(O)1",
            "Price": -1,
            "UseObjectDataPrice": True,
            "IgnoreShopPriceModifiers": True,
            "ApplyProfitMargins": False,
            "PriceModifiers": [],
            "PriceModifierMode": "Minimum",
        },
    )

    assert offer["useObjectDataPrice"] is True
    assert offer["ignoreShopPriceModifiers"] is True
    assert offer["shopPriceModifierMode"] == "Maximum"
    assert offer["priceModifierMode"] == "Minimum"


def test_static_shop_and_item_modifiers_follow_runtime_order_and_ignore_flag(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("object:1", "object")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "Modified": {
                    "Currency": "Money",
                    "PriceModifiers": [
                        {"Modification": "Multiply", "Amount": 1.5},
                        {"Modification": "Add", "Amount": 10},
                    ],
                    "Items": [
                        {
                            "Id": "normal",
                            "ItemId": "(O)1",
                            "Price": 100,
                            "PriceModifiers": [{"Modification": "Add", "Amount": 5}],
                        },
                        {
                            "Id": "ignore-shop",
                            "ItemId": "(O)1",
                            "Price": 100,
                            "IgnoreShopPriceModifiers": True,
                            "PriceModifiers": [{"Modification": "Add", "Amount": 5}],
                        },
                    ],
                }
            }
        ),
    )

    prices = {
        item.scope_id: item.integer_value
        for item in price_items(package, "fact:object:1:purchase_price")
    }
    assert prices == {
        "offer:shop:Modified:offer:normal": 165,
        "offer:shop:Modified:offer:ignore-shop": 105,
    }
    diagnostics = {row["offerKey"]: row for row in package.shop_price_diagnostics}
    assert diagnostics["shop:Modified:offer:normal"]["appliedShopModifiers"] == 2
    assert diagnostics["shop:Modified:offer:normal"]["appliedItemModifiers"] == 1
    assert diagnostics["shop:Modified:offer:ignore-shop"]["appliedShopModifiers"] == 0


def test_price_minus_one_uses_object_data_only_when_requested_and_crop_uses_seed_object(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [
            entity("object:472", "object", {"Price": 20}),
            # A crop with the same key must not be selected as the pricing source.
            entity("crop:472", "crop", {"SeedItemId": "472"}),
        ],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "SeedShop": {
                    "Items": [
                        {
                            "Id": "object-price",
                            "ItemId": "(O)472",
                            "Price": -1,
                            "UseObjectDataPrice": True,
                        }
                    ]
                }
            }
        ),
    )

    object_purchase_prices = price_items(package, "fact:object:472:purchase_price")
    seed_purchase_prices = price_items(package, "fact:crop:472:seed_purchase_price")
    assert [item.integer_value for item in object_purchase_prices] == [20]
    assert [item.integer_value for item in seed_purchase_prices] == [20]
    evidence_id = (
        "evidence:fact-item:fact-item:object:472:purchase_price:"
        "offer:shop:SeedShop:offer:object-price"
    )
    evidence = next(evidence for evidence in package.evidence if evidence.id == evidence_id)
    assert evidence.input_claim_id == "object:472"


def test_price_minus_one_without_object_data_flag_uses_runtime_sale_rule_not_object_price(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("object:1", "object", {"Price": 20})],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={"Shop": {"Items": [{"ItemId": "(O)1", "Price": -1}]}}
        ),
    )

    purchase_prices = price_items(package, "fact:object:1:purchase_price")
    assert [item.integer_value for item in purchase_prices] == [40]
    assert package.shop_price_diagnostics[0]["inputClaimId"] == "object:1"


def test_seedshop_out_of_season_multiplier_is_retained_as_a_dynamic_rule(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("object:2", "object"), entity("crop:2", "crop", {"SeedItemId": "2"})],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "SeedShop": {
                    "Items": [
                        {
                            "ItemId": "(O)2",
                            "Price": 50,
                            "Condition": "SEASON spring",
                        }
                    ]
                }
            }
        ),
    )

    price = price_items(package, "fact:crop:2:seed_purchase_price")[0]
    rule = price_items(package, "fact:crop:2:seed_purchase_price_rule")[0]
    assert price.integer_value == 50
    assert rule.text_value == "out-of-season-price-rule"
    assert next(row for row in package.shop_price_diagnostics if row["entityId"] == "crop:2")[
        "dynamicRule"
    ] == "out-of-season-price-rule"


def test_negative_trade_price_can_have_a_separate_modifier_coin_component(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("object:1", "object"), entity("object:2", "object")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "Mixed": {
                    "Items": [
                        {
                            "ItemId": "(O)1",
                            "Price": -1,
                            "TradeItemId": "(O)2",
                            "TradeItemAmount": 3,
                            "PriceModifiers": [{"Modification": "Add", "Amount": 5}],
                        }
                    ]
                }
            }
        ),
    )

    prices = price_items(package, "fact:object:1:purchase_price")
    assert [item.integer_value for item in prices] == [5]
    assert price_items(package, "fact:object:1:purchase_exchange_amount")[0].integer_value == 3


def test_negative_trade_price_with_dynamic_modifier_is_a_dynamic_rule(
    tmp_path: Path,
) -> None:
    package = build_schema5_staging_package(
        [entity("object:1", "object"), entity("object:2", "object")],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "Mixed": {
                    "Items": [
                        {
                            "ItemId": "(O)1",
                            "Price": -1,
                            "TradeItemId": "(O)2",
                            "TradeItemAmount": 3,
                            "IgnoreShopPriceModifiers": True,
                            "PriceModifiers": [
                                {
                                    "Modification": "Add",
                                    "Amount": 5,
                                    "Condition": "SEASON spring",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
    )

    assert not price_items(package, "fact:object:1:purchase_price")
    rule = price_items(package, "fact:object:1:purchase_price_rule")[0]
    assert rule.text_value == "conditional-or-random-price-modifier"
    diagnostic = package.shop_price_diagnostics[0]
    assert diagnostic["kind"] == "dynamic"
    assert diagnostic["reason"] == "conditional-or-random-price-modifier"


def test_exchange_and_dynamic_prices_never_become_coin_purchase_prices(tmp_path: Path) -> None:
    package = build_schema5_staging_package(
        [
            entity("object:1", "object"),
            entity("object:2", "object"),
            entity("crop:2", "crop", {"SeedItemId": "2"}),
        ],
        tmp_path,
        game_version="1.6.15",
        support=OfficialSupportData(
            shops={
                "Exchange": {
                    "Items": [
                        {
                            "Id": "barter",
                            "ItemId": "(O)1",
                            "Price": -1,
                            "TradeItemId": "(O)2",
                            "TradeItemAmount": 3,
                        },
                        {
                            "Id": "conditional-seed-price",
                            "ItemId": "(O)2",
                            "Price": 50,
                            "PriceModifiers": [
                                {
                                    "Modification": "Multiply",
                                    "Amount": 0.5,
                                    "Condition": "SEASON spring",
                                }
                            ],
                        },
                    ]
                }
            }
        ),
    )

    assert not price_items(package, "fact:object:1:purchase_price")
    exchange_item = price_items(package, "fact:object:1:purchase_exchange_item_id")[0]
    exchange_amount = price_items(package, "fact:object:1:purchase_exchange_amount")[0]
    assert exchange_item.text_value == "object:2"
    assert exchange_amount.integer_value == 3
    assert not price_items(package, "fact:crop:2:seed_purchase_price")
    rule = price_items(package, "fact:crop:2:seed_purchase_price_rule")[0]
    assert rule.text_value == "conditional-or-random-price-modifier"
    rule_slot = next(slot for slot in package.fact_slots if slot.id == rule.slot_id)
    assert rule_slot.status == "dynamic_rule"
    assert any(
        row["reason"] == "conditional-or-random-price-modifier"
        and row["entityId"] == "crop:2"
        for row in package.shop_price_diagnostics
    )
