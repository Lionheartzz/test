"""Production single-work control, measured isolation and real CAD witnesses."""
import json
from pathlib import Path
import pytest

from manifold.schema import Design,CavityDefinition
from manifold.ai_design.single_design import WorkDesign
from manifold.ai_design.design_space import LayoutDomain
from manifold.engineering_db import tool_definitions
from manifold.ai_design.joint_layout import exact_candidate
from test_engineering_layout_planner import shared_sources
from test_corridor_planner import crossing
from test_ai_design import client,HEADERS


def work(d,defs,**locks):
    return WorkDesign(d,defs,LayoutDomain.new_generation(d,{f.id for f in d.features if f.kind in ('cavity','port')},**locks),
        {},{},tool_definitions('drill'))


def forbid_search(monkeypatch):
    from manifold.ai_design import initialization,design_space,joint_layout,layout_search
    from manifold.ai_design.route_catalog import Session,Catalog
    from manifold import drilling_planner
    def forbidden(*a,**k):raise AssertionError('Expensive/general layout or route search entered')
    for obj,name in [(initialization,'initial_candidates'),(design_space,'pack_topology'),
        (joint_layout,'optimize_legacy_layout_portfolio'),(layout_search,'screen'),
        (Session,'prepare'),(Catalog,'step'),(drilling_planner,'plan_net')]:monkeypatch.setattr(obj,name,forbidden)


def test_normal_chain_is_one_work_design_and_real_exact(monkeypatch,tmp_path):
    from manifold.ai_design.layout_search import plan_new
    forbid_search(monkeypatch);d=crossing();before=d.model_dump_json()
    r=plan_new(d,{},movable_features={f.id for f in d.features},layout_limit=48,exact_limit=1,evidence_dir=tmp_path)
    assert r['status']=='EXACT_FEASIBLE',r['engineering_planner']
    assert r['evaluated_layouts']==1 and r['deferred_layouts']==0
    assert r['counters']['catalog_searches']==r['counters']['deep_labels']==0
    assert r['attempts'][0]['topology']==dict(valid=True,solids=1)
    assert r['attempts'][0]['step']['status']=='PASS'
    assert r['engineering_planner']['global_layout_queue']==0
    assert d.model_dump_json()==before


def test_rejected_plan_stops_before_expensive_router_and_keeps_source_draft(monkeypatch,tmp_path):
    from manifold.ai_design.layout_search import plan_new
    # Valid fixed source layout, individually manufacturable direct holes,
    # but two different-Net full cuts intersect. No permitted source movement.
    d=crossing();d.constraints.required_feature_faces={f.id:f.face for f in d.features}
    forbid_search(monkeypatch)
    r=plan_new(d,{},movable_features={f.id for f in d.features},growth_axes=(),
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features},exact_limit=1,evidence_dir=tmp_path)
    assert r['status']=='SOURCE_LAYOUT_READY_ROUTING_PENDING',r
    assert r['engineering_planner']['source_layout_ready']
    assert any(f[0]=='cross_net_wall' for rows in r['engineering_planner']['failures'].values() for f in rows)
    assert not r['attempts'] and not r['validation'] and not r['manufacturing_ready']
    assert Design.model_validate(r['proposals'][0]['design']).features==d.features
    assert r['engineering_planner']['catalog_searches']==r['engineering_planner']['deep_labels']==0


def test_rigid_three_net_calculation_and_bounded_exact_classification(monkeypatch,tmp_path):
    d,defs=shared_sources();before=d.model_dump_json();w=work(d,defs)
    assert w.initialize();w.materialize();assert w.precheck(),w.failures
    table=w.table
    assert table['groups']==[['S0','S1']] or table['groups']==[['S1','S0']]
    spacing=table['spacing'][0]
    assert spacing['required']==sum(spacing['radii'])+spacing['gap']
    target=w.design.model_copy(deep=True);target.features.extend(f for fs in w.routes.values() for f in fs)
    for n in target.nets:n.route_state='proposal'
    from manifold import store
    from manifold.ai_design.execution import supervise
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    out=supervise(dict(operation='exact-snapshot',design=target.model_dump(),definitions={k:v.model_dump() for k,v in defs.items()}),
        limits=dict(total=30,layout=25,deep=2))
    (tmp_path/'bounded-exact.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    if out['execution']['reason']=='COMPLETED':
        r=out['result']
        assert r['status']=='EXACT_FEASIBLE',r['failures']
        assert r['topology']==dict(valid=True,solids=1) and r['step']['status']=='PASS'
    else:
        # This asserts safe UNKNOWN classification, NOT CAD acceptance. The
        # release evidence records this witness as unaccepted, not a PASS.
        assert out['execution']['reason'] in ('LAYOUT_TIME_LIMIT','TOTAL_TIME_LIMIT')
        assert out['result'] is None and out['checkpoint']['manufacturing_ready'] is False
        assert out['execution']['exit_code'] is not None
    assert len(w.routes)==3 and all(len(f['windows'])==3 for f in table['features'])
    assert d.model_dump_json()==before
    (tmp_path/'engineering-calculations.json').write_text(json.dumps(w.diagnostics(),indent=2),encoding='utf-8')


def test_three_net_fixed_source_definitions_one_work_real_exact(monkeypatch,tmp_path):
    from manifold.ai_design.layout_search import plan_new
    d=Design(name='Three perpendicular Net process constraints',block=dict(length=120,width=120,height=120,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id=f'E{i}',kind='port',face=face,u=60,v=60,
            diameter=12,depth=16,tip_angle=180,circuit=f'N{i//2}',clearance_diameter=14,clearance_height=1)
            for i,face in enumerate(('left','right','front','back','bottom','top'))],
        nets=[dict(id=f'N{i}',diameter=8,routing='automatic') for i in range(3)])
    forbid_search(monkeypatch)
    r=plan_new(d,{},movable_features={f.id for f in d.features},exact_limit=1,evidence_dir=tmp_path)
    assert r['status']=='EXACT_FEASIBLE',r['engineering_planner']
    assert r['attempts'][0]['topology']==dict(valid=True,solids=1) and r['attempts'][0]['step']['status']=='PASS'
    assert len(r['proposals'][0]['assessment']['partial_routing']['nets'])==3


def test_same_geometry_rename_order_and_dependency_changes_are_deterministic():
    d,defs=shared_sources();raw=d.model_dump();fm={'S0':'Z','S1':'A'};nm={'N0':'Y','N1':'X','N2':'W'}
    for f in raw['features']:
        f['id']=fm[f['id']];f['interface_nets']={k:nm[v] for k,v in f['interface_nets'].items()}
    for n in raw['nets']:n['id']=nm[n['id']];n['members']=[]
    raw['features'].reverse();raw['nets'].reverse()
    a,b=work(d,defs),work(Design.model_validate(raw),defs)
    assert a.initialize() and b.initialize()
    a.materialize();b.materialize()
    geometry=lambda w:sorted((f.face,f.u,f.v,f.depth,f.diameter) for fs in w.routes.values() for f in fs)
    assert geometry(a)==geometry(b) and a.design.block==b.design.block
    changed=d.model_copy(deep=True);changed.features[0].u+=.25
    assert work(changed,defs).e.dependency!=a.e.dependency


def test_disjoint_opposite_projections_do_not_sum_depths():
    definition=CavityDefinition(id='QA_DEPTH',label='QA explicit depth',stages=[dict(start=0,end=40,diameter=16)],
        zones=[dict(id='w',start=20,end=30,diameter=16)],clearance_diameter=20,clearance_height=1)
    d=Design(name='Disjoint opposite columns',block=dict(length=120,width=120,height=120,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id='U',kind='cavity',face='top',u=25,v=25,cavity_id=definition.id,interface_nets={'w':'U'}),
            dict(id='D',kind='cavity',face='bottom',u=90,v=90,cavity_id=definition.id,interface_nets={'w':'D'})],
        nets=[dict(id=n,routing='automatic') for n in ('U','D')])
    w=work(d,{definition.id:definition},fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features})
    assert w.initialize();assert w.design.block.height==42
    d.features[1].u=25;d.features[1].v=25
    w=work(d,{definition.id:definition},fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features})
    assert w.initialize();assert w.design.block.height==82


def test_rectangular_installation_uses_actual_rotated_projection_not_circle():
    definition=CavityDefinition(id='QA_RECT',label='QA rectangular installed footprint',
        stages=[dict(start=0,end=20,diameter=4)],zones=[dict(id='w',start=10,end=16,diameter=4)],
        clearance_diameter=4,clearance_height=1,
        boundaries=[dict(points=[(-20,-4),(20,-4),(20,4),(-20,4)],height=2)])
    d=Design(name='Rectangular supports',block=dict(length=160,width=160,height=80,material='QA'),
        rules=dict(minimum_wall=2,minimum_access_gap=2),features=[dict(id=f'F{i}',kind='cavity',face='top',u=50+i*50,v=50,
            rotation=90,cavity_id=definition.id,interface_nets={'w':'N'}) for i in range(2)],
        nets=[dict(id='N',routing='automatic',diameter=2)])
    w=work(d,{definition.id:definition});spacing=w.spacing()[0]
    assert spacing.reason['formula'].startswith('projected')
    assert spacing.distance==pytest.approx(4+4+2)
    # Actual production boundary solids have a valid gap at this distance,
    # even though their enclosing circles overlap.
    d.features[0].u=30;d.features[1].u=40
    assert not w.source_conflicts(d)
    d.features[1].u=37
    assert w.source_conflicts(d)  # real access violation is still rejected


def test_plug_repair_uses_occupied_plug_against_full_other_cut():
    from manifold.schema import Feature
    from manifold.closure_runtime import bind_route
    d=crossing();w=work(d,{})
    cuts=bind_route(d,[Feature(id='A',kind='drilling',face='left',u=50,v=50,diameter=8,depth=50,plugged=True,circuit='P',route_net='P'),
        Feature(id='B',kind='drilling',face='front',u=5,v=50,diameter=8,depth=60,plugged=True,circuit='P',route_net='P')])
    w.junctions={'P':(30,50,50),'T':(50,30,50)}
    actions=list(w.separation_actions([dict(nets=['P'],features=[f.model_dump() for f in cuts],failures=[['plug_cut','A','B']])]))
    assert actions and all(cause['measured_envelopes']=={'A':'plug'} for _,cause in actions)


def test_axial_stock_bound_uses_real_engagement_and_source_safe_stop():
    definition=CavityDefinition(id='QA_STOCK',label='QA source stop',stages=[dict(start=0,end=40,diameter=16)],
        zones=[dict(id='deep',start=30,end=40,diameter=16)],clearance_diameter=20,clearance_height=1)
    d=Design(name='Necessary closure space',block=dict(length=140,width=140,height=120,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id='C',kind='cavity',face='top',u=50,v=50,cavity_id=definition.id,interface_nets={'deep':'N'}),
            dict(id='E',kind='port',face='front',u=80,v=50,diameter=12,depth=16,tip_angle=180,circuit='N')],
        nets=[dict(id='N',routing='automatic',diameter=8)])
    w=work(d,{definition.id:definition});floor,facts=w.necessary_stock()
    assert facts and facts[0]['member']=='C:deep'
    f=facts[0];assert floor[2]==pytest.approx(f['occupied_depth']-f['source_stop_offset']+2*(f['bore_radius']+f['wall']))
    assert floor[2]>40+2  # source depth alone cannot accommodate this closure/junction


def test_partial_coordinate_lock_keeps_other_coordinate_available_for_repair():
    d=crossing()
    for f in d.features:f.u=f.v=9
    w=work(d,{},fixed_positions={'P1':dict(u=9)})
    assert w.initialize(),w.diagnostics()
    p=next(f for f in w.design.features if f.id=='P1')
    assert p.u==9
    assert not w.source_conflicts(w.design)


def test_directional_entry_repair_preserves_sources_and_unrelated_net(tmp_path):
    definition=CavityDefinition(id='QA_ENTRY',label='QA side window',stages=[dict(start=0,end=40,diameter=16)],
        zones=[dict(id='w',start=15,end=25,diameter=16)],clearance_diameter=20,clearance_height=1)
    d=Design(name='Entry repair',block=dict(length=140,width=100,height=80,material='QA'),rules=dict(minimum_wall=2),features=[
        *[dict(id=f'C{i}',kind='cavity',face='top',u=x,v=60,cavity_id=definition.id,interface_nets={'w':'N'}) for i,x in enumerate((32,56))],
        dict(id='FIXED',kind='mounting',face='left',u=60,v=60,diameter=12,depth=18,tip_angle=180),
        dict(id='E0',kind='port',face='left',u=20,v=20,diameter=12,depth=16,circuit='OTHER',tip_angle=180),
        dict(id='E1',kind='port',face='right',u=20,v=20,diameter=12,depth=16,circuit='OTHER',tip_angle=180)],
        nets=[dict(id=n,diameter=8,routing='automatic') for n in ('N','OTHER')])
    w=work(d,{definition.id:definition},dimension_axes=(),fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features})
    assert w.initialize();w.materialize();assert not w.precheck()
    other=[f.model_dump() for f in w.routes['OTHER']];before=w.design.model_dump()
    assert w.repair(),w.diagnostics()
    assert w.precheck(),w.failures
    assert w.design.model_dump()==before
    assert [f.model_dump() for f in w.routes['OTHER']]==other
    assert w.materialized_nets[-1]==['N']
    target=w.design.model_copy(deep=True);target.features.extend(f for fs in w.routes.values() for f in fs)
    for n in target.nets:n.route_state='proposal'
    r=exact_candidate(target,{definition.id:definition},{},{},folder=tmp_path/'production')
    assert r['status']=='EXACT_FEASIBLE',r['failures']
    (tmp_path/'entry-repair.json').write_text(json.dumps(w.diagnostics(),indent=2),encoding='utf-8')


def test_partial_draft_save_reload_validate_build_preserves_authored_geometry(client,tmp_path):
    from manifold.ai_design.layout_search import plan_new
    import subprocess,sys
    d=crossing();raw=d.model_dump()
    raw['features']+= [dict(id=f'K{i}',kind='port',face=face,u=20,v=90,diameter=12,depth=16,
        tip_angle=180,circuit='K',clearance_diameter=14,clearance_height=1) for i,face in enumerate(('left','right'))]
    raw['nets'].append(dict(id='K',diameter=8,routing='automatic'));d=Design.model_validate(raw)
    r=plan_new(d,{},movable_features={f.id for f in d.features},growth_axes=(),
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features},exact_limit=0)
    assert r['proposals'][0]['assessment']['partial_routing']['nets']==['K']
    assert not r['manufacturing_ready']
    current=Design.model_validate(r['proposals'][0]['design']);response=client.post('/api/projects',json=dict(design=current.model_dump(),draft_only=True),headers=HEADERS)
    assert response.status_code==200,response.text
    loaded=client.get('/api/projects/'+response.json()['project_id']).json()['design'];current=Design.model_validate(loaded)
    assert current.block==d.block and [f for f in current.features if not f.route_net]==d.features
    path=tmp_path/'partial-project.json';path.write_text(json.dumps(loaded),encoding='utf-8')
    code='''
import sys,json
from pathlib import Path
from manifold.schema import Design
from manifold import routing,drilling_planner,store
from manifold.cad_worker import dispatch
from manifold.ai_design import joint_layout,generation
def forbidden(*a,**k):raise AssertionError('Implicit search or source movement')
routing.resolve_design=forbidden;drilling_planner.plan_net=forbidden
joint_layout.optimize=forbidden;generation.candidate=forbidden
d=Design.model_validate_json(Path(sys.argv[1]).read_text());before=d.model_dump_json()
rejected=[]
for name,operation in [('Validate',lambda:dispatch('validate',d.model_dump())),('Build',lambda:store.build_outputs(d,Path(sys.argv[2])))]:
    try:operation()
    except ValueError as exc:
        assert 'Routing must finish' in str(exc);rejected.append(name)
    else:raise AssertionError('Incomplete routes were accepted')
assert d.model_dump_json()==before
print(json.dumps(dict(rejected=rejected,source_unchanged=True,search_called=False,manufacturing_accepted=False)))
'''
    p=subprocess.run([sys.executable,'-B','-c',code,str(path),str(tmp_path/'build')],capture_output=True,text=True,timeout=25)
    assert p.returncode==0,p.stdout+p.stderr
    (tmp_path/'fresh-partial-worker.json').write_text(p.stdout,encoding='utf-8')
