"""Production replays of review E1/E2/E4/E5; no substituted CAD outcomes."""
import inspect
import sys

import pytest

from manifold.schema import Design,Feature,CavityDefinition
from manifold.routing_space import MachiningSpace
from manifold.routing import _manufacturing_cuts,_cuts_too_close,_plug_cut_overlap,route_obstructions
from manifold.geometry import feature_geometry
from manifold.closure_runtime import bind_route,plug_diameter
from manifold.ai_design import coupled_layout as cl
from manifold.ai_design.design_space import LayoutDomain,source_conflicts


def beam_case():
    zones=[dict(id=n,start=0,end=20,diameter=10,offset_v=v) for n,v in [('one',-12),('two',12)]]
    definition=CavityDefinition(id='QA_REVIEW',label='QA audit only',stages=[dict(start=0,end=20,diameter=10)],zones=zones,
        cutting_primitives=[dict(kind='cylinder',start=0,end=20,diameter=10,offset_v=z['offset_v']) for z in zones],
        clearance_diameter=34,clearance_height=4)
    d=Design(name='E1 coordinate state',block=dict(length=140,width=120,height=60,material='QA'),rules=dict(minimum_wall=3),
        features=[dict(id=k,kind='cavity',face='top',u=x,v=60,cavity_id=definition.id,
            interface_nets={'one':'N1','two':'N2'}) for k,x in [('A',90),('B',40)]],
        nets=[dict(id=n,routing='automatic',diameter=8) for n in ('N1','N2')])
    domain=LayoutDomain.new_generation(d,{'A','B'},dimension_axes=(),fixed_faces={'A':'top','B':'top'},
        fixed_rotations={'A':0,'B':0},fixed_positions={'B':dict(u=40,v=60)})
    return d,{definition.id:definition},domain


def test_e1_state_equivalence_includes_coordinates_stock_constraints_and_dependencies():
    d,defs,domain=beam_case();key=cl._beam_key(d,{'A'},domain)
    for change in ('position','stock','constraint','interface','placed','lock'):
        other=d.model_copy(deep=True);placed={'A'};locks=domain
        if change=='position':other.features[0].u+=1
        if change=='stock':other.block.height+=1
        if change=='constraint':other.rules.minimum_wall+=1
        if change=='interface':other.features[0].circuits['one']='N2'
        if change=='placed':placed.add('B')
        if change=='lock':locks=LayoutDomain.new_generation(d,{'A','B'},fixed_faces={'A':'top'})
        assert cl._beam_key(other,placed,locks)!=key,change
    assert cl._beam_key(d.model_copy(deep=True),{'A'},domain)==key


def test_e1_production_beam_keeps_distinct_positions_and_checks_locked_obstacle():
    d,defs,domain=beam_case();before=d.model_dump_json();captured={}
    lines,start=inspect.getsourcelines(cl._actions)
    stop=start+next(i for i,line in enumerate(lines) if line.strip()=='beam=kept')
    class Observed(Exception):pass
    def trace(frame,event,arg):
        if frame.f_code is not cl._actions.__code__:return None
        if event=='line' and frame.f_lineno==stop:
            captured.update(expanded=frame.f_locals['expanded'],kept=frame.f_locals['kept'])
            raise Observed
        return trace
    sys.settrace(trace)
    try:
        with pytest.raises(Observed):next(cl._actions(d,dict(unresolved_nets=['N1','N2']),defs,domain,{}, {},[(['A','B'],{'N1','N2'})]))
    finally:sys.settrace(None)
    kept=captured['kept']
    assert len(kept)>1
    assert len({tuple((f.u,f.v) for f in target.features) for target,_ in kept})==len(kept)
    assert all(not source_conflicts(target,defs,{}, {}) for target,_ in kept)
    assert all(any(f.id=='B' for f in cl._forward_context(target,{'A','B'},set(),'A',domain).features) for target,_ in kept)
    assert all(not source_conflicts(target,defs,{}, {}) for _,target,_ in captured['expanded'])
    assert d.model_dump_json()==before


@pytest.mark.parametrize('world',[False,True])
def test_e1_locked_and_unowned_features_are_never_deferred(world):
    d,defs,domain=beam_case()
    if world:domain.fixed_positions['B']=dict(x=40,y=60,z=60)
    assert len(cl._forward_context(d,{'A','B'},set(),'A',domain).features)==2
    domain=LayoutDomain.new_generation(d,{'A'})
    assert len(cl._forward_context(d,{'A','B'},set(),'A',domain).features)==2


def cache_case():
    return Design(name='E2 endpoint cache',block=dict(length=120,width=100,height=100,material='QA'),rules=dict(minimum_wall=3),
        constraints=dict(forbidden_drilling_faces=['right','front','back','top','bottom']),
        features=[dict(id='P'+str(i),kind='port',face='top',u=x,v=50,diameter=10,depth=10,circuit='N') for i,x in enumerate([20,70])],
        nets=[dict(id='N',diameter=8,routing='automatic')])


@pytest.mark.parametrize('order',[(1,20),(20,1)])
def test_e2_cached_geometry_never_caches_endpoint_acceptance(order):
    d=cache_case();space=MachiningSpace(d,d.nets[0],{}, {},{})
    for x in (*order,*order):
        result=space.operations((x,50,30),(60,50,30),[])
        fresh=MachiningSpace(d,d.nets[0],{}, {},{}).operations((x,50,30),(60,50,30),[])
        assert len(result)==len(fresh)==(1 if x==20 else 0)
        assert not any(rule=='occupied_entry' for _,failures in space.actions.values() for rule,*_ in failures)
    assert space.generated==1


def test_e2_endpoint_check_uses_actual_retained_coaxial_closure():
    d=cache_case();space=MachiningSpace(d,d.nets[0],{}, {},{})
    generated=space.operations((20,50,30),(60,50,30),[])[0][0]
    existing=generated.model_copy(update=dict(id='MANUAL_CLOSURE',depth=80,plug_length=30,
        closure_definition_id=None,closure_selection_mode='manual'))
    assert not space.operations((20,50,30),(60,50,30),[existing])


def short_case(x=6):
    definition=CavityDefinition(id='QA_SHORT_WINDOW',label='QA audit geometry',stages=[dict(start=0,end=25,diameter=4)],
        zones=[dict(id='one',start=15,end=25,diameter=4)],clearance_diameter=4,clearance_height=1)
    d=Design(name='E4 short machining',block=dict(length=40,width=40,height=40,material='QA'),rules=dict(minimum_wall=3),
        constraints=dict(forbidden_drilling_faces=['right','front','back','top','bottom']),
        features=[dict(id='P',kind='port',face='left',u=20,v=20,diameter=4,depth=1,tip_angle=180,circuit='N',clearance_diameter=4,clearance_height=1),
            dict(id='C',kind='cavity',face='top',u=x,v=20,cavity_id=definition.id,interface_nets={'one':'N'})],
        nets=[dict(id='N',diameter=3,routing='automatic',route_state='proposal')])
    return d,{definition.id:definition}


def test_e4_short_cut_reaches_real_validator_and_step(tmp_path):
    from manifold.ai_design.joint_layout import exact_candidate
    d,defs=short_case();before=d.model_dump_json()
    options=MachiningSpace(d,d.nets[0],defs,{},{}).operations((1,20,20),(6,20,20),[])
    assert len(options)==1 and options[0][0].depth==7.5
    target=d.model_copy(update=dict(features=[*d.features,*options[0]]))
    folder=tmp_path/'short';folder.mkdir()
    acceptance=exact_candidate(target,defs,{}, {},folder=folder)
    assert acceptance['status']=='EXACT_FEASIBLE',acceptance['failures']
    assert acceptance['validation']['counts']['FAIL']==0
    assert acceptance['topology']['valid'] and acceptance['topology']['solids']==1
    assert acceptance['step']['status']=='PASS'
    assert d.model_dump_json()==before


@pytest.mark.parametrize('constraint',['tool','face','wall','plug','breakout','source'])
def test_e4_short_cut_still_obeys_machining_constraints(constraint):
    d,defs=short_case();kwargs={};a=(1,20,20);b=(6,20,20)
    if constraint=='tool':kwargs['tools']=[]
    if constraint=='face':d.constraints.forbidden_drilling_faces.append('left')
    if constraint=='wall':d.rules.minimum_wall=21
    if constraint=='plug':d.features=d.features[1:]
    if constraint=='breakout':b=(39,20,20)
    if constraint=='source':a=(1,20,35);b=(6,20,35)
    assert not MachiningSpace(d,d.nets[0],defs,{}, {},**kwargs).operations(a,b,[])


def proxy_case():
    d=Design(name='E5 finite machining',block=dict(length=100,width=100,height=100,material='QA'),rules=dict(minimum_wall=3),
        nets=[dict(id='N',diameter=8,routing='manual')])
    a=Feature(id='A',kind='drilling',face='left',u=50,v=50,diameter=8,depth=20,tip_angle=180,circuit='N')
    b=Feature(id='B',kind='drilling',face='front',u=26.5,v=50,diameter=8,depth=43.5,tip_angle=180,circuit='OTHER')
    return d,a,b


def test_e5_finite_endcap_gap_uses_exact_without_relaxing_wall():
    d,a,b=proxy_case();cache={}
    cuts,*_=feature_geometry(d.model_copy(update=dict(features=[a,b])),{},{},{})
    assert cuts[a.id].distance(cuts[b.id])==pytest.approx(3.5355339059)
    assert not _cuts_too_close(list(_manufacturing_cuts(a,{},{},{})),next(_manufacturing_cuts(b,{},{},{})),d.block,3,cache)
    assert not route_obstructions(d.model_copy(update=dict(features=[b])),d.nets[0],[a],{}, {},{},cache)
    # Reuse the distance under a stricter CURRENT threshold; do not cache PASS.
    assert _cuts_too_close(list(_manufacturing_cuts(a,{},{},{})),next(_manufacturing_cuts(b,{},{},{})),d.block,4,cache)
    assert cache['local_exact_evaluations']['distance']==1
    crossing=b.model_copy(update=dict(u=18,depth=60))
    assert ('cross_net_wall','A','B') in route_obstructions(d.model_copy(update=dict(features=[crossing])),d.nets[0],[a],{}, {},{},{})


def test_e5_grazing_plug_intersection_is_not_certified_safe_by_sampling():
    d,a,_=proxy_case()
    plug=bind_route(d,[a.model_copy(update=dict(id='PLUG',depth=40,tip_angle=118,plugged=True,route_net='N'))])[0]
    graze=Feature(id='GRAZE',kind='drilling',face='front',u=plug.plug_length/2,v=50+plug_diameter(plug)/2+4-.02,
        diameter=8,depth=60,tip_angle=180,circuit='N')
    cuts,_,_,_,plugs,*_=feature_geometry(d.model_copy(update=dict(features=[plug,graze])),{},{},{})
    assert plugs[plug.id].intersect(cuts[graze.id]).Volume()==pytest.approx(.005325171623)
    assert any(_plug_cut_overlap(plug,c,d.block) for c in _manufacturing_cuts(graze,{},{},{}))
    assert ('plug_cut','GRAZE','PLUG') in route_obstructions(d,d.nets[0],[plug,graze],{}, {},{},{})


def test_e5_taper_and_annular_protected_regions_follow_actual_primitives():
    d,a,b=proxy_case();cache={}
    cone=dict(feature=a,start=0,end=20,radius_start=4,radius_end=0,inner_radius=0)
    annulus=dict(feature=a,start=0,end=20,radius_start=8,radius_end=8,inner_radius=5)
    coax=dict(feature=a,start=1,end=19,radius_start=4,radius_end=4,inner_radius=0)
    assert not _cuts_too_close([coax],annulus,d.block,1,cache)
    assert _cuts_too_close([coax],annulus,d.block,1.1,cache)
    near=dict(feature=b.model_copy(update=dict(u=22,depth=47)),start=0,end=47,radius_start=4,radius_end=4,inner_radius=0)
    from manifold.machining_predicates import cut_shape
    actual=cut_shape(cone,d.block,cache).distance(cut_shape(near,d.block,cache))
    assert not _cuts_too_close([cone],near,d.block,max(0,actual-.01),cache)
    assert _cuts_too_close([cone],near,d.block,actual+.01,cache)


def test_e5_uncertain_is_not_safe_and_failed_cad_never_supplies_clearance():
    from manifold.machining_predicates import bounds_state,ContactState,exact_state
    from manifold.cad import cq
    from manifold.cad_geometry import GeometryEvaluationError
    box=((0,1),)*3
    assert bounds_state(box,box,0)==ContactState.EXACT_REQUIRED
    valid=cq.Solid.makeBox(1,1,1)
    invalid=valid.copy();invalid.wrapped.Nullify()
    with pytest.raises(GeometryEvaluationError):
        exact_state('invalid',invalid,'valid',valid,3,{})


def test_e5_external_port_access_uses_source_envelope_not_feature_defaults():
    d,a,_=proxy_case()
    definition=CavityDefinition(id='QA_PORT',label='QA source installation',kind='external-port',
        stages=[dict(start=0,end=3,diameter=4)],zones=[dict(id='entry',start=0,end=3,diameter=4)],
        clearance_diameter=60,clearance_height=5)
    port=Feature(id='PORT',kind='port',face='left',u=65,v=50,port_definition_id=definition.id,circuit='OTHER')
    plug=bind_route(d,[a.model_copy(update=dict(id='PLUG',u=40,depth=40,plugged=True,route_net='N'))])[0]
    failures=route_obstructions(d.model_copy(update=dict(features=[port])),d.nets[0],[plug],{}, {definition.id:definition},{},{})
    assert ('installation_access','PLUG','PORT') in failures
