import copy
import hashlib
import json
from fastapi.testclient import TestClient
from manifold import catalog,network,store
from manifold.demo import demo
from manifold.server import app


def test_lan_hosts_and_exact_same_origin_follow_current_machine(monkeypatch):
    monkeypatch.setattr(network,'local_names',lambda:{'127.0.0.1','localhost','192.168.40.7','new-pc'})
    client=TestClient(app,base_url='http://192.168.40.7:8765')
    headers={'X-PMC-Request':'local-console','Origin':'http://192.168.40.7:8765'}
    monkeypatch.setenv('PMC_LAN','0')
    assert client.post('/api/check-design',json=demo().model_dump(),headers=headers).status_code==403
    monkeypatch.setenv('PMC_LAN','1')
    assert client.post('/api/check-design',json=demo().model_dump(),headers=headers).status_code==200
    for origin in ['http://192.168.40.8:8765','http://192.168.40.7:9000','https://192.168.40.7:8765','null','http://evil.example','http://192.168.40.7:8765/path']:
        assert client.post('/api/check-design',json=demo().model_dump(),headers={**headers,'Origin':origin}).status_code==403
    assert client.get('/api/state',headers={'Host':'evil.example:8765'}).status_code==403
    assert client.get('/api/state',headers={'Host':'192.168.40.8:8765'}).status_code==403
    machine=TestClient(app,base_url='http://new-pc:8765')
    assert machine.post('/api/check-design',json=demo().model_dump(),headers={**headers,'Origin':'http://new-pc:8765'}).status_code==200
    assert machine.post('/api/check-design',json=demo().model_dump()).status_code==403


def test_exact_draft_solid_is_machined_without_committing(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'PROJECT',tmp_path/'demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    d=demo();store.atomic_json(store.PROJECT,d.model_dump());before=store.PROJECT.read_bytes()
    response=TestClient(app).post('/api/preview-solid',json=d.model_dump(),headers={'X-PMC-Request':'local-console'})
    assert response.status_code==200
    result=response.json()
    assert result['status']=='UNVALIDATED_EXACT_GEOMETRY'
    assert result['model']['geometry_kind']=='machined-brep'
    body=next(p for p in result['model']['parts'] if p['kind']=='body')
    assert len(body['triangles'])>36 # Not the twelve triangles of an unmachined box.
    assert 0<result['model']['volume_mm3']<d.block.length*d.block.width*d.block.height
    assert store.PROJECT.read_bytes()==before and not store.OUTPUT.exists()


def test_pmc_interpretation_keeps_original_import_and_related_records():
    id='inch:lib45:cavity:57'
    definition=catalog.definition(id)
    source=definition.native.record.model_dump()
    relations=copy.deepcopy(definition.native.related_records)
    path=catalog.records()[id][1];file_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    body=definition.model_dump()
    body['native']['mapping_record']=copy.deepcopy(source)
    body['native']['mapping_record']['geometry']['axial_profile'][0]['depth']['value']+=.001
    response=TestClient(app).post('/api/library/project-native',json=body,headers={'X-PMC-Request':'local-console'})
    assert response.status_code==200
    mapped=response.json()
    assert mapped['native']['record']==source
    assert mapped['native']['related_records']==relations
    assert mapped['native']['mapping_record']!=source
    assert mapped['native']['source_sha256']==definition.native.source_sha256
    assert hashlib.sha256(path.read_bytes()).hexdigest()==file_hash
    assert catalog.get_record(id)==source
    # A caller modifying a returned source object cannot modify the catalog cache.
    detached=catalog.get_record(id);detached['geometry']['axial_profile'][0]['depth']['value']=999
    assert catalog.get_record(id)==source
