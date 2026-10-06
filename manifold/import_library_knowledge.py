"""Explicit non-CAD Main Station injection into an untouched REV2 v5 clone.

Archive documents are data, never executable instructions. No runtime execution
definition is written by this importer. Every selected structured row is retained.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import hashlib
import io
import json
import re
from pathlib import Path, PurePosixPath
import sqlite3
import zipfile

from . import engineering_db, library_schema
from .replace_relation_knowledge import encode, file_hash, table_digests

BASE = 'baseline/knowledge_collection_v2/remaining_domains/'
INCREMENTS = {
    'CLOSURES_2026-10-06_REV04': ('Closures / Plugs', 'CLOSURES'),
    'PORTS_2026-10-06_REV03': ('External Ports', 'PORTS'),
    'THREADS_2026-10-05_RUN01': ('Thread Standards', 'THREADS'),
}
REVIEWED_SOURCE = '33f579801c38102011a3dbc55c0b9cfeb8c13a5434fcff8cd8260bc608fe27d2'
EXCLUDED_FOLDERS = {'assets', 'raw_sources', 'source_documents', 'reports'}


def decode_rows(path, data):
    text = data.decode('utf-8-sig')
    if path.endswith('.csv'):
        csv.field_size_limit(16 * 1024 * 1024)
        reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f'Invalid CSV header: {path}')
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError(f'Invalid CSV row shape: {path}')
    elif path.endswith('.jsonl'):
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif path.endswith('.json'):
        value = json.loads(text)
        rows = value if isinstance(value, list) else [value]
    else:
        raise ValueError(f'Non-structured dataset: {path}')
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f'Expected object rows: {path}')
    for row in rows:
        encode(row)  # Reject NaN/Infinity before storing.
    return rows


class LibraryPackage:
    def __init__(self, path):
        self.path = Path(path)
        self.sha256 = file_hash(path)
        self.datasets = {}
        self.aliases = defaultdict(list)
        self.meta = {}
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate archive paths')
            for n in names:
                if '\\' in n or n.startswith('/') or '..' in PurePosixPath(n).parts:
                    raise ValueError(f'Unsafe archive path: {n}')
            if z.testzip() is not None:
                raise ValueError('Archive CRC failed')
            manifest = json.loads(z.read('MANIFEST.json'))
            self.manifest = {r['archive_path']: r for r in manifest['files']}
            if len(self.manifest) != len(manifest['files']):
                raise ValueError('Duplicate manifest paths')
            for n, r in self.manifest.items():
                if n not in names or z.getinfo(n).file_size != int(r['bytes']):
                    raise ValueError(f'Manifest membership/size mismatch: {n}')
            def read(n):
                data = z.read(n)
                r = self.manifest.get(n)
                if r is None or hashlib.sha256(data).hexdigest() != r['sha256']:
                    raise ValueError(f'Structured file SHA mismatch: {n}')
                return decode_rows(n, data)
            for n in ['TRANSFER_SUMMARY.json', 'LIB_DATASET_INDEX.csv', 'LIB_DOMAIN_INVENTORY.csv',
                      'PROPOSED_AFTER_INTEGRATION_TARGET_QUEUE.csv', 'SOURCE_FILE_MAP.csv']:
                self.meta[n] = read(n)
            for row in self.meta['LIB_DATASET_INDEX.csv']:
                r = self.manifest.get(row['archive_path'])
                if r is None or r['sha256'] != row['sha256'] or int(r['bytes']) != int(row['bytes']):
                    raise ValueError('Dataset index disagrees with manifest')
            mapped = set()
            for r in self.meta['SOURCE_FILE_MAP.csv']:
                n = r['archive_path']; mr = self.manifest.get(n)
                if not mr or mr['sha256'] != r['sha256'] or int(mr['bytes']) != int(r['bytes']):
                    raise ValueError(f'Source mapping disagrees with manifest: {n}')
                mapped.add(n)
                self.aliases[n].append(r['original_workspace_path'])
            selected = {BASE+'HARD_GATES_TARGET_QUEUE_V2.csv', BASE+'HARD_GATES_DOMAIN_STATUS_V2.csv'}
            for n in sorted(mapped):
                parts = n.removeprefix(BASE).split('/')
                if n.startswith(BASE) and len(parts) == 2 and parts[0] not in EXCLUDED_FOLDERS:
                    if n.endswith(('.csv', '.jsonl')) or n.endswith(('COVERAGE.json', 'RECHECK.json')):
                        selected.add(n)
                if any(n.startswith('increments/'+run+'/') for run in INCREMENTS):
                    if n.endswith(('.csv', '.jsonl', '.json')):
                        selected.add(n)
            # Accepted Seal is audit-only, never a second evidence/status import.
            seal = 'accepted_seal_revision/MERGE_RECONCILIATION.json'
            if seal in self.manifest:
                self.meta[seal] = read(seal)
            for n in sorted(selected):
                if n not in mapped:
                    raise ValueError(f'Authoritative dataset missing from source map: {n}')
                self.datasets[n] = read(n)
            # Already installed specialized masters are reconciliation inputs only.
            for name in ['GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv', 'MATERIAL_MASTER.jsonl']:
                n='baseline/knowledge_collection_v2/normalized/'+name
                if n in self.manifest:
                    self.meta[n]=read(n)
            self.index_gap = sorted(selected - {r['archive_path'] for r in self.meta['LIB_DATASET_INDEX.csv']})


def native_id(row):
    return str(next((row[k] for k in ('evidence_id', 'source_id', 'target_id', 'entity_id',
                                      'conflict_id', 'product_id', 'id') if row.get(k)), ''))


def ids(value):
    if isinstance(value, list):
        return {str(v) for v in value if v}
    return {v.strip() for v in re.split(r'[|;]', str(value or '')) if v.strip()}


def build_plan(package):
    targets = {}
    for row in package.datasets[BASE+'HARD_GATES_TARGET_QUEUE_V2.csv']:
        if row['domain'] == 'CAD / Assets':
            continue
        if row['target_id'] in targets:
            raise ValueError('Duplicate baseline target ID')
        targets[row['target_id']] = dict(row)
    # Evidence/source canonical views use explicit precedence: unified baseline,
    # then designated latest increments. All differing versions stay inspectable.
    evidence, sources, versions = {}, {}, defaultdict(dict)
    duplicates = Counter()
    def add(kind, key, row, path):
        store = evidence if kind == 'evidence' else sources
        content = encode(row)
        versions[(kind, key)].setdefault(content, []).append(path)
        if key in store:
            duplicates[kind] += int(encode(store[key]) == content)
        store[key] = row
    paths = sorted(package.datasets, key=lambda n: (n.startswith('increments/'),
                                                  '/unified_evidence/' in n, n))
    for path in paths:
        for row in package.datasets[path]:
            if row.get('evidence_id') and ('EVIDENCE' in PurePosixPath(path).name):
                add('evidence', str(row['evidence_id']), row, path)
            if row.get('source_id') and ('SOURCE_REGISTRY' in PurePosixPath(path).name):
                add('source', str(row['source_id']), row, path)
    gates = {r['domain']: r for r in package.datasets[BASE+'HARD_GATES_DOMAIN_STATUS_V2.csv']}
    for run, (domain, prefix) in INCREMENTS.items():
        folder = 'increments/'+run+'/'
        disposition = package.datasets[folder+prefix+'_TARGET_DISPOSITION_PROPOSED.csv']
        wanted = {key for key, r in targets.items() if r['domain'] == domain}
        if len(disposition) != len(wanted) or {r['target_id'] for r in disposition} != wanted:
            raise ValueError(f'Incomplete increment target reconciliation: {run}')
        for row in disposition:
            old = targets[row['target_id']]
            if row['baseline_status'] != old['queue_status']:
                raise ValueError(f'Increment baseline status mismatch: {row["target_id"]}')
            refs = ids(row.get('evidence_ids'))
            missing = refs - evidence.keys()
            if row['proposed_status'] == 'VERIFIED' and (missing or not refs or not row.get('verification_scope')):
                raise ValueError(f'Unsupported VERIFIED increment: {row["target_id"]}; missing {sorted(missing)}')
            old.update(queue_status=row['proposed_status'], verification_scope=row.get('verification_scope', ''),
                       increment=run, increment_disposition=row,
                       evidence_ids='|'.join(sorted(ids(old.get('evidence_ids')) | refs)))
        progress = package.datasets[folder+prefix+'_PROGRESS.json'][0]
        recheck = next((rows[0] for n, rows in package.datasets.items()
                        if n.startswith(folder) and n.endswith(('GATE_A_RECHECK.json', 'GATE_C_RECHECK.json'))), {})
        gates[domain] = dict(latest_increment=run, progress=progress, recheck=recheck)
    expected = {r['target_id']: r for r in package.meta['PROPOSED_AFTER_INTEGRATION_TARGET_QUEUE.csv']
                if r['domain'] != 'CAD / Assets'}
    if targets.keys() != expected.keys():
        raise ValueError('Proposed queue target set disagrees with computed merge')
    differences = [key for key, row in targets.items() if row['queue_status'] != expected[key]['queue_status']]
    if differences:
        raise ValueError(f'Computed status disagrees with proposed queue: {differences}')
    return targets, evidence, sources, gates, versions, duplicates


def integrate(source, package_path, output, *, expected_source_sha=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'Rebuild target already exists: {output}')
    with closing(engineering_db._connect(source)) as original:
        engineering_db.validate_database(source, schema_version=5)
        if original.execute('PRAGMA user_version').fetchone()[0] != 5:
            raise ValueError('Main Station requires REV2 schema v5 source')
        source_hash = file_hash(source)
        if expected_source_sha and source_hash != expected_source_sha:
            raise ValueError('Reviewed REV2 source hash differs; stop before import')
        before = table_digests(original)
        package = package_path if isinstance(package_path, LibraryPackage) else LibraryPackage(package_path)
        targets, evidence, sources, gates, versions, duplicates = build_plan(package)
        reconciliation={}
        for domain, name, field in [('cartridge','GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv','cartridge_part_number'),
                                    ('material','MATERIAL_MASTER.jsonl','material_id')]:
            rows=package.meta.get('baseline/knowledge_collection_v2/normalized/'+name,[])
            if domain=='cartridge':
                from .import_technical_knowledge import norm
                existing={(norm(r[0]),norm(r[1])) for r in original.execute(
                    'SELECT manufacturer_original,full_part_number FROM technical_identities WHERE domain=?',(domain,))}
                keys={(norm(r['manufacturer']),norm(r.get(field,''))) for r in rows}
            else:
                existing={str(r[0]) for r in original.execute(
                    'SELECT id FROM technical_identities WHERE domain=?',(domain,))}
                keys={str(r.get(field,'')) for r in rows}
            reconciliation[domain]=dict(package_rows=len(rows),existing_rows=len(existing),
                matched_keys=len(keys & existing),package_only_keys=sorted(keys-existing),
                action='READ_ONLY_RECONCILIATION; specialized tables preserved, no reimport')
        batch_id = 'LIB:'+package.sha256
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(output)) as db:
                original.backup(db)
                library_schema.initialize(db)
                db.execute('PRAGMA foreign_keys=ON')
                with db:
                    db.execute('INSERT INTO library_import_batches VALUES (?,?,?,?)',
                               (batch_id, source_hash, package.sha256, '{}'))
                    seen_files = {}
                    for path, rows in sorted(package.datasets.items()):
                        meta = package.manifest[path]; sha = meta['sha256']
                        if sha not in seen_files:
                            dataset_id = 'DATA:'+sha; seen_files[sha] = dataset_id
                            domain = path.removeprefix(BASE).split('/')[0] if path.startswith(BASE) else path.split('/')[1]
                            role = 'increment' if path.startswith('increments/') else 'baseline'
                            db.execute('INSERT INTO library_datasets VALUES (?,?,?,?,?,?,?,?)',
                                       (dataset_id,path,sha,domain,role,int(meta['bytes']),len(rows),batch_id))
                            unique_rows = {hashlib.sha256(encode(r).encode()).hexdigest():r for r in rows}
                            db.executemany('INSERT INTO library_records VALUES (?,?,?,?)',
                                           ((dataset_id,key,native_id(r),encode(r)) for key,r in sorted(unique_rows.items())))
                        for alias in package.aliases[path]:
                            db.execute('INSERT OR IGNORE INTO library_dataset_aliases VALUES (?,?,?)',
                                       (seen_files[sha],path,alias))
                    db.executemany('INSERT INTO library_sources VALUES (?,?)',
                                   ((key,encode(r)) for key,r in sorted(sources.items())))
                    # Lightweight document localization only. No document bytes.
                    for row in package.meta['SOURCE_FILE_MAP.csv']:
                        if PurePosixPath(row['archive_path']).suffix.lower() in {'.step','.stp','.iges','.igs','.dwg','.dxf'}:
                            continue
                        db.execute('INSERT OR IGNORE INTO library_source_aliases VALUES (?,?,?,?)',
                            (row['archive_path'],row.get('original_absolute_path',row['original_workspace_path']),
                             row['sha256'],int(row['bytes'])))
                    db.executemany('INSERT INTO library_evidence VALUES (?,?,?,?)',
                                   ((key,str(r.get('entity_id','')),str(r.get('source_id','')),encode(r))
                                    for key,r in sorted(evidence.items())))
                    for key, r in sorted(targets.items()):
                        db.execute('INSERT INTO library_targets VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                                   (key,r['domain'],r['target_type'],r['raw_identity'],
                                    r.get('canonical_identity',''),r['queue_status'],r['current_disposition'],
                                    r.get('verification_scope',r.get('required_gate','')),encode(gates.get(r['domain'],{})),
                                    r.get('notes',''),encode(r)))
                        for eid in sorted(ids(r.get('evidence_ids'))):
                            table = 'library_target_evidence' if eid in evidence else 'library_unresolved_links'
                            db.execute(f'INSERT INTO {table} VALUES (?,?)',(key,eid))
                    for (kind,key), variants in sorted(versions.items()):
                        if len(variants)>1:
                            cid = hashlib.sha256((kind+'\n'+key).encode()).hexdigest()
                            db.execute('INSERT INTO library_conflicts VALUES (?,?,?,?)',
                                       (cid,kind,key,encode([dict(row=json.loads(v),datasets=paths)
                                                            for v,paths in sorted(variants.items())])))
                    after = table_digests(db, library_schema.TABLES)
                    if before != after:
                        raise ValueError('Protected runtime/relation/technical tables changed')
                    integrity = db.execute('PRAGMA integrity_check').fetchall()
                    foreign_keys = db.execute('PRAGMA foreign_key_check').fetchall()
                    if integrity != [('ok',)] or foreign_keys:
                        raise ValueError(f'Integrity/FK failed: {integrity}, {foreign_keys}')
                    domain_counts = {}
                    for domain in sorted({r['domain'] for r in targets.values()}):
                        domain_targets = [r for r in targets.values() if r['domain']==domain]
                        linked = set().union(*(ids(r.get('evidence_ids')) for r in domain_targets))
                        source_ids = {str(evidence[e].get('source_id','')) for e in linked if e in evidence} - {''}
                        domain_counts[domain] = dict(targets=len(domain_targets),statuses=dict(Counter(r['queue_status'] for r in domain_targets)),
                            evidence=len(linked & evidence.keys()),sources=len(source_ids),unresolved=len(linked-evidence.keys()),
                            id_conflicts=sum(1 for (kind,key),v in versions.items() if len(v)>1 and
                                             ((kind=='evidence' and key in linked) or (kind=='source' and key in source_ids))),
                            gate=gates.get(domain,{}))
                    report = dict(source=str(source),source_schema=5,source_sha256=source_hash,
                        source_bytes=source.stat().st_size,package=str(package.path.resolve()),package_sha256=package.sha256,
                        output=str(output),schema=6,protected_before=before,protected_after=after,
                        domains=domain_counts,active_targets=len(targets),statuses=dict(Counter(r['queue_status'] for r in targets.values())),
                        specialized_reconciliation=reconciliation,
                        datasets=len(seen_files),evidence=len(evidence),sources=len(sources),identical_id_dedup=dict(duplicates),
                        id_conflicts=sum(len(v)>1 for v in versions.values()),index_gap=package.index_gap,
                        increments=list(INCREMENTS),seal_duplicated=False,
                        cad_targets_excluded=sum(r['domain']=='CAD / Assets' for r in package.meta['PROPOSED_AFTER_INTEGRATION_TARGET_QUEUE.csv']),
                        raw_binary_bytes_imported=0,cad_binary_bytes_imported=0,integrity='ok',foreign_keys=0)
                    db.execute('UPDATE library_import_batches SET report_json=? WHERE id=?',(encode(report),batch_id))
            engineering_db.validate_database(output, schema_version=6)
            if file_hash(source) != source_hash:
                raise ValueError('Read-only source file changed')
            report.update(output_sha256=file_hash(output),output_bytes=output.stat().st_size)
            return report
        except BaseException:
            output.unlink(missing_ok=True)  # Only this exclusively created staging target.
            raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--expected-source-sha',default=REVIEWED_SOURCE)
    args=parser.parse_args()
    report=integrate(args.source,args.package,args.output,expected_source_sha=args.expected_source_sha)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(encode({k:report[k] for k in ('active_targets','statuses','datasets','evidence','sources','id_conflicts','output_bytes')}))


if __name__=='__main__':
    main()
