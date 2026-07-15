from __future__ import annotations

from pathlib import Path

from rich.console import Console

from builder.config import ENTITY_TYPE_LABELS
from builder.database.writer import inspect_database

console = Console()


def inspect_command(db_path: str) -> None:
    summary = inspect_database(Path(db_path))
    console.print(f"数据库版本：{summary['schema_version']}")
    console.print(f"语言：{summary['locale']}")
    console.print(f"实体总数：{summary['entities']}")
    console.print(f"物品：{summary['objects']}")
    console.print(f"作物：{summary['crops']}")
    console.print(f"鱼类：{summary['fish']}")
    console.print(f"村民：{summary['villagers']}")
    for entity_type, count in sorted(summary["extra_counts"].items()):
        label = ENTITY_TYPE_LABELS.get(entity_type, entity_type)
        console.print(f"{label}：{count}")
    console.print(f"缺少中文：{summary['missing_translations']}")
    console.print(f"FTS 搜索：{summary['fts']}")
