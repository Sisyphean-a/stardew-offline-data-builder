from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console

from builder.commands.build import (
    assert_required_official_entities,
    resolve_build_inputs,
    source_hash,
)
from builder.config import DEFAULT_LOCALE
from builder.pipeline.images import materialize_entity_images_with_report
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.overrides import apply_entity_overrides
from builder.pipeline.release_state import block_release
from builder.pipeline.schema5_projection import build_schema5_staging_package
from builder.pipeline.schema5_writer import write_schema5_package
from builder.sources.game_source import load_game_data_from_unpacked_dir
from builder.sources.override_source import (
    load_aliases,
    load_categories,
    load_entity_overrides,
)
from builder.utils.versions import game_version

console = Console()
ALIASES_PATH = Path("data/aliases.zh-CN.json")
CATEGORIES_PATH = Path("data/categories.zh-CN.json")
OVERRIDES_PATH = Path("data/overrides.zh-CN.json")


def build_schema5_staging_command(
    game_dir: str | None,
    output: str,
    unpacked_dir: str | None,
    xnb_hack: str | None = None,
    force: bool = False,
) -> None:
    """Project real local official assets into a non-publishable schema-5 staging package."""
    output_dir = Path(output)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved_game_dir, resolved_unpacked_dir, _ = resolve_build_inputs(
            game_dir, unpacked_dir, xnb_hack, force
        )
        official = load_game_data_from_unpacked_dir(resolved_unpacked_dir)
        assert_required_official_entities(official, ("object", "crop", "fish", "villager"))
        normalized = normalize_entities(
            official.entities,
            aliases=load_aliases(ALIASES_PATH),
            categories=load_categories(CATEGORIES_PATH),
        )
        entities, unknown_overrides = apply_entity_overrides(
            normalized, load_entity_overrides(OVERRIDES_PATH)
        )
        with TemporaryDirectory(
            prefix=f".{output_dir.name}.staging-", dir=output_dir.parent
        ) as temporary:
            staging_dir = Path(temporary)
            images = materialize_entity_images_with_report(
                entities,
                asset_root=resolved_unpacked_dir,
                output_dir=staging_dir,
            )
            if official.errors:
                raise ValueError(f"官方数据错误，停止 schema 5 staging：{official.errors[0]}")
            if images.errors:
                raise ValueError(f"视觉物化错误，停止 schema 5 staging：{images.errors[0]}")
            if unknown_overrides:
                raise ValueError(f"存在未匹配覆盖，停止 schema 5 staging：{unknown_overrides[0]}")
            package = build_schema5_staging_package(
                images.entities,
                staging_dir,
                game_version=game_version(resolved_game_dir),
                support=official.support,
            )
            paths = write_schema5_package(
                staging_dir,
                package,
                locale=DEFAULT_LOCALE,
                source_hash=source_hash(resolved_unpacked_dir),
                game_version=game_version(resolved_game_dir),
                publishable=False,
            )
            block_release(
                staging_dir,
                "schema 5 staging 明确不可发布；等待完整分类门禁和正式发布流水线",
            )
            backup_dir = output_dir.with_name(f"{output_dir.name}.previous")
            try:
                if output_dir.exists():
                    if backup_dir.exists():
                        shutil.rmtree(backup_dir)
                    output_dir.replace(backup_dir)
                staging_dir.replace(output_dir)
            except Exception:
                if not output_dir.exists() and backup_dir.exists():
                    backup_dir.replace(output_dir)
                raise
            else:
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)

        database_path = output_dir / paths["database"].name
        console.print(f"已生成真实官方资产 schema 5 staging：{database_path}")
        console.print(
            f"实体：{len(package.entities)}，事实槽：{len(package.fact_slots)}，关系边：{len(package.relations)}"
        )
        console.print("⚠ staging 明确不可发布；分类事实、覆盖门禁和人工视觉复核尚未完成")
    except Exception as exc:
        block_release(output_dir, str(exc) or "schema 5 staging 未成功完成")
        raise
