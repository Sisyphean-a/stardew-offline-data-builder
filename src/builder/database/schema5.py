"""Schema 5 staging writer used by the B1 conformance fixture.

The normal v4 writer is intentionally not reused: a schema 5 database must not
carry the v4 ``extra_json``/``officialDerived`` public payload.  The writer is
small until B2 supplies the fact and evidence producers, but it creates the
complete relational surface and all protocol metadata now.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import orjson

from builder import __version__
from builder.config import ENTITY_TYPE_LABELS
from builder.models_schema5 import Schema5Entity
from builder.pipeline.schema5_contract import (
    CONTENT_CONTRACT,
    MANIFEST_VERSION,
    SCHEMA_VERSION,
    capabilities_payload,
)
from builder.utils.time import current_utc_iso

SCHEMA_FILENAME = "schema5.sql"
MANIFEST_FILENAME = "manifest.json"
CONFORMANCE_FILENAME = "schema5-conformance.json"


def write_schema5_fixture(
    output_dir: Path,
    entities: list[Schema5Entity] | None = None,
    *,
    locale: str = "zh-CN",
    source_hash: str = "f" * 64,
    game_version: str = "fixture",
    generated_at: str | None = None,
) -> dict[str, Path]:
    """Write an explicitly non-publishable schema 5 conformance fixture.

    The fixture intentionally has no fact slots.  It proves the protocol shape,
    metadata binding, foreign keys and capability declaration without pretending
    to be real player data.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or current_utc_iso()
    entities = entities or default_schema5_fixture_entities()
    database_path = output_dir / "stardew.db"
    manifest_path = output_dir / MANIFEST_FILENAME
    conformance_path = output_dir / CONFORMANCE_FILENAME

    tmp_path = database_path.with_suffix(database_path.suffix + ".tmp")
    tmp_path.unlink(missing_ok=True)
    connection = sqlite3.connect(tmp_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            (Path(__file__).with_name(SCHEMA_FILENAME)).read_text(encoding="utf-8")
        )
        fingerprint = schema_fingerprint(connection)
        metadata = build_schema5_metadata(
            entities=entities,
            locale=locale,
            source_hash=source_hash,
            game_version=game_version,
            generated_at=generated_at,
            schema_fingerprint=fingerprint,
            publishable=False,
        )
        insert_build_meta(connection, metadata)
        insert_capabilities(connection, metadata["capabilities"])
        insert_entities(connection, entities, generated_at)
        insert_cards_and_visuals(connection, entities)
        insert_aliases(connection, entities)
        insert_search(connection, entities)
        connection.commit()
    except Exception:
        connection.close()
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
    tmp_path.replace(database_path)

    manifest = manifest_payload(metadata, database_path)
    manifest_path.write_bytes(orjson.dumps(manifest, option=orjson.OPT_INDENT_2))
    conformance_path.write_bytes(
        orjson.dumps(
            {
                "status": "non_publishable_fixture",
                "manifestVersion": MANIFEST_VERSION,
                "schemaVersion": SCHEMA_VERSION,
                "contentContract": CONTENT_CONTRACT,
                "publishable": False,
                "databaseSha256": manifest["database"]["sha256"],
                "schemaFingerprint": fingerprint,
                "requiredCapabilities": metadata["capabilities"]["required"],
                "factSlots": 0,
                "containsLegacyOfficialDerived": False,
            },
            option=orjson.OPT_INDENT_2,
        )
    )
    return {
        "database": database_path,
        "manifest": manifest_path,
        "conformance": conformance_path,
    }


def default_schema5_fixture_entities() -> list[Schema5Entity]:
    return [
        Schema5Entity(
            id="object:1",
            entity_type="object",
            game_id="1",
            name_zh="测试物品",
            name_en="Test item",
            category="物品",
            action_summary_1="可作为测试条目浏览",
            sort_key="测试物品",
        ),
        Schema5Entity(
            id="villager:Abigail",
            entity_type="villager",
            game_id="Abigail",
            name_zh="阿比盖尔",
            name_en="Abigail",
            category="村民",
            action_summary_1="可作为测试人物浏览",
            sort_key="阿比盖尔",
        ),
    ]


def build_schema5_metadata(
    *,
    entities: list[Schema5Entity],
    locale: str,
    source_hash: str,
    game_version: str,
    generated_at: str,
    schema_fingerprint: str,
    publishable: bool,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for entity in entities:
        counts[entity.entity_type] = counts.get(entity.entity_type, 0) + 1
    entity_types = [
        {
            "id": entity_type,
            "displayName": ENTITY_TYPE_LABELS.get(entity_type, entity_type),
            "count": count,
        }
        for entity_type, count in sorted(counts.items())
    ]
    quality = {
        "status": "passed",
        "translations": {
            "complete": sum(entity.translation_status == "complete" for entity in entities),
            "missing": sum(entity.translation_status == "missing" for entity in entities),
            "invalid": sum(entity.translation_status == "invalid" for entity in entities),
            "notApplicable": sum(
                entity.translation_status == "not_applicable" for entity in entities
            ),
            "unusable": 0,
        },
        "dataErrors": 0,
        "unlabeledEntityTypes": [],
    }
    content = {
        "entities": len(entities),
        "objects": counts.get("object", 0),
        "crops": counts.get("crop", 0),
        "fish": counts.get("fish", 0),
        "villagers": counts.get("villager", 0),
        "extraCounts": {
            entity_type: count
            for entity_type, count in sorted(counts.items())
            if entity_type not in {"object", "crop", "fish", "villager"}
        },
        "missingTranslations": quality["translations"]["missing"],
        "entityTypes": entity_types,
    }
    capabilities = capabilities_payload()
    return {
        "manifestVersion": MANIFEST_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "contentContract": CONTENT_CONTRACT,
        "schemaFingerprint": schema_fingerprint,
        "builderVersion": __version__,
        "language": locale,
        "generatedAt": generated_at,
        "gameVersion": game_version,
        "sourceHash": source_hash,
        "publishable": publishable,
        "capabilities": capabilities,
        "content": content,
        "quality": quality,
        "coverage": {
            "factSlots": {"answered": 0, "unknown": 0, "notCollected": 0},
            "conditions": {"complete": 0, "partial": 0, "opaque": 0},
            "relations": {"groups": 0, "edges": 0},
            "visuals": {"pendingReview": 0, "packageErrors": 0},
        },
    }


def manifest_payload(metadata: dict[str, Any], database_path: Path) -> dict[str, Any]:
    return {
        "format": "stardew-offline-data",
        "manifestVersion": metadata["manifestVersion"],
        "schemaVersion": metadata["schemaVersion"],
        "contentContract": metadata["contentContract"],
        "schemaFingerprint": metadata["schemaFingerprint"],
        "builderVersion": metadata["builderVersion"],
        "gameVersion": metadata["gameVersion"],
        "language": metadata["language"],
        "generatedAt": metadata["generatedAt"],
        "sourceHash": metadata["sourceHash"],
        "publishable": metadata["publishable"],
        "capabilities": metadata["capabilities"],
        "database": {
            "file": database_path.name,
            "sha256": sha256_file(database_path),
            "schemaFingerprint": metadata["schemaFingerprint"],
        },
        "content": metadata["content"],
        "quality": metadata["quality"],
        "coverage": metadata["coverage"],
    }


def insert_build_meta(connection: sqlite3.Connection, metadata: dict[str, Any]) -> None:
    rows = [
        ("schema_version", str(SCHEMA_VERSION)),
        ("manifest_version", str(MANIFEST_VERSION)),
        ("content_contract", CONTENT_CONTRACT),
        ("schema_fingerprint", metadata["schemaFingerprint"]),
        ("builder_version", metadata["builderVersion"]),
        ("locale", metadata["language"]),
        ("generated_at", metadata["generatedAt"]),
        ("entity_count", str(metadata["content"]["entities"])),
        ("game_version", metadata["gameVersion"]),
        ("source_hash", metadata["sourceHash"]),
        ("artifact_metadata", orjson.dumps(metadata).decode("utf-8")),
    ]
    connection.executemany("INSERT INTO build_meta(key, value) VALUES (?, ?)", rows)


def insert_capabilities(connection: sqlite3.Connection, capabilities: dict[str, list[str]]) -> None:
    rows = [
        (capability, requirement)
        for requirement in ("required", "optional")
        for capability in capabilities[requirement]
    ]
    connection.executemany(
        "INSERT INTO package_capabilities(capability, requirement) VALUES (?, ?)", rows
    )


def insert_entities(
    connection: sqlite3.Connection,
    entities: list[Schema5Entity],
    generated_at: str,
) -> None:
    connection.executemany(
        """
        INSERT INTO entities(
            id, entity_type, game_id, internal_name, name_zh, name_en,
            description_zh, description_en, category, translation_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                entity.id,
                entity.entity_type,
                entity.game_id,
                entity.internal_name,
                entity.name_zh,
                entity.name_en,
                entity.description_zh,
                entity.description_en,
                entity.category,
                entity.translation_status,
                generated_at,
            )
            for entity in entities
        ],
    )


def insert_cards_and_visuals(
    connection: sqlite3.Connection,
    entities: list[Schema5Entity],
    visuals: list[Any] | None = None,
    cards: list[Any] | None = None,
) -> None:
    cards_by_entity = {card.entity_id: card for card in cards or []}
    card_rows = [
        (
            entity.id,
            cards_by_entity.get(entity.id, entity).identity_summary
            if entity.id in cards_by_entity
            else entity.description_zh,
            cards_by_entity.get(entity.id, entity).action_summary_1
            if entity.id in cards_by_entity
            else entity.action_summary_1,
            cards_by_entity.get(entity.id, entity).action_summary_2
            if entity.id in cards_by_entity
            else entity.action_summary_2,
            cards_by_entity.get(entity.id, entity).category_label
            if entity.id in cards_by_entity
            else entity.category,
            cards_by_entity.get(entity.id, entity).sort_key
            if entity.id in cards_by_entity
            else entity.sort_key or entity.name_zh,
        )
        for entity in sorted(entities, key=lambda item: item.id)
    ]
    connection.executemany(
        """
        INSERT INTO entity_cards(
            entity_id, identity_summary, action_summary_1, action_summary_2,
            category_label, sort_key
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        card_rows,
    )

    explicit_visuals = {(visual.entity_id, visual.role): visual for visual in visuals or []}
    visual_rows = [
        (
            f"visual:{entity.id}",
            entity.id,
            "entity",
            entity.visual_status,
            entity.visual_relative_path,
            entity.visual_sha256,
            entity.visual_source_entity_id,
            entity.visual_crop_rect,
            entity.visual_rule_version,
            entity.visual_reuse_reason,
        )
        for entity in sorted(entities, key=lambda item: item.id)
        if (entity.id, "entity") not in explicit_visuals
    ]
    visual_rows.extend(
        (
            visual.id,
            visual.entity_id,
            visual.role,
            visual.status,
            visual.relative_path,
            visual.sha256,
            visual.source_entity_id,
            visual.crop_rect,
            visual.rule_version,
            visual.reuse_reason,
        )
        for visual in sorted(visuals or [], key=lambda item: item.id)
    )
    connection.executemany(
        """
        INSERT INTO visuals(
            id, entity_id, role, status, relative_path, sha256, source_entity_id,
            crop_rect, rule_version, reuse_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        visual_rows,
    )


def insert_aliases(connection: sqlite3.Connection, entities: list[Schema5Entity]) -> None:
    rows = [(entity.id, alias, "fixture") for entity in entities for alias in entity.aliases]
    if rows:
        connection.executemany(
            "INSERT INTO entity_aliases(entity_id, alias, alias_type) VALUES (?, ?, ?)", rows
        )


def insert_search(connection: sqlite3.Connection, entities: list[Schema5Entity]) -> None:
    connection.executemany(
        """
        INSERT INTO entity_search(
            entity_id, name_zh, name_en, aliases, keywords, action_summaries, search_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                entity.id,
                entity.name_zh,
                entity.name_en or "",
                " ".join(entity.aliases),
                entity.category or "",
                " ".join(filter(None, (entity.action_summary_1, entity.action_summary_2))),
                " ".join(
                    filter(
                        None,
                        (
                            entity.name_zh,
                            entity.name_en,
                            *entity.aliases,
                            entity.category,
                            entity.action_summary_1,
                            entity.action_summary_2,
                        ),
                    )
                ),
            )
            for entity in entities
        ],
    )


def schema_fingerprint(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        SELECT type, name, COALESCE(sql, '')
        FROM sqlite_master
        WHERE type IN ('table', 'index', 'trigger', 'view')
          AND name NOT LIKE 'sqlite_%'
          AND name NOT LIKE 'entity_search_%'
        ORDER BY type, name
        """
    ).fetchall()
    payload = "\n".join("\x1f".join(str(value) for value in row) for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
