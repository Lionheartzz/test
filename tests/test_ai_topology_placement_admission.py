"""Compilation and source placement boundaries; no provider or CAD build."""
import copy

from manifold.ai_design.generation import topology_issues
from manifold.schema import Design,CavityDefinition
from manifold.layout import placement_conflicts,source_safe_port_positions,initial_placement


def test_single_terminal_name_is_not_a_connection_or_an_internal_pilot():
    result=dict(components=[dict(id='C1',label='Valve')],
        ports=[dict(id='P1',component_id='C1',label='3',disposition='connected',facts={})],
        nets=[dict(id='N1',label='Pilot',members=['P1'],status='uncertain')])
    original=copy.deepcopy(result)
    issues=topology_issues(result)
    assert [(i['code'],i['port_id'],i['net_id']) for i in issues]==[('single_terminal_net','P1','N1')]
    assert result==original  # The unresolved net and its physical port survive.
    result['ports'].append(dict(id='EXT',component_id=None,label='Real pilot port',facts={}))
    result['nets'][0]['members'].append('EXT')
    assert topology_issues(result)==[]


def test_supported_termination_and_source_assignment_conflict_are_distinct():
    result=dict(components=[],ports=[dict(id='A',component_id=None,label='A',facts={'net_assignment':'A'}),
        dict(id='B',component_id=None,label='B',facts={}),
        dict(id='UNUSED',component_id=None,label='Unused',disposition='terminated',facts={})],
        nets=[dict(id='N1',label='B',members=['A','B'])])
    assert [i['code'] for i in topology_issues(result)]==['net_evidence_conflict']
    assert topology_issues(result,overrides={'A'})==[]
    result['ports'][0]['reviewed_net_label']='B'
    assert topology_issues(result)==[]  # Persisted explicit correction also wins.
    result['ports'][0]['reviewed_net_label']='A-B'
    result['nets'][0]['label']='AB'
    assert topology_issues(result)[0]['code']=='net_evidence_conflict'


def layout_fixture():
    definition=CavityDefinition.model_validate(dict(id='source_test',label='Source offset machining',
        zones=[dict(id='one',start=20,end=30,diameter=16)],
        stages=[dict(start=0,end=30,diameter=16)],
        cutting_primitives=[dict(kind='cylinder',start=0,end=30,diameter=16,offset_u=4)],
        clearance_diameter=24,clearance_height=10))
    design=Design.model_validate(dict(name='Ownership test',block=dict(length=80,width=80,height=80,material='Aluminum'),
        rules=dict(minimum_wall=3),features=[
            dict(id='C',kind='cavity',cavity_id=definition.id,face='top',u=60,v=40,interface_nets={'one':'P'}),
            dict(id='E',kind='port',face='right',u=40,v=60,diameter=12,depth=5,tip_angle=118,circuit='P')]))
    return design,{definition.id:definition}


def test_cross_face_source_offsets_and_drill_tip_are_screened():
    design,definitions=layout_fixture();port=design.features[1]
    assert placement_conflicts(design,port,definitions,{}, {})==['C']
    # The cylinder stops before the source machining; the point extends into it.
    short=port.model_copy(update=dict(tip_angle=180))
    assert placement_conflicts(design,short,definitions,{}, {})==[]
    away=port.model_copy(update=dict(u=20))
    assert placement_conflicts(design,away,definitions,{}, {})==[]


def test_safe_port_proposals_do_not_move_saved_geometry():
    design,definitions=layout_fixture();before=design.model_dump_json()
    point=next(source_safe_port_positions(design,design.features[1],definitions,{},{}))
    assert point!=(design.features[1].u,design.features[1].v)
    probe=design.features[1].model_copy(update=dict(u=point[0],v=point[1]))
    assert not placement_conflicts(design,probe,definitions,{}, {})
    assert design.model_dump_json()==before


def test_existing_manual_initial_placement_does_not_opt_into_ai_screen(monkeypatch):
    design,definitions=layout_fixture()
    def forbidden(*args,**kwargs):raise AssertionError('AI source placement must be explicit')
    monkeypatch.setattr('manifold.layout.placement_conflicts',forbidden)
    initial_placement(design,definitions,plan_routes=False)


def test_explicit_port_layout_proposal_retains_other_authored_geometry():
    from manifold.layout_planning import alternatives
    design,definitions=layout_fixture()
    design.nets[0].routing='automatic'
    before=design.model_dump_json()
    baseline=dict(blocked_nets=[],conflicts=[['source_wall','C','E']],fixed_conflicts=[['source_wall','C','E']])
    reason,target=next(alternatives(design,definitions,baseline,allow_growth=False,movable_features={'E'}))
    assert reason=='Separate external entry machining from source cuts'
    assert target.features[0]==design.features[0]
    assert target.block==design.block
    assert (target.features[1].u,target.features[1].v)!=(design.features[1].u,design.features[1].v)
    assert design.model_dump_json()==before
