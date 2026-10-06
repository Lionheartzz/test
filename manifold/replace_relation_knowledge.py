"""Explicit REV2 relation replacement in a new clone, preserving all technical data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
import sqlite3
import zipfile

from . import engineering_db, relation_schema
from .import_mdtools import stable_id
from .knowledge_import import RELATION_FIELDS, identity_key, logical_key, master_id, import_knowledge, resolve_relation

REVIEWED_SHA = 'de7089dede165182500fd7a30ecdc31b86ae98099192cb27a5d51ebffcf2b372'
RELATION_TABLES = {'cartridge_cavities','cartridge_cavity_evidence','cartridge_cavity_evidence_links','kb_import_batches',*relation_schema.TABLES}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def table_digests(db, exclude=()):
    result = {}
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        if table in exclude or table.startswith('sqlite_'):
            continue
        quoted = '"'+table.replace('"','""')+'"'
        columns = db.execute(f'PRAGMA table_info({quoted})').fetchall()
        primary = sorted((r[5], i+1) for i,r in enumerate(columns) if r[5])
        order = ','.join(str(i) for _,i in primary) or ','.join(str(i+1) for i in range(len(columns)))
        digest, count = hashlib.sha256(), 0
        for row in db.execute(f'SELECT * FROM {quoted} ORDER BY {order}'):
            digest.update((encode(tuple(row))+'\n').encode());count += 1
        result[table] = dict(count=count, sha256=digest.hexdigest())
    return result


class RelationPackage:
    def __init__(self, path, *, rev2=False):
        self.path = Path(path).resolve();self.sha256 = file_hash(self.path)
        required = {'00_manifest.json','data/relations/cartridge_cavity_relations.csv',
                    'master_ref/cavities_master.jsonl','master_ref/logical_cavity_master.csv',
                    'master_ref/physical_cavity_master.csv','master_ref/physical_to_logical_crosswalk.csv',
                    'data/source_supplement/logical_cavity_supplement.csv'}
        if rev2:
            required.update({'data/source_supplement/cavities_supplement.jsonl','pending_registry/pending_registry.jsonl'})
        with zipfile.ZipFile(self.path) as archive:
            names = archive.namelist()
            if len(names)!=len(set(names)) or len(names)>500 or not required<=set(names):
                raise ValueError('Relation ZIP has duplicate entries or lacks required files')
            if sum(item.file_size for item in archive.infolist())>200_000_000 or archive.testzip():
                raise ValueError('Relation ZIP size/CRC validation failed')
            self.manifest = json.loads(archive.read('00_manifest.json'))
            if rev2 and (self.manifest.get('package')!='KB_REV2' or not self.manifest.get('supersedes')):
                raise ValueError('Replacement requires a REV2 package explicitly superseding REV1')
            def read_csv(name):
                return list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig'))))
            def read_lines(name):
                return [json.loads(line) for line in archive.read(name).decode('utf-8-sig').splitlines() if line.strip()] if name in names else []
            self.relations = read_csv('data/relations/cartridge_cavity_relations.csv')
            self.logical = read_csv('master_ref/logical_cavity_master.csv')
            self.physical = read_csv('master_ref/physical_cavity_master.csv')
            self.crosswalk = read_csv('master_ref/physical_to_logical_crosswalk.csv')
            self.logical_supplements = read_csv('data/source_supplement/logical_cavity_supplement.csv')
            self.supplements = read_lines('data/source_supplement/cavities_supplement.jsonl')
            self.pending = read_lines('pending_registry/pending_registry.jsonl')
            self.master = {r['canonical_id']:r for r in read_lines('master_ref/cavities_master.jsonl') if r.get('active_revision_id')}
            self.master_sha256 = hashlib.sha256(archive.read('master_ref/cavities_master.jsonl')).hexdigest()
            self.files = len(names)
            self.audit_files = {n:archive.read(n).decode('utf-8-sig') for n in names
                                if n.endswith('.md') and ('deepseek' in n or 'restore' in n or 'REV1' in n)}
        if not self.relations or set(self.relations[0])!=set(RELATION_FIELDS):
            raise ValueError('Relation CSV must preserve exactly the 25 source fields')
        self.by_id = {}
        for row in self.relations:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Malformed relation row')
            confidence = float(row['confidence'])
            if not math.isfinite(confidence) or not 0<=confidence<=1 or row['relation_type']!='USES_CAVITY' or row['verification_status'] not in {'CONFIRMED','PROBABLE'}:
                raise ValueError('Unsupported relation type/status/confidence')
            if not all(row[k].strip() for k in ('relation_id','manufacturer','cartridge_part_number')):
                raise ValueError('Relation lacks a required identity')
            if row['relation_id'] in self.by_id and self.by_id[row['relation_id']]!=row:
                raise ValueError('Conflicting duplicate relation ID: '+row['relation_id'])
            self.by_id[row['relation_id']] = row
        self.identities = {identity_key(r['manufacturer'],r['cartridge_part_number']) for r in self.by_id.values()}
        self.logical_keys = {logical_key(r['canonical_family'],r['canonical_name']) for r in self.logical}
        self.supplement_keys = {logical_key(r['canonical_family'],r['canonical_name']) for r in self.logical_supplements}
        self.cross_by_key = defaultdict(list)
        physical = {r['canonical_id']:r for r in self.physical}
        if len(physical)!=len(self.physical) or len(self.logical_keys)!=len(self.logical):
            raise ValueError('Duplicate physical/logical master identity')
        seen = set()
        for row in self.crosswalk:
            cid = row['canonical_id'];key = logical_key(row['canonical_family'],row['canonical_name'])
            expected = (row['unit'],key)
            if cid in seen or cid not in physical or cid not in self.master or key not in self.logical_keys:
                raise ValueError('Invalid physical crosswalk: '+cid)
            for original in (physical[cid],self.master[cid]):
                if expected != (original['unit'],logical_key(original['canonical_family'],original['canonical_name'])):
                    raise ValueError('Master/crosswalk identity mismatch: '+cid)
            seen.add(cid);self.cross_by_key[key].append(row)
        if seen!=set(physical):
            raise ValueError('Crosswalk does not cover the physical master')
        if rev2:
            self._validate_supplements()
            pending_ids = [r['id'] for r in self.pending]
            if len(pending_ids)!=len(set(pending_ids)):
                raise ValueError('Duplicate pending registry ID')
        if rev2 and self.sha256==REVIEWED_SHA:
            actual = (len(self.relations),len(self.identities),Counter(r['verification_status'] for r in self.relations),len(self.logical_supplements),len(self.supplements),Counter(r.get('status','') for r in self.pending))
            expected = (16066,15665,Counter(CONFIRMED=13078,PROBABLE=2988),5,10,Counter(resolved=88,open=132,awaiting_official_catalog=11,**{'':2}))
            if actual!=expected:
                raise ValueError('Reviewed REV2 package statistics differ from the declared baseline')

    def _validate_supplements(self):
        if len(self.supplement_keys)!=len(self.logical_supplements) or self.supplement_keys&self.logical_keys:
            raise ValueError('Supplement logical identity collision')
        seen, groups = set(), defaultdict(list)
        for row in self.supplements:
            key = logical_key(row['canonical_family'],row['canonical_name'])
            if row['canonical_id'] in seen or row['canonical_id'] in self.master or key not in self.supplement_keys:
                raise ValueError('Supplement physical identity collision')
            if row['status']!='SUPPLEMENT_EXTERNAL' or row.get('_supplement',{}).get('geometry')!='NOT_COLLECTED' or row.get('revisions') or row['unit'] not in {'inch','metric'}:
                raise ValueError('Supplement must be a geometry-free reference identity')
            if any(key in row for key in ('stages','cutting_primitives','zones','interfaces','clearance_diameter','clearance_height')) or any(re.match(r'^(Circle|ORing|Thread)',key) for key in row):
                raise ValueError('Supplement placeholder contains forbidden machining geometry')
            seen.add(row['canonical_id']);groups[key].append(row)
        for row in self.logical_supplements:
            group = groups[logical_key(row['canonical_family'],row['canonical_name'])]
            units = [r['unit'] for r in group]
            if len(group)!=int(row['physical_identity_count']) or len(set(units))!=len(units) or set(units)!=set(row['units'].split(';')):
                raise ValueError('Supplement logical/physical count or unit mismatch')


def runtime_map(db):
    result = {}
    for table,role in [('cavities','cavity'),('external_port_definitions','external_port')]:
        for cid,unit,usable,active in db.execute(f'SELECT id,unit_system,usable,active FROM {table}'):
            result[cid] = dict(runtime_type=role,unit=unit,usable=bool(usable),active=bool(active))
    return result


def preflight(db, old, new):
    existing = {}
    for cid,maker,model in db.execute('SELECT id,manufacturer,model FROM cartridges'):
        key = identity_key(maker,model)
        if key in existing:raise ValueError('Normalized Cartridge identity collision: '+str(key))
        existing[key] = cid
    runtime = runtime_map(db);statuses = Counter();eligible = 0;new_pairs = set();diagnostics = []
    for row in new.by_id.values():
        status, detail = resolve_relation(row,new.logical_keys,new.supplement_keys,new.cross_by_key,runtime)
        statuses[status] += 1
        if status not in {'RESOLVED','REFERENCE_ONLY_SUPPLEMENT'}:
            diagnostics.append(dict(relation_id=row['relation_id'],status=status,detail=detail))
        if status=='RESOLVED' and row['verification_status']=='CONFIRMED' and float(row['confidence'])>=.85:
            eligible += 1;key = identity_key(row['manufacturer'],row['cartridge_part_number'])
            cid = existing.get(key) or stable_id('cart_',*key)
            new_pairs.update((cid,target) for target in detail['candidate_canonical_ids'])
    old_pairs = set(map(tuple,db.execute('SELECT cartridge_id,cavity_id FROM cartridge_cavities WHERE valid=1')))
    derived = set(map(tuple,db.execute('''SELECT DISTINCT e.cartridge_id,l.cavity_id FROM cartridge_cavity_evidence e
        JOIN cartridge_cavity_evidence_links l ON l.relation_id=e.relation_id WHERE e.execution_eligible=1''')))
    manual = old_pairs-derived;new_pairs.update(manual)
    retained = old.by_id.keys()&new.by_id.keys();changes = []
    for rid in sorted(retained):
        fields = [name for name in RELATION_FIELDS if old.by_id[rid][name]!=new.by_id[rid][name]]
        if fields:changes.append(dict(relation_id=rid,fields=fields,confidence_before=old.by_id[rid]['confidence'],confidence_after=new.by_id[rid]['confidence'],status_before=old.by_id[rid]['verification_status'],status_after=new.by_id[rid]['verification_status']))
    removed_pairs = []
    for cid,cavity in sorted(old_pairs-new_pairs):
        rows = db.execute('''SELECT DISTINCT e.relation_id FROM cartridge_cavity_evidence e JOIN cartridge_cavity_evidence_links l
            ON l.relation_id=e.relation_id WHERE e.cartridge_id=? AND l.cavity_id=? AND e.execution_eligible=1''',(cid,cavity)).fetchall()
        reasons = []
        for (rid,) in rows:
            row = new.by_id.get(rid)
            if row is None:reason = 'RELATION_REMOVED'
            else:
                status,detail = resolve_relation(row,new.logical_keys,new.supplement_keys,new.cross_by_key,runtime)
                reason = status if status!='RESOLVED' else 'PROBABLE' if row['verification_status']!='CONFIRMED' else 'CONFIDENCE_BELOW_0_85' if float(row['confidence'])<.85 else 'PHYSICAL_MAPPING_CHANGED'
            reasons.append(dict(relation_id=rid,reason=reason))
        if not reasons:raise ValueError('Unexplained execution pair removal')
        removed_pairs.append(dict(cartridge_id=cid,cavity_id=cavity,reasons=reasons))
    report = dict(rev1_path=str(old.path),rev1_sha256=old.sha256,rev2_path=str(new.path),rev2_sha256=new.sha256,
        rev1_relations=len(old.relations),rev2_relations=len(new.relations),relation_ids_retained=len(retained),
        relation_ids_added=sorted(new.by_id.keys()-old.by_id.keys()),relation_ids_removed=sorted(old.by_id.keys()-new.by_id.keys()),
        retained_rows_changed=len(changes),changed_rows=changes,
        identity_retained=len(old.identities&new.identities),identity_added=sorted(new.identities-old.identities),identity_removed=sorted(old.identities-new.identities),
        verification_before=dict(Counter(r['verification_status'] for r in old.by_id.values())),verification_after=dict(Counter(r['verification_status'] for r in new.by_id.values())),
        field_change_counts=dict(Counter(field for change in changes for field in change['fields'])),
        predicted_resolution=dict(statuses),resolution_diagnostics=diagnostics,execution_eligible=eligible,
        execution_pairs_before=len(old_pairs),execution_pairs_after=len(new_pairs),execution_pairs_added=sorted(new_pairs-old_pairs),execution_pairs_removed=removed_pairs,
        retained_manual_pairs=len(manual),supplement_logical=new.logical_supplements,supplement_physical=new.supplements,
        supplement_relations=[r['relation_id'] for r in new.by_id.values() if logical_key(r['cavity_family'],r['cavity_name']) in new.supplement_keys],
        pending_count=len(new.pending),pending_statuses=dict(Counter(r.get('status','') for r in new.pending)),
        classification_pending=new.manifest.get('kpi',{}).get('classification_pending_identities'),manifest=new.manifest)
    if new.sha256==REVIEWED_SHA and (len(retained),len(report['relation_ids_added']),len(report['relation_ids_removed']),len(changes),report['identity_retained'],len(report['identity_added']),len(report['identity_removed']))!=(15272,794,0,1354,15005,660,0):
        raise ValueError('Reviewed REV1→REV2 comparison has unexplained differences')
    return report, new_pairs


def write_preflight(directory, report):
    directory = Path(directory);directory.mkdir(parents=True,exist_ok=True)
    (directory/'REV1_RELATION_TO_REV2_PREFLIGHT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows = ['# REV1 → REV2 relation replacement preflight','',f"REV2: `{report['rev2_path']}`",f"SHA-256: `{report['rev2_sha256']}`",'',
        f"Relations: {report['rev1_relations']} → {report['rev2_relations']}; retained {report['relation_ids_retained']}, added {len(report['relation_ids_added'])}, removed {len(report['relation_ids_removed'])}.",
        f"Changed retained rows: {report['retained_rows_changed']}.",f"Identities retained {report['identity_retained']}; added {len(report['identity_added'])}; removed {len(report['identity_removed'])}.",
        f"Verification: {report['verification_before']} → {report['verification_after']}.",f"Changed source fields: {report['field_change_counts']}.",
        f"Predicted resolution: {report['predicted_resolution']}; eligible relations {report['execution_eligible']}.",
        f"Execution pairs: {report['execution_pairs_before']} → {report['execution_pairs_after']}; added {len(report['execution_pairs_added'])}, removed {len(report['execution_pairs_removed'])}.",
        f"Supplements: {len(report['supplement_logical'])} logical / {len(report['supplement_physical'])} physical / {len(report['supplement_relations'])} reference relations.",
        f"Pending registry: {report['pending_count']} rows, {report['pending_statuses']}; classification pending is separately {report['classification_pending']} identities.",'',
        'Full relation IDs, field/confidence/status changes, physical pair additions/removal reasons and raw manifest facts are in the adjacent JSON.','']
    (directory/'REV1_RELATION_TO_REV2_PREFLIGHT.md').write_text('\n'.join(rows),encoding='utf-8')


def reversal_audit(original, staging, package):
    # Audit targets from PR-155/PR-160; these constants never influence import or execution.
    aft = {'vp000'+value for value in ['006','013','015','038','070','120','121','127','154','166','193','198','204','250','330','388','555']}
    before,after = runtime_map(original),runtime_map(staging)
    groups = {}
    for label,family,names in [('AFT','atlantic fluid tech',aft),('Walvoil','walvoil',None)]:
        keys = sorted(key for key in package.cross_by_key if key[0]==family and (names is None or key[1] in names))
        rows = []
        for key in keys:
            ids = [r['canonical_id'] for r in package.cross_by_key[key]]
            if any(before.get(cid)!=after.get(cid) for cid in ids):
                raise ValueError('Official reversal cavity changed or was stripped: '+str(key))
            relations = [r for r in package.by_id.values() if logical_key(r['cavity_family'],r['cavity_name'])==key]
            statuses = dict(Counter(staging.execute('SELECT resolution_status FROM cartridge_cavity_evidence WHERE relation_id=?',(r['relation_id'],)).fetchone()[0] for r in relations))
            rows.append(dict(family=key[0],name=key[1],physical_ids=ids,relations=[r['relation_id'] for r in relations],resolution=statuses,preserved=True))
        groups[label] = dict(logical_count=len(rows),physical_count=sum(len(r['physical_ids']) for r in rows),rows=rows,status='PASS')
    walvoil_family = [r for r in groups['Walvoil']['rows'] if r['name'].startswith(('vmpd','vui','vse','vpr'))]
    groups['Walvoil'].update(specified_prefix_count=len(walvoil_family),specified_prefix_names=[r['name'] for r in walvoil_family],
        scope='All canonical Walvoil identities preserved; includes the full requested reversal family',
        reference_count_note='Task states 12 prefix identities; exact package contains 11 such logical names. All Walvoil logical identities are audited instead, including uncovered names.')
    if package.sha256==REVIEWED_SHA and (groups['AFT']['logical_count']!=17 or groups['Walvoil']['logical_count']<12):
        raise ValueError('Reviewed official reversal audit does not cover the expected identity universe')
    return groups


def _import_audit(db, package):
    batch = 'kb_'+package.sha256[:24]
    for row in package.logical_supplements:
        db.execute('INSERT INTO kb_logical_cavity_supplements VALUES (?,?,?,?,?,?,?,?)',
            (master_id(row['canonical_family'],row['canonical_name']),row['canonical_family'],row['canonical_name'],row['preferred_display_name'],int(row['physical_identity_count']),row['units'],row['display_families'],batch))
    groups = defaultdict(list)
    for row in package.supplements:
        logical = master_id(row['canonical_family'],row['canonical_name']);groups[logical].append(row)
        db.execute('''INSERT INTO kb_cavity_supplements(canonical_id,logical_id,unit,canonical_family,display_family,canonical_name,display_name,status,
            active_selection_basis,source_count,geometry_status,raw_metadata_json,import_batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (row['canonical_id'],logical,row['unit'],row['canonical_family'],row['display_family'],row['canonical_name'],row['display_name'],row['status'],row['active_selection_basis'],int(row['source_count']),row['_supplement']['geometry'],encode(row),batch))
    for rid,logical,detail_json in db.execute("SELECT relation_id,master_record_id,resolution_detail_json FROM cartridge_cavity_evidence WHERE resolution_status='REFERENCE_ONLY_SUPPLEMENT'").fetchall():
        rows = groups[logical]
        if not rows:raise ValueError('Supplement relation has no registered supplemental identity')
        for row in rows:db.execute('INSERT INTO cartridge_cavity_supplement_links VALUES (?,?)',(rid,row['canonical_id']))
        detail = json.loads(detail_json)
        detail.update(candidate_canonical_ids=[r['canonical_id'] for r in rows],runtime_matches=[dict(canonical_id=r['canonical_id'],unit=r['unit'],runtime_type='supplement_identity',expected_type='cavity',usable=False,active=False,geometry_status='NOT_COLLECTED') for r in rows])
        db.execute('UPDATE cartridge_cavity_evidence SET resolution_detail_json=? WHERE relation_id=?',(encode(detail),rid))
    for row in package.pending:
        status = row.get('status')
        db.execute('INSERT INTO kb_pending_registry VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (row['id'],row.get('ts',''),row.get('family',''),row.get('identity',''),row.get('category',''),row.get('suspicion',''),status,(status or 'UNSPECIFIED').upper(),row.get('resolution'),encode(row),batch))


def integrate(source, package, rev1, output=None, *, report_dir=Path('.')):
    source = Path(source).resolve();new = RelationPackage(package,rev2=True);old = RelationPackage(rev1)
    source_sha = file_hash(source)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original:
        version = original.execute('PRAGMA user_version').fetchone()[0]
        engineering_db.validate_database(source,schema_version=version)
        if not original.execute("SELECT count(*) FROM technical_identities WHERE domain='cartridge'").fetchone()[0]:
            raise ValueError('Preservation source must contain the current Technical KB')
        if old.master_sha256!=new.master_sha256:raise ValueError('REV2 master baseline differs from REV1; explicitly review the new canonical baseline first')
        print('Checking read-only source database integrity',flush=True)
        if original.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or original.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Preservation source integrity/foreign-key validation failed')
        print('Validated inputs; calculating preflight and preservation digests',flush=True)
        report,predicted_pairs = preflight(original,old,new)
        report.update(source_path=str(source),source_sha256=source_sha,source_schema=version)
        write_preflight(report_dir,report)  # Must exist before any staging mutation.
        if output is None:return report
        output = Path(output).resolve()
        if output==source or output.exists():raise ValueError('Output must be a new staging path; existing files are never overwritten')
        before = table_digests(original,RELATION_TABLES|{'cartridges'})
        original_cartridges = list(original.execute('SELECT * FROM cartridges ORDER BY id'))
        old_batches = [dict(zip([c[1] for c in original.execute('PRAGMA table_info(kb_import_batches)')],row)) for row in original.execute('SELECT * FROM kb_import_batches')]
        technical_ids = {row[0] for row in original.execute("SELECT id FROM technical_identities WHERE domain='cartridge'")}
        output.parent.mkdir(parents=True,exist_ok=True);output.open('xb').close()
        try:
            with closing(sqlite3.connect(output)) as db:
                print('Cloning read-only source into '+str(output),flush=True);original.backup(db)
                db.execute('PRAGMA foreign_keys=ON')
                if version<5:relation_schema.initialize(db)
                db.execute('BEGIN IMMEDIATE')
                for table in ['cartridge_cavity_supplement_links','kb_cavity_supplements','kb_logical_cavity_supplements','kb_pending_registry']:
                    db.execute('DELETE FROM '+table)
                db.execute('''DELETE FROM cartridge_cavities WHERE (cartridge_id,cavity_id) IN
                    (SELECT e.cartridge_id,l.cavity_id FROM cartridge_cavity_evidence e JOIN cartridge_cavity_evidence_links l ON l.relation_id=e.relation_id WHERE e.execution_eligible=1)''')
                for table in ['cartridge_cavity_evidence_links','cartridge_cavity_evidence','kb_import_batches']:db.execute('DELETE FROM '+table)
                print('Replacing all active relationship evidence with REV2',flush=True)
                imported = import_knowledge(db,new.path)
                _import_audit(db,new)
                for row in original_cartridges:
                    if db.execute('SELECT * FROM cartridges WHERE id=?',(row[0],)).fetchone()!=row:
                        raise ValueError('Existing Cartridge identity or stable ID changed')
                pairs = set(map(tuple,db.execute('SELECT cartridge_id,cavity_id FROM cartridge_cavities WHERE valid=1')))
                if pairs!=predicted_pairs:raise ValueError('Imported execution pair set differs from preflight')
                actual_rows = {rid:json.loads(raw) for rid,raw in db.execute('SELECT relation_id,source_row_json FROM cartridge_cavity_evidence')}
                if actual_rows!=new.by_id:raise ValueError('REV2 25-field source rows were not preserved exactly')
                print('Verifying all non-relation/technical tables remain identical',flush=True)
                after = table_digests(db,RELATION_TABLES|{'cartridges'})
                if before!=after:raise ValueError('Relation replacement changed a non-relation domain')
                if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('Staging integrity/foreign-key validation failed')
                if file_hash(source)!=source_sha:raise ValueError('Read-only preservation source changed during integration')
                count = db.execute('SELECT count(*) FROM cartridges').fetchone()[0]
                report.update(imported=imported,source_tables=before,staging_tables=after,schema_version=engineering_db.SCHEMA_VERSION,
                    technical_target_count=len(technical_ids),current_cartridge_count=count,extra_relation_only_count=count-len(technical_ids),
                    missing_technical_target_count=db.execute("SELECT count(*) FROM technical_identities t WHERE t.domain='cartridge' AND NOT EXISTS(SELECT 1 FROM cartridges c WHERE c.id=t.id)").fetchone()[0],
                    cartridge_ids_retained=len(original_cartridges),cartridge_ids_added=count-len(original_cartridges),cartridge_ids_removed=0,
                    supplement_logical_count=len(new.logical_supplements),supplement_physical_count=len(new.supplements),pending_registry_count=len(new.pending),
                    validation='PASS',output_hash_location='External report: a database cannot contain its own final file SHA-256')
                report['official_reversal_audit'] = reversal_audit(original,db,new)
                db.execute('UPDATE kb_import_batches SET report_json=? WHERE id=?',(encode(report),'kb_'+new.sha256[:24]))
                db.execute('INSERT INTO kb_relation_migrations VALUES (?,?,?,?,?,?)',
                    ('replace_'+hashlib.sha256((source_sha+new.sha256).encode()).hexdigest()[:24],source_sha,version,new.sha256,encode(old_batches),encode(report)))
                db.commit()
            engineering_db.validate_database(output)
        except BaseException:
            output.unlink(missing_ok=True);raise
    return report | dict(output_path=str(output),output_sha256=file_hash(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--knowledge-package',type=Path,required=True)
    parser.add_argument('--rev1-package',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--report-dir',type=Path,default=Path('.'));parser.add_argument('--report',type=Path)
    args = parser.parse_args();report = integrate(args.source,args.knowledge_package,args.rev1_package,args.output,report_dir=args.report_dir)
    if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(encode({key:report.get(key) for key in ['validation','source_path','output_path','output_sha256','schema_version','rev2_relations','execution_eligible','execution_pairs_after','cartridge_ids_added']}))


if __name__=='__main__':main()
