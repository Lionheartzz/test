"""Source numeric units for AI mounting intent stay separate from thread identity."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from manifold.ai_design.intent import interpret, mounting_from_intent, reconcile_mounting
from manifold.ai_design.models import MountingRequirement
from manifold.schema import Design


def hole(requirement_id, designation, u, v, depth, thread_depth):
    return dict(hole=SimpleNamespace(requirement_id=requirement_id, face='top', through=False,
                                     u=u, v=v, depth=depth, thread_depth=thread_depth),
                thread={'display_name': designation})


def reconcile(requirement, holes, intent_id='I1'):
    row=dict(intent_id=intent_id, mounting=deepcopy(requirement), status='review_required')
    blocked=reconcile_mounting([row], holes)
    return row, blocked


def sourced(quote, **mounting):
    intent=dict(id='I1',claim_id='K1',category='mounting',property='threaded_hole',
                operator='equal',strength='requirement',target_labels=[],mounting=mounting)
    result=dict(ports=[],components=[],nets=[],design_intent=[intent],
                claims=[dict(id='K1',evidence_ids=['E1'])],evidence=[dict(id='E1',quote=quote)])
    return result,intent


def test_inch_source_unit_and_unc_identity_are_preserved_from_literal_quote():
    quote='4 × 3/8-16 UNC, position 1.0 in, thread depth 0.5 in'
    result={'claims':[{'id':'K1','evidence_ids':['E1']}],
            'evidence':[{'id':'E1','quote':quote}]}
    intent={'claim_id':'K1','mounting':{'count':4,'thread_designation':'3/8-16 UNC',
                                      'positions':[(1.0,1.0)],'thread_depth':0.5}}
    parsed=mounting_from_intent(result,intent)
    assert parsed['numeric_unit']=='in'
    assert parsed['thread_designation']=='3/8-16 UNC'
    assert parsed['thread_depth']==0.5
    assert MountingRequirement.model_validate(parsed).numeric_unit=='in'
    assert 'numeric_unit' not in mounting_from_intent({'claims':[], 'evidence':[]},intent)


def test_inch_positions_and_both_depths_reconcile_in_mm_without_renaming_thread():
    positions=[(1,1),(2,1),(1,2),(2,2)]
    requirement=dict(count=4,thread_designation='3/8-16 UNC',thread_family='UNC',
                     face='top',positions=positions,numeric_unit='in',drill_depth=.75,thread_depth=.5)
    holes=[hole('I1','3/8-16 UNC-2B',u*25.4,v*25.4,19.05,12.7) for u,v in positions]
    row,blocked=reconcile(requirement,holes)
    assert row['status']=='applied' and not blocked
    assert row['mounting']['thread_designation']=='3/8-16 UNC'
    assert holes[0]['hole'].u==25.4 and holes[0]['hole'].thread_depth==12.7
    moved=deepcopy(holes)
    moved[0]['hole'].u+=1
    assert reconcile(requirement,moved)[0]['status']=='conflict'
    shallow=deepcopy(holes)
    shallow[0]['hole'].thread_depth=11.7
    assert reconcile(requirement,shallow)[0]['status']=='conflict'


def test_metric_and_inch_mounting_requirements_coexist_in_metric_project():
    inch=dict(intent_id='I1',mounting=dict(count=1,thread_designation='3/8-16 UNC',numeric_unit='in',
                                           positions=[(1,1)],thread_depth=.5),status='review_required')
    metric=dict(intent_id='I2',mounting=dict(count=1,thread_designation='M10x1.5-6H',numeric_unit='mm',
                                             positions=[(50,50)],thread_depth=16),status='review_required')
    holes=[hole('I1','3/8-16 UNC-2B',25.4,25.4,20,12.7),
           hole('I2','M10x1.5-6H',50,50,20,16)]
    assert reconcile_mounting([inch,metric],holes)==[]
    assert [inch['status'],metric['status']]==['applied','applied']
    design=Design(name='Mixed mounting standards',project_context='metric',
                  block=dict(length=100,width=100,height=60,material='QA'),features=[
                      dict(id='MH1',kind='mounting',face='top',u=25.4,v=25.4,mounting_mode='threaded',
                           thread_definition_id='UNC',thread_depth=12.7,depth=20),
                      dict(id='MH2',kind='mounting',face='top',u=50,v=50,mounting_mode='threaded',
                           thread_definition_id='METRIC',thread_depth=16,depth=20)])
    assert [feature.u for feature in design.features]==[25.4,50]


def test_legacy_missing_numeric_unit_keeps_mm_comparison_and_mixed_units_block():
    legacy=MountingRequirement.model_validate(dict(count=1,thread_designation='3/8-16 UNC',
                                                     positions=[(1,1)],thread_depth=.5))
    assert legacy.numeric_unit is None
    row,blocked=reconcile(legacy.model_dump(exclude_none=True),[hole('I1','3/8-16 UNC-2B',1,1,20,.5)])
    assert row['status']=='applied' and not blocked
    row,blocked=reconcile(legacy.model_dump(exclude_none=True),[hole('I1','3/8-16 UNC-2B',25.4,25.4,20,12.7)])
    assert row['status']=='conflict' and blocked
    quote='Position 1.0 in, thread depth 12 mm for 3/8-16 UNC'
    result={'claims':[{'id':'K1','evidence_ids':['E1']}], 'evidence':[{'id':'E1','quote':quote}]}
    mixed=mounting_from_intent(result,{'claim_id':'K1','mounting':{'count':1,'positions':[(1,1)],'thread_depth':12}})
    assert mixed['numeric_unit']=='mixed'
    row,blocked=reconcile(mixed,[hole('I1','3/8-16 UNC-2B',25.4,25.4,20,12)])
    assert row['status']=='review_required' and blocked


def test_quote_mark_inch_keeps_thread_identity_and_converts_position_and_depth():
    result,intent=sourced('1 × 3/8-16 UNC, position U 1.0", V 1.0", thread depth 0.5"',
                          count=1,thread_designation='3/8-16 UNC',positions=[(1.0,1.0)],thread_depth=.5)
    parsed=mounting_from_intent(result,intent)
    assert parsed['numeric_unit']=='in'
    assert parsed['thread_designation']=='3/8-16 UNC'
    assert parsed['positions']==[(1.0,1.0)] and parsed['thread_depth']==.5
    row,blocked=reconcile(parsed,[hole('I1','3/8-16 UNC-2B',25.4,25.4,20,12.7)])
    assert row['status']=='applied' and not blocked


@pytest.mark.parametrize(('literal','inches'),[
    ('1 in',1),('1.0 IN',1),('.5 in',.5),('1 inch',1),('1 inches',1),
    ('1"',1),('1.0"',1),('1″',1),('1/2 in',.5),('3/8 in',.375),
    ('1-1/2 in',1.5),('1 1/2 in',1.5),('1/2″',.5),
])
def test_imperial_depth_literals_match_structured_decimal(literal,inches):
    result,intent=sourced(f'1 × 3/8-16 UNC, thread depth {literal}',
                          count=1,thread_designation='3/8-16 UNC',thread_depth=inches)
    parsed=mounting_from_intent(result,intent)
    assert parsed['numeric_unit']=='in' and parsed['thread_depth']==inches
    row,blocked=reconcile(parsed,[hole('I1','3/8-16 UNC-2B',20,20,40,inches*25.4)])
    assert row['status']=='applied' and not blocked


@pytest.mark.parametrize(('literal','millimetres'),[('12 mm',12),('12.5 MM',12.5)])
def test_metric_depth_literals_remain_metric(literal,millimetres):
    result,intent=sourced(f'1 × M10x1.5-6H, thread depth {literal}',
                          count=1,thread_designation='M10x1.5-6H',thread_depth=millimetres)
    parsed=mounting_from_intent(result,intent)
    assert parsed['numeric_unit']=='mm' and parsed['thread_depth']==millimetres


def test_fractional_drill_and_thread_depths_both_reconcile_in_millimetres():
    result,intent=sourced('1 × 3/8-16 UNC, drill depth 3/4 in, thread depth 1/2 in',
                          count=1,thread_designation='3/8-16 UNC',drill_depth=.75,thread_depth=.5)
    parsed=mounting_from_intent(result,intent)
    row,blocked=reconcile(parsed,[hole('I1','3/8-16 UNC-2B',20,20,19.05,12.7)])
    assert parsed['numeric_unit']=='in' and row['status']=='applied' and not blocked


def test_thread_fraction_is_not_a_measurement_or_an_inferred_numeric_unit():
    result,intent=sourced('4 × 3/8-16 UNC',count=4,thread_designation='3/8-16 UNC',
                          positions=[(.375,.375)],thread_depth=.375)
    parsed=mounting_from_intent(result,intent)
    assert 'numeric_unit' not in parsed and parsed['thread_designation']=='3/8-16 UNC'
    settings=interpret(result,SimpleNamespace(port_faces={},component_faces={}))
    row=settings['mounting_requirements'][0]
    assert set(row['_source_unverified'])=={'positions','thread_depth'}
    blocked=reconcile_mounting([row],[hole('I1','3/8-16 UNC-2B',.375,.375,20,.375)]*4)
    assert row['status']=='review_required' and blocked
    assert '_source_unverified' not in row


@pytest.mark.parametrize('literal',['3/8-16 UNC','3/8"-16 UNC','3/8″-16 UNC','3/8 in-16 UNC'])
def test_quoted_thread_size_does_not_supply_mounting_numeric_unit(literal):
    result,intent=sourced(f'1 × {literal}',count=1,thread_designation='3/8-16 UNC')
    parsed=mounting_from_intent(result,intent)
    assert parsed['thread_designation']=='3/8-16 UNC'
    assert parsed['thread_family']=='UNC'
    assert 'numeric_unit' not in parsed


def test_one_source_position_number_cannot_justify_two_coordinates():
    result,_=sourced('1 × 3/8-16 UNC, position 1 in',count=1,
                     thread_designation='3/8-16 UNC',positions=[(1,1)])
    row=interpret(result,SimpleNamespace(port_faces={},component_faces={}))['mounting_requirements'][0]
    assert row['_source_unverified']==['positions']
    assert reconcile_mounting([row],[hole('I1','3/8-16 UNC-2B',25.4,25.4,20,10)])
    assert row['status']=='review_required'


def test_unverified_structured_depth_is_retained_for_review_not_silently_applied():
    result,_=sourced('1 × 3/8-16 UNC, position 0.5 in, thread depth 3/8 in',
                     count=1,thread_designation='3/8-16 UNC',thread_depth=.5)
    row=interpret(result,SimpleNamespace(port_faces={},component_faces={}))['mounting_requirements'][0]
    assert row['mounting']['thread_depth']==.5
    assert row['_source_unverified']==['thread_depth']
    blocked=reconcile_mounting([row],[hole('I1','3/8-16 UNC-2B',20,20,30,12.7)])
    assert row['status']=='review_required' and blocked


def test_fractional_inch_depth_conflicts_with_ten_millimetre_resolved_hole():
    result,intent=sourced('1 × 3/8-16 UNC, thread depth 1/2 in',
                          count=1,thread_designation='3/8-16 UNC',thread_depth=.5)
    parsed=mounting_from_intent(result,intent)
    row,blocked=reconcile(parsed,[hole('I1','3/8-16 UNC-2B',20,20,30,10)])
    assert row['status']=='conflict' and blocked
