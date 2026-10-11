"""Analytic samples are diagnostics; only explicit actions release old samples."""
import pytest
from test_ai_design import client,create,HEADERS
from test_ai_coordinated_layout import four_ports
from manifold import store
from manifold.ai_design import generation,service,layout_search
from manifold.routing import resolve_design


@pytest.mark.parametrize('compatible',[False,True])
def test_new_layout_never_pins_analytic_samples(monkeypatch,compatible):
    d=four_ports();before=d.model_dump_json()
    baseline=dict(score=(3,),feasibility_score=(3,),conflicts=[],blocked_nets=['N'])
    assessed=dict(score=(0,),feasibility_score=(0,),conflicts=[] if compatible else [('cross_net_wall','one','two')],
        blocked_nets=[],selected={'N':'branch_0_50_50_50:xyz:nearest'},compatible=compatible,witnesses=[])
    monkeypatch.setattr(layout_search,'assess',lambda *a,**k:baseline)
    monkeypatch.setattr(layout_search,'_columns',lambda *a,**k:(d.model_copy(deep=True),{'N':50},50))
    monkeypatch.setattr(layout_search,'screen',lambda *a,**k:assessed)
    monkeypatch.setattr(layout_search,'_children',lambda *a,**k:[])
    result=layout_search.plan_new(d,{},movable_features={f.id for f in d.features},growth_axes=(0,1,2))
    assert result['proposals'][0]['design']['nets'][0]['routing_variant'] is None
    assert result['proposals'][0]['assessment']['selected']==assessed['selected']
    assert d.model_dump_json()==before


def test_explicit_pin_blocks_ai_rearrangement_and_survives_common_router(monkeypatch):
    d=four_ports();d.nets[0].routing_variant='xyz:nearest:direct';before=d.model_dump_json()
    monkeypatch.setattr(layout_search,'assess',lambda *a,**k:dict(score=(0,),feasibility_score=(0,),conflicts=[],blocked_nets=[]))
    def forbidden(*a,**k):raise AssertionError('Explicit pin must not enter AI layout adaptation')
    monkeypatch.setattr(layout_search,'_columns',forbidden)
    result=layout_search.plan_new(d,{},movable_features={f.id for f in d.features},growth_axes=(0,1,2))
    assert result['proposals']==[] and d.model_dump_json()==before
    target,routes=resolve_design(d,exact=False)
    assert routes[0]['variant']=='xyz:nearest:direct'
    assert target.block==d.block
    assert [(f.id,f.face,f.u,f.v) for f in target.features if f.kind=='port']==[(f.id,f.face,f.u,f.v) for f in d.features]


def owned_packet(client):
    task=create(client);key=task['id'];gid='d'*32;d=four_ports()
    d.nets[0].routing_variant='branch_0_50_50_50:xyz:nearest'
    packet=dict(id=gid,task_id=key,design=d.model_dump(),route_status='NOT_ROUTED_NOT_VALIDATED',validation=None,attempts=[],
        layout_planning=dict(scope='AI_GENERATION_ONLY',selected=dict(status='ANALYTIC_UNVALIDATED',compatible=False,
            selected={'N':d.nets[0].routing_variant})))
    path=store.OUTPUT/'ai-design'/key/'generations'/gid/'generation.json';store.atomic_json(path,packet)
    return key,gid,d,packet,path


def test_recovery_api_returns_copy_and_preserves_original_and_revision(client):
    key,gid,d,packet,path=owned_packet(client);before=path.read_bytes();source=d.model_dump_json()
    response=client.post(f'/api/ai-design/tasks/{key}/generations/{gid}/recover-analytic-routes',json=d.model_dump(),headers=HEADERS)
    assert response.status_code==200,response.text
    recovered=response.json();assert recovered['design']['nets'][0]['routing_variant'] is None
    assert recovered['design']['features']==d.model_dump(mode='json')['features'] and recovered['design']['block']==d.model_dump(mode='json')['block']
    assert d.model_dump_json()==source and path.read_bytes()==before
    modified=d.model_copy(deep=True);modified.features[0].u+=1
    response=client.post(f'/api/ai-design/tasks/{key}/generations/{gid}/recover-analytic-routes',json=modified.model_dump(),headers=HEADERS)
    assert response.status_code==422 and path.read_bytes()==before
    downloaded=client.get(f'/api/ai-design/tasks/{key}/generations/{gid}/project?release_analytic_samples=true')
    assert downloaded.status_code==200 and downloaded.json()['nets'][0]['routing_variant'] is None
    assert path.read_bytes()==before


@pytest.mark.parametrize('case',['user_pin','manual','committed','frozen','origin_only'])
def test_recovery_refuses_unproven_or_fixed_choices(client,case):
    key,gid,d,packet,path=owned_packet(client)
    if case=='user_pin':d.nets[0].routing_variant='xyz:nearest:direct'
    elif case=='manual':d.nets[0].routing='manual'
    elif case=='committed':d.nets[0].route_state='committed'
    elif case=='frozen':d.features[0].frozen_net='N'
    elif case=='origin_only':packet['layout_planning']={};d.origin.method='ai-assisted'
    packet['design']=d.model_dump();store.atomic_json(path,packet);before=path.read_bytes()
    response=client.post(f'/api/ai-design/tasks/{key}/generations/{gid}/recover-analytic-routes',json=d.model_dump(),headers=HEADERS)
    assert response.status_code==422,response.text
    assert path.read_bytes()==before


def test_frontier_ranks_quality_then_keeps_diverse_families_independent_of_append_order(monkeypatch):
    entries=[]
    for name,family,score in [('bad-rotation','rotation',9),('best-plane','plane',0),('second-plane','plane',1),('good-entry','entry',2)]:
        d=four_ports();d.name=name
        entries.append(dict(family=family,candidate=(d,{'N':50},50),parent={'feasibility_score':(3,)}))
    scores={'bad-rotation':9,'best-plane':0,'second-plane':1,'good-entry':2}
    monkeypatch.setattr(layout_search,'_scout',lambda e,*args:(scores[e['candidate'][0].name],))
    for ordered in (entries,list(reversed(entries))):
        selected=layout_search._rank_frontier(ordered,{}, {}, {},{})
        assert [e['candidate'][0].name for e in selected]==['best-plane','good-entry']
    assert all(e['candidate'][0].nets[0].routing_variant is None for e in entries)


def test_fresh_unpinned_draft_invokes_complete_global_router(monkeypatch):
    from manifold.schema import Design
    import manifold.routing as routing
    d=Design.model_validate(dict(name='Fresh global handoff',block=dict(length=100,width=100,height=100,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id=f'E{i}{j}',kind='port',face=face,u=position,v=position,
            diameter=12,depth=16,circuit=f'N{i}') for i,position in enumerate((20,50,80)) for j,face in enumerate(('left','right'))],
        nets=[dict(id=f'N{i}',routing='automatic',diameter=8) for i in range(3)]))
    before=d.model_dump_json();calls=[];original=routing._complete_route_combination
    def observe(*args,**kwargs):calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(routing,'_complete_route_combination',observe)
    target,routes=routing.resolve_design(d,exact=False)
    assert calls and all(r['connection_verified'] for r in routes)
    assert target.block==d.block and d.model_dump_json()==before


def test_shared_branch_family_is_bounded_regenerable_and_does_not_pin():
    from manifold.branch_candidates import terminal_branch_candidates
    from manifold.routing import route_from_variant
    d=four_ports();before=d.model_dump_json()
    options=list(terminal_branch_candidates(d,d.nets[0],{}, {}, {}))
    assert 1<=len(options)<=12
    for key,route in options:
        assert key.startswith('branch_')
        assert [f.model_dump() for f in route_from_variant(d,d.nets[0],key,{}, {}, {})]==[f.model_dump() for f in route]
    assert d.model_dump_json()==before
    from manifold.routing import port_approach_candidates
    assert list(port_approach_candidates(d,d.nets[0],[dict(key=key,route=route,risk=0) for key,route in options],{}, {}, {}))==[]


def test_parallel_branch_entries_use_compatible_opposite_faces():
    from manifold.schema import Design
    from manifold.routing import propose,route_obstructions,_verify_route_candidate,_ProposalSnapshot
    d=Design.model_validate(dict(name='Parallel branch access',block=dict(length=120,width=120,height=100,material='QA'),
        rules=dict(minimum_wall=.5),features=[dict(id=key,kind='port',face=face,u=u,v=v,diameter=8,depth=20,
            circuit='N',clearance_diameter=8,clearance_height=1) for key,face,u,v in
            [('P1','front',30,40),('P2','front',38,48.8),('P3','back',90,80)]],
        nets=[dict(id='N',routing='automatic',diameter=8)]))
    before=d.model_dump_json();n=d.nets[0]
    route=propose(d,n,(1,0,2),definitions={},entry_safe=True,thread_definitions={},modifier_definitions={},junction_override=(80,80,70))
    parallel=[f for f in route if f.face in ('left','right') and abs(f.u-80)<1e-7 and f.v in (40,48.8)]
    assert {f.face for f in parallel}=={'left','right'}
    assert not route_obstructions(d,n,route,{}, {}, {})
    option=dict(key='test',route=route,risk=0);_verify_route_candidate(d,n,option,_ProposalSnapshot(d,{}, {}, {}))
    assert option['connection_verified'] and d.model_dump_json()==before


def face_open_source():
    from manifold.schema import CavityDefinition,Design
    definition=CavityDefinition(id='QA_FACE',label='Test face-open source windows',
        stages=[dict(start=0,end=30,diameter=12)],
        cutting_primitives=[dict(source_ref=name,kind='cylinder',start=0,end=end,diameter=diameter,offset_u=u,offset_v=v)
            for name,end,diameter,u,v in [('A',30,12,-15,0),('B',30,12,15,20),('bolt-left',18,4,-25,0),('bolt-right',18,4,-5,0)]],
        zones=[dict(id='A',start=0,end=30,diameter=12,offset_u=-15,clip_to_cut=True),
               dict(id='B',start=0,end=30,diameter=12,offset_u=15,offset_v=20,clip_to_cut=True)],
        clearance_diameter=64,clearance_height=12)
    d=Design(name='Offset face-open turn',block=dict(length=120,width=120,height=100,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id='CV',kind='cavity',face='front',u=60,v=50,cavity_id=definition.id,interface_nets={'A':'N','B':'M'}),
            dict(id='EXT',kind='port',face='left',u=85,v=65,diameter=10,depth=20,circuit='N')],
        nets=[dict(id='N',routing='automatic',diameter=8),dict(id='M',routing='manual',diameter=8)])
    return d,{definition.id:definition}


def test_face_open_turn_preserves_offset_and_proves_real_connection_behind_bolt_machining():
    from manifold.branch_candidates import face_window_points
    from manifold.routing import route_from_variant,route_obstructions,_verify_route_candidate,_ProposalSnapshot
    d,defs=face_open_source();n=d.nets[0];before=d.model_dump_json()
    point=face_window_points(d,n,defs,{}, {})['CV:A']
    assert point==pytest.approx((45,25.9,50))
    midpoint=route_from_variant(d,n,'branch_0_80_85_65:xyz:nearest',defs,{}, {})
    assert any(f[0] in ('source_protected','source_wall') for f in route_obstructions(d,n,midpoint,{},defs,{}))
    key='window:branch_0_80_85_65:yxz:nearest'
    route=route_from_variant(d,n,key,defs,{}, {})
    assert not route_obstructions(d,n,route,{},defs,{})
    option=dict(key=key,route=route,risk=0)
    assert _verify_route_candidate(d,n,option,_ProposalSnapshot(d,defs,{},{}))
    assert option['connection_verified'] and d.model_dump_json()==before


def test_face_open_turn_uses_pose_rotation_and_rejects_interrupted_source_core():
    from manifold.branch_candidates import face_window_points
    from manifold.schema import CuttingPrimitive
    d,defs=face_open_source();source=d.features[0];source.face='right';source.u=80;source.v=70;source.rotation=90
    assert face_window_points(d,d.nets[0],defs,{}, {})['CV:A']==pytest.approx((94.1,80,55))
    definition=defs[source.definition]
    # Nominal window metadata cannot override a real uncut land.
    definition.cutting_primitives[0].end=10
    definition.cutting_primitives.append(CuttingPrimitive(source_ref='after-land',kind='cylinder',start=12,end=30,diameter=12,offset_u=-15))
    assert not face_window_points(d,d.nets[0],defs,{}, {})
    d,defs=face_open_source();defs[d.features[0].definition].zones[0].start=1
    assert not face_window_points(d,d.nets[0],defs,{}, {})
