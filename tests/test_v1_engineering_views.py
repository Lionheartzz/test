"""V1 exact geometry fixtures A–F, workflow parity and evidence boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient
from manifold import store
from manifold.engineering_db import get_definition,search_definitions
from manifold.schema import Design
from manifold.geometry import build_geometry, review_model, tip_depth
from manifold.validation import validate
from manifold.routing import resolve_design, authorize_generated_contacts
from manifold.server import app


def bores(cross=False, angle=118):
    return Design(name='V1 bore intersections',block=dict(length=100,width=100,height=100,material='Fixture'),
        features=[dict(id='X',kind='drilling',face='left',u=50,v=50,circuit='P',diameter=10,depth=65,
                       tip_angle=angle,plugged=True,connects_to=[] if cross else ['Y']),
                  dict(id='Y',kind='drilling',face='front',u=50,v=50,circuit='T' if cross else 'P',diameter=10,
                       depth=65,tip_angle=angle,plugged=True,connects_to=[] if cross else ['X'])])


def port():
    rows=search_definitions(kind='port_definition',unit='metric',limit=100)['items']
    definition=next(get_definition(row['id']) for row in rows if row['usable'] and len(get_definition(row['id']).cutting_primitives)>1)
    depth=(definition.zones[0].start+definition.zones[0].end)/2
    return Design(name='V1 source-backed port',block=dict(length=120,width=120,height=120,material='Fixture'),
        features=[dict(id='PORT',kind='port',face='top',u=60,v=60,circuit='P',port_definition_id=definition.id),
                  dict(id='LATERAL',kind='drilling',face='left',u=60,v=120-depth,circuit='P',diameter=6,depth=64,
                       tip_angle=180,plugged=True,connects_to=['PORT'])])


def automatic():
    d=Design.model_validate_json(Path('tests/fixtures/route-cost-vs-proxy.json').read_text(encoding='utf-8'))
    assert any(n.routing=='automatic' and not n.routing_variant for n in d.nets)
    return d


def part(model,kind):
    return next(p for p in model['parts'] if p['kind']==kind)


def test_A_same_net_is_exact_union_without_internal_overlap():
    d=bores();g=build_geometry(d);m=review_model(d,g)
    assert validate(d,g)['status']=='WARNING' # Source plug-entry machining is deliberately unresolved.
    common=g.nodes['X'].intersect(g.nodes['Y']).Volume()
    assert common>1
    net=part(m,'hydraulic-net')
    assert net['solid_count']==1 and len([p for p in m['parts'] if p['kind']=='hydraulic-net'])==1
    assert net['volume_mm3']==pytest.approx(sum(s.Volume() for s in g.nodes.values())-common)
    # The delivered triangles themselves must describe the union, not concatenated
    # bore meshes accompanied by correct-looking union metadata.
    import numpy as np
    vertices=np.array(net['vertices']).reshape(-1,3)
    triangles=np.array(net['triangles']).reshape(-1,3)
    signed=np.einsum('ij,ij->i',vertices[triangles[:,0]],np.cross(vertices[triangles[:,1]],vertices[triangles[:,2]]))
    assert abs(signed.sum()/6)==pytest.approx(net['volume_mm3'],rel=.01)
    assert part(m,'machined-void')['volume_mm3']==pytest.approx(g.block.Volume()-g.production.Volume())
    assert not m['collisions']


@pytest.mark.parametrize('angle',[118,180])
def test_B_C_drill_tip_exact_mesh_extent(angle):
    d=bores(angle=angle);g=build_geometry(d);m=review_model(d,g)
    f=d.features[0];tip=tip_depth(f)
    assert (tip>0)==(angle!=180)
    cut=next(p for p in m['parts'] if p['id']=='X:machining')
    assert max(cut['vertices'][0::3])==pytest.approx(f.depth+tip,abs=1e-5)
    assert g.cuts['X'].BoundingBox().xmax==pytest.approx(f.depth+tip)


def test_D_closure_excluded_from_flow_but_in_machining(tmp_path):
    from manifold.manufacturing import manufacturing_outputs
    d=bores();g=build_geometry(d);m=review_model(d,g)
    assert g.nodes['X'].intersect(g.plugs['X']).Volume()<1e-6
    assert g.cuts['X'].Volume()-g.nodes['X'].Volume()==pytest.approx(g.plugs['X'].Volume())
    assert part(m,'plug')['triangles']
    manufacturing_outputs(d,g,tmp_path)
    profile=json.loads((tmp_path/'manufacturing.json').read_text())['machining_profiles'][0]
    assert profile['closure']['entry_machining_status']=='unresolved'
    assert profile['tip_angle_degrees']==118


def test_E_cross_net_failure_keeps_separate_networks_and_collision():
    d=bores(cross=True);g=build_geometry(d);m=review_model(d,g);r=validate(d,g)
    assert any(c['rule']=='circuit_intersection' and c['status']=='FAIL' for c in r['checks'])
    assert {p['circuit'] for p in m['parts'] if p['kind']=='hydraulic-net'}=={'P','T'}
    assert m['collisions'][0]['nets']==['P','T'] and m['collisions'][0]['volume_mm3']>1
    assert part(m,'collision')['triangles']


def test_F_source_port_complete_profile_separate_hydraulic_window(tmp_path):
    from manifold.manufacturing import manufacturing_outputs
    d=port();g=build_geometry(d);m=review_model(d,g);r=validate(d,g)
    assert r['status']=='WARNING' # Source plug-entry machining is deliberately unresolved.
    assert g.cuts['PORT'].Volume()>g.nodes['PORT'].Volume()
    assert g.nodes['PORT'].intersect(g.nodes['LATERAL']).Volume()>1
    assert part(m,'port-machining')['volume_mm3']==pytest.approx(g.cuts['PORT'].Volume())
    assert part(m,'port')['vertices']!=part(m,'port-machining')['vertices']
    assert not any(c['rule']=='drill_reach' and 'PORT' in c['items'] for c in r['checks'])
    manufacturing_outputs(d,g,tmp_path)
    data=json.loads((tmp_path/'manufacturing.json').read_text())
    rows=[r for r in data['drill_chart'] if r['feature']=='PORT']
    definition=get_definition(d.features[0].port_definition_id)
    assert len(rows)==len(definition.cutting_primitives or definition.stages)>1
    assert max(r['diameter'] for r in rows)>min(r['diameter'] for r in rows)
    assert data['machining_profiles'][0]['definition']==definition.id
    assert data['machining_profiles'][0]['hydraulic_interfaces']


def test_automatic_transient_preview_freeze_refine_does_not_write(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    def forbidden(*args,**kwargs):raise AssertionError('Transient operation wrote evidence')
    monkeypatch.setattr(store,'atomic_json',forbidden)
    client=TestClient(app);headers={'X-PMC-Request':'local-console'};d=automatic()
    for _ in range(2):
        for endpoint in ['preview','preview-solid']:
            result=client.post('/api/'+endpoint,json=d.model_dump(),headers=headers)
            assert result.status_code==200,result.text[:500]
    frozen=client.post('/api/freeze-net',json=dict(design=d.model_dump(),net='P'),headers=headers)
    assert frozen.status_code==200,frozen.text[:500]
    feature=next(f for f in frozen.json()['features'] if f.get('frozen_net'))
    result=client.post('/api/refine-route',json=dict(design=frozen.json(),feature_id=feature['id'],u=feature['u'],v=feature['v']),headers=headers)
    assert result.status_code==200,result.text[:500]
    # Transient diagnostics may persist, but never engineering/route evidence.
    files=[p for p in tmp_path.rglob('*') if p.is_file()]
    assert files and all(p.parent.name=='cad-diagnostics' and p.suffix=='.json' for p in files)


def test_explicit_optimization_budget_is_total_exact_evaluations(tmp_path,monkeypatch):
    from manifold import optimization
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output');monkeypatch.setattr(store,'PROJECT',tmp_path/'project.json')
    d=automatic();store.atomic_json(store.PROJECT,d.model_dump());calls=[]
    monkeypatch.setattr(store,'read_design',lambda: d.model_copy(deep=True))
    real=optimization.validate
    def counted(*args,**kwargs):calls.append(1);return real(*args,**kwargs)
    monkeypatch.setattr(optimization,'validate',counted)
    # A nested resolver would call validation.validate outside the budget owner.
    import manifold.validation as validation
    monkeypatch.setattr(validation,'validate',lambda *a,**k:pytest.fail('Nested exact search'))
    result=optimization.optimize_routes(d,store.revision(d),max_attempts=3)
    assert len(calls)==len(result['attempts'])==3
    assert not (store.OUTPUT/'route-selections').exists()
    assert all(n['routing_variant'] for n in result['design']['nets'] if n['routing']=='automatic')


def test_cli_file_validation_resolves_same_geometry(tmp_path):
    d=automatic();path=tmp_path/'automatic.json';path.write_text(d.model_dump_json(),encoding='utf-8')
    resolved,_=resolve_design(d);g=build_geometry(resolved);authorize_generated_contacts(resolved,g)
    expected=validate(resolved,g)
    run=subprocess.run([sys.executable,'-m','manifold','validate','--project',str(path)],capture_output=True,text=True,encoding='utf-8')
    assert run.returncode==(1 if expected['status']=='FAIL' else 0),run.stderr
    actual=json.loads(run.stdout)
    assert actual['graph']==expected['graph'] and actual['counts']==expected['counts']
    assert not list(tmp_path.glob('*.step'))


def test_frozen_owner_cannot_silently_change():
    d=bores().model_dump();d['features'][0]['frozen_net']='P';d['features'][0]['circuit']='T'
    with pytest.raises(ValueError,match='single owner'):Design.model_validate(d)


def test_engine_identity_does_not_relabel_loaded_code(tmp_path,monkeypatch):
    from manifold import engine
    for path in engine.ROOT.glob('*.py'):(tmp_path/path.name).write_bytes(path.read_bytes())
    monkeypatch.setattr(engine,'ROOT',tmp_path)
    revision=engine.engine_revision();assert engine.engine_current()
    assert engine.engine_evidence()['dependencies']['cadquery-ocp']!='unavailable'
    (tmp_path/'geometry.py').write_text('# changed after import',encoding='utf-8')
    assert not engine.engine_current() and engine.engine_revision()==revision
    with pytest.raises(RuntimeError,match='Restart'):engine.assert_engine_current()
    with pytest.raises(RuntimeError,match='Restart'):store.build_outputs(bores(),tmp_path/'forbidden-build')
    assert not (tmp_path/'forbidden-build').exists()


def test_source_port_ranking_uses_machining_profile_not_summary():
    from manifold.routing import proximity_risk
    from manifold.schema import Feature,HydraulicNet
    d=port();d.features=d.features[:1]
    bore=Feature(id='PROBE',kind='drilling',face='left',u=73,v=119,circuit='T',diameter=2,depth=65,tip_angle=180)
    net=HydraulicNet(id='T',members=[],routing='manual')
    source_risk=proximity_risk(d,net,[bore])
    # Changing the derived summary must not change the machining obstacle ranking.
    d.features[0].diameter=1;d.features[0].depth=1
    assert proximity_risk(d,net,[bore])==source_risk>0


def test_exact_preview_never_searches_candidates_and_reports_resolution_reason(monkeypatch):
    import manifold.validation as validation
    from manifold.cad_worker import dispatch
    monkeypatch.setattr(validation,'validate',lambda *a,**k:pytest.fail('Preview performed exact route selection'))
    # Instrument the worker entrypoint itself, not an unused parent-process import.
    assert dispatch('preview-solid',automatic().model_dump())['route_selection']=='CURRENT_PROPOSAL_NOT_OPTIMIZED'
    client=TestClient(app);headers={'X-PMC-Request':'local-console'}
    result=client.post('/api/preview-solid',json=automatic().model_dump(),headers=headers)
    assert result.status_code==200,result.text[:500]
    assert result.json()['route_selection']=='CURRENT_PROPOSAL_NOT_OPTIMIZED'
    assert any(p['kind']=='hydraulic-net' for p in result.json()['model']['parts'])
    # This flow/velocity requires a diameter beyond the sourced drill catalog.
    # Route depth is checked separately against actual candidate drillings.
    invalid=automatic();invalid.nets[0].flow_lpm=10000;invalid.nets[0].velocity_limit=.5;invalid.nets[0].diameter_mode='automatic'
    for endpoint in ('preview','preview-solid'):
        result=client.post('/api/'+endpoint,json=invalid.model_dump(),headers=headers)
        assert result.status_code==422 and 'hydraulic sizing unresolved' in result.json()['detail'] and 'no source-backed drill' in result.json()['detail']
