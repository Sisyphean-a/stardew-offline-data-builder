PRAGMA foreign_keys = ON;
PRAGMA user_version = 5;

CREATE TABLE build_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE package_capabilities (
    capability TEXT PRIMARY KEY NOT NULL,
    requirement TEXT NOT NULL CHECK (requirement IN ('required', 'optional'))
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
    created_at TEXT NOT NULL,
    UNIQUE(entity_type, game_id)
);

CREATE INDEX index_entities_type ON entities(entity_type);
CREATE INDEX index_entities_name_zh ON entities(name_zh);
CREATE INDEX index_entities_game_id ON entities(game_id);

CREATE TABLE entity_aliases (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE(entity_id, alias, alias_type)
);

CREATE INDEX index_entity_aliases_entity ON entity_aliases(entity_id);
CREATE INDEX index_entity_aliases_alias ON entity_aliases(alias COLLATE NOCASE);

CREATE TABLE id_aliases (
    alias_id TEXT PRIMARY KEY NOT NULL,
    entity_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE INDEX index_id_aliases_entity ON id_aliases(entity_id);

CREATE TABLE condition_sets (
    id TEXT PRIMARY KEY NOT NULL,
    completeness TEXT NOT NULL CHECK (completeness IN ('complete', 'partial', 'opaque')),
    player_summary TEXT,
    original_text TEXT
);

CREATE TABLE condition_terms (
    id TEXT PRIMARY KEY NOT NULL,
    condition_set_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    kind TEXT NOT NULL,
    value_text TEXT,
    value_integer INTEGER,
    value_real REAL,
    FOREIGN KEY(condition_set_id) REFERENCES condition_sets(id) ON DELETE CASCADE,
    UNIQUE(condition_set_id, ordinal)
);

CREATE INDEX index_condition_terms_set ON condition_terms(condition_set_id, ordinal);

CREATE TABLE source_documents (
    id TEXT PRIMARY KEY NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('official_direct', 'official_derived', 'supplemental', 'display_override')),
    title TEXT NOT NULL,
    game_version TEXT,
    content_hash TEXT,
    revision TEXT,
    source_url TEXT,
    revision_at TEXT,
    platform TEXT,
    language TEXT,
    reviewed_at TEXT,
    review_status TEXT NOT NULL DEFAULT 'not_required' CHECK (review_status IN ('not_required', 'pending', 'approved', 'rejected')),
    expires_at TEXT,
    conflict_status TEXT NOT NULL DEFAULT 'none' CHECK (conflict_status IN ('none', 'conflict', 'superseded'))
);

CREATE TABLE source_locators (
    id TEXT PRIMARY KEY NOT NULL,
    source_document_id TEXT NOT NULL,
    source_file TEXT,
    json_path TEXT,
    record_key TEXT,
    FOREIGN KEY(source_document_id) REFERENCES source_documents(id) ON DELETE CASCADE
);

CREATE INDEX index_source_locators_document ON source_locators(source_document_id);

CREATE TABLE fact_slots (
    id TEXT PRIMARY KEY NOT NULL,
    entity_id TEXT NOT NULL,
    slot_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('fixed', 'conditional', 'dynamic_rule', 'unknown', 'not_collected', 'not_applicable')),
    value_type TEXT,
    text_value TEXT,
    integer_value INTEGER,
    real_value REAL,
    boolean_value INTEGER CHECK (boolean_value IS NULL OR boolean_value IN (0, 1)),
    unit TEXT,
    condition_set_id TEXT,
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY(condition_set_id) REFERENCES condition_sets(id) ON DELETE RESTRICT,
    UNIQUE(entity_id, slot_key),
    CHECK (
        status IN ('unknown', 'not_collected', 'not_applicable')
        OR value_type IS NOT NULL
        OR status = 'dynamic_rule'
    )
);

CREATE INDEX index_fact_slots_entity ON fact_slots(entity_id, slot_key);
CREATE INDEX index_fact_slots_key_status ON fact_slots(slot_key, status);
CREATE INDEX index_fact_slots_condition ON fact_slots(condition_set_id);

CREATE TABLE fact_items (
    id TEXT PRIMARY KEY NOT NULL,
    slot_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    value_type TEXT NOT NULL,
    text_value TEXT,
    integer_value INTEGER,
    real_value REAL,
    boolean_value INTEGER CHECK (boolean_value IS NULL OR boolean_value IN (0, 1)),
    unit TEXT,
    scope_id TEXT,
    condition_set_id TEXT,
    FOREIGN KEY(slot_id) REFERENCES fact_slots(id) ON DELETE CASCADE,
    FOREIGN KEY(condition_set_id) REFERENCES condition_sets(id) ON DELETE RESTRICT,
    UNIQUE(slot_id, ordinal)
);

CREATE INDEX index_fact_items_slot ON fact_items(slot_id, ordinal);
CREATE INDEX index_fact_items_scope ON fact_items(scope_id);
CREATE INDEX index_fact_items_condition ON fact_items(condition_set_id);

CREATE TABLE relation_groups (
    id TEXT PRIMARY KEY NOT NULL,
    entity_id TEXT NOT NULL,
    family TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('fixed', 'conditional', 'dynamic_rule', 'unknown', 'not_collected', 'not_applicable')),
    condition_set_id TEXT,
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY(condition_set_id) REFERENCES condition_sets(id) ON DELETE RESTRICT,
    UNIQUE(entity_id, family)
);

CREATE INDEX index_relation_groups_entity ON relation_groups(entity_id, family);

CREATE TABLE relations (
    id TEXT PRIMARY KEY NOT NULL,
    relation_group_id TEXT NOT NULL,
    subject_entity_id TEXT NOT NULL,
    predicate TEXT NOT NULL CHECK (predicate IN ('kinship', 'friendship', 'friendship_unspecified', 'guardianship', 'cohabitation', 'love_interest_pointer')),
    object_entity_id TEXT NOT NULL,
    original_direction TEXT NOT NULL,
    label TEXT,
    condition_set_id TEXT,
    FOREIGN KEY(relation_group_id) REFERENCES relation_groups(id) ON DELETE CASCADE,
    FOREIGN KEY(subject_entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY(object_entity_id) REFERENCES entities(id) ON DELETE RESTRICT,
    FOREIGN KEY(condition_set_id) REFERENCES condition_sets(id) ON DELETE RESTRICT,
    UNIQUE(subject_entity_id, predicate, object_entity_id)
);

CREATE INDEX index_relations_subject ON relations(subject_entity_id, predicate, id);
CREATE INDEX index_relations_object ON relations(object_entity_id, predicate, id);
CREATE INDEX index_relations_group ON relations(relation_group_id);

CREATE TABLE evidence (
    id TEXT PRIMARY KEY NOT NULL,
    source_locator_id TEXT NOT NULL,
    evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('direct', 'derived', 'supplemental', 'override')),
    transformation_rule TEXT,
    input_claim_id TEXT,
    FOREIGN KEY(source_locator_id) REFERENCES source_locators(id) ON DELETE RESTRICT
);

CREATE INDEX index_evidence_locator ON evidence(source_locator_id);

CREATE TABLE claim_evidence (
    claim_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    claim_type TEXT NOT NULL CHECK (claim_type IN ('fact_slot', 'fact_item', 'relation_group', 'relation', 'visual', 'card', 'facet')),
    PRIMARY KEY(claim_id, evidence_id),
    FOREIGN KEY(evidence_id) REFERENCES evidence(id) ON DELETE RESTRICT
);

CREATE INDEX index_claim_evidence_evidence ON claim_evidence(evidence_id);
CREATE INDEX index_claim_evidence_claim ON claim_evidence(claim_id, claim_type);

CREATE TABLE visuals (
    id TEXT PRIMARY KEY NOT NULL,
    entity_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('entity', 'proxy')),
    status TEXT NOT NULL CHECK (status IN ('official_own', 'official_reuse', 'official_none', 'proxy', 'pending_review', 'package_error')),
    relative_path TEXT,
    sha256 TEXT,
    source_entity_id TEXT,
    crop_rect TEXT,
    rule_version TEXT,
    reuse_reason TEXT,
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY(source_entity_id) REFERENCES entities(id) ON DELETE RESTRICT,
    UNIQUE(entity_id, role)
);

CREATE INDEX index_visuals_entity ON visuals(entity_id, role);
CREATE INDEX index_visuals_status ON visuals(status);

CREATE TABLE entity_cards (
    entity_id TEXT PRIMARY KEY NOT NULL,
    identity_summary TEXT,
    action_summary_1 TEXT,
    action_summary_2 TEXT,
    category_label TEXT,
    sort_key TEXT NOT NULL,
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE INDEX index_entity_cards_sort ON entity_cards(sort_key, entity_id);

CREATE TABLE browse_facet_groups (
    id TEXT PRIMARY KEY NOT NULL,
    entity_id TEXT NOT NULL,
    family TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('fixed', 'conditional', 'dynamic_rule', 'unknown', 'not_collected', 'not_applicable')),
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE(entity_id, family)
);

CREATE INDEX index_browse_facet_groups_entity ON browse_facet_groups(entity_id, family);

CREATE TABLE browse_facets (
    id TEXT PRIMARY KEY NOT NULL,
    group_id TEXT NOT NULL,
    scope_family TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    value_type TEXT NOT NULL CHECK (value_type IN ('text', 'integer', 'real', 'boolean', 'range')),
    text_value TEXT,
    integer_value INTEGER,
    real_value REAL,
    boolean_value INTEGER CHECK (boolean_value IS NULL OR boolean_value IN (0, 1)),
    range_min REAL,
    range_max REAL,
    unit TEXT,
    claim_status TEXT NOT NULL CHECK (claim_status IN ('fixed', 'conditional', 'dynamic_rule')),
    condition_set_id TEXT,
    FOREIGN KEY(group_id) REFERENCES browse_facet_groups(id) ON DELETE CASCADE,
    FOREIGN KEY(condition_set_id) REFERENCES condition_sets(id) ON DELETE RESTRICT,
    UNIQUE(group_id, scope_family, scope_id, value_type, text_value, integer_value, real_value, range_min, range_max)
);

CREATE INDEX index_browse_facets_group ON browse_facets(group_id, scope_family, scope_id);
CREATE INDEX index_browse_facets_text ON browse_facets(scope_family, text_value);
CREATE INDEX index_browse_facets_integer ON browse_facets(scope_family, integer_value);
CREATE INDEX index_browse_facets_range ON browse_facets(scope_family, range_min, range_max);

CREATE VIRTUAL TABLE entity_search USING fts4(
    entity_id,
    name_zh,
    name_en,
    aliases,
    keywords,
    action_summaries,
    search_text
);
