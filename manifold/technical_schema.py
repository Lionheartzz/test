"""Schema v4 knowledge layer. Called only by explicit initialization/import."""
import sqlite3

TABLES = {
    'technical_import_batches': {'id', 'package_sha256', 'report_json'},
    'technical_identities': {'domain', 'id', 'cartridge_id', 'material_id', 'disposition', 'original_json'},
    'technical_sources': {'domain', 'id', 'original_json'},
    'technical_source_aliases': {'domain', 'alias', 'source_id'},
    'technical_evidence': {'domain', 'id', 'property', 'scope', 'scope_original', 'evidence_class', 'original_json'},
    'technical_evidence_sources': {'domain', 'evidence_id', 'source_id'},
    'technical_evidence_observations': {'domain', 'evidence_id', 'dataset', 'original_json'},
    'technical_identity_evidence': {'domain', 'identity_id', 'evidence_id', 'attribution'},
    'technical_values': {'domain', 'id', 'identity_id', 'evidence_id', 'property', 'status', 'preferred_evidence_id'},
    'technical_field_status': {'domain', 'identity_id', 'field_group', 'status', 'original_json'},
    'technical_conflicts': {'domain', 'id', 'entity_id', 'property', 'resolution', 'original_json'},
    'technical_conflict_evidence': {'domain', 'conflict_id', 'side', 'evidence_id'},
    'technical_identity_conflicts': {'domain', 'identity_id', 'conflict_id'},
    'material_surface_treatments': {'id', 'original_json'},
    'material_supplier_stock': {'id', 'original_json', 'availability'},
    'material_research_links': {'material_id', 'record_id', 'kind', 'treatment_id', 'stock_id'},
}


def initialize(connection: sqlite3.Connection):
    connection.executescript('''
    CREATE TABLE technical_import_batches(
        id TEXT PRIMARY KEY, package_name TEXT NOT NULL, package_sha256 TEXT NOT NULL,
        generated_at TEXT NOT NULL, imported_at TEXT NOT NULL, report_json TEXT NOT NULL);
    CREATE TABLE technical_identities(
        domain TEXT NOT NULL CHECK(domain IN ('cartridge','material')), id TEXT NOT NULL,
        cartridge_id TEXT REFERENCES cartridges(id), material_id TEXT REFERENCES materials(id),
        manufacturer_original TEXT NOT NULL, full_part_number TEXT NOT NULL, base_model TEXT NOT NULL,
        series TEXT NOT NULL, product_family TEXT NOT NULL, disposition TEXT NOT NULL,
        research_stage TEXT NOT NULL, original_json TEXT NOT NULL,
        CHECK((domain='cartridge' AND cartridge_id=id AND material_id IS NULL) OR
              (domain='material' AND cartridge_id IS NULL)), PRIMARY KEY(domain,id));
    CREATE TABLE technical_sources(
        domain TEXT NOT NULL, id TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
        sha256 TEXT NOT NULL, original_json TEXT NOT NULL, PRIMARY KEY(domain,id));
    CREATE TABLE technical_source_aliases(
        domain TEXT NOT NULL, alias TEXT NOT NULL, source_id TEXT NOT NULL,
        PRIMARY KEY(domain,alias), FOREIGN KEY(domain,source_id) REFERENCES technical_sources(domain,id));
    CREATE TABLE technical_evidence(
        domain TEXT NOT NULL, id TEXT NOT NULL, entity_id TEXT NOT NULL, manufacturer TEXT NOT NULL,
        property TEXT NOT NULL, raw_value TEXT NOT NULL, raw_unit TEXT NOT NULL,
        normalized_value_json TEXT NOT NULL, normalized_unit TEXT NOT NULL,
        condition TEXT NOT NULL, scope TEXT NOT NULL, scope_original TEXT NOT NULL,
        scope_detail TEXT NOT NULL, applicable_option TEXT NOT NULL,
        evidence_class TEXT NOT NULL CHECK(evidence_class IN ('parameter','identity','source_review','stock')),
        original_json TEXT NOT NULL, PRIMARY KEY(domain,id));
    CREATE TABLE technical_evidence_sources(
        domain TEXT NOT NULL, evidence_id TEXT NOT NULL, source_id TEXT NOT NULL,
        PRIMARY KEY(domain,evidence_id,source_id),
        FOREIGN KEY(domain,evidence_id) REFERENCES technical_evidence(domain,id),
        FOREIGN KEY(domain,source_id) REFERENCES technical_sources(domain,id));
    CREATE TABLE technical_evidence_observations(
        domain TEXT NOT NULL, evidence_id TEXT NOT NULL, dataset TEXT NOT NULL, original_json TEXT NOT NULL,
        PRIMARY KEY(domain,evidence_id,dataset),
        FOREIGN KEY(domain,evidence_id) REFERENCES technical_evidence(domain,id));
    CREATE TABLE technical_identity_evidence(
        domain TEXT NOT NULL, identity_id TEXT NOT NULL, evidence_id TEXT NOT NULL, attribution TEXT NOT NULL,
        PRIMARY KEY(domain,identity_id,evidence_id),
        FOREIGN KEY(domain,identity_id) REFERENCES technical_identities(domain,id),
        FOREIGN KEY(domain,evidence_id) REFERENCES technical_evidence(domain,id));
    CREATE TABLE technical_values(
        domain TEXT NOT NULL, id TEXT NOT NULL, identity_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
        property TEXT NOT NULL, status TEXT NOT NULL, preferred_evidence_id TEXT,
        PRIMARY KEY(domain,id), FOREIGN KEY(domain,identity_id) REFERENCES technical_identities(domain,id),
        FOREIGN KEY(domain,evidence_id) REFERENCES technical_evidence(domain,id),
        FOREIGN KEY(domain,preferred_evidence_id) REFERENCES technical_evidence(domain,id));
    CREATE TABLE technical_field_status(
        domain TEXT NOT NULL, identity_id TEXT NOT NULL, field_group TEXT NOT NULL,
        status TEXT NOT NULL, original_json TEXT NOT NULL, PRIMARY KEY(domain,identity_id,field_group),
        FOREIGN KEY(domain,identity_id) REFERENCES technical_identities(domain,id));
    CREATE TABLE technical_conflicts(
        domain TEXT NOT NULL, id TEXT NOT NULL, entity_id TEXT NOT NULL, property TEXT NOT NULL,
        conflict_type TEXT NOT NULL, resolution TEXT NOT NULL, link_status TEXT NOT NULL,
        preferred_evidence_id TEXT, original_json TEXT NOT NULL, PRIMARY KEY(domain,id),
        FOREIGN KEY(domain,preferred_evidence_id) REFERENCES technical_evidence(domain,id));
    CREATE TABLE technical_conflict_evidence(
        domain TEXT NOT NULL, conflict_id TEXT NOT NULL, side TEXT NOT NULL CHECK(side IN ('a','b')),
        evidence_id TEXT NOT NULL, PRIMARY KEY(domain,conflict_id,side,evidence_id),
        FOREIGN KEY(domain,conflict_id) REFERENCES technical_conflicts(domain,id),
        FOREIGN KEY(domain,evidence_id) REFERENCES technical_evidence(domain,id));
    CREATE TABLE technical_identity_conflicts(
        domain TEXT NOT NULL, identity_id TEXT NOT NULL, conflict_id TEXT NOT NULL,
        PRIMARY KEY(domain,identity_id,conflict_id),
        FOREIGN KEY(domain,identity_id) REFERENCES technical_identities(domain,id),
        FOREIGN KEY(domain,conflict_id) REFERENCES technical_conflicts(domain,id));
    CREATE TABLE material_surface_treatments(id TEXT PRIMARY KEY, original_json TEXT NOT NULL);
    CREATE TABLE material_supplier_stock(
        id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL, domain TEXT NOT NULL DEFAULT 'material' CHECK(domain='material'),
        availability TEXT NOT NULL, original_json TEXT NOT NULL,
        FOREIGN KEY(domain,evidence_id) REFERENCES technical_evidence(domain,id));
    CREATE TABLE material_research_links(
        material_id TEXT NOT NULL, domain TEXT NOT NULL DEFAULT 'material' CHECK(domain='material'),
        record_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('treatment','stock')),
        treatment_id TEXT REFERENCES material_surface_treatments(id), stock_id TEXT REFERENCES material_supplier_stock(id),
        CHECK((kind='treatment' AND treatment_id=record_id AND stock_id IS NULL) OR
              (kind='stock' AND stock_id=record_id AND treatment_id IS NULL)),
        PRIMARY KEY(material_id,record_id,kind), FOREIGN KEY(domain,material_id) REFERENCES technical_identities(domain,id));
    CREATE INDEX technical_identity_search ON technical_identities(domain,base_model,disposition);
    CREATE INDEX technical_evidence_property ON technical_evidence(domain,property,scope,id);
    CREATE INDEX technical_evidence_source ON technical_evidence_sources(domain,source_id,evidence_id);
    CREATE INDEX technical_identity_evidence_reverse ON technical_identity_evidence(domain,evidence_id,identity_id);
    CREATE INDEX technical_value_identity ON technical_values(domain,identity_id,property,id);
    CREATE INDEX technical_conflict_identity ON technical_identity_conflicts(domain,identity_id,conflict_id);
    CREATE INDEX technical_conflict_property ON technical_conflicts(domain,entity_id,property);
    PRAGMA user_version=4;
    ''')
