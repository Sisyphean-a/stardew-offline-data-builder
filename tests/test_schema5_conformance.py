from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from builder.cli import app
from builder.database.schema5 import schema_fingerprint, write_schema5_fixture
from builder.pipeline.schema5_contract import (
    CONTENT_CONTRACT,
    MANIFEST_VERSION,
    SCHEMA_VERSION,
    validate_capabilities,
)

runner = CliRunner()


def test_schema5_fixture_has_manifest2_core_and_is_not_publishable(tmp_path: Path) -> None:
    paths = write_schema5_fixture(tmp_path / "fixture")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    conformance = json.loads(paths["conformance"].read_text(encoding="utf-8"))

    assert manifest["manifestVersion"] == MANIFEST_VERSION
    assert manifest["schemaVersion"] == SCHEMA_VERSION
    assert manifest["contentContract"] == CONTENT_CONTRACT
    assert manifest["publishable"] is False
    assert manifest["database"]["schemaFingerprint"] == conformance["schemaFingerprint"]
    assert conformance["containsLegacyOfficialDerived"] is False

    connection = sqlite3.connect(paths["database"])
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "entities",
            "fact_slots",
            "relation_groups",
            "relations",
            "condition_sets",
            "source_documents",
            "evidence",
            "visuals",
            "entity_cards",
            "browse_facets",
            "entity_search",
        } <= tables
        assert "extra_json" not in {
            row[1] for row in connection.execute("PRAGMA table_info(entities)")
        }
        assert schema_fingerprint(connection) == conformance["schemaFingerprint"]
    finally:
        connection.close()


def test_schema5_capabilities_reject_unknown_required_or_missing_required() -> None:
    for capabilities, expected in [
        ({"required": ["entities", "future-capability"], "optional": []}, "包含未知必需能力"),
        ({"required": ["entities"], "optional": []}, "缺少必需能力"),
    ]:
        try:
            validate_capabilities(capabilities)
        except ValueError as error:
            assert str(error) == expected
        else:
            raise AssertionError("非法 capability manifest 不应通过")


def test_schema5_manifest_exposes_coverage_shape(tmp_path: Path) -> None:
    paths = write_schema5_fixture(tmp_path / "fixture")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["coverage"]["factSlots"] == {
        "answered": 0,
        "unknown": 0,
        "notCollected": 0,
    }


def test_schema5_fixture_cli_is_explicitly_non_release(tmp_path: Path) -> None:
    result = runner.invoke(app, ["build-schema5-fixture", "--output", str(tmp_path / "fixture")])

    assert result.exit_code == 0
    assert "不可发布" in result.stdout
    assert (tmp_path / "fixture" / "schema5-conformance.json").is_file()
