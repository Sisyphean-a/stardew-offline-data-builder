from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from builder.models_schema5 import (
    Schema5ClaimEvidence,
    Schema5ConditionSet,
    Schema5ConditionTerm,
    Schema5Entity,
    Schema5Evidence,
    Schema5Facet,
    Schema5FacetGroup,
    Schema5FactItem,
    Schema5FactSlot,
    Schema5Package,
    Schema5Relation,
    Schema5RelationGroup,
    Schema5SourceDocument,
    Schema5SourceLocator,
    Schema5Visual,
)
from builder.pipeline.schema5_writer import validate_schema5_package, write_schema5_package


def b2_package() -> Schema5Package:
    return Schema5Package(
        entities=[
            Schema5Entity(
                id="object:1",
                entity_type="object",
                game_id="1",
                name_zh="测试物品",
                action_summary_1="用于测试",
            ),
            Schema5Entity(
                id="villager:Abigail",
                entity_type="villager",
                game_id="Abigail",
                name_zh="阿比盖尔",
            ),
        ],
        condition_sets=[
            Schema5ConditionSet(
                id="condition:object:1:availability",
                completeness="partial",
                player_summary="春季可获得",
                original_text="spring",
            )
        ],
        condition_terms=[
            Schema5ConditionTerm(
                id="term:object:1:availability:0",
                condition_set_id="condition:object:1:availability",
                ordinal=0,
                kind="season",
                value_text="spring",
            )
        ],
        source_documents=[
            Schema5SourceDocument(
                id="document:data-objects",
                source_kind="official_direct",
                title="Objects.json",
                game_version="1.6",
            )
        ],
        source_locators=[
            Schema5SourceLocator(
                id="locator:data-objects:1",
                source_document_id="document:data-objects",
                source_file="Data/Objects.json",
                json_path='$."1"',
                record_key="1",
            )
        ],
        fact_slots=[
            Schema5FactSlot(
                id="fact:object:1:name",
                entity_id="object:1",
                slot_key="name",
                status="fixed",
                value_type="text",
                text_value="测试物品",
            ),
            Schema5FactSlot(
                id="fact:object:1:availability",
                entity_id="object:1",
                slot_key="availability",
                status="conditional",
                value_type="text",
                text_value="春季",
                condition_set_id="condition:object:1:availability",
            ),
            Schema5FactSlot(
                id="fact:villager:Abigail:relationship",
                entity_id="villager:Abigail",
                slot_key="relationship",
                status="unknown",
            ),
        ],
        fact_items=[
            Schema5FactItem(
                id="item:object:1:availability:0",
                slot_id="fact:object:1:availability",
                ordinal=0,
                value_type="text",
                text_value="春季",
                scope_id="availability:object:1",
            )
        ],
        evidence=[
            Schema5Evidence(
                id="evidence:object:1:name",
                source_locator_id="locator:data-objects:1",
                evidence_kind="direct",
            ),
            Schema5Evidence(
                id="evidence:object:1:availability",
                source_locator_id="locator:data-objects:1",
                evidence_kind="derived",
                transformation_rule="official-record-to-availability-v1",
                input_claim_id="fact:object:1:name",
            ),
        ],
        claim_evidence=[
            Schema5ClaimEvidence(
                claim_id="fact:object:1:name",
                evidence_id="evidence:object:1:name",
                claim_type="fact_slot",
            ),
            Schema5ClaimEvidence(
                claim_id="fact:object:1:availability",
                evidence_id="evidence:object:1:availability",
                claim_type="fact_slot",
            ),
        ],
    )


def test_b2_writes_typed_facts_conditions_and_evidence(tmp_path: Path) -> None:
    paths = write_schema5_package(tmp_path / "b2", b2_package())
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    connection = sqlite3.connect(paths["database"])
    try:
        status = connection.execute(
            "SELECT status FROM fact_slots WHERE id = ?",
            ("fact:object:1:availability",),
        ).fetchone()[0]
        assert status == "conditional"
        completeness = connection.execute(
            "SELECT completeness FROM condition_sets"
        ).fetchone()[0]
        assert completeness == "partial"
        rule = connection.execute(
            "SELECT transformation_rule FROM evidence WHERE evidence_kind = 'derived'"
        ).fetchone()[0]
        assert rule == "official-record-to-availability-v1"
        assert connection.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        connection.close()
    assert manifest["coverage"]["factSlots"] == {"answered": 2, "unknown": 1, "notCollected": 0}
    assert manifest["coverage"]["relations"] == {"groups": 0, "edges": 0}
    assert manifest["publishable"] is False


def test_b2_rejects_fixed_fact_with_partial_condition() -> None:
    package = b2_package()
    package.fact_slots[1] = package.fact_slots[1].__class__(
        **{**package.fact_slots[1].__dict__, "status": "fixed"}
    )

    with pytest.raises(ValueError, match="固定事实引用不完整条件"):
        validate_schema5_package(package, publishable=False)


def test_b2_rejects_dynamic_fact_without_explanatory_rule() -> None:
    package = b2_package()
    package.fact_slots[0] = replace(
        package.fact_slots[0],
        status="dynamic_rule",
        text_value=None,
    )

    with pytest.raises(ValueError, match="动态事实缺少可解释规则"):
        validate_schema5_package(package, publishable=False)


def test_b2_allows_dynamic_fact_with_companion_rule() -> None:
    package = b2_package()
    package.fact_slots[0] = replace(
        package.fact_slots[0],
        status="dynamic_rule",
        text_value=None,
    )
    package.fact_slots.append(
        Schema5FactSlot(
            id="fact:object:1:name_rule",
            entity_id="object:1",
            slot_key="name_rule",
            status="dynamic_rule",
            value_type="text",
            text_value="按运行时规则确定",
        )
    )
    package.evidence.append(
        Schema5Evidence(
            id="evidence:object:1:name-rule",
            source_locator_id="locator:data-objects:1",
            evidence_kind="derived",
            transformation_rule="official-runtime-rule-v1",
            input_claim_id="fact:object:1:name",
        )
    )
    package.claim_evidence.append(
        Schema5ClaimEvidence(
            claim_id="fact:object:1:name_rule",
            evidence_id="evidence:object:1:name-rule",
            claim_type="fact_slot",
        )
    )
    validate_schema5_package(package, publishable=False)


def test_b2_rejects_publishable_fact_without_evidence() -> None:
    package = b2_package()
    package.claim_evidence = package.claim_evidence[:1]

    with pytest.raises(ValueError, match="发布 claim 缺少证据"):
        validate_schema5_package(package, publishable=True)


def test_b2_rejects_fact_item_on_unknown_slot() -> None:
    package = b2_package()
    package.fact_items[0] = package.fact_items[0].__class__(
        **{**package.fact_items[0].__dict__, "slot_id": "fact:villager:Abigail:relationship"}
    )

    with pytest.raises(ValueError, match="缺失事实不能包含事实项"):
        validate_schema5_package(package, publishable=False)


def test_b2_rejects_fact_item_without_typed_value() -> None:
    package = b2_package()
    package.fact_items[0] = package.fact_items[0].__class__(
        **{**package.fact_items[0].__dict__, "text_value": None}
    )

    with pytest.raises(ValueError, match="事实项缺少类型化值"):
        validate_schema5_package(package, publishable=False)


def test_b2_rejects_relation_subject_mismatch() -> None:
    package = b2_package()
    package.relation_groups = [
        Schema5RelationGroup(
            id="group:abigail:friendship",
            entity_id="villager:Abigail",
            family="friendship",
            status="fixed",
        )
    ]
    package.relations = [
        Schema5Relation(
            id="relation:wrong-subject",
            relation_group_id="group:abigail:friendship",
            subject_entity_id="object:1",
            predicate="friendship",
            object_entity_id="villager:Abigail",
            original_direction="official",
        )
    ]

    with pytest.raises(ValueError, match="关系边"):
        validate_schema5_package(package, publishable=False)


def publishable_b2_package() -> Schema5Package:
    package = b2_package()
    package.condition_sets[0] = Schema5ConditionSet(
        id=package.condition_sets[0].id,
        completeness="complete",
        player_summary=package.condition_sets[0].player_summary,
        original_text=None,
    )
    package.fact_slots[2] = package.fact_slots[2].__class__(
        **{**package.fact_slots[2].__dict__, "status": "not_collected"}
    )
    package.fact_items = []
    for claim_id, claim_type in (
        ("fact:villager:Abigail:relationship", "fact_slot"),
        ("visual:object:1", "visual"),
        ("visual:villager:Abigail", "visual"),
        ("object:1", "card"),
        ("villager:Abigail", "card"),
    ):
        evidence_id = f"evidence:{claim_type}:{claim_id}"
        package.evidence.append(
            Schema5Evidence(
                id=evidence_id,
                source_locator_id="locator:data-objects:1",
                evidence_kind="direct",
            )
        )
        package.claim_evidence.append(
            Schema5ClaimEvidence(
                claim_id=claim_id,
                evidence_id=evidence_id,
                claim_type=claim_type,
            )
        )
    return package


def test_b2_allows_publishable_not_collected_slot_when_covered() -> None:
    validate_schema5_package(publishable_b2_package(), publishable=True)


def test_b2_rejects_duplicate_visual_role() -> None:
    package = b2_package()
    package.visuals = [
        Schema5Visual(
            id="visual:object:1:entity",
            entity_id="object:1",
            role="entity",
            status="official_none",
        ),
        Schema5Visual(
            id="visual:object:1:proxy",
            entity_id="object:1",
            role="entity",
            status="official_none",
        ),
    ]

    with pytest.raises(ValueError, match="稳定键重复"):
        validate_schema5_package(package, publishable=False)


def test_b2_rejects_visual_resource_without_hash() -> None:
    package = b2_package()
    package.visuals = [
        Schema5Visual(
            id="visual:object:1:entity",
            entity_id="object:1",
            role="entity",
            status="official_own",
            relative_path="images/object.webp",
            crop_rect="0,0,16,16",
            rule_version="fixture-v1",
        )
    ]

    with pytest.raises(ValueError, match="视觉资源哈希无效"):
        validate_schema5_package(package, publishable=False)


def test_b2_rejects_publishable_visual_without_evidence() -> None:
    package = b2_package()
    package.visuals = [
        Schema5Visual(
            id="visual:object:1:entity",
            entity_id="object:1",
            role="entity",
            status="pending_review",
        )
    ]

    with pytest.raises(ValueError, match="发布视觉状态未通过"):
        validate_schema5_package(package, publishable=True)


def test_b2_rejects_value_type_mismatch() -> None:
    package = b2_package()
    package.fact_slots[0] = package.fact_slots[0].__class__(
        **{**package.fact_slots[0].__dict__, "value_type": "integer"}
    )

    with pytest.raises(ValueError, match="事实槽值与类型不匹配"):
        validate_schema5_package(package, publishable=False)


def test_b2_rejects_publishable_invalid_translation() -> None:
    package = b2_package()
    package.entities[0] = package.entities[0].__class__(
        **{**package.entities[0].__dict__, "translation_status": "missing"}
    )

    with pytest.raises(ValueError, match="发布实体翻译未通过"):
        validate_schema5_package(package, publishable=True)


def test_b2_rejects_derived_evidence_without_transformation() -> None:
    package = b2_package()
    package.evidence[1] = replace(package.evidence[1], transformation_rule=None)

    with pytest.raises(ValueError, match="派生证据缺少转换规则"):
        validate_schema5_package(package, publishable=False)


def test_b3_accepts_directional_relation_visual_and_scoped_facet() -> None:
    package = b2_package()
    package.relation_groups = [
        Schema5RelationGroup(
            id="group:villager:Abigail:friendship",
            entity_id="villager:Abigail",
            family="friendship",
            status="fixed",
        )
    ]
    package.relations = [
        Schema5Relation(
            id="relation:villager:Abigail:friendship:object:1",
            relation_group_id="group:villager:Abigail:friendship",
            subject_entity_id="villager:Abigail",
            predicate="friendship",
            object_entity_id="object:1",
            original_direction="official",
            label="朋友",
        )
    ]
    package.visuals = [
        Schema5Visual(
            id="visual:object:1:entity",
            entity_id="object:1",
            role="entity",
            status="official_none",
        ),
        Schema5Visual(
            id="visual:villager:Abigail:entity",
            entity_id="villager:Abigail",
            role="entity",
            status="official_none",
        ),
    ]
    package.facet_groups = [
        Schema5FacetGroup(
            id="facet-group:object:1:season",
            entity_id="object:1",
            family="season",
            status="conditional",
        )
    ]
    package.facets = [
        Schema5Facet(
            id="facet:object:1:season:spring",
            group_id="facet-group:object:1:season",
            scope_family="availability",
            scope_id="availability:object:1",
            value_type="text",
            text_value="春季",
            claim_status="conditional",
            condition_set_id="condition:object:1:availability",
        )
    ]
    validate_schema5_package(package, publishable=False)


def test_b3_allows_approved_supplemental_source() -> None:
    package = b2_package()
    package.source_documents[0] = replace(
        package.source_documents[0],
        source_kind="supplemental",
        source_url="https://example.test/fact",
        revision="rev-1",
        revision_at="2026-08-01T00:00:00Z",
        game_version="1.6.15",
        platform="pc",
        language="zh-CN",
        reviewed_at="2026-08-02T00:00:00Z",
        review_status="approved",
    )
    validate_schema5_package(package, publishable=False)


def test_b3_rejects_expired_supplemental_source() -> None:
    package = b2_package()
    package.source_documents[0] = replace(
        package.source_documents[0],
        source_kind="supplemental",
        source_url="https://example.test/fact",
        revision="rev-1",
        revision_at="2026-08-01T00:00:00Z",
        game_version="1.6.15",
        platform="pc",
        language="zh-CN",
        reviewed_at="2026-08-02T00:00:00Z",
        review_status="approved",
        expires_at="2020-01-01T00:00:00Z",
    )

    with pytest.raises(ValueError, match="补充来源已过期"):
        validate_schema5_package(package, publishable=False)


def test_b3_rejects_conflicted_supplemental_source() -> None:
    package = b2_package()
    package.source_documents[0] = replace(
        package.source_documents[0],
        source_kind="supplemental",
        source_url="https://example.test/fact",
        revision="rev-1",
        revision_at="2026-08-01T00:00:00Z",
        game_version="1.6.15",
        platform="pc",
        language="zh-CN",
        reviewed_at="2026-08-02T00:00:00Z",
        review_status="approved",
        conflict_status="conflict",
    )

    with pytest.raises(ValueError, match="补充来源存在冲突"):
        validate_schema5_package(package, publishable=False)


def test_b3_rejects_missing_relation_direction_and_edges_on_unknown_group() -> None:
    package = b2_package()
    package.relation_groups = [
        Schema5RelationGroup(
            id="group:abigail:friendship",
            entity_id="villager:Abigail",
            family="friendship",
            status="unknown",
        )
    ]
    package.relations = [
        Schema5Relation(
            id="relation:unknown-group-edge",
            relation_group_id="group:abigail:friendship",
            subject_entity_id="villager:Abigail",
            predicate="friendship",
            object_entity_id="object:1",
            original_direction="official",
        )
    ]

    with pytest.raises(ValueError, match="缺失关系组不能包含关系边"):
        validate_schema5_package(package, publishable=False)


def test_b3_rejects_proxy_as_entity_visual_and_missing_reuse_reason() -> None:
    package = b2_package()
    package.visuals = [
        Schema5Visual(
            id="visual:object:1:entity",
            entity_id="object:1",
            role="entity",
            status="proxy",
            relative_path="images/object.webp",
            sha256="a" * 64,
            crop_rect="0,0,16,16",
            rule_version="fixture-v1",
        )
    ]
    with pytest.raises(ValueError, match="代理视觉不能作为实体自身视觉"):
        validate_schema5_package(package, publishable=False)

    package.visuals = [
        Schema5Visual(
            id="visual:object:1:entity",
            entity_id="object:1",
            role="entity",
            status="official_reuse",
            relative_path="images/object.webp",
            sha256="a" * 64,
            source_entity_id="villager:Abigail",
            crop_rect="0,0,16,16",
            rule_version="fixture-v1",
        )
    ]
    with pytest.raises(ValueError, match="官方复用视觉缺少来源或理由"):
        validate_schema5_package(package, publishable=False)
