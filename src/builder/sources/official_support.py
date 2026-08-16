from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from builder.parsers.localization import load_localization_tables
from builder.utils.json_io import load_json_file

SUPPORT_FILES = {
    "fish_ponds": ("FishPondData.json", list),
    "locations": ("Locations.json", dict),
    "machines": ("Machines.json", dict),
    "shops": ("Shops.json", dict),
}
OPTIONAL_SUPPORT_FILES = {
    "monster_slayer_quests": ("MonsterSlayerQuests.json", dict),
}

LOCALIZED_TEXT = re.compile(r"^\[LocalizedText\s+([^:]+):([^\]]+)\]$")


@dataclass(frozen=True)
class OfficialSupportData:
    fish_ponds: list[dict[str, Any]] = field(default_factory=list)
    locations: dict[str, dict[str, Any]] = field(default_factory=dict)
    machines: dict[str, dict[str, Any]] = field(default_factory=dict)
    shops: dict[str, dict[str, Any]] = field(default_factory=dict)
    monster_slayer_quests: dict[str, dict[str, Any]] = field(default_factory=dict)
    hats_zh: dict[str, str] = field(default_factory=dict)
    shirts_zh: dict[str, str] = field(default_factory=dict)
    pants_zh: dict[str, str] = field(default_factory=dict)

    def hat_name_zh(self, hat_id: str) -> str | None:
        """官方 hats.zh-CN.json 旧格式：名称/描述/…/中文名（最后一个字段）。"""
        value = self.hats_zh.get(hat_id)
        if not isinstance(value, str):
            return None
        fields = value.split("/")
        return fields[-1].strip() or None


def load_official_support_data(unpacked_dir: Path) -> OfficialSupportData:
    data_dir = unpacked_dir / "Data"
    loaded: dict[str, object] = {}
    for field_name, (filename, expected_type) in SUPPORT_FILES.items():
        loaded[field_name] = load_support_file(data_dir / filename, expected_type)
    for field_name, (filename, expected_type) in OPTIONAL_SUPPORT_FILES.items():
        path = data_dir / filename
        loaded[field_name] = (
            load_support_file(path, expected_type) if path.exists() else {}
        )
    hats_path = data_dir / "hats.zh-CN.json"
    hats_zh = load_string_dict(hats_path) if hats_path.exists() else {}
    tables = load_localization_tables(unpacked_dir)
    return OfficialSupportData(
        fish_ponds=loaded["fish_ponds"],
        locations=loaded["locations"],
        machines=loaded["machines"],
        shops=loaded["shops"],
        monster_slayer_quests=loaded["monster_slayer_quests"],
        hats_zh=hats_zh,
        shirts_zh=clothing_names_zh(data_dir / "Shirts.json", "strings/shirts", tables),
        pants_zh=clothing_names_zh(data_dir / "Pants.json", "strings/pants", tables),
    )


def clothing_names_zh(
    path: Path,
    asset_key: str,
    tables: dict[str, dict[str, dict[str, str]]],
) -> dict[str, str]:
    """Shirts/Pants.json → 中文显示名（通过 Strings/Shirts、Strings/Pants 表解析）。"""
    if not path.exists():
        return {}
    payload = load_json_file(path)
    if not isinstance(payload, dict):
        return {}
    zh_table = tables.get("zh-CN", {}).get(asset_key, {})
    result: dict[str, str] = {}
    for raw_id, value in payload.items():
        if not isinstance(value, dict):
            continue
        display_name = value.get("DisplayName")
        if not isinstance(display_name, str):
            continue
        match = LOCALIZED_TEXT.match(display_name)
        if match is None:
            continue
        name = zh_table.get(match.group(2))
        if name:
            result[str(raw_id)] = name
    return result


def load_string_dict(path: Path) -> dict[str, str]:
    payload = load_json_file(path)
    if not isinstance(payload, dict) or not all(
        isinstance(value, str) for value in payload.values()
    ):
        raise ValueError(f"官方字符串字典数据结构无效：{path}")
    return {str(key): str(value) for key, value in payload.items()}


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
