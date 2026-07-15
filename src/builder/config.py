from __future__ import annotations

from pathlib import Path

APP_NAME = "stardew-offline-data-builder"
DEFAULT_LOCALE = "zh-CN"
SCHEMA_VERSION = 1
DEFAULT_FIXTURE_ROOT = Path("tests/fixtures/game-data")
DEFAULT_COMMUNITY_DATA = Path("tests/fixtures/community-data")
BUILD_DB_FILENAME = "stardew.db"
TEMP_DB_SUFFIX = ".tmp"

EXIT_OK = 0
EXIT_UNKNOWN = 1
EXIT_CONFIG = 2
EXIT_GAME_DIR = 3
EXIT_UNPACK_TOOL = 4
EXIT_SOURCE_DATA = 5
EXIT_DATABASE = 6
EXIT_PACKAGE = 7
