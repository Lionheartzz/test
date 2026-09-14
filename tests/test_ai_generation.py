"""Real transport contract tests use a local HTTP fixture, never a paid model.

Engineering tests use actual catalog BReps; fixture selections are not vendor approval.
"""
import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import time
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pydantic import SecretStr
from manifold import catalog, store, projects
from manifold.server import app
from manifold.ai_design import config, service, generation, jobs
from manifold.ai_design.generation_models import GenerationRequest
from manifold.ai_design.providers import AnalysisRequest, DocumentContent, ProviderFailure
from manifold.ai_design.remote import MultimodalProvider
from manifold.ai_design.semantic import CircuitReading, normalize
from manifold.ai_design.models import TaskInput
from manifold.ai_design.documents import render

HEADERS={'X-PMC-Request':'local-console'}
SOURCE_ROOT=store.ROOT


@pytest.fixture
def client(tmp_path,monkeypatch):
    from mock_ai_provider import MockProvider
    monkeypatch.setattr(service,'available_providers',lambda:{mode:MockProvider(mode) for mode in ('mock-safe','mock-example')})
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects'/'demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    monkeypatch.setattr(config,'path',lambda:tmp_path/'private'/'ai-provider.json')
    return TestClient(app)


def inputs(client,requirements='P on left. T on right. Maximum block width 150 mm.'):
    data=(Path(__file__).parent/'fixtures'/'ai-demo.png').read_bytes()
    response=client.post('/api/assets',content=data,headers={**HEADERS,'Content-Type':'image/png','X-File-Name':'test.png'})
    assert response.status_code==200
    return dict(title='Generation QA',engineering_requirements=requirements,documents=[dict(id='DOC1',asset=response.json())])


def analyzed(client,requirements='P on left. T on right. Maximum block width 150 mm.'):
    response=client.post('/api/ai-design/tasks',json=dict(inputs=inputs(client,requirements)),headers=HEADERS)
    assert response.status_code==200,response.text
    task=response.json()
    response=client.post(f'/api/ai-design/tasks/{task["id"]}/analyze',json=dict(expected_revision=task['revision'],provider='mock-example'),headers=HEADERS)
    assert response.status_code==200,response.text
    return response.json()['task'],response.json()['run']


def selection_request(task,run,**options):
    definition=catalog.definition('metric:lib109:cavity:352')
    selected=dict(definition_key='native:metric:lib109:cavity:352',definition_sha256=service.digest(definition.model_dump()),
                  zone_ports={'port1':'RV1_P','port2':'RV1_T'},decision='QA fixture: select existing VC08-2 geometry and map P/T for draft testing only.')
    return GenerationRequest(expected_revision=task['revision'],run_id=run['id'],options={
        'bindings':{'VALVE_RV1':selected},'max_attempts':2,**options})


def reading(text='P on left.'):
    source=dict(kind='schematic',document=1,page=1,bbox=[.2,.2,.4,.4],quote='RV1')
    def obs(value):return dict(value=value,status='clear',source=source)
    return dict(components=[dict(label='RV1',source=source,functional_type=obs('pressure_relief'),manufacturer=obs('HydraForce'),
                                model=obs('unverified fixture model'),cavity=obs('VC08-2'),
                                ports=[dict(label='1',net=obs('P')),dict(label='2',net=obs('T'))])],
                external_ports=[dict(label='P',net=obs('P')),dict(label='T',net=obs('T'))],
                requirements=[dict(quote=text,category='port_face',targets=['P'],property='preferred_face',operator='equal',value='left')])


def test_semantic_contract_computes_ids_and_exact_requirement_offsets(client):
    original='  P on left.\nKeep coils accessible.'
    task=TaskInput.model_validate(inputs(client,original))
    result=normalize(CircuitReading.model_validate(reading()),task,{'DOC1':1})
    assert len(result.components)==1 and len(result.ports)==4 and len(result.nets)==2
    source=next(e for e in result.evidence if e.kind=='user_requirement')
    assert source.requirement_span==(2,12) and original[slice(*source.requirement_span)]=='P on left.'
    assert any('Keep coils accessible' in u.description for u in result.unresolved)
    malformed=reading();malformed['requirements'][0]['quote']='Translated or fabricated instruction'
    with pytest.raises(ValueError):normalize(CircuitReading.model_validate(malformed),task,{'DOC1':1})
    malformed=reading();malformed['components'][0]['cavity']['source']['page']=2
    with pytest.raises(ValueError):normalize(CircuitReading.model_validate(malformed),task,{'DOC1':1})
    malformed=reading();malformed['components'][0]['cavity_dimensions']=[1,2,3]
    with pytest.raises(ValueError):CircuitReading.model_validate(malformed)


def test_settings_are_operator_local_redacted_and_require_new_endpoint_key(client):
    assert not client.get('/api/ai-design/settings').json()['ready']
    secret='fixture-secret-never-return'
    settings=dict(base_url='https://model.example/v1',model='operator-chosen-vision',api_key=secret,enabled=True)
    response=client.post('/api/ai-design/settings',json=settings,headers=HEADERS)
    assert response.status_code==200 and response.json()['ready']
    assert secret not in response.text and 'api_key' not in response.json()
    assert secret not in client.get('/api/ai-design/settings').text
    assert client.get('/api/ai-design/providers').json()[-1]['model']=='operator-chosen-vision'
    response=client.post('/api/ai-design/settings',json={**settings,'base_url':'https://other.example','api_key':''},headers=HEADERS)
    assert response.status_code==422 and secret not in response.text
    response=client.post('/api/ai-design/settings',json={**settings,'base_url':'http://remote.example'},headers=HEADERS)
    assert response.status_code==422 and secret not in response.text
    remote=TestClient(app,client=('192.168.1.44',3333))
    assert remote.get('/api/ai-design/settings',headers={'Host':'127.0.0.1:8765'}).status_code==403
    assert client.post('/api/ai-design/settings/clear-key',json={},headers=HEADERS).json()['key_present'] is False


def test_pdf_pages_render_locally_and_preserve_identity(client):
    pages=[Image.new('RGB',(300,200),color) for color in ('white','lightblue')]
    pdf=io.BytesIO();pages[0].save(pdf,format='PDF',save_all=True,append_images=pages[1:])
    data=pdf.getvalue();doc=DocumentContent('DOC_PDF','application/pdf',hashlib.sha256(data).hexdigest(),data)
    rendered=render(doc,max_pages=2,max_side=1200)
    assert [p['page'] for p in rendered]==[1,2]
    assert all(p['data'].startswith(b'\x89PNG') and p['sha256']==hashlib.sha256(p['data']).hexdigest() for p in rendered)
    with pytest.raises(ValueError,match='configured limit'):render(doc,max_pages=1,max_side=1200)
    invalid=b'%PDF-1.7\nnot a pdf\n%%EOF'
    bad=DocumentContent('DOC_BAD','application/pdf',hashlib.sha256(invalid).hexdigest(),invalid)
    with pytest.raises(ValueError,match='could not be rendered'):render(bad,max_pages=2,max_side=1200)


@pytest.fixture
def http_provider():
    state={'requests':[],'status':200,'results':[]}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            state['requests'].append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length']))),self.headers.get('Authorization')))
            self.send_response(state['status']);self.send_header('Content-Type','application/json');self.end_headers()
            response=state['results'].pop(0) if state['results'] else {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(reading())}}],
                                                                   'usage':{'prompt_tokens':111,'completion_tokens':222}}
            self.wfile.write(json.dumps(response).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield state,'http://127.0.0.1:'+str(server.server_port)
    finally:server.shutdown();thread.join();server.server_close()


def test_real_multimodal_transport_sends_documents_requirements_and_normalizes(client,http_provider):
    state,url=http_provider
    task=TaskInput.model_validate(inputs(client,'P on left.'))
    adapter=MultimodalProvider(config.ProviderSettings(base_url=url,model='custom-test-model',api_key=SecretStr('test-token'),enabled=True,contract_retries=1))
    response=adapter.analyze(AnalysisRequest(inputs=task,documents=service.verified_documents(task),result_schema={}))
    assert len(response.representation['components'])==1 and len(response.representation['nets'])==2
    path,body,authorization=state['requests'][0]
    assert path=='/chat/completions' and body['model']=='custom-test-model' and authorization=='Bearer test-token'
    content=body['messages'][1]['content']
    assert 'P on left.' in content[0]['text']
    assert base64.b64decode(next(x['image_url']['url'].split(',',1)[1] for x in content if x['type']=='image_url')).startswith(b'\x89PNG')
    assert response.input_tokens==111 and response.output_tokens==222
    assert response.metadata['requests']==1 and len(response.metadata['document_pages'])==1
    assert 'test-token' not in json.dumps(response.metadata)
    # The same adapter contract supports shape retry, but auth failures are not retried.
    state['results']=[{'choices':[{'message':{'content':'not JSON'}}]}]
    before=len(state['requests']);again=adapter.analyze(AnalysisRequest(inputs=task,documents=service.verified_documents(task),result_schema={}))
    assert again.metadata['requests']==2 and len(state['requests'])==before+2
    state['status']=401;before=len(state['requests'])
    with pytest.raises(ProviderFailure) as exc:adapter.analyze(AnalysisRequest(inputs=task,documents=service.verified_documents(task),result_schema={}))
    assert exc.value.code=='PROVIDER_AUTH' and len(state['requests'])==before+1


def test_native_generation_is_editable_traceable_and_does_not_write_projects_or_library(client,tmp_path):
    task,run=analyzed(client)
    request=selection_request(task,run)
    ready=generation.preflight(task['id'],request)
    assert ready['ready'],ready['blocked']
    result=generation.generate(task['id'],request)
    assert result['status']=='draft',result
    assert result['geometry_failures']==0,result['attempts']
    from manifold.schema import Design
    design=Design.model_validate(result['design'])
    assert len(design.components)==1 and len([f for f in design.features if f.kind=='port'])==2
    assert design.block.width<=150 and design.origin.ai_trace.original_requirements==run['inputs']['engineering_requirements']
    assert design.origin.ai_trace.analysis_id==task['id'] and design.origin.ai_trace.run_id==run['id']
    assert not (tmp_path/'projects'/'saved').exists() and not (tmp_path/'projects'/'library').exists()
    assert design.library[0].native.source_sha256==catalog.definition('metric:lib109:cavity:352').native.source_sha256
    assert design.review_items and any(i.status=='open' for i in design.review_items)
    # The existing import/save/build path handles the generated Design without a parallel project store.
    imported=client.post('/api/import-project',json=design.model_dump(),headers=HEADERS)
    assert imported.status_code==200,imported.text
    project=projects.save(design)
    rebuilt=projects.build(project['project_id'],project['revision'])
    assert rebuilt['build']['counts']['FAIL']==0
    build_folder=store.OUTPUT/'builds'/rebuilt['build']['build_id']
    assert (build_folder/'production.step').is_file()
    restored=projects.read(project['project_id'])['design']
    assert restored['origin']['ai_trace']==design.origin.ai_trace.model_dump()


def test_generation_requires_real_bindings_and_rejects_stale_or_conflicting_intent(client):
    task,run=analyzed(client)
    blank=GenerationRequest(expected_revision=task['revision'],run_id=run['id'])
    result=generation.preflight(task['id'],blank)
    assert not result['ready'] and any('choose an existing cavity' in x for x in result['blocked'])
    request=selection_request(task,run)
    request.options.bindings['VALVE_RV1'].zone_ports={'port1':'RV1_P','port2':'RV1_P'}
    assert not generation.preflight(task['id'],request)['ready']
    changed=TaskInput.model_validate(task['inputs']);changed.engineering_requirements+=' P and T must remain separate internally.'
    task=service.save(changed,task['id'],task['revision'])
    with pytest.raises(ValueError,match='stale'):
        generation.preflight(task['id'],GenerationRequest(expected_revision=task['revision'],run_id=run['id']))


def test_required_face_and_forbidden_drilling_constraints_survive_generation_and_edit(client):
    task,run=analyzed(client,'P on left. T on right. Avoid cross drilling from the top face. Maximum block width 150 mm.')
    req=selection_request(task,run)
    plan=generation.prepare(TaskInput.model_validate(task['inputs']),run['result'],req.options)
    design,_,_=generation.candidate(plan,'a'*32,0)
    assert design.constraints.forbidden_drilling_faces==['top']
    from manifold.routing import resolve_design,authorize_generated_contacts
    from manifold.geometry import build_geometry
    from manifold.validation import validate
    resolved,_=resolve_design(design);g=build_geometry(resolved);authorize_generated_contacts(resolved,g)
    report=validate(resolved,g)
    assert not any(c['rule']=='drilling_face_constraint' and c['status']=='FAIL' for c in report['checks'])
    drilling=next(f for f in resolved.features if f.kind=='drilling')
    resolved.constraints.forbidden_drilling_faces.append(drilling.face)
    assert any(c['rule']=='drilling_face_constraint' and c['status']=='FAIL' for c in validate(resolved,g)['checks'])


def test_jobs_finish_and_restart_status_does_not_claim_success(client,monkeypatch):
    task,run=analyzed(client)
    monkeypatch.setattr(service,'analyze',lambda *args:dict(task=task,run=run))
    job=jobs.start(task['id'],'analyze',dict(expected_revision=task['revision'],provider='mock-example'))
    for _ in range(100):
        state=jobs.read(job['id'])
        if state['status']=='completed':break
        time.sleep(.01)
    assert state['status']=='completed' and 'request' not in state
    fake=dict(id='f'*32,task_id=task['id'],operation='analyze',status='running',process='old',request={},message='old',result=None)
    store.atomic_json(jobs.path(fake['id']),fake)
    assert jobs.read(fake['id'])['status']=='interrupted'


def test_bottom_ports_generate_without_drilling_through_other_cartridge_zones(client):
    task,run=analyzed(client,'P and T on bottom. Maximum block width 150 mm. Avoid cross drilling from the top face.')
    result=generation.generate(task['id'],selection_request(task,run,max_attempts=4))
    assert result['status']=='draft',result
    assert all(f['face']=='bottom' for f in result['design']['features'] if f['kind']=='port')
    assert result['geometry_failures']==0,result['attempts']
    assert result['design']['constraints']['forbidden_drilling_faces']==['top']
    assert result['attempts'][0]['geometry_failures']>0 and result['selected_attempt']>0

def test_intent_keeps_unmatched_targets_and_terminal_loads_explicit(client):
    from manifold.ai_design.intent import interpret, parameter_for
    from manifold.ai_design.generation_models import GenerationOptions
    task, run = analyzed(client)
    result = copy.deepcopy(run['result'])
    face = next(i for i in result['design_intent'] if i['category'] == 'port_face')
    face['target_labels'].append('DOES_NOT_EXIST')
    result['claims'].append(dict(id='LOAD',subject_id='EXT_P',predicate='flow',value=12,unit='l/min',kind='schematic',status='confirmed'))
    # Use the actual external P identity from the contract.
    terminal = next(p['id'] for p in result['ports'] if p['component_id'] is None and any(c['subject_id']==p['id'] and c['predicate']=='label' and c['value']=='P' for c in result['claims']))
    result['claims'][-1]['subject_id'] = terminal
    settings = interpret(result, GenerationOptions())
    assert next(r for r in settings['dispositions'] if r['intent_id']==face['id'])['status']=='review_required'
    net = next(n for n in result['nets'] if terminal in n['members'])
    assert parameter_for(result,settings['flows'],net)==12
    result['claims'][-1]['kind']='ai_inference'
    assert not interpret(result,GenerationOptions())['flows']

def test_corrupt_settings_can_be_replaced_without_exposing_old_contents(client):
    config.path().parent.mkdir(parents=True)
    config.path().write_text('invalid-private-configuration',encoding='utf-8')
    response=client.get('/api/ai-design/settings')
    assert response.status_code==200 and response.json()['configuration_warning']
    assert 'invalid-private-configuration' not in response.text
    assert client.get('/api/ai-design/providers').status_code==200
    response=client.post('/api/ai-design/settings',json=dict(base_url='http://127.0.0.1:8999/v1',model='user-model',anonymous=True,enabled=True),headers=HEADERS)
    assert response.status_code==200 and response.json()['ready']
