import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from manifold.schema import Design,ConstructionAccess
from manifold.engineering_db import initialize_schema, get_definition
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
    assert sizing['status']=='FLOW_SIZED' and sizing['diameter_mm']>=sizing['required_diameter_mm']
    assert sizing['selected_tool_id'].startswith('tool_')
    assert all(f.diameter==sizing['diameter_mm'] for f in r.features if f.route_net)
    checks=report(r)
    assert checks['status']=='PASS',checks
    openings=[c for c in checks['checks'] if c['rule']=='connection_opening_area']
    assert openings and all(c['status']=='PASS' for c in openings)
    assert d.features==r.features[:2]  # source/terminal geometry not resized


def test_no_standard_large_enough_is_blocking_and_not_clamped(monkeypatch):
    monkeypatch.setattr('manifold.engineering_db.tool_definitions',lambda *args,**kwargs:[
        dict(id=f'TOOL_{diameter}',diameter_mm=diameter,max_depth_mm=200) for diameter in (4,6,8)])
    d=design();d.constraints.standard_drills=[4,6,8]
    with pytest.raises(ValueError,match='P: hydraulic sizing unresolved'):
        resolve_design(d,exact=False)


def test_manual_override_retained_and_reports_insufficient_capacity():
    d=design();d.nets[0].diameter_mode='manual';d.nets[0].diameter=8
    r,_=resolve_design(d,exact=False)
    assert all(f.diameter==8 for f in r.features if f.route_net)
    result=report(r)
    assert any(c['rule']=='hydraulic_passage_area' and c['status']=='FAIL' for c in result['checks'])
    assert any(c['rule']=='connection_opening_area' and c['status']=='FAIL' for c in result['checks'])


def test_freeze_displayed_proposal_without_resolution_and_later_flow_change(monkeypatch):
    import manifold.route_edit as edit
    d=design();d.nets[0].construction_access=[ConstructionAccess(id='ACCESS_P',face='top',fraction=.5)]
    visible,_=resolve_design(d,exact=False)
    before=shape_signature([f for f in visible.features if f.route_net])
    monkeypatch.setattr(edit,'resolve_design',lambda *a,**k:pytest.fail('Adoption reran routing'))
    frozen=freeze(d,'P',visible)
    assert frozen.nets[0].routing=='manual' and frozen.nets[0].diameter_mode=='manual'
    assert frozen.nets[0].construction_access==d.nets[0].construction_access
    assert not any(f.route_net for f in frozen.features)
    assert shape_signature([f for f in frozen.features if f.frozen_net])==before
    Design.model_validate(frozen.model_dump())
    frozen.nets[0].flow_lpm=100
    resolved,_=resolve_design(frozen)
    assert shape_signature([f for f in resolved.features if f.frozen_net])==before
    assert route_sizing(resolved.nets[0])['required_diameter_mm']>resolved.nets[0].diameter
    segment=next(f for f in frozen.features if f.frozen_net)
    edited,_,_=refine(frozen,segment.id,segment.u+1,segment.v)
    assert next(f for f in edited.features if f.id==segment.id).u==segment.u+1


def test_construction_access_uses_route_size_and_missing_flow_is_unresolved():
    d=design();d.nets[0].construction_access=[ConstructionAccess(id='X-P',face='top',fraction=.5)]
    d=Design.model_validate(d.model_dump());r,meta=resolve_design(d,exact=False)
    assert any(f.plugged for f in r.features if f.route_net)
    assert all(f.diameter==meta[0]['sizing']['diameter_mm'] for f in r.features if f.route_net)
    d.nets[0].flow_lpm=None
    assert route_sizing(d.nets[0],d.constraints.standard_drills)['status']=='UNRESOLVED_FLOW'


def test_source_interface_is_not_enlarged_to_make_flow_pass(tmp_path,monkeypatch):
    path=tmp_path/'engineering.db';connection=sqlite3.connect(path);initialize_schema(connection)
    stages=json.dumps([dict(start=0,end=20,diameter=8)])
    primitives=json.dumps([dict(kind='cylinder',source_ref='qa',start=0,end=20,diameter=8,end_diameter=0,inner_diameter=0,offset_u=0,offset_v=0)])
    interface=json.dumps(dict(id='flow',start=0,end=20,diameter=8,offset_u=0,offset_v=0,clip_to_cut=True))
    connection.execute('INSERT INTO external_port_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        ('QA_PORT','QA limited window','QA','metric','QA','Unspecified QA',stages,primitives,'[]','[]',interface,20,20,1,'',1,None))
    connection.execute('INSERT INTO tool_definitions VALUES (?,?,?,?,?,?,?)',('TOOL_8','drill',8,160,'metric',1,1))
    connection.execute('INSERT INTO tool_definitions VALUES (?,?,?,?,?,?,?)',('TOOL_12','drill',12,160,'metric',1,1))
    connection.commit();connection.close();monkeypatch.setenv('PMC_ENGINEERING_DB',str(path))
    d=design()
    raw=d.model_dump();raw['features'][0].update(port_definition_id='QA_PORT',diameter=None,depth=None)
    d=Design.model_validate(raw);source=get_definition('QA_PORT').model_dump()
    r,_=resolve_design(d,exact=False)
    assert get_definition('QA_PORT').model_dump()==source
    result=report(r)
    assert any(c['rule']=='hydraulic_passage_area' and c['items']==['P1'] and c['status']=='FAIL' for c in result['checks'])


def test_auto_sizing_uses_candidate_depth_instead_of_whole_block(monkeypatch):
    monkeypatch.setattr('manifold.engineering_db.tool_definitions',lambda *args,**kwargs:[
        dict(id='TOOL_8_5',diameter_mm=8.5,max_depth_mm=120,unit_system='metric'),
        dict(id='TOOL_10',diameter_mm=10,max_depth_mm=300,unit_system='inch')])
    d=Design(name='Actual route depth',block=dict(length=200,width=70,height=70,material='QA'),
        features=[dict(id='P1',kind='port',face='front',u=80,v=35,circuit='P',diameter=12,depth=12,tip_angle=180),
                  dict(id='P2',kind='port',face='front',u=100,v=35,circuit='P',diameter=12,depth=12,tip_angle=180)],
        nets=[dict(id='P',members=['P1','P2'],routing='automatic',flow_lpm=20,velocity_limit=6)])
    resolved,meta=resolve_design(d,exact=False)
    assert meta[0]['sizing']['selected_tool_id']=='TOOL_8_5'
    assert max(f.depth for f in resolved.features if f.route_net)<120
