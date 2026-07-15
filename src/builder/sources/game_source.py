from __future__ import annotations

from pathlib import Path

from builder.models import DiscoveredJsonFile, RawEntity
from builder.parsers.crops import parse_crops_file
from builder.parsers.fish import parse_fish_file
from builder.parsers.localization import classify_localized_json
from builder.parsers.objects import parse_objects_file
from builder.parsers.villagers import parse_villagers_file
from builder.utils.json_io import load_json_file


def discover_game_json_files(unpacked_dir: Path) -> list[DiscoveredJsonFile]:
    discovered: list[DiscoveredJsonFile] = []
    for json_file in sorted(unpacked_dir.rglob("*.json")):
        payload = load_json_file(json_file)
        classified = classify_localized_json(json_file, payload)
        if classified is not None:
            discovered.append(classified)
    return discovered


def load_raw_entities_from_unpacked_dir(unpacked_dir: Path) -> list[RawEntity]:
    entities: list[RawEntity] = []
    for discovered in discover_game_json_files(unpacked_dir):
        payload = load_json_file(Path(discovered.path))
        entities.extend(parse_discovered_file(discovered, payload))
    return entities


def parse_discovered_file(discovered: DiscoveredJsonFile, payload: object) -> list[RawEntity]:
    parser_map = {
        "object": parse_objects_file,
        "crop": parse_crops_file,
        "fish": parse_fish_file,
        "villager": parse_villagers_file,
    }
    parser = parser_map[discovered.entity_type]
    return parser(Path(discovered.path), payload, discovered.locale)
