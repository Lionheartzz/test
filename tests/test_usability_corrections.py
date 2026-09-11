import json
import pytest
from fastapi.testclient import TestClient
from manifold import catalog,projects,store
from manifold.schema import Design,Feature
from manifold.server import app

HEADERS={'X-PMC-Request':'local-console'}

def test_external_port_uses_source_cut_not_summary_bore():
    from manifold.geometry import build_geometry
    from manifold.routing import terminal_points
    from manifold.kinematics import pose
    definition=catalog.definition('metric:lib167:cavity:3')
    original=catalog.get_record('metric:lib167:cavity:3')
    assert original['cavity_type']=='Port' and len(definition.zones)==1
    assert definition.native.record.model_dump()==original
    design=Design(name='Source port',block=dict(length=160,width=140,height=120,material='Test'),library=[definition],features=[
        dict(id='P',kind='port',face='front',u=80,v=60,circuit='P',definition=definition.id,size='G1/2 BSPP')])
    f=design.features[0];g=build_geometry(design)
    cavity=design.model_copy(deep=True)
    cavity.features=[Feature(id='CV',kind='cavity',face=f.face,u=f.u,v=f.v,definition=definition.id,circuits={definition.zones[0].id:'P'})]
    expected=build_geometry(cavity)
    assert g.cuts['P'].Volume()==pytest.approx(expected.cuts['CV'].Volume())
    assert g.cuts['P'].cut(expected.cuts['CV']).Volume()<1e-6
    assert set(g.nodes)=={'P'} and g.circuits=={'P':'P'}
    p,axis=pose(f,design.block);z=definition.zones[0]
    assert terminal_points(design)['P']==pytest.approx(tuple(a+b*(z.start+z.end)/2 for a,b in zip(p,axis)))
    raw=design.model_dump();raw['features'][0]['diameter']=999;raw['features'][0]['depth']=999
    normalized=Design.model_validate(raw)
    assert normalized.features[0].diameter==f.diameter and normalized.features[0].depth==f.depth

def test_port_definition_rejects_cartridge_semantics():
    from manifold.demo import demo
    d=demo();definition=d.library[0]
    with pytest.raises(ValueError,match='usage role is not external-port'):
        Design(name='Invalid port',block=d.block,library=[definition],features=[dict(id='P',kind='port',face='front',u=40,v=50,circuit='P',definition=definition.id)])

def test_cavity_search_and_definition_do_not_load_unrelated_catalog(monkeypatch):
    monkeypatch.setattr(catalog,'records',lambda: (_ for _ in ()).throw(AssertionError('Full catalog load')))
    rows=catalog.search(kind='port_definition',q='BSP',unit='metric',limit=30)
    assert rows['total']>0 and all(r['cavity_type']=='Port' for r in rows['items'])
    d=catalog.definition('metric:lib167:cavity:3')
    assert len(d.zones)==1 and d.native.record.id=='metric:lib167:cavity:3'

def test_footprint_search_indexes_cover_all_full_source_relationships():
    for unit in ('metric','inch'):
        index=catalog.footprint_index(str(catalog.ROOT),unit)
        expected={}
        for record,_ in catalog.group_records(str(catalog.ROOT),unit,'footprints').values():
            expected.setdefault(record['source_identity']['cavity_ref'],set()).add(record['id'])
        assert index==expected

def test_delete_project_requires_confirmation_and_preserves_shared_data(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects'/'demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    client=TestClient(app)
    d=Design(name='Delete only this',block=dict(length=100,width=100,height=100,material='Test'))
    state=projects.save(d);key=state['project_id'];projects.save(d,key,state['revision'])
    other=projects.save(d.model_copy(update={'name':'Keep me'}))
    shared=tmp_path/'projects'/'library'/'source.json';shared.parent.mkdir();shared.write_text('source unchanged')
    build=tmp_path/'output'/'builds'/'proof'/'evidence.json';build.parent.mkdir(parents=True);build.write_text('immutable')
    url=f'/api/projects/{key}/delete';payload=dict(expected_revision=state['revision'],confirm_name=d.name)
    assert client.post(url,json=payload).status_code==403
    assert client.post(url,json={**payload,'confirm_name':'wrong'},headers=HEADERS).status_code==409
    assert client.post(url,json={**payload,'expected_revision':'0'*64},headers=HEADERS).status_code==409
    assert projects.path(key).exists()
    assert client.post(url,json=payload,headers=HEADERS).status_code==200
    assert not projects.path(key).exists() and not (projects.folder()/'history'/key).exists()
    assert client.get(f'/api/projects/{key}').status_code==404
    assert projects.path(other['project_id']).exists() and shared.read_text()=='source unchanged' and build.read_text()=='immutable'
    assert client.post('/api/projects/not-an-id/delete',json=payload,headers=HEADERS).status_code==409
