"""Real shared searches and local CAD gates; no mocked engineering outcomes."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from manifold.schema import Design,Feature,CavityDefinition
from manifold.drilling_planner import plan_net,candidate
from manifold.routing_continuation import AISearchContext
from manifold.routing_space import network_key
from manifold.ai_design.local_admission import LocalAdmission,ADMISSIBLE,REJECTED,CAD_ERROR,ANALYTIC_CLEAR
from manifold import engineering_db as db
from test_corridor_planner import crossing
from test_phase_a_correctness import short_case


def run_batches(batches):
    d=crossing();ctx=AISearchContext(trace=True);net=d.nets[0];results=[];details=[]
    for count in batches:
        options,detail=plan_net(d,net,{}, {},{},label_limit=count,alternatives=20,ai_context=ctx)
        results.extend(options);details.append(detail)
    search=ctx.searches[ctx.last_key]
    return ctx,search,results,details


def test_shared_search_batch_partition_preserves_exact_trace_and_candidates():
    split,first,_,details=run_batches([16,16,32]);whole,second,_,_=run_batches([64])
    assert first.trace==second.trace and len(first.trace)==64
    assert set(first.candidates)==set(second.candidates)
    assert [d['labels'] for d in details]==[16,16,32]
    assert [d['cumulative_labels'] for d in details]==[16,32,64]
    assert [d['resumed'] for d in details]==[False,True,True]
    assert first.trace[:16]!=first.trace[16:32]
    assert first.path.queue and first.path.seen and first.visited
    assert first.space.coordinates and first.space.visited_coordinates
    assert first.budget['alternatives'] is None and not first.path.done


def test_independent_reference_reuses_only_geometry_and_keeps_its_own_search_frontier():
    d=crossing();net=d.nets[0];cache={};first=AISearchContext(trace=True);second=AISearchContext(trace=True)
    a,_=plan_net(d,net,{}, {},{},label_limit=32,alternatives=20,ai_context=first,cache=cache)
    b,_=plan_net(d,net,{}, {},{},label_limit=32,alternatives=20,ai_context=second,cache=cache)
    one=first.searches[first.last_key];two=second.searches[second.last_key]
    assert one.trace==two.trace and one is not two and one.path is not two.path
    assert one.space.actions is two.space.actions and two.space.generated==0
    assert [o['key'] for o in a]==[o['key'] for o in b]
    if a:
        before=one.candidates[network_key(a[0]['route'])]['route'][0].depth
        a[0]['route'][0].depth+=1
        assert any(o['route'][0].depth==before for o in one.candidates.values())


@pytest.mark.parametrize('change',['source','block','endpoint','definition','thread','modifier','closure','reserved','tool'])
def test_search_dependencies_invalidate_without_mutating_or_losing_original_frontier(change):
    from copy import deepcopy
    d,defs=short_case();tools=db.tool_definitions('drill');net=d.nets[0];ctx=AISearchContext(trace=True)
    args=dict(definitions=defs,threads={},modifiers={},tools=tools,reserved=[])
    plan_net(d,net,**args,label_limit=2,ai_context=ctx);original_key=ctx.last_key;search=ctx.searches[original_key]
    old_used=search.budget['used'];new=d.model_copy(deep=True);changed=deepcopy(args)
    if change=='source':new.features[0].v+=1
    if change=='block':new.block.height+=1
    if change=='endpoint':new.nets[0].members=['P']
    if change=='definition':changed['definitions']['QA_SHORT_WINDOW'].clearance_diameter+=1
    if change=='thread':changed['threads']['new']={'tap_diameter_mm':3}
    if change=='modifier':changed['modifiers']['new']={'primitives':[]}
    if change in ('reserved','closure'):
        cut=Feature(id='RESERVED',kind='drilling',face='right',u=30,v=30,diameter=4,depth=20,circuit='OTHER',plugged=True,plug_length=5)
        if change=='closure':cut.plug_length=6
        changed['reserved']=[cut]
    if change=='tool':changed['tools']=[]
    _,detail=plan_net(new,new.nets[0],**changed,label_limit=0,ai_context=ctx)
    assert not detail['resumed'] and ctx.last_key!=original_key
    if change=='endpoint':assert detail['classification']=='SOURCE_DATA_UNRESOLVED'
    _,detail=plan_net(d,net,**args,label_limit=2,ai_context=ctx)
    assert ctx.last_key==original_key and detail['resumed'] and detail['cumulative_labels']==old_used+2
    assert ctx.searches[original_key] is search


def test_context_freezes_definition_objects_and_does_not_replay_delivered_candidates():
    d,defs=short_case();ctx=AISearchContext(trace=True)
    options,_=plan_net(d,d.nets[0],defs,{}, {},label_limit=8,alternatives=20,ai_context=ctx)
    search=ctx.searches[ctx.last_key];original=search.space.definitions['QA_SHORT_WINDOW'].clearance_diameter
    defs['QA_SHORT_WINDOW'].clearance_diameter+=2
    assert search.space.definitions['QA_SHORT_WINDOW'].clearance_diameter==original
    later,_=plan_net(d,d.nets[0],search.space.definitions,{}, {},label_limit=8,alternatives=20,ai_context=ctx,
                     forbidden=[network_key(o['route']) for o in options])
    assert not {o['key'] for o in options}&{o['key'] for o in later}


def safe_local_case():
    d,defs=short_case();route=plan_net(d,d.nets[0],defs,{}, {},label_limit=32,alternatives=1)[0][0]
    return d,defs,route


def test_local_success_rejection_pending_and_dependency_cache_are_distinct():
    d,defs,option=safe_local_case();tools=db.tool_definitions('drill');net=d.nets[0]
    gate=LocalAdmission(8);core={net.id:option}
    good=gate.check(d,net,option,core,defs,{}, {},tools)
    assert good['status']==ADMISSIBLE and good['physical_connectivity'] is True
    assert gate.check(d,net,option,core,defs,{}, {},tools)==good and gate.used==1
    changed=d.model_copy(deep=True);changed.block.height+=1
    again=gate.check(changed,changed.nets[0],option,core,defs,{}, {},tools)
    assert again['dependency']!=good['dependency'] and gate.used==2
    shallow=candidate([option['route'][0].model_copy(update=dict(depth=1))])
    bad=gate.check(d,net,shallow,{net.id:shallow},defs,{}, {},tools)
    assert bad['status']==REJECTED and bad['physical_connectivity'] is False
    pending=LocalAdmission(0).check(d,net,option,core,defs,{}, {},tools)
    assert pending['status']==ANALYTIC_CLEAR and pending['physical_connectivity'] is None
    assert not pending['checked'] and pending['full_engineering_validation_passed'] is None
    retained=Feature(id='OUTSIDE',kind='drilling',face='right',u=30,v=30,diameter=4,depth=12,circuit='OTHER')
    conditional={**core,'OTHER':candidate([retained])}
    other=gate.check(d,net,option,conditional,defs,{}, {},tools)
    assert other['dependency']!=good['dependency']


def test_cross_net_rejection_is_conditional_and_never_poisoned_into_intrinsic_failure():
    d,defs,option=safe_local_case();tools=db.tool_definitions('drill');net=d.nets[0]
    gate=LocalAdmission(4)
    catalog=SimpleNamespace(definitions=defs,threads={},modifiers={},tools=tools)
    gate.bind(d,{'N':net},{'N':catalog})
    obstacle=Feature(id='CROSS',kind='drilling',face='front',u=5,v=20,diameter=3,depth=25,circuit='OTHER',route_net='OTHER')
    core={'N':option,'OTHER':candidate([obstacle])}
    record=gate.check(d,net,option,core,defs,{}, {},tools)
    assert record['status']==REJECTED and record['physical_connectivity'] is True
    assert gate.permits({'N':option})
    good=gate.check(d,net,option,{'N':option},defs,{}, {},tools)
    assert good['status']==ADMISSIBLE and good['dependency']!=record['dependency']


def test_e6_real_core_error_remains_diagnostic_and_legal_routes_survive(tmp_path):
    from manifold.ai_design.route_catalog import Session
    from manifold.ai_design.joint_routes import improve,coordinate
    raw=json.loads(Path('tests/fixtures/phase-b-local-core.json').read_text(encoding='utf-8'))
    d=Design.model_validate(raw['source']);defs={k:CavityDefinition.model_validate(v) for k,v in raw['definitions'].items()}
    nets={n.id:n for n in d.nets};core={n:dict(key='saved:'+n,risk=0,
        route=[Feature.model_validate(f) for f in raw['core']['features'] if f['route_net']==n]) for n in raw['core']['nets']}
    before={n:[f.model_dump_json() for f in o['route']] for n,o in core.items()};session=Session()
    tools=db.tool_definitions('drill')
    session.catalogs={n:SimpleNamespace(definitions=defs,threads=raw['threads'],modifiers={},tools=tools) for n in core}
    from manifold.routing import route_obstructions
    def pair(a,ao,b,bo):
        context=d.model_copy(update=dict(features=[*d.features,*ao['route'],*bo['route']]))
        return route_obstructions(context,nets[a],ao['route'],raw['threads'],defs,{}, {})|route_obstructions(context,nets[b],bo['route'],raw['threads'],defs,{}, {})
    kept,joint=coordinate(session,d,nets,{n:[core[n]] if n in core else [] for n in nets},pair,core,
                          dict(states=0,limit=32),labels=0,fragments=False)
    records=session.local_records
    errors=[r for r in records.values() if r['status']==CAD_ERROR]
    assert len(errors)==1 and len(kept)==5
    error=errors[0];expected=raw['expected_error']
    assert error['cad_error']['reason_code']==expected['reason_code']=='INVALID_TOPOLOGY'
    assert error['cad_error']['node_pair']==expected['node_pair']
    assert error['physical_connectivity'] is None and error['retry_conditions']
    assert all(records[n]['status']==ADMISSIBLE for n in kept)
    assert {n:[f.model_dump_json() for f in o['route']] for n,o in core.items()}==before
    # This is a real CAD result guiding the existing core selector. No fake
    # pair approvals: every pair goes through the actual shared obstruction API.
    selected,_,_=improve(d,nets,{n:[o] for n,o in core.items()},pair,core,dict(states=0,limit=32),eligible=session.permits_core)
    assert set(selected)==set(kept)
    assert session.admit_core(d,nets,core).keys()==kept.keys() and session.local_admission.used==6
    name=error['net'];c=session.catalogs[name]
    retried=session.local_admission.check(d,nets[name],core[name],core,c.definitions,c.threads,c.modifiers,c.tools,retry=True)
    assert retried['status']==CAD_ERROR and not retried['cad_error'].get('cached_rejection')
    from copy import deepcopy
    from manifold.routing import _verify_route_candidate,_ProposalSnapshot
    default=deepcopy(core[name]);context=d.model_copy(update=dict(features=[*d.features,*[f for o in core.values() for f in o['route']]]))
    assert not _verify_route_candidate(context,nets[name],default,_ProposalSnapshot(context,defs,raw['threads'],{}))
    assert default['cad_geometry_error']['reason_code']==error['cad_error']['reason_code']
    (tmp_path/'local-admission.json').write_text(json.dumps(records,indent=2),encoding='utf-8')


def test_admission_evidence_does_not_reset_search_and_score_keeps_unknown_separate():
    from manifold.ai_design.joint_state import capture
    d,defs=short_case();ctx=AISearchContext(trace=True)
    options,detail=plan_net(d,d.nets[0],defs,{}, {},label_limit=16,alternatives=20,ai_context=ctx)
    assert options
    search=ctx.searches[ctx.last_key];before=search.budget['used'];gate=LocalAdmission(4)
    record=gate.check(d,d.nets[0],options[0],{d.nets[0].id:options[0]},defs,{}, {},db.tool_definitions('drill'))
    ctx.record_admission(options[0],record)
    plan_net(d,d.nets[0],defs,{}, {},label_limit=8,alternatives=20,ai_context=ctx)
    assert search.budget['used']==before+8
    assert record['dependency'] in search.evidence[options[0]['key']]
    partial=dict(nets=['N'],features=[f.model_dump(mode='json') for f in options[0]['route']],local_admission={'N':record})
    state=capture(d,dict(partial_routing=partial),defs)
    assert state['locally_admitted_nets']==['N'] and not state['local_pending_nets']
    partial['local_admission']={}
    state=capture(d,dict(partial_routing=partial),defs)
    assert not state['locally_admitted_nets'] and state['local_pending_nets']==['N']


def test_real_local_rejection_is_retained_while_its_search_frontier_continues():
    d,defs=short_case();d.rules.minimum_overlap_volume=1000
    ctx=AISearchContext(trace=True)
    options,_=plan_net(d,d.nets[0],defs,{}, {},label_limit=16,alternatives=20,ai_context=ctx)
    assert options
    search=ctx.searches[ctx.last_key];old_candidates=set(search.candidates);actions=search.space.actions
    gate=LocalAdmission(4);record=gate.check(d,d.nets[0],options[0],{'N':options[0]},defs,{}, {},db.tool_definitions('drill'))
    assert record['status']==REJECTED and record['physical_connectivity'] is False
    ctx.record_admission(options[0],record)
    assert gate.check(d,d.nets[0],options[0],{'N':options[0]},defs,{}, {},db.tool_definitions('drill'))==record
    assert gate.used==1
    later,detail=plan_net(d,d.nets[0],defs,{}, {},label_limit=8,alternatives=20,ai_context=ctx)
    assert detail['labels']==8 and detail['cumulative_labels']==24 and detail['resumed']
    assert old_candidates<=set(search.candidates) and search.space.actions is actions
    assert not {o['key'] for o in options}&{o['key'] for o in later}
    assert record['dependency'] in search.evidence[options[0]['key']]
