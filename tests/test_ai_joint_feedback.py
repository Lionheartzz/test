"""Small general machining cases, not vendor/manufacturing certification."""
from manifold.schema import Design, Feature
from manifold.ai_design import joint_layout
from manifold.ai_design.layout_search import screen
from manifold.ai_design.route_catalog import Session, Catalog
from manifold.ai_design.route_feedback import measured_actions, exact_witnesses
from manifold.ai_design.design_space import LayoutDomain
from manifold.ai_design.joint_state import capture, rank
from manifold.routing import simple_routes


TOOLS=[dict(diameter_mm=8,max_depth_mm=200)]


def crossed():
    return Design(name='QA complete-cut spatial feedback',
        block=dict(length=100,width=100,height=20,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id=n+f,kind='port',face=f,u=50,v=10,diameter=12,depth=12,tip_angle=180,
                       circuit=n,clearance_diameter=12,clearance_height=1)
                  for n,faces in [('A',('left','right')),('B',('front','back'))] for f in faces],
        nets=[dict(id=n,routing='automatic',diameter=8) for n in ('A','B')])


def direct_screen(design):
    # Supply real shared-Router coaxial cuts to the real source/pair screen.
    # Freeze candidate enumeration only, so the layout feedback is exercised
    # without an unrelated large fixed-layout corridor search.
    session=Session();session.context=session.source_context(design,{}, {},{})
    session._prepared_once=True;session.remaining=0
    for net in design.nets:
        c=Catalog(design,net,{}, {},{},TOOLS,{})
        routes=simple_routes(design,net,{},include_detours=False)
        c.accept('qa-direct',routes[0] if routes else None,'simple')
        assert not any(o['connection_verified'] for o in c.clear)
        session.catalogs[net.id]=c
    return screen(design,{}, {},{},TOOLS,{}, {},include_routes=True,general_families=True,
                  corridor_labels=0,route_session=session)


def row(design,a,index=0):
    return dict(index=index,design=design.model_dump(),assessment=a,joint_state=capture(design,a,{}))


def test_real_pair_failure_reaches_joint_layout_and_requires_growth_and_joint_motion(tmp_path):
    d=crossed();original=d.model_dump_json();before=direct_screen(d)
    assert not before['compatible'] and len(before['partial_routing']['nets'])==1
    assert before['diagnostic_combination']['conflicts']
    assert before['coordination_constraints'][0]['evidence']=='CURRENT_COMPATIBLE_CORE_INSERTION'
    assert len({f['route_net'] for f in before['route_features']})==1
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features},dimension_axes=(2,),
                                       fixed_faces={f.id:f.face for f in d.features})
    options=[]
    for _,candidate,reason in measured_actions(d,before,{},domain,{},{}):
        # The existing source machining permits neither a shallower separation
        # nor a legal fixed-stock coaxial solution. Both terminals must move.
        if len(reason.get('owners',[]))<2:continue
        after=direct_screen(candidate)
        if after['compatible']:options.append(row(candidate,after,len(options)+1))
    assert options
    selected=min([row(d,before),*options],key=rank)
    assert selected['joint_state']['unresolved_nets']==[]
    candidate=Design.model_validate(selected['design'])
    assert candidate.block.height>d.block.height
    changed=[f.id for f,g in zip(candidate.features,d.features) if f!=g]
    assert len(changed)==2
    assert domain.accepts(d,candidate) and d.model_dump_json()==original
    candidate.features.extend(Feature.model_validate(f) for f in selected['assessment']['route_features'])
    for net in candidate.nets:net.route_state='proposal'
    result=joint_layout.exact_candidate(candidate,{}, {},{},folder=tmp_path)
    assert result['status']=='EXACT_FEASIBLE',result.get('failures')
    assert result['validation']['counts']['FAIL']==0
    assert result['topology']==dict(valid=True,solids=1)
    assert result['step']['status']=='PASS'


def test_diagnostic_incompatible_combination_cannot_improve_layout_rank():
    d=crossed();a=direct_screen(d);b={**a,'diagnostic_combination':dict(conflicts=[['cross_net_wall']]*100),
                                 'score':(999,)*8,'feasibility_score':(999,)}
    assert rank(row(d,a))==rank(row(d,b))


def test_explicit_locks_stop_autonomous_feedback():
    d=crossed();a=direct_screen(d)
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features},dimension_axes=(),
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features},
        fixed_faces={f.id:f.face for f in d.features},fixed_rotations={f.id:f.rotation for f in d.features})
    assert not list(measured_actions(d,a,{},domain,{},{}))


def test_source_interference_expands_a_motion_cluster_and_rechecks_third_net():
    d=crossed();d.block.height=60
    added=[f.model_copy(update=dict(id='C'+f.face,circuit='C',v=26)) for f in d.features if f.circuit=='A']
    d=Design.model_validate({**d.model_dump(),'features':d.features+added,
        'nets':d.nets+[dict(id='C',routing='automatic',diameter=8)]})
    assessment=direct_screen(d)
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features},dimension_axes=(),fixed_faces={f.id:f.face for f in d.features})
    choices=[]
    for _,candidate,reason in measured_actions(d,assessment,{},domain,{},{}):
        if set(reason.get('owners',[]))>={'Aleft','Aright','Cleft','Cright'}:
            after=direct_screen(candidate)
            if after['compatible']:choices.append(candidate)
    assert choices  # All three complete machining routes, not just the pair.


def test_exact_rejection_is_attributed_to_real_cuts_and_returns_layout_actions():
    d=crossed();a=direct_screen(d)
    cuts=[]
    for net in d.nets:cuts+=simple_routes(d,net,{},include_detours=False)[0]
    context=d.model_copy(update=dict(features=d.features+cuts))
    constraints,spatial=exact_witnesses(context,[dict(rule='circuit_intersection',items=['A','B'],actual=1)],{}, {},{})
    assert constraints and constraints[0]['evidence']=='EXACT_REJECTION'
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features},dimension_axes=(2,),fixed_faces={f.id:f.face for f in d.features})
    assert next(measured_actions(d,dict(coordination_constraints=constraints,spatial_feedback=spatial),{},domain,{},{}))


def test_repeated_core_remembering_keeps_different_compatible_arrangements():
    d=crossed();session=Session();session.context=session.source_context(d,{}, {},{})
    a=direct_screen(d)['route_features']
    option=dict(key='one',route=[Feature.model_validate(f) for f in a])
    name=option['route'][0].route_net
    alternate={**option,'route':[f.model_copy(update=dict(v=f.v+1)) for f in option['route']]}
    session.seed_combination(d,{name:option});session.seed_combination(d,{name:alternate})
    for _ in range(10):session.seed_combination(d,{name:option})
    assert len(session.combinations)==2


def test_optimizer_uses_refined_failure_for_next_layout_and_real_exact(monkeypatch,tmp_path):
    from manifold.ai_design import layout_search,initialization
    d=crossed();original=d.model_dump_json()
    # Restrict enumeration to one real strategy per Net. Source protection,
    # pair screening, feedback, optimizer and final engineering gates are real.
    monkeypatch.setattr(layout_search,'screen',lambda target,*args,**kw:direct_screen(target))
    monkeypatch.setattr(layout_search,'_columns',lambda *args:None)
    monkeypatch.setattr(initialization,'initial_candidates',lambda *args:iter(()))
    monkeypatch.setattr(joint_layout,'actions',lambda *args:iter(()))
    observed=[];real_feedback=initialization.route_feedback
    def feedback(target,assessment,*args):
        observed.append(assessment)
        # Scheduling adversary: only the refined diagnostic generates actions.
        return real_feedback(target,assessment,*args) if assessment.get('routing_refinement') else iter(())
    monkeypatch.setattr(initialization,'route_feedback',feedback)
    monkeypatch.setattr(joint_layout,'run_exact',lambda target,defs,threads,modifiers,**kw:
        joint_layout.exact_candidate(target,defs,threads,modifiers,folder=kw.get('folder')))
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features},dimension_axes=(2,),
        fixed_faces={f.id:f.face for f in d.features})
    result=joint_layout.optimize(d,{},domain,layout_limit=8,exact_limit=1,evidence_dir=tmp_path)
    assert result['status']=='EXACT_FEASIBLE',result['attempts']
    assert result['counters']['stalled_route_refinements']==1
    assert any(a.get('routing_refinement') and a['coordination_constraints'] for a in observed)
    assert any(e['family'].startswith('feedback-') and not e['joint_state']['unresolved_nets'] for e in result['evaluations'])
    assert result['validation']['counts']['FAIL']==0
    assert d.model_dump_json()==original
