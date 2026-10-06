"""Additive, non-executable Library research schema; explicit import only."""

VERSION = 6
TABLES = {
    'library_import_batches': {'id', 'source_sha256', 'package_sha256', 'report_json'},
    'library_datasets': {'id', 'archive_path', 'sha256', 'domain', 'role'},
    'library_dataset_aliases': {'dataset_id', 'archive_path', 'original_path'},
    'library_records': {'dataset_id', 'row_key', 'native_id', 'original_json'},
    'library_targets': {'id', 'domain', 'status', 'verification_scope', 'original_json'},
    'library_sources': {'id', 'original_json'},
    'library_source_aliases': {'archive_path', 'original_path', 'sha256', 'byte_count'},
    'library_evidence': {'id', 'entity_id', 'source_id', 'original_json'},
    'library_target_evidence': {'target_id', 'evidence_id'},
    'library_conflicts': {'id', 'kind', 'native_id', 'variants_json'},
    'library_unresolved_links': {'target_id', 'evidence_id'},
}


def initialize(db):
    db.executescript('''
    CREATE TABLE library_import_batches(id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL,
        package_sha256 TEXT NOT NULL, report_json TEXT NOT NULL);
    CREATE TABLE library_datasets(id TEXT PRIMARY KEY, archive_path TEXT NOT NULL,
        sha256 TEXT NOT NULL, domain TEXT NOT NULL, role TEXT NOT NULL,
        byte_count INTEGER NOT NULL, row_count INTEGER NOT NULL,
        batch_id TEXT NOT NULL REFERENCES library_import_batches(id));
    CREATE TABLE library_dataset_aliases(dataset_id TEXT NOT NULL REFERENCES library_datasets(id),
        archive_path TEXT NOT NULL, original_path TEXT NOT NULL,
        PRIMARY KEY(dataset_id,archive_path,original_path));
    CREATE TABLE library_records(dataset_id TEXT NOT NULL REFERENCES library_datasets(id),
        row_key TEXT NOT NULL, native_id TEXT NOT NULL, original_json TEXT NOT NULL,
        PRIMARY KEY(dataset_id,row_key));
    CREATE TABLE library_targets(id TEXT PRIMARY KEY, domain TEXT NOT NULL, target_type TEXT NOT NULL,
        raw_identity TEXT NOT NULL, canonical_identity TEXT NOT NULL, status TEXT NOT NULL,
        disposition TEXT NOT NULL, verification_scope TEXT NOT NULL, gate_json TEXT NOT NULL,
        notes TEXT NOT NULL, original_json TEXT NOT NULL);
    CREATE TABLE library_sources(id TEXT PRIMARY KEY, original_json TEXT NOT NULL);
    CREATE TABLE library_source_aliases(archive_path TEXT NOT NULL, original_path TEXT NOT NULL,
        sha256 TEXT NOT NULL, byte_count INTEGER NOT NULL, PRIMARY KEY(archive_path,original_path));
    CREATE TABLE library_evidence(id TEXT PRIMARY KEY, entity_id TEXT NOT NULL,
        source_id TEXT NOT NULL, original_json TEXT NOT NULL);
    CREATE TABLE library_target_evidence(target_id TEXT NOT NULL REFERENCES library_targets(id),
        evidence_id TEXT NOT NULL REFERENCES library_evidence(id), PRIMARY KEY(target_id,evidence_id));
    CREATE TABLE library_unresolved_links(target_id TEXT NOT NULL REFERENCES library_targets(id),
        evidence_id TEXT NOT NULL, PRIMARY KEY(target_id,evidence_id));
    CREATE TABLE library_conflicts(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
        native_id TEXT NOT NULL, variants_json TEXT NOT NULL);
    CREATE INDEX library_target_search ON library_targets(domain,status,raw_identity);
    CREATE INDEX library_evidence_entity ON library_evidence(entity_id);
    CREATE INDEX library_evidence_source ON library_evidence(source_id);
    CREATE INDEX library_records_native ON library_records(native_id);
    CREATE INDEX library_reverse_evidence ON library_target_evidence(evidence_id);
    PRAGMA user_version=6;
    ''')
