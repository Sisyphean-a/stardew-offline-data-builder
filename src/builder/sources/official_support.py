from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from builder.utils.json_io import load_json_file

SUPPORT_FILES = {
    "fish_ponds": ("FishPondData.json", list),
    "locations": ("Locations.json", dict),
    "machines": ("Machines.json", dict),
    "shops": ("Shops.json", dict),
}


@dataclass(frozen=True)
class OfficialSupportData:
    fish_ponds: list[dict[str, Any]] = field(default_factory=list)
    locations: dict[str, dict[str, Any]] = field(default_factory=dict)
    machines: dict[str, dict[str, Any]] = field(default_factory=dict)
    shops: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_official_support_data(unpacked_dir: Path) -> OfficialSupportData:
    data_dir = unpacked_dir / "Data"
    loaded: dict[str, object] = {}
    for field_name, (filename, expected_type) in SUPPORT_FILES.items():
        loaded[field_name] = load_support_file(data_dir / filename, expected_type)
    return OfficialSupportData(
        fish_ponds=loaded["fish_ponds"],
        locations=loaded["locations"],
        machines=loaded["machines"],
        shops=loaded["shops"],
    )


def load_support_file(path: Path, expected_type: type) -> object:
    if not path.exists():
        raise FileNotFoundError(f"缺少官方支持数据：{path}")
    payload = load_json_file(path)
    if not isinstance(payload, expected_type):
        raise ValueError(f"官方支持数据结构无效：{path}")
    if expected_type is list:
        if not all(isinstance(item, dict) for item in payload):
            raise ValueError(f"官方支持数据包含非对象记录：{path}")
        return [dict(item) for item in payload]
    if not all(isinstance(value, dict) for value in payload.values()):
        raise ValueError(f"官方支持数据包含非对象记录：{path}")
    return {str(key): dict(value) for key, value in payload.items()}
