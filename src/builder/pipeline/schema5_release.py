from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from builder.models_schema5 import (
    Schema5ClaimEvidence,
    Schema5Evidence,
    Schema5FactSlot,
    Schema5Package,
)
from builder.pipeline.schema5_projection import stable_part

# These are the player-facing answer slots that the formal candidate must make
# explicit.  A source-backed not_collected row is valid; silently omitting the
# question is not.
CORE_FACT_SLOTS: dict[str, tuple[str, ...]] = {
    "object": ("sell_price",),
    "mineral": ("sell_price",),
    "ring": ("sell_price",),
    "crop": (
        "seasons",
        "first_harvest_days",
        "regrow_days",
        "needs_watering",
        "seed_item_id",
        "harvest_item_id",
        "sell_price",
        "seed_purchase_price",
    ),
    "fish": (
        "difficulty",
        "behavior",
        "min_size",
        "max_size",
        "fishing_time",
        "seasons",
        "weather",
        "sell_price",
        "fishing_locations",
    ),
    "villager": ("residence_region", "birthday", "gender", "can_be_romanced"),
    "big_craftable": ("purchase_price", "crafting_material_id", "crafting_material_quantity"),
    "tool": ("purchase_price", "upgrade_material_id", "upgrade_price"),
    "weapon": ("sell_price", "purchase_price", "acquisition"),
    "monster": ("locations", "drops"),
}


P0_CORE_SLOTS = {
    "fishing_locations",
    "fishing_time",
    "locations",
    "sell_price",
    "purchase_price",
    "seed_purchase_price",
    "crafting_material_id",
    "crafting_material_quantity",
    "upgrade_material_id",
    "upgrade_price",
    "acquisition",
    "drops",
}
STABLE_DIRECT_SLOTS = {
    "sell_price",
    "difficulty",
    "behavior",
    "min_size",
    "max_size",
    "fishing_time",
    "seasons",
    "weather",
    "first_harvest_days",
    "regrow_days",
    "needs_watering",
    "seed_item_id",
    "harvest_item_id",
    "residence_region",
    "birthday",
    "gender",
    "can_be_romanced",
}


def ensure_core_fact_slots(package: Schema5Package) -> None:
    """Materialize every registered player question with auditable evidence."""
    existing = {(slot.entity_id, slot.slot_key) for slot in package.fact_slots}
    locators_by_entity = _entity_locators(package)
    evidence_ids = {evidence.id for evidence in package.evidence}
    claims = {(claim.claim_id, claim.claim_type) for claim in package.claim_evidence}
    for entity in package.entities:
        locator_id = locators_by_entity.get(entity.id)
        if locator_id is None:
            raise ValueError(f"核心事实缺少实体来源定位：{entity.id}")
        for slot_key in CORE_FACT_SLOTS.get(entity.entity_type, ()):
            if (entity.id, slot_key) in existing:
                continue
            slot_id = f"fact:{entity.id}:{slot_key}"
            package.fact_slots.append(
                Schema5FactSlot(
                    id=slot_id,
                    entity_id=entity.id,
                    slot_key=slot_key,
                    status="not_collected",
                    value_type=None,
                )
            )
            evidence_id = f"evidence:fact-slot:{stable_part(slot_id)}"
            if evidence_id not in evidence_ids:
                package.evidence.append(
                    Schema5Evidence(
                        id=evidence_id,
                        source_locator_id=locator_id,
                        evidence_kind="direct",
                    )
                )
                evidence_ids.add(evidence_id)
            claim_key = (slot_id, "fact_slot")
            if claim_key not in claims:
                package.claim_evidence.append(
                    Schema5ClaimEvidence(slot_id, evidence_id, "fact_slot")
                )
                claims.add(claim_key)
            existing.add((entity.id, slot_key))


def validate_core_coverage(package: Schema5Package) -> dict[str, object]:
    """Apply the per-category coverage thresholds before a package is publishable."""
    by_key: dict[tuple[str, str], list[Schema5FactSlot]] = {}
    entity_types = {entity.id: entity.entity_type for entity in package.entities}
    for slot in package.fact_slots:
        entity_type = entity_types.get(slot.entity_id)
        if entity_type in CORE_FACT_SLOTS:
            by_key.setdefault((entity_type, slot.slot_key), []).append(slot)
    rows: dict[str, dict[str, object]] = {}
    failures: list[str] = []
    for entity_type, slot_keys in CORE_FACT_SLOTS.items():
        for slot_key in slot_keys:
            key = (entity_type, slot_key)
            slots = by_key.get(key, [])
            eligible = [slot for slot in slots if slot.status != "not_applicable"]
            answered = sum(
                slot.status in {"fixed", "conditional", "dynamic_rule"}
                for slot in eligible
            )
            unknown = sum(slot.status == "unknown" for slot in eligible)
            not_collected = sum(slot.status == "not_collected" for slot in eligible)
            denominator = len(eligible)
            answered_rate = answered / denominator if denominator else 1.0
            not_collected_rate = not_collected / denominator if denominator else 0.0
            threshold = 1.0 if slot_key in STABLE_DIRECT_SLOTS else (
                0.95 if slot_key in P0_CORE_SLOTS else 0.85
            )
            max_not_collected = 0.0 if slot_key in STABLE_DIRECT_SLOTS else (
                0.02 if slot_key in P0_CORE_SLOTS else 0.10
            )
            rows[f"{entity_type}:{slot_key}"] = {
                "eligible": denominator,
                "answered": answered,
                "unknown": unknown,
                "notCollected": not_collected,
                "answeredRate": round(answered_rate, 6),
                "notCollectedRate": round(not_collected_rate, 6),
                "minimumAnsweredRate": threshold,
                "maximumNotCollectedRate": max_not_collected,
            }
            if denominator and (
                answered_rate < threshold or not_collected_rate > max_not_collected
            ):
                failures.append(
                    f"{entity_type}:{slot_key} answered={answered_rate:.3f} "
                    f"not_collected={not_collected_rate:.3f}"
                )
    if failures:
        raise ValueError(f"核心事实覆盖未达发布门槛：{failures[0]}")
    return {"bySlot": dict(sorted(rows.items()))}


def validate_release_coverage(package: Schema5Package) -> dict[str, object]:
    core = validate_core_coverage(package)
    groups = [group for group in package.relation_groups if group.status != "not_applicable"]
    answered_groups = sum(
        group.status in {"fixed", "conditional", "dynamic_rule"} for group in groups
    )
    not_collected_groups = sum(group.status == "not_collected" for group in groups)
    group_denominator = len(groups)
    group_answered_rate = answered_groups / group_denominator if group_denominator else 1.0
    group_not_collected_rate = (
        not_collected_groups / group_denominator if group_denominator else 0.0
    )
    if group_denominator and (group_answered_rate < 0.90 or group_not_collected_rate > 0.05):
        raise ValueError(
            "人物关系组覆盖未达发布门槛："
            f"answered={group_answered_rate:.3f} not_collected={group_not_collected_rate:.3f}"
        )
    condition_counts = {
        completeness: sum(
            condition.completeness == completeness for condition in package.condition_sets
        )
        for completeness in ("complete", "partial", "opaque")
    }
    condition_total = sum(condition_counts.values())
    complete_rate = condition_counts["complete"] / condition_total if condition_total else 1.0
    opaque_rate = condition_counts["opaque"] / condition_total if condition_total else 0.0
    if condition_total and (complete_rate < 0.95 or opaque_rate > 0.01):
        raise ValueError(
            "条件完整性未达发布门槛："
            f"complete={complete_rate:.3f} opaque={opaque_rate:.3f}"
        )
    return {
        "core": core,
        "relationGroups": {
            "eligible": group_denominator,
            "answered": answered_groups,
            "notCollected": not_collected_groups,
            "answeredRate": round(group_answered_rate, 6),
            "notCollectedRate": round(group_not_collected_rate, 6),
        },
        "conditions": {
            **condition_counts,
            "completeRate": round(complete_rate, 6),
            "opaqueRate": round(opaque_rate, 6),
        },
    }


def validate_regression_budget(
    previous_output: Path,
    current: dict[str, object],
    current_package: Schema5Package | None = None,
) -> None:
    """Reject unexplained typed-projection loss versus the previous candidate."""
    comparison_output = previous_output
    manifest_path = comparison_output / "manifest.json"
    if not manifest_path.is_file():
        comparison_output = previous_output.with_name(f"{previous_output.name}.previous")
        manifest_path = comparison_output / "manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("上一候选 manifest 无法读取，拒绝开放回归门禁") from exc
    if not isinstance(manifest, dict):
        raise ValueError("上一候选 manifest 格式无效，拒绝开放回归门禁")
    previous_release = manifest.get("coverage", {}).get("release", {})
    previous_slots = previous_release.get("core", {}).get("bySlot", {})
    current_slots = current.get("core", {}).get("bySlot", {})
    if not isinstance(previous_slots, dict) or not isinstance(current_slots, dict):
        # 旧格式（非 schema 5）历史产物没有可比基线，不阻塞构建。
        return
    for key, previous in previous_slots.items():
        current_row = current_slots.get(key)
        if not isinstance(previous, dict) or not isinstance(current_row, dict):
            continue
        previous_answered = previous.get("answeredRate")
        current_answered = current_row.get("answeredRate")
        previous_missing = previous.get("notCollectedRate")
        current_missing = current_row.get("notCollectedRate")
        if (
            isinstance(previous_answered, int | float)
            and isinstance(current_answered, int | float)
            and current_answered < previous_answered - 0.01
        ):
            raise ValueError(f"核心事实回答率回归未获批准：{key}")
        if (
            isinstance(previous_missing, int | float)
            and isinstance(current_missing, int | float)
            and current_missing > previous_missing + 0.005
        ):
            raise ValueError(f"核心事实暂未收录率回归未获批准：{key}")

    if current_package is None:
        return
    database_path = comparison_output / "stardew.db"
    if not database_path.is_file():
        return
    try:
        with sqlite3.connect(database_path) as connection:
            previous_sets = {
                "实体": {row[0] for row in connection.execute("SELECT id FROM entities")},
                "事实槽": {
                    (row[0], row[1])
                    for row in connection.execute("SELECT entity_id, slot_key FROM fact_slots")
                },
                "事实项": {row[0] for row in connection.execute("SELECT id FROM fact_items")},
                "关系组": {row[0] for row in connection.execute("SELECT id FROM relation_groups")},
                "关系": {row[0] for row in connection.execute("SELECT id FROM relations")},
                "视觉": {row[0] for row in connection.execute("SELECT id FROM visuals")},
                "卡片": {row[0] for row in connection.execute("SELECT entity_id FROM entity_cards")},
                "facet": {row[0] for row in connection.execute("SELECT id FROM browse_facets")},
                "ID 重定向": {row[0] for row in connection.execute("SELECT alias_id FROM id_aliases")},
            }
    except sqlite3.OperationalError:
        # 旧格式数据库（v4 恢复包等）没有 schema 5 表，不是可比基线。
        return
    current_sets = {
        "实体": {item.id for item in current_package.entities},
        "事实槽": {(item.entity_id, item.slot_key) for item in current_package.fact_slots},
        "事实项": {item.id for item in current_package.fact_items},
        "关系组": {item.id for item in current_package.relation_groups},
        "关系": {item.id for item in current_package.relations},
        "视觉": {item.id for item in current_package.visuals},
        "卡片": {item.entity_id for item in current_package.entity_cards},
        "facet": {item.id for item in current_package.facets},
        "ID 重定向": {item.alias_id for item in current_package.id_aliases},
    }
    for label, previous_ids in previous_sets.items():
        removed = sorted(previous_ids - current_sets[label], key=str)
        if removed:
            raise ValueError(f"上一获准包的{label}被移除，未获批准：{removed[0]}")


def _entity_locators(package: Schema5Package) -> dict[str, str]:
    by_record_key = {
        locator.record_key: locator.id
        for locator in package.source_locators
        if locator.record_key
    }
    result: dict[str, str] = {}
    for entity in package.entities:
        if entity.game_id and entity.game_id in by_record_key:
            result[entity.id] = by_record_key[entity.game_id]
            continue
        suffix = stable_part(entity.id)
        matches = [locator.id for locator in package.source_locators if locator.id.endswith(suffix)]
        if len(matches) == 1:
            result[entity.id] = matches[0]
    return result


__all__ = [
    "CORE_FACT_SLOTS",
    "ensure_core_fact_slots",
    "validate_core_coverage",
    "validate_release_coverage",
    "validate_regression_budget",
]
