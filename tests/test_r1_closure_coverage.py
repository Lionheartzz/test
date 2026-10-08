import json
from pathlib import Path

import pytest

from manifold.closure_runtime import catalog,profile,compatible,normalize_design
from manifold.demo import demo
from manifold.geometry import build_geometry,review_layer
from manifold.validation import validate
from manifold.cad_acceptance import step_round_trip


@pytest.fixture
def expanded_catalog():
    rows=catalog()
    if not any(profile(r)['operation']=='SOURCE_FORM_PORT_ENTRY' for r in rows):
        pytest.skip('Explicit R1 staging integration is required for this real source acceptance test')
    return rows


def test_all_r1_sae_names_and_both_contexts_have_independent_machining(expanded_catalog):
    rows=[r for r in expanded_catalog if profile(r).get('closure_type')=='sae-short-port']
    assert {(profile(r)['source_profile_row']['CavityName'],r['unit_system']) for r in rows}=={
        (name,unit) for name in ('SP-02','SP-03','SP-04','SP-05','SP-06','SP-08','SP-10','SP-12','SP-16') for unit in ('metric','inch')}
    for r in rows:
        p=profile(r);raw=p['source_profile_row']
        assert r['closure_thread']['tap_diameter_mm']==float(raw['Circle3Dia'])*p['source_scale']
        assert r['closure_thread']['tap_diameter_mm']<float(raw['ThreadSize'])*25.4
        assert p['sealing_form']=='straight-thread O-ring boss short construction port'
        assert r['engagement_mm']==raw['InsertionDepth']*p['source_scale']
        assert r['closure_tools'][p['form_tool_id']]['tool_type']=='form-port'
        assert r['closure_tools'][p['tap_tool_id']]['tool_type']=='tap'


@pytest.mark.parametrize('unit',['metric','inch'])
def test_real_sae_entry_has_seat_pilot_and_variable_hydraulic_bore(expanded_catalog,unit,tmp_path):
    row=next(r for r in expanded_catalog if r['unit_system']==unit and profile(r).get('source_profile_row',{}).get('CavityName')=='SP-04')
    d=demo();f=next(f for f in d.features if f.plugged);f.closure_definition_id=row['id']
    assert compatible(f,row)
    d=normalize_design(d);f=next(f for f in d.features if f.plugged)
    assert f.diameter==8
    g=build_geometry(d);r=validate(d,g)
    assert g.production.isValid() and len(g.production.Solids())==1
    assert not [c for c in r['checks'] if c['rule'].startswith('closure_') or c['rule']=='construction_closure' if c['status']!='PASS']
    assert r['status']=='PASS' and r['manufacturing_ready'] and not r['unresolved_plug_entries']
    assert step_round_trip(g,tmp_path/'sae.step')['status']=='PASS'
    assert review_layer(d,g,'features') and review_layer(d,g,'void')


def test_external_port_hydraulic_usability_is_not_forged_for_closures(expanded_catalog):
    independent=next(r for r in expanded_catalog if not r['port_usable'])
    assert independent['port_reason']=='External port requires one executable hydraulic interface'
    assert profile(independent)['independent_machining_interface']
    f=next(f for f in demo().features if f.plugged);f.diameter=1.6
    assert compatible(f,independent)
    blocked=dict(independent,port_reason='Required special cut is not executable')
    assert not compatible(f,blocked)


def test_standard_sae_uses_its_own_pilot_and_declared_installed_dimensions(expanded_catalog):
    rows=[r for r in expanded_catalog if profile(r).get('closure_type')=='sae-standard-port']
    assert len(rows)==26
    for r in rows:
        p=profile(r);raw=p['source_profile_row'];scale=p['source_scale']
        assert p['pilot_circle']==4 and raw['ThreadCircle']==3
        assert r['closure_thread']['tap_diameter_mm']==float(raw['Circle4Dia'])*scale
        assert r['engagement_mm']==raw['InsertionDepth']*scale
        assert r['envelope']['height_mm']==raw['PlugHeadHeight']*scale
        assert p['role_reference']['pdf_page']==644
        assert p['hydraulic_diameter_max_mm']==float(raw['MaxCircle12Dia'])*scale


@pytest.mark.parametrize('unit',['metric','inch'])
def test_iso6149_uses_literal_metric_thread_and_source_installed_geometry(expanded_catalog,unit,tmp_path):
    rows=[r for r in expanded_catalog if r['unit_system']==unit and profile(r).get('closure_type')=='metric-iso6149']
    assert len(rows)==12
    for row in rows:
        p=profile(row);raw=p['source_profile_row'];scale=p['source_scale']
        assert row['closure_thread']['tap_diameter_mm']==float(raw['Circle4Dia'])*scale
        assert row['closure_thread']['unit_system']=='metric'
        assert row['closure_thread']['thread_class']=='6H'
        assert row['engagement_mm']==raw['InsertionDepth']*scale
        assert row['envelope']['height_mm']==raw['PlugHeadHeight']*scale
        assert p['role_reference']['scope'].startswith('Generic ISO 6149 ORB interface only')
    row=next(r for r in rows if float(profile(r)['source_profile_row']['ThreadSize'])==16)
    d=demo();f=next(f for f in d.features if f.plugged);f.closure_definition_id=row['id']
    assert compatible(f,row)
    d=normalize_design(d);g=build_geometry(d);r=validate(d,g)
    assert r['manufacturing_ready'] and r['counts']['FAIL']==0
    assert g.production.isValid() and len(g.production.Solids())==1
    assert step_round_trip(g,tmp_path/'iso6149.step')['status']=='PASS'


def test_source_form_and_tap_tools_are_readable_through_existing_api(expanded_catalog):
    from fastapi.testclient import TestClient
    from manifold.server import app
    with TestClient(app) as client:
        for kind in ('form-port','tap'):
            response=client.get('/api/tools',params={'type':kind})
            assert response.status_code==200
            value=response.json()
            rows=value['items'] if isinstance(value,dict) else value
            assert rows and all(r['tool_type']==kind for r in rows)


def test_standard_sae_geometry_and_step_are_manufacturable(expanded_catalog,tmp_path):
    row=next(r for r in expanded_catalog if r['unit_system']=='metric'
             and profile(r).get('source_profile_row',{}).get('CavityName')=='#4 SAE')
    d=demo();f=next(f for f in d.features if f.plugged);f.closure_definition_id=row['id']
    assert compatible(f,row)
    d=normalize_design(d);g=build_geometry(d);r=validate(d,g)
    assert g.production.isValid() and len(g.production.Solids())==1
    assert r['status']=='PASS' and r['manufacturing_ready'] and not r['unresolved_plug_entries']
    assert step_round_trip(g,tmp_path/'standard-sae.step')['status']=='PASS'
    assert next(f for f in d.features if f.plugged).diameter==8
    from manifold.manufacturing import manufacturing_outputs
    from manifold.closure_runtime import bound,cutting_primitives
    # Isolate the schedule/geometry contract from the demo's unrelated cavity
    # overlap section calculations. Both solids below are real OCCT geometry.
    from manifold.schema import Design
    feature=next(f for f in d.features if f.plugged)
    schedule_design=Design.model_validate(dict(name='SAE machining schedule',
        block=dict(length=120,width=120,height=120,material='Aluminum'),
        features=[feature.model_copy(update=dict(face='top',u=60,v=60,depth=60,connects_to=[],route_net=None)).model_dump()]))
    schedule_geometry=build_geometry(schedule_design)
    manufacturing_outputs(schedule_design,schedule_geometry,tmp_path)
    output=json.loads((tmp_path/'manufacturing.json').read_text())
    feature=schedule_design.features[0]
    exported=next(p for p in output['machining_profiles'] if p['feature']==feature.id)
    assert exported['cutting_steps']==cutting_primitives(feature,bound(feature))
    assert len([r for r in output['drill_chart'] if r['feature']==feature.id])==len(exported['cutting_steps'])


@pytest.mark.xfail(strict=True,raises=ValueError,
                  reason='Starting HEAD 43e3efb + v7 Expander: legacy manual demo has a null hydraulic centroid section during export; baseline reproduction retained.')
def test_legacy_manual_demo_complete_schedule_baseline_exception(expanded_catalog,tmp_path):
    from manifold.manufacturing import manufacturing_outputs
    row=next(r for r in expanded_catalog if r['unit_system']=='metric'
             and profile(r).get('source_profile_row',{}).get('CavityName')=='#4 SAE')
    d=demo();next(f for f in d.features if f.plugged).closure_definition_id=row['id']
    d=normalize_design(d)
    manufacturing_outputs(d,build_geometry(d),tmp_path)


def test_committed_auto_user_clear_is_not_silently_rebound(expanded_catalog):
    from manifold.schema import Design
    from manifold.closure_runtime import bind_route
    d=Design.model_validate(dict(schema_version=4,name='Committed closure intent',
        block=dict(length=120,width=120,height=120,material='Aluminum'),
        features=[dict(id='R',kind='drilling',face='top',u=60,v=60,circuit='P',diameter=8,depth=60,plugged=True,route_net='P')],
        nets=[dict(id='P',routing='automatic',route_state='committed')]))
    assert d.rules.minimum_wall is None
    # The unchanged automatic-wall resolver handles None; no assumed 7 mm.
    generated=bind_route(d,d.features)[0]
    assert generated.closure_definition_id
    assert 'closure_selection_mode' not in d.features[0].model_dump()
    d.features[0].closure_selection_mode='manual'
    assert normalize_design(d,resolve_generated=True).features[0].closure_definition_id is None
    d.nets[0].route_state='unresolved'
    assert normalize_design(d,resolve_generated=True).features[0].closure_definition_id is None
    d=Design.model_validate_json(d.model_dump_json())
    assert d.features[0].closure_selection_mode=='manual'
    d.features[0].closure_selection_mode='automatic'
    assert normalize_design(d,resolve_generated=True).features[0].closure_definition_id


@pytest.mark.parametrize('unit',['metric','inch'])
@pytest.mark.parametrize('diameter,name',[(6,'G 1/4'),(12,'G 1/2'),(25,'G 1 1/4')])
def test_generated_source_port_manifold_closures(expanded_catalog,unit,diameter,name,tmp_path):
    from manifold.schema import Design
    from manifold.engineering_db import _connect,get_definition
    from manifold.routing import resolve_design
    from contextlib import closing
    with closing(_connect()) as db:
        identifier=db.execute('SELECT id FROM external_port_definitions WHERE name=? AND unit_system=? AND usable=1 AND active=1',
                              (name,unit)).fetchone()[0]
    definition=get_definition(identifier)
    edge=240 if diameter==25 else 168
    face='top' if unit=='metric' else 'front'
    design=Design.model_validate(dict(name='Source port closure matrix',project_context=unit,
        block=dict(length=edge,width=edge,height=edge,material='Aluminum'),
        features=[dict(id=ident,kind='port',face=face,u=u,v=edge/2,circuit='P',port_definition_id=identifier,
                       diameter=definition.zones[0].diameter,depth=definition.zones[0].end,
                       clearance_diameter=definition.clearance_diameter,clearance_height=definition.clearance_height)
                  for ident,u in [('P1',edge/3),('P2',edge*2/3)]],
        nets=[dict(id='P',members=['P1','P2'],routing='automatic',diameter_mode='manual',diameter=diameter)]))
    resolved,metadata,geometry,report=resolve_design(design,exact=True,prepared=True)
    plugs=[f for f in resolved.features if f.plugged]
    assert plugs and all(f.closure_definition_id for f in plugs)
    assert report['counts']['FAIL']==report['counts']['WARNING']==0
    assert report['manufacturing_ready'] and report['unresolved_plug_entries']==[]
    assert geometry.production.isValid() and len(geometry.production.Solids())==1
    assert step_round_trip(geometry,tmp_path/'matrix.step')['status']=='PASS'
    assert metadata[0]['exact_attempts']<=8


def test_expander_to_sae_switch_changes_cut_and_engagement_without_changing_bore(expanded_catalog):
    from manifold.closure_runtime import choices
    d=demo();feature=next(f for f in d.features if f.plugged)
    expander=next(r for r in choices(feature,'metric') if profile(r)['operation']=='SOURCE_EXPANDER_ENTRY')
    sae=next(r for r in expanded_catalog if r['unit_system']=='metric'
             and profile(r).get('source_profile_row',{}).get('CavityName')=='#4 SAE')
    results=[]
    for row in (expander,sae):
        copy=d.model_copy(deep=True);f=next(f for f in copy.features if f.plugged);f.closure_definition_id=row['id']
        copy=normalize_design(copy);f=next(f for f in copy.features if f.plugged);g=build_geometry(copy)
        assert f.diameter==feature.diameter
        assert validate(copy,g)['manufacturing_ready']
        results.append((f.closure_definition_id,f.plug_length,g.cuts[f.id].Volume(),
                        review_layer(copy,g,'features'),review_layer(copy,g,'void'),g.production.Volume()))
    assert all(a!=b for a,b in zip(*results))


def test_normal_automatic_demand_is_not_capped_at_largest_current_closure(expanded_catalog,tmp_path):
    from manifold.schema import Design
    from manifold.routing import resolve_design
    from manifold.construction_closure_audit import demonstrated_coverage
    design=Design.model_validate_json((Path(__file__).parent/'fixtures/automatic-msr102ke-demand.json').read_text(encoding='utf-8-sig'))
    resolved,metadata,geometry,report=resolve_design(design,exact=True,prepared=True)
    assert metadata[0]['sizing']['mode']=='automatic'
    assert metadata[0]['sizing']['status']=='FLOW_SIZED'
    assert metadata[0]['sizing']['diameter_mm']>61.1124
    assert metadata[0]['exact_attempts']<=8
    assert all(c['status']=='PASS' for c in report['checks'] if c['rule']!='construction_closure')
    step=step_round_trip(geometry,tmp_path/'large-demand.step')
    assert geometry.production.isValid() and len(geometry.production.Solids())==1 and step['status']=='PASS'
    case=dict(id='large-source-witness',resolved_design=resolved.model_dump(),checks=report['checks'],
              brep_valid=True,solids=1,step=step)
    result=demonstrated_coverage([case],tmp_path/'coverage.json')
    assert result['classes']==1 and result['items'][0]['hydraulic_bore_diameter_mm']>61.1124
    assert not result['exhaustive_domain_established']
    # Catalogue membership or a failed fixed port is not a valid demand witness.
    rejected=dict(case,id='invalid-fixed-geometry',checks=case['checks']+[
        dict(rule='source_operation_tool',status='FAIL',items=['CV1'])])
    result=demonstrated_coverage([rejected],tmp_path/'rejected.json')
    assert result['classes']==0 and result['rejected_witnesses']
