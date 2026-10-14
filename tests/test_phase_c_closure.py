"""Continuation and resource scheduling, using real machining/CAD interfaces."""
import json

from manifold.schema import Design, Feature
from manifold.ai_design.joint_solver import RepairTransaction, assignment_key
from manifold.ai_design.joint_layout import exact_candidate
from manifold.ai_design.layout_resources import RefinementSchedule
from manifold.ai_design.local_admission import ADMISSIBLE, ANALYTIC_CLEAR
from manifold.routing import simple_routes
from manifold.closure_runtime import bind_route
from test_phase_c_joint_solver import context
from test_corridor_planner import mutual_barriers, candidate, crossing
from test_ai_global_layout import record
from test_ai_design import client, HEADERS


def three_barriers():
    d,seeds=mutual_barriers()
    raw=d.model_dump()
    raw['features'] += [dict(id=face,kind='port',face=face,u=x,v=60,diameter=10,depth=16,
        tip_angle=180,circuit='Z',clearance_diameter=10,clearance_height=1)
        for face,x in [('bottom',21),('top',92.5)]]
    raw['nets'].append(dict(id='Z',routing='automatic',diameter=8))
    d=Design.model_validate(raw)
    holes=[Feature(id=f'OLD_Z_{i}',kind='drilling',face=('bottom','top')[i%2],u=8+6.5*i,v=60,
        diameter=8,depth=107.5,circuit='Z',route_net='Z',plugged=i not in (2,13)) for i in range(17)]
    seeds['Z']=candidate(bind_route(d,holes))
    return d,seeds


def test_three_new_routes_conditional_batches_and_historical_completion(tmp_path):
    d,seeds=three_barriers();before=d.model_dump_json();s,nets,pair=context(d,seeds=seeds)
    assert all(c.clear for c in s.catalogs.values())
    # The old complete machining of every pair really conflicts.
    import itertools
    assert all(pair(a,seeds[a],b,seeds[b]) for a,b in itertools.combinations(nets,2))
    t=RepairTransaction(s.solver.current,nets,{})
    trace=[];complete=[];spent=[]
    for _ in range(16):
        rows,cost,details=t.advance(s,pair,labels=32,samples=16,states=64)
        spent.append(cost);trace.extend(details)
        if rows:complete=rows;break
    assert complete,t.diagnostics()
    selected=complete[0]
    from manifold.ai_design.route_catalog import geometry_key
    assert all(geometry_key(selected[n]['route'])!=geometry_key(seeds[n]['route']) for n in nets)
    assert max(len(r['conditional_parent']) for r in trace)>=2
    assert any(r.get('resumed') for r in trace)
    delivered={assignment_key(c) for c in complete};calls=t.calls;visited=len(t.visited)
    # A historical completion must neither be redelivered nor stop another
    # non-equivalent branch after one old-result replay.
    later,cost,details=t.advance(s,pair,labels=64,samples=16,states=64)
    assert not delivered & {assignment_key(c) for c in later}
    assert t.calls>calls+1 or later
    assert len(t.visited)>visited or cost['labels']>0
    target=d.model_copy(deep=True)
    target.features.extend(f for o in selected.values() for f in o['route'])
    for n in target.nets:n.route_state='proposal'
    folder=tmp_path/'three-net-exact';folder.mkdir()
    exact=exact_candidate(target,{},{},{},folder=folder)
    assert exact['status']=='EXACT_FEASIBLE',exact.get('failures')
    assert exact['topology']==dict(valid=True,solids=1) and exact['step']['status']=='PASS'
    assert d.model_dump_json()==before
    (tmp_path/'transaction.json').write_text(json.dumps(dict(spent=spent,searches=trace,
        transaction=t.diagnostics(),validation=exact['validation']['counts']),indent=2),encoding='utf-8')


def test_completed_partial_groups_extend_through_real_controller_to_exact(tmp_path):
    from manifold.ai_design.joint_routes import coordinate
    from manifold.ai_design.route_catalog import geometry_key
    d,seeds=three_barriers();before=d.model_dump_json();s,nets,pair=context(d,seeds=seeds)
    selected,detail=coordinate(s,d,nets,{n:c.clear for n,c in s.catalogs.items()},pair,{},
        dict(states=0,limit=1000),labels=512,fragments=True,
        limits=dict(labels=512,states=1000,pairs=4000,probes=128,samples=32))
    assert set(selected)==set(nets),detail
    assert any(e['action']=='CONTINUE_COMPLETED_PARTIAL' and len(e['parent'])>=2 for e in detail['events'])
    assert all(geometry_key(selected[n]['route'])!=geometry_key(seeds[n]['route']) for n in nets)
    target=d.model_copy(deep=True);target.features.extend(f for o in selected.values() for f in o['route'])
    for n in target.nets:n.route_state='proposal'
    folder=tmp_path/'controller-exact';folder.mkdir()
    exact=exact_candidate(target,{},{},{},folder=folder)
    assert exact['status']=='EXACT_FEASIBLE',exact.get('failures')
    assert exact['topology']==dict(valid=True,solids=1) and exact['step']['status']=='PASS'
    assert d.model_dump_json()==before
    (tmp_path/'controller.json').write_text(json.dumps(dict(coverage=len(selected),detail=detail,
        transactions=[t.diagnostics() for t in s.solver.current.transactions.values()]),indent=2),encoding='utf-8')


def test_pending_pair_requires_neither_new_labels_nor_new_samples():
    d=crossing()
    for f in d.features:
        if f.circuit=='T':f.v=80
    s,nets,pair=context(d)
    other=candidate(simple_routes(d,nets['T'],{},include_detours=False)[0])
    t=RepairTransaction(s.solver.current,{'P'},{'T':other})
    s.pair_snapshot.combination_budget['limit']=0
    rows,first,_=t.advance(s,pair,labels=32,samples=8,states=20)
    assert not rows and t.diagnostics()['deferred_pair_candidates']
    count=t.new_candidates
    s.pair_snapshot.combination_budget['limit']=4000
    rows,cost,_=t.advance(s,pair,labels=0,samples=0,states=20)
    assert rows and cost['labels']==cost['samples']==0 and t.new_candidates==count


def test_resource_ledger_does_not_require_labels_for_other_work():
    schedule=RefinementSchedule(2,3,12)
    schedule.used['labels']=schedule.total['labels']
    row=record(0,2)
    row['joint_state']['exploration']=dict(pending_joint_branches=2,new_conditional_depth=2,
        deferred_pair_candidates=1)
    chosen,limits=schedule.select([row],12,final=True)
    assert chosen is row and limits['labels']==0 and limits['probes'] and limits['states']
    schedule.used['samples']=schedule.total['samples'];schedule.used['probes']=schedule.total['probes']
    chosen,limits=schedule.select([row],12,final=True)
    assert limits['samples']==limits['probes']==0 and limits['pairs']


def test_stalled_deep_branch_does_not_starve_new_late_core():
    schedule=RefinementSchedule(2,3,12)
    early=record(0,2);late=record(1,3,rotation=90)
    early['joint_state']['exploration']=dict(pending_joint_branches=4,new_conditional_depth=2)
    schedule.history[0]=dict(calls=2,stalled=1,coverage=2,burden=(3,6))
    chosen,_=schedule.select([early,late],12,final=True)
    assert chosen is late
    schedule.history[0]['stalled']=0
    chosen,_=schedule.select([early,late],12,final=True)
    assert chosen is early  # genuine conditional progress earns follow-up


def test_late_admission_allocation_preserves_real_cached_facts(tmp_path):
    d=crossing()
    for f in d.features:
        if f.circuit=='T':f.v=80
    s,nets,pair=context(d)
    core={n:candidate(simple_routes(d,net,{},include_detours=False)[0]) for n,net in nets.items()}
    s.local_allocation=1
    kept=s.admit_core(d,nets,core)
    assert kept and s.local_admission.used==1
    assert sorted(r['status'] for r in s.local_records.values())==sorted([ADMISSIBLE,ANALYTIC_CLEAR])
    # A later source geometry gets its own real evaluation; early repeated
    # screens consume no reserve and no unknown route is promoted.
    s.admit_core(d,nets,core);assert s.local_admission.used==1
    later=d.model_copy(deep=True);later.block.height+=10
    s.local_allocation=1;s.admit_core(later,nets,core)
    assert s.local_admission.used==2
    s.local_allocation=None;s.admit_core(later,nets,core)
    assert all(r['status']==ADMISSIBLE for r in s.local_records.values())
    (tmp_path/'late-admission.json').write_text(json.dumps(s.local_admission.diagnostics(),indent=2),encoding='utf-8')


def test_late_rejection_reranks_and_checks_the_actual_selected_core(tmp_path):
    from manifold.ai_design.joint_layout import admit_final_cores
    from manifold.ai_design.joint_state import capture,rank
    d=crossing()
    for f in d.features:
        if f.circuit=='T':f.v=80
    seeds={n.id:candidate(simple_routes(d,n,{},include_detours=False)[0]) for n in d.nets}
    bad={n:{**o,'route':[f.model_copy(deep=True) for f in o['route']]} for n,o in seeds.items()}
    for f in bad['P']['route']:f.depth=50  # real source-clear but disconnected
    s,nets,pair=context(d,seeds=bad);state=s.solver.current
    rows=[]
    def add(source,state):
        core={n:c.clear[0] for n,c in state.catalogs.items()}
        a=dict(status='ANALYTIC_UNVALIDATED',compatible=False,partial_routing=dict(nets=sorted(core),
            features=[f.model_dump(mode='json') for o in core.values() for f in o['route']],local_admission={}))
        s.solver.update(a,state=state)
        rows.append(dict(index=len(rows),design=source.model_dump(),assessment=a,joint_state=capture(source,a,{})))
    add(d,state)
    good=d.model_copy(deep=True);good.block.height+=10
    other,good_nets,_=context(good,seeds=seeds)
    s.solver.bind(good,good_nets,other.catalogs);add(good,s.solver.current)
    assert min(rows,key=rank)['index']==0
    def record_state(row,source):row['joint_state']=capture(source,row['assessment'],{})
    visited=[]
    admit_final_cores(rows,s,record_state,lambda stage,**details:visited.append(details['layout_index']))
    selected=min(rows,key=rank)
    assert visited==[0,1] and selected['index']==1
    assert all(r['status']==ADMISSIBLE for r in selected['assessment']['partial_routing']['local_admission'].values())
    assert s.local_admission.used==4
    assert rows[0]['assessment']['partial_routing']['local_admission']['P']['status']=='LOCAL_EXACT_REJECTED'
    (tmp_path/'reranked-admission.json').write_text(json.dumps(dict(visited=visited,used=s.local_admission.used,
        selected=selected['index'],records=[r['assessment']['partial_routing']['local_admission'] for r in rows]),indent=2),encoding='utf-8')


def test_conditional_fragments_use_remaining_probes_without_labels():
    d=crossing()
    for f in d.features:
        if f.circuit=='T':f.v=80
    seeds={n.id:candidate(simple_routes(d,n,{},include_detours=False)[0]) for n in d.nets}
    s,nets,pair=context(d,seeds=seeds)
    t=RepairTransaction(s.solver.current,{'P'},{'T':seeds['T']})
    rows,spent,details=t.advance(s,pair,labels=0,samples=8,states=32,probes=16)
    assert spent['labels']==0 and spent['probes']>0 and details
    assert t.probes==spent['probes']
    assert all(r['labels']==0 for r in details)
    assert s.search_context.searches=={}  # no reconstruction of any 3D prefix


def test_partial_draft_save_reload_and_explicit_reroute_preserve_sources(client,monkeypatch,tmp_path):
    import subprocess, sys
    from manifold import routing
    from manifold.ai_design.joint_routes import coordinate
    from manifold.schema import Design
    d,seeds=three_barriers();s,nets,pair=context(d,seeds=seeds)
    selected,detail=coordinate(s,d,nets,{n:c.clear for n,c in s.catalogs.items()},pair,{},
        dict(states=0,limit=1000),labels=512,fragments=True,
        limits=dict(labels=512,states=1000,pairs=4000,probes=128,samples=32))
    assert set(selected)==set(nets)
    missing=sorted(nets)[-1];retained=set(nets)-{missing}
    current=d.model_copy(deep=True)
    current.features.extend(f for n,o in selected.items() if n in retained for f in o['route'])
    for n in current.nets:n.route_state='proposal' if n.id in retained else 'unresolved'
    saved=client.post('/api/projects',json=dict(design=current.model_dump(),draft_only=True),headers=HEADERS)
    assert saved.status_code==200,saved.text
    loaded=client.get('/api/projects/'+saved.json()['project_id']).json()['design']
    assert loaded['features']==current.model_dump(mode='json')['features']
    assert next(n for n in loaded['nets'] if n['id']==missing)['route_state']=='unresolved'
    path=tmp_path/'partial.json';path.write_text(json.dumps(loaded),encoding='utf-8')
    # New process, no candidate cache. Validate/Build refuse the missing route;
    # they neither manufacture a PASS nor silently initiate routing/layout.
    code='''
import sys,json
from pathlib import Path
from manifold.schema import Design
from manifold import routing,drilling_planner,store
from manifold.cad_worker import dispatch
from manifold.ai_design import joint_layout,generation
def forbidden(*a,**k):raise AssertionError('Implicit search or layout mutation')
routing.resolve_design=forbidden;drilling_planner.plan_net=forbidden
joint_layout.optimize=forbidden;generation.candidate=forbidden
d=Design.model_validate_json(Path(sys.argv[1]).read_text());before=d.model_dump_json();results=[]
for action in (lambda:dispatch('validate',d.model_dump()),lambda:store.build_outputs(d,Path(sys.argv[2]))):
    try:action()
    except ValueError as e:
        assert 'Routing must finish for '+sys.argv[3] in str(e),e
        results.append(str(e))
    else:raise AssertionError('Incomplete routes cannot be accepted')
assert d.model_dump_json()==before
print(json.dumps(dict(blocked=results,search_called=False,geometry_unchanged=True)))
'''
    p=subprocess.run([sys.executable,'-c',code,str(path),str(tmp_path/'partial-build'),missing],capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    (tmp_path/'partial-worker.json').write_text(p.stdout,encoding='utf-8')
    loaded=Design.model_validate(loaded)
    # Releasing only the unresolved Net is explicit. The retained Net is
    # committed as in Model and all source coordinates remain user-owned.
    for n in loaded.nets:
        if n.id in retained:n.route_state='committed'
    before=[f.model_dump_json() for f in loaded.features if not f.route_net or f.route_net in retained]
    calls=[];real=routing.route_options
    def released_only(design,net,**kwargs):
        assert net.id==missing
        calls.append(net.id);return real(design,net,**kwargs)
    monkeypatch.setattr(routing,'route_options',released_only)
    result,_=routing.resolve_design(loaded,exact=False)
    assert result.block==loaded.block
    assert [f.model_dump_json() for f in result.features if not f.route_net or f.route_net in retained]==before
    assert calls and set(calls)=={missing}
