"""Focused regressions for AI route sampling and conflict-driven placement."""
from manifold.schema import Design,CavityDefinition,Feature
from manifold.ai_design import design_space
from manifold.ai_design.design_space import LayoutDomain
from manifold.ai_design.route_feedback import obstruction_witnesses,measured_actions
from manifold.ai_design.route_catalog import Session


def sources():
    definition=CavityDefinition(id='QA_CORE',label='QA machining, not vendor data',
        stages=[dict(start=0,end=30,diameter=12)],zones=[dict(id='port1',start=18,end=30,diameter=12)],
        clearance_diameter=16,clearance_height=4)
    design=Design(name='QA joint backtracking',block=dict(length=80,width=80,height=60,material='QA'),
        rules=dict(minimum_wall=2),features=[
            dict(id='CV',kind='cavity',face='top',u=20,v=20,cavity_id=definition.id,interface_nets={'port1':'P'}),
            dict(id='P0',kind='port',face='left',u=20,v=40,diameter=12,depth=32,tip_angle=180,circuit='P',clearance_diameter=14,clearance_height=1)],
        nets=[dict(id='P',routing='automatic',diameter=8)])
    return design,{definition.id:definition}


def test_joint_pack_keeps_earlier_choice_until_late_cross_face_port_fits(monkeypatch):
    design,defs=sources();before=design.model_dump_json()
    domain=LayoutDomain.new_generation(design,{'CV','P0'},dimension_axes=(),fixed_faces={'CV':'top','P0':'left'})
    def positions(context,feature,*args):
        if feature.id=='CV':
            yield feature
            yield feature.model_copy(update=dict(u=60))
        else:yield feature
    monkeypatch.setattr(design_space,'anchored',positions)
    result=design_space.pack_topology(design,defs,domain,{},{} )
    assert result is not None
    assert next(f for f in result.features if f.id=='CV').u==60
    assert not design_space.source_conflicts(result,defs,{},{} )
    assert domain._packing_diagnostics['dead_ends']>0
    assert domain._packing_diagnostics['probes']<=domain._packing_diagnostics['probe_limit']
    assert design.model_dump_json()==before


def test_failed_cut_drives_measured_owned_motion_without_changing_source_definition():
    design,defs=sources();definition=defs['QA_CORE'].model_dump_json()
    bore=Feature(id='R-QA',kind='drilling',face='left',u=20,v=40,diameter=8,depth=35,circuit='Q',route_net='Q',tip_angle=180)
    net=design.nets[0].model_copy(update=dict(id='Q',members=['P0','OTHER:port1']))
    witness=obstruction_witnesses(design,{'Q':net},{'Q':dict(rejected_samples=[dict(variant='xyz:nearest:direct',
        features=[bore.model_dump()],failures=[('source_wall','CV',bore.id)])])},defs,{},{} )
    assert witness and witness[0]['contact_location']
    # Give the route its actual Net for the layout action, no physical admission.
    design=design.model_copy(update=dict(nets=[net]))
    domain=LayoutDomain.new_generation(design,{'CV'},dimension_axes=(),fixed_faces={'CV':'top'})
    actions=list(measured_actions(design,dict(spatial_feedback=witness),defs,domain,{},{}))
    assert actions
    for _,candidate,reason in actions:
        assert domain.accepts(design,candidate)
        assert reason['delta_mm'] and reason['requires_route_regeneration']
        assert next(f for f in candidate.features if f.id=='P0')==design.features[1]
    assert defs['QA_CORE'].model_dump_json()==definition


def test_ai_sample_tokens_are_reassigned_not_cut_off_at_32(monkeypatch):
    # Scheduling adversary only: no mocked candidate is called engineering-safe.
    from manifold.ai_design import route_catalog
    design,_=sources()
    nets={n:design.nets[0].model_copy(update=dict(id=n,members=['CV:port1','P0'])) for n in ('hard','easy')}
    class Stream:
        def __init__(self,source,net,*args):self.net=net;self.clear=[];self.attempts=0;self.queues=[1];self.refinements=[];self.seed_queue=[]
        def step(self):
            self.attempts+=1
            if self.net.id=='easy' or self.attempts==40:self.clear.append(dict(key=str(self.attempts)))
            return True
        def active(self):return self.clear
    monkeypatch.setattr(route_catalog,'Catalog',Stream)
    session=Session();session.prepare(design,nets,{}, {},{},[])
    session.coordinate(design,[]);pools={n:c.active() for n,c in session.catalogs.items()}
    assert any(o['key']=='40' for o in pools['hard'])
    assert sum(c.attempts for c in session.catalogs.values())==64
    assert session.catalogs['hard'].attempts>32


def test_model_simple_route_default_and_ai_opt_in_are_separate():
    import inspect
    from manifold.routing import simple_routes
    design,defs=sources()
    assert inspect.signature(simple_routes).parameters['include_detours'].default is True
    from manifold.branch_candidates import terminal_branch_candidates
    assert inspect.signature(terminal_branch_candidates).parameters['diverse'].default is False
    # Exercise the opt-in on real source cuts. It must not alter input geometry.
    before=design.model_dump_json()
    routes=simple_routes(design,design.nets[0],defs,include_detours=False)
    assert all(f.kind=='drilling' for route in routes for f in route)
    assert design.model_dump_json()==before


def test_explicit_analytic_cuts_still_require_real_exact_connectivity():
    from manifold.ai_design.joint_layout import exact_candidate
    design,defs=sources()
    design.features[0].u=60
    design.features.append(Feature(id='R-DISCONNECTED',kind='drilling',face='front',u=40,v=15,
        diameter=8,depth=20,circuit='P',route_net='P',tip_angle=180))
    design.nets[0].route_state='proposal'
    result=exact_candidate(design,defs,{},{} )
    assert result['status']=='EXACT_ROUTING_REJECTED'
    assert result['validation'] is None and not result['full_cad_evaluated']
    assert result['failures']


def test_retained_partial_cut_is_rescreened_against_a_moved_obstacle():
    from manifold.ai_design.route_catalog import Catalog,terminal_key
    from manifold.engineering_db import tool_definitions
    design,defs=sources()
    design.features[0].u=40
    design.features[1].u=40
    other=design.features[1].model_copy(update=dict(id='P1',face='right'))
    design.features.append(other);design.nets[0].members=['P0','P1']
    bore=Feature(id='R-RETAINED',kind='drilling',face='left',u=40,v=40,
        diameter=8,depth=70,circuit='P',route_net='P',tip_angle=180)
    original=Catalog(design,design.nets[0],defs,{}, {},tool_definitions('drill'),{})
    original.accept('explicit-retained', [bore], 'retained')
    assert original.clear
    moved=design.model_copy(deep=True);moved.features[0].v=40
    assert terminal_key(design,design.nets[0])==terminal_key(moved,moved.nets[0])
    replay=Catalog(moved,moved.nets[0],defs,{}, {},tool_definitions('drill'),{},original.clear)
    replay.step()
    assert replay.reused==1 and not replay.clear
    assert not replay.refinements  # Explicit cached geometry is not a variant grammar.
    assert any(f[0] in ('source_protected','source_wall') and 'CV' in f for f in replay.rejected[0]['failures'])


def test_shared_multiport_owners_are_not_lost_by_net_set_subtraction():
    design,defs=sources()
    definition=CavityDefinition(id='QA_TWO',label='QA two separate windows',stages=[dict(start=0,end=30,diameter=12)],
        zones=[dict(id='a',start=4,end=12,diameter=12),dict(id='b',start=20,end=30,diameter=12)],
        clearance_diameter=16,clearance_height=4)
    defs={definition.id:definition}
    design.features=[Feature(id=k,kind='cavity',face='top',u=x,v=20,cavity_id=definition.id,interface_nets={'a':'A','b':'B'})
                     for k,x in [('C1',20),('C2',60)]]
    design.nets=[design.nets[0].model_copy(update=dict(id=n,members=['C1:'+z,'C2:'+z])) for n,z in [('A','a'),('B','b')]]
    a=Feature(id='RA',kind='drilling',face='left',u=20,v=40,diameter=8,depth=60,circuit='A',route_net='A',tip_angle=180)
    b=Feature(id='RB',kind='drilling',face='top',u=40,v=20,diameter=8,depth=30,circuit='B',route_net='B',tip_angle=180)
    assessment=dict(witnesses=[dict(features=[f.model_dump() for f in (a,b)],nets=['A','B'])])
    domain=LayoutDomain.new_generation(design,{'C1','C2'},dimension_axes=())
    actions=list(measured_actions(design,assessment,defs,domain,{},{}))
    assert any(reason.get('shared_interface') and reason['from_face']!=reason['to_face'] for _,_,reason in actions)
    locked=LayoutDomain.new_generation(design,{'C1','C2'},dimension_axes=(),fixed_faces={'C1':'top','C2':'top'})
    assert all(all(f.face=='top' for f in candidate.features) for _,candidate,_ in measured_actions(design,assessment,defs,locked,{},{}))
    locked=LayoutDomain.new_generation(design,{'C1','C2'},dimension_axes=(),
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in design.features})
    assert not list(measured_actions(design,assessment,defs,locked,{},{}))


def test_shallow_generated_plug_is_rejected_without_aborting_feedback():
    from manifold.ai_design.route_catalog import Catalog
    from manifold.engineering_db import tool_definitions
    design,defs=sources()
    bore=Feature(id='R-SHALLOW',kind='drilling',face='front',u=40,v=40,diameter=8,depth=12,
        circuit='P',route_net='P',plugged=True).model_copy(update=dict(depth=9,plug_length=10))
    catalog=Catalog(design,design.nets[0],defs,{}, {},tool_definitions('drill'),{})
    catalog.accept('xyz:nearest:direct',[bore],'direct')
    assert not catalog.clear
    assert ('invalid_machining',bore.id) in catalog.rejected[0]['failures']
    detail=catalog.diagnostics([])
    # Invalid generated machining remains a rejection, not a crash or PASS.
    obstruction_witnesses(design,{'P':design.nets[0]},{'P':detail},defs,{},{} )


def test_compatibility_promoted_partial_gets_a_reuse_slot():
    from manifold.ai_design.route_catalog import Catalog,terminal_key,geometry_key
    design,defs=sources()
    catalog=Catalog(design,design.nets[0],defs,{}, {},[],{})
    catalog.clear=[dict(key='diagnostic-'+str(i),route=[Feature(id='R-'+str(i),kind='drilling',face='front',
        u=20+i*2,v=10,depth=20,diameter=8,circuit='P',route_net='P',tip_angle=180)],
        failures=set(),connection_verified=False) for i in range(9)]
    session=Session();session.catalogs={'P':catalog}
    session.remember(design,{'P':catalog.clear[-1]})
    retained=session.previous[terminal_key(design,design.nets[0])]
    assert retained[0]['key']=='diagnostic-8' and len(retained)<=8
    assert not any(o['connection_verified'] for o in retained)
    f=catalog.clear[0]['route'][0]
    assert geometry_key([f])!=geometry_key([f.model_copy(update=dict(plug_length=11))])
