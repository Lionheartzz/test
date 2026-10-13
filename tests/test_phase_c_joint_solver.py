"""Real machining and CAD evidence for the AI-owned joint controller."""
import itertools
import json
from pathlib import Path

from manifold.schema import Design, Feature
from manifold.ai_design.route_catalog import Session, Catalog, geometry_key
from manifold.ai_design.joint_solver import RepairTransaction
from manifold.ai_design.layout_search import screen
from manifold.ai_design.local_admission import LocalAdmission, CAD_ERROR, REJECTED
from manifold.ai_design.design_space import LayoutDomain
from manifold.ai_design.coupled_layout import actions
from manifold.ai_design.joint_layout import exact_candidate
from manifold.ai_design.layout_resources import RefinementSchedule
from manifold.routing import _ProposalSnapshot, _route_pair_failures, simple_routes
from manifold.routing_continuation import AISearchContext
from manifold import engineering_db as db
from test_corridor_planner import crossing, mutual_barriers, candidate
from test_ai_global_layout import coupled, record, exhaust_slice
from test_ai_joint_feedback import crossed, direct_screen, row


def context(d, defs=None, seeds=None):
    defs=defs or {};s=Session();s.search_context=AISearchContext(trace=True)
    tools=db.tool_definitions('drill');nets={n.id:n for n in d.nets if len(n.members)>=2}
    s.context=s.source_context(d,defs,{},{},tools);s._prepared_once=True
    for n,net in nets.items():
        c=Catalog(d,net,defs,{},{},tools,s.cache)
        if seeds and n in seeds:c.accept(seeds[n]['key'],seeds[n]['route'],'reviewed-real-cuts')
        s.catalogs[n]=c
    s.solver.bind(d,nets,s.catalogs)
    snapshot=_ProposalSnapshot(d,defs,{},{})
    s.pair_snapshot=snapshot
    def pair(a,ao,b,bo):
        state=s.solver.current;fact=state.pair_fact(a,ao,b,bo)
        if fact is not None:return {tuple(f) for f in fact['failures']}
        failures=_route_pair_failures(d,nets[a],ao,nets[b],bo,snapshot,snapshot.combination_budget)
        state.pair_fact(a,ao,b,bo,failures)
        return failures
    return s,nets,pair


def test_two_nets_need_new_conditional_routes_and_true_exact(tmp_path):
    d,seeds=mutual_barriers();before=d.model_dump_json();s,nets,pair=context(d,seeds=seeds)
    assert pair(*[x for n in nets for x in (n,seeds[n])])
    assert all(c.clear for c in s.catalogs.values())
    from manifold.ai_design.joint_routes import coordinate
    state=s.solver.current
    selected,coordination=coordinate(s,d,nets,{n:c.clear for n,c in s.catalogs.items()},pair,{},
        dict(states=0,limit=1000),labels=512,fragments=True,
        limits=dict(labels=512,states=1000,pairs=4000,probes=128,samples=32))
    details=coordination['net_searches'];spent=coordination['labels']
    assert coordination['fragments_deferred_for_joint_continuation'] and coordination['raw_probes']==0
    assert set(selected)==set(nets),coordination
    transaction=next(t for t in state.transactions.values() if t.completed)
    assert transaction.outside=={}  # real temporary 1 -> 0 -> 2 core retreat
    assert any(e['action']=='EXTEND_WITH_JOINT_3D' and e['before']==1 and e['after']==2 for e in coordination['events'])
    assert all(geometry_key(selected[n]['route'])!=geometry_key(seeds[n]['route']) for n in nets)
    assert any(r['conditional_parent'] for r in details)
    assert any(e['action']=='JOINT_REPLACEMENT_READY' and set(e['regenerated'])==set(nets) for e in transaction.events)
    result=d.model_copy(deep=True);result.features.extend(f for o in selected.values() for f in o['route'])
    for n in result.nets:n.route_state='proposal'
    folder=tmp_path/'joint-exact';folder.mkdir()
    exact=exact_candidate(result,{},{},{},folder=folder)
    assert exact['status']=='EXACT_FEASIBLE',exact.get('failures')
    assert exact['topology']==dict(valid=True,solids=1) and exact['step']['status']=='PASS'
    assert exact['validation']['counts']['FAIL']==0
    assert d.model_dump_json()==before
    (tmp_path/'joint-search.json').write_text(json.dumps(dict(searches=details,spent=spent,
        transaction=transaction.diagnostics()),indent=2),encoding='utf-8')


def test_joint_repair_resumes_real_3d_heaps_without_repeating_prefix():
    d=crossing();s,nets,pair=context(d);t=RepairTransaction(s.solver.current,set(nets),{})
    _,cost,one=t.advance(s,pair,labels=1,samples=8,states=20)
    first={k:list(v.trace) for k,v in s.search_context.searches.items()}
    two=[]
    for _ in range(2):
        _,cost,details=t.advance(s,pair,labels=1,samples=8,states=20);two.extend(details)
    assert any(r['resumed'] for r in two)
    for k,trace in first.items():
        search=s.search_context.searches[k]
        assert search.trace[:len(trace)]==trace
        assert len(search.trace)>len(trace)
        assert search.trace[len(trace):]!=trace
    assert sum(v.budget['used'] for v in s.search_context.searches.values())==3


def test_unchecked_pair_candidate_is_retained_then_rechecked():
    d=crossing()
    for f in d.features:
        if f.circuit=='T':f.v=80
    s,nets,pair=context(d)
    retained=candidate(simple_routes(d,nets['T'],{},include_detours=False)[0])
    t=RepairTransaction(s.solver.current,{'P'},{'T':retained})
    s.pair_snapshot.combination_budget['limit']=0
    complete,_,_=t.advance(s,pair,labels=32,samples=8,states=100)
    assert not complete and t.diagnostics()['deferred_pair_candidates']
    assert not s.solver.current.violations
    s.pair_snapshot.combination_budget['limit']=4000
    complete,_,_=t.advance(s,pair,labels=32,samples=8,states=100)
    assert complete and set(complete[0])=={'P','T'}


def test_clear_net_keeps_source_blocked_alternate_entry_feedback():
    d=crossing();raw=d.model_dump();raw['features'].append(dict(id='obstacle',kind='port',face='top',u=30,v=60,
        diameter=12,depth=25,tip_angle=180,circuit='unused',clearance_diameter=14,clearance_height=1))
    raw['nets'].append(dict(id='unused',routing='manual',diameter=8));d=Design.model_validate(raw)
    seeds={n.id:candidate(simple_routes(d,n,{},include_detours=False)[0]) for n in d.nets if len(n.members)>1}
    s,nets,pair=context(d,seeds=seeds)
    alternative=Feature(id='alternate',kind='drilling',face='top',u=30,v=60,diameter=8,depth=75,
        circuit=d.nets[0].id,route_net=d.nets[0].id,plugged=True)
    s.catalogs[d.nets[0].id].accept('other-entry',[alternative],'alternative-entry')
    assert s.catalogs[d.nets[0].id].clear and s.catalogs[d.nets[0].id].rejected
    a=screen(d,{},{},{},db.tool_definitions('drill'),{},{},general_families=True,
             corridor_labels=0,route_session=s,include_routes=True)
    witnesses=[w for w in a['spatial_feedback'] if w['net']==d.nets[0].id and w['source']=='obstacle']
    assert witnesses and a['pools'][d.nets[0].id]['source_clear']>0
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features})
    from manifold.ai_design.route_feedback import measured_actions
    proposals=list(itertools.islice(measured_actions(d,a,{},domain,{},{}),12))
    assert any(r.get('source')=='obstacle' or 'obstacle' in r.get('owners',[]) for _,_,r in proposals)
    assert a['joint_solver']['source_obstacle_count']


def test_conditioned_nogoods_expire_on_source_stock_and_route_change():
    d=crossing();seeds={n.id:candidate(simple_routes(d,n,{},include_detours=False)[0]) for n in d.nets}
    s,nets,pair=context(d,seeds=seeds);state=s.solver.current
    assert pair('P',seeds['P'],'T',seeds['T']) and not state.permits(seeds)
    changed=d.model_copy(deep=True);changed.block.height+=8;changed.features[0].v+=8
    new_catalogs={n:Catalog(changed,next(k for k in changed.nets if k.id==n),{},{},{},db.tool_definitions('drill'),{}) for n in nets}
    s.solver.bind(changed,{n.id:n for n in changed.nets},new_catalogs)
    assert s.solver.current is not state and s.solver.current.permits(seeds)
    changed_route={**seeds,'P':{**seeds['P'],'route':[f.model_copy(update=dict(v=f.v+8)) for f in seeds['P']['route']]}}
    assert state.permits(changed_route)  # unknown, not a transferred approval
    s.solver.bind(d,nets,s.catalogs)
    assert s.solver.current is state and not s.solver.permits(seeds)


def test_shared_rigid_sources_move_all_windows_and_affected_nets():
    d,defs=coupled();s,nets,pair=context(d,defs);original=d.model_dump_json()
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features})
    s.solver.domain=domain.diagnostics()
    proposals=list(itertools.islice(actions(d,dict(unresolved_nets=list(nets)),defs,domain,{},{}),3))
    assert proposals
    for _,target,why in proposals:
        assert len(why['changed_features'])>=2
        assert set(why['affected_nets'])==set(nets)
        assert domain.accepts(d,target)
        assert len(why['interface_frames_after'])==6
    assert d.model_dump_json()==original


def test_temporary_coverage_loss_retained_and_receives_refinement():
    # A lower-coverage geometry is a different future space, not a dominated
    # assignment. Actual CAD witness below also checks the safe endpoint.
    scheduler=RefinementSchedule(2,4,24)
    incumbent=record(0,3);retreat=record(1,2,rotation=90)
    selected,limits=scheduler.select([incumbent],4);exhaust_slice(scheduler,selected,limits)
    selected,_=scheduler.select([incumbent,retreat],8)
    assert selected is retreat
    d=crossing();s,nets,pair=context(d)
    source_clear={n.id:candidate(simple_routes(d,n,{},include_detours=False)[0]) for n in d.nets}
    s.solver.current.retain({'P':source_clear['P']});s.solver.current.retain({})
    # No maximum-coverage-only prune in the operation-owned core frontier.
    s.seed_combination(d,{'P':source_clear['P']})
    s.seed_combination(d,{'T':source_clear['T']})
    assert {tuple(sorted(c)) for c in s.solver.current.cores.values()}=={(),('P',),('T',)}


def test_unknown_cad_and_actual_violations_never_become_same_constraint():
    data=json.loads((Path(__file__).parent/'fixtures/phase-b-local-core.json').read_text(encoding='utf-8'))
    from manifold.schema import CavityDefinition
    d=Design.model_validate(data['source']);defs={k:CavityDefinition.model_validate(v) for k,v in data['definitions'].items()}
    core={n:dict(key='saved:'+n,risk=0,route=[Feature.model_validate(f) for f in data['core']['features'] if f['route_net']==n])
          for n in data['core']['nets']}
    s,nets,pair=context(d,defs);gate=LocalAdmission(2);s.local_admission=gate;gate.bind(d,nets,s.catalogs)
    c=s.catalogs['P']
    error=gate.check(d,nets['P'],core['P'],core,defs,data['threads'],{},c.tools)
    assert error['status']==CAD_ERROR and error['physical_connectivity'] is None
    assert not s.solver.current.constraints
    assert error['cad_error']['reason_code']=='INVALID_TOPOLOGY'
    assert error['retry_conditions']


def test_real_full_exact_rejection_updates_the_owned_feedback_state():
    from manifold.ai_design.route_feedback import exact_witnesses
    from manifold.ai_design.initialization import route_feedback
    d=crossing();s,nets,pair=context(d)
    original=dict(status='ANALYTIC_UNVALIDATED',spatial_feedback=[],coordination_constraints=[],partial_routing={})
    s.solver.update(original);state=s.solver.current
    trial=d.model_copy(deep=True)
    trial.features.extend(f for n in d.nets for f in simple_routes(d,n,{},include_detours=False)[0])
    for n in trial.nets:n.route_state='proposal'
    actual=exact_candidate(trial,{},{},{})
    assert actual['status']=='EXACT_ROUTING_REJECTED' and actual['failures']
    constraints,spatial=exact_witnesses(trial,actual['failures'],{},{},{})
    updated={**original,'exact_failures':actual['failures'],'exact_connections':actual['connections'],
             'coordination_constraints':constraints,'spatial_feedback':spatial,'full_exact_status':actual['status']}
    # Change the active source state to exercise feedback for a stored layout,
    # not just whichever layout happened to be evaluated last.
    other=d.model_copy(deep=True);other.block.height+=20
    s.solver.bind(other,{n.id:n for n in other.nets},s.catalogs)
    s.solver.update(updated,state=state)
    assert state.assessment is updated and state.assessment['exact_failures']==actual['failures']
    assert state.assessment['joint_solver']['full_exact_status']==actual['status']
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features})
    proposal=next(route_feedback(d,state.assessment,{},domain,{},{},joint_state=state))
    assert domain.accepts(d,proposal[1]) and proposal[2]['requires_route_regeneration']
