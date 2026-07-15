CREATE TABLE build_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE entities (
    id TEXT PRIMARY KEY NOT NULL,
    entity_type TEXT NOT NULL,
    game_id TEXT,
    internal_name TEXT,
    name_zh TEXT NOT NULL,
    name_en TEXT,
    description_zh TEXT,
    description_en TEXT,
    category TEXT,
    translation_status TEXT NOT NULL DEFAULT 'complete',
    image_path TEXT,
    extra_json TEXT NOT NULL DEFAULT '{}',
    source_file TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX index_entities_type ON entities(entity_type);
CREATE INDEX index_entities_name_zh ON entities(name_zh);
CREATE INDEX index_entities_game_id ON entities(game_id);

CREATE TABLE entity_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    FOREIGN KEY(entity_id) REFERENCES entities(id)
);

CREATE VIRTUAL TABLE entity_search USING fts4(
    entity_id,
    name_zh,
    name_en,
    pinyin,
    pinyin_initials,
    aliases,
    keywords,
    search_text
);
