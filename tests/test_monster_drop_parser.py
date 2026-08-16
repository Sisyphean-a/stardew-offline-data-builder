from __future__ import annotations

from pathlib import Path

from builder.models import DiscoveredJsonFile
from builder.parsers.official import build_legacy_entity, build_monster_drops
from builder.pipeline.normalize_support import percent_label


def discovered(locale: str | None = "en") -> DiscoveredJsonFile:
    return DiscoveredJsonFile(path="Data/Monsters.json", entity_type="monster", locale=locale)


def test_build_monster_drops_deduplicates_identical_records() -> None:
    drops = list(
        build_monster_drops(
            Path("Data/Monsters.json"),
            "Big Slime",
            "1/1/1/1/false/1000/766 .5 766 .5 766 .5 157 .1 157 .1/1/.01/4/2/.00/true/3/Big Slime",
            discovered(),
        )
    )

    assert len(drops) == 2
    assert [drop.source_id for drop in drops] == ["Big Slime:0", "Big Slime:1"]
    assert [drop.attributes["itemId"] for drop in drops] == ["766", "157"]
    assert [drop.attributes["chance"] for drop in drops] == [".5", ".1"]


def test_build_monster_drops_keeps_distinct_chances() -> None:
    drops = list(
        build_monster_drops(
            Path("Data/Monsters.json"),
            "Ghost",
            "1/1/1/1/false/1000/768 .95 768 .1/1/.01/4/2/.00/true/3/Ghost",
            discovered(),
        )
    )

    assert len(drops) == 2
    assert [drop.attributes["chance"] for drop in drops] == [".95", ".1"]


def test_universal_gift_row_parses_single_preference_list() -> None:
    entity = build_legacy_entity(
        Path("Data/NPCGiftTastes.json"),
        "Universal_Love",
        "74 446 797 373 279",
        DiscoveredJsonFile(
            path="Data/NPCGiftTastes.json", entity_type="villager_gift", locale="en"
        ),
    )

    assert entity.attributes["GiftTastes"] == [
        {"preference": "loved", "items": ["74", "446", "797", "373", "279"]}
    ]


def test_percent_label_avoids_scientific_notation_for_tiny_chances() -> None:
    assert percent_label(75) == "75%"
    assert percent_label(0.1) == "0.1%"
    assert percent_label(1.5) == "1.5%"
    assert percent_label(0.00001) == "0.00001%"
    assert percent_label(0.001) == "0.001%"
