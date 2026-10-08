"""Focused release checks against the configured real v8 engineering database."""
import json
from contextlib import closing

import pytest

from manifold import engineering_db,closure_runtime,store,projects
from manifold.schema import Design
from manifold.routing import resolve_design
from manifold.route_state import validate_current_design
from manifold.manufacturing import manufacturing_outputs


@pytest.fixture
def v8():
    if engineering_db.validate_database()['schema_version']!=8:
        pytest.skip('Explicit v8 deployment required')
    return closure_runtime.catalog()


def normal_design():
    with closing(engineering_db._connect()) as db:
        port=db.execute("SELECT id FROM external_port_definitions WHERE name='G 1/2' AND unit_system='metric' AND usable=1 AND active=1").fetchone()[0]
    definition=engineering_db.get_definition(port)
    design=Design.model_validate(dict(schema_version=4,name='v8 closure acceptance',project_context='metric',
        block=dict(length=168,width=168,height=168,material='Engineer stress override'),
        rules=dict(minimum_wall=7,allowable_stress_mpa=150),
        features=[dict(id=i,kind='port',face='top',u=u,v=84,circuit='P',port_definition_id=port,
            diameter=definition.zones[0].diameter,depth=definition.zones[0].end,
            clearance_diameter=definition.clearance_diameter,clearance_height=definition.clearance_height)
            for i,u in [('P1',56),('P2',112)]],
        nets=[dict(id='P',members=['P1','P2'],routing='automatic',diameter_mode='manual',diameter=12)]))
    result,_,_,report=resolve_design(design,exact=True,prepared=True)
    assert report['counts']['FAIL']==report['counts']['WARNING']==0
    return result


def test_v8_aliases_and_other_domains_use_one_runtime_database(v8):
    from fastapi.testclient import TestClient
    from manifold.server import app
    aliases=closure_runtime.aliases();assert len(aliases)==24
    assert len([r for r in v8 if r['usable'] and r['active']])==103
    for old,new in aliases.items():
        design=Design.model_validate(dict(name='Legacy closure reference',block=dict(length=120,width=120,height=120,material='Aluminum'),
            features=[dict(id='D',kind='drilling',face='top',u=60,v=60,circuit='P',diameter=1,depth=60,plugged=True,closure_definition_id=old)]))
        assert engineering_db.closure_definitions_for_design(design)[old]['id']==new
    with TestClient(app) as client:
        assert client.get('/api/health').status_code==200
        categories=client.get('/api/engineering-library/categories').json()['items']
        closure=next(c for c in categories if c['key']=='closures')
        assert closure['definition_count']==103 and closure['knowledge_count']==443
        for path in ('/api/threads','/api/materials','/api/tools','/api/machining-modifiers','/api/closures'):
            response=client.get(path);assert response.status_code==200 and response.json()
        for kind in ('drill','flat-bottom-drill','spotface','form-port','tap'):
            response=client.get('/api/tools',params={'type':kind})
            assert response.status_code==200 and response.json()


def test_new_family_does_not_displace_established_automatic_technology(v8):
    from manifold.schema import Feature
    feature=Feature(id='R',kind='drilling',face='top',u=100,v=100,circuit='P',diameter=40,depth=300,plugged=True)
    choices=closure_runtime.choices(feature,'metric')
    assert any(closure_runtime.profile(r)['closure_type']=='metric-iso6149' for r in choices)
    assert closure_runtime.profile(choices[0])['closure_type']=='sae-standard-port'


def test_manual_closure_save_reload_validate_duplicate_and_pinned_drawing(v8,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from manifold.server import app
    from manifold.drawing.generate import anchors
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects/demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    design=normal_design();feature=next(f for f in design.features if f.plugged)
    expander=closure_runtime.bound(feature)
    sae=next(r for r in closure_runtime.choices(feature,'metric') if r['unit_system']=='metric' and
             closure_runtime.profile(r).get('source_profile_row',{}).get('CavityName')=='#8 SAE')
    results=[]
    with TestClient(app) as client:
        key=None;revision=None
        for closure in (expander,sae):
            feature.closure_definition_id=closure['id'];feature.closure_selection_mode='manual'
            design=closure_runtime.normalize_design(design);feature=next(f for f in design.features if f.plugged)
            saved=client.post('/api/projects',json=dict(design=design.model_dump(),project_id=key,expected_revision=revision),headers={'X-PMC-Request':'local-console'})
            assert saved.status_code==200,saved.text
            record=saved.json();key=record['project_id'];revision=record['revision']
            reloaded=client.get('/api/projects/'+key).json();design=Design.model_validate(reloaded['design'])
            feature=next(f for f in design.features if f.plugged)
            assert feature.closure_definition_id==closure['id'] and feature.closure_selection_mode=='manual'
            checked,_,geometry,report=validate_current_design(design,step_path=tmp_path/(closure['id']+'.step'))
            assert report['counts']['FAIL']==report['counts']['WARNING']==0 and report['manufacturing_ready']
            assert next(f for f in checked.features if f.plugged).closure_definition_id==closure['id']
            folder=tmp_path/closure['id'];folder.mkdir();manufacturing_outputs(checked,geometry,folder)
            output=json.loads((folder/'manufacturing.json').read_text())
            profile=next(p for p in output['machining_profiles'] if p['feature']==feature.id)
            assert profile['cutting_steps']==closure_runtime.cutting_primitives(feature,closure)
            assert profile['closure']['model']=='' and profile['closure']['id']==closure['id']
            data,rows,operations=anchors(dict(resolved=checked.model_dump(),manufacturing=output))
            row=next(r for r in rows if r['id']==feature.id)
            assert row['model']=='' and 'ENTRY Ø' in row['specification']
            assert data['F:'+feature.id]['diameter']==max(p['diameter'] for p in profile['cutting_steps'])>feature.diameter
            assert next(o for o in operations if o['feature']==feature.id)['closure']['id']==closure['id']
            if closure_runtime.profile(closure)['operation']=='SOURCE_FORM_PORT_ENTRY':
                assert {'FORM PORT','TAP'}<={o['operation'] for o in profile['closure']['machining']}
                assert profile['closure']['thread_facts']['tap_diameter_mm']>0
                assert all(o['status']=='RESOLVED' for o in profile['operation_tools'])
            results.append((feature.plug_length,geometry.cuts[feature.id].Volume(),geometry.production.Volume()))
            assert feature.diameter==12
        assert all(a!=b for a,b in zip(*results))
        copied=client.post('/api/projects/'+key+'/manage',json=dict(action='duplicate',expected_revision=revision),headers={'X-PMC-Request':'local-console'})
        assert copied.status_code==200
        assert next(f for f in copied.json()['design']['features'] if f['plugged'])['closure_definition_id']==sae['id']


def test_incompatible_selected_closure_is_not_exported_as_resolved(v8,tmp_path):
    row=min(v8,key=lambda r:closure_runtime.profile(r)['hydraulic_diameter_max_mm'])
    design=Design.model_validate(dict(name='Unsupported selected closure',block=dict(length=200,width=200,height=200,material='Aluminum'),
        features=[dict(id='D',kind='drilling',face='top',u=100,v=100,circuit='P',diameter=76,depth=100,plugged=True,closure_definition_id=row['id'])]))
    from manifold.geometry import build_geometry
    from manifold.validation import validate
    geometry=build_geometry(design);report=validate(design,geometry)
    assert any(c['rule']=='construction_closure' and c['status']=='FAIL' for c in report['checks'])
    manufacturing_outputs(design,geometry,tmp_path)
    profile=json.loads((tmp_path/'manufacturing.json').read_text())['machining_profiles'][0]
    assert profile['closure']['entry_machining_status']=='unresolved'
    assert not report['manufacturing_ready']
