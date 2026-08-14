from __future__ import annotations

import json
from pathlib import Path

from builder.config import REQUIRED_ENTITY_TYPES
from builder.sources.game_source import load_raw_entities_from_unpacked_dir


def add_required_entity_baseline(unpacked_dir: Path) -> None:
    existing = {entity.entity_type for entity in load_raw_entities_from_unpacked_dir(unpacked_dir)}
    for entity_type in sorted(set(REQUIRED_ENTITY_TYPES) - existing):
        write_entity_fixture(unpacked_dir, entity_type, "en", f"Fixture {entity_type}")
        write_entity_fixture(unpacked_dir, entity_type, "zh-CN", f"测试{entity_type}")


def write_entity_fixture(unpacked_dir: Path, entity_type: str, locale: str, name: str) -> None:
    payload = {
        "entityType": entity_type,
        "locale": locale,
        "entries": [
            {
                "id": f"fixture-{entity_type}",
                "internalName": f"Fixture{entity_type}",
                "name": name,
                "description": f"Fixture {entity_type} description.",
                **fixture_attributes(entity_type),
            }
        ],
    }
    path = unpacked_dir / "Data" / f"fixture-{entity_type}.{locale}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def enrich_fixture_entries(unpacked_dir: Path) -> None:
    """Make the synthetic candidate complete enough to exercise release gates."""
    data_dir = unpacked_dir / "Data"
    for path in data_dir.glob("*.json"):
        if path.name in {"Locations.json", "Shops.json", "Machines.json", "FishPondData.json"}:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
            continue
        entity_type = payload.get("entityType")
        if not isinstance(entity_type, str):
            continue
        for entry in payload["entries"]:
            if not isinstance(entry, dict):
                continue
            entry.update(fixture_attributes(entity_type))
            if entity_type == "crop":
                entry["id"] = "24"
                entry["SeedItemId"] = "24"
                entry["HarvestItemId"] = "24"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    locations = {
        "River": {
            "Fish": [
                {
                    "ItemId": "(O)sturgeon",
                    "FishAreaId": "main",
                    "Season": "Spring",
                    "Chance": 0.5,
                    "MinFishingLevel": 1,
                }
            ]
        }
    }
    (data_dir / "Locations.json").write_text(
        json.dumps(locations, ensure_ascii=False), encoding="utf-8"
    )
    shops = {
        "SeedShop": {
            "Currency": "Money",
            "Items": [{"Id": "parsnip-seeds", "ItemId": "(O)24", "Price": 20}],
        }
    }
    (data_dir / "Shops.json").write_text(
        json.dumps(shops, ensure_ascii=False), encoding="utf-8"
    )


def fixture_attributes(entity_type: str) -> dict[str, object]:
    return {
        "object": {"Price": 35},
        "mineral": {"Price": 35},
        "ring": {"Price": 35},
        "crop": {
            "Seasons": ["Spring"],
            "DaysInPhase": [4],
            "RegrowDays": 2,
            "NeedsWatering": True,
            "SeedItemId": "24",
            "HarvestItemId": "24",
        },
        "fish": {
            "Difficulty": 45,
            "Behavior": "mixed",
            "MinSize": 10,
            "MaxSize": 30,
            "FishingTime": "6:00-19:00",
            "Seasons": ["Spring"],
            "Weather": "any",
            "Price": 75,
        },
        "villager": {
            "HomeRegion": "Town",
            "Gender": "Female",
            "CanBeRomanced": False,
            "BirthSeason": "Spring",
            "BirthDay": 1,
        },
        "big_craftable": {
            "PurchasePrice": 100,
            "CraftingMaterial": "24",
            "CraftingMaterialQuantity": 1,
        },
        "tool": {
            "PurchasePrice": 100,
            "UpgradeMaterial": "24",
            "UpgradeCost": 200,
            "Acquisition": "商店购买",
        },
        "weapon": {
            "Price": 50,
            "PurchasePrice": 100,
            "MinDamage": 10,
            "MaxDamage": 20,
            "Speed": 0,
            "Precision": 0,
            "Defense": 0,
            "Type": 0,
            "CritChance": 0.02,
            "CritMultiplier": 3.0,
            "Acquisition": "商店购买",
        },
        "monster": {
            "Locations": ["Mines"],
            "Drops": [{"itemId": "24", "chance": 0.5}],
        },
    }.get(entity_type, {})
