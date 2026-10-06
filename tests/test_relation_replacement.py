import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from manifold import engineering_db, relation_schema
from manifold.import_mdtools import import_database, stable_id
from manifold.replace_relation_knowledge import RelationPackage, integrate, table_digests, file_hash
from manifold.server import app
from test_knowledge_import import fixture, csv_bytes


def replace_zip(path, payload):
    with zipfile.ZipFile(path,'w') as archive:
        for name,data in payload.items():archive.writestr(name,data)


@pytest.fixture
def replacement_inputs(tmp_path,monkeypatch):
    monkeypatch.setattr('manifold.import_mdtools.linked_special_cuts',lambda source:set())
    master,old=fixture(tmp_path);source=tmp_path/'source.db'
    import_database(master,source,knowledge_package=old)
    owner=stable_id('cart_','maker','model-a')
    with sqlite3.connect(source) as db:
        for table in reversed(relation_schema.TABLES):db.execute('DROP TABLE '+table)
        db.execute('PRAGMA user_version=4')
        db.execute('INSERT INTO technical_identities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            ('cartridge',owner,owner,None,'Maker','MODEL-A','BASE','Series','Family','PARTIAL_CONFIRMED','SOURCE_REVIEW','{"keep":"technical"}'))
        db.execute("INSERT INTO materials VALUES ('MAT','Reviewed steel','Steel',1)")
        db.execute('INSERT INTO cartridge_cavities VALUES (?,?,1)',(stable_id('cart_','maker','model-l'),'C_B'))
    with zipfile.ZipFile(old) as archive:payload={n:archive.read(n) for n in archive.namelist()}
    rows=list(csv.DictReader(io.StringIO(payload['data/relations/cartridge_cavity_relations.csv'].decode())))
    rows=[r for r in rows if r['relation_id']!='REL_B']
    rows[0]=rows[0]|dict(evidence_text='REV2 replacement quotation',confidence='0.90',updated_at='2026-10-05')
    rows.append(rows[0]|dict(relation_id='REL_NEW',cartridge_part_number='MODEL-NEW',cartridge_part_number_original='MODEL-NEW'))
    logical=[dict(canonical_family='maker',canonical_name=name,preferred_display_name=name.upper(),physical_identity_count='2',units='inch;metric',display_families='Maker') for name in ['supp','sc-08-03','sc-10-03','sc-10-05','t-20a']]
    physical=[dict(canonical_id=f'sup_{index}_{unit}',unit=unit,canonical_family='maker',canonical_name=r['canonical_name'],display_family='Maker',display_name=r['preferred_display_name'],status='SUPPLEMENT_EXTERNAL',active_selection_basis='OFFICIAL',source_count=1,revisions=[],_supplement=dict(geometry='NOT_COLLECTED'))
              for index,r in enumerate(logical) for unit in ['inch','metric']]
    pending=[dict(id='PR-1',ts='2026-10-05',family='Maker',identity='Not a mapping',category='audit',suspicion='review',status='resolved',resolution='Historical note'),
             dict(id='PR-2',family='Maker',identity='MODEL-NEW',status='open'),dict(id='PR-3',family='Maker',identity='Raw blank')]
    payload.update({'00_manifest.json':json.dumps(dict(package='KB_REV2',supersedes=old.name,kpi={'classification_pending_identities':307})).encode(),
        'data/relations/cartridge_cavity_relations.csv':csv_bytes(rows),
        'data/source_supplement/logical_cavity_supplement.csv':csv_bytes(logical),
        'data/source_supplement/cavities_supplement.jsonl':'\n'.join(json.dumps(r) for r in physical).encode(),
        'pending_registry/pending_registry.jsonl':'\n'.join(json.dumps(r) for r in pending).encode()})
    new=tmp_path/'rev2.zip';replace_zip(new,payload)
    return source,old,new,payload


def test_transactional_replacement_preserves_domains_and_rebuilds_twice(replacement_inputs,tmp_path,monkeypatch):
    source,old,new,_=replacement_inputs;before=file_hash(source)
    paths=[tmp_path/'a.db',tmp_path/'b.db']
    reports=[integrate(source,new,old,path,report_dir=tmp_path) for path in paths]
    assert (tmp_path/'REV1_RELATION_TO_REV2_PREFLIGHT.json').exists()
    assert file_hash(source)==before
    assert reports[0]['source_tables']==reports[0]['staging_tables']
    assert reports[0]['cartridge_ids_added']==1 and reports[0]['cartridge_ids_removed']==0
    with sqlite3.connect(paths[0]) as db,sqlite3.connect(paths[1]) as second:
        for table in ['cartridges','cartridge_cavity_evidence','cartridge_cavity_evidence_links','cartridge_cavities','kb_logical_cavity_supplements','kb_cavity_supplements','cartridge_cavity_supplement_links','kb_pending_registry']:
            assert table_digests(db)[table]==table_digests(second)[table]
        assert db.execute("SELECT count(*) FROM cartridge_cavity_evidence WHERE relation_id='REL_B'").fetchone()[0]==0
        raw=json.loads(db.execute("SELECT source_row_json FROM cartridge_cavity_evidence WHERE relation_id='REL_A'").fetchone()[0])
        assert len(raw)==25 and raw['evidence_text']=='REV2 replacement quotation' and raw['confidence']=='0.90'
        assert db.execute("SELECT count(*) FROM kb_import_batches").fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM kb_logical_cavity_supplements').fetchone()[0]==5
        assert db.execute('SELECT count(*) FROM kb_cavity_supplements').fetchone()[0]==10
        assert db.execute("SELECT count(*) FROM kb_cavity_supplements WHERE geometry_status!='NOT_COLLECTED' OR runtime_selectable OR machining_usable OR routing_usable OR tooling_usable OR execution_geometry_available").fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM cartridge_cavity_supplement_links').fetchone()[0]==2
        assert db.execute("SELECT count(*) FROM cartridge_cavity_supplement_links l JOIN kb_cavity_supplements s ON s.canonical_id=l.canonical_id WHERE s.canonical_name IN ('sc-10-05','t-20a')").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM cavities WHERE id LIKE 'sup_%'").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM cartridge_cavity_evidence_links WHERE relation_id='REL_S'").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM cartridge_cavity_evidence WHERE relation_id IN ('REL_S','REL_P','REL_L','REL_T') AND execution_eligible=1").fetchone()[0]==0
        new_id=stable_id('cart_','maker','model-new')
        assert db.execute("SELECT function,ratings_json FROM cartridges WHERE id=?",(new_id,)).fetchone()==('','{}')
        assert db.execute('SELECT count(*) FROM technical_identities WHERE id=?',(new_id,)).fetchone()[0]==0
        assert db.execute("SELECT raw_status,normalized_status FROM kb_pending_registry WHERE id='PR-3'").fetchone()==(None,'UNSPECIFIED')
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(paths[0]))
    assert engineering_db.compatible_cavity_ids(new_id)==['C_IN','C_MM']
    assert len({r['logical_id'] for r in engineering_db.compatible_logical_cavities(new_id)})==1
    assert not engineering_db.compatible(new_id,'C_B')  # Equal geometry is not a relation.
    assert engineering_db.compatible(stable_id('cart_','maker','model-l'),'C_B')  # Preserve unrelated manual fact.
    client=TestClient(app)
    technical=client.get('/api/cartridges/'+new_id+'/technical').json()
    assert technical['identity']['technical_record_present'] is False and technical['values']==[]
    owner=stable_id('cart_','maker','model-a')
    assert client.get('/api/cartridges/'+owner+'/technical').json()['identity']['technical_record_present'] is True
    supplement=client.get('/api/knowledge/relations/REL_S').json()
    assert supplement['execution_eligible'] is False and supplement['resolved_cavities']==[]
    assert len(supplement['supplemental_cavities'])==2
    assert client.get('/api/knowledge/cavity-supplements?q=t-20a').json()['total']==2
    assert client.get('/api/knowledge/pending-registry?status=UNSPECIFIED').json()['total']==1
    assert client.get('/api/knowledge/pending-registry?limit=1000').status_code==422
    assert client.get('/api/knowledge/relations/REL_B').status_code==404
    with pytest.raises(ValueError,match='existing files'):
        integrate(source,new,old,paths[0],report_dir=tmp_path)


@pytest.mark.parametrize('problem',['rev1','conflicting_duplicate','crosswalk','master_id','geometry'])
def test_package_boundary_and_unresolved_admission(replacement_inputs,tmp_path,problem):
    source,old,new,payload=replacement_inputs;output=tmp_path/'invalid.db'
    if problem=='rev1':
        with pytest.raises(ValueError):integrate(source,old,old,output,report_dir=tmp_path)
        assert not output.exists();return
    rows=list(csv.DictReader(io.StringIO(payload['data/relations/cartridge_cavity_relations.csv'].decode())))
    if problem=='conflicting_duplicate':rows.append(rows[0]|{'evidence_text':'Conflicting'})
    if problem=='master_id':rows[-1]['master_record_id']='ML:wrong'
    payload['data/relations/cartridge_cavity_relations.csv']=csv_bytes(rows)
    if problem=='crosswalk':
        cross=list(csv.DictReader(io.StringIO(payload['master_ref/physical_to_logical_crosswalk.csv'].decode())));cross[0]['unit']='custom';payload['master_ref/physical_to_logical_crosswalk.csv']=csv_bytes(cross)
    if problem=='geometry':
        physical=[json.loads(line) for line in payload['data/source_supplement/cavities_supplement.jsonl'].decode().splitlines()];physical[0]['_supplement']['geometry']='COLLECTED';payload['data/source_supplement/cavities_supplement.jsonl']='\n'.join(json.dumps(r) for r in physical).encode()
    replace_zip(new,payload)
    if problem=='master_id':
        integrate(source,new,old,output,report_dir=tmp_path)
        with sqlite3.connect(output) as db:
            assert db.execute("SELECT resolution_status,execution_eligible FROM cartridge_cavity_evidence WHERE relation_id='REL_NEW'").fetchone()==('UNRESOLVED_MASTER',0)
    else:
        with pytest.raises(ValueError):integrate(source,new,old,output,report_dir=tmp_path)
        assert not output.exists()


def test_existing_normalized_identity_keeps_id(replacement_inputs,tmp_path):
    source,old,new,payload=replacement_inputs
    rows=list(csv.DictReader(io.StringIO(payload['data/relations/cartridge_cavity_relations.csv'].decode())))
    rows[0].update(manufacturer='  MAKER  ',cartridge_part_number='  model-a  ')
    payload['data/relations/cartridge_cavity_relations.csv']=csv_bytes(rows);replace_zip(new,payload)
    output=tmp_path/'normalized.db';integrate(source,new,old,output,report_dir=tmp_path)
    with sqlite3.connect(output) as db:
        assert db.execute("SELECT cartridge_id FROM cartridge_cavity_evidence WHERE relation_id='REL_A'").fetchone()[0]==stable_id('cart_','maker','model-a')
        assert db.execute("SELECT count(*) FROM cartridges WHERE lower(trim(model))='model-a'").fetchone()[0]==1


def test_replacement_failure_removes_partial_clone_and_preserves_source(replacement_inputs,tmp_path,monkeypatch):
    source,old,new,_=replacement_inputs;before=file_hash(source);output=tmp_path/'partial.db'
    def failure(*args):raise ValueError('Injected audit import failure')
    monkeypatch.setattr('manifold.replace_relation_knowledge._import_audit',failure)
    with pytest.raises(ValueError,match='Injected audit import failure'):
        integrate(source,new,old,output,report_dir=tmp_path)
    assert not output.exists() and file_hash(source)==before


def test_real_staging_relation_acceptance(monkeypatch):
    value=os.environ.get('PMC_RELATION_ACCEPTANCE_DB')
    if not value:pytest.skip('Explicit real staging acceptance DB not configured')
    with sqlite3.connect(value) as db:
        assert db.execute('SELECT count(*) FROM cartridge_cavity_evidence').fetchone()[0]==16066
        assert db.execute('SELECT count(*) FROM cartridges').fetchone()[0]==15665
        assert db.execute("SELECT count(*) FROM technical_identities WHERE domain='cartridge'").fetchone()[0]==15005
        assert db.execute('SELECT count(*) FROM cartridge_cavity_evidence WHERE execution_eligible=1').fetchone()[0]==13068
        assert db.execute('SELECT count(*) FROM cartridge_cavities WHERE valid=1').fetchone()[0]==26081
        assert db.execute("SELECT count(*) FROM cartridge_cavity_evidence WHERE verification_status='PROBABLE' AND execution_eligible=1").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM cartridge_cavity_evidence WHERE resolution_status='REFERENCE_ONLY_SUPPLEMENT'").fetchone()[0]==5
        assert db.execute('SELECT count(*) FROM cartridge_cavity_supplement_links').fetchone()[0]==10
        assert db.execute('SELECT count(*) FROM kb_pending_registry').fetchone()[0]==233
        assert db.execute("SELECT count(*) FROM kb_pending_registry WHERE coalesce(raw_status,'')=''").fetchone()[0]==2
        assert db.execute("SELECT count(*) FROM technical_identities t WHERE t.domain='cartridge' AND NOT EXISTS(SELECT 1 FROM cartridges c WHERE c.id=t.id)").fetchone()[0]==0
