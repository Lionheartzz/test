"""Real source geometry; explicit test-only bindings never change compatibility."""
import copy
import json
import math
import time
import pytest
from test_ai_generation import client,analyzed,reading,selection_request,HEADERS
from manifold import projects,store
from manifold.schema import Design
from manifold.ai_design import generation,service,jobs
from manifold.ai_design.models import TaskInput
from manifold.ai_design.semantic import CircuitReading,normalize
from manifold.ai_design.generation_models import GenerationRequest
from manifold.demo import CAVITY_ID
from manifold.engineering_db import get_definition
from manifold.engineering import CalculationError


def many_request(client,count):
    task,run=analyzed(client,requirements='')
    raw=reading();raw['requirements']=[]
    base=raw['components'][0];raw['components']=[]
    for i in range(count):
        row=copy.deepcopy(base);row['label']=f'RV{i+1}';row['source']['quote']=row['label']
        raw['components'].append(row)
    inputs=TaskInput.model_validate(task['inputs'])
    result=normalize(CircuitReading.model_validate(raw),inputs,{'DOC1':1})
    run['result']=service.compact_result(result)
    store.atomic_json(service.run_path(task['id'],run['id']),run)
    definition=get_definition(CAVITY_ID)
    bindings={}
    for c in run['result']['components']:
        ports=[p for p in run['result']['ports'] if p['component_id']==c['id']]
        bindings[c['id']]=dict(definition_key='db:'+CAVITY_ID,definition_sha256=service.digest(definition.model_dump()),
            zone_ports={z.id:p['id'] for z,p in zip(definition.zones,ports)},decision='Explicit test-only source cavity / hydraulic interface mapping; no vendor compatibility is inferred.')
    options=dict(bindings=bindings,provisional_ports={p['id']:'Explicit test custom straight bore.' for p in run['result']['ports'] if p['component_id'] is None},
                 minimum_wall=3,drilling_diameter=5,max_attempts=2,max_runtime_s=120)
    return task,run,GenerationRequest(expected_revision=task['revision'],run_id=run['id'],options=options)


@pytest.mark.parametrize('count',[4,5,8,12,16])
def test_real_multi_cavity_generation(client,tmp_path,count):
    task,run,request=many_request(client,count)
    if count>=8:request.options.max_runtime_s=240
    plan=generation.prepare(TaskInput.model_validate(task['inputs']),run['result'],request.options)
    assert not plan['blocked'],plan['blocked']
    authored,_,_=generation.candidate(plan,'f'*32,0)
    cavities=[f for f in authored.features if f.kind=='cavity']
    radius=generation.definition_planar_radius(get_definition(CAVITY_ID))
    assert len(cavities)==count
    assert all(math.hypot(a.u-b.u,a.v-b.v)>=2*radius+request.options.minimum_wall for i,a in enumerate(cavities) for b in cavities[i+1:])
    packet=generation.generate(task['id'],request)
    assert packet['status']=='draft' and packet['geometry_failures']==0,packet
    assert packet['validation']['counts']['FAIL']==0,packet['attempts']
    checks={row['rule']:row for row in packet['validation']['checks'] if row['rule'] in ('solid_validity','solid_count','step_round_trip')}
    assert checks['solid_validity']['actual'] is True and checks['solid_count']['actual']==1
    assert checks['step_round_trip']['status']=='PASS' and checks['step_round_trip']['valid'] and checks['step_round_trip']['solids']==1
    assert checks['step_round_trip']['volume_measurement']['converged']
    design=Design.model_validate(packet['design'])
    assert len(design.components)==count and len(design.nets)==2
    assert packet['elapsed_s']<request.options.max_runtime_s+10
    saved=client.post('/api/projects',json=dict(design=design.model_dump()),headers=HEADERS)
    assert saved.status_code==200,saved.text
    loaded=client.get('/api/projects/'+saved.json()['project_id']).json()
    assert len(Design.model_validate(loaded['design']).components)==count
    assert all(n['route_state']=='committed' for n in loaded['design']['nets'])
    audit=store.ROOT/'output'/'ai-recovery'/f'capacity-{count}.json'
    store.atomic_json(audit,dict(packet=packet,saved=loaded,source_cavity=CAVITY_ID))


def test_draft_save_strips_obsolete_routes_and_keeps_revision_guard(client):
    raw=json.loads((store.ROOT/'tests'/'fixtures'/'automatic-t10a.json').read_text(encoding='utf-8'))['design']
    d=Design.model_validate(raw)
    # Source fixture still requires new routing; add a deliberately stale cut.
    from manifold.schema import Feature
    net=d.nets[0];net.route_state='unresolved'
    d.features.append(Feature(id='OLD',kind='drilling',face='bottom',u=40,v=40,diameter=8,depth=10,circuit=net.id,route_net=net.id,plugged=True))
    original=d.model_dump()
    assert client.post('/api/projects',json=dict(design=original),headers=HEADERS).status_code==409
    response=client.post('/api/projects',json=dict(design=original,draft_only=True),headers=HEADERS)
    assert response.status_code==200,response.text
    saved=response.json();assert not any(f['id']=='OLD' for f in saved['design']['features'])
    assert all(n['route_state']=='unresolved' for n in saved['design']['nets'])
    assert saved['build'] is None
    assert client.post('/api/build',json=dict(project_id=saved['project_id'],expected_revision=saved['revision']),headers=HEADERS).status_code==409
    changed=copy.deepcopy(saved['design']);changed['name']='Newer saved draft'
    updated=client.post('/api/projects',json=dict(design=changed,draft_only=True,project_id=saved['project_id'],expected_revision=saved['revision']),headers=HEADERS)
    assert updated.status_code==200
    stale=client.post('/api/projects',json=dict(design=original,draft_only=True,project_id=saved['project_id'],expected_revision=saved['revision']),headers=HEADERS)
    assert stale.status_code==409 and d.model_dump()==original


def test_draft_only_never_commits_an_unresolved_single_terminal(client):
    d=Design(name='Single-terminal unfinished circuit',block=dict(length=100,width=100,height=100,material='QA'),
             features=[dict(id='P',kind='port',face='left',u=50,v=50,circuit='P',diameter=8,depth=10)],
             nets=[dict(id='P',routing='automatic')])
    response=client.post('/api/projects',json=dict(design=d.model_dump(),draft_only=True),headers=HEADERS)
    assert response.status_code==200,response.text
    assert response.json()['design']['nets'][0]['route_state']=='unresolved'


def test_explicit_draft_save_retains_previous_build_as_history_not_current_approval(client):
    design=Design(name='Draft preservation',block=dict(length=100,width=100,height=100,material='QA'))
    saved=client.post('/api/projects',json=dict(design=design.model_dump()),headers=HEADERS).json()
    built=client.post('/api/build',json=dict(project_id=saved['project_id'],expected_revision=saved['revision']),headers=HEADERS)
    assert built.status_code==200,built.text
    record=client.get('/api/projects/'+saved['project_id']).json()
    pointer=record['build'];assert pointer
    response=client.post('/api/projects',json=dict(design=record['design'],project_id=saved['project_id'],expected_revision=record['revision'],draft_only=True),headers=HEADERS)
    assert response.status_code==200 and response.json()['build'] is None
    assert (store.OUTPUT/'builds'/pointer['build_id']/'validation.json').is_file()
    assert any(json.loads(p.read_text(encoding='utf-8')).get('build')==pointer for p in (projects.folder()/'history'/saved['project_id']).glob('*.json'))


@pytest.mark.parametrize('cancel',[False,True])
def test_generation_failure_and_cancellation_retain_authored_checkpoint(client,monkeypatch,cancel):
    task,run=analyzed(client);request=selection_request(task,run)
    event={'cancel':False}
    def fail(*args,**kwargs):
        event['cancel']=cancel
        raise CalculationError('Generation cancelled.' if cancel else 'CAD worker timeout; inspect diagnostics.',409 if cancel else 504)
    monkeypatch.setattr(generation,'calculate_sync',fail)
    packet=generation.generate(task['id'],request,cancelled=lambda:event['cancel'])
    assert packet['status']==('cancelled' if cancel else 'incomplete_draft')
    assert packet['design'] and packet['attempts'][0]['message']
    assert all(n['route_state']=='unresolved' for n in packet['design']['nets'])
    assert Design.model_validate(generation.load_generation(task['id'],packet['id'])['design'])==Design.model_validate(packet['design'])
    assert service.load_run(task['id'],run['id'])['status']=='completed'


def test_resource_gate_preserves_large_analysis_and_constrained_packing_is_actionable(client):
    task,run,request=many_request(client,16)
    plan=generation.prepare(TaskInput.model_validate(task['inputs']),run['result'],request.options)
    plan['settings']['maximum']=[50,50,50]
    with pytest.raises(ValueError,match='cannot fit'):
        generation.candidate(plan,'f'*32,0)
    result=copy.deepcopy(run['result']);result['nets']*=21
    # Capacity diagnostic uses actual schema, not a special cavity count.
    assert any('40' in line for line in generation.prepare(TaskInput.model_validate(task['inputs']),result,request.options)['blocked'])


def test_preferred_block_padding_is_not_a_false_engineering_size_limit(client):
    task,run=analyzed(client,requirements='');request=selection_request(task,run,minimum_wall=3)
    plan=generation.prepare(TaskInput.model_validate(task['inputs']),run['result'],request.options)
    plan['settings']['maximum']=[70,70,70]
    design,_,_=generation.candidate(plan,'f'*32,0)
    assert [design.block.length,design.block.width,design.block.height]==[70,70,70]


def test_cancel_generation_api_retains_reloadable_draft(client,monkeypatch):
    task,run=analyzed(client);request=selection_request(task,run)
    def wait_for_cancel(*args,cancelled,**kwargs):
        deadline=time.monotonic()+5
        while not cancelled() and time.monotonic()<deadline:time.sleep(.02)
        assert cancelled()
        raise CalculationError('Generation cancelled. Authored draft retained.',409)
    monkeypatch.setattr(generation,'calculate_sync',wait_for_cancel)
    response=client.post(f'/api/ai-design/tasks/{task["id"]}/generation/jobs',json=request.model_dump(),headers=HEADERS)
    assert response.status_code==200,response.text
    key=response.json()['id']
    deadline=time.monotonic()+5
    while jobs.read(key)['status']=='queued' and time.monotonic()<deadline:time.sleep(.02)
    assert client.post('/api/ai-design/jobs/'+key+'/cancel',json={},headers=HEADERS).status_code==200
    while jobs.read(key)['status'] in ('queued','running') and time.monotonic()<deadline:time.sleep(.02)
    result=jobs.read(key)
    assert result['status']=='completed' and result['result']['status']=='cancelled'
    # Cancellation before the first layout can legitimately retain analysis only.
    assert service.load_run(task['id'],run['id'])['status']=='completed'


def test_changed_analysis_retains_source_draft_without_overwriting_new_inputs(client,monkeypatch):
    task,run=analyzed(client);request=selection_request(task,run)
    def changed(*args,**kwargs):
        inputs=TaskInput.model_validate(task['inputs']);inputs.engineering_requirements+=' Newer engineer input.'
        service.save(inputs,task['id'],task['revision'])
        raise CalculationError('Calculation interrupted; draft retained.')
    monkeypatch.setattr(generation,'calculate_sync',changed)
    packet=generation.generate(task['id'],request)
    assert packet['status']=='superseded_draft' and packet['design']
    assert packet['source_task_revision']==request.expected_revision
    latest=service.read(task['id'])
    assert latest['inputs']['engineering_requirements'].endswith('Newer engineer input.')
    assert latest['generations'][-1]['id']==packet['id']
    assert generation.load_generation(task['id'],packet['id'])['status']=='superseded_draft'
