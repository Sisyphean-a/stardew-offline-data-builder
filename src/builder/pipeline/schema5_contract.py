from __future__ import annotations

"""Shared constants for the player-facts-v1 staging contract.

The v4 pipeline intentionally remains available while the migration slices are
being delivered.  Anything written through this module is explicitly schema 5
and must not be interpreted by the v4 ``extra_json`` reader.
"""

SCHEMA_VERSION = 5
MANIFEST_VERSION = 2
CONTENT_CONTRACT = "player-facts-v1"

# Capability names are stable protocol identifiers, not implementation module names.
REQUIRED_CAPABILITIES = (
    "entities",
    "fact-slots",
    "relations",
    "conditions",
    "evidence",
    "visuals",
    "entity-cards",
    "browse-facets",
    "search",
    "id-aliases",
)
OPTIONAL_CAPABILITIES = ("supplemental-facts",)

FACT_STATUSES = (
    "fixed",
    "conditional",
    "dynamic_rule",
    "unknown",
    "not_collected",
    "not_applicable",
)
CONDITION_COMPLETENESS = ("complete", "partial", "opaque")
VISUAL_STATUSES = (
    "official_own",
    "official_reuse",
    "official_none",
    "proxy",
    "pending_review",
    "package_error",
)
VISUAL_ROLES = ("entity", "proxy")
SOURCE_KINDS = (
    "official_direct",
    "official_derived",
    "supplemental",
    "display_override",
)
EVIDENCE_KINDS = ("direct", "derived", "supplemental", "override")
CLAIM_TYPES = ("fact_slot", "fact_item", "relation_group", "relation", "visual", "card", "facet")
FACET_VALUE_TYPES = ("text", "integer", "real", "boolean", "range")
FACET_CLAIM_STATUSES = ("fixed", "conditional", "dynamic_rule")
TYPED_VALUE_TYPES = ("text", "integer", "real", "boolean")
RELATION_PREDICATES = (
    "kinship",
    "friendship",
    "friendship_unspecified",
    "guardianship",
    "cohabitation",
    "love_interest_pointer",
)


def validate_capabilities(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError("capabilities 必须是对象")
    required = value.get("required")
    optional = value.get("optional")
    if not isinstance(required, list) or not all(
        isinstance(item, str) and item for item in required
    ):
        raise ValueError("capabilities.required 无效")
    if not isinstance(optional, list) or not all(
        isinstance(item, str) and item for item in optional
    ):
        raise ValueError("capabilities.optional 无效")
    if set(required) & set(optional):
        raise ValueError("capabilities 不能同时声明 required 和 optional")
    known = set(REQUIRED_CAPABILITIES) | set(OPTIONAL_CAPABILITIES)
    if any(item not in known for item in required):
        raise ValueError("包含未知必需能力")
    if not set(REQUIRED_CAPABILITIES).issubset(required):
        raise ValueError("缺少必需能力")
    return {"required": sorted(set(required)), "optional": sorted(set(optional))}


def capabilities_payload(
    required: tuple[str, ...] = REQUIRED_CAPABILITIES,
    optional: tuple[str, ...] = OPTIONAL_CAPABILITIES,
) -> dict[str, list[str]]:
    return {
        "required": sorted(set(required)),
        "optional": sorted(set(optional)),
    }
