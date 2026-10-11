"""Focused topology/strategy/ownership tests with the real shared Router."""
from manifold.schema import Design
from manifold.routing import (propose, route_from_variant, select_route_combination,
                               _ProposalSnapshot, _verify_route_candidate)


def four_ports():
    return Design.model_validate(dict(name='Four terminal branch',block=dict(length=100,width=100,height=100,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id=f'E{i}',kind='port',face=face,u=u,v=v,diameter=12,depth=16,circuit='N')
          for i,(face,u,v) in enumerate([('left',25,35),('right',75,65),('front',65,25),('back',35,75)])],
        nets=[dict(id='N',routing='automatic',diameter=8)]))


def test_fourth_root_and_explicit_junction_connect_every_terminal_without_moving_sources():
    d=four_ports();n=d.nets[0];before=d.model_dump_json()
    root=propose(d,n,(0,1,2),definitions={},connection_topology=4)
    assert root and d.model_dump_json()==before
    key='branch_0_50.123456_55.654321_60.246810:xyz:nearest'
    route=route_from_variant(d,n,key,{}, {}, {})
    assert route and any(abs(f.u-50.123456)<1e-9 and abs(f.v-55.654321)<1e-9 for f in route)
    option=dict(key=key,route=route,risk=0)
    _verify_route_candidate(d,n,option,_ProposalSnapshot(d,{}, {}, {}))
    assert option['connection_verified'],option.get('connectivity_detail')
    assert d.model_dump_json()==before


def test_combination_search_backtracks_and_does_not_upgrade_analytic_connectivity():
    d=four_ports();a=d.nets[0];b=a.model_copy(update=dict(id='OTHER'))
    one=propose(d,a,(0,1,2),definitions={})
    pools={'N':[dict(key='preferred',route=one,risk=0),dict(key='compatible',route=one,risk=0)],
           'OTHER':[dict(key='only',route=one,risk=0)]}
    chosen,diagnostic=select_route_combination(d,{'N':a,'OTHER':b},pools,{},
        lambda x,xo,y,yo:{('cross_net_wall','real_cut','other_cut')} if 'preferred' in (xo['key'],yo['key']) else set())
    assert chosen['N']['key']=='compatible' and diagnostic['states']<=1000
    assert all('connection_verified' not in o for o in chosen.values())


def test_branch_entry_faces_do_not_change_with_mutable_net_iteration_order():
    from manifold.schema import Feature
    d=four_ports();key='branch_0_50.123456_55.654321_60.246810:xyz:nearest'
    before=route_from_variant(d,d.nets[0],key,{}, {}, {})
    d.nets.append(d.nets[0].model_copy(update=dict(id='OTHER',members=[],route_state='unresolved')))
    other=Feature(id='OTHER_CUT',kind='drilling',face='left',u=25,v=35,diameter=12,depth=60,circuit='OTHER',route_net='OTHER')
    d.features.append(other)
    after=route_from_variant(d,d.nets[0],key,{}, {}, {})
    assert [f.model_dump() for f in after]==[f.model_dump() for f in before]
    assert d.features[-1]==other


def test_ai_column_family_cannot_move_authored_or_frozen_cuts():
    from manifold.ai_design.layout_search import _columns
    from manifold.layout_planning import _permissions
    from test_ai_topology_placement_admission import layout_fixture
    d,defs=layout_fixture();before=d.model_dump_json();movable,_=_permissions(d)
    assert _columns(d,defs,movable,(),{}) is None
    assert d.model_dump_json()==before


def test_offset_staged_cavity_does_not_become_a_transverse_mounting_pattern():
    from manifold.ai_design.layout_search import _distributed_openings
    from test_ai_topology_placement_admission import layout_fixture
    _,definitions=layout_fixture();definition=next(iter(definitions.values()))
    zone=definition.zones[0]
    staged=definition.model_copy(update=dict(zones=[zone,zone.model_copy(update=dict(id='offset',start=40,end=50,offset_u=20))]))
    assert not _distributed_openings(staged)


def test_preparation_keeps_full_connector_instead_of_near_tangent_shortcut():
    from manifold.schema import Feature
    from manifold.routing import prune_branch_connectors
    d=Design.model_validate(dict(name='Near tangent branch',block=dict(length=100,width=100,height=100,material='QA'),
        rules=dict(minimum_wall=2,minimum_overlap_volume=.1),features=[
          dict(id='E1',kind='port',face='front',u=40,v=40,diameter=8,depth=20,circuit='N'),
          dict(id='E2',kind='port',face='front',u=47.95,v=80,diameter=8,depth=20,circuit='N')],
        nets=[dict(id='N',routing='automatic',diameter=8)]))
    cuts=[('Y1','front',40,40,60),('Y2','front',47.95,80,60),('Z1','bottom',40,56,84),
          ('Z2','bottom',47.95,56,84),('FULL_BRIDGE','left',56,60,51.95)]
    route=[Feature(id=key,kind='drilling',face=face,u=u,v=v,depth=depth,diameter=8,circuit='N',route_net='N',plugged=True) for key,face,u,v,depth in cuts]
    kept=prune_branch_connectors(d,d.nets[0],route,{}, {}, {})
    assert 'FULL_BRIDGE' in {f.id for f in kept}
    option=dict(key='test',route=kept,risk=0)
    _verify_route_candidate(d,d.nets[0],option,_ProposalSnapshot(d,{}, {}, {}))
    assert option['connection_verified'],option.get('connectivity_detail')
