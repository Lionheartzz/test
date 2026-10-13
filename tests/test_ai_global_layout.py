"""Shared-window pose and operation-budget checks; never CAD certification."""
import itertools
from manifold.schema import Design,CavityDefinition
from manifold.ai_design.design_space import LayoutDomain,source_conflicts,fit_violations
from manifold.ai_design.coupled_layout import actions,interfaces,coupling_groups
from manifold.ai_design.layout_resources import RefinementSchedule


def coupled():
    zones=[dict(id=n,start=0,end=12,diameter=8,offset_u=u,offset_v=v) for n,u,v in [('a',-12,0),('b',12,0),('c',0,20)]]
    definition=CavityDefinition(id='QA_SHARED',label='QA multi-window source',stages=[dict(start=0,end=12,diameter=1)],
        zones=zones,cutting_primitives=[dict(kind='cylinder',start=0,end=12,diameter=8,offset_u=z['offset_u'],offset_v=z['offset_v']) for z in zones],
        clearance_diameter=60,clearance_height=4)
    d=Design(name='QA overlapping hydraulic hyperedges',block=dict(length=160,width=160,height=100,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id=k,kind='cavity',face='top',u=x,v=y,cavity_id=definition.id,
        interface_nets={'a':'A','b':'B','c':'C'}) for k,x,y in [('S1',50,50),('S2',110,110)]],
        nets=[dict(id=n,routing='automatic',diameter=8) for n in ('A','B','C')])
    return d,{definition.id:definition}


def test_shared_owners_generate_rigid_joint_poses_and_cover_all_interfaces():
    d,defs=coupled();original=d.model_dump_json();physical=defs['QA_SHARED'].model_dump_json()
    a=dict(unresolved_nets=['A','B'],coordination_constraints=[])
    assert coupling_groups(d,a)
    frames=interfaces(d,defs)
    assert len(frames)==6 and all(f['source_normal'] and f['approach_normals'] for f in frames)
    domain=LayoutDomain.new_generation(d,{f.id for f in d.features})
    proposals=list(itertools.islice(actions(d,a,defs,domain,{},{}),3))
    assert proposals
    for _,target,reason in proposals:
        assert len(reason['changed_features'])>=2
        assert reason['affected_nets']==['A','B','C']
        assert len(reason['interface_frames_after'])==6
        assert domain.accepts(d,target) and not source_conflicts(target,defs,{}, {})
        assert not fit_violations(target,defs,domain)
        assert not reason['exact_verified']
    assert d.model_dump_json()==original and defs['QA_SHARED'].model_dump_json()==physical


def test_joint_pose_search_respects_all_explicit_locks():
    d,defs=coupled();domain=LayoutDomain.new_generation(d,{f.id for f in d.features},dimension_axes=(),
        fixed_faces={f.id:f.face for f in d.features},fixed_rotations={f.id:f.rotation for f in d.features},
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features})
    assert not list(actions(d,dict(unresolved_nets=['A','B']),defs,domain,{},{}))


def test_distinct_shared_groups_are_exposed_before_repeating_one_groups_poses():
    d,defs=coupled();features=[]
    for index,(x,y,names) in enumerate([(50,60,'ABC'),(120,60,'ABC'),(190,60,'ABC'),(270,220,'DEF'),(340,220,'DEF')]):
        features.append(d.features[0].model_copy(update=dict(id='S'+str(index),u=x,v=y,interface_nets=dict(zip(('a','b','c'),names)))))
    raw=d.model_dump();raw.update(block=dict(length=400,width=300,height=100,material='QA'),features=features,
        nets=[dict(id=n,routing='automatic',diameter=8) for n in 'ABCDEF'])
    d=Design.model_validate(raw);domain=LayoutDomain.new_generation(d,{f.id for f in d.features})
    first=list(itertools.islice(actions(d,dict(unresolved_nets=['A','D']),defs,domain,{},{}),2))
    assert [len(a[2]['owners']) for a in first]==[3,2]
    assert set(first[0][2]['owners']).isdisjoint(first[1][2]['owners'])


def test_window_approach_normal_influences_joint_pose_cost():
    from manifold.ai_design.coupled_layout import _error
    d,defs=coupled()
    defs['QA_SHARED']=defs['QA_SHARED'].model_copy(update=dict(zones=[z.model_copy(update=dict(start=4)) for z in defs['QA_SHARED'].zones]))
    values=[]
    for face in ('top','left'):
        target=d.model_copy(deep=True);target.features[0].face=face
        window=next(f for f in interfaces(target,defs) if f['terminal']=='S1:a')
        anchor=tuple(v+(8 if axis==0 else 0) for axis,v in enumerate(window['center']))
        values.append(_error(target,defs,{'A':anchor},{'S1'}))
    # The same X displacement aligns radially with a top staged window,
    # whereas a left staged window requires a transverse turn.
    assert values==[8,16]


def record(index,coverage,burden=(3,6),rotation=0):
    return dict(index=index,assessment=dict(status='ANALYTIC_UNVALIDATED',compatible=False),routing_scale=8,
        joint_state=dict(compatible_nets=list(range(coverage)),repair_burden=burden,exact_failures=[],
        dimensions=[100,100,100],placements=[dict(id='S',face='top',rotation=rotation)]))


def exhaust_slice(schedule,row,limits):
    before=(len(row['joint_state']['compatible_nets']),tuple(row['joint_state']['repair_burden']))
    row['assessment'].update(joint_coordination=dict(labels=limits['labels'],states=limits['states'],raw_probes=limits['probes'],samples=limits['samples']),
                             combination=dict(pair_screens=limits['pairs']))
    schedule.charge(row,before,limits)


def test_early_states_cannot_spend_reserve_and_later_better_layout_receives_depth():
    s=RefinementSchedule(2,6,24);early=[record(0,3),record(1,3,rotation=90)]
    for evaluated in (4,8):
        row,limits=s.select(early,evaluated);exhaust_slice(s,row,limits)
    assert all(s.used[k]<=s.total[k]//2 for k in s.total)
    assert s.select([*early,record(2,4)],10) is None
    late=record(3,5,burden=(1,1),rotation=180)
    chosen,limits=s.select([*early,late],16)
    assert chosen is late and all(limits[k]<=s.remaining()[k] for k in limits)
    exhaust_slice(s,late,limits)
    assert all(s.used[k]<=s.total[k] for k in s.total)
    final=record(4,6,burden=(0,0),rotation=270)
    assert s.select([*early,late,final],22) is None
    chosen,limits=s.select([*early,late,final],24)
    assert chosen is final and all(limits[k]>0 for k in limits)
    exhaust_slice(s,final,limits)
    assert all(s.used[k]==s.total[k] for k in s.total)


def test_lower_real_insertion_conflict_burden_qualifies_without_more_candidates():
    s=RefinementSchedule(2,6,24);a=record(0,4)
    chosen,limits=s.select([a],4);exhaust_slice(s,chosen,limits)
    b=record(1,4,burden=(1,2))
    chosen,_=s.select([a,b],8)
    assert chosen is b


def test_context_resume_restores_only_identical_source_geometry():
    from manifold.ai_design.route_catalog import Session
    d=Design(name='QA context dependencies',block=dict(length=100,width=100,height=60,material='QA'),
        features=[dict(id=face,kind='port',face=face,u=50,v=30,diameter=12,depth=12,circuit='A') for face in ('left','right')],
        nets=[dict(id='A',routing='automatic',diameter=8)])
    s=Session();tools=[dict(diameter_mm=8,max_depth_mm=200)]
    s.prepare(d,{'A':d.nets[0]}, {},{},{},tools)
    original=s.catalogs['A'];s.pair_evidence[('known',)]=frozenset();s.remaining=7;s.remember_context()
    changed=d.model_copy(deep=True);changed.block.height+=10
    s.prepare(changed,{'A':changed.nets[0]}, {},{},{},tools)
    assert s.invalidated and s.catalogs['A'] is not original and not s.pair_evidence
    s.remember_context();s.prepare(d,{'A':d.nets[0]}, {},{},{},tools)
    assert s.invalidated and s.catalogs['A'] is original and ('known',) in s.pair_evidence and s.remaining==7
