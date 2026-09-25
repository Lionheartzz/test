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
from manifold import store, projects
from manifold.demo import CAVITY_ID
from manifold.engineering_db import get_definition, search_threads
from manifold.server import app
from manifold.ai_design import config, service, generation, jobs
from manifold.ai_design.generation_models import GenerationOptions, GenerationRequest
from manifold.ai_design.library_resolution import exact_port_candidates
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
    definition=get_definition(CAVITY_ID)
    selected=dict(definition_key='db:'+CAVITY_ID,definition_sha256=service.digest(definition.model_dump()),
                  zone_ports={'port1':'RV1_P','port2':'RV1_T'},decision='QA fixture: select existing VC08-2 geometry and map P/T for draft testing only.')
    return GenerationRequest(expected_revision=task['revision'],run_id=run['id'],options={
        'bindings':{'VALVE_RV1':selected},
        'provisional_ports':{'EXT_P':'QA explicitly approves a one-off straight bore.','EXT_T':'QA explicitly approves a one-off straight bore.'},
        'max_attempts':2,**options})


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


def test_ai_preserves_mixed_port_standards_and_terminal_dispositions(client):
    task=TaskInput.model_validate(inputs(client))
    assert {row['unit'] for row in exact_port_candidates(task,'1/4-18 NPT')}=={'metric','inch'}
    assert exact_port_candidates(task,'1/4-18 NPTF')
    assert all('NPTF' in row['label'].upper() or '[SPD]' in row['label'].upper()
               for row in exact_port_candidates(task,'1/4-18 NPTF'))

    source=dict(kind='schematic',document=1,page=1,bbox=[.2,.2,.4,.4],quote='RV1')
    unknown=dict(value=None,status='unknown',source=dict(kind='unknown'))
    raw=reading()
    raw['external_ports'][0].update(net=unknown,disposition='blocked')
    raw['external_ports'][1].update(net=unknown,disposition='terminated')
    result=normalize(CircuitReading.model_validate(raw),task,{'DOC1':1})
    terminals=result.ports[-2:]
    assert [row.disposition for row in terminals]==['blocked','terminated']
    assert all(row.id not in {member for net in result.nets for member in net.members} for row in terminals)
    assert not any(row.subject_ids and row.subject_ids[0] in {p.id for p in terminals} for row in result.unresolved)
    with pytest.raises(ValueError,match='Blocked or terminated'):
        generation.topology(result.model_dump(),GenerationOptions(
            net_overrides={terminals[0].id:result.nets[0].id},topology_decision='Try routing a blocked port'))


def test_settings_are_operator_local_redacted_and_require_new_endpoint_key(client,monkeypatch):
    permissions=[];monkeypatch.setattr(config,'POSIX',True)
    monkeypatch.setattr(config.os,'chmod',lambda path,mode:permissions.append((Path(path),mode)))
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
    assert any(path.name=='private' and mode==0o700 for path,mode in permissions)
    assert sum(path.name=='ai-provider.json' and mode==0o600 for path,mode in permissions)==2


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


def test_ai_generation_is_editable_and_uses_sqlite_ids_without_embedded_library(client,tmp_path):
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
    assert design.block.width<=150 and design.origin.method=='ai-assisted'
    assert not (tmp_path/'projects'/'saved').exists() and not (tmp_path/'projects'/'library').exists()
    assert all(f.cavity_id==CAVITY_ID for f in design.features if f.kind=='cavity')
    assert 'library' not in design.model_dump() and 'ai_trace' not in design.origin.model_dump()
    assert design.review_items == []
    assert not any(key in run['result'] for key in ('claims','evidence','knowledge_references'))
    # The existing import/save/build path handles the generated Design without a parallel project store.
    imported=client.post('/api/import-project',json=design.model_dump(),headers=HEADERS)
    assert imported.status_code==200,imported.text
    definitions=imported.json()['engineering']['definitions']
    assert all(f.definition in definitions for f in design.features if f.definition)
    assert all(definitions[f.definition]['cutting_primitives'] for f in design.features if f.definition)
    broken=design.model_copy(deep=True);next(f for f in broken.features if f.kind=='cavity').cavity_id='missing_ai_cavity'
    rejected=client.post('/api/import-project',json=broken.model_dump(),headers=HEADERS)
    assert rejected.status_code==409 and 'missing_ai_cavity' in rejected.text
    project=projects.save(design)
    rebuilt=projects.build(project['project_id'],project['revision'])
    assert rebuilt['build']['counts']['FAIL']==0
    build_folder=store.OUTPUT/'builds'/rebuilt['build']['build_id']
    assert (build_folder/'production.step').is_file()
    restored=projects.read(project['project_id'])['design']
    assert restored['origin']['method']=='ai-assisted' and 'library' not in restored


def test_generation_requires_real_bindings_and_rejects_stale_or_conflicting_intent(client):
    task,run=analyzed(client)
    blank=GenerationRequest(expected_revision=task['revision'],run_id=run['id'])
    result=generation.preflight(task['id'],blank)
    assert not result['ready'] and result['blocked']
    assert any('Custom Straight Bore' in item for item in result['blocked'])
    request=selection_request(task,run)
    request.options.bindings['VALVE_RV1'].zone_ports={'port1':'RV1_P','port2':'RV1_P'}
    assert not generation.preflight(task['id'],request)['ready']
    changed=TaskInput.model_validate(task['inputs']);changed.engineering_requirements+=' P and T must remain separate internally.'
    task=service.save(changed,task['id'],task['revision'])
    with pytest.raises(ValueError,match='stale'):
        generation.preflight(task['id'],GenerationRequest(expected_revision=task['revision'],run_id=run['id']))


def test_ai_mounting_and_provisional_ports_keep_explicit_engineering_standards(client):
    task,run=analyzed(client)
    inputs_model=TaskInput.model_validate(task['inputs'])
    result=copy.deepcopy(run['result'])
    external=next(row for row in result['ports'] if row['id']=='EXT_P')
    external['facts']['port_specification']='1/4-18 NPT'
    external.setdefault('fact_kinds',{})['port_specification']='schematic'
    automatic=generation.prepare(inputs_model,result,GenerationOptions(
        provisional_ports={'EXT_T':'Engineer approved a one-off bore.'}))
    resolved_port=next(row for row in automatic['external'] if row['id']=='EXT_P')
    assert resolved_port['automatic'] and resolved_port['definition'].unit_system=='metric'
    unified=next(row for row in search_threads('',usable_only=True,limit=500)
                 if row['display_name']=='3/8-16 UNC-2B' and row['unit_system']=='inch')
    options=GenerationOptions(
        provisional_ports={'EXT_P':'Engineer requested a one-off bore.','EXT_T':'Engineer requested a one-off bore.'},
        threaded_mounting_holes=[dict(thread_definition_id=unified['id'],face='top',u=20,v=20,depth=20,thread_depth=16)],
        mounting_decision='Explicit UNC thread and position entered by the engineer.')
    plan=generation.prepare(inputs_model,result,options)
    assert plan['mounting'][0]['thread']['unit_system']=='inch'
    assert any('cannot be replaced by a straight bore' in row for row in plan['blocked'])


def test_imported_ai_threaded_draft_has_thread_facts_before_first_preview(client):
    from manifold.schema import Design
    thread=next(row for row in search_threads('',usable_only=True,limit=500)
                if row['display_name']=='M10x1.5-6H' and row['tap_diameter_mm']==pytest.approx(8.0))
    design=Design(name='AI threaded draft',project_context='metric',
                  block=dict(length=80,width=80,height=80,material='QA'),features=[
                      dict(id='MH1',kind='mounting',face='top',u=25,v=25,mounting_mode='threaded',
                           thread_definition_id=thread['id'],thread_depth=16,depth=20)])
    imported=client.post('/api/import-project',json=design.model_dump(),headers=HEADERS)
    assert imported.status_code==200,imported.text
    hydrated=imported.json()['engineering']['threads'][thread['id']]
    assert hydrated['display_name']=='M10x1.5-6H' and hydrated['tap_diameter_mm']==pytest.approx(8.0)
    preview=client.post('/api/preview-solid',json=imported.json()['design'],headers=HEADERS)
    assert preview.status_code==200,preview.text[:500]
    project=projects.save(design)
    reopened=client.get('/api/projects/'+project['project_id'])
    assert reopened.status_code==200,reopened.text
    assert reopened.json()['design']['features'][0]['thread_definition_id']==thread['id']
    assert reopened.json()['engineering']['threads'][thread['id']]['display_name']==hydrated['display_name']


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
    monkeypatch.setattr(jobs,'_active',None)
    assert jobs.current()['id']==fake['id'] and jobs.current()['status']=='interrupted'


def test_intent_keeps_unmatched_targets_and_terminal_loads_explicit(client):
    from manifold.ai_design.intent import interpret, parameter_for
    from manifold.ai_design.generation_models import GenerationOptions
    task, run = analyzed(client)
    result = copy.deepcopy(run['result'])
    face = next(i for i in result['design_intent'] if i['category'] == 'port_face')
    face['value'] = 'left'
    face['target_labels'].append('DOES_NOT_EXIST')
    # Use the actual external P identity from the compact persisted contract.
    port = next(p for p in result['ports'] if p['id']=='EXT_P')
    port['label'] = 'P'
    terminal = port['id']
    port['facts']['flow'] = 12
    port['fact_units']['flow'] = 'l/min'
    port['fact_kinds']['flow'] = 'schematic'
    settings = interpret(result, GenerationOptions())
    assert next(r for r in settings['dispositions'] if r['intent_id']==face['id'])['status']=='review_required'
    net = next(n for n in result['nets'] if terminal in n['members'])
    assert parameter_for(result,settings['flows'],net)==12
    port['fact_kinds']['flow']='ai_inference'
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
