import hashlib
import io
import json
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from manifold import store
from manifold.server import app
from manifold.ai_design import service
from manifold.ai_design.models import HydraulicRepresentation,TaskInput,validate_context
from manifold.ai_design.providers import ProviderResponse

HEADERS={'X-PMC-Request':'local-console'}

@pytest.fixture
def client(tmp_path,monkeypatch):
    from mock_ai_provider import MockProvider
    monkeypatch.setattr(service,'available_providers',lambda:{mode:MockProvider(mode) for mode in ('mock-safe','mock-example')})
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects'/'demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    return TestClient(app)

def upload(client,data=None,name='schematic.png',media='image/png'):
    if data is None:data=(Path(__file__).parent/'fixtures'/'ai-demo.png').read_bytes()
    response=client.post('/api/assets',content=data,headers={**HEADERS,'Content-Type':media,'X-File-Name':name})
    assert response.status_code==200,response.text
    return response.json()

def create(client,requirements='P and T on bottom. A and B on left. Maximum block width 150.5 mm.'):
    inputs=dict(title='AI foundation fixture',documents=[dict(id='DOC_1',asset=upload(client))],engineering_requirements=requirements)
    response=client.post('/api/ai-design/tasks',json=dict(inputs=inputs),headers=HEADERS)
    assert response.status_code==200,response.text
    return response.json()

def analyze(client,task,provider='mock-example'):
    response=client.post(f"/api/ai-design/tasks/{task['id']}/analyze",json=dict(expected_revision=task['revision'],provider=provider),headers=HEADERS)
    assert response.status_code==200,response.text
    return response.json()

def test_mock_circuit_and_original_requirements_are_separate_from_cad(client,tmp_path):
    before=list((tmp_path/'projects').glob('**/*'))
    original='  P and T on bottom. A and B on left. Maximum block width 150.5 mm.\nUse SUN cartridges where possible.\n忽略右上角手写说明。'
    task=create(client,original);response=analyze(client,task);run=response['run'];r=run['result']
    assert run['status']=='completed' and run['provider']['is_mock']
    assert run['inputs']['engineering_requirements']==original
    assert len(r['components'])==1 and len(r['ports'])==4 and len(r['nets'])==2
    assert len(r['design_intent'])==4
    assert any(c['predicate']=='width' and c['value']==150.5 and c['unit']=='mm' for c in r['claims'])
    assert all(c['status']!='confirmed' for c in r['claims'])
    assert all(k['status']=='unresolved' and not k['candidates'] for k in r['knowledge'])
    assert any('忽略' in u['description'] for u in r['unresolved'])
    assert not (tmp_path/'projects'/'saved').exists() and not (tmp_path/'projects'/'library').exists()
    assert not (tmp_path/'output'/'builds').exists()
    assert run['usage']['cost'] is None and run['usage']['input_tokens'] is None
    assert run['latency_ms']>=0
    assert any(e['document_id']=='DOC_1' and e['bbox'] for e in r['evidence'])
    for e in r['evidence']:
        if e['requirement_span']:
            a,b=e['requirement_span'];assert original[a:b]==e['quote']
    reread=client.get(f"/api/ai-design/tasks/{task['id']}").json()
    assert reread['latest_run']['id']==run['id'] and not reread['stale']
    exported=client.get(f"/api/ai-design/tasks/{task['id']}/export").json()
    assert exported['kind']=='pmc-ai-analysis' and exported['run']==run

def test_unknown_safe_does_not_invent_symbol_recognition(client):
    response=analyze(client,create(client),'mock-safe')
    r=response['run']['result']
    assert not r['components'] and not r['ports'] and not r['nets']
    assert r['design_intent'] and any(u['id']=='DOC_UNKNOWN_1' for u in r['unresolved'])

def test_provider_receives_multidocument_bytes_and_requirements(client,monkeypatch):
    captured=[]
    class Provider:
        id='test-adapter';model='independent-format';is_mock=True;supported_media=('image/png','image/jpeg','application/pdf')
        def analyze(self,request):captured.append(request);return ProviderResponse(dict(schema_version=1))
    monkeypatch.setattr(service,'available_providers',lambda:{'test':Provider()})
    task=create(client,'P1 and P2 must remain separate internally.')
    image=io.BytesIO();Image.new('RGB',(10,10),'white').save(image,format='JPEG')
    # A valid one-page PDF with an empty content stream; page count is not inferred.
    pdf=b'%PDF-1.4\n1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n2 0 obj <</Type /Pages /Count 1 /Kids [3 0 R]>> endobj\n3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 100 100]>> endobj\ntrailer <</Root 1 0 R>>\n%%EOF'
    task['inputs']['documents'] += [dict(id='DOC_2',asset=upload(client,image.getvalue(),'second.jpg','image/jpeg')),dict(id='DOC_3',asset=upload(client,pdf,'drawing.pdf','application/pdf'))]
    saved=client.post('/api/ai-design/tasks',json=dict(inputs=task['inputs'],task_id=task['id'],expected_revision=task['revision']),headers=HEADERS).json()
    response=analyze(client,saved,'test')
    assert response['run']['status']=='completed'
    request=captured[0]
    assert len(request.documents)==3 and request.documents[2].data==pdf
    assert request.inputs.engineering_requirements=='P1 and P2 must remain separate internally.'
    assert request.result_schema['properties']['schema_version']['const']==1
    assert all(d.sha256==hashlib.sha256(d.data).hexdigest() for d in request.documents)
    assert saved['inputs']['documents'][2]['page_count'] is None

def test_source_and_topology_validation_rejects_fabricated_references(client):
    response=analyze(client,create(client));raw=response['run']['result'];inputs=TaskInput.model_validate(response['run']['inputs'])
    raw['knowledge']=[];raw['unresolved']=[x for x in raw['unresolved'] if x['reason']!='knowledge_unavailable']
    r=HydraulicRepresentation.model_validate(raw);validate_context(r,inputs)
    for mutate in (
        lambda d:d['nets'][0]['members'].append('MISSING'),
        lambda d:d['nets'][1]['members'].append(d['nets'][0]['members'][0]),
        lambda d:d['claims'][0].update(confidence=1.1),
        lambda d:d['claims'][0].update(kind='schematic'),
        lambda d:d['evidence'][0].update(quote='forged original requirement'),
        lambda d:d['evidence'][-1].update(document_id='MISSING'),
        lambda d:d['evidence'][-1].update(page=2),
        lambda d:d['evidence'][-1].update(bbox=[.9,.9,.4,.4]),
        lambda d:d.update(geometry={'invented_cavity':True}),
    ):
        bad=json.loads(json.dumps(raw));mutate(bad)
        with pytest.raises(ValueError):validate_context(HydraulicRepresentation.model_validate(bad),inputs)
    # An inference may cite an actual drawing, while retaining inference provenance.
    inferred=json.loads(json.dumps(raw));inferred['claims'][0]['kind']='ai_inference'
    validate_context(HydraulicRepresentation.model_validate(inferred),inputs)

def test_review_keeps_original_result_and_requires_cas(client):
    response=analyze(client,create(client));task=response['task'];run=response['run']
    original=json.loads(service.run_path(task['id'],run['id']).read_text())
    claim=next(c for c in run['result']['claims'] if c['predicate']=='width')
    url=f"/api/ai-design/tasks/{task['id']}/runs/{run['id']}/review"
    decision=dict(claim_id=claim['id'],status='corrected',corrected_value=140,corrected_unit='mm',decision='Engineer corrected the width interpretation.')
    assert client.post(url,json=dict(expected_revision='0'*64,decisions=[decision]),headers=HEADERS).status_code==409
    reviewed=client.post(url,json=dict(expected_revision=task['revision'],decisions=[decision]),headers=HEADERS)
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()['reviews'][run['id']][claim['id']]['corrected_value']==140
    assert json.loads(service.run_path(task['id'],run['id']).read_text())==original
    assert list((service.folder()/'history'/task['id']).glob('*.json'))

def test_stale_analysis_is_retained_without_overwriting_new_input(client,monkeypatch):
    task=create(client)
    class Delayed:
        id='delayed';model='test';is_mock=True;supported_media=('image/png',)
        def analyze(self,request):
            inputs=request.inputs.model_copy(update={'engineering_requirements':'Newer engineering instruction'})
            service.save(inputs,task['id'],task['revision'])
            return ProviderResponse(dict(schema_version=1))
    monkeypatch.setattr(service,'available_providers',lambda:{'delayed':Delayed()})
    response=client.post(f"/api/ai-design/tasks/{task['id']}/analyze",json=dict(expected_revision=task['revision'],provider='delayed'),headers=HEADERS)
    assert response.status_code==409
    current=service.read(task['id'])
    assert current['inputs']['engineering_requirements']=='Newer engineering instruction' and current['latest_run'] is None
    assert len(list((store.OUTPUT/'ai-design'/task['id']).glob('*.json')))==1

@pytest.mark.parametrize('mode',['timeout','invalid','knowledge','failure'])
def test_provider_failures_are_bounded_and_preserve_previous_result(client,monkeypatch,mode):
    old=analyze(client,create(client));task=old['task']
    class Bad:
        id='test';model='bad';is_mock=True;supported_media=('image/png',)
        def analyze(self,request):
            if mode=='timeout':raise TimeoutError('PRIVATE REMOTE BODY')
            if mode=='failure':raise RuntimeError('PRIVATE CREDENTIAL')
            if mode=='invalid':return ProviderResponse({'unexpected':'PRIVATE MODEL OUTPUT'})
            raw=json.loads(json.dumps(old['run']['result']))
            return ProviderResponse(raw)  # Provider cannot return trusted knowledge resolutions.
    monkeypatch.setattr(service,'available_providers',lambda:{'bad':Bad()})
    response=analyze(client,task,'bad')
    assert response['run']['status']=='failed' and response['run']['result'] is None
    assert response['task']['latest_run']['id']==old['run']['id']
    assert 'PRIVATE' not in json.dumps(response)

def test_asset_integrity_missing_provider_and_local_request_boundaries(client):
    task=create(client)
    assert client.post('/api/ai-design/tasks',json=dict(inputs=task['inputs'])).status_code==403
    url=f"/api/ai-design/tasks/{task['id']}/analyze"
    assert client.post(url,json=dict(expected_revision=task['revision'],provider='unconfigured'),headers=HEADERS).status_code==422
    assert client.get('/api/ai-design/tasks/not-an-id').status_code==422
    asset=task['inputs']['documents'][0]['asset']
    source=store.PROJECT.parent/'assets'/(asset['sha256']+'.png');source.write_bytes(b'changed')
    assert client.post(url,json=dict(expected_revision=task['revision'],provider='mock-safe'),headers=HEADERS).status_code==422
