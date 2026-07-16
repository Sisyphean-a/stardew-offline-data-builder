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
from builder.models import BuildSummary, MatchResult, NormalizedEntity, UnmatchedRecord
from builder.pipeline.images import materialize_entity_images, materialize_entity_images_with_report
from builder.pipeline.match import match_community_entities
from builder.pipeline.merge import merge_official_and_community
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.overrides import apply_entity_overrides
from builder.pipeline.reports import summarize_entities, write_build_reports
from builder.pipeline.search_tokens import build_search_documents
from builder.sources.community_source import (
    CommunitySourceLoad,
    load_community_data_from_dir,
)
from builder.sources.game_source import GameSourceLoad, load_game_data_from_unpacked_dir
from builder.sources.override_source import (
    load_aliases,
    load_categories,
    load_entity_overrides,
    load_match_overrides,
)
from builder.utils.hashing import sha256_paths
from builder.utils.paths import (
    ensure_community_data_directory,
    ensure_directory,
    ensure_game_directory,
    ensure_json_output,
)
from builder.utils.time import current_utc_iso
from builder.utils.versions import community_data_version, game_version

console = Console()
OVERRIDES_PATH = Path("data/overrides.zh-CN.json")


def build_fixture_command(output: str) -> None:
    unpacked_dir = DEFAULT_FIXTURE_ROOT / "Content (unpacked)"
    output_dir = ensure_directory(Path(output))
    raw_entities = load_game_data_from_unpacked_dir(unpacked_dir).entities
    entities = normalize_entities(
        raw_entities,
        aliases=load_aliases(Path("data/aliases.zh-CN.json")),
        categories=load_categories(Path("data/categories.zh-CN.json")),
    )
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
    game_dir: str,
    community_data: str | None,
    output: str,
    unpacked_dir: str | None,
    xnb_hack: str | None = None,
    force: bool = False,
) -> None:
    resolved_game_dir, resolved_community_dir, resolved_unpacked_dir = resolve_build_inputs(
        game_dir,
        community_data,
        unpacked_dir,
        xnb_hack,
        force,
    )
    official = load_game_data_from_unpacked_dir(resolved_unpacked_dir)
    assert_primary_official_entities(official)
    community = load_community_data(resolved_community_dir)
    output_dir = ensure_directory(Path(output))
    aliases = load_aliases(Path("data/aliases.zh-CN.json"))
    categories = load_categories(Path("data/categories.zh-CN.json"))
    match_overrides = load_match_overrides(OVERRIDES_PATH)
    entity_overrides = load_entity_overrides(OVERRIDES_PATH)
    official_entities = normalize_entities(
        official.entities,
        aliases=aliases,
        categories=categories,
    )
    community_entities = normalize_entities(community.entities, aliases={}, categories={})
    matches, unmatched = match_community_entities(
        official_entities,
        community_entities,
        match_overrides,
    )
    merged_entities = merge_official_and_community(official_entities, community_entities, matches)
    merged_entities, unknown_overrides = apply_entity_overrides(merged_entities, entity_overrides)
    images = materialize_entity_images_with_report(
        merged_entities,
        asset_root=resolved_unpacked_dir,
        output_dir=output_dir,
    )
    merged_entities, _ = apply_entity_overrides(images.entities, entity_overrides)
    write_build_output(
        output_dir,
        merged_entities,
        official,
        community,
        official_entities,
        community_entities,
        unmatched,
        matches,
        [
            *official.errors,
            *community.errors,
            *images.errors,
            *override_errors(unknown_overrides),
        ],
        source_hash(resolved_unpacked_dir, resolved_community_dir),
        game_version(resolved_game_dir),
        community_data_version(resolved_community_dir),
    )


def resolve_build_inputs(
    game_dir: str,
    community_data: str | None,
    unpacked_dir: str | None,
    xnb_hack: str | None,
    force: bool,
) -> tuple[Path, Path | None, Path]:
    try:
        resolved_game_dir = ensure_game_directory(Path(game_dir))
        resolved_community_dir = resolve_community_dir(community_data)
        resolved_unpacked_dir = resolve_unpacked_dir(
            resolved_game_dir,
            Path(unpacked_dir) if unpacked_dir else None,
            Path(xnb_hack) if xnb_hack else None,
            force,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        console.print(f"✗ {exc}")
        raise typer.Exit(code=EXIT_GAME_DIR) from exc
    return resolved_game_dir, resolved_community_dir, resolved_unpacked_dir


def resolve_community_dir(community_data: str | None) -> Path | None:
    if community_data is None:
        return None
    return ensure_community_data_directory(Path(community_data))


def resolve_unpacked_dir(
    game_dir: Path, unpacked_dir: Path | None, xnb_hack: Path | None, force: bool
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


def load_community_data(community_dir: Path | None) -> CommunitySourceLoad:
    return load_community_data_from_dir(community_dir) if community_dir else CommunitySourceLoad()


def assert_primary_official_entities(official: GameSourceLoad) -> None:
    counts = Counter(entity.entity_type for entity in official.entities)
    primary_types = ("object", "crop", "fish", "villager")
    missing = [entity_type for entity_type in primary_types if not counts[entity_type]]
    if missing:
        names = "、".join(missing)
        console.print(f"✗ 官方解包数据缺少基础类型：{names}")
        raise typer.Exit(code=EXIT_SOURCE_DATA)


def write_build_output(
    output_dir: Path,
    entities: list[NormalizedEntity],
    official: GameSourceLoad,
    community: CommunitySourceLoad,
    official_entities: list[NormalizedEntity],
    community_entities: list[NormalizedEntity],
    unmatched: list[UnmatchedRecord],
    matches: dict[str, MatchResult],
    errors: list[dict[str, str]],
    input_hash: str,
    detected_game_version: str,
    detected_community_version: str,
) -> None:
    db_path = output_dir / BUILD_DB_FILENAME
    reports_dir = output_dir / REPORTS_DIRNAME
    generated_at = current_utc_iso()
    summary = summarize_entities(entities)
    summary.unmatched = len(unmatched)
    write_database(
        db_path,
        entities,
        build_search_documents(entities),
        locale=DEFAULT_LOCALE,
        summary=summary,
        generated_at=generated_at,
        source_hash=input_hash,
        game_version=detected_game_version,
        community_data_version=detected_community_version,
    )
    write_build_reports(
        reports_dir=reports_dir,
        summary=summary,
        unmatched=unmatched,
        missing_translations=[
            entity for entity in entities if entity.translation_status == "missing"
        ],
        errors=errors,
        source_discovery={"official": official.discovered, "community": community.discovered},
        coverage=build_coverage(official_entities, community_entities, summary, matches),
    )
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


def source_hash(unpacked_dir: Path, community_dir: Path | None) -> str:
    paths = [*sorted(unpacked_dir.rglob("*.json")), OVERRIDES_PATH]
    if community_dir is not None:
        paths.extend(sorted(community_dir.rglob("*.json")))
    return sha256_paths(paths)


def build_coverage(
    official_entities: list[NormalizedEntity],
    community_entities: list[NormalizedEntity],
    summary: BuildSummary,
    matches: dict[str, MatchResult],
) -> dict[str, object]:
    return {
        "official": dict(Counter(entity.entity_type for entity in official_entities)),
        "community": dict(Counter(entity.entity_type for entity in community_entities)),
        "merged": summary.counts_by_type,
        "communityMatches": len(matches),
    }


def override_errors(unknown_overrides: list[str]) -> list[dict[str, str]]:
    return [
        {
            "source": "manual_override",
            "source_file": "data/overrides.zh-CN.json",
            "reason": "覆盖规则未匹配到实体",
            "entity_id": entity_id,
        }
        for entity_id in unknown_overrides
    ]
