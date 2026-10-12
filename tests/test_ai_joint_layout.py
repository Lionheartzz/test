"""Real CAD evidence for NEW AI layout ownership; QA is not vendor data."""
import json
from pathlib import Path
import pytest

from manifold.schema import Design,CavityDefinition
from manifold.ai_design.design_space import LayoutDomain
from manifold.ai_design import joint_layout,layout_search
from manifold.layout_planning import _fits
from manifold.routing import manufacturing_metrics
from manifold import store


def definitions():
    c=CavityDefinition(id='QA_JOINT',label='QA source window, not vendor approval',
        stages=[dict(start=0,end=24,diameter=12)],zones=[dict(id='deep',start=12,end=24,diameter=12)],
        clearance_diameter=16,clearance_height=4)
    return {c.id:c}


def crossed_layout(*,small=False):
    coords=[('C1',14,10,'P'),('C2',30,10,'P'),('C3',14,30,'T'),('C4',30,30,'T')] if small else [
        ('C1',25,40,'P'),('C2',115,70,'P'),('C3',25,70,'T'),('C4',115,40,'T')]
    return Design(name='QA joint layout',block=dict(length=40 if small else 140,width=40 if small else 110,height=40 if small else 90,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id=i,kind='cavity',face='top',u=x,v=y,cavity_id='QA_JOINT',interface_nets={'deep':net}) for i,x,y,net in coords]+[
            dict(id=net+'0',kind='port',face='left',u=y,v=22 if small else 72,diameter=12,depth=16,tip_angle=180,
                circuit=net,clearance_diameter=14,clearance_height=1) for net,y in [('P',10 if small else 40),('T',30 if small else 70)]],
        nets=[dict(id=n,routing='automatic',diameter=8) for n in ('P','T')])


def local_exact(monkeypatch):
    # Only bypass transport for explicit QA definitions unavailable in SQLite.
    # Selection, Router gates, geometry, validator and STEP remain real.
    monkeypatch.setattr(joint_layout,'run_exact',lambda d,defs,threads,modifiers,**kw:
        joint_layout.exact_candidate(d,defs,threads,modifiers,folder=kw.get('folder'),cancelled=kw.get('cancelled',lambda:False)))


def accepted(result,folder):
    (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    assert result['status']=='EXACT_FEASIBLE',[(a['status'],a.get('failures')) for a in result['attempts']]
    assert result['validation']['counts']['FAIL']==0
    selected=Design.model_validate(result['proposals'][0]['design'])
    actual=[a for a in result['attempts'] if a['status']=='EXACT_FEASIBLE']
    assert actual and all(a['topology']==dict(valid=True,solids=1) and a['step']['status']=='PASS' for a in actual)
    assert all(n.routing_variant is None for n in selected.nets)
    assert not any(c['status']=='FAIL' for c in result['validation']['checks'] if c['rule'] in ('circuit_intersection','connected_interface','cavity_protected_region'))
    return selected


def test_repositions_components_and_reduces_real_drilling_complexity(monkeypatch,tmp_path):
    local_exact(monkeypatch);d=crossed_layout();before=d.model_dump_json();defs=definitions()
    result=layout_search.plan_new(d,defs,movable_features={f.id for f in d.features},layout_limit=16,exact_limit=2,evidence_dir=tmp_path)
    selected=accepted(result,tmp_path)
    assert d.model_dump_json()==before
    assert any((f.u,f.v,f.face)!=(g.u,g.v,g.face) for f in d.features for g in selected.features if f.id==g.id and f.kind=='cavity')
    route=[f for f in selected.features if f.route_net]
    assert len(route)<result['baseline']['drillings']


def test_moves_a_functional_port_to_the_real_window_without_moving_fixed_cavity(monkeypatch,tmp_path):
    local_exact(monkeypatch);defs=definitions()
    d=Design(name='QA functional port relocation',block=dict(length=140,width=110,height=90,material='QA'),rules=dict(minimum_wall=2),features=[
        dict(id='CV',kind='cavity',face='top',u=70,v=30,cavity_id='QA_JOINT',interface_nets={'deep':'P'}),
        dict(id='P0',kind='port',face='left',u=80,v=40,diameter=12,depth=16,tip_angle=180,circuit='P',clearance_diameter=14,clearance_height=1)],
        nets=[dict(id='P',routing='automatic',diameter=8)])
    before=d.model_dump_json()
    result=layout_search.plan_new(d,defs,movable_features={'P0'},growth_axes=(),layout_limit=8,exact_limit=2,evidence_dir=tmp_path)
    selected=accepted(result,tmp_path)
    port=next(f for f in selected.features if f.id=='P0')
    assert (port.face,port.u,port.v)!=('left',80,40)
    assert next(f for f in selected.features if f.id=='CV')==d.features[0] and selected.block==d.block
    assert d.model_dump_json()==before


def test_can_reduce_unused_stock_after_safety_and_machining_feasibility(monkeypatch,tmp_path):
    local_exact(monkeypatch)
    d=Design(name='QA stock reduction',block=dict(length=140,width=140,height=140,material='QA'),rules=dict(minimum_wall=2),features=[
        dict(id='P'+face,kind='port',face=face,u=30,v=50,diameter=12,depth=16,tip_angle=180,circuit='P',clearance_diameter=14,clearance_height=1)
        for face in ('left','right')],nets=[dict(id='P',routing='automatic',diameter=8)])
    fixed={f.id:dict(u=f.u,v=f.v) for f in d.features};before=d.model_dump_json()
    result=layout_search.plan_new(d,{},movable_features=set(fixed),growth_axes=(1,2),fixed_positions=fixed,
        layout_limit=8,exact_limit=2,evidence_dir=tmp_path)
    selected=accepted(result,tmp_path)
    assert selected.block.length==140 and selected.block.width*selected.block.height<140*140
    assert d.model_dump_json()==before


def test_inadequate_space_grows_and_relocates_sources_while_fixed_ports_stay(monkeypatch,tmp_path):
    local_exact(monkeypatch);d=crossed_layout(small=True);defs=definitions();before=d.model_dump_json()
    faces={f.id:f.face for f in d.features};positions={f.id:dict(u=f.u,v=f.v) for f in d.features if f.kind=='port'}
    result=layout_search.plan_new(d,defs,movable_features={f.id for f in d.features},growth_axes=(0,),
        fixed_faces=faces,fixed_positions=positions,layout_limit=24,exact_limit=2,evidence_dir=tmp_path)
    selected=accepted(result,tmp_path)
    assert selected.block.length>d.block.length and selected.block.width==40 and selected.block.height==40
    for f in selected.features:
        if f.id in positions:assert (f.face,f.u,f.v)==(faces[f.id],positions[f.id]['u'],positions[f.id]['v'])
    assert d.model_dump_json()==before


def test_rotates_actual_offset_windows_to_separate_two_hydraulic_nets(monkeypatch,tmp_path):
    local_exact(monkeypatch)
    c=CavityDefinition(id='QA_PATTERN',label='QA two-window machining interface',stages=[dict(start=0,end=12,diameter=1)],
        cutting_primitives=[dict(kind='cylinder',start=0,end=12,diameter=10,offset_u=x) for x in (-12,12)],
        zones=[dict(id=n,start=0,end=12,diameter=10,offset_u=x) for n,x in [('P',-12),('T',12)]],clearance_diameter=40,clearance_height=4)
    d=Design(name='QA real window rotation',block=dict(length=100,width=100,height=100,material='QA'),rules=dict(minimum_wall=2),features=[
        dict(id='CV',kind='cavity',face='top',u=50,v=50,cavity_id=c.id,interface_nets={'P':'P','T':'T'}),
        *[dict(id=n+'0',kind='port',face=face,u=50,v=90,diameter=12,depth=16,tip_angle=180,circuit=n,clearance_diameter=14,clearance_height=1)
          for n,face in [('P','front'),('T','back')]]],nets=[dict(id=n,routing='automatic',diameter=8) for n in ('P','T')])
    faces={f.id:f.face for f in d.features};positions={f.id:dict(u=f.u,v=f.v) for f in d.features if f.kind=='port'}
    result=layout_search.plan_new(d,{c.id:c},movable_features={f.id for f in d.features},growth_axes=(),fixed_faces=faces,
        fixed_positions=positions,layout_limit=12,exact_limit=2,evidence_dir=tmp_path)
    selected=accepted(result,tmp_path)
    assert next(f for f in selected.features if f.id=='CV').rotation!=0
    # Real K scenario: the first layout is Exact-feasible; a later route fails
    # positive source connectivity. Selection must retain the feasible layout.
    assert any(a['status']=='EXACT_FEASIBLE' for a in result['attempts'])
    assert any(a['status'].endswith('REJECTED') for a in result['attempts'])


def test_fixed_height_requires_a_different_permitted_cavity_face(monkeypatch,tmp_path):
    local_exact(monkeypatch)
    c=CavityDefinition(id='QA_DEEP',label='QA deep source',stages=[dict(start=0,end=40,diameter=12)],
        zones=[dict(id='deep',start=28,end=40,diameter=12)],clearance_diameter=16,clearance_height=4)
    d=Design(name='QA constrained face',block=dict(length=80,width=80,height=30,material='QA'),rules=dict(minimum_wall=2),features=[
        dict(id='CV',kind='cavity',face='top',u=40,v=40,cavity_id=c.id,interface_nets={'deep':'P'}),
        dict(id='P0',kind='port',face='right',u=40,v=15,diameter=12,depth=12,tip_angle=180,circuit='P',clearance_diameter=14,clearance_height=1)],
        nets=[dict(id='P',routing='automatic',diameter=8)],constraints=dict(envelope_min=[80,80,30],envelope_max=[80,80,30]))
    assert not _fits(d,{c.id:c})
    result=layout_search.plan_new(d,{c.id:c},movable_features={'CV','P0'},fixed_faces={'P0':'right'},
        fixed_positions={'P0':dict(u=40,v=15)},layout_limit=12,exact_limit=2,evidence_dir=tmp_path)
    selected=accepted(result,tmp_path)
    assert selected.block==d.block and next(f for f in selected.features if f.id=='CV').face not in ('top','bottom')


def test_explicit_fixed_geometry_is_not_relabelled_as_soft_or_feasible(tmp_path):
    d=crossed_layout(small=True);before=d.model_dump_json();defs=definitions()
    result=layout_search.plan_new(d,defs,movable_features=set(),growth_axes=(),fixed_faces={f.id:f.face for f in d.features},
        layout_limit=3,exact_limit=0,evidence_dir=tmp_path)
    assert result['status']!='EXACT_FEASIBLE' and result['validation'] is None and d.model_dump_json()==before
    assert result['proposals'][0]['design']==d.model_dump()
    assert result['domain']['movable']==[] and result['domain']['dimension_axes']==[]


def test_existing_disposable_worker_accepts_explicit_ai_drillings(monkeypatch,tmp_path):
    from test_corridor_planner import crossing
    from manifold.drilling_planner import coordinate_routes,materialized_proposal
    from manifold.engineering import executor
    d=crossing();chosen,detail=coordinate_routes(d,d.nets,{}, {}, {},label_limit=256)
    target,_=materialized_proposal(d,chosen,detail)
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    folder=tmp_path/'worker';folder.mkdir()
    result=joint_layout.run_exact(target,{}, {}, {},folder=folder)
    assert result['status']=='EXACT_FEASIBLE',result
    assert executor.history[-1]['operation']=='ai-layout-exact'
    assert (folder/'production.step').is_file() and result['step']['status']=='PASS'


def test_real_worker_rejection_retains_connection_evidence_instead_of_transport_error(monkeypatch,tmp_path):
    from test_corridor_planner import crossing
    from manifold.engineering import executor
    d=crossing()
    for net in d.nets:net.route_state='proposal'
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    folder=tmp_path/'rejected';folder.mkdir()
    result=joint_layout.run_exact(d,{}, {}, {},folder=folder)
    assert result['status']=='EXACT_ROUTING_REJECTED' and not result['full_cad_evaluated']
    assert result['failures'] and result['connections'] and result['validation'] is None
    assert executor.history[-1]['state']=='completed'
    assert not (folder/'production.step').exists()
    from manifold.ai_design.generation import _attempt_summary
    summary=_attempt_summary(dict(index=0,layout_index=0,**result),{'connected_interface'})
    assert summary['error'] and summary['counts'] is None and summary['geometry_failures'] is None


def test_fixed_mounting_preserves_its_cut_but_allows_unrelated_stock_growth(monkeypatch,tmp_path):
    local_exact(monkeypatch);d=crossed_layout(small=True);defs=definitions()
    from manifold.schema import Feature
    mount=Feature(id='FIXED_MOUNT',kind='mounting',face='top',u=10,v=10,diameter=5,depth=8)
    d.features.append(mount);before=d.model_dump_json()
    owned={f.id for f in d.features if f.kind in ('cavity','port')}
    result=layout_search.plan_new(d,defs,movable_features=owned,growth_axes=(0,),fixed_faces={f.id:f.face for f in d.features},
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features if f.kind=='port'},layout_limit=20,exact_limit=2,evidence_dir=tmp_path)
    target=accepted(result,tmp_path)
    assert target.block.length>40 and target.block.width==target.block.height==40
    assert next(f for f in target.features if f.id==mount.id)==mount and d.model_dump_json()==before
    assert result['domain']['dimension_axes']==[0]


def test_explicit_source_positions_faces_and_stock_stay_fixed_in_real_acceptance(monkeypatch,tmp_path):
    local_exact(monkeypatch)
    d=Design(name='QA fixed authored intent in new AI candidate',block=dict(length=100,width=80,height=90,material='QA'),
        rules=dict(minimum_wall=2),features=[dict(id='P'+face,kind='port',face=face,u=30,v=50,diameter=12,depth=16,
        tip_angle=180,circuit='P',clearance_diameter=14,clearance_height=1) for face in ('left','right')],
        nets=[dict(id='P',routing='automatic',diameter=8)],constraints=dict(envelope_min=[100,80,90],envelope_max=[100,80,90]))
    before=d.model_dump_json();owned={f.id for f in d.features}
    result=layout_search.plan_new(d,{},movable_features=owned,fixed_faces={f.id:f.face for f in d.features},
        fixed_positions={f.id:dict(u=f.u,v=f.v) for f in d.features},fixed_rotations={f.id:f.rotation for f in d.features},
        layout_limit=4,exact_limit=2,evidence_dir=tmp_path)
    target=accepted(result,tmp_path)
    assert target.block==d.block and all(next(f for f in target.features if f.id==s.id)==s for s in d.features)
    assert d.model_dump_json()==before


def test_three_overlapping_connected_sources_require_coordinated_relocation(monkeypatch,tmp_path):
    local_exact(monkeypatch);defs=definitions()
    d=Design(name='QA coordinated three sources',block=dict(length=120,width=80,height=70,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id='C'+str(i),kind='cavity',face='top',u=30,v=30,cavity_id='QA_JOINT',interface_nets={'deep':'P'}) for i in range(3)]+
        [dict(id='P0',kind='port',face='left',u=30,v=52,diameter=12,depth=16,tip_angle=180,circuit='P',clearance_diameter=14,clearance_height=1)],
        nets=[dict(id='P',routing='automatic',diameter=8)])
    before=d.model_dump_json();faces={f.id:f.face for f in d.features}
    result=layout_search.plan_new(d,defs,movable_features=set(faces),growth_axes=(),fixed_faces=faces,
        fixed_positions={'P0':dict(u=30,v=52)},layout_limit=12,exact_limit=2,evidence_dir=tmp_path)
    target=accepted(result,tmp_path)
    moved=[f for f in target.features if f.kind=='cavity' and (f.u,f.v)!=(30,30)]
    # Moving any single source leaves the other two coincident and source-unsafe.
    assert len(moved)>=2 and target.block==d.block and d.model_dump_json()==before


def test_hard_height_and_required_face_report_the_actual_source_conflict(tmp_path,monkeypatch):
    c=CavityDefinition(id='QA_CONSTRAINED',label='QA hard source depth',stages=[dict(start=0,end=40,diameter=12)],
        zones=[dict(id='deep',start=28,end=40,diameter=12)],clearance_diameter=16,clearance_height=4)
    d=Design(name='QA incompatible hard requirements',block=dict(length=80,width=80,height=30,material='QA'),rules=dict(minimum_wall=2),
        features=[dict(id='CV',kind='cavity',face='top',u=40,v=40,cavity_id=c.id)],
        constraints=dict(envelope_min=[80,80,30],envelope_max=[80,80,30]))
    result=layout_search.plan_new(d,{c.id:c},movable_features={'CV'},fixed_faces={'CV':'top'},layout_limit=3,exact_limit=1,evidence_dir=tmp_path)
    assert result['outcome_classification']=='PROVEN_HARD_CONSTRAINT_CONFLICT'
    conflict=result['hard_constraint_conflicts'][0]
    assert conflict['feature']=='CV' and conflict['permitted_faces'][0]['required'][2]==42 and conflict['maximum'][2]==30
    assert result['validation'] is None and result['counters']['exact_attempts']==0
    from types import SimpleNamespace
    from manifold.ai_design.generation import _plan_generated_layout
    original=layout_search.plan_new
    def small(*args,**kwargs):kwargs['layout_limit']=3;return original(*args,**kwargs)
    monkeypatch.setattr(layout_search,'plan_new',small)
    settings=dict(dispositions=[],soft_dimensions={},envelope_min_axes=['length','width','height'],
        envelope_max_axes=['length','width','height'],material_proposal={})
    output=_plan_generated_layout(d,{c.id:c},settings,SimpleNamespace(project_engineering=None),{'CV':'CV'},fixed_faces={'CV':'top'},exact_limit=1)
    assert '42 mm > limit 30 mm' in settings['layout_planning']['message']
    assert any(r.subject=='CV' and r.severity=='blocking' for r in output.review_items)
