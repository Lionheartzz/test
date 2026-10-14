"""Focused production-algorithm witnesses; no full complex Generate."""
from dataclasses import replace
import json
from pathlib import Path
import pytest

from manifold.schema import Design,Feature,CavityDefinition
from manifold.ai_design.single_design import WorkDesign
from manifold.ai_design.design_space import LayoutDomain
from manifold.ai_design.corridor_planner import MachiningPlan
from manifold.ai_design.engineering_decisions import DecisionState
from manifold.engineering_db import definitions_for_design,thread_definitions_for_design,tool_definitions
from test_engineering_layout_planner import shared_sources
from test_single_work_design import work,forbid_search

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('preferred',('top','front','back','left','right'))
def test_five_cavity_faces_are_real_soft_domains_not_top_locks(preferred):
    d,defs=shared_sources();w=work(d,defs,soft_faces={f.id:preferred for f in d.features})
    assert all(set(w.e.domain.faces(f))=={'top','front','back','left','right'} for f in d.features)
    assert w.initialize(),w.diagnostics()
    assert preferred in {f.face for f in w.design.features}
    assert not any(f.face=='bottom' for f in w.design.features)
    assert not w.source_conflicts(w.design) and w.e.domain.accepts(d,w.design)
    w.materialize();assert w.precheck(),w.failures


def test_bottom_and_coordinate_rotation_requirements_win_over_soft_face():
    d,defs=shared_sources();d.features[0].face='bottom';d.features[0].u=d.features[0].v=25;d.features[0].rotation=90
    w=work(d,defs,fixed_faces={'S0':'bottom'},fixed_positions={'S0':dict(u=25,v=25)},fixed_rotations={'S0':90},soft_faces={'S0':'front'})
    assert w.initialize(),w.diagnostics()
    f=next(f for f in w.design.features if f.id=='S0')
    assert (f.face,f.u,f.v,f.rotation)==('bottom',25,25,90)
    assert w.e.domain.faces(f)==('bottom',) and w.e.domain.accepts(d,w.design)
    # A Port's separate six-face domain is unchanged by the Cavity policy.
    p=Feature(id='E',kind='port',face='bottom',u=30,v=30,diameter=10,depth=10,circuit='N')
    d.features.append(p);domain=LayoutDomain.new_generation(d,{p.id})
    assert set(domain.faces(p))=={'top','bottom','front','back','left','right'}
    assert domain.faces(d.features[0])==('bottom',)


def test_hyperedge_adjacency_does_not_collapse_transitive_chain():
    d,defs=shared_sources();third=d.features[1].model_copy(update=dict(id='S2',u=90))
    d.features.append(third)
    d.features[0].interface_nets={'w0':'N0','w1':'N1'}
    d.features[1].interface_nets={'w0':'N0','w1':'N1','w2':'N2'}
    d.features[2].interface_nets={'w2':'N2'}
    d=Design.model_validate(d.model_dump())
    w=work(d,defs);rows=w.e.associations()
    assert rows[0]['features']==['S0','S1'] or rows[0]['features']==['S1','S0']
    assert set(rows[0]['nets'])=={'N0','N1'}
    assert all(set(g)!={'S0','S1','S2'} for g in w.groups())
    assert not any(set(r['features'])=={'S0','S2'} for r in rows)


def test_coupled_area_allocation_avoids_irrevocable_greedy_strip():
    from manifold.ai_design.source_arrangement import arrange
    definition=CavityDefinition(id='QA_2D',label='QA large hydraulic windows',stages=[dict(start=0,end=30,diameter=32)],
        zones=[dict(id='w',start=10,end=30,diameter=32)],clearance_diameter=40,clearance_height=2)
    d=Design(name='Measured two dimensional arrangement',block=dict(length=200,width=200,height=60,material='QA'),
        rules=dict(minimum_wall=2,minimum_access_gap=2),features=[dict(id=f'C{i}',kind='cavity',face='top',u=30+i*45,v=30,
            cavity_id=definition.id,interface_nets={'w':'N'}) for i in range(4)],nets=[dict(id='N',routing='automatic',diameter=20)])
    w=work(d,{definition.id:definition},fixed_faces={f.id:'top' for f in d.features})
    ok,records=arrange(w)
    assert ok and len({f.u for f in w.design.features})==2 and len({f.v for f in w.design.features})==2
    assert not w.source_conflicts(w.design) and not w.fit(w.design)
    assert w.design.block.length==w.design.block.width==86
    assert records[0]['area_allocation']['projected_area']>0


def test_real_saved_positive_escape_cycle_replans_only_implicated_processes(tmp_path,monkeypatch):
    forbid_search(monkeypatch)
    old=json.loads((ROOT/'output/runtime-checks/single-work-20261014/precheck/result.json').read_text())['result']
    d=Design.model_validate(old['design']);before_json=d.model_dump_json();defs=definitions_for_design(d)
    w=WorkDesign(d,defs,LayoutDomain.new_generation(d,{f.id for f in d.features}),thread_definitions_for_design(d),{},tool_definitions('drill'))
    def restore(r):
        return MachiningPlan(r['net'],r['spine_axis'],tuple((m,tuple(o)) for m,o in r['terminal_orders'].items()),
            entry=r['entry'],planar=r['planar'],side=r['side'],access=r['access'],axial_members=tuple(r['axial_members']),
            layer_axis=r['layer_axis'],entry_axes=tuple(r['entry_axes'].items()),reserve_columns=r['reserve_columns'])
    plans={n:restore(p) for n,p in old['evidence']['selected_processes'].items()}
    w.state=DecisionState(plans,preserve=False);w.state=replace(w.state,separations=w.spacing())
    before,detail=w.solve(w.state)
    assert before is None
    assert {tuple(c['nets']) for c in detail['cycle']}=={('T_DC','P'),('P','T'),('T','T_DC')}
    assert all(c['axis']==1 and c['required']==pytest.approx(11.1) for c in detail['cycle'])
    solved,after=w.replan_constraints()
    assert {tuple(c.get('nets',[])) for c in after.get('cycle',[])}!={('T_DC','P'),('P','T'),('T','T_DC')}
    assert solved or after.get('uncovered_process_domain'),after
    changes=[r for r in w.records if r['kind']=='CONTRADICTORY_PROCESS_REPLAN']
    assert changes and changes[0]['net'] in {'T_DC','P','T'}
    assert changes[0]['previous']['spine_axis']!=changes[0]['selected']['spine_axis'] or changes[0]['previous']['layer_axis']!=changes[0]['selected']['layer_axis']
    # An unchanged all-top row may still have another sufficient-domain
    # contradiction. That must retain the actual expression gap, not PASS.
    if solved:
        target,junctions=solved
        w.design,w.junctions=target,junctions;w.materialize();w.precheck()
        assert any(f[0] in ('source_protected','plug_cut','installation_access') for rows in w.failures.values() for f in rows)
    (tmp_path/'real-escape-cycle.json').write_text(json.dumps(dict(before=detail,after=after,evidence=w.diagnostics()),indent=2))
    assert before_json==d.model_dump_json()


def test_pose_change_uses_target_block_and_invalidates_only_real_dependencies():
    d,defs=shared_sources()
    # Offset drilling primitive projects differently after the target changes
    # mounting face. Testing circularity against the old Block is incorrect.
    definition=CavityDefinition(id='OFFSET',label='QA offset machining',stages=[dict(start=0,end=30,diameter=8)],
        cutting_primitives=[dict(start=0,end=30,diameter=8,offset_u=6)],zones=[dict(id='w',start=15,end=25,diameter=8)],
        clearance_diameter=20,clearance_height=1)
    d.features[0].cavity_id='OFFSET';d.features[0].interface_nets={'w':'N0'};defs['OFFSET']=definition
    d=Design.model_validate(d.model_dump())
    w=work(d,defs);target=d.model_copy(deep=True);target.block.height=180;target.features[0].face='left'
    assert not w.circular(target.features[0],target)
    # Independent far route cannot inherit the shared source's incident set.
    w.routes['FAR']=[Feature(id='RF',kind='drilling',face='left',u=115,v=95,diameter=4,depth=10,circuit='FAR',route_net='FAR')]
    target=d.model_copy(deep=True);target.features[0].u+=1
    affected,changed=w.affected(d,target,set())
    assert changed=={'S0'} and 'N0' in affected and 'FAR' not in affected
    target.block.height+=1
    assert w.affected(d,target,set())[0]==set(w.state.plans)


def test_process_choice_records_complete_external_depth_and_forbidden_entry():
    d,defs=shared_sources();d.constraints.forbidden_drilling_faces=['left']
    w=work(d,defs);assert w.initialize()
    assert w.process_choices
    for name,p in w.state.plans.items():
        candidates=w.process_choices[name]
        assert candidates[0]['evidence']['estimated_external_length']>0
        assert not candidates[0]['evidence']['blocked_entries']
    w.materialize();assert w.precheck(),w.failures
    assert all(f.face!='left' for fs in w.routes.values() for f in fs)


def test_failed_entry_context_depends_on_all_retained_machining():
    d,defs=shared_sources();w=work(d,defs);assert w.initialize();w.materialize()
    before=w.repair_dependency();source=w.design.model_dump_json()
    # Same source and same Net under repair, different third-party drilling.
    other=next(iter(w.routes));w.routes[other][0].depth+=.25
    assert w.repair_dependency()!=before and w.design.model_dump_json()==source
