"""Compilation authority and real worker handoff, without a paid AI call."""
import json
import pytest
from manifold.schema import Design
from manifold.ai_design import generation,joint_layout,layout_search
from manifold.ai_design.intent import interpret
from manifold.ai_design.generation_models import GenerationOptions
from manifold.layout import propose_dimensions
from manifold.layout import placement_conflicts
from manifold import store
from test_ai_generation import client,analyzed,selection_request
from test_ai_joint_layout import definitions,crossed_layout
from manifold.ai_design.design_space import LayoutDomain


def test_soft_dimension_intent_is_not_an_envelope_or_manual_sizing_change():
    result=dict(components=[],ports=[],design_intent=[dict(id='SOFT_SIZE',category='envelope',property='length',operator='equal',
        value=40,unit='mm',strength='preference',target_labels=[])])
    settings=interpret(result,GenerationOptions())
    assert settings['soft_dimensions']=={'length':40}
    assert settings['maximum']==[2000]*3 and settings['envelope_axes']==[]
    d=crossed_layout();before=d.model_dump_json()
    # Existing manual callers keep the old hard-preference contract; only new
    # AI compilation explicitly opts into soft inherited dimensions.
    with pytest.raises(ValueError):propose_dimensions(d,definitions(),(20,20,20))
    sizes=propose_dimensions(d,definitions(),(20,20,20),preferred_is_soft=True)
    assert all(s>=20 for s in sizes) and any(s>20 for s in sizes)
    assert d.model_dump_json()==before
    result['design_intent'][0]['strength']='requirement'
    hard=interpret(result,GenerationOptions())
    assert hard['minimum'][0]==hard['maximum'][0]==40 and hard['soft_dimensions']=={}


def test_unowned_and_world_positions_are_protected_but_local_uv_does_not_fix_stock():
    d=crossed_layout()
    only_port=LayoutDomain.new_generation(d,{'P0'})
    assert 2 not in only_port.dimension_axes and 'C1' in only_port.protected
    d.features[-1].face='right'
    owned={f.id for f in d.features}
    uv=dict(u=d.features[-1].u,v=d.features[-1].v)
    local=LayoutDomain.new_generation(d,owned,fixed_positions={'T0':uv})
    target=d.model_copy(deep=True);target.block.length+=20
    assert 0 in local.dimension_axes and local.accepts(d,target)
    fixed=LayoutDomain.new_generation(d,owned,fixed_positions={'T0':dict(**uv,x=d.block.length)})
    assert 0 not in fixed.dimension_axes
    before=d.model_dump_json()
    assert not fixed.accepts(d,target) and d.model_dump_json()==before


def test_explicit_generation_face_choice_needs_no_redundant_text_confirmation():
    settings=interpret(dict(components=[dict(id='CV',label='Valve')],ports=[],nets=[],design_intent=[]),
                       GenerationOptions(component_faces={'CV':'front'}))
    assert settings['component_faces']=={'CV':'front'} and settings['conflicts']==[]


def test_generation_job_retains_specific_hard_constraint_error(client,monkeypatch):
    import threading
    from manifold.ai_design import jobs
    task,run=analyzed(client);request=selection_request(task,run)
    def constrained(*args,**kwargs):
        raise ValueError('CV: source depth 40 mm plus wall 2 mm exceeds fixed Z 30 mm on required top face')
    monkeypatch.setattr(generation,'generate',constrained)
    key='e'*32
    jobs._cancel_events[key]=threading.Event()
    record=dict(id=key,task_id=task['id'],operation='generate',request=request.model_dump(),status='queued')
    jobs._execute(record)
    state=jobs.read(key)
    assert state['status']=='failed' and 'fixed Z 30 mm' in state['message'] and 'required top face' in state['message']


def test_cancel_after_initial_snapshot_retains_an_openable_registered_draft(client):
    task,run=analyzed(client);request=selection_request(task,run,minimum_wall=3)
    stopped=[False]
    def progress(update):
        if isinstance(update,dict) and update.get('initial_generation_id'):stopped[0]=True
    packet=generation.generate(task['id'],request,progress,cancelled=lambda:stopped[0])
    assert packet['status']=='cancelled' and packet['design'] and packet['validation'] is None
    assert all(n['route_state']=='unresolved' for n in packet['design']['nets'])
    assert generation.load_generation(task['id'],packet['id'])['design']==packet['design']
    from manifold.ai_design import service
    assert service.read(task['id'])['generations'][-1]['id']==packet['id']


def test_profile_cache_never_reuses_an_acceptance_or_different_source_geometry():
    d=crossed_layout(small=True);defs=definitions();cache={}
    for x in (14,20,26,34):
        changed=d.model_copy(deep=True);changed.features[0].u=x
        for wall in (2,5):
            changed.rules.minimum_wall=wall
            assert placement_conflicts(changed,changed.features[0],defs,{}, {},cache=cache)==placement_conflicts(changed,changed.features[0],defs,{}, {})
    newer={key:value.model_copy(update=dict(clearance_diameter=value.clearance_diameter+4)) for key,value in defs.items()}
    assert placement_conflicts(d,d.features[0],newer,{}, {},cache=cache)==placement_conflicts(d,d.features[0],newer,{}, {})
    for x in (14,26,14):
        d.features[0].u=x
        assert placement_conflicts(d,d.features[0],defs,{}, {},cache=cache)==placement_conflicts(d,d.features[0],defs,{}, {})


def test_impossibility_requires_explicit_limits_and_valid_source_envelope():
    from manifold.schema import CavityDefinition
    from manifold.ai_design.initialization import constraint_conflicts
    c=CavityDefinition(id='QA_OFFSET_BOUND',label='QA bounds only',stages=[dict(start=0,end=12,diameter=1)],
        cutting_primitives=[dict(kind='cylinder',start=0,end=12,diameter=8,offset_u=x) for x in (-20,20)],
        zones=[dict(id='one',start=0,end=12,diameter=8,offset_u=-20)],clearance_diameter=50,clearance_height=4)
    d=Design(name='QA impossibility proof boundary',block=dict(length=60,width=60,height=30,material='QA'),rules=dict(minimum_wall=2),
        constraints=dict(envelope_max=[60,60,30]),features=[dict(id='CV',kind='cavity',face='top',u=30,v=30,cavity_id=c.id)])
    domain=LayoutDomain.new_generation(d,{'CV'},fixed_faces={'CV':'top'})
    assert not constraint_conflicts(d,{c.id:c},domain,{}, {})
    restricted=d.model_copy(deep=True);restricted.block.length=40;restricted.constraints.envelope_max=(40,60,30)
    fixed=LayoutDomain.new_generation(restricted,{'CV'},fixed_faces={'CV':'top'},fixed_rotations={'CV':0})
    assert constraint_conflicts(restricted,{c.id:c},fixed,{}, {})[0]['feature']=='CV'
    software=LayoutDomain.new_generation(restricted,{'CV'},fixed_faces={'CV':'top'},fixed_rotations={'CV':0},
        explicit_dimension_axes=dict(minimum=[],maximum=[]))
    assert not constraint_conflicts(restricted,{c.id:c},software,{}, {})


def test_shared_material_defaults_defer_layout_only_for_explicit_ai_opt_in(monkeypatch):
    from manifold import draft_defaults
    d=crossed_layout();defs=definitions();before=d.model_dump_json();calls=[]
    original=draft_defaults.propose_dimensions
    def measured(*args,**kwargs):calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(draft_defaults,'propose_dimensions',measured)
    _,manual=draft_defaults.apply_draft_defaults(d,defs,preferred_dimensions=(20,20,20))
    assert calls and manual['status']=='UNRESOLVED' and 'layout_status' not in manual
    calls.clear()
    target,ai=draft_defaults.apply_draft_defaults(d,defs,preferred_dimensions=(20,20,20),defer_layout=True)
    assert not calls and ai['layout_status']=='DEFERRED_TO_NEW_AI_CONSTRAINT_SEARCH'
    assert target.block.length==d.block.length and target.block.width==d.block.width and target.block.height==d.block.height
    assert d.model_dump_json()==before


def test_initial_draft_is_available_before_real_exact_worker_and_final_handoff_is_separate(client,monkeypatch,tmp_path):
    task,run=analyzed(client)
    request=selection_request(task,run,max_exact_attempts=1,minimum_wall=3)
    # A deliberately small test calculation budget, with real selection and
    # the same CAD worker; no candidate/geometry/validator outcome is faked.
    real_plan=layout_search.plan_new
    def small_budget(*args,**kwargs):
        kwargs['layout_limit']=4
        return real_plan(*args,**kwargs)
    monkeypatch.setattr(layout_search,'plan_new',small_budget)
    real_exact=joint_layout.run_exact;observed=[];updates=[]
    def check_initial(d,defs,threads,modifiers,**kwargs):
        initial=next((store.OUTPUT/'ai-design'/task['id']/'generations').glob('*/authored-draft.json'))
        packet=initial.parent/'generation.json';row=json.loads(packet.read_text())
        response=client.get(f"/api/ai-design/tasks/{task['id']}/generations/{row['id']}/project")
        assert response.status_code==200 and row['route_status']=='INITIAL_LAYOUT_NOT_VERIFIED'
        observed.append((initial,initial.read_bytes(),response.json()))
        return real_exact(d,defs,threads,modifiers,**kwargs)
    monkeypatch.setattr(joint_layout,'run_exact',check_initial)
    packet=generation.generate(task['id'],request,updates.append)
    assert packet['status']==('draft' if packet['route_status']=='EXACT_FEASIBLE' else 'incomplete_draft') and observed
    assert any('initial_draft_url' in row for row in updates)
    percentages=[row['progress']['percent'] for row in updates if 'progress' in row]
    assert percentages==sorted(percentages) and max(percentages)<100
    assert all(row['progress']['layout']<=row['progress']['layout_limit'] for row in updates if row.get('progress',{}).get('layout'))
    for path,before,opened in observed:
        assert path.read_bytes()==before
        assert not any(f.get('route_net') for f in opened['features'])
    assert packet['resource_limits']['exact_layout_attempts']==1
    assert packet['layout_planning']['scope']=='AI_GENERATION_ONLY'
    assert packet['route_status'] in ('EXACT_FEASIBLE','EXACT_ENGINEERING_REJECTED','UNRESOLVED_LAYOUT')
    assert not any(n.get('routing_variant') for n in packet['design']['nets'])
    assert not (tmp_path/'projects'/'saved').exists()
    if packet['route_status']=='EXACT_FEASIBLE':
        assert packet['validation']['counts']['FAIL']==0
    else:assert 'unresolved' in packet['message'].lower()


def test_generation_compiles_before_legacy_packing_even_with_tiny_inherited_stock(client,monkeypatch,tmp_path):
    from manifold import layout
    task,run=analyzed(client,requirements='')
    inputs=task['inputs'];inputs['project_engineering']=Design(name='Soft inherited seed',block=dict(length=10,width=10,height=10,material='QA')).model_dump()
    from manifold.ai_design import service
    # Keep the reviewed observation run; only context defaults are supplied to
    # the local compiler. This is not another paid recognition request.
    from manifold.ai_design.models import TaskInput
    model_inputs=TaskInput.model_validate(inputs)
    request=selection_request(task,run,minimum_wall=3)
    plan=generation.prepare(model_inputs,run['result'],request.options)
    assert not plan['blocked']
    def forbidden(*args,**kwargs):raise AssertionError('Legacy packing must not gate AI generation')
    monkeypatch.setattr(layout,'circle_layout',forbidden)
    monkeypatch.setattr(layout,'initial_placement',forbidden)
    monkeypatch.setattr(generation,'_scaffold_faces',forbidden)
    candidate,_,_=generation.candidate(plan,'a'*32,0,exact_limit=1,evidence_dir=store.OUTPUT/'acceptance')
    planning=plan['settings']['layout_planning']
    (tmp_path/'generation-acceptance.json').write_text(json.dumps(dict(design=candidate.model_dump(),planning=planning),indent=2),encoding='utf-8')
    assert planning['status']=='EXACT_FEASIBLE' and planning['validation']['counts']['FAIL']==0
    assert max(candidate.block.length,candidate.block.width,candidate.block.height)>10


def test_uncompiled_hard_placement_is_retained_and_never_auto_rearranged(client,monkeypatch):
    from manifold.ai_design.models import TaskInput
    task,run=analyzed(client);request=selection_request(task,run)
    plan=generation.prepare(TaskInput.model_validate(task['inputs']),run['result'],request.options)
    plan['settings']['dispositions'].append(dict(intent_id='EXPLICIT_XYZ',strength='requirement',category='serviceability',
        property='fixed_position_xyz',targets=['VALVE_RV1'],value='20, 30, 40',unit='mm',status='review_required'))
    def forbidden(*args,**kwargs):raise AssertionError('Uncompiled hard placements must not authorize optimization')
    monkeypatch.setattr(layout_search,'plan_new',forbidden)
    design,_,_=generation.candidate(plan,'b'*32,0)
    evidence=plan['settings']['layout_planning']
    assert evidence['status']=='POSITION_REQUIREMENT_UNRESOLVED' and evidence['pending_requirements'][0]['intent_id']=='EXPLICIT_XYZ'
    assert any(r.id=='AI_LAYOUT_POSITION' and r.severity=='blocking' for r in design.review_items)
