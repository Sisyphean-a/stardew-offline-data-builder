from __future__ import annotations

from pathlib import Path

APP_NAME = "stardew-offline-data-builder"
DEFAULT_LOCALE = "zh-CN"
SCHEMA_VERSION = 4
DEFAULT_FIXTURE_ROOT = Path("tests/fixtures/game-data")
BUILD_DB_FILENAME = "stardew.db"
TEMP_DB_SUFFIX = ".tmp"
MANIFEST_FILENAME = "manifest.json"
REPORTS_DIRNAME = "reports"
PACKAGE_BASENAME = "stardew-{locale}.svdata"
PRIMARY_ENTITY_TYPES = ("object", "crop", "fish", "villager")
FIXTURE_REQUIRED_ENTITY_TYPES = (
    *PRIMARY_ENTITY_TYPES,
    "achievement",
    "big_craftable",
    "furniture",
    "footwear",
)
ENTITY_TYPE_LABELS = {
    "object": "物品",
    "crop": "作物",
    "fish": "鱼类",
    "villager": "村民",
    "monster": "怪物",
    "weapon": "武器",
    "achievement": "成就",
    "big_craftable": "大型可制作物",
    "ring": "戒指",
    "mineral": "矿物",
    "furniture": "家具",
    "footwear": "鞋类",
    "drop": "掉落",
    "bundle": "收集包",
    "quest": "任务",
    "shop": "商店",
    "special_order": "特殊订单",
    "ginger_island": "姜岛数据",
    "npc_schedule": "NPC日程",
    "villager_gift": "村民礼物",
    "cooking_recipe": "料理",
    "crafting_recipe": "制作配方",
    "tailoring_recipe": "裁缝规则",
    "tool": "工具",
    "trinket": "饰品",
}
REQUIRED_ENTITY_TYPES = tuple(ENTITY_TYPE_LABELS)

EXIT_OK = 0
EXIT_UNKNOWN = 1
EXIT_CONFIG = 2
EXIT_GAME_DIR = 3
EXIT_UNPACK_TOOL = 4
EXIT_SOURCE_DATA = 5
EXIT_DATABASE = 6
EXIT_PACKAGE = 7
EXIT_QUALITY = 8
