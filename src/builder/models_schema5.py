from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from builder.pipeline.schema5_contract import (
    CONDITION_COMPLETENESS,
    FACT_STATUSES,
    RELATION_PREDICATES,
    VISUAL_STATUSES,
)


@dataclass(frozen=True)
class Schema5Entity:
    id: str
    entity_type: str
    name_zh: str
    name_en: str | None = None
    description_zh: str | None = None
    description_en: str | None = None
    game_id: str | None = None
    internal_name: str | None = None
    category: str | None = None
    translation_status: str = "complete"
    aliases: tuple[str, ...] = field(default_factory=tuple)
    action_summary_1: str | None = None
    action_summary_2: str | None = None
    sort_key: str | None = None
    visual_status: str = "official_none"
    visual_relative_path: str | None = None
    visual_sha256: str | None = None
    visual_source_entity_id: str | None = None
    visual_crop_rect: str | None = None
    visual_rule_version: str | None = None
    visual_reuse_reason: str | None = None


@dataclass(frozen=True)
class Schema5FactSlot:
    id: str
    entity_id: str
    slot_key: str
    status: str
    value_type: str | None = None
    text_value: str | None = None
    integer_value: int | None = None
    real_value: float | None = None
    boolean_value: bool | None = None
    unit: str | None = None
    condition_set_id: str | None = None


@dataclass(frozen=True)
class Schema5FactItem:
    id: str
    slot_id: str
    ordinal: int
    value_type: str
    text_value: str | None = None
    integer_value: int | None = None
    real_value: float | None = None
    boolean_value: bool | None = None
    unit: str | None = None
    scope_id: str | None = None
    condition_set_id: str | None = None


@dataclass(frozen=True)
class Schema5ConditionSet:
    id: str
    completeness: str
    player_summary: str | None = None
    original_text: str | None = None


@dataclass(frozen=True)
class Schema5ConditionTerm:
    id: str
    condition_set_id: str
    ordinal: int
    kind: str
    value_text: str | None = None
    value_integer: int | None = None
    value_real: float | None = None


@dataclass(frozen=True)
class Schema5SourceDocument:
    id: str
    source_kind: str
    title: str
    game_version: str | None = None
    content_hash: str | None = None
    revision: str | None = None
    source_url: str | None = None
    revision_at: str | None = None
    platform: str | None = None
    language: str | None = None
    reviewed_at: str | None = None
    review_status: str = "not_required"
    expires_at: str | None = None
    conflict_status: str = "none"


@dataclass(frozen=True)
class Schema5SourceLocator:
    id: str
    source_document_id: str
    source_file: str | None = None
    json_path: str | None = None
    record_key: str | None = None


@dataclass(frozen=True)
class Schema5Evidence:
    id: str
    source_locator_id: str
    evidence_kind: str
    transformation_rule: str | None = None
    input_claim_id: str | None = None


@dataclass(frozen=True)
class Schema5ClaimEvidence:
    claim_id: str
    evidence_id: str
    claim_type: str


@dataclass(frozen=True)
class Schema5RelationGroup:
    id: str
    entity_id: str
    family: str
    status: str
    condition_set_id: str | None = None


@dataclass(frozen=True)
class Schema5Relation:
    id: str
    relation_group_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str
    original_direction: str
    label: str | None = None
    condition_set_id: str | None = None


@dataclass(frozen=True)
class Schema5Visual:
    id: str
    entity_id: str
    role: str
    status: str
    relative_path: str | None = None
    sha256: str | None = None
    source_entity_id: str | None = None
    crop_rect: str | None = None
    rule_version: str | None = None
    reuse_reason: str | None = None


@dataclass(frozen=True)
class Schema5EntityCard:
    entity_id: str
    identity_summary: str | None = None
    action_summary_1: str | None = None
    action_summary_2: str | None = None
    category_label: str | None = None
    sort_key: str = ""


@dataclass(frozen=True)
class Schema5FacetGroup:
    id: str
    entity_id: str
    family: str
    status: str


@dataclass(frozen=True)
class Schema5Facet:
    id: str
    group_id: str
    scope_family: str
    scope_id: str
    value_type: str
    text_value: str | None = None
    integer_value: int | None = None
    real_value: float | None = None
    boolean_value: bool | None = None
    range_min: float | None = None
    range_max: float | None = None
    unit: str | None = None
    claim_status: str = "fixed"
    condition_set_id: str | None = None


@dataclass(frozen=True)
class Schema5IdAlias:
    alias_id: str
    entity_id: str
    reason: str


@dataclass
class Schema5Package:
    entities: list[Schema5Entity] = field(default_factory=list)
    fact_slots: list[Schema5FactSlot] = field(default_factory=list)
    fact_items: list[Schema5FactItem] = field(default_factory=list)
    condition_sets: list[Schema5ConditionSet] = field(default_factory=list)
    condition_terms: list[Schema5ConditionTerm] = field(default_factory=list)
    source_documents: list[Schema5SourceDocument] = field(default_factory=list)
    source_locators: list[Schema5SourceLocator] = field(default_factory=list)
    evidence: list[Schema5Evidence] = field(default_factory=list)
    claim_evidence: list[Schema5ClaimEvidence] = field(default_factory=list)
    relation_groups: list[Schema5RelationGroup] = field(default_factory=list)
    relations: list[Schema5Relation] = field(default_factory=list)
    visuals: list[Schema5Visual] = field(default_factory=list)
    entity_cards: list[Schema5EntityCard] = field(default_factory=list)
    facet_groups: list[Schema5FacetGroup] = field(default_factory=list)
    facets: list[Schema5Facet] = field(default_factory=list)
    id_aliases: list[Schema5IdAlias] = field(default_factory=list)
    # Build-only audit rows; they are emitted into reports, never into the public DB API.
    shop_price_diagnostics: list[dict[str, object]] = field(default_factory=list)
    gift_reference_diagnostics: list[dict[str, object]] = field(default_factory=list)


# These aliases make protocol closure visible to callers without duplicating the
# string literals in each producer.
VALID_FACT_STATUSES = set(FACT_STATUSES)
VALID_RELATION_PREDICATES = set(RELATION_PREDICATES)
VALID_VISUAL_STATUSES = set(VISUAL_STATUSES)
VALID_CONDITION_COMPLETENESS = set(CONDITION_COMPLETENESS)


def typed_value_present(value: Any) -> bool:
    return any(
        value is not None
        for value in (value.text_value, value.integer_value, value.real_value, value.boolean_value)
    )
