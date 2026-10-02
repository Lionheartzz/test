import copy
import math
import pytest
from fastapi.testclient import TestClient
from manifold import engineering_db,routing
from manifold.schema import Design,Feature,upgrade_project_v2
from manifold.engineering_conditions import effective_conditions,effective_net,material_strength,required_wall,wall_unresolved,project_engineering_context
from manifold.geometry import build_geometry
from manifold.validation import validate
from manifold.server import app

M65='material_rev2_b94740bd5246a06e64a9defb'
M80='material_rev2_a29da6fa9ef46e4c1da1310f'

def project(**extra):
    return Design(schema_version=3,name='Project engineering fixture',
        block=dict(length=120,width=120,height=100,material='Exact runtime identity',material_id=M65),
        project_defaults=dict(pressure_bar=250,flow_lpm=60,velocity_limit=6,drilling_mode='orthogonal'),
        nets=[dict(id='P',routing='automatic'),dict(id='T',routing='automatic',pressure_bar=30,flow_lpm=80,velocity_limit=4,drilling_mode='simplest')],**extra)

@pytest.mark.parametrize('field,source,default,override',[
    ('pressure_bar','pressure_source',250,30),('flow_lpm','flow_source',60,80),
    ('velocity_limit','velocity_source',6,4),('drilling_mode','drilling_mode_source','orthogonal','simplest')])
def test_default_override_precedence_updates_only_inherited_values(field,source,default,override):
    d=project();before=d.model_dump();p,t=d.nets
    assert effective_conditions(d,p)[field]==default and effective_conditions(d,p)[source]=='project'
    assert effective_conditions(d,t)[field]==override and effective_conditions(d,t)[source]=='net'
    setattr(d.project_defaults,field,300 if field=='pressure_bar' else 90 if field=='flow_lpm' else 8 if field=='velocity_limit' else 'allow-angled')
    assert effective_conditions(d,p)[field]==getattr(d.project_defaults,field)
    assert effective_conditions(d,t)[field]==override and getattr(p,field) is None
    assert before['nets'][0][field] is None

def test_new_v3_blank_floor_and_margin_really_mean_automatic_and_no_extra_preference():
    d=project();assert d.rules.minimum_wall is None and d.constraints.preferred_wall_margin is None
    f=Feature(id='BORE',kind='drilling',face='front',u=30,v=50,diameter=12,depth=20,circuit='P',tip_angle=180)
    assert 0<required_wall(d,f)<7
    assert d.rules.allowable_stress_mpa is None
    d.project_defaults.pressure_bar=None;assert required_wall(d,f)==0
    assert effective_conditions(d,d.nets[0])['pressure_source']=='unspecified'

def test_v2_and_versionless_adapter_preserves_concrete_old_defaults_and_explicit_rules():
    raw=dict(schema_version=2,name='Old',block=dict(length=120,width=120,height=100,material='legacy',material_id='material_1'),
             rules=dict(allowable_stress_mpa=100,pressure_safety_factor=2.5),nets=[dict(id='P',pressure_bar=280,flow_lpm=80)])
    before=copy.deepcopy(raw);d=Design.model_validate(raw);assert raw==before
    assert d.schema_version==3 and d.rules.minimum_wall==7 and d.constraints.preferred_wall_margin==4
    assert d.nets[0].velocity_limit==6 and d.nets[0].drilling_mode=='orthogonal'
    assert material_strength(d)['design_strength_mpa']==40
    assert Design.model_validate(d.model_dump()).model_dump()==d.model_dump()
    raw.pop('schema_version');assert Design.model_validate(raw).rules.minimum_wall==7

def separated(material):
    return Design(schema_version=3,name='Real local ligament screen',block=dict(length=120,width=120,height=100,material='exact',material_id=material),
        project_defaults=dict(pressure_bar=250),nets=[dict(id='P',routing='automatic'),dict(id='T',routing='manual',pressure_bar=30)],
        features=[dict(id='PROBE',kind='drilling',face='front',u=30,v=50,depth=20,diameter=12,tip_angle=180,circuit='P',route_net='P'),
                  dict(id='OTHER',kind='port',face='front',u=42.95,v=50,depth=20,diameter=12,tip_angle=180,circuit='T')])

def test_actual_source_strength_changes_exact_ligament_and_router_validator_agree():
    cases=[]
    for material in (M65,M80):
        d=separated(material);before=d.model_dump();g=build_geometry(d);report=validate(d,g)
        pair=next(c for c in report['checks'] if c['rule']=='minimum_feature_wall')
        required=required_wall(d,*d.features)
        failures=routing.route_obstructions(d,d.nets[0],[d.features[0]])
        assert abs(pair['actual']-.95)<1e-4 and abs(pair['required']-required)<1e-5
        assert (pair['status']=='FAIL')==any(f[0]=='cross_net_wall' for f in failures)
        assert material_strength(d)['status']=='SOURCE_BACKED'
        assert d.model_dump()==before
        cases.append((material_strength(d)['source_strength_mpa'],required,pair['status']))
    assert cases[0][0]<cases[1][0] and cases[0][1]>cases[1][1]
    assert [c[2] for c in cases]==['FAIL','PASS']

def test_project_floor_can_raise_never_lower_and_preferred_margin_is_not_failure_requirement():
    d=separated(M80);automatic=required_wall(d,*d.features)
    d.rules.minimum_wall=.1;assert required_wall(d,*d.features)==automatic
    d.rules.minimum_wall=6;assert required_wall(d,*d.features)==6
    d.rules.minimum_wall=None;before=validate(d,build_geometry(d))['checks']
    d.constraints.preferred_wall_margin=20;after=validate(d,build_geometry(d))['checks']
    assert before==after

def test_planning_ligament_cache_tracks_suppression_and_net_ownership():
    from manifold.engineering_conditions import planning_wall
    d=separated(M80);before=planning_wall(d)
    d.features[0].suppressed=True;assert planning_wall(d)<before
    d.features[0].suppressed=False;assert planning_wall(d)==before
    d.features[0].circuit='T';d.features[0].route_net=None;assert planning_wall(d)<before

@pytest.mark.parametrize('material',[None,'material_1','material_2','material_rev2_492922aeac1fa94c78d8faf1'])
def test_missing_or_inapplicable_strength_never_uses_tensile_or_assumed_grade(material):
    d=separated(M65);d.block.material_id=material
    assert material_strength(d)['status']=='UNRESOLVED' and wall_unresolved(d,d.features[0])
    failures=routing.route_obstructions(d,d.nets[0],[d.features[0]])
    assert ('pressure_strength','PROBE') in failures
    assert any(c['rule']=='pressure_strength' and c['status']=='FAIL' for c in validate(d,build_geometry(d))['checks'])

def test_inherited_flow_sizing_does_not_materialize_overrides_in_route_json():
    from test_routing_priorities import straight_net
    d=straight_net();d.project_defaults.flow_lpm=30;d.nets[0].flow_lpm=None;d.nets[0].velocity_limit=None
    target,metadata=routing.resolve_design(d,exact=False)
    assert metadata[0]['sizing']['status']=='FLOW_SIZED'
    assert target.nets[0].flow_lpm is None and target.nets[0].velocity_limit is None
    assert target.model_dump()['nets'][0]['flow_lpm'] is None

def test_effective_read_only_api_returns_sources_and_preserves_original_design():
    d=project();payload=d.model_dump();client=TestClient(app,base_url='http://127.0.0.1:8765')
    r=client.post('/api/engineering/conditions',json=payload,headers={'X-PMC-Request':'local-console'})
    assert r.status_code==200,r.text
    e=r.json()['nets'][0]['effective'];assert e['pressure_bar']==250 and e['pressure_source']=='project'
    assert d.model_dump()==payload

@pytest.mark.parametrize('preference,native',[('metric','inch'),('inch','metric')])
def test_project_unit_preference_does_not_restrict_other_native_standards(preference,native):
    rows=engineering_db.search_definitions(kind='external-port',unit=native,status='usable',limit=1)['items']
    assert rows
    d=Design(schema_version=3,name='Mixed standards',project_context=preference,block=dict(length=200,width=200,height=200,material='QA'),
        features=[dict(id='PORT',kind='port',face='front',u=100,v=100,port_definition_id=rows[0]['id'],circuit='P')])
    engineering_db.validate_references(d)
    assert build_geometry(d).production.isValid() and d.units=='mm'

def test_generation_preferences_are_request_only_and_ai_context_has_effective_sources():
    from manifold.ai_design.generation_models import GenerationOptions
    from manifold.ai_design.models import TaskInput
    d=project();snapshot=d.model_dump()
    options=GenerationOptions(preferred_component_face='front',preferred_port_face='left')
    context=project_engineering_context(TaskInput(title='Context',project_engineering=d).project_engineering)
    assert context['nets'][0]['overrides']['pressure_bar'] is None
    assert context['nets'][0]['effective']['pressure_source']=='project'
    assert options.preferred_component_face=='front' and d.model_dump()==snapshot
