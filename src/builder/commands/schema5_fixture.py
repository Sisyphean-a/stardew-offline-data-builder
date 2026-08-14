from __future__ import annotations

from pathlib import Path

from rich.console import Console

from builder.database.schema5 import write_schema5_fixture
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
from builder.pipeline.schema5_writer import write_schema5_package

console = Console()


def build_schema5_fixture_command(output: str) -> None:
    paths = write_schema5_fixture(Path(output))
    console.print(f"已生成 schema 5 conformance fixture：{paths['database']}")
    console.print(f"已生成 manifest 2：{paths['manifest']}")
    console.print("⚠ fixture 明确不可发布，不代表真实 v5 数据覆盖")


def build_schema5_b2_fixture_command(output: str) -> None:
    paths = write_schema5_package(Path(output), b2_fixture_package())
    console.print(f"已生成 schema 5 B2 typed fixture：{paths['database']}")
    console.print(f"已生成事实/条件/证据 manifest：{paths['manifest']}")
    console.print("⚠ fixture 明确不可发布，不代表真实 v5 数据覆盖")


def b2_fixture_package() -> Schema5Package:
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
                game_version="fixture",
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
        relation_groups=[
            Schema5RelationGroup(
                id="group:villager:Abigail:friendship",
                entity_id="villager:Abigail",
                family="friendship",
                status="fixed",
            )
        ],
        relations=[
            Schema5Relation(
                id="relation:villager:Abigail:friendship:object:1",
                relation_group_id="group:villager:Abigail:friendship",
                subject_entity_id="villager:Abigail",
                predicate="friendship",
                object_entity_id="object:1",
                original_direction="official",
                label="朋友",
            )
        ],
        visuals=[
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
        ],
        facet_groups=[
            Schema5FacetGroup(
                id="facet-group:object:1:season",
                entity_id="object:1",
                family="season",
                status="conditional",
            )
        ],
        facets=[
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
