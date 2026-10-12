"""Real operation-space CAD milestones; no planner or CAD-result mocks."""
import json
import heapq
from pathlib import Path
import pytest

from manifold.schema import Design,Feature,CavityDefinition
from manifold import engineering_db,geometry,routing
from manifold.drilling_planner import plan_net,coordinate_routes,candidate
from manifold.closure_runtime import bind_route
from manifold.cad_acceptance import step_round_trip
from manifold.validation import validate


def crossing():
    return Design(name='Corridor Stage A',block=dict(length=120,width=120,height=120,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id=i,kind='port',face=f,u=u,v=v,diameter=12,depth=16,tip_angle=180,circuit=n,clearance_diameter=14,clearance_height=1)
            for i,f,u,v,n in [('P1','left',60,50,'P'),('P2','right',60,50,'P'),('T1','front',60,50,'T'),('T2','back',60,50,'T')]],
        nets=[dict(id=n,routing='automatic',diameter=8) for n in ('P','T')])


def verify_case(d,chosen,defs,folder,monkeypatch,diagnostics=None):
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:defs)
    result=d.model_copy(deep=True);owners=set(chosen)
    result.features=[f for f in result.features if f.route_net not in owners]+[f for o in chosen.values() for f in o['route']]
    for n in result.nets:
        if n.id in owners:n.route_state='proposal';n.routing_variant=None
    g=geometry.build_geometry(result,defs,{},{});routing.authorize_generated_contacts(result,g)
    report=validate(result,g);folder.mkdir(parents=True,exist_ok=True)
    step=step_round_trip(g,folder/'production.step')
    evidence=dict(design=result.model_dump(mode='json'),definitions={k:v.model_dump(mode='json') for k,v in defs.items()},
        validation=report,step=step,brep_valid=g.production.isValid(),solid_count=len(g.production.Solids()),diagnostics=diagnostics)
    (folder/'acceptance.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    assert report['counts']['FAIL']==0,[(c['rule'],c['items'],c['actual']) for c in report['checks'] if c['status']=='FAIL']
    assert g.production.isValid() and len(g.production.Solids())==1
    assert step['status']=='PASS',step
    assert not any(c['rule']=='construction_closure' and c['status']!='PASS' for c in report['checks'])
    return result,report


def test_stage_a_changes_layer_with_real_drillings(monkeypatch,tmp_path):
    d=crossing();before=d.model_dump_json()
    # The unconstrained direct operations really do intersect.
    a=Feature(id='DIRECT_P',kind='drilling',face='left',u=60,v=50,diameter=8,depth=108,circuit='P',route_net='P')
    b=Feature(id='DIRECT_T',kind='drilling',face='front',u=60,v=50,diameter=8,depth=108,circuit='T',route_net='T')
    raw=d.model_copy(update=dict(features=d.features+[a,b]));g=geometry.build_geometry(raw,{}, {}, {})
    assert g.nodes[a.id].intersect(g.nodes[b.id]).Volume()>100
    chosen,diag=coordinate_routes(d,d.nets,{}, {}, {},label_limit=256)
    assert chosen,diag
    result,_=verify_case(d,chosen,{},tmp_path/'stage-a',monkeypatch,diag)
    assert any(f.face in ('top','bottom') for f in result.features if f.route_net)
    assert d.model_dump_json()==before


def branching():
    definition=CavityDefinition(id='QA_WINDOW',label='QA explicit source window, not vendor data',
        stages=[dict(start=0,end=40,diameter=16)],zones=[dict(id='deep',start=30,end=40,diameter=16)],
        clearance_diameter=20,clearance_height=5)
    d=Design(name='Corridor Stage B',block=dict(length=140,width=140,height=120,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id='CV',kind='cavity',face='top',u=70,v=70,cavity_id=definition.id,interface_nets={'deep':'N'}),
            *[dict(id=i,kind='port',face=f,u=u,v=v,diameter=12,depth=16,tip_angle=180,circuit='N',clearance_diameter=14,clearance_height=1)
                for i,f,u,v in [('E1','left',30,40),('E2','right',100,85),('E3','front',100,30),('E4','back',40,95)]]],
        nets=[dict(id='N',routing='automatic',diameter=8)])
    return d,{definition.id:definition}


def minimum_internal_turns(design,start,end):
    # Declarations here were rebuilt by authorize_generated_contacts from the
    # real BReps; verify_case has also required every direct opening to pass.
    from manifold.kinematics import FACE_AXES
    graph={};axes={f.id:FACE_AXES[f.face][2] for f in design.features if f.route_net}
    for feature in design.features:
        for other in feature.connects_to:
            graph.setdefault(feature.id,set()).add(other);graph.setdefault(other,set()).add(feature.id)
    queue=[(0,start,-1)];seen=set()
    while queue:
        turns,node,last=heapq.heappop(queue)
        if (node,last) in seen:continue
        seen.add((node,last))
        if node==end:return turns
        for other in graph.get(node,()):
            axis=axes.get(other,last)
            heapq.heappush(queue,(turns+int(last>=0 and axis!=last),other,axis))
    raise AssertionError('Required terminal is disconnected')


@pytest.mark.parametrize('terminals',[3,4,5])
def test_stage_b_source_window_multiple_entries(monkeypatch,tmp_path,terminals):
    d,defs=branching()
    d=Design.model_validate({**d.model_dump(), 'features':[f.model_dump() for f in d.features[:terminals]],
        'nets':[{**d.nets[0].model_dump(),'members':[]}]})
    chosen,diag=coordinate_routes(d,d.nets,defs,{}, {},label_limit=1024)
    assert chosen,diag
    result,_=verify_case(d,chosen,defs,tmp_path/'stage-b',monkeypatch,diag)
    assert len(d.nets[0].members)==terminals
    assert len({f.face for f in result.features if f.route_net})>=2
    assert len([f for f in result.features if f.route_net])>=3
    assert minimum_internal_turns(result,'CV:deep','E1')>=2
    if terminals==5:assert len({f.face for f in result.features if f.route_net})>=3


def test_stage_c_revisits_first_automatic_net(monkeypatch,tmp_path):
    d=crossing();seeds={}
    for name,face in [('P','left'),('T','front')]:
        f=Feature(id='OLD_'+name,kind='drilling',face=face,u=60,v=50,diameter=8,depth=108,circuit=name,route_net=name)
        seeds[name]=candidate([f])
    chosen,diag=coordinate_routes(d,d.nets,{}, {}, {},seeds=seeds,label_limit=256)
    assert chosen,diag
    assert chosen['P']['key']!=seeds['P']['key']
    verify_case(d,chosen,{},tmp_path/'stage-c-first',monkeypatch,diag)
    assert diag['events'][0]['nets']==['P']


def mutual_barriers():
    d=Design(name='Corridor Stage C joint release',block=dict(length=120,width=120,height=120,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id=i,kind='port',face=f,u=u,v=v,diameter=10,depth=16,tip_angle=180,circuit=n,clearance_diameter=10,clearance_height=1)
            for i,f,u,v,n in [('P1','left',21,60,'P'),('P2','right',92.5,60,'P'),('T1','front',60,21,'T'),('T2','back',60,92.5,'T')]],
        nets=[dict(id=n,routing='automatic',diameter=8) for n in ('P','T')])
    seeds={}
    for name,faces in [('P',('left','right')),('T',('front','back'))]:
        holes=[]
        for i in range(17):
            coordinate=8+6.5*i;face=faces[i%2];u,v=(coordinate,60) if name=='P' else (60,coordinate)
            functional=i in (2,13)
            holes.append(Feature(id=f'OLD_{name}_{i}',kind='drilling',face=face,u=u,v=v,diameter=8,depth=107.5,
                circuit=name,route_net=name,plugged=not functional))
        seeds[name]=candidate(bind_route(d,holes))
    return d,seeds


def test_stage_c_joint_release_when_individual_corridors_are_blocked(monkeypatch,tmp_path):
    d,seeds=mutual_barriers()
    for n in d.nets:
        # Real, individually source-safe and connected existing cut networks.
        assert routing._verify_route_candidate(d,n,seeds[n.id],routing._ProposalSnapshot(d,{}, {}, {}),prune=False),seeds[n.id].get('conflicts')
        other=[f for key,o in seeds.items() if key!=n.id for f in o['route']]
        options,detail=plan_net(d,n,{}, {}, {},reserved=other,label_limit=256)
        assert not options and detail['classification']=='RESERVED_CORRIDOR_BARRIER',detail
    chosen,diag=coordinate_routes(d,d.nets,{}, {}, {},seeds=seeds,label_limit=512)
    assert chosen,diag
    assert all(chosen[n]['key']!=seeds[n]['key'] for n in seeds)
    assert any(len(e['nets'])==2 for e in diag['events'] if e['action']=='RIP_UP')
    verify_case(d,chosen,{},tmp_path/'stage-c-joint',monkeypatch,diag)


def test_candidate_batch_is_resumable_and_budget_failure_is_not_space_impossibility():
    from manifold.routing_space import network_key
    d=crossing();n=d.nets[0]
    first,detail=plan_net(d,n,{}, {}, {},label_limit=64,alternatives=1)
    assert first
    later,other=plan_net(d,n,{}, {}, {},label_limit=128,alternatives=1,forbidden=[network_key(first[0]['route'])])
    assert later and network_key(later[0]['route'])!=network_key(first[0]['route'])
    assert later[0]['route'][0].face!=first[0]['route'][0].face
    chosen,limited=coordinate_routes(d,d.nets,{}, {}, {},label_limit=64,state_limit=1)
    assert not chosen and limited['classification']=='CANDIDATE_TRUNCATION'
    assert any(row['state']=='COORDINATION_BUDGET_DEFERRED' for row in limited['deferred'])
    assert limited['exact_admitted']>0
    assert len(limited['search_history'])==limited['search_count']
    assert limited['search_history'][0]['lifecycle'][0]['generated_drillings']


def test_initial_four_geometry_batch_does_not_hide_later_entry():
    from manifold.routing_space import network_key
    d=crossing();n=d.nets[0]
    first,detail=plan_net(d,n,{}, {}, {},label_limit=512,alternatives=4)
    assert len(first)==4
    later,other=plan_net(d,n,{}, {}, {},label_limit=1024,alternatives=1,
        forbidden=[network_key(o['route']) for o in first])
    assert later and all(network_key(later[0]['route'])!=network_key(o['route']) for o in first)
    snapshot=routing._ProposalSnapshot(d,{}, {}, {})
    assert routing._verify_route_candidate(d,n,later[0],snapshot)
    assert other['lifecycle'][0]['state']=='ANALYTIC_SCREENED_NOT_EXACT'
