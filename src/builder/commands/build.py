from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from builder.config import BUILD_DB_FILENAME, DEFAULT_FIXTURE_ROOT, DEFAULT_LOCALE, EXIT_DATABASE
from builder.database.writer import write_database
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.reports import summarize_entities
from builder.pipeline.search_tokens import build_search_documents
from builder.sources.game_source import load_raw_entities_from_unpacked_dir
from builder.sources.override_source import load_aliases, load_categories
from builder.utils.paths import ensure_directory

console = Console()


def build_fixture_command(output: str) -> None:
    fixture_root = DEFAULT_FIXTURE_ROOT
    unpacked_dir = fixture_root / "Content (unpacked)"
    output_dir = ensure_directory(Path(output))
    db_path = output_dir / BUILD_DB_FILENAME

    raw_entities = load_raw_entities_from_unpacked_dir(unpacked_dir)
    aliases = load_aliases(Path("data/aliases.zh-CN.json"))
    categories = load_categories(Path("data/categories.zh-CN.json"))
    entities = normalize_entities(raw_entities, aliases=aliases, categories=categories)
    search_documents = build_search_documents(entities)
    summary = summarize_entities(entities)

    try:
        write_database(db_path, entities, search_documents, locale=DEFAULT_LOCALE, summary=summary)
    except Exception as exc:  # pragma: no cover - Typer exit path
        raise typer.Exit(code=EXIT_DATABASE) from exc

    console.print(f"已生成数据库：{db_path}")
