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
    assert isolated.get('/api/library').json()==[]
    assert isolated.get('/api/projects').json()==[]
    first=isolated.post('/api/projects',json=dict(design=blank().model_dump()),headers=HEADERS).json()
    second=isolated.post('/api/projects',json=dict(design=blank('Second').model_dump()),headers=HEADERS).json()
    assert first['project_id']!=second['project_id']
    d=first['design'];d['name']='Edited first'
    saved=isolated.post('/api/projects',json=dict(design=d,project_id=first['project_id'],expected_revision=first['revision']),headers=HEADERS)
    assert saved.status_code==200 and saved.json()['design']['library']==[]
    assert isolated.get('/api/projects/'+second['project_id']).json()['design']['name']=='Second'
    assert isolated.post('/api/projects',json=dict(design=d,project_id=first['project_id'],expected_revision=first['revision']),headers=HEADERS).status_code==409
    assert not store.PROJECT.exists() and store.current() is None

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


def test_automatic_route_prefers_healthier_equal_complexity_elbow():
    from manifold.schema import CavityDefinition,HydraulicNet
    from manifold.routing import route_options,authorize_generated_contacts
    from manifold.geometry import build_geometry
    from manifold.validation import validate
    d=blank()
    d.library=[CavityDefinition(id='TEST',label='Synthetic window',source='Test geometry only',thread_note='',
        stages=[dict(start=0,end=20,diameter=4)],zones=[dict(id='p',start=10,end=15,diameter=4)],clearance_diameter=4,clearance_height=5)]
    d.features=[Feature(id=k,kind='cavity',face='top',u=x,v=y,definition='TEST',circuits={'p':'P'}) for k,x,y in [('C1',11.5,70),('C2',70,30)]]
    d.nets=[HydraulicNet(id='P',members=['C1:p','C2:p'],routing='automatic',diameter=4)]
    d.constraints.preferred_wall_margin=6
    options=route_options(d,d.nets[0]);chosen=options[0]
    competitor=next(o for o in options if o['key']=='yxz:nearest:direct')
    assert len(chosen['route'])==len(competitor['route'])==2
    assert sum(f.depth for f in chosen['route'])==sum(f.depth for f in competitor['route'])
    assert route_margin(d,chosen['route'])['estimated_min_wall_mm']>route_margin(d,competitor['route'])['estimated_min_wall_mm']
    resolved,_=resolve_design(d);g=build_geometry(resolved);authorize_generated_contacts(resolved,g)
    assert validate(resolved,g)['status']=='PASS'

def test_refining_route_extends_connected_branch_preserving_intent():
    d=blank();d.features=[
        Feature(id='TRUNK',kind='drilling',face='left',u=50,v=50,circuit='P',diameter=8,depth=70,plugged=True,frozen_net='P',connects_to=['BRANCH']),
        Feature(id='BRANCH',kind='drilling',face='front',u=50,v=50,circuit='P',diameter=8,depth=54,plugged=True,frozen_net='P',connects_to=['TRUNK'])]
    d.nets=[]
    result,changed,notes=refine(d,'TRUNK',60,50)
    assert changed==['BRANCH'] and result.features[1].depth==64
    assert d.features[1].depth==54
    assert result.features[0].connects_to==d.features[0].connects_to
    assert result.nets==d.nets
    from manifold.geometry import build_geometry
    from manifold.validation import validate
    report=validate(result,build_geometry(result))
    assert not [c for c in report['checks'] if c['rule']=='required_connection' and c['status']=='FAIL']

def test_freeze_changes_only_selected_automatic_net():
    d=adopt_routes(demo());before=d.model_dump()
    result=freeze(d,'P')
    assert next(n for n in result.nets if n.id=='P').routing=='manual'
    assert all(n.routing=='automatic' for n in result.nets if n.id!='P')
    assert any(f.frozen_net=='P' for f in result.features)
    assert not any(f.route_net=='P' for f in result.features)
    assert d.model_dump()==before


def test_source_circle_and_assembly_role_are_preserved_without_name_matching(isolated):
    import hashlib,math
    from manifold import catalog
    from manifold.boundaries import boundary_shape
    from manifold.geometry import build_geometry
    record=catalog.get_record('metric:assembly_envelope:56')
    source_path=catalog.records()[record['id']][1]
    before=hashlib.sha256(source_path.read_bytes()).hexdigest()
    shape=boundary_shape(record['dimension_raw'],record['envelope_type'])
    assert shape==dict(circle=(0,0,60))
    assert boundary_shape(record['dimension_raw'],'Custom') is None
    assert boundary_shape(record['dimension_raw'].replace('A;60;0;0;60','A;61;0;0;60'),'Circle') is None
    d=demo();d.features=[d.features[0]];d.features[0].u=90;d.features[0].v=60;d.nets=[]
    payload=dict(design=d.model_dump(),definition_id=d.features[0].definition,source_id=record['id'],category='service',height=12,decision='Synthetic test association; not vendor approval')
    response=isolated.post('/api/assign-boundary',json=payload,headers=HEADERS)
    assert response.status_code==200,response.text
    result=Design.model_validate(response.json())
    boundary=result.library[0].boundaries[-1]
    assert boundary.source_role=='assembly-envelope' and boundary.category=='service'
    assert boundary.association=='engineer-selected' and boundary.source_raw==record['dimension_raw']
    assert result.library_resources[-1].record==record
    geometry=build_geometry(result)
    assert geometry.boundaries['CV1/0']['shape'].Volume()==pytest.approx(math.pi*60**2*12)
    assert hashlib.sha256(source_path.read_bytes()).hexdigest()==before
    assert not d.library[0].boundaries and not d.library_resources
