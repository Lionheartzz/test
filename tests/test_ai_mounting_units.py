"""Source numeric units for AI mounting intent stay separate from thread identity."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from manifold.ai_design.intent import mounting_from_intent, reconcile_mounting
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
