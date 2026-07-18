from __future__ import annotations

from collections import Counter
from pathlib import Path

import typer
from rich.console import Console

from builder.commands.build_output import write_build_output
from builder.commands.package import quarantine_existing_package
from builder.commands.unpack import unpack_game_directory
from builder.config import (
    BUILD_DB_FILENAME,
    DEFAULT_FIXTURE_ROOT,
    DEFAULT_LOCALE,
    EXIT_GAME_DIR,
    EXIT_QUALITY,
    EXIT_SOURCE_DATA,
    FIXTURE_REQUIRED_ENTITY_TYPES,
    REQUIRED_ENTITY_TYPES,
)
from builder.database.writer import write_database
from builder.pipeline.artifact_metadata import build_artifact_metadata
from builder.pipeline.images import materialize_entity_images_with_report
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.official_enrichment import enrich_official_entities
from builder.pipeline.overrides import apply_entity_overrides
from builder.pipeline.quality import quality_errors, quality_status
from builder.pipeline.release_state import block_fixture_release, block_release
from builder.pipeline.reports import summarize_entities
from builder.pipeline.search_tokens import build_search_documents
from builder.sources.game_source import GameSourceLoad, load_game_data_from_unpacked_dir
from builder.sources.override_source import (
    load_aliases,
    load_categories,
    load_entity_overrides,
)
from builder.sources.steam_discovery import resolve_game_directory
from builder.utils.hashing import sha256_paths
from builder.utils.paths import ensure_directory, ensure_json_output
from builder.utils.time import current_utc_iso
from builder.utils.versions import game_version

console = Console()
ALIASES_PATH = Path("data/aliases.zh-CN.json")
CATEGORIES_PATH = Path("data/categories.zh-CN.json")
OVERRIDES_PATH = Path("data/overrides.zh-CN.json")
CONFIG_PATHS = (ALIASES_PATH, CATEGORIES_PATH, OVERRIDES_PATH)


def build_fixture_command(output: str) -> None:
    output_dir = Path(output)
    try:
        unpacked_dir = DEFAULT_FIXTURE_ROOT / "Content (unpacked)"
        output_dir = ensure_directory(output_dir)
        quarantine_fixture_package(output_dir)
        official = load_game_data_from_unpacked_dir(unpacked_dir)
        assert_required_official_entities(official, FIXTURE_REQUIRED_ENTITY_TYPES)
        entities = normalize_entities(
            official.entities,
            aliases=load_aliases(ALIASES_PATH),
            categories=load_categories(CATEGORIES_PATH),
        )
        entities = enrich_official_entities(entities, official.support)
        images = materialize_entity_images_with_report(entities, unpacked_dir, output_dir)
        errors = [*official.errors, *images.errors, *quality_errors(images.entities)]
        summary = summarize_entities(images.entities, data_errors=len(errors))
        generated_at = current_utc_iso()
        artifact_metadata = build_artifact_metadata(
            summary,
            DEFAULT_LOCALE,
            generated_at,
            source_hash="fixture",
            game_version="fixture",
            publishable=False,
        )
        write_database(
            output_dir / BUILD_DB_FILENAME,
            images.entities,
            build_search_documents(images.entities),
            locale=DEFAULT_LOCALE,
            summary=summary,
            generated_at=generated_at,
            source_hash="fixture",
            game_version="fixture",
            artifact_metadata=artifact_metadata,
        )
        if quality_status(summary) != "passed":
            console.print("✗ fixture 构建质量未通过；数据库不可打包")
            raise typer.Exit(code=EXIT_QUALITY)
        console.print(f"已生成数据库：{output_dir / BUILD_DB_FILENAME}")
    except Exception as exc:
        handle_build_failure(output_dir, exc)
        raise


def build_command(
    game_dir: str | None,
    output: str,
    unpacked_dir: str | None,
    xnb_hack: str | None = None,
    force: bool = False,
) -> None:
    output_dir = Path(output)
    try:
        resolved_game_dir, resolved_unpacked_dir, origin = resolve_build_inputs(
            game_dir, unpacked_dir, xnb_hack, force
        )
        if origin == "auto":
            console.print(f"✓ 自动发现游戏目录：{resolved_game_dir}")
        official = load_game_data_from_unpacked_dir(resolved_unpacked_dir)
        assert_required_official_entities(official)
        output_dir = ensure_directory(output_dir)
        normalized = normalize_entities(
            official.entities,
            aliases=load_aliases(ALIASES_PATH),
            categories=load_categories(CATEGORIES_PATH),
        )
        enriched = enrich_official_entities(normalized, official.support)
        overrides = load_entity_overrides(OVERRIDES_PATH)
        entities, unknown_overrides = apply_entity_overrides(enriched, overrides)
        images = materialize_entity_images_with_report(
            entities,
            asset_root=resolved_unpacked_dir,
            output_dir=output_dir,
        )
        write_build_output(
            output_dir=output_dir,
            entities=images.entities,
            official=official,
            errors=[*official.errors, *images.errors, *override_errors(unknown_overrides)],
            input_hash=source_hash(resolved_unpacked_dir),
            detected_game_version=game_version(resolved_game_dir),
            console=console,
        )
    except Exception as exc:
        handle_build_failure(output_dir, exc)
        raise


def resolve_build_inputs(
    game_dir: str | None,
    unpacked_dir: str | None,
    xnb_hack: str | None,
    force: bool,
) -> tuple[Path, Path, str]:
    try:
        resolved = resolve_game_directory(Path(game_dir) if game_dir is not None else None)
        resolved_game_dir = resolved.path
        resolved_unpacked_dir = resolve_unpacked_dir(
            resolved_game_dir,
            Path(unpacked_dir) if unpacked_dir else None,
            Path(xnb_hack) if xnb_hack else None,
            force,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_GAME_DIR) from exc
    return resolved_game_dir, resolved_unpacked_dir, resolved.origin


def resolve_unpacked_dir(
    game_dir: Path,
    unpacked_dir: Path | None,
    xnb_hack: Path | None,
    force: bool,
) -> Path:
    target = unpacked_dir or game_dir / "Content (unpacked)"
    try:
        ensure_json_output(target)
        return target
    except FileNotFoundError:
        if unpacked_dir is not None:
            raise
    target, _ = unpack_game_directory(game_dir, None, xnb_hack, force)
    return target


def assert_required_official_entities(
    official: GameSourceLoad, required_types: tuple[str, ...] = REQUIRED_ENTITY_TYPES
) -> None:
    counts = Counter(entity.entity_type for entity in official.entities)
    missing = [entity_type for entity_type in required_types if not counts[entity_type]]
    if not missing:
        return
    console.print(f"✗ 官方解包数据缺少必需类型：{'、'.join(missing)}")
    raise typer.Exit(code=EXIT_SOURCE_DATA)


def source_hash(unpacked_dir: Path) -> str:
    paths = [*sorted(unpacked_dir.rglob("*.json")), *CONFIG_PATHS]
    return sha256_paths(paths)


def override_errors(unknown_overrides: list[str]) -> list[dict[str, str]]:
    return [
        {
            "source": "manual_override",
            "source_file": str(OVERRIDES_PATH).replace("\\", "/"),
            "reason": "覆盖规则未匹配到实体",
            "entity_id": entity_id,
        }
        for entity_id in unknown_overrides
    ]


def handle_build_failure(output_dir: Path, exc: Exception) -> None:
    block_release(output_dir, str(exc) or "构建未成功完成")
    quarantined = quarantine_existing_package(output_dir, DEFAULT_LOCALE)
    if quarantined is not None:
        console.print(f"已隔离上一版数据包：{quarantined}")


def quarantine_fixture_package(output_dir: Path) -> None:
    block_fixture_release(output_dir)
    quarantined = quarantine_existing_package(output_dir, DEFAULT_LOCALE)
    if quarantined is not None:
        console.print(f"已隔离上一版数据包：{quarantined}")
