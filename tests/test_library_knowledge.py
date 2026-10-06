import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from manifold import engineering_db, library_knowledge
from manifold.import_library_knowledge import BASE, INCREMENTS, LibraryPackage, build_plan, integrate
from manifold.replace_relation_knowledge import table_digests


def csv_data(rows, fields=None):
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=fields or list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode()


def package(path, *, missing=False, conflict=False, legacy=False):
    targets=[]; evidence=[]; sources=[]; payload={}
    for index,(run,(domain,prefix)) in enumerate(INCREMENTS.items()):
        key=f'T{index}';eid=f'E{index}'
        targets.append(dict(target_id=key,domain=domain,target_type='reference',raw_identity=key,
                            current_disposition='REFERENCE_ONLY',queue_status='PARTIAL',evidence_ids=eid,
                            required_gate='reference only',notes='scoped'))
        row=dict(target_id=key,baseline_status='PARTIAL',proposed_status='PARTIAL' if index==2 else 'VERIFIED',
                 verification_scope='reference identity only',evidence_ids=eid)
        payload[f'increments/{run}/{prefix}_TARGET_DISPOSITION_PROPOSED.csv']=csv_data([row])
        payload[f'increments/{run}/{prefix}_PROGRESS.json']=json.dumps({'gate':'FAIL' if index!=2 else 'PASS'}).encode()
        evidence.append(dict(evidence_id=eid,source_id='S'+str(index),entity_id=key,scope='condition preserved',raw_value='fact'))
        sources.append(dict(source_id='S'+str(index),source_title='official scoped document'))
    targets.extend([dict(targets[0],target_id='SURFACE',domain='Surface Treatments / Coatings',evidence_ids='E0'),
                    dict(targets[0],target_id='SEAL',domain='Seals / O-rings / Backup Rings',queue_status='VERIFIED',evidence_ids='E0'),
                    dict(targets[0],target_id='CAD',domain='CAD / Assets')])
    payload[BASE+'HARD_GATES_TARGET_QUEUE_V2.csv']=csv_data(targets)
    payload[BASE+'HARD_GATES_DOMAIN_STATUS_V2.csv']=csv_data([dict(domain=r['domain'],hard_gate_status='FAIL') for r in targets])
    payload[BASE+'unified_evidence/UNIFIED_EVIDENCE.jsonl']='\n'.join(json.dumps(r) for r in evidence[1:] if missing).encode() if missing else '\n'.join(json.dumps(r) for r in evidence).encode()
    payload[BASE+'unified_evidence/UNIFIED_EVIDENCE_SOURCE_REGISTRY.csv']=csv_data(sources)
    payload[BASE+'seal/SEAL_EVIDENCE.jsonl']=json.dumps(evidence[0]).encode()
    payload['accepted_seal_revision/MERGE_RECONCILIATION.json']=b'{"formal_progress_merged":true}'
    payload['accepted_seal_revision/SEAL_EVIDENCE_DELTA.jsonl']=json.dumps(evidence[0]).encode()
    if missing:
        payload[BASE+'seal/SEAL_EVIDENCE.jsonl']=b''
    if conflict:
        payload['increments/CLOSURES_2026-10-06_REV04/CLOSURES_EVIDENCE_DELTA.jsonl']=json.dumps(dict(evidence[0],raw_value='new accepted field')).encode()
    if legacy:
        payload['legacy_reference_only/OLD_EVIDENCE.jsonl']=json.dumps(dict(evidence[0],raw_value='old unsafe override')).encode()
    payload['baseline/assets/model.step']=b'CAD CONTENT MUST NEVER BE IMPORTED'
    payload['baseline/raw/document.pdf']=b'RAW PDF MUST NEVER BE IMPORTED'
    proposed=[dict(r,queue_status='VERIFIED' if r['target_id'] in ('T0','T1') else r['queue_status']) for r in targets]
    payload['PROPOSED_AFTER_INTEGRATION_TARGET_QUEUE.csv']=csv_data(proposed)
    payload['LIB_DOMAIN_INVENTORY.csv']=csv_data([{'domain':'synthetic','target_count':5}])
    payload['TRANSFER_SUMMARY.json']=b'{"synthetic":true}'
    maps=[dict(archive_path=n,original_workspace_path=n,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for n,data in payload.items()]
    payload['LIB_DATASET_INDEX.csv']=csv_data(maps)
    payload['SOURCE_FILE_MAP.csv']=csv_data(maps)
    manifest=[dict(archive_path=n,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for n,data in payload.items()]
    payload['MANIFEST.json']=json.dumps({'files':manifest}).encode()
    with zipfile.ZipFile(path,'w') as z:
        for name,data in payload.items():z.writestr(name,data)
    return path


@pytest.fixture
def source(tmp_path):
    path=tmp_path/'v5.db'
    with sqlite3.connect(path) as db:
        engineering_db.initialize_schema(db)
        db.execute('''INSERT INTO external_port_definitions
            (id,name,unit_system,stages_json,primitives_json,boundaries_json,machining_json,interface_json,
             clearance_diameter,clearance_height,usable) VALUES
            ('PORT-KEEP','Existing valid port','metric','[]','[{"kind":"cylinder"}]','[]','[]','{}',10,20,1)''')
        db.execute('''INSERT INTO thread_definitions(id,display_name,family,unit_system,usable)
            VALUES ('THREAD-KEEP','Rp','BSPT','inch',1)''')
    return path


def test_preservation_determinism_and_research_boundaries(source,tmp_path):
    p=package(tmp_path/'input.zip',legacy=True)
    a,b=tmp_path/'a.db',tmp_path/'b.db'
    before=source.read_bytes()
    ra=integrate(source,p,a);rb=integrate(source,p,b)
    assert source.read_bytes()==before
    assert ra['protected_before']==ra['protected_after']==rb['protected_after']
    assert ra['active_targets']==5 and ra['cad_targets_excluded']==1
    assert ra['raw_binary_bytes_imported']==ra['cad_binary_bytes_imported']==0
    assert ra['seal_duplicated'] is False and len(ra['increments'])==3
    with sqlite3.connect(a) as x,sqlite3.connect(b) as y:
        assert table_digests(x,{'library_import_batches'})==table_digests(y,{'library_import_batches'})
        assert x.execute('SELECT count(*) FROM library_evidence').fetchone()[0]==3
        assert x.execute('SELECT count(*) FROM closure_definitions').fetchone()[0]==0
        assert x.execute('SELECT usable,primitives_json FROM external_port_definitions').fetchone()==(1,'[{"kind":"cylinder"}]')
        assert x.execute('SELECT display_name FROM thread_definitions').fetchone()[0]=='Rp'
        assert x.execute('SELECT count(*) FROM library_targets WHERE status="PARTIAL"').fetchone()[0]==2
        assert not x.execute('SELECT 1 FROM library_records WHERE original_json LIKE "%unsafe override%"').fetchone()
    assert library_knowledge.browse(path=a,status='PARTIAL')['count']==2
    d=library_knowledge.detail('T0',path=a)
    assert d['verification_scope']=='reference identity only'
    assert d['evidence'][0]['scope']=='condition preserved'
    with pytest.raises(FileExistsError):integrate(source,p,a)


def test_reject_v4_before_package_or_output(source,tmp_path):
    with sqlite3.connect(source) as db:db.execute('PRAGMA user_version=4')
    with pytest.raises(RuntimeError,match='schema is invalid'):
        integrate(source,tmp_path/'missing.zip',tmp_path/'out.db')
    assert not (tmp_path/'out.db').exists()


def test_unsupported_status_upgrade_fails(source,tmp_path):
    with pytest.raises(ValueError,match='Unsupported VERIFIED'):
        integrate(source,package(tmp_path/'input.zip',missing=True),tmp_path/'out.db')
    assert not (tmp_path/'out.db').exists()


def test_conflicting_native_id_retains_both_versions(source,tmp_path):
    out=tmp_path/'out.db'
    r=integrate(source,package(tmp_path/'input.zip',conflict=True),out)
    assert r['id_conflicts']==1
    with sqlite3.connect(out) as db:
        row=json.loads(db.execute('SELECT variants_json FROM library_conflicts').fetchone()[0])
        assert len(row)==2
    assert library_knowledge.detail('T0',path=out)['evidence'][0]['raw_value']=='new accepted field'


def test_hash_tampering_and_duplicate_paths(tmp_path):
    p=package(tmp_path/'input.zip')
    with zipfile.ZipFile(p) as z:payload={n:z.read(n) for n in z.namelist()}
    payload[BASE+'seal/SEAL_EVIDENCE.jsonl']=b'{}'  # Same schema/CRC, wrong declared SHA.
    with zipfile.ZipFile(p,'w') as z:
        for n,data in payload.items():z.writestr(n,data)
    with pytest.raises(ValueError,match='mismatch'):LibraryPackage(p)
    with zipfile.ZipFile(p,'a') as z:z.writestr('MANIFEST.json',b'{}')
    with pytest.raises(ValueError,match='Duplicate archive'):LibraryPackage(p)


def test_source_hash_gate(source,tmp_path):
    with pytest.raises(ValueError,match='hash differs'):
        integrate(source,tmp_path/'absent.zip',tmp_path/'out.db',expected_source_sha='wrong')


def test_malformed_structured_rows_rejected():
    from manifold.import_library_knowledge import decode_rows
    with pytest.raises(ValueError):decode_rows('bad.jsonl',b'{broken}')
    with pytest.raises(ValueError,match='shape'):decode_rows('bad.csv',b'a,b\n1\n')
    with pytest.raises(ValueError,match='header'):decode_rows('bad.csv',b'a,a\n1,2\n')


def test_native_evidence_id_separators():
    from manifold.import_library_knowledge import ids
    assert ids('E0;E1|E2')=={'E0','E1','E2'}
