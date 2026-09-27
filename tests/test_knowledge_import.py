import csv
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from manifold import engineering_db
from manifold.ai_design import library_resolution
from manifold.import_mdtools import import_database, stable_id
from manifold.knowledge_import import RELATION_FIELDS, master_id
from manifold.schema import Design
from manifold.server import app


def csv_bytes(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def fixture(tmp_path):
    source = tmp_path / 'mdtools'
    source.mkdir()
    identities = []
    for identifier, unit, family, name, role in [
        ('C_IN', 'inch', 'maker', 'a-1', 'CV'),
        ('C_MM', 'metric', 'maker', 'a-1', 'CV'),
        ('C_B', 'metric', 'maker', 'b-2', 'CV'),
        ('PORT_X', 'metric', 'maker', 'x-3', 'Port'),
    ]:
        identities.append(dict(canonical_id=identifier, unit=unit, canonical_family=family,
                               canonical_name=name, display_family='Maker', display_name=name,
                               active_revision_id='rev_'+identifier,
                               revisions=[dict(revision_id='rev_'+identifier, active=True, row={
                                   'CavityType':role, 'Circle0Dia':10, 'Circle0Depth':20,
                                   'NumberofPorts':1, 'Port1Depth':15, 'Port1Diameter':4,
                                   'MachineOperation1':'Bore', 'MachineTool1':'T10'})]))
    master = ''.join(json.dumps(x)+'\n' for x in identities).encode()
    (source/'cavities_master.jsonl').write_bytes(master)
    (source/'footprints_master.jsonl').write_text('')
    physical = [dict(canonical_id=x['canonical_id'],unit=x['unit'],canonical_family=x['canonical_family'],
                     canonical_name=x['canonical_name']) for x in identities]
    logical = [dict(canonical_family='maker',canonical_name=name) for name in ['a-1','b-2','x-3']]
    supplement = [dict(canonical_family='maker',canonical_name='supp')]
    def relation(identifier, model, name, status='CONFIRMED', confidence='0.95'):
        row = dict.fromkeys(RELATION_FIELDS, '')
        row.update(relation_id=identifier,relation_type='USES_CAVITY',manufacturer='Maker',
                   manufacturer_original='MAKER',cartridge_part_number=model,
                   cartridge_part_number_original=model,cavity_family='maker',cavity_name=name,
                   cavity_name_original=name,master_record_id=master_id('maker',name),
                   source_url='https://example.test/source',page_number='7',evidence_text='Exact source',
                   confidence=confidence,verification_status=status)
        return row
    rows = [relation('REL_A','MODEL-A','a-1'), relation('REL_B','MODEL-A','b-2'),
            relation('REL_P','MODEL-P','a-1','PROBABLE','0.70'),
            relation('REL_L','MODEL-L','a-1','CONFIRMED','0.50'),
            relation('REL_S','MODEL-S','supp'),relation('REL_T','MODEL-T','x-3')]
    package = tmp_path/'kb.zip'
    with zipfile.ZipFile(package,'w') as archive:
        archive.writestr('00_manifest.json',json.dumps({'package':'KB_TEST','generated_at':'2026-09-26'}))
        archive.writestr('master_ref/cavities_master.jsonl',master)
        archive.writestr('master_ref/logical_cavity_master.csv',csv_bytes(logical))
        archive.writestr('master_ref/physical_cavity_master.csv',csv_bytes(physical))
        archive.writestr('master_ref/physical_to_logical_crosswalk.csv',csv_bytes(physical))
        archive.writestr('data/source_supplement/logical_cavity_supplement.csv',csv_bytes(supplement))
        archive.writestr('data/relations/cartridge_cavity_relations.csv',csv_bytes(rows))
    return source,package


def test_rebuild_evidence_policy_and_v2_preservation(tmp_path,monkeypatch):
    monkeypatch.setattr('manifold.import_mdtools.linked_special_cuts',lambda source:set())
    source,package=fixture(tmp_path)
    previous=tmp_path/'previous.db'
    with sqlite3.connect(previous) as old:
        engineering_db.initialize_schema(old)
        old.execute('PRAGMA user_version=2')
        old.execute("INSERT INTO cavities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ('legacy_1','Legacy','Local','metric','','','[]','[]','[]','[]',10,20,1,'',1))
        old.execute("INSERT INTO cavity_interfaces VALUES (?,?,?,?,?,?,?,?)",
                    ('legacy_1','P',1,2,3,0,0,1))
        old.execute("INSERT INTO thread_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ('custom_thread_1','Local thread','Local','1/4','18','','both',0,'inch',8.0,1,'',1))
        old.execute("INSERT INTO external_port_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ('custom_port_1','Local port','Local','inch','','1/4-18','[]','[]','[]','[]','{}',
                     10.0,20.0,1,'',1,'custom_thread_1'))
    original=hashlib.sha256(previous.read_bytes()).hexdigest()
    first=tmp_path/'first.db';second=tmp_path/'second.db'
    for destination in [first,second]:
        report=import_database(source,destination,preserve_custom_from=previous,knowledge_package=package)
        assert report['kb_relations']==6 and report['kb_execution_eligible']==2
        assert report['kb_reference_only']==1 and report['kb_type_mismatch']==1
        assert report['compatibility']==3
    assert hashlib.sha256(previous.read_bytes()).hexdigest()==original
    def keys(path,table,columns):
        with sqlite3.connect(path) as db:
            return set(db.execute(f'SELECT {columns} FROM {table}'))
    for table,columns in [('cartridges','id'),('cartridge_cavity_evidence','relation_id'),
                          ('cartridge_cavity_evidence_links','relation_id,cavity_id'),
                          ('cartridge_cavities','cartridge_id,cavity_id')]:
        assert keys(first,table,columns)==keys(second,table,columns)
    with sqlite3.connect(first) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==3
        assert db.execute('SELECT count(*) FROM cavity_interfaces WHERE cavity_id="legacy_1"').fetchone()[0]==1
        assert db.execute("SELECT thread_definition_id FROM external_port_definitions WHERE id='custom_port_1'").fetchone()[0]=='custom_thread_1'
        assert db.execute("SELECT display_name FROM thread_definitions WHERE id='custom_thread_1'").fetchone()[0]=='Local thread'
        stored=json.loads(db.execute("SELECT source_row_json FROM cartridge_cavity_evidence WHERE relation_id='REL_A'").fetchone()[0])
        assert len(stored)==25 and set(stored)==set(RELATION_FIELDS)
        assert stored['manufacturer_original']=='MAKER' and stored['evidence_text']=='Exact source'
        assert db.execute("SELECT id FROM cartridges WHERE model='MODEL-A'").fetchone()[0]==stable_id('cart_','maker','model-a')
        for relation in ('REL_P','REL_L','REL_S','REL_T'):
            assert db.execute('SELECT execution_eligible FROM cartridge_cavity_evidence WHERE relation_id=?',(relation,)).fetchone()[0]==0
        for relation in ('REL_S','REL_T'):
            assert db.execute('SELECT count(*) FROM cartridge_cavity_evidence_links WHERE relation_id=?',(relation,)).fetchone()[0]==0
        mismatch=json.loads(db.execute("SELECT resolution_detail_json FROM cartridge_cavity_evidence WHERE relation_id='REL_T'").fetchone()[0])
        assert mismatch['candidate_canonical_ids']==['PORT_X']
        assert mismatch['runtime_matches'][0]['runtime_type']=='external_port'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(first))
    engineering_db.validate_database()
    client=TestClient(app)
    cartridges=client.get('/api/cartridges?q=MODEL-A').json()['items']
    cartridge_id=cartridges[0]['id']
    assert client.get(f'/api/knowledge/cartridges/{cartridge_id}/cavities').json()['total']==2
    assert client.get('/api/knowledge/cavities/C_IN/cartridges').json()['total']==3
    assert client.get('/api/knowledge/relations/REL_T').json()['resolution_status']=='TYPE_MISMATCH'
    assert client.get('/api/knowledge/relations/missing').status_code==404
    assert engineering_db.compatible(cartridge_id,'C_IN')
    probable=client.get('/api/cartridges?q=MODEL-P').json()['items'][0]['id']
    assert not engineering_db.compatible(probable,'C_IN')
    assert engineering_db.compatible_cavity_ids(probable)==[]
    design=Design.model_validate(dict(name='Evidence is not a compatibility grant',
        block=dict(length=100,width=100,height=100,material='Test'),
        features=[dict(id='CV1',kind='cavity',face='top',u=50,v=50,cavity_id='C_IN',
                       cartridge_id=probable,interface_nets={'port1':'P'})]))
    with pytest.raises(ValueError,match='not compatible'):
        engineering_db.validate_references(design)
    class Inputs:project_context='metric'
    choices=[dict(cartridge_id=cartridge_id,logical_id=row['logical_id'],key='db:'+row['cavity_id'],
                  unit='inch' if row['cavity_id']=='C_IN' else 'metric',usable=True,zones=[])
             for row in engineering_db.compatible_logical_cavities(cartridge_id)]
    assert library_resolution.automatic_choice(Inputs,choices)[1]=='ambiguous_cavities'
    same=[row for row in choices if row['logical_id']==master_id('maker','a-1')]
    assert library_resolution.automatic_choice(Inputs,same)[0]['key']=='db:C_MM'
    repeated=[*same,{**same[-1],'cartridge_id':'second-explicit-cartridge'}]
    assert library_resolution.automatic_choice(Inputs,repeated)[0]['key']=='db:C_MM'
    Inputs.project_context='custom'
    assert library_resolution.automatic_choice(Inputs,same)[1]=='unit_context_unavailable'
    with pytest.raises(ValueError,match='already exists'):
        import_database(source,first,knowledge_package=package)


def test_conflicting_duplicate_relation_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr('manifold.import_mdtools.linked_special_cuts',lambda source:set())
    source,package=fixture(tmp_path)
    with zipfile.ZipFile(package) as original:
        files={name:original.read(name) for name in original.namelist()}
    key='data/relations/cartridge_cavity_relations.csv'
    rows=list(csv.DictReader(io.StringIO(files[key].decode())))
    duplicate={**rows[0],'evidence_text':'Contradictory source text'}
    files[key]=csv_bytes([*rows,duplicate])
    conflict=tmp_path/'conflict.zip'
    with zipfile.ZipFile(conflict,'w') as archive:
        for name,body in files.items():archive.writestr(name,body)
    destination=tmp_path/'rejected.db'
    with pytest.raises(ValueError,match='Conflicting duplicate relation ID'):
        import_database(source,destination,knowledge_package=conflict)
    assert not destination.exists()


def test_wrong_logical_master_id_preserves_candidates_without_admission(tmp_path,monkeypatch):
    monkeypatch.setattr('manifold.import_mdtools.linked_special_cuts',lambda source:set())
    source,package=fixture(tmp_path)
    with zipfile.ZipFile(package) as original:
        files={name:original.read(name) for name in original.namelist()}
    key='data/relations/cartridge_cavity_relations.csv'
    rows=list(csv.DictReader(io.StringIO(files[key].decode())))
    rows[0]['master_record_id']='ML:wrong'
    files[key]=csv_bytes(rows)
    changed=tmp_path/'wrong-master.zip'
    with zipfile.ZipFile(changed,'w') as archive:
        for name,body in files.items():archive.writestr(name,body)
    destination=tmp_path/'diagnostic.db'
    report=import_database(source,destination,knowledge_package=changed)
    assert report['kb_master_id_mismatch']==1
    with sqlite3.connect(destination) as db:
        status,detail=db.execute("SELECT resolution_status,resolution_detail_json FROM cartridge_cavity_evidence WHERE relation_id='REL_A'").fetchone()
        assert status=='UNRESOLVED_MASTER'
        assert json.loads(detail)['candidate_canonical_ids']==['C_IN','C_MM']
        assert db.execute("SELECT count(*) FROM cartridge_cavity_evidence_links WHERE relation_id='REL_A'").fetchone()[0]==0
