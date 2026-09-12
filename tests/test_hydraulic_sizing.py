import pytest
from fastapi.testclient import TestClient
from manifold.schema import Design,ConstructionAccess,CavityDefinition
from manifold.routing import resolve_design,authorize_generated_contacts
from manifold.route_edit import freeze,refine
from manifold.geometry import build_geometry
from manifold.validation import validate
from manifold.server import app
from manifold.sizing import route_sizing


def design():
    return Design(name='Hydraulic sizing QA',block=dict(length=120,width=100,height=100,material='QA'),
        features=[dict(id=name,kind='port',face=face,u=50,v=50,circuit='P',diameter=20,depth=20,tip_angle=180)
                  for name,face in [('P1','left'),('P2','right')]],
        nets=[dict(id='P',members=['P1','P2'],routing='automatic',flow_lpm=40,velocity_limit=6)])


def report(d):
    g=build_geometry(d);authorize_generated_contacts(d,g)
    return validate(d,g)


def shape_signature(features):
    return [(f.id,f.face,f.u,f.v,f.depth,f.diameter,f.direction,f.plugged,f.plug_length) for f in features]


def test_auto_flow_uses_next_standard_and_exact_openings_pass():
    d=design();r,meta=resolve_design(d,exact=False)
    sizing=meta[0]['sizing']
    assert sizing['required_area_mm2']==pytest.approx(40*1000/60/6)
    assert 8<sizing['required_diameter_mm']<12
    assert sizing['status']=='FLOW_SIZED' and sizing['diameter_mm']==12
    assert all(f.diameter==12 for f in r.features if f.route_net)
    checks=report(r)
    assert checks['status']=='PASS',checks
    openings=[c for c in checks['checks'] if c['rule']=='connection_opening_area']
    assert openings and all(c['status']=='PASS' for c in openings)
    assert d.features==r.features[:2]  # source/terminal geometry not resized


def test_no_standard_large_enough_is_blocking_and_not_clamped():
    d=design();d.constraints.standard_drills=[4,6,8]
    with pytest.raises(ValueError,match='P: hydraulic sizing unresolved'):
        resolve_design(d,exact=False)
    response=TestClient(app).post('/api/preview',json=d.model_dump(),headers={'X-PMC-Request':'local-console'})
    assert response.status_code==422 and 'no available standard drill' in response.json()['detail']


def test_manual_override_retained_and_reports_insufficient_capacity():
    d=design();d.nets[0].diameter_mode='manual';d.nets[0].diameter=8
    r,_=resolve_design(d,exact=False)
    assert all(f.diameter==8 for f in r.features if f.route_net)
    result=report(r)
    assert any(c['rule']=='hydraulic_passage_area' and c['status']=='FAIL' for c in result['checks'])
    assert any(c['rule']=='connection_opening_area' and c['status']=='FAIL' for c in result['checks'])


def test_freeze_displayed_proposal_without_resolution_and_later_flow_change(monkeypatch):
    import manifold.route_edit as edit
    d=design();visible,_=resolve_design(d,exact=False)
    before=shape_signature([f for f in visible.features if f.route_net])
    monkeypatch.setattr(edit,'resolve_design',lambda *a,**k:pytest.fail('Adoption reran routing'))
    frozen=freeze(d,'P',visible)
    assert frozen.nets[0].routing=='manual' and frozen.nets[0].diameter_mode=='manual'
    assert not any(f.route_net for f in frozen.features)
    assert shape_signature([f for f in frozen.features if f.frozen_net])==before
    assert report(frozen)['status']=='PASS'
    frozen.nets[0].flow_lpm=100
    resolved,_=resolve_design(frozen)
    assert shape_signature([f for f in resolved.features if f.frozen_net])==before
    assert any(c['rule']=='hydraulic_passage_area' and c['status']=='FAIL' for c in report(resolved)['checks'])
    segment=next(f for f in frozen.features if f.frozen_net)
    edited,_,_=refine(frozen,segment.id,segment.u+1,segment.v)
    assert next(f for f in edited.features if f.id==segment.id).u==segment.u+1


def test_construction_access_uses_route_size_and_missing_flow_is_unresolved():
    d=design();d.nets[0].construction_access=[ConstructionAccess(id='X-P',face='top',fraction=.5)]
    d=Design.model_validate(d.model_dump());r,_=resolve_design(d,exact=False)
    assert any(f.plugged for f in r.features if f.route_net)
    assert all(f.diameter==12 for f in r.features if f.route_net)
    d.nets[0].flow_lpm=None
    assert route_sizing(d.nets[0],d.constraints.standard_drills)['status']=='UNRESOLVED_FLOW'


def test_source_interface_is_not_enlarged_to_make_flow_pass():
    d=design()
    d.library=[CavityDefinition(id='QA_PORT',label='QA limited window',manufacturer='QA',revision='1',provenance='demo',source='QA',thread_note='Unspecified QA',
                   usage_role='external-port',usage_decision='QA external port',stages=[dict(start=0,end=20,diameter=8)],
                   zones=[dict(id='flow',start=0,end=20,diameter=8)],clearance_diameter=20,clearance_height=20)]
    raw=d.model_dump();raw['features'][0].update(definition='QA_PORT',diameter=None,depth=None)
    d=Design.model_validate(raw);source=d.library[0].model_dump()
    r,_=resolve_design(d,exact=False)
    assert r.library[0].model_dump()==source
    result=report(r)
    assert any(c['rule']=='hydraulic_passage_area' and c['items']==['P1'] and c['status']=='FAIL' for c in result['checks'])
