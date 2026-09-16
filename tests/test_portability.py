import json
from fastapi.testclient import TestClient
from manifold import network,store
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
    assert store.PROJECT.read_bytes()==before
    files=[p for p in store.OUTPUT.rglob('*') if p.is_file()]
    assert files and all(p.parent.name=='cad-diagnostics' and p.suffix=='.json' for p in files)
