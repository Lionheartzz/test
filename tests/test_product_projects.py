import json
import pytest
from fastapi.testclient import TestClient
from manifold import store,projects
from manifold.schema import Design,Feature
from manifold.demo import demo
from manifold.server import app
from manifold.routing import route_cost,route_margin,adopt_routes,resolve_design
from manifold.route_edit import freeze,refine
HEADERS={'X-PMC-Request':'local-console'}

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects'/'demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    return TestClient(app)

def blank(name='Empty project'):
    return Design(name=name,block=dict(length=100,width=100,height=100,material='Test'))

def test_project_library_empty_start_and_independent_reopen(isolated):
    assert isolated.get('/api/health').json()['service']=='pmc-manifold'
    assert isolated.get('/api/catalog/manifest').json()['schema_version']==1
    assert isolated.get('/api/projects').json()==[]
    first=isolated.post('/api/projects',json=dict(design=blank().model_dump()),headers=HEADERS).json()
    second=isolated.post('/api/projects',json=dict(design=blank('Second').model_dump()),headers=HEADERS).json()
    assert first['project_id']!=second['project_id']
    d=first['design'];d['name']='Edited first'
    saved=isolated.post('/api/projects',json=dict(design=d,project_id=first['project_id'],expected_revision=first['revision']),headers=HEADERS)
    assert saved.status_code==200 and 'library' not in saved.json()['design']
    assert isolated.get('/api/projects/'+second['project_id']).json()['design']['name']=='Second'
    assert isolated.post('/api/projects',json=dict(design=d,project_id=first['project_id'],expected_revision=first['revision']),headers=HEADERS).status_code==409
    assert not store.PROJECT.exists() and store.current() is None


def test_project_library_lists_eight_projects_without_opening_or_engineering_resolution(isolated,monkeypatch):
    from manifold import engineering_db,network
    now='2026-09-18T12:00:00+00:00';engine=store.engine_revision()
    expected={}
    projects.folder().mkdir(parents=True)
    for index in range(8):
        design=blank(f'Project {index}').model_dump();revision=projects.saved_revision(design)
        build=None
        if index==1:build=dict(build_id='a'*32,design_revision=revision,engine_revision=engine,status='PASS',counts={})
        if index==2:build=dict(build_id='b'*32,design_revision=revision,engine_revision=engine,status='FAIL',counts={})
        if index==3:build=dict(build_id='c'*32,design_revision='0'*64,engine_revision=engine,status='PASS',counts={})
        key=f'{index:032x}';store.atomic_json(projects.path(key),dict(id=key,design=design,build=build,archived=False,updated_at=now))
        expected[index]=revision
    monkeypatch.setattr(projects,'snapshot',lambda *_:pytest.fail('listing opened a project snapshot'))
    monkeypatch.setattr(engineering_db,'validate_references',lambda *_a,**_k:pytest.fail('listing validated SQLite references'))
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda *_a,**_k:pytest.fail('listing resolved SQLite definitions'))
    monkeypatch.setattr(network,'endpoints',lambda:pytest.fail('listing performed network discovery'))
    calls=[];monkeypatch.setattr(store,'engine_current',lambda:calls.append(1) or True)
    response=isolated.get('/api/projects');assert response.status_code==200
    rows=response.json();assert len(rows)==8 and calls==[1]
    by_name={row['name']:row for row in rows}
    assert by_name['Project 0']['status']=='SAVED DRAFT'
    assert by_name['Project 1']['status']=='PASS' and by_name['Project 2']['status']=='FAIL'
    assert by_name['Project 3']['status']=='STALE'
    assert by_name['Project 7']['revision']==expected[7]
    assert all('engineering' not in row and 'network' not in row and row['project_context']=='metric' for row in rows)

def test_project_manage_preserves_copies_history_and_source(isolated):
    first=projects.save(blank());key=first['project_id']
    req=dict(expected_revision=first['revision'],action='duplicate',name='Copy')
    copy=isolated.post(f'/api/projects/{key}/manage',json=req,headers=HEADERS).json()
    assert copy['project_id']!=key and copy['design']['name']=='Copy'
    for action in ['archive','restore']:
        r=isolated.post(f'/api/projects/{key}/manage',json=dict(expected_revision=first['revision'],action=action),headers=HEADERS)
        assert r.status_code==200 and r.json()['archived']==(action=='archive')
    assert projects.read(copy['project_id'])['design']['name']=='Copy'
    assert list((projects.folder()/'history'/key).glob('*.json'))
    assert isolated.get('/api/projects/not-a-project').status_code==404
    assert isolated.post('/api/projects',json=dict(design=blank().model_dump(),project_id='../demo'),headers=HEADERS).status_code==422
    assert isolated.post('/api/projects',json=dict(design=blank().model_dump())).status_code==403

def test_project_build_failure_and_stale_save_do_not_replace_saved_project(isolated,monkeypatch):
    first=projects.save(blank());key=first['project_id'];before=projects.path(key).read_bytes()
    def fail(*args):raise RuntimeError('fixture CAD failure')
    monkeypatch.setattr(store,'build_outputs',fail)
    with pytest.raises(RuntimeError):projects.build(key,first['revision'])
    assert projects.path(key).read_bytes()==before

def test_each_project_retains_its_own_build_pointer(isolated):
    a=projects.save(demo());b=projects.save(blank('B'))
    result=projects.build(a['project_id'],a['revision'])
    assert result['build']['status']=='PASS' and not result['stale']
    assert projects.snapshot(projects.read(b['project_id']))['build'] is None
    assert store.current() is None
    assert (store.OUTPUT/'builds'/result['build']['build_id']/'production.step').is_file()

def test_routing_rewards_margin_without_relaxing_minimum_wall():
    d=blank();d.rules.minimum_wall=7
    near=Feature(id='NEAR',kind='drilling',face='left',u=11.2,v=50,circuit='P',diameter=8,depth=60,plugged=True)
    healthy=near.model_copy(update=dict(id='HEALTHY',u=18))
    assert route_margin(d,[near])['estimated_min_wall_mm']==pytest.approx(7.2)
    assert route_cost(d,[healthy])<route_cost(d,[near])
    d.constraints.preferred_wall_margin=0
    assert route_cost(d,[healthy])==route_cost(d,[near])
    assert d.rules.minimum_wall==7


def test_refining_route_extends_connected_branch_preserving_intent():
    d=blank();d.features=[
        Feature(id='TRUNK',kind='drilling',face='left',u=50,v=50,circuit='P',diameter=8,depth=70,plugged=True,frozen_net='P',connects_to=['BRANCH']),
        Feature(id='BRANCH',kind='drilling',face='front',u=50,v=50,circuit='P',diameter=8,depth=54,plugged=True,frozen_net='P',connects_to=['TRUNK'])]
    from manifold.schema import HydraulicNet
    d.nets=[HydraulicNet(id='P',members=[],routing='manual')]
    result,changed,notes=refine(d,'TRUNK',60,50)
    assert changed==['BRANCH'] and result.features[1].depth==64
    assert d.features[1].depth==54
    assert result.features[0].connects_to==d.features[0].connects_to
    assert result.nets==d.nets
    from manifold.geometry import build_geometry
    from manifold.validation import validate
    report=validate(result,build_geometry(result))
    for rule, count in [('expected_connection',1),('connected_interface',2),('circuit_connectivity',1)]:
        checks=[c for c in report['checks'] if c['rule']==rule]
        assert len(checks)==count and all(c['status']=='PASS' for c in checks), checks

def test_freeze_changes_only_selected_automatic_net():
    d=adopt_routes(demo());before=d.model_dump()
    result=freeze(d,'P')
    assert next(n for n in result.nets if n.id=='P').routing=='manual'
    assert all(n.routing=='automatic' for n in result.nets if n.id!='P')
    assert any(f.frozen_net=='P' for f in result.features)
    assert not any(f.route_net=='P' for f in result.features)
    assert d.model_dump()==before
