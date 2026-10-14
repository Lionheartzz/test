"""Engineering-first planning through production Router and real CAD gates."""
import json
from pathlib import Path
import pytest

from manifold.schema import Design, CavityDefinition
from manifold.ai_design.design_space import LayoutDomain
from manifold.ai_design.engineering_decisions import EngineeringDecisionController
from manifold.ai_design.placement_solver import DifferenceSystem
from manifold.ai_design.layout_search import screen
from manifold.ai_design.route_catalog import Session
from manifold.ai_design.joint_layout import exact_candidate
from manifold.engineering_db import tool_definitions
from test_ai_design import client, HEADERS


def shared_sources():
    definition=CavityDefinition(id='QA_RIGID',label='Explicit engineering witness, not vendor geometry',
        stages=[dict(start=0,end=65,diameter=16)],
        zones=[dict(id=f'w{i}',start=10+20*i,end=20+20*i,diameter=16) for i in range(3)],
        clearance_diameter=20,clearance_height=1)
    d=Design(name='Engineering-first shared rigid windows',
        block=dict(length=120,width=120,height=100,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id=f'S{i}',kind='cavity',face='top',u=50+i,v=50,cavity_id=definition.id,
            interface_nets={f'w{j}':f'N{j}' for j in range(3)}) for i in range(2)],
        nets=[dict(id=f'N{i}',diameter=6,routing='automatic') for i in range(3)])
    return d,{definition.id:definition}


def controller(d,defs,**locks):
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features},**locks)
    return EngineeringDecisionController(d,defs,domain,{},{},tool_definitions('drill'),limit=512)


def evaluate(c,limit=16):
    e=c.plan;s=Session();s.local_allocation=0;rows=[]
    for _ in range(limit):
        next_=c.next_candidate()
        if next_ is None:break
        d,reason,cuts=next_
        a=screen(d,e.definitions,e.threads,e.modifiers,e.tools,{}, {},include_routes=True,
            corridor_labels=0,general_families=True,route_session=s,planned_routes=cuts)
        c.observe(d,a,reason['engineering_decision']);rows.append((d,a,reason))
        if a['compatible']:return rows
    return rows


def test_difference_graph_propagates_shared_coordinates_and_proves_only_selected_domain():
    s=DifferenceSystem();s.bounds('D',1,100,dict(rule='dimension'))
    s.lower('B','A',22,dict(rule='source-spacing'));s.lower('D','B',10,dict(rule='edge'))
    s.bounds('A',10,100,dict(rule='source-edge'))
    v,cycle=s.solve();assert not cycle and v['D']==42 and v['B']==32
    s.bounds('D',1,30,dict(rule='hard-max'))
    v,cycle=s.solve();assert v is None and cycle


@pytest.mark.parametrize('dependency',('separation','stock_floor','release','released_axes'))
def test_alternative_frontier_includes_complete_constraint_dependencies(dependency,tmp_path):
    from dataclasses import replace
    from manifold.ai_design.engineering_decisions import DecisionState
    from manifold.ai_design.placement_solver import Separation
    d,defs=shared_sources();before=d.model_dump_json();c=controller(d,defs)
    state=DecisionState(c.corridors.initial(),preserve=False);name=c.corridors.order[0]
    c.queue.clear();c.alternatives(state,[name]);initial=len(c.queue)
    c.queue.clear()  # already explored this old domain; preserve its cache
    changes=dict(
        separation=dict(separations=(Separation(c.placement.origin('S0',0),'ZERO',44,
            dict(rule='MEASURED_SOURCE_CLEARANCE')),)),
        stock_floor=dict(dimension_floor=(140,120,100)),
        release=dict(release=('S0',)),released_axes=dict(release_axes={'S0':(0,)}))
    changed=replace(state,**changes[dependency]);assert c.token(changed)!=c.token(state)
    c.alternatives(changed,[name]);new=len(c.queue)
    assert initial and new
    assert all(s.separations==changed.separations and s.dimension_floor==changed.dimension_floor and
        s.release==changed.release and s.release_axes==changed.release_axes for _,s in c.queue)
    assert d.model_dump_json()==before
    (tmp_path/'alternative-dependency.json').write_text(json.dumps(dict(dependency=dependency,
        original_domains=initial,changed_domains=new,production_controller=True)),encoding='utf-8')


def test_corridor_constraints_precede_joint_placement_and_three_net_exact(tmp_path):
    d,defs=shared_sources();before=d.model_dump_json();c=controller(d,defs)
    rows=evaluate(c)
    assert rows and rows[-1][1]['compatible'],c.diagnostics()
    target,a,reason=rows[-1]
    assert len(a['partial_routing']['nets'])==3
    from manifold.ai_design.route_catalog import geometry_key
    planned=c.by_decision[reason['engineering_decision']]['routes']
    assert geometry_key([f for fs in planned.values() for f in fs])==geometry_key(
        [__import__('manifold.schema',fromlist=['Feature']).Feature.model_validate(f) for f in a['route_features']])
    assert all((f.u,f.v)!=(g.u,g.v) for f,g in zip(d.features,target.features))
    assert (target.block.length,target.block.width,target.block.height)!=(120,120,100)
    decision=c.by_decision[reason['engineering_decision']]['record']
    assert decision['decision_order'].startswith('MACHINING_PLAN')
    assert any(v['cause']['rule'] in ('RADIAL_BRANCH_SOURCE_COLUMNS','COAXIAL_WINDOW_ALIGNMENT') for v in decision['responsible_constraints']['constraints'])
    assert any(v['cause']['rule'] in ('WINDOW_LAYER','COAXIAL_WINDOW_ALIGNMENT') for v in decision['responsible_constraints']['constraints'])
    from manifold.schema import Feature
    target.features.extend(Feature.model_validate(f) for f in a['route_features'])
    for n in target.nets:n.route_state='proposal'
    folder=tmp_path/'production';folder.mkdir()
    exact=exact_candidate(target,defs,{},{},folder=folder)
    assert exact['status']=='EXACT_FEASIBLE',exact.get('failures')
    assert exact['topology']==dict(valid=True,solids=1) and exact['step']['status']=='PASS'
    assert d.model_dump_json()==before
    (tmp_path/'engineering-decisions.json').write_text(json.dumps(c.diagnostics(),indent=2),encoding='utf-8')


def test_rename_and_order_do_not_change_solved_process_geometry():
    d,defs=shared_sources();raw=d.model_dump()
    mapping={'S0':'Zebra','S1':'Alpha'};netmap={'N0':'Last','N1':'First','N2':'Middle'}
    for f in raw['features']:
        f['id']=mapping[f['id']]
        key='interface_nets' if 'interface_nets' in f else 'circuits'
        f[key]={k:netmap[v] for k,v in f[key].items()}
    for n in raw['nets']:
        n['id']=netmap[n['id']];n['members']=[]
    raw['features'].reverse();raw['nets'].reverse();other=Design.model_validate(raw)
    a=controller(d,defs).next_candidate();b=controller(other,defs).next_candidate()
    geometry=lambda row:sorted((f.face,f.u,f.v,f.rotation) for f in row[0].features)
    assert a and b and geometry(a)==geometry(b)
    assert a[0].block==b[0].block
    cuts=lambda row:sorted((f.face,f.u,f.v,f.depth,f.diameter) for fs in row[2].values() for f in fs)
    assert cuts(a)==cuts(b)


def test_explicit_locks_are_never_released_by_constraint_solver():
    d,defs=shared_sources();c=controller(d,defs,dimension_axes=(),
        fixed_faces={f.id:f.face for f in d.features},fixed_rotations={f.id:f.rotation for f in d.features},
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features})
    assert c.next_candidate() is None
    assert c.plan.source.model_dump_json()==d.model_dump_json()
    assert all(r['outcome'].startswith('ROLLBACK') for r in c.records)


def test_rigid_window_cycle_changes_process_constraints_before_trying_entries():
    d,defs=shared_sources();d.features[1].u=90
    d.features[1].circuits={'w0':'N1','w1':'N0','w2':'N2'}
    d=Design.model_validate(d.model_dump());before=d.model_dump_json();c=controller(d,defs)
    c.limit=96;c.next_candidate()
    assert c.records[0]['responsible_constraints']['status']=='SELECTED_DOMAIN_CONTRADICTION'
    assert c.records[1]['cause']['rule'] in ('PROPAGATE_RIGID_WINDOW_CYCLE','PROPAGATE_SHARED_WINDOW_ORDER','PROPAGATE_PROCESS_CORRIDOR_CYCLE','PROPAGATE_ALIGNED_WINDOW_CYCLE')
    assert c.records[1]['cause']['nets']
    if c.records[1]['cause']['rule']=='PROPAGATE_RIGID_WINDOW_CYCLE':
        assert all(not c.records[1]['selected_plan'][n]['planar'] for n in c.records[1]['cause']['nets'])
    elif c.records[1]['cause']['rule']=='PROPAGATE_SHARED_WINDOW_ORDER':assert c.records[1]['cause']['owners']
    else:assert any(c.records[1]['selected_plan'][n]!=c.records[0]['selected_plan'][n] for n in c.records[1]['cause']['nets'])
    assert d.model_dump_json()==before


def test_soft_scaffold_coordinates_do_not_become_hard_engineering_constraints():
    d,defs=shared_sources();d.features[0].u=130;d.features[1].u=131
    c=controller(d,defs);c.limit=96;c.next_candidate()
    assert any(r['cause']['rule']=='PROPAGATE_SOFT_SEED_CONTRADICTION' for r in c.records)
    assert any(r['responsible_constraints'].get('preserve_sources') is False for r in c.records)


def test_shared_crossed_windows_reassign_rigid_frame_without_losing_process_choice(tmp_path):
    d,defs=shared_sources();d.features[1].u=90
    d.features[1].circuits={'w0':'N1','w1':'N0','w2':'N2'}
    d=Design.model_validate(d.model_dump());before=d.model_dump_json();c=controller(d,defs)
    chosen=None
    # Examine production process instances. A pending instance is not a pass;
    # all siblings remain in the same controller's real constraint frontier.
    for _ in range(24):
        row=c.next_candidate()
        if row is None:break
        info=c.by_decision[row[1]['engineering_decision']]
        if not info['record']['actual_measurement']['machining_failures']:
            chosen=row;break
    assert chosen,c.diagnostics()
    target,reason,routes=chosen
    assert any(f.face!=g.face for f,g in zip(d.features,target.features))
    assert any(r['cause']['rule']=='PROPAGATE_SHARED_WINDOW_ORDER' for r in c.records)
    assert len(routes)==3
    target.features.extend(f for fs in routes.values() for f in fs)
    for n in target.nets:n.route_state='proposal'
    folder=tmp_path/'production';folder.mkdir()
    result=exact_candidate(target,defs,{},{},folder=folder)
    assert result['status']=='EXACT_FEASIBLE',result.get('failures')
    assert result['topology']==dict(valid=True,solids=1) and result['step']['status']=='PASS'
    assert d.model_dump_json()==before
    (tmp_path/'rigid-frame-decisions.json').write_text(json.dumps(c.diagnostics(),indent=2),encoding='utf-8')


def test_alternative_entry_is_used_before_source_movement(tmp_path):
    definition=CavityDefinition(id='QA_SIDE',label='Explicit side-window witness',
        stages=[dict(start=0,end=40,diameter=16)],zones=[dict(id='w',start=15,end=25,diameter=16)],
        clearance_diameter=20,clearance_height=1)
    d=Design(name='Entry constrained by fixed machining',block=dict(length=140,width=100,height=80,material='QA'),
        rules=dict(minimum_wall=2),features=[
            *[dict(id=f'C{i}',kind='cavity',face='top',u=x,v=60,cavity_id=definition.id,interface_nets={'w':'N'})
                for i,x in enumerate((32,56))],
            dict(id='FIXED',kind='mounting',face='left',u=60,v=60,diameter=12,depth=18,tip_angle=180)],
        nets=[dict(id='N',diameter=8,routing='automatic')])
    defs={definition.id:definition};domain=LayoutDomain.new_generation(d,{'C0','C1'},dimension_axes=())
    c=EngineeringDecisionController(d,defs,domain,{},{},tool_definitions('drill'),limit=128)
    rows=evaluate(c,8);target,a,reason=rows[-1]
    assert a['compatible'],c.diagnostics()
    assert target.model_dump()==d.model_dump()
    record=c.by_decision[reason['engineering_decision']]['record']
    # Check the PLAN's real cuts, rather than letting a legacy route stand in
    # for an unexecuted symbolic intent.
    planned=c.by_decision[reason['engineering_decision']]['routes']['N']
    assert record['selected_plan']['N']['entry']=='positive',record
    assert any(f.face=='right' for f in planned)
    from manifold.routing import route_obstructions
    assert not route_obstructions(d,d.nets[0],planned,{},defs,{})
    actual=target.model_copy(deep=True);actual.features.extend(planned)
    for n in actual.nets:n.route_state='proposal'
    folder=tmp_path/'production';folder.mkdir()
    exact=exact_candidate(actual,defs,{},{},folder=folder)
    assert exact['status']=='EXACT_FEASIBLE',exact.get('failures')
    (tmp_path/'entry-decision.json').write_text(json.dumps(c.diagnostics(),indent=2),encoding='utf-8')


def test_three_source_clear_nets_joint_process_allocation_to_real_exact(tmp_path):
    from manifold.routing import simple_routes,route_obstructions,_ProposalSnapshot,_route_pair_failures
    from manifold.schema import Feature
    d=Design(name='Three mutually blocking machining axes',
        block=dict(length=120,width=120,height=120,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id=f'PORT{i}',kind='port',face=face,u=60,v=60,diameter=12,depth=16,
            tip_angle=180,circuit='N'+str(i//2),clearance_diameter=14,clearance_height=1)
            for i,face in enumerate(('left','right','front','back','bottom','top'))],
        nets=[dict(id='N'+str(i),diameter=8,routing='automatic') for i in range(3)])
    seeds={n.id:dict(route=simple_routes(d,n,{},include_detours=False)[0]) for n in d.nets}
    assert all(not route_obstructions(d,n,seeds[n.id]['route'],{},{},{}) for n in d.nets)
    import itertools
    snap=_ProposalSnapshot(d,{},{},{})
    assert all(_route_pair_failures(d,a,seeds[a.id],b,seeds[b.id],snap,dict(used=0,limit=4000)) for a,b in itertools.combinations(d.nets,2))
    c=controller(d,{});rows=evaluate(c,12);target,a,reason=rows[-1]
    assert a['compatible'],c.diagnostics()
    assert any(any(f[0]=='cross_net_wall' for rows in r.get('actual_measurement',{}).get('machining_failures',{}).values() for f in rows)
               for r in c.records)
    from manifold.ai_design.route_catalog import geometry_key
    planned=c.by_decision[reason['engineering_decision']]['routes']
    assert geometry_key([f for fs in planned.values() for f in fs])==geometry_key([Feature.model_validate(f) for f in a['route_features']])
    assert target.model_dump()!=d.model_dump()
    assert any(r['cause'].get('rule')=='FULL_MACHINING_SEPARATION' for r in c.records)
    target.features.extend(Feature.model_validate(f) for f in a['route_features'])
    for n in target.nets:n.route_state='proposal'
    folder=tmp_path/'production';folder.mkdir()
    exact=exact_candidate(target,{},{},{},folder=folder)
    assert exact['status']=='EXACT_FEASIBLE',exact.get('failures')
    assert exact['topology']==dict(valid=True,solids=1) and exact['step']['status']=='PASS'
    (tmp_path/'three-axis-decisions.json').write_text(json.dumps(c.diagnostics(),indent=2),encoding='utf-8')


def test_normal_plan_new_uses_engineering_frontier_and_real_exact_worker(tmp_path):
    from manifold.ai_design.layout_search import plan_new
    from test_corridor_planner import crossing
    d=crossing();before=d.model_dump_json()
    result=plan_new(d,{},movable_features={f.id for f in d.features},layout_limit=8,exact_limit=1,evidence_dir=tmp_path)
    assert result['status']=='EXACT_FEASIBLE',result.get('attempts')
    assert result['evaluations'][0]['family']=='engineering-plan'
    assert result['engineering_planner']['actual_router_materializations']>0
    assert result['attempts'][0]['full_cad_evaluated']
    assert result['attempts'][0]['topology']==dict(valid=True,solids=1)
    assert result['attempts'][0]['step']['status']=='PASS'
    assert d.model_dump_json()==before


def test_inadequate_direct_contact_drives_axis_constraint_and_real_cad(tmp_path):
    from manifold.schema import Feature
    from manifold.routing import _ProposalSnapshot,_verify_route_candidate
    from manifold.ai_design.engineering_decisions import DecisionState
    from manifold.ai_design.engineering_plan import digest
    from manifold.ai_design.design_space import signature
    from dataclasses import replace
    d=Design(name='Insufficient direct opening, full-cylinder repair',
        block=dict(length=120,width=120,height=120,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id='E0',kind='port',face='back',u=57.95,v=50,diameter=12,depth=16,tip_angle=180,circuit='N'),
                  dict(id='E1',kind='port',face='top',u=50,v=60,diameter=12,depth=16,tip_angle=180,circuit='N'),
                  dict(id='E2',kind='port',face='left',u=60,v=50,diameter=12,depth=16,tip_angle=180,circuit='N')],
        nets=[dict(id='N',diameter=8,routing='automatic')])
    cuts=[Feature(id='A',kind='drilling',face='back',u=57.95,v=50,diameter=8,depth=90,circuit='N',route_net='N'),
          Feature(id='B',kind='drilling',face='top',u=50,v=60,diameter=8,depth=74,circuit='N',route_net='N'),
          Feature(id='C',kind='drilling',face='left',u=60,v=50,diameter=8,depth=65,circuit='N',route_net='N')]
    option=dict(key='skew-junction',route=cuts,risk=0)
    assert not _verify_route_candidate(d,d.nets[0],option,_ProposalSnapshot(d,{},{},{}),prune=False)
    contacts=option['connectivity_detail']['insufficient_direct_contacts']
    assert contacts and all(0<r['volume_mm3']<d.rules.minimum_overlap_volume for r in contacts)
    c=controller(d,{})
    plans={n:replace(p,planar=False) for n,p in c.corridors.initial().items()}
    c.queue.clear();c.enqueue(DecisionState(plans,route_overrides={'N':cuts},override_geometry=digest(signature(d))))
    source,reason,_=c.next_candidate()
    c.observe(source,dict(compatible=False,unresolved_nets=['N'],partial_routing=dict(local_admission={
        'N':dict(status='LOCAL_EXACT_REJECTED',connectivity=option['connectivity_detail'])})),reason['engineering_decision'])
    rows=evaluate(c);target,a,reason=rows[-1]
    (tmp_path/'debug-decisions.json').write_text(json.dumps(c.diagnostics(),indent=2),encoding='utf-8')
    assert a['compatible'],c.diagnostics()
    assert any(r['cause']['rule']=='DIRECT_CONTACT_AXIS_ALIGNMENT' for r in c.records)
    assert d.rules.minimum_overlap_volume==.1
    target.features.extend(Feature.model_validate(f) for f in a['route_features']);target.nets[0].route_state='proposal'
    folder=tmp_path/'production';folder.mkdir()
    result=exact_candidate(target,{},{},{},folder=folder)
    assert result['status']=='EXACT_FEASIBLE',result.get('failures')
    (tmp_path/'contact-repair.json').write_text(json.dumps(dict(decisions=c.diagnostics(),before=contacts,after=result['connections']),indent=2),encoding='utf-8')


def test_engineering_planned_cuts_persist_and_fresh_worker_never_replans(client,tmp_path):
    import subprocess,sys
    from manifold.schema import Feature
    from test_corridor_planner import crossing
    d=crossing();c=controller(d,{});target,a,_=evaluate(c)[-1]
    assert a['compatible']
    target.features.extend(Feature.model_validate(f) for f in a['route_features'])
    for n in target.nets:n.route_state='proposal'
    folder=tmp_path/'first-exact';folder.mkdir()
    exact=exact_candidate(target,{},{},{},folder=folder);assert exact['status']=='EXACT_FEASIBLE'
    current=Design.model_validate(exact['design'])
    response=client.post('/api/projects',json=dict(design=current.model_dump()),headers=HEADERS)
    assert response.status_code==200,response.text
    loaded=client.get('/api/projects/'+response.json()['project_id']).json()['design']
    assert loaded['features']==current.model_dump(mode='json')['features']
    assert all(n['route_state']=='committed' and n['routing_variant'] is None for n in loaded['nets'])
    path=tmp_path/'project.json';path.write_text(json.dumps(loaded),encoding='utf-8')
    code='''
import sys,json
from pathlib import Path
from manifold.schema import Design
from manifold import routing,drilling_planner,store
from manifold.cad_worker import dispatch
from manifold.ai_design import joint_layout,generation,engineering_decisions
def forbidden(*a,**k):raise AssertionError('Implicit replan')
routing.resolve_design=forbidden;drilling_planner.plan_net=forbidden
joint_layout.optimize=forbidden;generation.candidate=forbidden
engineering_decisions.EngineeringDecisionController=forbidden
d=Design.model_validate_json(Path(sys.argv[1]).read_text());before=d.model_dump_json()
r=dispatch('validate',d.model_dump());assert r['report']['counts']['FAIL']==0,r['report']
b=store.build_outputs(d,Path(sys.argv[2]));assert b['counts']['FAIL']==0,b
assert d.model_dump_json()==before
print(json.dumps(dict(validation=r['report']['counts'],build=b['counts'],geometry_unchanged=True,search_called=False)))
'''
    p=subprocess.run([sys.executable,'-B','-c',code,str(path),str(tmp_path/'build')],capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    (tmp_path/'fresh-worker.json').write_text(p.stdout,encoding='utf-8')


def test_optional_operation_provenance_preserves_default_router_geometry():
    import itertools
    from manifold.routing import propose
    from test_corridor_planner import crossing
    d=crossing()
    for net,order,entry in itertools.product(d.nets,itertools.permutations(range(3)),('nearest','negative','positive')):
        records=[]
        before=propose(d,net,order,entry,definitions={})
        after=propose(d,net,order,entry,definitions={},operation_records=records)
        assert [f.model_dump_json() for f in before]==[f.model_dump_json() for f in after]
        assert all(r['required_interval'][0]<r['required_interval'][1] for r in records)
        assert {r['feature'] for r in records}=={f.id for f in after}


def test_source_profile_axial_intervals_drive_actual_machining_and_exact(tmp_path):
    from manifold.schema import Feature
    definition=CavityDefinition(id='QA_END_WINDOW',label='Explicit end-window machining witness',
        stages=[dict(start=0,end=40,diameter=16)],zones=[dict(id='deep',start=30,end=40,diameter=16)],
        clearance_diameter=20,clearance_height=1)
    d=Design(name='Source-backed axial process before placement',block=dict(length=140,width=140,height=120,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id='C'+str(i),kind='cavity',face='top',u=x,v=60,
            cavity_id=definition.id,interface_nets={'deep':'N'}) for i,x in enumerate((40,90))]+[
                dict(id='FIXED',kind='mounting',face='front',u=65,v=85,diameter=12,depth=130)],
        nets=[dict(id='N',diameter=8,routing='automatic')])
    c=controller(d,{definition.id:definition},dimension_axes=(),fixed_faces={'C0':'top','C1':'top'},
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features if f.kind=='cavity'})
    rows=evaluate(c);target,a,reason=rows[-1]
    assert len(c.corridors.profile_access)==2
    info=c.by_decision[reason['engineering_decision']]
    assert info['state'].plans['N'].axial_members
    assert any(r['cause']['rule']=='SOURCE_BACKED_AXIAL_INTERVAL' for r in info['record']['responsible_constraints']['constraints'])
    target.features.extend(Feature.model_validate(f) for f in a['route_features']);target.nets[0].route_state='proposal'
    assert any('-AX' in f.id for f in target.features)
    folder=tmp_path/'production';folder.mkdir()
    result=exact_candidate(target,{definition.id:definition},{},{},folder=folder)
    assert result['status']=='EXACT_FEASIBLE',result.get('failures')
    assert result['topology']==dict(valid=True,solids=1) and result['step']['status']=='PASS'
    (tmp_path/'axial-plan.json').write_text(json.dumps(c.diagnostics(),indent=2),encoding='utf-8')
