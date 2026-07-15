from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from builder.commands.package import create_svdata_package, write_manifest
from builder.config import (
    BUILD_DB_FILENAME,
    DEFAULT_FIXTURE_ROOT,
    DEFAULT_LOCALE,
    EXIT_DATABASE,
    EXIT_GAME_DIR,
    REPORTS_DIRNAME,
)
from builder.database.writer import write_database
from builder.pipeline.images import materialize_entity_images
from builder.pipeline.match import match_community_entities
from builder.pipeline.merge import merge_official_and_community
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.reports import summarize_entities, write_build_reports
from builder.pipeline.search_tokens import build_search_documents
from builder.sources.community_source import load_raw_entities_from_community_dir
from builder.sources.game_source import load_raw_entities_from_unpacked_dir
from builder.sources.override_source import load_aliases, load_categories, load_match_overrides
from builder.utils.hashing import sha256_paths
from builder.utils.paths import (
    ensure_community_data_directory,
    ensure_directory,
    ensure_game_directory,
    ensure_json_output,
)
from builder.utils.time import current_utc_iso

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
    entities = materialize_entity_images(
        entities,
        asset_root=unpacked_dir,
        output_dir=output_dir,
    )
    search_documents = build_search_documents(entities)
    summary = summarize_entities(entities)

    try:
        write_database(db_path, entities, search_documents, locale=DEFAULT_LOCALE, summary=summary)
    except Exception as exc:  # pragma: no cover - Typer exit path
        raise typer.Exit(code=EXIT_DATABASE) from exc

    console.print(f"已生成数据库：{db_path}")


def build_command(
    game_dir: str,
    community_data: str,
    output: str,
    unpacked_dir: str | None,
) -> None:
    try:
        resolved_game_dir = ensure_game_directory(Path(game_dir))
        resolved_community_dir = ensure_community_data_directory(Path(community_data))
    except FileNotFoundError as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_GAME_DIR) from exc

    resolved_unpacked_dir = (
        Path(unpacked_dir)
        if unpacked_dir
        else resolved_game_dir / "Content (unpacked)"
    )
    try:
        ensure_json_output(resolved_unpacked_dir)
    except FileNotFoundError as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_GAME_DIR) from exc

    output_dir = ensure_directory(Path(output))
    db_path = output_dir / BUILD_DB_FILENAME
    reports_dir = output_dir / REPORTS_DIRNAME
    generated_at = current_utc_iso()

    aliases = load_aliases(Path("data/aliases.zh-CN.json"))
    categories = load_categories(Path("data/categories.zh-CN.json"))
    overrides = load_match_overrides(Path("data/overrides.zh-CN.json"))
    source_hash = sha256_paths(
        [
            *sorted(resolved_unpacked_dir.rglob("*.json")),
            *sorted(resolved_community_dir.rglob("*.json")),
            Path("data/aliases.zh-CN.json"),
            Path("data/categories.zh-CN.json"),
            Path("data/overrides.zh-CN.json"),
        ]
    )

    official_raw = load_raw_entities_from_unpacked_dir(resolved_unpacked_dir)
    official_entities = normalize_entities(official_raw, aliases=aliases, categories=categories)
    community_raw = load_raw_entities_from_community_dir(resolved_community_dir)
    community_entities = normalize_entities(community_raw, aliases={}, categories={})
    matches, unmatched = match_community_entities(official_entities, community_entities, overrides)
    merged_entities = merge_official_and_community(official_entities, community_entities, matches)
    merged_entities = materialize_entity_images(
        merged_entities,
        asset_root=resolved_unpacked_dir,
        output_dir=output_dir,
    )
    search_documents = build_search_documents(merged_entities)
    summary = summarize_entities(merged_entities)
    summary.unmatched = len(unmatched)
    missing_translations = [
        entity for entity in merged_entities if entity.translation_status == "missing"
    ]

    try:
        write_database(
            db_path,
            merged_entities,
            search_documents,
            locale=DEFAULT_LOCALE,
            summary=summary,
            generated_at=generated_at,
            source_hash=source_hash,
        )
        write_build_reports(
            reports_dir=reports_dir,
            summary=summary,
            unmatched=unmatched,
            missing_translations=missing_translations,
            errors=[],
        )
        manifest_path = write_manifest(
            output_dir=output_dir,
            locale=DEFAULT_LOCALE,
            generated_at=generated_at,
            db_path=db_path,
            summary=summary,
        )
        package_path = create_svdata_package(
            output_dir=output_dir,
            locale=DEFAULT_LOCALE,
            generated_at=generated_at,
            db_path=db_path,
            manifest_path=manifest_path,
            reports_dir=reports_dir,
        )
    except Exception as exc:  # pragma: no cover
        raise typer.Exit(code=EXIT_DATABASE) from exc

    console.print(f"已完成构建：{db_path}")
    console.print(f"已生成数据包：{package_path}")
