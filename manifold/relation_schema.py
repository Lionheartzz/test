"""Schema v5 relation audit identities. Initialization is an explicit import action."""

TABLES = {
    'kb_logical_cavity_supplements': {'id','canonical_family','canonical_name','preferred_display_name','physical_identity_count','units','display_families','import_batch_id'},
    'kb_cavity_supplements': {'canonical_id','logical_id','unit','canonical_family','display_family','canonical_name','display_name','status','active_selection_basis','source_count','geometry_status','raw_metadata_json','import_batch_id','promoted_cavity_id','runtime_selectable','machining_usable','routing_usable','tooling_usable','execution_geometry_available'},
    'cartridge_cavity_supplement_links': {'relation_id','canonical_id'},
    'kb_pending_registry': {'id','timestamp','family','identity','category','suspicion','raw_status','normalized_status','resolution','raw_metadata_json','import_batch_id'},
    'kb_relation_migrations': {'id','source_sha256','source_schema','package_sha256','replaced_batches_json','report_json'},
}


def initialize(db):
    db.executescript('''
    CREATE TABLE kb_logical_cavity_supplements(
        id TEXT PRIMARY KEY, canonical_family TEXT NOT NULL, canonical_name TEXT NOT NULL,
        preferred_display_name TEXT NOT NULL, physical_identity_count INTEGER NOT NULL,
        units TEXT NOT NULL, display_families TEXT NOT NULL,
        import_batch_id TEXT NOT NULL REFERENCES kb_import_batches(id),
        UNIQUE(canonical_family,canonical_name));
    CREATE TABLE kb_cavity_supplements(
        canonical_id TEXT PRIMARY KEY, logical_id TEXT NOT NULL REFERENCES kb_logical_cavity_supplements(id),
        unit TEXT NOT NULL CHECK(unit IN ('inch','metric')), canonical_family TEXT NOT NULL,
        display_family TEXT NOT NULL, canonical_name TEXT NOT NULL, display_name TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('SUPPLEMENT_EXTERNAL','PROMOTED','SUPERSEDED_BY_CANONICAL')),
        active_selection_basis TEXT NOT NULL, source_count INTEGER NOT NULL,
        geometry_status TEXT NOT NULL, raw_metadata_json TEXT NOT NULL,
        import_batch_id TEXT NOT NULL REFERENCES kb_import_batches(id),
        promoted_cavity_id TEXT REFERENCES cavities(id),
        runtime_selectable INTEGER NOT NULL DEFAULT 0 CHECK(runtime_selectable=0),
        machining_usable INTEGER NOT NULL DEFAULT 0 CHECK(machining_usable=0),
        routing_usable INTEGER NOT NULL DEFAULT 0 CHECK(routing_usable=0),
        tooling_usable INTEGER NOT NULL DEFAULT 0 CHECK(tooling_usable=0),
        execution_geometry_available INTEGER NOT NULL DEFAULT 0 CHECK(execution_geometry_available=0),
        UNIQUE(logical_id,unit));
    CREATE TABLE cartridge_cavity_supplement_links(
        relation_id TEXT NOT NULL REFERENCES cartridge_cavity_evidence(relation_id),
        canonical_id TEXT NOT NULL REFERENCES kb_cavity_supplements(canonical_id),
        PRIMARY KEY(relation_id,canonical_id));
    CREATE TABLE kb_pending_registry(
        id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, family TEXT NOT NULL, identity TEXT NOT NULL,
        category TEXT NOT NULL, suspicion TEXT NOT NULL, raw_status TEXT, normalized_status TEXT NOT NULL,
        resolution TEXT, raw_metadata_json TEXT NOT NULL,
        import_batch_id TEXT NOT NULL REFERENCES kb_import_batches(id));
    CREATE TABLE kb_relation_migrations(
        id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, source_schema INTEGER NOT NULL,
        package_sha256 TEXT NOT NULL, replaced_batches_json TEXT NOT NULL, report_json TEXT NOT NULL);
    CREATE INDEX supplement_logical ON kb_cavity_supplements(logical_id,unit);
    CREATE INDEX supplement_reverse ON cartridge_cavity_supplement_links(canonical_id,relation_id);
    CREATE INDEX pending_audit_status ON kb_pending_registry(normalized_status,family,id);
    PRAGMA user_version=5;
    ''')
