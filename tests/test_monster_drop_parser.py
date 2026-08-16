from __future__ import annotations

from pathlib import Path

from builder.models import DiscoveredJsonFile
from builder.parsers.official import build_monster_drops


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
