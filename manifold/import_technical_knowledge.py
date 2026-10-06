"""Explicit REV2 ZIP integration into a new SQLite staging file; never startup migration."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import zipfile

from . import engineering_db, technical_schema

SCOPES = {'FULL_PART_NUMBER', 'BASE_MODEL', 'OPTION_FAMILY', 'SERIES', 'PRODUCT_FAMILY'}
REQUIRED = {
    'normalized/GLOBAL_CARTRIDGE_TECHNICAL_MASTER.jsonl',
    'normalized/GLOBAL_FULL_PART_TO_BASE_MODEL.csv',
    'normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv',
    'normalized/MANUFACTURER_ALIAS_INDEX.csv',
    'evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl',
    'sources/GLOBAL_SOURCE_REGISTRY.csv', 'conflicts/GLOBAL_CARTRIDGE_CONFLICTS.csv',
    'reports/GLOBAL_COVERAGE.json', 'reports/GLOBAL_CONVERGENCE_AUDIT.json',
    'reports/GLOBAL_FINAL_AUDIT.md', 'reports/GLOBAL_FIELD_GAP_LEDGER.csv',
    'material/MATERIAL_MASTER.jsonl', 'material/MATERIAL_PROPERTY_EVIDENCE.jsonl',
    'material/MATERIAL_SURFACE_TREATMENT.jsonl', 'material/MATERIAL_STOCK_MASTER.csv',
    'material/MATERIAL_STOCK_EVIDENCE.jsonl', 'material/MATERIAL_SOURCE_REGISTRY.csv',
    'material/MATERIAL_CONFLICTS.csv', 'material/MATERIAL_COVERAGE.json',
    'material/MATERIAL_FINAL_AUDIT.md',
}
REV1_REQUIRED = {'00_manifest.json', 'data/relations/cartridge_cavity_relations.csv',
                 'master_ref/logical_cavity_master.csv', 'master_ref/physical_cavity_master.csv',
                 'master_ref/physical_to_logical_crosswalk.csv',
                 'data/source_supplement/logical_cavity_supplement.csv', 'master_ref/cavities_master.jsonl'}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def stable(*values):
    return hashlib.sha256(encode(values).encode()).hexdigest()[:32]


def text(value):
    return '' if value is None else value if isinstance(value, str) else encode(value)


def norm(value):
    return text(value).strip().casefold()


class Package:
    """Read-only archive with checked manifest, schemas and logical references."""
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.files = {}
        self.data = {}
        with zipfile.ZipFile(self.path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or len(names) > 150 or not REQUIRED <= set(names):
                raise ValueError('Technical ZIP has duplicate entries or lacks required files')
            if sum(row.file_size for row in archive.infolist()) > 1_200_000_000:
                raise ValueError('Technical ZIP exceeds the supported uncompressed size')
            manifest = list(csv.DictReader(io.StringIO(archive.read('MANIFEST_SHA256.csv').decode('utf-8-sig'))))
            if {row['archive_path'] for row in manifest} != set(names) - {'MANIFEST_SHA256.csv'}:
                raise ValueError('Manifest does not cover exactly the ZIP payload')
            for item in manifest:
                name = item['archive_path']
                data = archive.read(name)
                sha = hashlib.sha256(data).hexdigest()
                if len(data) != int(item['bytes']) or sha != item['sha256']:
                    raise ValueError(f'Manifest mismatch: {name}')
                fields = set()
                if name.endswith('.jsonl'):
                    rows = [json.loads(line) for line in data.decode('utf-8-sig').splitlines() if line.strip()]
                    fields = set(k for row in rows for k in row)
                elif name.endswith('.csv'):
                    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
                    fields = set(reader.fieldnames or [])
                    rows = list(reader)
                    if any(None in row or any(v is None for v in row.values()) for row in rows):
                        raise ValueError(f'Malformed CSV: {name}')
                elif name.endswith('.json'):
                    rows = json.loads(data)
                    fields = set(rows) if isinstance(rows, dict) else set()
                else:
                    rows = None
                self.files[name] = dict(path=str(self.path) + '!/' + name, size=len(data), sha256=sha,
                                        record_count=len(rows) if isinstance(rows, list) else 1, fields=sorted(fields))
                if rows is not None:
                    self.data[name] = rows
        self.evidence = {'cartridge': {}, 'material': {}}
        self.observations = []
        self.duplicates = 0
        self.stock_ids = []
        self.stock_aliases = defaultdict(set)
        datasets = [('cartridge', 'evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl'),
                    ('cartridge', 'sun/SUN_PARAMETER_EVIDENCE.jsonl'),
                    ('cartridge', 'sun/SUN_IDENTITY_EVIDENCE.jsonl'),
                    ('cartridge', 'evidence/SOURCE_REVIEW_EVIDENCE.jsonl'),
                    ('material', 'material/MATERIAL_PROPERTY_EVIDENCE.jsonl'),
                    ('material', 'material/MATERIAL_STOCK_EVIDENCE.jsonl')]
        for domain, name in datasets:
            seen = {}
            for row in self.get(name):
                identifier = row.get('evidence_id')
                if not identifier or not row.get('property'):
                    raise ValueError(f'Evidence lacks ID/property: {name}')
                if name == 'material/MATERIAL_STOCK_EVIDENCE.jsonl':
                    # Export IDs omit thickness encoded in notes. Preserve each complete
                    # observation under a deterministic key; the original ID stays in raw JSON.
                    internal_id = 'stock_ev_' + stable(row)
                    self.stock_ids.append(internal_id)
                    self.stock_aliases[identifier].add(internal_id)
                    identifier = internal_id
                if identifier in seen:
                    if row != seen[identifier]:
                        raise ValueError(f'Conflicting duplicate evidence: {identifier}')
                    self.duplicates += 1
                    continue
                seen[identifier] = row
                self.observations.append((domain, identifier, name, row))
                if identifier in self.evidence[domain]:
                    previous = self.evidence[domain][identifier]
                    # Independent identity ledgers may have more detailed identity notes.
                    for field in ('property', 'raw_value', 'raw_unit', 'normalized_value', 'normalized_unit', 'scope'):
                        if previous.get(field, '') != row.get(field, ''):
                            raise ValueError(f'Conflicting cross-dataset evidence: {identifier}/{field}')
                else:
                    self.evidence[domain][identifier] = row
        self.sources = {'cartridge': {}, 'material': {}}
        self.aliases = {'cartridge': {}, 'material': {}}
        for domain, name in [('cartridge', 'sources/GLOBAL_SOURCE_REGISTRY.csv'),
                             ('cartridge', 'sun/SUN_SOURCE_REGISTRY.csv'),
                             ('material', 'material/MATERIAL_SOURCE_REGISTRY.csv')]:
            for row in self.get(name):
                sid = row['source_id']
                self.sources[domain].setdefault(sid, row)
                for alias in [sid, row.get('source_id_original'), *json.loads(row.get('alternate_source_ids_json') or '[]')]:
                    if alias:
                        self.aliases[domain][alias] = sid
        for row in self.get('sources/SOURCE_ID_ALIAS_INDEX.csv'):
            if row['canonical_source_id'] not in self.sources['cartridge']:
                raise ValueError('Source alias target is missing')
            self.aliases['cartridge'][row['evidence_source_id']] = row['canonical_source_id']
        self.validate()

    def get(self, name):
        return self.data.get(name, [])

    def validate(self):
        for domain, evidence in self.evidence.items():
            for identifier, row in evidence.items():
                if domain == 'cartridge' and row.get('scope') not in SCOPES:
                    raise ValueError(f'Illegal parameter scope: {identifier}')
                for sid in [row.get('source_id'), *(row.get('source_ids') or [])]:
                    if sid and sid not in self.aliases[domain]:
                        raise ValueError(f'Unresolved source: {identifier}/{sid}')
                if row.get('source_evidence_id') and row['source_evidence_id'] not in evidence:
                    raise ValueError(f'Unresolved original evidence: {identifier}')
                confidence = row.get('confidence')
                if confidence not in (None, '') and not 0 <= float(confidence) <= 1:
                    raise ValueError(f'Invalid confidence: {identifier}')
        for domain, name in [('cartridge', 'normalized/GLOBAL_CARTRIDGE_TECHNICAL_MASTER.jsonl'),
                             ('material', 'material/MATERIAL_MASTER.jsonl')]:
            for row in self.get(name):
                for eid in row.get('evidence_ids', []):
                    if eid not in self.evidence[domain]:
                        raise ValueError(f'Unresolved master evidence: {eid}')
        for domain, name in [('cartridge', 'conflicts/GLOBAL_CARTRIDGE_CONFLICTS.csv'),
                             ('material', 'material/MATERIAL_CONFLICTS.csv')]:
            for row in self.get(name):
                for side in ('a', 'b'):
                    ids = json.loads(row.get(f'evidence_{side}_ids_json') or '[]')
                    if not ids or any(not self.resolve_evidence(domain, eid) for eid in ids):
                        raise ValueError(f'Unresolved conflict evidence: {row["entity_id"]}/{side}')
                preferred = row.get('preferred_evidence_id')
                if preferred and preferred not in self.evidence[domain]:
                    raise ValueError('Invalid declared conflict preference')
        targets = self.get('normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv')
        if any(not row.get('technical_disposition') or not row.get('research_stage') or
               row['research_stage'] in ('NOT_STARTED', 'SEED_ONLY') for row in targets):
            raise ValueError('Incomplete target disposition/research stage')
        actual = dict(Counter(row['technical_disposition'] for row in targets))
        for name in ('reports/GLOBAL_COVERAGE.json', 'reports/GLOBAL_CONVERGENCE_AUDIT.json'):
            audit = self.get(name)
            if audit['target_identities'] != len(targets) or audit['target_disposition_counts'] != actual:
                raise ValueError(f'Target audit disagreement: {name}')
        if self.get('reports/GLOBAL_CONVERGENCE_AUDIT.json').get('result') != 'RESEARCH_CONVERGED':
            raise ValueError('Global research is not converged')
        for row in self.get('material/MATERIAL_STOCK_EVIDENCE.jsonl'):
            if row['source_url'] not in {r.get('url') for r in self.sources['material'].values()}:
                raise ValueError(f'Unregistered material stock URL: {row["evidence_id"]}')
        stock = self.get('material/MATERIAL_STOCK_MASTER.csv')
        stock_evidence = self.get('material/MATERIAL_STOCK_EVIDENCE.jsonl')
        if len(stock) != len(stock_evidence) or any(
                norm(row['material']) != norm(evidence['entity_id']) or row['source_url'] != evidence['source_url'] or
                {key: row[key] for key in ('product_form','width','height','length','diameter','unit','stock_code','notes')} != json.loads(evidence['raw_value'])
                for row, evidence in zip(stock, stock_evidence)):
            raise ValueError('Material stock/evidence row identity mismatch')
        allowed_states = {'EVIDENCE_PRESENT_SCOPE_BOUND', 'NOT_REPORTED_IN_REVIEWED_SOURCE_SET',
                          'OFFICIAL_SEARCH_EXHAUSTED_NO_FIELD_VALUE', 'IDENTITY_AMBIGUOUS_NO_ATTRIBUTION',
                          'EVIDENCE_PRESENT', 'NOT_REPORTED', 'OFFICIAL_SEARCH_EXHAUSTED',
                          'IDENTITY_AMBIGUOUS', 'NOT_APPLICABLE', 'CONFLICT', 'SOURCE_BLOCKED'}
        if any(row['field_gap_state'] not in allowed_states for row in self.get('reports/GLOBAL_FIELD_GAP_LEDGER.csv')):
            raise ValueError('Unknown field-gap disposition')
        audit = self.get('reports/GLOBAL_CONVERGENCE_AUDIT.json')
        if audit.get('conflict_rows') != len(self.get('conflicts/GLOBAL_CARTRIDGE_CONFLICTS.csv')):
            raise ValueError('Conflict audit disagreement')

    def resolve_evidence(self, domain, identifier):
        if identifier in self.evidence[domain]:
            return identifier
        if domain == 'material' and identifier in self.stock_aliases:
            candidates = self.stock_aliases[identifier]
            if len(candidates) != 1:
                raise ValueError(f'Ambiguous stock evidence reference: {identifier}')
            return next(iter(candidates))
        return None


def preserved_tables(connection):
    """Digest all old domain data, including execution eligibility and custom definitions."""
    result = {}
    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        if name in technical_schema.TABLES or name.startswith('sqlite_'):
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        columns = connection.execute(f'PRAGMA table_info({quoted})').fetchall()
        order = ','.join(str(i+1) for i in range(len(columns)))
        h, count = hashlib.sha256(), 0
        for row in connection.execute(f'SELECT * FROM {quoted} ORDER BY {order}'):
            h.update((encode(tuple(row)) + '\n').encode())
            count += 1
        result[name] = dict(count=count, sha256=h.hexdigest())
    return result


def integrate(source: Path, package: Path, rev1: Path, output: Path | None = None, *, material_supplement: Path | None = None):
    source, rev1 = source.resolve(), rev1.resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(rev1) as archive:
        if not REV1_REQUIRED <= set(archive.namelist()) or archive.testzip():
            raise ValueError('Invalid REV1 ZIP')
        relation_count = sum(1 for _ in csv.DictReader(io.StringIO(
            archive.read('data/relations/cartridge_cavity_relations.csv').decode('utf-8-sig'))))
    research = Package(package)
    if material_supplement:
        from .material_supplement import read_supplement
        supplement_data,supplement_sha=read_supplement(material_supplement)
        if supplement_data.get('base_rev2_sha256')!=research.sha256:raise ValueError('Material supplement base package mismatch')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        source_version = original.execute('PRAGMA user_version').fetchone()[0]
        if source_version not in (3, 4, engineering_db.SCHEMA_VERSION):
            raise ValueError('Explicit technical integration requires a supported schema v3/v4/v5 source')
        if source_version >= 4:
            engineering_db.validate_database(source, schema_version=source_version)
        targets = {(norm(m), norm(code)): cid for cid, m, code in original.execute('SELECT id,manufacturer,model FROM cartridges')}
        package_targets = {(norm(row['manufacturer']), norm(row['cartridge_part_number'])) for row in research.get('normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv')}
        missing_targets = package_targets - set(targets)
        if missing_targets:
            raise ValueError(f'Technical targets missing from the existing Cartridge identity set: {sorted(missing_targets)}')
        before = preserved_tables(original)
        old_materials = original.execute('SELECT * FROM materials ORDER BY id').fetchall()
        report = dict(source_path=str(source), source_sha256=source_hash, source_schema=source_version,
                      package_path=str(research.path), package_sha256=research.sha256,
                      rev1_path=str(rev1), rev1_sha256=hashlib.sha256(rev1.read_bytes()).hexdigest(),
                      rev1_relation_count=relation_count, files=research.files,
                      dispositions=dict(Counter(row['technical_disposition'] for row in research.get('normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv'))),
                      input_evidence_rows=len(research.get('evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl')),
                      identical_duplicate_rows=research.duplicates, preserved_before=before)
        report.update(technical_target_count=len(package_targets), current_cartridge_count=len(targets),
                      extra_relation_only_count=len(set(targets)-package_targets), missing_technical_target_count=0)
        report['stock_original_id_collision_groups'] = sum(len(ids) > 1 for ids in research.stock_aliases.values())
        report['stock_stable_internal_ids'] = len(set(research.stock_ids))
        if output is None:
            return report | {'validation': 'PASS', 'staging_created': False}
        output = output.resolve()
        if output == source or output.exists():
            raise ValueError('Output must be a new staging path; an existing output is never overwritten')
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(output)) as db:
                original.backup(db)
                db.execute('PRAGMA foreign_keys=ON')
                if source_version == 3:
                    technical_schema.initialize(db)
                else:
                    # Rebuild the knowledge layer in the NEW clone only. Keep the
                    # current corrected MDTools/REV1 engineering definitions intact.
                    for table in reversed(technical_schema.TABLES):
                        db.execute(f'DELETE FROM {table}')
                if source_version < 5:
                    from .relation_schema import initialize as initialize_relations
                    initialize_relations(db)
                _import(db, research, targets)
                if material_supplement:
                    from .material_supplement import apply_supplement
                    report['core_material_supplement']=apply_supplement(db,material_supplement,research.sha256)
                from .engineering_facts import promote_materials
                report['material_promotion'] = promote_materials(db,refresh_metadata=bool(material_supplement))
                after = preserved_tables(db)
                if {k:after[k] for k in before if k!='materials'} != {k:v for k,v in before.items() if k!='materials'}:
                    raise ValueError('Technical import changed existing engineering domain data')
                for row in old_materials:
                    actual=db.execute('SELECT * FROM materials WHERE id=?', (row[0],)).fetchone()
                    reviewed=next((m for m in report['material_promotion'] if m['selectable'] and m['runtime_id']==row[0]),None)
                    expected=(row[0],reviewed['display_name'],reviewed['material_family'],row[3]) if material_supplement and reviewed else row
                    if actual != expected:
                        raise ValueError('Existing runtime material changed during promotion')
                if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('Staging integrity/foreign-key check failed')
                if source_hash != hashlib.sha256(source.read_bytes()).hexdigest():
                    raise ValueError('Production source changed during integration')
                report.update(preserved_after=after, schema_version=engineering_db.SCHEMA_VERSION, validation='PASS',
                              counts={table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in technical_schema.TABLES})
                report['counts']['technical_import_batches'] = 1
                db.execute('INSERT INTO technical_import_batches VALUES (?,?,?,?,?,?)',
                           ('rev2_' + research.sha256[:24], research.path.name, research.sha256,
                            text(research.get('reports/GLOBAL_CONVERGENCE_AUDIT.json').get('audit_date')),
                            datetime.now(timezone.utc).isoformat(), encode(report)))
                db.commit()
            engineering_db.validate_database(output)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    return report | {'output_path': str(output), 'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def _import(db, package, targets):
    manufacturer_alias = {}
    for row in package.get('normalized/MANUFACTURER_ALIAS_INDEX.csv'):
        if row.get('status') == 'VERIFIED_ALIAS':
            manufacturer_alias[norm(row['manufacturer_alias'])] = norm(row['canonical_manufacturer'])
    def manufacturer(value):
        return manufacturer_alias.get(norm(value), norm(value))
    exact, base_targets, identities = defaultdict(set), defaultdict(set), {}
    for (maker, code), cid in targets.items():
        exact[(manufacturer(maker), code)].add(cid)
    maps = defaultdict(list)
    for row in package.get('normalized/GLOBAL_FULL_PART_TO_BASE_MODEL.csv'):
        maps[(manufacturer(row['manufacturer']), norm(row['full_part_number']))].append(row)
    for row in package.get('sun/SUN_FULL_PART_TO_BASE_MODEL.csv'):
        maps[(manufacturer('Sun Hydraulics'), norm(row['full_part_number']))].append(row)
    masters = defaultdict(list)
    for row in package.get('normalized/GLOBAL_CARTRIDGE_TECHNICAL_MASTER.jsonl'):
        masters[(manufacturer(row['manufacturer']), norm(row.get('full_part_number') or row.get('normalized_full_part_number') or row.get('base_model')))].append(row)
    for row in package.get('normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv'):
        key = (manufacturer(row['manufacturer']), norm(row['cartridge_part_number']))
        cid = targets[(norm(row['manufacturer']), norm(row['cartridge_part_number']))]
        associations = maps[key]
        bases = {r.get('base_model') or r.get('base_model_or_spec_sheet') for r in associations} - {None, ''}
        records = masters[key]
        bases.update(r['base_model'] for r in records if r.get('base_model'))
        base = next(iter(bases)) if len(bases) == 1 else ''
        series = next((r.get('series') for r in records + associations if r.get('series')), '')
        family = next((r.get('product_family') for r in records + associations if r.get('product_family')), '')
        original = dict(disposition=row, normalization=associations, master_records=records)
        db.execute('INSERT INTO technical_identities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('cartridge', cid, cid, None, row['manufacturer'], row['cartridge_part_number'], base,
                    series, family, row['technical_disposition'], row['research_stage'], encode(original)))
        identities[cid] = row['technical_disposition']
        if base and row['technical_disposition'] not in ('IDENTITY_AMBIGUOUS', 'RELATION_SOURCE_ONLY'):
            base_targets[(key[0], norm(base))].add(cid)
    material_aliases = defaultdict(set)
    for row in package.get('material/MATERIAL_MASTER.jsonl'):
        mid = row['material_id']
        db.execute('INSERT INTO technical_identities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('material', mid, None, None, '', row['canonical_grade'], row['canonical_grade'],
                    row.get('temper_condition', ''), row.get('material_family', ''), row['collection_status'], '', encode(row)))
        for alias in [mid, row['canonical_grade'], *row.get('aliases', []), row['canonical_grade'] + '-' + row.get('temper_condition', '')]:
            material_aliases[norm(alias)].add(mid)
    urls = defaultdict(set)
    for domain, sources in package.sources.items():
        for sid, row in sources.items():
            url = row.get('canonical_url') or row.get('url') or ''
            db.execute('INSERT INTO technical_sources VALUES (?,?,?,?,?,?)',
                       (domain, sid, row.get('source_name') or row.get('title') or '', url, row.get('sha256', ''), encode(row)))
            urls[(domain, url)].add(sid)
        db.executemany('INSERT INTO technical_source_aliases VALUES (?,?,?)',
                       ((domain, alias, sid) for alias, sid in package.aliases[domain].items()))
    links = set()
    by_evidence = defaultdict(set)
    classes = {}
    for domain, evidence in package.evidence.items():
        for eid, row in evidence.items():
            entity = row.get('cartridge_part_number') or row.get('entity_id') or ''
            kind = ('source_review' if row.get('evidence_class') == 'SOURCE_REGISTRY_INSPECTION_RECORD' else
                    'stock' if row.get('entity_type') == 'MATERIAL_STOCK_LISTING' else
                    'identity' if 'IDENTITY' in row.get('entity_type', '') or row['property'].endswith('_identity') else 'parameter')
            classes[(domain, eid)] = kind
            db.execute('INSERT INTO technical_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (domain, eid, entity, row.get('manufacturer', 'Sun Hydraulics' if eid.startswith('EV-SUN') else ''),
                        row['property'], text(row.get('raw_value', row.get('value'))), text(row.get('raw_unit', row.get('unit'))),
                        encode(row.get('normalized_value')), text(row.get('normalized_unit')), text(row.get('condition')),
                        text(row.get('scope')), text(row.get('scope_original', row.get('scope'))), text(row.get('scope_detail')),
                        text(row.get('applicable_option')), kind, encode(row)))
            source_ids = {package.aliases[domain][sid] for sid in [row.get('source_id'), *(row.get('source_ids') or [])] if sid}
            if not source_ids:
                source_ids = urls.get((domain, row.get('source_url', '')), set())
            db.executemany('INSERT INTO technical_evidence_sources VALUES (?,?,?)', ((domain, eid, sid) for sid in source_ids))
            if domain == 'cartridge':
                key = (manufacturer(row.get('manufacturer', 'Sun Hydraulics' if eid.startswith('EV-SUN') else '')), norm(entity))
                if key in exact:
                    links.update((domain, cid, eid, 'EXACT_IDENTITY') for cid in exact[key])
                if row.get('scope') != 'FULL_PART_NUMBER' and kind != 'source_review':
                    links.update((domain, cid, eid, 'EXPLICIT_BASE_MAPPING') for cid in base_targets[key])
            elif kind != 'stock':
                links.update((domain, mid, eid, 'EXACT_RESEARCH_IDENTITY') for mid in material_aliases[norm(entity)])
    db.executemany('INSERT INTO technical_evidence_observations VALUES (?,?,?,?)',
                   ((domain, eid, dataset, encode(row)) for domain, eid, dataset, row in package.observations))
    # The package's own explicit master references add evidence; no cavity/name inference.
    for row in package.get('normalized/GLOBAL_CARTRIDGE_TECHNICAL_MASTER.jsonl'):
        key = (manufacturer(row['manufacturer']), norm(row.get('full_part_number') or row.get('normalized_full_part_number') or row.get('base_model')))
        if key in exact:
            links.update(('cartridge', cid, eid, 'EXPLICIT_MASTER_REFERENCE') for cid in exact[key] for eid in row.get('evidence_ids', []))
    # One deterministic attribution per edge, with direct identity taking precedence.
    unique_links = {}
    for domain, identity, eid, attribution in sorted(links):
        unique_links.setdefault((domain, identity, eid), attribution)
        by_evidence[(domain, eid)].add(identity)
    db.executemany('INSERT INTO technical_identity_evidence VALUES (?,?,?,?)', ((*key, value) for key, value in unique_links.items()))
    for domain, name in [('cartridge', 'conflicts/GLOBAL_CARTRIDGE_CONFLICTS.csv'), ('material', 'material/MATERIAL_CONFLICTS.csv')]:
        for row in package.get(name):
            conflict_id = row.get('conflict_id') or 'conflict_' + stable(domain, row)
            db.execute('INSERT INTO technical_conflicts VALUES (?,?,?,?,?,?,?,?,?)',
                       (domain, conflict_id, row['entity_id'], row['property'], row['conflict_type'], row['resolution'],
                        row['evidence_link_status'], row.get('preferred_evidence_id') or None, encode(row)))
            related = set()
            for side in ('a', 'b'):
                for original_id in set(json.loads(row[f'evidence_{side}_ids_json'])):
                    eid = package.resolve_evidence(domain, original_id)
                    db.execute('INSERT INTO technical_conflict_evidence VALUES (?,?,?,?)', (domain, conflict_id, side, eid))
                    evidence_row = package.evidence[domain][eid]
                    evidence_entity = evidence_row.get('entity_id') or evidence_row.get('cartridge_part_number')
                    if domain == 'material' or norm(evidence_entity) == norm(row['entity_id']):
                        related.update(by_evidence[(domain, eid)])
            if domain == 'material':
                related.update(material_aliases[norm(row['entity_id'])])
            else:
                key = (manufacturer(row.get('manufacturer')), norm(row['entity_id']))
                related.update(base_targets[key])
                if key in exact:
                    related.update(exact[key])
            db.executemany('INSERT INTO technical_identity_conflicts VALUES (?,?,?)', ((domain, identity, conflict_id) for identity in related))
    conflicts = {(domain, identity, prop) for domain, identity, prop in db.execute('''
        SELECT l.domain,l.identity_id,c.property FROM technical_identity_conflicts l
        JOIN technical_conflicts c ON c.domain=l.domain AND c.id=l.conflict_id''')}
    for (domain, identity, eid), attribution in unique_links.items():
        row = package.evidence[domain][eid]
        kind = classes[(domain, eid)]
        if kind != 'parameter' or identities.get(identity) in ('IDENTITY_AMBIGUOUS', 'RELATION_SOURCE_ONLY'):
            continue
        status = 'CONFLICT' if (domain, identity, row['property']) in conflicts else 'EVIDENCE_PRESENT'
        db.execute('INSERT INTO technical_values VALUES (?,?,?,?,?,?,?)',
                   (domain, 'value_' + stable(domain, identity, eid), identity, eid, row['property'], status, None))
    states = {'EVIDENCE_PRESENT_SCOPE_BOUND': 'EVIDENCE_PRESENT', 'NOT_REPORTED_IN_REVIEWED_SOURCE_SET': 'NOT_REPORTED',
              'OFFICIAL_SEARCH_EXHAUSTED_NO_FIELD_VALUE': 'OFFICIAL_SEARCH_EXHAUSTED', 'IDENTITY_AMBIGUOUS_NO_ATTRIBUTION': 'IDENTITY_AMBIGUOUS'}
    for row in package.get('reports/GLOBAL_FIELD_GAP_LEDGER.csv'):
        cid = targets[(norm(row['manufacturer']), norm(row['cartridge_part_number']))]
        raw_status = row['field_gap_state']
        status = states.get(raw_status, raw_status)
        if status not in ('EVIDENCE_PRESENT', 'NOT_REPORTED', 'OFFICIAL_SEARCH_EXHAUSTED', 'IDENTITY_AMBIGUOUS', 'NOT_APPLICABLE', 'CONFLICT', 'SOURCE_BLOCKED'):
            raise ValueError(f'Unknown field-gap status: {raw_status}')
        db.execute('INSERT INTO technical_field_status VALUES (?,?,?,?,?)', ('cartridge', cid, row['field_group'], status, encode(row)))
    for kind, name in [('treatment', 'material/MATERIAL_SURFACE_TREATMENT.jsonl'), ('stock', 'material/MATERIAL_STOCK_MASTER.csv')]:
        for index, row in enumerate(package.get(name)):
            rid = kind + '_' + stable(row)
            if kind == 'treatment':
                db.execute('INSERT INTO material_surface_treatments VALUES (?,?)', (rid, encode(row)))
            else:
                # Stock evidence and stock CSV are exported in the same stable row order.
                evidence_row = package.get('material/MATERIAL_STOCK_EVIDENCE.jsonl')[index]
                if norm(evidence_row['entity_id']) != norm(row['material']) or evidence_row['source_url'] != row['source_url']:
                    raise ValueError('Material stock/evidence row identity mismatch')
                stated = re.search(r'\b(LISTED_SIZE|LIVE_STOCK|UNKNOWN_AVAILABILITY)\b', row.get('notes', ''))
                explicit = row.get('availability_status') or row.get('stock_status') or (stated.group(1) if stated else '')
                note = row.get('notes', '').lower()
                availability = explicit or ('LIVE_STOCK' if 'dated' in note and 'in stock' in note else
                                             'LISTED_SIZE' if any(row.get(key) for key in ('width', 'height', 'length', 'diameter')) else 'UNKNOWN_AVAILABILITY')
                db.execute('INSERT INTO material_supplier_stock VALUES (?,?,?,?,?)', (rid, package.stock_ids[index], 'material', availability, encode(row)))
            # Browse association from an explicitly printed grade; never runtime stock admission.
            related = material_aliases[norm(row['material'])]
            if not related:
                for material in package.get('material/MATERIAL_MASTER.jsonl'):
                    grade = material['canonical_grade']
                    if re.search(r'(?<![A-Za-z0-9])' + re.escape(grade) + r'(?![A-Za-z0-9])', row['material'], re.I):
                        related.add(material['material_id'])
            db.executemany('INSERT INTO material_research_links VALUES (?,?,?,?,?,?)',
                           ((mid, 'material', rid, kind, rid if kind == 'treatment' else None,
                             rid if kind == 'stock' else None) for mid in related))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--knowledge-package', type=Path, required=True)
    parser.add_argument('--relationship-package', type=Path, required=True)
    parser.add_argument('--material-supplement', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = integrate(args.source, args.knowledge_package, args.relationship_package, args.output,material_supplement=args.material_supplement)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('files', 'preserved_before', 'preserved_after')}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
