from __future__ import annotations

import sqlite3
from pathlib import Path

import orjson

from builder import __version__
from builder.config import SCHEMA_VERSION, TEMP_DB_SUFFIX
from builder.models import BuildSummary, NormalizedEntity, SearchDocument
from builder.utils.time import current_utc_iso


def write_database(
    db_path: Path,
    entities: list[NormalizedEntity],
    search_documents: list[SearchDocument],
    locale: str,
    summary: BuildSummary,
    generated_at: str | None = None,
    source_hash: str = "",
    game_version: str = "unknown",
) -> None:
    tmp_path = db_path.with_suffix(db_path.suffix + TEMP_DB_SUFFIX)
    if tmp_path.exists():
        tmp_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(tmp_path)
    try:
        create_schema(connection)
        created_at = generated_at or current_utc_iso()
        insert_meta(
            connection,
            locale,
            summary,
            generated_at=created_at,
            source_hash=source_hash,
            game_version=game_version,
        )
        insert_entities(connection, entities, created_at=created_at)
        insert_aliases(connection, entities)
        insert_search_documents(connection, search_documents)
        connection.commit()
    except Exception:
        connection.close()
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    connection.close()
    tmp_path.replace(db_path)


def create_schema(connection: sqlite3.Connection) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    connection.executescript(schema_path.read_text(encoding="utf-8"))


def insert_meta(
    connection: sqlite3.Connection,
    locale: str,
    summary: BuildSummary,
    generated_at: str,
    source_hash: str,
    game_version: str,
) -> None:
    rows = [
        ("schema_version", str(SCHEMA_VERSION)),
        ("builder_version", __version__),
        ("locale", locale),
        ("generated_at", generated_at),
        ("entity_count", str(summary.entities)),
        ("game_version", game_version),
        ("source_hash", source_hash),
    ]
    connection.executemany("INSERT INTO build_meta(key, value) VALUES (?, ?)", rows)


def insert_entities(
    connection: sqlite3.Connection,
    entities: list[NormalizedEntity],
    created_at: str,
) -> None:
    rows = []
    for entity in entities:
        rows.append(
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
                entity.image_path,
                orjson.dumps(entity.extra_json).decode("utf-8"),
                entity.source_file,
                created_at,
            )
        )
    connection.executemany(
        """
        INSERT INTO entities(
            id, entity_type, game_id, internal_name, name_zh, name_en,
            description_zh, description_en, category, translation_status,
            image_path, extra_json, source_file, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def insert_aliases(connection: sqlite3.Connection, entities: list[NormalizedEntity]) -> None:
    rows = []
    for entity in entities:
        for alias in entity.aliases:
            rows.append((entity.id, alias, "manual"))
    if rows:
        connection.executemany(
            "INSERT INTO entity_aliases(entity_id, alias, alias_type) VALUES (?, ?, ?)",
            rows,
        )


def insert_search_documents(
    connection: sqlite3.Connection,
    documents: list[SearchDocument],
) -> None:
    rows = [
        (
            document.entity_id,
            document.name_zh,
            document.name_en,
            document.pinyin,
            document.pinyin_initials,
            document.aliases,
            document.keywords,
            document.search_text,
        )
        for document in documents
    ]
    connection.executemany(
        """
        INSERT INTO entity_search(
            entity_id, name_zh, name_en, pinyin, pinyin_initials, aliases, keywords, search_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def inspect_database(db_path: Path) -> dict[str, str | int]:
    connection = sqlite3.connect(db_path)
    counts_by_type = dict(
        connection.execute(
            "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
        ).fetchall()
    )
    summary = {
        "schema_version": lookup_meta(connection, "schema_version"),
        "locale": lookup_meta(connection, "locale"),
        "entities": query_count(connection, "SELECT COUNT(*) FROM entities"),
        "objects": query_count(
            connection,
            "SELECT COUNT(*) FROM entities WHERE entity_type = 'object'",
        ),
        "crops": query_count(
            connection,
            "SELECT COUNT(*) FROM entities WHERE entity_type = 'crop'",
        ),
        "fish": query_count(
            connection,
            "SELECT COUNT(*) FROM entities WHERE entity_type = 'fish'",
        ),
        "villagers": query_count(
            connection,
            "SELECT COUNT(*) FROM entities WHERE entity_type = 'villager'",
        ),
        "missing_translations": query_count(
            connection,
            "SELECT COUNT(*) FROM entities WHERE translation_status = 'missing'",
        ),
        "fts": (
            "正常"
            if query_count(connection, "SELECT COUNT(*) FROM entity_search") >= 0
            else "异常"
        ),
        "extra_counts": {
            entity_type: count
            for entity_type, count in counts_by_type.items()
            if entity_type not in {"object", "crop", "fish", "villager"}
        },
    }
    connection.close()
    return summary


def lookup_meta(connection: sqlite3.Connection, key: str) -> str:
    cursor = connection.execute("SELECT value FROM build_meta WHERE key = ?", (key,))
    row = cursor.fetchone()
    return str(row[0]) if row else ""


def query_count(connection: sqlite3.Connection, sql: str) -> int:
    cursor = connection.execute(sql)
    row = cursor.fetchone()
    return int(row[0]) if row else 0
