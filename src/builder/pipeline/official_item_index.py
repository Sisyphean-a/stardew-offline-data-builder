from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from builder.models import NormalizedEntity
from builder.pipeline.official_values import (
    entity_ids_for_item,
    item_category,
    string_set,
)

CATEGORY_TAGS = {
    -81: "category_greens",
    -79: "category_fruits",
    -75: "category_vegetable",
    -12: "category_minerals",
    -4: "category_fish",
    -2: "category_gem",
}
OBJECT_ENTITY_TYPES = {"object", "mineral", "ring", "fish"}


@dataclass(frozen=True)
class ItemReferenceResolver:
    by_id: dict[str, NormalizedEntity]
    category_index: dict[int, set[str]]
    internal_name_index: dict[str, set[str]]
    machine_entity_ids: frozenset[str]

    @classmethod
    def create(
        cls,
        by_id: dict[str, NormalizedEntity],
    ) -> ItemReferenceResolver:
        return cls(
            by_id=by_id,
            category_index=build_category_index(by_id),
            internal_name_index=build_internal_name_index(by_id),
            machine_entity_ids=frozenset(
                entity_id
                for entity_id, entity in by_id.items()
                if entity.entity_type in OBJECT_ENTITY_TYPES
            ),
        )

    def resolve(self, value: object) -> tuple[str, ...]:
        category = item_category(value)
        if category is not None:
            return tuple(sorted(self.category_index.get(category, set())))
        candidates = entity_ids_for_item(value)
        resolved = tuple(
            entity_id
            for entity_id in candidates
            if entity_id in self.by_id
        )
        if resolved:
            return resolved
        allowed_types = {entity_id.partition(":")[0] for entity_id in candidates}
        source_ids = {entity_id.partition(":")[2].casefold() for entity_id in candidates}
        return tuple(
            sorted(
                entity_id
                for source_id in source_ids
                for entity_id in self.internal_name_index.get(source_id, set())
                if self.by_id[entity_id].entity_type in allowed_types
            )
        )


def add_item_reference(
    index: dict[str, list[dict[str, object]]],
    item_id: object,
    reference: dict[str, object],
    *,
    resolver: ItemReferenceResolver,
) -> None:
    for entity_id in resolver.resolve(item_id):
        index[entity_id].append(reference)


def add_tag_references(
    index: dict[str, list[dict[str, object]]],
    required_tags: object,
    reference: dict[str, object],
    *,
    tag_index: dict[str, set[str]],
    candidate_ids: frozenset[str],
) -> None:
    tags = string_set(required_tags)
    if not tags:
        return
    positive = {tag for tag in tags if not tag.startswith("!")}
    negative = {tag[1:] for tag in tags if tag.startswith("!") and len(tag) > 1}
    entity_ids = matching_positive_ids(positive, tag_index, candidate_ids)
    for tag in negative:
        entity_ids.difference_update(tag_index.get(tag, set()))
    for entity_id in entity_ids:
        index[entity_id].append(reference)


def matching_positive_ids(
    tags: set[str],
    tag_index: dict[str, set[str]],
    candidate_ids: frozenset[str],
) -> set[str]:
    if not tags:
        return set(candidate_ids)
    return set.intersection(*(tag_index.get(tag, set()) for tag in tags))


def build_tag_index(
    by_id: dict[str, NormalizedEntity],
) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for entity_id, entity in by_id.items():
        for tag in tags_for_entity(entity, by_id):
            index[tag].add(entity_id)
    return index


def build_fish_tag_index(
    by_id: dict[str, NormalizedEntity],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for entity_id, entity in by_id.items():
        if entity.entity_type != "fish" or not entity.game_id:
            continue
        item = by_id.get(f"object:{entity.game_id}")
        result[entity_id] = tags_for_entity(item, by_id) if item else set()
    return result


def build_category_index(
    by_id: dict[str, NormalizedEntity],
) -> dict[int, set[str]]:
    index: dict[int, set[str]] = defaultdict(set)
    for entity_id, entity in by_id.items():
        category = entity_category(entity, by_id)
        if category is not None:
            index[category].add(entity_id)
    return index


def build_internal_name_index(
    by_id: dict[str, NormalizedEntity],
) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for entity_id, entity in by_id.items():
        if entity.internal_name:
            index[entity.internal_name.casefold()].add(entity_id)
    return index


def entity_category(
    entity: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
) -> int | None:
    category = entity.extra_json.get("Category")
    if isinstance(category, int):
        return category
    if entity.entity_type == "fish" and entity.game_id:
        item = by_id.get(f"object:{entity.game_id}")
        inherited = item.extra_json.get("Category") if item else None
        return inherited if isinstance(inherited, int) else None
    return None


def tags_for_entity(
    entity: NormalizedEntity,
    by_id: dict[str, NormalizedEntity],
) -> set[str]:
    tags = entity_context_tags(entity)
    if entity.entity_type == "fish" and entity.game_id:
        item = by_id.get(f"object:{entity.game_id}")
        tags.update(entity_context_tags(item) if item else set())
    return tags


def entity_context_tags(entity: NormalizedEntity) -> set[str]:
    tags = string_set(entity.extra_json.get("ContextTags"))
    category = entity.extra_json.get("Category")
    if isinstance(category, int) and category in CATEGORY_TAGS:
        tags.add(CATEGORY_TAGS[category])
    if entity.entity_type in OBJECT_ENTITY_TYPES and entity.game_id:
        tags.add(f"id_o_{entity.game_id.lower()}")
    return tags
