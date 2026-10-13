"""Dependency and alternative-constraint checks used by complex AI search."""
from manifold.schema import Design,Feature
from manifold.ai_design.route_catalog import Session,Catalog,terminal_key,cut_locations,geometry_key
from manifold.ai_design.design_space import LayoutDomain
from manifold.ai_design.route_feedback import _combined_actions
from manifold.routing import simple_routes


def source():
    return Design(name='QA cache world dependencies',block=dict(length=100,width=100,height=30,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id=n+face,kind='port',face=face,u=50,v=12,
        diameter=12,depth=12,tip_angle=180,circuit=n,clearance_diameter=12,clearance_height=1)
        for n,faces in [('A',('left','right')),('B',('front','back'))] for face in faces],
        nets=[dict(id=n,routing='automatic',diameter=8) for n in ('A','B')])


def test_unrelated_stock_growth_keeps_world_unchanged_route_but_invalidates_pair_proof():
    d=source();net=d.nets[0];tools=[dict(diameter_mm=8,max_depth_mm=200)]
    route=simple_routes(d,net,{},include_detours=False)[0]
    session=Session();session.context=session.source_context(d,{}, {},{})
    session.seed_combination(d,{'A':dict(key='retained',route=route)})
    session.pair_evidence={('obsolete',):frozenset()}
    changed=d.model_copy(deep=True);changed.block.height+=20
    assert terminal_key(d,net)==terminal_key(changed,changed.nets[0])
    session.prepare(changed,{'A':changed.nets[0]}, {},{},{},tools)
    assert session.invalidated and not session.pair_evidence
    assert session.catalogs['A'].reused
    assert any(geometry_key(o['route'])==geometry_key(route) for o in session.catalogs['A'].clear)
    assert not any(o.get('connection_verified') for o in session.catalogs['A'].clear)


def test_opposite_entry_or_terminal_motion_changes_cache_dependencies():
    d=source();changed=d.model_copy(deep=True);changed.block.length+=20
    route=[Feature(id='R',kind='drilling',face='right',u=50,v=12,depth=50,diameter=8,
                   circuit='A',route_net='A')]
    assert terminal_key(d,d.nets[0])!=terminal_key(changed,changed.nets[0])
    assert cut_locations(d,route)!=cut_locations(changed,route)


def test_mutually_exclusive_candidate_constraints_keep_separate_measured_actions():
    d=source();domain=LayoutDomain.new_generation(d,{f.id for f in d.features},dimension_axes=(2,),
                                                  fixed_faces={f.id:f.face for f in d.features})
    retained=Feature(id='RB',kind='drilling',face='front',u=50,v=12,depth=90,diameter=8,
        circuit='B',route_net='B',tip_angle=180)
    witnesses=[]
    for key,z in [('first',12),('second',13)]:
        a=Feature(id='RA',kind='drilling',face='left',u=50,v=z,depth=90,diameter=8,
            circuit='A',route_net='A',tip_angle=180)
        witnesses.append(dict(nets=['A','B'],missing_net='A',candidate=key,
                              features=[a.model_dump(),retained.model_dump()]))
    actions=list(_combined_actions(d,witnesses,{},domain,{},{}))
    deltas={round(reason['delta_mm'],2) for _,_,reason in actions if reason['owners']==['Aleft','Aright']}
    assert {9.01,10.01}<=deltas


def test_linked_source_poses_are_only_a_new_value_and_never_copy_routes():
    from manifold.ai_design.initialization import linked_source_seed
    linked=source()
    for f in linked.features:f.schematic_id=f.id
    target=linked.model_copy(deep=True)
    for f in target.features:f.id='NEW_'+f.id;f.v+=1
    linked.features.append(Feature(id='OLD_CUT',kind='drilling',face='left',u=50,v=12,diameter=8,depth=90,route_net='A',circuit='A'))
    original=linked.model_dump_json();authored=target.model_dump_json()
    seed=linked_source_seed(target,linked)
    assert seed is not None and all(f.id.startswith('NEW_') and f.v==12 for f in seed.features)
    assert linked.model_dump_json()==original and target.model_dump_json()==authored
    locked=LayoutDomain.new_generation(target,{f.id for f in target.features},dimension_axes=(),
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in target.features})
    assert not locked.accepts(target,seed)


def test_duplicate_inner_generation_yields_a_counted_checkpoint(monkeypatch):
    from manifold.ai_design import joint_routes
    from manifold.ai_design.joint_routes import corridor_alternatives
    from manifold import routing
    d=source();net=d.nets[0];route=simple_routes(d,net,{},include_detours=False)[0];calls=[]
    def regenerate(*args,**kwargs):calls.append(1);return route
    monkeypatch.setattr(routing,'route_from_variant',regenerate)
    monkeypatch.setattr(joint_routes,'entry_alternatives',lambda *args:iter(()))
    base=dict(key='branch_0_50_50_12:xyz:nearest',route=route)
    stream=corridor_alternatives(d,net,[base],[],{},{},{},[dict(diameter_mm=8,max_depth_mm=200)],{},
                                excluded={geometry_key(route)},allow_bypass=False)
    result=next(stream)
    assert result['checkpoint']=='DUPLICATE_GEOMETRY' and len(calls)==1
    assert 'route' not in result  # Scheduling evidence cannot enter admission.
