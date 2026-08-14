from __future__ import annotations

import pytest

from builder.commands.schema5_candidate import (
    prepare_formal_inputs,
    reject_legacy_only_inputs,
)
from builder.models import NormalizedEntity


def entity(
    *,
    extra_json: dict[str, object],
    source_attributes: dict[str, object] | None = None,
) -> NormalizedEntity:
    return NormalizedEntity(
        id="object:1",
        entity_type="object",
        game_id="1",
        internal_name="Object",
        name_zh="测试",
        name_en="Test",
        description_zh=None,
        description_en=None,
        category=None,
        source_file="Data/Objects.json",
        extra_json=extra_json,
        source_attributes=source_attributes or {},
    )


@pytest.mark.parametrize(
    "extra_json",
    [
        {"legacyFields": ["Test/10"]},
        {"legacyValue": "Test/10"},
        {"officialDerived": {"sellPrice": 10}},
    ],
)
def test_formal_candidate_rejects_legacy_markers_retained_for_v4(
    extra_json: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="schema 5.*legacy"):
        reject_legacy_only_inputs([entity(extra_json=extra_json)])


def test_formal_candidate_rejects_legacy_markers_even_if_structured_values_exist() -> None:
    with pytest.raises(ValueError, match="schema 5.*legacy"):
        reject_legacy_only_inputs(
            [
                entity(
                    extra_json={"legacyFields": ["Test/10"]},
                    source_attributes={"Price": 10},
                )
            ]
        )


def test_formal_candidate_accepts_compact_record_only_with_explicit_source_boundary() -> None:
    prepared = prepare_formal_inputs(
        [
            entity(
                extra_json={
                    "legacyFields": ["Test/10"],
                    "legacyValue": "Test/10",
                    "sourceFormat": "official_compact",
                    "imageSource": "Objects.png",
                },
                source_attributes={"sourceFormat": "official_compact", "Price": 10},
            )
        ]
    )
    assert prepared[0].source_attributes["Price"] == 10
    assert "legacyFields" not in prepared[0].extra_json
    assert "legacyValue" not in prepared[0].extra_json
    assert prepared[0].extra_json["sourceFormat"] == "official_compact"


def test_formal_candidate_rejects_unknown_legacy_source_boundary() -> None:
    with pytest.raises(ValueError, match="schema 5.*legacy"):
        prepare_formal_inputs(
            [
                entity(
                    extra_json={"legacyFields": ["Test/10"]},
                    source_attributes={"Price": 10},
                )
            ]
        )
