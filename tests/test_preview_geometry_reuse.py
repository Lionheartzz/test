"""Request-local exact pruning reuse, using the observed T-10A design."""
from manifold import geometry, routing, validation
from manifold.cad_worker import dispatch
from test_routing_obstacles import observed, signature
from test_routing_priorities import straight_net, drilling


def test_real_preview_has_one_shared_source_and_one_final_build_including_stored_variants(monkeypatch):
    design,definitions=observed()
    from manifold import engineering_db
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    builds=[];original=geometry.build_geometry
    def measured(d,*args,**kwargs):
        builds.append(sum(bool(f.route_net) for f in d.features))
        return original(d,*args,**kwargs)
    monkeypatch.setattr(geometry,'build_geometry',measured)
    def forbidden(*args,**kwargs):
        raise AssertionError('Transient preview must not Validate')
    monkeypatch.setattr(validation,'validate',forbidden)
    proposals=[]
    before=design.model_dump()
    result=dispatch('preview-solid',design.model_dump(),proposal_ready=proposals.append)
    assert builds==[0,14]
    assert result['status']=='UNVALIDATED_EXACT_GEOMETRY'
    routes=proposals[0]['routes']
    assert [(r['net'],r['variant'],r['pruned_drillings']) for r in routes]==[
        ('A','yzx:nearest:offset_y_m',['R-559aead0-3']),
        ('B','xzy:nearest:offset_x_p',['R-df7e70e5-1']),
        ('P','yzx:nearest:offset_y_p',[]),
        ('T','axial_1_0:yxz:nearest',[])]
    resolved=proposals[0]['design']
    for net in design.nets:
        net.routing_variant=next(r['variant'] for r in routes if r['net']==net.id)
    pinned=dispatch('preview-solid',design.model_dump())
    assert builds==[0,14,0,14]  # New snapshot; no cross-request CAD cache.
    from manifold.schema import Design
    assert signature(Design.model_validate({**resolved,'features':pinned['features']}))==signature(Design.model_validate(resolved))
    for net in design.nets:net.routing_variant=None
    assert design.model_dump()==before


def test_same_snapshot_reuses_exact_pruning_but_preserves_new_declared_contacts(monkeypatch):
    design=straight_net();net=design.nets[0]
    route=[drilling('LONG','left',106),drilling('SHORT','left',60),drilling('DEAD','front',65,plugged=True)]
    snapshot=routing._ProposalSnapshot(design,{}, {}, {})
    calls=[];original=routing.simplify_generated_route
    def measured(*args,**kwargs):
        calls.append(1)
        return original(*args,**kwargs)
    monkeypatch.setattr(routing,'simplify_generated_route',measured)
    first,connected=snapshot.simplify(design,net,route)
    assert connected and [f.id for f in first]==['LONG']
    first[0].depth=1  # Cached records do not share mutable proposal objects.
    second,_=snapshot.simplify(design,net,[f.model_copy(deep=True) for f in route])
    assert len(calls)==1 and second[0].depth==106
    design.features[0].connects_to=['SHORT']
    third,_=snapshot.simplify(design,net,route)
    assert len(calls)==2 and {f.id for f in third}=={'LONG','SHORT'}


def test_resolution_cache_is_keyed_by_entire_draft_snapshot(monkeypatch):
    design=straight_net();design.nets[0].routing_variant='xyz:nearest:direct'
    snapshots={};builds=[];original=geometry.build_geometry
    def measured(d,*args,**kwargs):
        builds.append(d.features[0].u)
        return original(d,*args,**kwargs)
    monkeypatch.setattr(geometry,'build_geometry',measured)
    first,_=routing._resolve_proposals(design,snapshots=snapshots)
    repeated,_=routing._resolve_proposals(design,snapshots=snapshots)
    assert signature(first)==signature(repeated) and builds==[60]
    moved=design.model_copy(deep=True);moved.features[0].u=61
    routing._resolve_proposals(moved,snapshots=snapshots)
    assert builds==[60,61] and len(snapshots)==2


def test_candidate_budget_uses_cheap_rank_before_exact_pruning(monkeypatch):
    design=straight_net();design.constraints.priority='short_drills';net=design.nets[0]
    routes=[[drilling(f'R{i}','left',40+i)] for i in range(40)]
    monkeypatch.setattr(routing,'simple_routes',lambda *_:list(reversed(routes)))
    monkeypatch.setattr(routing,'propose',lambda *_:routes[-1])
    monkeypatch.setattr(routing,'route_obstructions',lambda d,n,r,*a: {('blocked',r[0].id)} if r[0].id=='R0' else set())
    inspected=[]
    def simplify(d,n,r,**kwargs):
        inspected.append(r[0].id)
        return r,True
    monkeypatch.setattr(routing,'simplify_generated_route',simplify)
    choices=routing.route_options(design,net,definitions={},thread_definitions={},modifier_definitions={})
    assert inspected==[f'R{i}' for i in range(1,17)]
    assert choices[0]['route'][0].id=='R1'
    assert choices[-1]['hard_failures']==1
