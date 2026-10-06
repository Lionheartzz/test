import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from manifold import engineering_db,library_schema
from manifold.library_presentation import CATEGORIES,DOMAIN_CATEGORY,record_key
from manifold.server import app

FORBIDDEN={'evidence_id','source_id','dataset_id','verification_scope','gate_json','original_json',
           'variants_json','archive_path','sha256','target_id','entity_id','confidence'}


def assert_friendly(value):
    if isinstance(value,dict):
        assert not FORBIDDEN & value.keys()
        for child in value.values():assert_friendly(child)
    elif isinstance(value,list):
        for child in value:assert_friendly(child)


@pytest.fixture
def library(tmp_path,monkeypatch):
    path=tmp_path/'library.db'
    with sqlite3.connect(path) as db:
        engineering_db.initialize_schema(db);library_schema.initialize(db)
        db.execute("INSERT INTO library_import_batches VALUES ('batch','source','package','{}')")
        for domain,category in DOMAIN_CATEGORY.items():
            identifier='ID-'+category
            name='Manufacturer part 123' if category=='closures' else 'Useful '+category+' designation'
            original={'increment_disposition':{'thread_family':'NPTF','nominal_size':'1/4','pitch_tpi':'18 TPI','taper_parallel':'Taper'}} if category=='threads' else {}
            db.execute('INSERT INTO library_targets VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (identifier,domain,'internal_research_type',name,'','PARTIAL' if category in ('threads','surface-treatments') else 'VERIFIED',
                 'REFERENCE_ONLY','audit scope','{"gate":"FAIL"}','internal note',json.dumps(original)))
        db.execute('''INSERT INTO external_port_definitions
            (id,name,unit_system,stages_json,primitives_json,boundaries_json,machining_json,interface_json,clearance_diameter,clearance_height,usable)
            VALUES ('P','Existing port','metric','[]','[]','[]','[]','{}',10,20,1)''')
        db.execute("INSERT INTO library_evidence VALUES ('E','ID-closures','SRC',?)",(json.dumps(
            {'source_author':'Maker Works','source_id':'SECRET','evidence_id':'E','property':'installation_data',
             'raw_value':json.dumps({'part_number':'123','manufacturer':'Maker Works','pressure':'350 bar','material':'Steel'})}),))
        db.execute("INSERT INTO library_target_evidence VALUES ('ID-closures','E')")
        db.execute("INSERT INTO cartridges VALUES ('relation-only','Maker','123','','{}',1)")
        db.execute("INSERT INTO library_targets VALUES ('CAD','CAD / Assets','cad','CAD junk','','PARTIAL','','','','','{}')")
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(path))
    with TestClient(app) as client:yield client,path


def test_categories_cover_each_domain_once_counts_and_no_cad(library):
    client,path=library;before=path.read_bytes()
    data=client.get('/api/engineering-library/categories').json()
    assert len(data['items'])==20
    assert len(DOMAIN_CATEGORY)==18
    assert sum(r['knowledge_count'] for r in data['items'])==18
    cards={r['key']:r for r in data['items']}
    assert cards['external-ports']['definition_count']==1
    assert cards['closures']['definition_count']==0 and cards['closures']['knowledge_count']==1
    assert cards['closures']['browse_mode']=='knowledge'
    assert cards['threads']['knowledge_count']==1
    assert 'CAD' not in json.dumps(data)
    assert_friendly(data)
    assert path.read_bytes()==before


def test_knowledge_api_friendly_only_search_paging_and_detail(library):
    client,path=library;before=path.read_bytes()
    page=client.get('/api/engineering-library/knowledge',params={'category':'closures','q':'Maker Works','limit':1}).json()
    assert page['total']==1
    row=page['items'][0];assert row['name']=='Manufacturer part 123'
    detail=client.get('/api/engineering-library/knowledge/'+row['key']).json()
    assert {'label':'Operating pressure','value':'350 bar'} in detail['groups'][0]['fields']
    assert_friendly(page);assert_friendly(detail)
    body=json.dumps(detail)
    for name in ['audit scope','SECRET','REFERENCE_ONLY','internal_research_type','gate']:assert name not in body
    assert client.get('/api/engineering-library/knowledge',params={'category':'threads','status':'PARTIAL'}).json()['items'][0]['status']=='Partial data'
    assert path.read_bytes()==before


def test_unknown_domain_neutral_fallback_and_invalid_inputs(library):
    client,path=library
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO library_targets VALUES ('FUTURE','INTERNAL_PIPELINE_FUTURE','future','Useful new information','','PARTIAL','','','','','{}')")
    cards=client.get('/api/engineering-library/categories').json()['items']
    row=next(r for r in cards if r['key']=='other-knowledge')
    assert row['label']=='Additional Engineering Data' and row['knowledge_count']==1
    assert client.get('/api/engineering-library/knowledge',params={'category':'other-knowledge'}).json()['total']==1
    assert client.get('/api/engineering-library/knowledge',params={'category':'closures','limit':101}).status_code==422
    assert client.get('/api/engineering-library/knowledge',params={'category':'closures','offset':-1}).status_code==422
    assert client.get('/api/engineering-library/knowledge',params={'category':"' OR 1=1--"}).status_code==404
    assert client.get('/api/engineering-library/knowledge/not-a-record').status_code==404
    assert client.get('/api/engineering-library/knowledge/'+record_key('CAD')).status_code==404


def test_missing_values_and_cross_reference_keys_never_become_names():
    from manifold.library_presentation import text
    assert text('cav_0a123abc0123456789ab RAWTHREAD-hash')==''
    assert text('{"pressure":350}')==''
    assert text('NOT_REPORTED')==''
    assert text('NPTF')=='NPTF' and text('Rp')=='Rp'
    assert text('UN_SERIES_UNRESOLVED_PITCH_CLASS')=='UN · class not specified'


def test_relation_only_cartridge_and_material_presentations_have_no_audit(library):
    client,path=library;before=path.read_bytes()
    record=client.get('/api/engineering-library/cartridges/relation-only')
    assert record.status_code==200 and record.json()['available'] is False
    assert record.json()['cavity_identities']==[]
    assert_friendly(record.json())
    material=client.get('/api/engineering-library/materials/not-a-material')
    assert material.status_code==200 and material.json()['groups']==[]
    assert path.read_bytes()==before
