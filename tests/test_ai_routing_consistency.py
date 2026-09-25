"""Focused checks for source requirements and exact external-port routing."""
import copy

import pytest

from manifold.demo import CAVITY_ID
from manifold.schema import Design
from manifold.engineering_db import search_threads, thread_semantics
from manifold.import_mdtools import thread_record
from manifold.ai_design import generation
from manifold.ai_design.generation_models import GenerationOptions
from manifold.ai_design.intent import reconcile_mounting
from manifold.ai_design.library_resolution import exact_port_candidates, port_standard
from manifold.ai_design.models import TaskInput
from manifold.geometry import build_geometry
from manifold.routing import resolve_design, authorize_generated_contacts
from manifold.validation import validate


def test_existing_external_port_is_open_exact_terminal_after_move():
    port_id='cav_4b8ba46ae1ccb0e430e4'
    for u,v in ((123,66),(123,78)):
        design=Design(name='B port route',block=dict(length=160,width=150,height=150,material='QA'),features=[
            dict(id='CV2',kind='cavity',cavity_id=CAVITY_ID,face='top',u=123,v=60,
                 interface_nets={'port1':'T','port2':'B'}),
            dict(id='B',kind='port',port_definition_id=port_id,face='front',u=u,v=v,circuit='B')],
            nets=[dict(id='B',routing='automatic',diameter=8),dict(id='T',routing='manual',diameter=8)])
        resolved,_=resolve_design(design,exact=False)
        routes=[f for f in resolved.features if f.route_net=='B']
        assert routes and any(f.face=='front' and f.u==u and f.v==v and not f.plugged for f in routes)
        geometry=build_geometry(resolved)
        assert geometry.production.isValid()
        authorize_generated_contacts(resolved,geometry)
        report=validate(resolved,geometry)
        b_connection=next(c for c in report['checks'] if c['rule']=='connected_interface' and c['items']==['B'])
        b_connectivity=next(c for c in report['checks'] if c['rule']=='circuit_connectivity' and c['items'][0]=='B')
        assert b_connection['status']=='PASS' and b_connection['actual']>=1
        assert b_connectivity['status']=='PASS' and b_connectivity['actual']==b_connectivity['required']
        assert any(f.plugged for f in routes)
        failed=[c for c in report['checks'] if c['status']=='FAIL' and
                (c['rule'] in ('connected_interface','circuit_connectivity','port_protected_region','minimum_feature_wall','unintended_cut_intersection')) and
                ('B' in c.get('items',[]) or c.get('net')=='B')]
        assert not failed,failed


def test_mounting_requirement_is_reconciled_by_count_thread_and_position():
    m10=next(row for row in search_threads('M10x1.5',usable_only=True,limit=200) if row['display_name']=='M10x1.5-6H')
    m12=next(row for row in search_threads('M12x1.75',usable_only=True,limit=200) if row['display_name']=='M12x1.75-6H')
    def hole(thread,x):
        from manifold.ai_design.generation_models import ThreadedMountingHole
        return dict(hole=ThreadedMountingHole(thread_definition_id=thread['id'],face='top',u=x,v=20,depth=20,thread_depth=16),thread=thread)
    source=dict(intent_id='I1',mounting=dict(count=4,thread_family='Metric',thread_designation='M10x1.5-6H'),status='review_required')
    cases=[([hole(m10,x) for x in (20,40,60,80)],'applied'),
           ([hole(m12,20)],'conflict'),([], 'review_required'),
           ([hole(m10,x) for x in (20,40,60)],'partially_applied')]
    for holes,status in cases:
        row=copy.deepcopy(source)
        blocked=reconcile_mounting([row],holes)
        assert row['status']==status
        assert bool(blocked)==(status!='applied')


def test_port_families_and_thread_forms_use_exact_source_identity():
    inputs=TaskInput(title='port standards')
    for specification,standard in [('G1/4 BSPP','BSPP'),('1/4 BSPP','BSPP'),('1/4-18 NPT','NPT'),
                                    ('1/4-18 NPTF','NPTF'),('SAE ORB #6','SAE_ORB'),
                                    ('M18x1.5 ISO 6149','ISO_6149')]:
        assert port_standard(specification)[0]==standard
        assert exact_port_candidates(inputs,specification)
    assert port_standard('SAE J518 Code 61')[0]=='SAE_J518'
    assert not exact_port_candidates(inputs,'SAE J518 Code 61')
    for name,tapered in [('G1/4',0),('Rp1/4',0),('R1/4',1),('Rc1/4',1),
                         ('1/4-18 NPT',1),('1/4-18 NPTF',1),('M10x1.5',0)]:
        assert thread_semantics({'display_name':name})['tapered']==tapered
    assert thread_record(dict(ThreadPitch='Rp1/4',MachineOperation1='TAP DRILL',MachineDia1='6'),1)['tapered']==0


def test_route_cost_is_recomputed_after_tool_changes_candidate_diameter(monkeypatch):
    from manifold import routing, sizing
    design=Design(name='Resize ranking',block=dict(length=160,width=150,height=150,material='QA'),features=[
        dict(id='CV2',kind='cavity',cavity_id=CAVITY_ID,face='top',u=123,v=60,
             interface_nets={'port1':'T','port2':'B'}),
        dict(id='B',kind='port',face='front',u=123,v=66,circuit='B',diameter=12,depth=16)],
        nets=[dict(id='B',routing='automatic',diameter=8,flow_lpm=10),dict(id='T',routing='manual')])
    real_cost=routing.route_cost
    measured=[]
    def cost(context,route):
        measured.append(tuple(f.diameter for f in route))
        return real_cost(context,route)
    monkeypatch.setattr(routing,'route_cost',cost)
    monkeypatch.setattr(sizing,'route_sizing',lambda net,**kw:dict(diameter_mm=10 if net.id=='B' and kw['required_depth'] else 8.5))
    resolved,_=routing.resolve_design(design,exact=False)
    assert next(net for net in resolved.nets if net.id=='B').diameter==10
    assert any(diameters and all(d==8.5 for d in diameters) for diameters in measured)
    assert any(diameters and all(d==10 for d in diameters) for diameters in measured)
