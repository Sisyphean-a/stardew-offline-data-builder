from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import typer
from rich.console import Console

from builder.commands.build import (
    assert_required_official_entities,
    resolve_build_inputs,
    source_hash,
)
from builder.commands.package import create_schema5_svdata_package
from builder.config import DEFAULT_LOCALE
from builder.models import NormalizedEntity
from builder.models_schema5 import Schema5Package
from builder.pipeline.images import materialize_entity_images_with_report
from builder.pipeline.normalize import normalize_entities
from builder.pipeline.overrides import apply_entity_overrides
from builder.pipeline.publish import filter_publishable_entities
from builder.pipeline.release_state import block_release
from builder.pipeline.reports import summarize_entities, write_build_reports
from builder.pipeline.schema5_artifacts import schema5_artifact_hashes
from builder.pipeline.schema5_projection import build_schema5_package
from builder.pipeline.schema5_release import (
    ensure_core_fact_slots,
    validate_regression_budget,
    validate_release_coverage,
)
from builder.pipeline.schema5_writer import write_schema5_package
from builder.sources.game_source import load_game_data_from_unpacked_dir
from builder.sources.override_source import (
    load_aliases,
    load_categories,
    load_entity_overrides,
)
from builder.utils.json_io import dump_json_file, load_json_file
from builder.utils.time import current_utc_iso
from builder.utils.versions import game_version

console = Console()
ALIASES_PATH = Path("data/aliases.zh-CN.json")
CATEGORIES_PATH = Path("data/categories.zh-CN.json")
OVERRIDES_PATH = Path("data/overrides.zh-CN.json")


def build_schema5_candidate_command(
    game_dir: str | None,
    output: str,
    unpacked_dir: str | None,
    xnb_hack: str | None = None,
    force: bool = False,
) -> None:
    """Build the formal typed schema-5 candidate without the legacy writer."""
    output_dir = Path(output)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    failure_dir = output_dir.with_name(f"{output_dir.name}.failed")
    try:
        resolved_game_dir, resolved_unpacked_dir, _ = resolve_build_inputs(
            game_dir, unpacked_dir, xnb_hack, force
        )
        official = load_game_data_from_unpacked_dir(resolved_unpacked_dir)
        assert_required_official_entities(official)
        normalized = normalize_entities(
            official.entities,
            aliases=load_aliases(ALIASES_PATH),
            categories=load_categories(CATEGORIES_PATH),
        )
        all_entities, unknown_overrides = apply_entity_overrides(
            normalized, load_entity_overrides(OVERRIDES_PATH)
        )
        formal_entities = prepare_formal_inputs(all_entities)
        entities = filter_publishable_entities(formal_entities)
        if official.errors:
            raise ValueError(f"官方数据错误，停止 schema 5 候选：{official.errors[0]}")
        if unknown_overrides:
            raise ValueError(f"存在未匹配覆盖，停止 schema 5 候选：{unknown_overrides[0]}")
        detected_game_version = game_version(resolved_game_dir)
        input_digest = source_hash(resolved_unpacked_dir)
        with TemporaryDirectory(
            prefix=f".{output_dir.name}.candidate-", dir=output_dir.parent
        ) as temporary:
            staging_dir = Path(temporary)
            try:
                images = materialize_entity_images_with_report(
                    entities,
                    asset_root=resolved_unpacked_dir,
                    output_dir=staging_dir,
                    allow_legacy=False,
                )
                if images.errors:
                    raise ValueError(f"视觉物化错误，停止 schema 5 候选：{images.errors[0]}")
                candidate = build_schema5_package(
                    images.entities,
                    staging_dir,
                    game_version=detected_game_version,
                    support=official.support,
                    support_entities=formal_entities,
                )
                ensure_core_fact_slots(candidate)
                release_coverage = validate_release_coverage(candidate)
                validate_regression_budget(output_dir, release_coverage, candidate)
                coverage = typed_coverage(candidate)
                coverage["release"] = release_coverage
                generated_at = current_utc_iso()
                paths = write_schema5_package(
                    staging_dir,
                    candidate,
                    locale=DEFAULT_LOCALE,
                    source_hash=input_digest,
                    game_version=detected_game_version,
                    generated_at=generated_at,
                    publishable=True,
                    coverage=coverage,
                )
                summary = summarize_entities(images.entities)
                write_build_reports(
                    staging_dir / "reports",
                    summary,
                    [
                        entity
                        for entity in images.entities
                        if entity.translation_status in {"missing", "invalid"}
                    ],
                    errors=[],
                    source_discovery={"official": official.discovered},
                    coverage=coverage,
                )
                bind_schema5_artifacts(staging_dir)
                create_schema5_svdata_package(
                    staging_dir,
                    DEFAULT_LOCALE,
                    generated_at,
                    paths["database"],
                    paths["manifest"],
                    staging_dir / "reports",
                    paths["conformance"],
                )
                replace_candidate_directory(staging_dir, output_dir)
            except Exception as exc:
                quarantine_candidate_output(output_dir)
                preserve_failed_candidate(staging_dir, failure_dir, str(exc))
                raise

        if failure_dir.exists():
            shutil.rmtree(failure_dir)
        console.print(f"已完成 schema 5 候选：{output_dir / 'stardew.db'}")
        console.print(f"已生成数据包：{output_dir / 'stardew-zh-cn.svdata'}")
    except Exception as exc:
        if not failure_dir.exists():
            quarantine_candidate_output(output_dir)
            preserve_failed_candidate(None, failure_dir, str(exc))
        raise typer.Exit(code=1) from exc


def prepare_formal_inputs(entities: list[NormalizedEntity]) -> list[NormalizedEntity]:
    """Validate and detach the v4 serialization before schema-5 projection.

    Official compact records are parsed into ``source_attributes`` with an
    explicit ``sourceFormat`` and typed fields.  Their legacy payload remains
    on the object only so the separate v4 recovery writer can use it; it is
    removed from the copies that enter the formal candidate.  A record with
    legacy markers but no explicit typed source boundary is rejected rather
    than being allowed to fall back to the v4 representation.
    """
    reject_legacy_only_inputs(entities)
    legacy_keys = {"legacyFields", "legacyValue", "officialDerived"}
    return [
        entity.model_copy(
            update={
                "extra_json": {
                    key: value
                    for key, value in entity.extra_json.items()
                    if key not in legacy_keys
                }
            }
        )
        for entity in entities
    ]


def reject_legacy_only_inputs(entities: list[NormalizedEntity]) -> None:
    """Reject legacy-shaped input that has no explicit typed source boundary.

    ``normalize_entities`` keeps the compact v4 fields in ``extra_json`` for
    the explicit recovery writer, while the parser copies only typed mappings
    into ``source_attributes``.  A compact record is therefore admissible
    only when it declares ``sourceFormat=official_compact``; arbitrary legacy
    markers injected beside structured values remain a hard failure.  Staging
    fixtures use their explicit adapter and never call this boundary.
    """
    legacy_payload_keys = {"legacyFields", "legacyValue"}
    forbidden_keys = {"legacyFields", "legacyValue", "officialDerived"}
    for entity in entities:
        if any(key in entity.source_attributes for key in forbidden_keys):
            raise ValueError(f"schema 5 正式候选拒绝 legacy 输入：{entity.id}")
        if "officialDerived" in entity.extra_json:
            raise ValueError(f"schema 5 正式候选拒绝 legacy 输入：{entity.id}")
        if legacy_payload_keys.intersection(entity.extra_json) and (
            entity.source_attributes.get("sourceFormat") != "official_compact"
        ):
            raise ValueError(f"schema 5 正式候选拒绝 legacy 输入：{entity.id}")


def bind_schema5_artifacts(output_dir: Path) -> None:
    manifest_path = output_dir / "manifest.json"
    manifest = load_json_file(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("schema 5 manifest 无效")
    manifest["artifacts"] = schema5_artifact_hashes(output_dir)
    dump_json_file(manifest_path, manifest)


def typed_coverage(package: Schema5Package) -> dict[str, object]:
    status_counts: dict[str, int] = {}
    by_type: dict[str, int] = {}
    entities = {entity.id: entity.entity_type for entity in package.entities}
    for slot in package.fact_slots:
        status_counts[slot.status] = status_counts.get(slot.status, 0) + 1
        key = f"{entities.get(slot.entity_id, 'unknown')}:{slot.slot_key}:{slot.status}"
        by_type[key] = by_type.get(key, 0) + 1
    return {
        "factSlots": status_counts,
        "factSlotsByType": dict(sorted(by_type.items())),
        "conditions": {
            "complete": sum(
                condition.completeness == "complete" for condition in package.condition_sets
            ),
            "partial": sum(
                condition.completeness == "partial" for condition in package.condition_sets
            ),
            "opaque": sum(
                condition.completeness == "opaque" for condition in package.condition_sets
            ),
        },
        "relations": {
            "groups": len(package.relation_groups),
            "edges": len(package.relations),
        },
        "visuals": {
            "pendingReview": sum(
                visual.status == "pending_review" for visual in package.visuals
            ),
            "packageErrors": sum(
                visual.status == "package_error" for visual in package.visuals
            ),
        },
    }


def quarantine_candidate_output(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    previous_dir = output_dir.with_name(f"{output_dir.name}.previous")
    if previous_dir.exists():
        shutil.rmtree(previous_dir)
    output_dir.replace(previous_dir)


def replace_candidate_directory(staging_dir: Path, output_dir: Path) -> None:
    backup_dir = output_dir.with_name(f"{output_dir.name}.previous")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    try:
        if output_dir.exists():
            output_dir.replace(backup_dir)
        staging_dir.replace(output_dir)
    except Exception:
        if not output_dir.exists() and backup_dir.exists():
            backup_dir.replace(output_dir)
        raise
    else:
        if backup_dir.exists():
            shutil.rmtree(backup_dir)


def preserve_failed_candidate(
    staging_dir: Path | None,
    failure_dir: Path,
    reason: str,
) -> None:
    if failure_dir.exists():
        shutil.rmtree(failure_dir)
    if staging_dir is not None and staging_dir.exists():
        staging_dir.replace(failure_dir)
    else:
        failure_dir.mkdir(parents=True, exist_ok=True)
    block_release(failure_dir, reason)


__all__ = ["build_schema5_candidate_command"]
