"""Transactional B2 writer for typed facts, conditions and evidence."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import orjson

from builder.database.schema5 import (
    CONFORMANCE_FILENAME,
    MANIFEST_FILENAME,
    SCHEMA_FILENAME,
    build_schema5_metadata,
    insert_aliases,
    insert_build_meta,
    insert_capabilities,
    insert_cards_and_visuals,
    insert_entities,
    insert_search,
    schema_fingerprint,
    sha256_file,
)
from builder.models_schema5 import (
    VALID_CONDITION_COMPLETENESS,
    VALID_FACT_STATUSES,
    VALID_RELATION_PREDICATES,
    VALID_VISUAL_STATUSES,
    Schema5ClaimEvidence,
    Schema5ConditionSet,
    Schema5ConditionTerm,
    Schema5Evidence,
    Schema5FactItem,
    Schema5FactSlot,
    Schema5Package,
    Schema5SourceDocument,
    Schema5SourceLocator,
    Schema5Visual,
    typed_value_present,
)
from builder.pipeline.schema5_contract import (
    CLAIM_TYPES,
    CONTENT_CONTRACT,
    EVIDENCE_KINDS,
    FACET_CLAIM_STATUSES,
    FACET_VALUE_TYPES,
    MANIFEST_VERSION,
    SCHEMA_VERSION,
    SOURCE_KINDS,
    TYPED_VALUE_TYPES,
    VISUAL_ROLES,
)
from builder.utils.time import current_utc_iso

HASH_PATTERN = re.compile(r"[a-fA-F0-9]{64}")


def write_schema5_package(
    output_dir: Path,
    package: Schema5Package,
    *,
    locale: str = "zh-CN",
    source_hash: str = "f" * 64,
    game_version: str = "fixture",
    generated_at: str | None = None,
    publishable: bool = False,
    coverage: dict[str, object] | None = None,
) -> dict[str, Path]:
    """Write a schema5 package from typed rows and fail before touching output.

    B2 owns row validation and the public writer.  It deliberately accepts a
    package object rather than the v4 ``NormalizedEntity.extra_json`` payload.
    """

    validate_schema5_package(package, publishable=publishable)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or current_utc_iso()
    database_path = output_dir / "stardew.db"
    manifest_path = output_dir / MANIFEST_FILENAME
    conformance_path = output_dir / CONFORMANCE_FILENAME
    tmp_path = database_path.with_suffix(database_path.suffix + ".tmp")
    tmp_path.unlink(missing_ok=True)
    connection = sqlite3.connect(tmp_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            (Path(__file__).parents[1] / "database" / SCHEMA_FILENAME).read_text(encoding="utf-8")
        )
        fingerprint = schema_fingerprint(connection)
        metadata = build_schema5_metadata(
            entities=package.entities,
            locale=locale,
            source_hash=source_hash,
            game_version=game_version,
            generated_at=generated_at,
            schema_fingerprint=fingerprint,
            publishable=publishable,
        )
        metadata["coverage"] = coverage or coverage_payload(package)
        insert_build_meta(connection, metadata)
        insert_capabilities(connection, metadata["capabilities"])
        insert_entities(connection, package.entities, generated_at)
        insert_cards_and_visuals(
            connection,
            package.entities,
            visuals=package.visuals,
            cards=package.entity_cards,
        )
        insert_aliases(connection, package.entities)
        insert_search(connection, package.entities)
        insert_conditions(connection, package.condition_sets, package.condition_terms)
        insert_sources(connection, package.source_documents, package.source_locators)
        insert_fact_rows(connection, package.fact_slots, package.fact_items)
        insert_evidence(connection, package.evidence, package.claim_evidence)
        insert_relations(connection, package.relation_groups, package.relations)
        insert_facets(connection, package.facet_groups, package.facets)
        insert_id_aliases(connection, package.id_aliases)
        connection.commit()
    except Exception:
        connection.close()
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
    manifest = {
        "format": "stardew-offline-data",
        "manifestVersion": MANIFEST_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "contentContract": CONTENT_CONTRACT,
        "schemaFingerprint": fingerprint,
        "builderVersion": metadata["builderVersion"],
        "gameVersion": metadata["gameVersion"],
        "language": metadata["language"],
        "generatedAt": metadata["generatedAt"],
        "sourceHash": metadata["sourceHash"],
        "publishable": metadata["publishable"],
        "capabilities": metadata["capabilities"],
        "database": {
            "file": database_path.name,
            "sha256": sha256_file(tmp_path),
            "schemaFingerprint": fingerprint,
        },
        "content": metadata["content"],
        "quality": metadata["quality"],
        "coverage": metadata["coverage"],
    }
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    conformance_tmp = conformance_path.with_suffix(conformance_path.suffix + ".tmp")
    try:
        manifest_tmp.write_bytes(orjson.dumps(manifest, option=orjson.OPT_INDENT_2))
        conformance_tmp.write_bytes(
            orjson.dumps(
                {
                    "status": (
                        "release"
                        if publishable
                        else ("non_publishable_fixture" if game_version == "fixture" else "staging")
                    ),
                    "manifestVersion": MANIFEST_VERSION,
                    "schemaVersion": SCHEMA_VERSION,
                    "contentContract": CONTENT_CONTRACT,
                    "publishable": publishable,
                    "databaseSha256": manifest["database"]["sha256"],
                    "schemaFingerprint": fingerprint,
                    "factSlots": len(package.fact_slots),
                    "conditions": len(package.condition_sets),
                    "evidence": len(package.evidence),
                    "coverage": metadata["coverage"],
                    "containsLegacyOfficialDerived": False,
                },
                option=orjson.OPT_INDENT_2,
            )
        )
        commit_schema5_files(
            (
                (tmp_path, database_path),
                (manifest_tmp, manifest_path),
                (conformance_tmp, conformance_path),
            )
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)
        conformance_tmp.unlink(missing_ok=True)
        raise
    return {"database": database_path, "manifest": manifest_path, "conformance": conformance_path}


def commit_schema5_files(files: tuple[tuple[Path, Path], ...]) -> None:
    backups: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for _, target in files:
            if target.exists():
                backup = target.with_name(f".{target.name}.backup-{uuid4().hex}")
                target.replace(backup)
                backups.append((target, backup))
        for temporary, target in files:
            temporary.replace(target)
            installed.append(target)
    except Exception:
        for target in installed:
            target.unlink(missing_ok=True)
        for target, backup in reversed(backups):
            backup.replace(target)
        raise
    else:
        for _, backup in backups:
            backup.unlink(missing_ok=True)


def validate_schema5_package(package: Schema5Package, *, publishable: bool) -> None:
    if publishable:
        validate_schema5_publish_quality(package)
    entity_ids = {entity.id for entity in package.entities}
    if len(entity_ids) != len(package.entities) or any(
        ":" not in entity_id or not entity_id.split(":", 1)[1] for entity_id in entity_ids
    ):
        raise ValueError("schema 5 实体 ID 必须稳定且唯一")
    validate_unique((entity.id, entity.entity_type) for entity in package.entities)
    validate_unique((slot.entity_id, slot.slot_key) for slot in package.fact_slots)
    validate_unique((fact.slot_id, fact.ordinal) for fact in package.fact_items)
    validate_unique((card.entity_id,) for card in package.entity_cards)
    if any(card.entity_id not in entity_ids for card in package.entity_cards):
        raise ValueError("卡片实体引用不存在")
    validate_unique((group.entity_id, group.family) for group in package.facet_groups)
    validate_unique(
        (facet.group_id, facet.scope_family, facet.scope_id, facet.id)
        for facet in package.facets
    )
    validate_unique((condition.id,) for condition in package.condition_sets)
    validate_unique((condition.id, condition.ordinal) for condition in package.condition_terms)
    validate_unique((source.id,) for source in package.source_documents)
    validate_unique((locator.id,) for locator in package.source_locators)
    validate_unique((evidence.id,) for evidence in package.evidence)
    validate_unique((relation.id,) for relation in package.relations)
    validate_unique((visual.id,) for visual in package.visuals)
    validate_unique((visual.entity_id, visual.role) for visual in package.visuals)
    validate_unique((alias.alias_id,) for alias in package.id_aliases)

    all_ids = {
        item.id
        for items in (
            package.condition_sets,
            package.condition_terms,
            package.source_documents,
            package.source_locators,
            package.evidence,
            package.fact_slots,
            package.fact_items,
            package.relation_groups,
            package.relations,
            package.visuals,
        )
        for item in items
    }
    if any(not item_id for item_id in all_ids):
        raise ValueError("schema 5 稳定 ID 不能为空")
    if any(not item.id for item in package.relation_groups):
        raise ValueError("关系组稳定 ID 不能为空")
    claim_ids = {
        claim.claim_id
        for claim in package.claim_evidence
    }
    if any(not item.id for item in package.facet_groups):
        raise ValueError("facet group 稳定 ID 不能为空")
    if any(not item.alias_id or not item.entity_id for item in package.id_aliases):
        raise ValueError("ID 重定向不能为空")
    if any(item.entity_id not in entity_ids for item in package.id_aliases):
        raise ValueError("ID 重定向目标不存在")
    condition_ids = {condition.id for condition in package.condition_sets}
    slot_ids = {slot.id for slot in package.fact_slots}
    document_ids = {document.id for document in package.source_documents}
    locator_ids = {locator.id for locator in package.source_locators}
    evidence_ids = {evidence.id for evidence in package.evidence}
    relation_ids = {relation.id for relation in package.relations}
    visual_ids = {visual.id for visual in package.visuals}
    items_by_slot: dict[str, list[Schema5FactItem]] = {}
    for item in package.fact_items:
        items_by_slot.setdefault(item.slot_id, []).append(item)

    for condition in package.condition_sets:
        if condition.completeness not in VALID_CONDITION_COMPLETENESS:
            raise ValueError(f"条件完整性无效：{condition.id}")
    for document in package.source_documents:
        if document.source_kind not in SOURCE_KINDS or not document.title.strip():
            raise ValueError(f"来源文档无效：{document.id}")
        validate_source_document(document)
    for term in package.condition_terms:
        if term.condition_set_id not in condition_ids:
            raise ValueError(f"条件项引用不存在：{term.id}")
        if term.ordinal < 0:
            raise ValueError(f"条件项顺序无效：{term.id}")
        if sum(value is not None for value in (
            term.value_text, term.value_integer, term.value_real
        )) > 1:
            raise ValueError(f"条件项类型化值不唯一：{term.id}")
    for locator in package.source_locators:
        if locator.source_document_id not in document_ids:
            raise ValueError(f"来源定位引用不存在：{locator.id}")
        if not locator.source_file and not locator.json_path and not locator.record_key:
            raise ValueError(f"来源定位缺少位置：{locator.id}")
    for slot in package.fact_slots:
        if slot.entity_id not in entity_ids or slot.status not in VALID_FACT_STATUSES:
            raise ValueError(f"事实槽引用或状态无效：{slot.id}")
        values = typed_value_present(slot)
        slot_items = items_by_slot.get(slot.id, [])
        if slot.value_type not in TYPED_VALUE_TYPES and values:
            raise ValueError(f"事实槽值类型无效：{slot.id}")
        if values and not value_matches_type(slot.value_type, slot):
            raise ValueError(f"事实槽值与类型不匹配：{slot.id}")
        if sum(value is not None for value in (
            slot.text_value, slot.integer_value, slot.real_value, slot.boolean_value
        )) > 1:
            raise ValueError(f"事实槽类型化值不唯一：{slot.id}")
        if slot.status in {"unknown", "not_collected", "not_applicable"} and values:
            raise ValueError(f"缺失事实不能携带值：{slot.id}")
        if (
            slot.status in {"fixed", "conditional", "dynamic_rule"}
            and not values
            and not slot_items
        ):
            raise ValueError(f"已知事实缺少类型化值：{slot.id}")
        if slot.status == "conditional" and slot.condition_set_id not in condition_ids:
            raise ValueError(f"条件事实缺少条件集合：{slot.id}")
        if slot.condition_set_id is not None and slot.condition_set_id not in condition_ids:
            raise ValueError(f"事实槽条件引用不存在：{slot.id}")
        if slot.status == "fixed" and slot.condition_set_id is not None:
            condition = next(c for c in package.condition_sets if c.id == slot.condition_set_id)
            if condition.completeness != "complete":
                raise ValueError(f"固定事实引用不完整条件：{slot.id}")
    for item in package.fact_items:
        if item.slot_id not in slot_ids or item.ordinal < 0:
            raise ValueError(f"事实项引用或顺序无效：{item.id}")
        if item.condition_set_id is not None and item.condition_set_id not in condition_ids:
            raise ValueError(f"事实项条件引用不存在：{item.id}")
        if item.value_type not in TYPED_VALUE_TYPES:
            raise ValueError(f"事实项值类型无效：{item.id}")
        slot = next(slot for slot in package.fact_slots if slot.id == item.slot_id)
        if slot.status in {"unknown", "not_collected", "not_applicable"}:
            raise ValueError(f"缺失事实不能包含事实项：{item.id}")
        if slot.value_type != item.value_type:
            raise ValueError(f"事实项与事实槽值类型不一致：{item.id}")
        if not typed_value_present(item):
            raise ValueError(f"事实项缺少类型化值：{item.id}")
        if sum(value is not None for value in (
            item.text_value, item.integer_value, item.real_value, item.boolean_value
        )) != 1:
            raise ValueError(f"事实项必须恰有一个类型化值：{item.id}")
        if not value_matches_type(item.value_type, item):
            raise ValueError(f"事实项值与类型不匹配：{item.id}")
    for evidence in package.evidence:
        if evidence.evidence_kind not in EVIDENCE_KINDS:
            raise ValueError(f"证据类型无效：{evidence.id}")
        if evidence.source_locator_id not in locator_ids:
            raise ValueError(f"证据定位引用不存在：{evidence.id}")
        if evidence.evidence_kind == "derived" and not evidence.transformation_rule:
            raise ValueError(f"派生证据缺少转换规则：{evidence.id}")
        if evidence.input_claim_id and evidence.input_claim_id not in (
            slot_ids | relation_ids | visual_ids | claim_ids
        ):
            raise ValueError(f"证据输入 claim 不存在：{evidence.id}")
    generated_visual_ids = {
        f"visual:{entity.id}"
        for entity in package.entities
        if (entity.id, "entity")
        not in {(visual.entity_id, visual.role) for visual in package.visuals}
    }
    valid_claims = {
        **{slot.id: "fact_slot" for slot in package.fact_slots},
        **{item.id: "fact_item" for item in package.fact_items},
        **{group.id: "relation_group" for group in package.relation_groups},
        **{relation.id: "relation" for relation in package.relations},
        **{visual.id: "visual" for visual in package.visuals},
        **{visual_id: "visual" for visual_id in generated_visual_ids},
        **{entity.id: "card" for entity in package.entities},
        **{card.entity_id: "card" for card in package.entity_cards},
        **{facet.id: "facet" for facet in package.facets},
    }
    for claim in package.claim_evidence:
        if claim.claim_type not in CLAIM_TYPES:
            raise ValueError(f"claim 类型无效：{claim.claim_id}")
        if (
            claim.evidence_id not in evidence_ids
            or valid_claims.get(claim.claim_id) != claim.claim_type
        ):
            raise ValueError(f"claim evidence 引用无效：{claim.claim_id}")
    relations_by_group: dict[str, list[Any]] = {}
    for relation in package.relations:
        relations_by_group.setdefault(relation.relation_group_id, []).append(relation)
    for group in package.relation_groups:
        if group.entity_id not in entity_ids or group.status not in VALID_FACT_STATUSES:
            raise ValueError(f"关系组无效：{group.id}")
        if group.condition_set_id and group.condition_set_id not in condition_ids:
            raise ValueError(f"关系组条件引用不存在：{group.id}")
        if group.status == "conditional" and not group.condition_set_id:
            raise ValueError(f"条件关系组缺少条件集合：{group.id}")
        if group.status in {"fixed", "conditional"} and not relations_by_group.get(group.id):
            raise ValueError(f"已知关系组缺少关系边：{group.id}")
        if (
            group.status in {"unknown", "not_collected", "not_applicable"}
            and relations_by_group.get(group.id)
        ):
            raise ValueError(f"缺失关系组不能包含关系边：{group.id}")
    for visual in package.visuals:
        if visual.entity_id not in entity_ids:
            raise ValueError(f"视觉实体引用不存在：{visual.id}")
        if visual.source_entity_id and visual.source_entity_id not in entity_ids:
            raise ValueError(f"视觉来源实体不存在：{visual.id}")
        if visual.role not in VISUAL_ROLES or visual.status not in VALID_VISUAL_STATUSES:
            raise ValueError(f"视觉状态或角色无效：{visual.id}")
        if visual.status == "proxy" and visual.role != "proxy":
            raise ValueError(f"代理视觉不能作为实体自身视觉：{visual.id}")
        if (
            visual.status in {"official_own", "official_reuse", "proxy"}
            and not visual.relative_path
        ):
            raise ValueError(f"视觉状态缺少资源路径：{visual.id}")
        if visual.relative_path and (
            not visual.sha256 or not HASH_PATTERN.fullmatch(visual.sha256)
        ):
            raise ValueError(f"视觉资源哈希无效：{visual.id}")
        if visual.status == "official_reuse" and (
            not visual.source_entity_id or not visual.reuse_reason
        ):
            raise ValueError(f"官方复用视觉缺少来源或理由：{visual.id}")
        if visual.status == "official_none" and any(
            value is not None
            for value in (visual.relative_path, visual.sha256, visual.source_entity_id)
        ):
            raise ValueError(f"官方无图视觉不应绑定资源：{visual.id}")
        if visual.status in {"official_own", "official_reuse", "proxy"} and (
            not visual.rule_version or not visual.crop_rect
        ):
            raise ValueError(f"发布视觉缺少裁切或规则绑定：{visual.id}")
        if visual.crop_rect:
            validate_crop_rect(visual.crop_rect, visual.id)
    for facet_group in package.facet_groups:
        if facet_group.entity_id not in entity_ids or facet_group.status not in VALID_FACT_STATUSES:
            raise ValueError(f"facet group 无效：{facet_group.id}")
    for facet in package.facets:
        if facet.value_type not in FACET_VALUE_TYPES:
            raise ValueError(f"facet 值类型无效：{facet.id}")
        if not facet_value_matches_type(facet):
            raise ValueError(f"facet 值与类型不匹配：{facet.id}")
        if facet.claim_status not in FACET_CLAIM_STATUSES:
            raise ValueError(f"facet claim 状态无效：{facet.id}")
        if facet.condition_set_id and facet.condition_set_id not in condition_ids:
            raise ValueError(f"facet 条件引用不存在：{facet.id}")
        if facet.scope_family.strip() == "" or facet.scope_id.strip() == "":
            raise ValueError(f"facet scope 无效：{facet.id}")
    relation_group_by_id = {group.id: group for group in package.relation_groups}
    for group in package.relation_groups:
        if group.condition_set_id:
            condition = next(
                (item for item in package.condition_sets if item.id == group.condition_set_id),
                None,
            )
            if condition is None:
                raise ValueError(f"关系组条件引用不存在：{group.id}")
            if group.status == "fixed" and condition.completeness != "complete":
                raise ValueError(f"固定关系组引用不完整条件：{group.id}")
    for relation in package.relations:
        if (
            relation.predicate not in VALID_RELATION_PREDICATES
            or not relation.original_direction.strip()
        ):
            raise ValueError(f"关系谓词或方向无效：{relation.id}")
        group = relation_group_by_id.get(relation.relation_group_id)
        if (
            group is None
            or relation.subject_entity_id != group.entity_id
            or relation.subject_entity_id not in entity_ids
            or relation.object_entity_id not in entity_ids
        ):
            raise ValueError(f"关系边引用不存在或主体不匹配：{relation.id}")
        if relation.condition_set_id and relation.condition_set_id not in condition_ids:
            raise ValueError(f"关系边条件引用不存在：{relation.id}")
        if relation.condition_set_id:
            condition = next(c for c in package.condition_sets if c.id == relation.condition_set_id)
            if group.status == "fixed" and condition.completeness != "complete":
                raise ValueError(f"固定关系引用不完整条件：{relation.id}")
    if publishable:
        generated_visuals = [
            visual
            for entity in package.entities
            for visual in (
                next(
                    (
                        candidate
                        for candidate in package.visuals
                        if candidate.entity_id == entity.id and candidate.role == "entity"
                    ),
                    None,
                )
                or Schema5Visual(
                    id=f"visual:{entity.id}",
                    entity_id=entity.id,
                    role="entity",
                    status=entity.visual_status,
                ),
            )
        ]
        if len(generated_visuals) != len(package.entities):
            raise ValueError("发布视觉实体覆盖不完整")
        if any(
            visual.status in {"official_own", "official_reuse", "proxy"}
            and (not visual.relative_path or not visual.sha256)
            for visual in generated_visuals
        ):
            raise ValueError("发布视觉内容绑定不完整")
        if any(
            visual.status in {"pending_review", "package_error"}
            for visual in generated_visuals
        ):
            raise ValueError("发布视觉状态未通过")
        if not package.fact_slots:
            raise ValueError("发布包缺少事实槽")
        covered_claims = {claim.claim_id for claim in package.claim_evidence}
        required_claims = {slot.id for slot in package.fact_slots}
        required_claims.update(item.id for item in package.fact_items)
        required_claims.update(group.id for group in package.relation_groups)
        required_claims.update(relation.id for relation in package.relations)
        required_claims.update(
            visual.id for visual in package.visuals
        )
        required_claims.update(
            f"visual:{entity.id}"
            for entity in package.entities
            if (entity.id, "entity") not in {
                (visual.entity_id, visual.role) for visual in package.visuals
            }
        )
        required_claims.update(entity.id for entity in package.entities)
        required_claims.update(card.entity_id for card in package.entity_cards)
        required_claims.update(facet.id for facet in package.facets)
        missing = sorted(required_claims - covered_claims)
        if missing:
            raise ValueError(f"发布 claim 缺少证据：{missing[0]}")
        from builder.pipeline.schema5_release import validate_release_coverage

        validate_release_coverage(package)


def validate_schema5_publish_quality(package: Schema5Package) -> None:
    invalid_translation = next(
        (
            entity.id
            for entity in package.entities
            if entity.translation_status in {"missing", "invalid", "unusable"}
        ),
        None,
    )
    if invalid_translation is not None:
        raise ValueError(f"发布实体翻译未通过：{invalid_translation}")
    if any(not entity.name_zh.strip() for entity in package.entities):
        raise ValueError("发布实体缺少中文名称")
    if any(
        entity.entity_type.strip() == "" or entity.id.split(":", 1)[0].strip() == ""
        for entity in package.entities
    ):
        raise ValueError("发布实体类型无效")


def validate_schema5_database_output(
    db_path: Path,
    output_dir: Path,
    manifest: dict[str, object],
    conformance: dict[str, object],
) -> None:
    """Revalidate a persisted publishable database before packaging it."""
    database = manifest.get("database")
    if not isinstance(database, dict) or database.get("sha256") != sha256_file(db_path):
        raise ValueError("schema 5 database 哈希与 manifest 不一致")
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise ValueError("schema 5 database 版本无效")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("schema 5 database 完整性校验失败")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("schema 5 database 外键校验失败")
        fingerprint = schema_fingerprint(connection)
        if manifest.get("schemaFingerprint") != fingerprint:
            raise ValueError("schema 5 schema fingerprint 不匹配")
        database = manifest.get("database")
        if not isinstance(database, dict) or database.get("schemaFingerprint") != fingerprint:
            raise ValueError("schema 5 database fingerprint 元数据不一致")
        meta = dict(connection.execute("SELECT key, value FROM build_meta").fetchall())
        expected_meta = {
            "schema_version": str(SCHEMA_VERSION),
            "manifest_version": str(MANIFEST_VERSION),
            "content_contract": CONTENT_CONTRACT,
        }
        if any(meta.get(key) != value for key, value in expected_meta.items()):
            raise ValueError("schema 5 build metadata 契约不一致")
        artifact_metadata = json.loads(meta.get("artifact_metadata", "{}"))
        if not isinstance(artifact_metadata, dict):
            raise ValueError("schema 5 artifact metadata 无效")
        if artifact_metadata.get("coverage") != manifest.get("coverage"):
            raise ValueError("schema 5 coverage 元数据不一致")
        if artifact_metadata.get("publishable") is not True:
            raise ValueError("schema 5 数据库 metadata 不可发布")
        capabilities = {
            (str(row["capability"]), str(row["requirement"]))
            for row in connection.execute(
                "SELECT capability, requirement FROM package_capabilities"
            )
        }
        manifest_capabilities = manifest.get("capabilities")
        if not isinstance(manifest_capabilities, dict):
            raise ValueError("schema 5 manifest capabilities 无效")
        expected_capabilities = {
            (str(capability), requirement)
            for requirement in ("required", "optional")
            for capability in manifest_capabilities.get(requirement, [])
        }
        if capabilities != expected_capabilities:
            raise ValueError("schema 5 capabilities 与数据库不一致")

        entity_ids = {str(row["id"]) for row in connection.execute("SELECT id FROM entities")}
        if len(entity_ids) != connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0]:
            raise ValueError("schema 5 entity ID 重复")
        content = manifest.get("content")
        if isinstance(content, dict) and content.get("entities") != len(entity_ids):
            raise ValueError("schema 5 manifest 实体覆盖不一致")
        condition_ids = {
            str(row["id"]) for row in connection.execute("SELECT id FROM condition_sets")
        }
        valid_completeness = {"complete", "partial", "opaque"}
        for row in connection.execute("SELECT id, completeness FROM condition_sets"):
            if row["completeness"] not in valid_completeness:
                raise ValueError(f"schema 5 条件完整性无效：{row['id']}")
        slot_rows = list(connection.execute("SELECT * FROM fact_slots"))
        slot_ids = {str(row["id"]) for row in slot_rows}
        slot_by_id = {str(row["id"]): row for row in slot_rows}
        valid_statuses = set(VALID_FACT_STATUSES)
        for row in slot_rows:
            if row["status"] not in valid_statuses or row["entity_id"] not in entity_ids:
                raise ValueError(f"schema 5 事实槽无效：{row['id']}")
            values = [
                row[key]
                for key in ("text_value", "integer_value", "real_value", "boolean_value")
            ]
            present = [value for value in values if value is not None]
            if row["value_type"] is not None and row["value_type"] not in TYPED_VALUE_TYPES:
                raise ValueError(f"schema 5 事实槽值类型无效：{row['id']}")
            if len(present) > 1:
                raise ValueError(f"schema 5 事实槽类型化值不唯一：{row['id']}")
            if row["status"] in {"unknown", "not_collected", "not_applicable"} and present:
                raise ValueError(f"schema 5 缺失事实携带值：{row['id']}")
            if present and not value_matches_database_type(row["value_type"], row):
                raise ValueError(f"schema 5 事实槽值与类型不匹配：{row['id']}")
            if row["condition_set_id"] is not None and row["condition_set_id"] not in condition_ids:
                raise ValueError(f"schema 5 事实槽条件不存在：{row['id']}")
        item_rows = list(connection.execute("SELECT * FROM fact_items"))
        item_ids = {str(row["id"]) for row in item_rows}
        for row in item_rows:
            slot = slot_by_id.get(str(row["slot_id"]))
            if slot is None or row["condition_set_id"] not in condition_ids | {None}:
                raise ValueError(f"schema 5 事实项引用无效：{row['id']}")
            if slot["status"] in {"unknown", "not_collected", "not_applicable"}:
                raise ValueError(f"schema 5 缺失事实包含事实项：{row['id']}")
            if (
                row["value_type"] not in TYPED_VALUE_TYPES
                or row["value_type"] != slot["value_type"]
            ):
                raise ValueError(f"schema 5 事实项与槽值类型不一致：{row['id']}")
            values = [
                row[key]
                for key in ("text_value", "integer_value", "real_value", "boolean_value")
            ]
            if sum(value is not None for value in values) != 1 or not value_matches_database_type(
                row["value_type"], row
            ):
                raise ValueError(f"schema 5 事实项类型化值无效：{row['id']}")
        relation_group_ids = {
            str(row["id"])
            for row in connection.execute("SELECT id FROM relation_groups")
        }
        relation_ids = {str(row["id"]) for row in connection.execute("SELECT id FROM relations")}
        visual_rows = list(connection.execute("SELECT * FROM visuals"))
        visual_ids = {str(row["id"]) for row in visual_rows}
        card_ids = {
            str(row["entity_id"])
            for row in connection.execute("SELECT entity_id FROM entity_cards")
        }
        facet_ids = {str(row["id"]) for row in connection.execute("SELECT id FROM browse_facets")}
        valid_claim_ids = (
            slot_ids
            | item_ids
            | relation_group_ids
            | relation_ids
            | visual_ids
            | card_ids
            | facet_ids
        )
        evidence_ids = {str(row["id"]) for row in connection.execute("SELECT id FROM evidence")}
        claim_rows = list(
            connection.execute("SELECT claim_id, claim_type, evidence_id FROM claim_evidence")
        )
        claims = {(str(row["claim_id"]), str(row["claim_type"])) for row in claim_rows}
        for row in claim_rows:
            if row["claim_id"] not in valid_claim_ids or row["evidence_id"] not in evidence_ids:
                raise ValueError(f"schema 5 claim evidence 引用无效：{row['claim_id']}")
        for row in connection.execute("SELECT id, input_claim_id FROM evidence"):
            if row["input_claim_id"] is not None and row["input_claim_id"] not in valid_claim_ids:
                raise ValueError(f"schema 5 evidence 输入 claim 不存在：{row['id']}")
        required_claims = {
            (claim_id, claim_type)
            for claim_id, claim_type in (
                *[(item, "fact_slot") for item in slot_ids],
                *[(item, "fact_item") for item in item_ids],
                *[(item, "relation_group") for item in relation_group_ids],
                *[(item, "relation") for item in relation_ids],
                *[(item, "visual") for item in visual_ids],
                *[(item, "card") for item in card_ids],
                *[(item, "facet") for item in facet_ids],
            )
        }
        if not required_claims.issubset(claims):
            raise ValueError("schema 5 发布 claim 证据覆盖不完整")
        for row in visual_rows:
            status = row["status"]
            if status in {"pending_review", "package_error"}:
                raise ValueError(f"schema 5 视觉状态未通过：{row['id']}")
            if status in {"official_own", "official_reuse", "proxy"}:
                relative_path = row["relative_path"]
                if not isinstance(relative_path, str) or not relative_path.strip():
                    raise ValueError(f"schema 5 视觉路径缺失：{row['id']}")
                path = (output_dir / relative_path).resolve()
                try:
                    path.relative_to(output_dir.resolve())
                except ValueError as exc:
                    raise ValueError(f"schema 5 视觉路径越界：{row['id']}") from exc
                if not path.is_file() or sha256_file(path) != row["sha256"]:
                    raise ValueError(f"schema 5 视觉哈希不匹配：{row['id']}")
    finally:
        connection.close()
    if conformance.get("schemaFingerprint") != manifest.get("schemaFingerprint"):
        raise ValueError("schema 5 conformance fingerprint 不一致")
    if (
        conformance.get("coverage") is not None
        and conformance.get("coverage") != manifest.get("coverage")
    ):
        raise ValueError("schema 5 conformance coverage 不一致")


def value_matches_database_type(value_type: str | None, row: sqlite3.Row) -> bool:
    columns = {
        "text": "text_value",
        "integer": "integer_value",
        "real": "real_value",
        "boolean": "boolean_value",
    }
    return value_type in columns and row[columns[value_type]] is not None


def value_matches_type(value_type: str | None, value: Any) -> bool:
    values = {
        "text": value.text_value,
        "integer": value.integer_value,
        "real": value.real_value,
        "boolean": value.boolean_value,
    }
    return value_type in values and values[value_type] is not None


def facet_value_matches_type(facet: Any) -> bool:
    typed_values = {
        "text": facet.text_value,
        "integer": facet.integer_value,
        "real": facet.real_value,
        "boolean": facet.boolean_value,
    }
    if facet.value_type == "range":
        return (
            facet.range_min is not None
            or facet.range_max is not None
        ) and all(
            value is None
            for value in (
                facet.text_value,
                facet.integer_value,
                facet.real_value,
                facet.boolean_value,
            )
        )
    if facet.value_type not in typed_values or typed_values[facet.value_type] is None:
        return False
    return sum(
        value is not None
        for value in (
            facet.text_value,
            facet.integer_value,
            facet.real_value,
            facet.boolean_value,
            facet.range_min,
            facet.range_max,
        )
    ) == 1


def validate_unique(rows: Iterable[tuple[Any, ...]]) -> None:
    values = list(rows)
    if len(set(values)) != len(values):
        raise ValueError("schema 5 稳定键重复")


def coverage_payload(package: Schema5Package) -> dict[str, object]:
    status_counts = {status: 0 for status in VALID_FACT_STATUSES}
    for slot in package.fact_slots:
        status_counts[slot.status] += 1
    condition_counts = {status: 0 for status in VALID_CONDITION_COMPLETENESS}
    for condition in package.condition_sets:
        condition_counts[condition.completeness] += 1
    return {
        "factSlots": {
            "answered": sum(
                status_counts[status] for status in ("fixed", "conditional", "dynamic_rule")
            ),
            "unknown": status_counts["unknown"],
            "notCollected": status_counts["not_collected"],
        },
        "conditions": condition_counts,
        "relations": {"groups": len(package.relation_groups), "edges": len(package.relations)},
        "visuals": {
            "pendingReview": sum(visual.status == "pending_review" for visual in package.visuals),
            "packageErrors": sum(visual.status == "package_error" for visual in package.visuals),
        },
    }


def insert_conditions(
    connection: sqlite3.Connection,
    condition_sets: list[Schema5ConditionSet],
    condition_terms: list[Schema5ConditionTerm],
) -> None:
    connection.executemany(
        """
        INSERT INTO condition_sets(id, completeness, player_summary, original_text)
        VALUES (?, ?, ?, ?)
        """,
        [
            (item.id, item.completeness, item.player_summary, item.original_text)
            for item in condition_sets
        ],
    )
    connection.executemany(
        """
        INSERT INTO condition_terms(
            id, condition_set_id, ordinal, kind, value_text, value_integer, value_real
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.id,
                item.condition_set_id,
                item.ordinal,
                item.kind,
                item.value_text,
                item.value_integer,
                item.value_real,
            )
            for item in condition_terms
        ],
    )


def validate_crop_rect(value: str, visual_id: str) -> None:
    try:
        rect = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"视觉裁切矩形格式无效：{visual_id}") from exc
    if (
        not isinstance(rect, list)
        or len(rect) != 4
        or not all(type(item) is int for item in rect)
        or rect[0] < 0
        or rect[1] < 0
        or rect[2] <= 0
        or rect[3] <= 0
    ):
        raise ValueError(f"视觉裁切矩形无效：{visual_id}")


def validate_source_document(document: Schema5SourceDocument) -> None:
    if document.source_kind == "supplemental":
        required = {
            "source_url": document.source_url,
            "revision": document.revision,
            "revision_at": document.revision_at,
            "game_version": document.game_version,
            "platform": document.platform,
            "language": document.language,
            "reviewed_at": document.reviewed_at,
        }
        if any(not isinstance(value, str) or not value.strip() for value in required.values()):
            raise ValueError(f"补充来源缺少版本、地址或审核信息：{document.id}")
        if document.review_status != "approved":
            raise ValueError(f"补充来源未通过审核：{document.id}")
        if document.conflict_status != "none":
            raise ValueError(f"补充来源存在冲突：{document.id}")
        if document.expires_at and parse_timestamp(document.expires_at) <= datetime.now(UTC):
            raise ValueError(f"补充来源已过期：{document.id}")
    elif document.review_status != "not_required" or document.conflict_status != "none":
        raise ValueError(f"官方来源不能携带补充审核或冲突状态：{document.id}")


def parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise ValueError(f"来源时间格式无效：{value}") from exc


def insert_sources(
    connection: sqlite3.Connection,
    documents: list[Schema5SourceDocument],
    locators: list[Schema5SourceLocator],
) -> None:
    connection.executemany(
        """
        INSERT INTO source_documents(
            id, source_kind, title, game_version, content_hash, revision,
            source_url, revision_at, platform, language, reviewed_at,
            review_status, expires_at, conflict_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.id,
                item.source_kind,
                item.title,
                item.game_version,
                item.content_hash,
                item.revision,
                item.source_url,
                item.revision_at,
                item.platform,
                item.language,
                item.reviewed_at,
                item.review_status,
                item.expires_at,
                item.conflict_status,
            )
            for item in documents
        ],
    )
    connection.executemany(
        """
        INSERT INTO source_locators(id, source_document_id, source_file, json_path, record_key)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (item.id, item.source_document_id, item.source_file, item.json_path, item.record_key)
            for item in locators
        ],
    )


def insert_fact_rows(
    connection: sqlite3.Connection,
    slots: list[Schema5FactSlot],
    items: list[Schema5FactItem],
) -> None:
    connection.executemany(
        """
        INSERT INTO fact_slots(
            id, entity_id, slot_key, status, value_type, text_value, integer_value,
            real_value, boolean_value, unit, condition_set_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.id,
                item.entity_id,
                item.slot_key,
                item.status,
                item.value_type,
                item.text_value,
                item.integer_value,
                item.real_value,
                None if item.boolean_value is None else int(item.boolean_value),
                item.unit,
                item.condition_set_id,
            )
            for item in slots
        ],
    )
    connection.executemany(
        """
        INSERT INTO fact_items(
            id, slot_id, ordinal, value_type, text_value, integer_value,
            real_value, boolean_value, unit, scope_id, condition_set_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.id,
                item.slot_id,
                item.ordinal,
                item.value_type,
                item.text_value,
                item.integer_value,
                item.real_value,
                None if item.boolean_value is None else int(item.boolean_value),
                item.unit,
                item.scope_id,
                item.condition_set_id,
            )
            for item in items
        ],
    )


def insert_evidence(
    connection: sqlite3.Connection,
    evidence: list[Schema5Evidence],
    claims: list[Schema5ClaimEvidence],
) -> None:
    connection.executemany(
        """
        INSERT INTO evidence(
            id, source_locator_id, evidence_kind, transformation_rule, input_claim_id
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                item.id,
                item.source_locator_id,
                item.evidence_kind,
                item.transformation_rule,
                item.input_claim_id,
            )
            for item in evidence
        ],
    )
    connection.executemany(
        "INSERT INTO claim_evidence(claim_id, evidence_id, claim_type) VALUES (?, ?, ?)",
        [(item.claim_id, item.evidence_id, item.claim_type) for item in claims],
    )


def insert_relations(
    connection: sqlite3.Connection, groups: list[Any], relations: list[Any]
) -> None:
    connection.executemany(
        """
        INSERT INTO relation_groups(id, entity_id, family, status, condition_set_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (item.id, item.entity_id, item.family, item.status, item.condition_set_id)
            for item in groups
        ],
    )
    connection.executemany(
        """
        INSERT INTO relations(
            id, relation_group_id, subject_entity_id, predicate, object_entity_id,
            original_direction, label, condition_set_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.id,
                item.relation_group_id,
                item.subject_entity_id,
                item.predicate,
                item.object_entity_id,
                item.original_direction,
                item.label,
                item.condition_set_id,
            )
            for item in relations
        ],
    )


def insert_facets(connection: sqlite3.Connection, groups: list[Any], facets: list[Any]) -> None:
    if groups:
        connection.executemany(
            "INSERT INTO browse_facet_groups(id, entity_id, family, status) VALUES (?, ?, ?, ?)",
            [(item.id, item.entity_id, item.family, item.status) for item in groups],
        )
    if facets:
        connection.executemany(
            """
            INSERT INTO browse_facets(
                id, group_id, scope_family, scope_id, value_type, text_value,
                integer_value, real_value, boolean_value, range_min, range_max, unit,
                claim_status, condition_set_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.id,
                    item.group_id,
                    item.scope_family,
                    item.scope_id,
                    item.value_type,
                    item.text_value,
                    item.integer_value,
                    item.real_value,
                    None if item.boolean_value is None else int(item.boolean_value),
                    item.range_min,
                    item.range_max,
                    item.unit,
                    item.claim_status,
                    item.condition_set_id,
                )
                for item in facets
            ],
        )


def insert_id_aliases(connection: sqlite3.Connection, aliases: list[Any]) -> None:
    if aliases:
        connection.executemany(
            "INSERT INTO id_aliases(alias_id, entity_id, reason) VALUES (?, ?, ?)",
            [(item.alias_id, item.entity_id, item.reason) for item in aliases],
        )
