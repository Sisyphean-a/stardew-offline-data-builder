from __future__ import annotations

from collections import Counter
from pathlib import Path

import typer
from rich.console import Console

from builder.commands.package import create_svdata_package, write_manifest
from builder.commands.unpack import unpack_game_directory
from builder.config import (
    BUILD_DB_FILENAME,
    DEFAULT_FIXTURE_ROOT,
    DEFAULT_LOCALE,
    EXIT_GAME_DIR,
    EXIT_SOURCE_DATA,
    REPORTS_DIRNAME,
)
from builder.database.writer import write_database
from builder.models import BuildSummary, NormalizedEntity
from builder.pipeline.images import materialize_entity_images, materialize_entity_images_with_report
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.official_enrichment import enrich_official_entities
from builder.pipeline.overrides import apply_entity_overrides
from builder.pipeline.reports import summarize_entities, write_build_reports
from builder.pipeline.search_tokens import build_search_documents
from builder.sources.game_source import GameSourceLoad, load_game_data_from_unpacked_dir
from builder.sources.override_source import (
    load_aliases,
    load_categories,
    load_entity_overrides,
)
from builder.sources.steam_discovery import resolve_game_directory
from builder.utils.hashing import sha256_paths
from builder.utils.paths import (
    ensure_directory,
    ensure_json_output,
)
from builder.utils.time import current_utc_iso
from builder.utils.versions import game_version

console = Console()
ALIASES_PATH = Path("data/aliases.zh-CN.json")
CATEGORIES_PATH = Path("data/categories.zh-CN.json")
OVERRIDES_PATH = Path("data/overrides.zh-CN.json")
CONFIG_PATHS = (ALIASES_PATH, CATEGORIES_PATH, OVERRIDES_PATH)


def build_fixture_command(output: str) -> None:
    unpacked_dir = DEFAULT_FIXTURE_ROOT / "Content (unpacked)"
    output_dir = ensure_directory(Path(output))
    official = load_game_data_from_unpacked_dir(unpacked_dir)
    entities = normalize_entities(
        official.entities,
        aliases=load_aliases(ALIASES_PATH),
        categories=load_categories(CATEGORIES_PATH),
    )
    entities = enrich_official_entities(entities, official.support)
    entities = materialize_entity_images(entities, asset_root=unpacked_dir, output_dir=output_dir)
    write_database(
        output_dir / BUILD_DB_FILENAME,
        entities,
        build_search_documents(entities),
        locale=DEFAULT_LOCALE,
        summary=summarize_entities(entities),
    )
    console.print(f"已生成数据库：{output_dir / BUILD_DB_FILENAME}")


def build_command(
    game_dir: str | None,
    output: str,
    unpacked_dir: str | None,
    xnb_hack: str | None = None,
    force: bool = False,
) -> None:
    resolved_game_dir, resolved_unpacked_dir, origin = resolve_build_inputs(
        game_dir, unpacked_dir, xnb_hack, force
    )
    if origin == "auto":
        console.print(f"✓ 自动发现游戏目录：{resolved_game_dir}")
    official = load_game_data_from_unpacked_dir(resolved_unpacked_dir)
    assert_primary_official_entities(official)
    output_dir = ensure_directory(Path(output))
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
    entities, _ = apply_entity_overrides(images.entities, overrides)
    write_build_output(
        output_dir=output_dir,
        entities=entities,
        official=official,
        errors=[*official.errors, *images.errors, *override_errors(unknown_overrides)],
        input_hash=source_hash(resolved_unpacked_dir),
        detected_game_version=game_version(resolved_game_dir),
    )


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


def assert_primary_official_entities(official: GameSourceLoad) -> None:
    counts = Counter(entity.entity_type for entity in official.entities)
    missing = [
        entity_type
        for entity_type in ("object", "crop", "fish", "villager")
        if not counts[entity_type]
    ]
    if not missing:
        return
    console.print(f"✗ 官方解包数据缺少基础类型：{'、'.join(missing)}")
    raise typer.Exit(code=EXIT_SOURCE_DATA)


def write_build_output(
    output_dir: Path,
    entities: list[NormalizedEntity],
    official: GameSourceLoad,
    errors: list[dict[str, str]],
    input_hash: str,
    detected_game_version: str,
) -> None:
    db_path = output_dir / BUILD_DB_FILENAME
    reports_dir = output_dir / REPORTS_DIRNAME
    generated_at = current_utc_iso()
    summary = summarize_entities(entities)
    write_database(
        db_path,
        entities,
        build_search_documents(entities),
        locale=DEFAULT_LOCALE,
        summary=summary,
        generated_at=generated_at,
        source_hash=input_hash,
        game_version=detected_game_version,
    )
    write_official_reports(reports_dir, summary, entities, official, errors)
    manifest_path = write_manifest(
        output_dir=output_dir,
        locale=DEFAULT_LOCALE,
        generated_at=generated_at,
        db_path=db_path,
        summary=summary,
        game_version=detected_game_version,
    )
    package_path = create_svdata_package(
        output_dir=output_dir,
        locale=DEFAULT_LOCALE,
        generated_at=generated_at,
        db_path=db_path,
        manifest_path=manifest_path,
        reports_dir=reports_dir,
    )
    console.print(f"已完成构建：{db_path}")
    console.print(f"已生成数据包：{package_path}")


def write_official_reports(
    reports_dir: Path,
    summary: BuildSummary,
    entities: list[NormalizedEntity],
    official: GameSourceLoad,
    errors: list[dict[str, str]],
) -> None:
    write_build_reports(
        reports_dir=reports_dir,
        summary=summary,
        missing_translations=[
            entity for entity in entities if entity.translation_status == "missing"
        ],
        errors=errors,
        source_discovery={"official": official.discovered},
        coverage=build_coverage(entities),
    )


def source_hash(unpacked_dir: Path) -> str:
    paths = [*sorted(unpacked_dir.rglob("*.json")), *CONFIG_PATHS]
    return sha256_paths(paths)


def build_coverage(entities: list[NormalizedEntity]) -> dict[str, object]:
    official = Counter(entity.entity_type for entity in entities)
    enriched = Counter(
        entity.entity_type
        for entity in entities
        if isinstance(entity.extra_json.get("officialDerived"), dict)
    )
    return {"official": dict(official), "officialDerived": dict(enriched)}


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
