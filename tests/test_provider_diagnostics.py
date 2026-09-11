"""Provider regressions use in-process HTTP transports; never the configured paid endpoint."""
import asyncio
import copy
import json
import time
import httpx
import pytest
from pydantic import SecretStr
from test_ai_generation import client, inputs, analyzed, reading, HEADERS
from manifold import store
from manifold.ai_design import config, service, jobs
from manifold.ai_design.providers import AnalysisRequest, ProviderFailure, ProviderResponse
from manifold.ai_design.remote import MultimodalProvider
from manifold.ai_design.models import TaskInput
from manifold.ai_design.diagnostics import normalize_usage
from manifold.ai_design.transport_controls import reasoning_parameters
from manifold.ai_design.semantic import prompt_schema, CircuitReading

SECRET='fixture-private-provider-body'
REAL_ASYNC_CLIENT=httpx.AsyncClient


def request_for(client):
    task=TaskInput.model_validate(inputs(client,'P on left.'))
    return AnalysisRequest(inputs=task,documents=service.verified_documents(task),result_schema={})


def response(content=None,usage=None,finish='stop'):
    return {'choices':[{'finish_reason':finish,'message':{'content':json.dumps(reading()) if content is None else content,
                                                       'reasoning_content':SECRET}}],
            'usage':usage}


def transport(monkeypatch,handler):
    calls=[]
    async def wrapped(request):
        calls.append(json.loads(request.content))
        return await handler(request)
    mock=httpx.MockTransport(wrapped)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:REAL_ASYNC_CLIENT(transport=mock,**kwargs))
    return calls


def adapter(**changes):
    return MultimodalProvider(config.ProviderSettings(base_url='https://fixture.invalid/v1',model='operator-model',
                              api_key=SecretStr(SECRET),enabled=True,**changes))


@pytest.mark.parametrize('tokens',[None,1,32769,131072,100000000000000000003])
def test_output_budget_passed_exactly_or_omitted(client,monkeypatch,tokens):
    async def handle(request):return httpx.Response(200,json=response())
    calls=transport(monkeypatch,handle)
    request=request_for(client)
    a=adapter(max_tokens=tokens)
    a.analyze(request)
    assert calls[0].get('max_tokens')==tokens
    assert ('max_tokens' in calls[0])==(tokens is not None)
    assert a.settings.max_tokens==tokens
    assert len(calls)==1
    assert 'thinking' not in calls[0] and 'reasoning_effort' not in calls[0]


def test_settings_budget_has_no_browser_precision_loss_or_pmc_ceiling(client):
    huge='100000000000000000003'
    result=client.post('/api/ai-design/settings',json={'max_tokens':huge},headers=HEADERS)
    assert result.status_code==200 and result.json()['max_tokens']==huge
    assert config.read().max_tokens==int(huge)
    for invalid in (-1,0,1.5,True,'1e5'):
        assert client.post('/api/ai-design/settings',json={'max_tokens':invalid},headers=HEADERS).status_code==422
    assert client.post('/api/ai-design/settings',json={'max_tokens':None},headers=HEADERS).json()['max_tokens'] is None


@pytest.mark.parametrize('dialect,mode,effort,expected',[
    ('provider_default','provider_default','provider_default',{}),
    ('thinking','disabled','provider_default',{'thinking':{'type':'disabled'}}),
    ('thinking','enabled','low',{'thinking':{'type':'enabled'},'reasoning_effort':'low'}),
    ('reasoning_effort','disabled','provider_default',{'reasoning_effort':'none'}),
    ('reasoning_effort','enabled','high',{'reasoning_effort':'high'}),
])
def test_explicit_reasoning_dialects_and_operation_overrides(client,monkeypatch,dialect,mode,effort,expected):
    async def handle(request):return httpx.Response(200,json=response())
    calls=transport(monkeypatch,handle)
    a=adapter(reasoning={'dialect':'thinking','mode':'enabled','effort':'max'},
              operation_reasoning={'hydraulic_understanding':{'dialect':dialect,'mode':mode,'effort':effort}})
    r=a.analyze(request_for(client))
    assert {k:calls[0][k] for k in ('thinking','reasoning_effort') if k in calls[0]}==expected
    assert r.diagnostics['reasoning']=={'dialect':dialect,'mode':mode,'effort':effort}


def test_unsupported_controls_are_visible_and_no_model_name_detection():
    a=adapter(reasoning={'dialect':'provider_default','mode':'disabled'})
    chosen,body,warnings,state=reasoning_parameters(a.settings,'hydraulic_understanding')
    assert body=={} and state=='not_sent' and 'reasoning_dialect_required' in warnings
    a=adapter(reasoning={'dialect':'reasoning_effort','mode':'enabled'})
    assert 'effort_required' in reasoning_parameters(a.settings,'hydraulic_understanding')[2]


def test_truncation_retains_usage_before_parsing_and_never_retries(client,monkeypatch):
    usage={'prompt_tokens':500,'completion_tokens':32000,'completion_tokens_details':{'reasoning_tokens':31990},
           'prompt_cache_hit_tokens':100,'total_tokens':32500}
    async def handle(request):return httpx.Response(200,json=response('{',usage,'length'))
    calls=transport(monkeypatch,handle)
    with pytest.raises(ProviderFailure) as exc:adapter(contract_retries=1).analyze(request_for(client))
    d=exc.value.diagnostics
    assert exc.value.code=='PROVIDER_OUTPUT_TRUNCATED' and len(calls)==1
    assert d['usage']==dict(input_tokens=500,output_tokens=32000,reasoning_tokens=31990,cached_tokens=100,total_tokens=32500)
    assert d['attempts'][0]['finish_reason']=='length' and d['attempts'][0]['reasoning_chars']==len(SECRET)
    assert SECRET not in json.dumps(d)


@pytest.mark.parametrize('status,code',[(400,'PROVIDER_REQUEST_REJECTED'),(401,'PROVIDER_AUTH'),(429,'PROVIDER_RATE_LIMIT'),(503,'PROVIDER_HTTP_ERROR')])
def test_http_failures_classify_without_raw_error_or_retry(client,monkeypatch,status,code):
    async def handle(request):return httpx.Response(status,json={'error':{'param':'max_tokens','message':SECRET}})
    calls=transport(monkeypatch,handle)
    with pytest.raises(ProviderFailure) as exc:adapter(max_tokens=1000000,contract_retries=1).analyze(request_for(client))
    assert exc.value.code==code and len(calls)==1
    a=exc.value.diagnostics['attempts'][0]
    assert a['http_status']==status and a['rejected_parameter']=='max_tokens'
    assert SECRET not in json.dumps(exc.value.diagnostics)


def test_contract_retry_is_opt_in_and_does_not_replay_output(client,monkeypatch):
    replies=[response('bad JSON',{'prompt_tokens':7,'completion_tokens':8}),response()]
    async def handle(request):return httpx.Response(200,json=replies.pop(0))
    calls=transport(monkeypatch,handle)
    with pytest.raises(ProviderFailure) as exc:adapter().analyze(request_for(client))
    assert exc.value.code=='INVALID_STRUCTURED_OUTPUT' and len(calls)==1
    replies[:]=[response('bad JSON',{'prompt_tokens':7,'completion_tokens':8}),response()]
    calls.clear()
    r=adapter(contract_retries=1).analyze(request_for(client))
    assert len(calls)==2 and r.diagnostics['retry_count']==1
    assert r.input_tokens is None and r.diagnostics['reported_usage']['input_tokens']==7
    assert calls[1]['messages'][:2]==calls[0]['messages']
    assert all(m['role']!='assistant' for m in calls[1]['messages'])
    assert SECRET not in json.dumps(calls)


@pytest.mark.parametrize('kind,code,phase',[
    ('envelope','PROVIDER_MALFORMED_RESPONSE','response_parse'),
    ('schema','INVALID_STRUCTURED_OUTPUT','structured_output_validation'),
    ('normalization','NORMALIZATION_FAILED','normalization'),
])
def test_failure_stages_are_distinct(client,monkeypatch,kind,code,phase):
    data=reading()
    if kind=='normalization':data['requirements'][0]['quote']='fabricated requirement'
    async def handle(request):
        return httpx.Response(200,json={'error':SECRET} if kind=='envelope' else response(json.dumps({'bogus':1} if kind=='schema' else data)))
    transport(monkeypatch,handle)
    with pytest.raises(ProviderFailure) as exc:adapter().analyze(request_for(client))
    assert (exc.value.code,exc.value.diagnostics['phase'])==(code,phase)


class Stream(httpx.AsyncByteStream):
    def __init__(self,chunks,hang=False):self.chunks,self.hang,self.closed=chunks,hang,False
    async def __aiter__(self):
        for chunk in self.chunks:yield chunk
        if self.hang:await asyncio.sleep(5)
    async def aclose(self):self.closed=True


def event(data):return ('data: '+json.dumps(data)+'\r\n\r\n').encode()


def test_stream_usage_counts_snapshots_once_and_discards_reasoning(client,monkeypatch):
    text=json.dumps(reading())
    usage={'prompt_tokens':10,'completion_tokens':20,'total_tokens':30,'completion_tokens_details':{'reasoning_tokens':8},'prompt_tokens_details':{'cached_tokens':0}}
    chunks=[event({'choices':[{'delta':{'reasoning_content':SECRET}}]}),
            event({'choices':[{'delta':{'content':text[:30]}}],'usage':usage}),
            event({'choices':[{'delta':{'content':text[30:]},'finish_reason':'stop'}],'usage':usage}),
            event({'choices':[],'usage':usage}),b'data: [DONE]\r\n\r\n']
    stream=Stream(chunks)
    async def handle(request):return httpx.Response(200,stream=stream,headers={'Content-Type':'text/event-stream'})
    calls=transport(monkeypatch,handle)
    r=adapter(stream=True).analyze(request_for(client));a=r.diagnostics['attempts'][0]
    assert r.total_tokens==30 and r.reasoning_tokens==8 and r.cached_tokens==0
    assert a['response_bytes']==sum(map(len,chunks)) and a['stream_completed'] and stream.closed
    assert calls[0]['stream_options']=={'include_usage':True}
    assert SECRET not in json.dumps(r.diagnostics)


def test_total_deadline_stops_stream_and_keeps_reported_partial_usage(client,monkeypatch):
    stream=Stream([event({'choices':[{'delta':{'reasoning_content':SECRET}}],'usage':{'prompt_tokens':12}})],hang=True)
    async def handle(request):return httpx.Response(200,stream=stream)
    calls=transport(monkeypatch,handle)
    a=adapter(stream=True,contract_retries=1)
    a.settings=a.settings.model_copy(update={'timeout_seconds':0.08})
    started=time.monotonic()
    with pytest.raises(ProviderFailure) as exc:a.analyze(request_for(client))
    assert time.monotonic()-started<2 and len(calls)==1 and stream.closed
    assert exc.value.code=='PROVIDER_TIMEOUT'
    d=exc.value.diagnostics
    assert d['usage']['input_tokens'] is None and d['reported_usage']['input_tokens']==12 and d['usage']['output_tokens'] is None
    assert not d['attempts'][0]['usage_final']
    assert d['attempts'][0]['reasoning_chars']==len(SECRET) and d['phase']=='provider_call'


def test_network_failure_is_not_retried(client,monkeypatch):
    async def handle(request):raise httpx.ConnectError(SECRET)
    calls=transport(monkeypatch,handle)
    with pytest.raises(ProviderFailure) as exc:adapter(contract_retries=1).analyze(request_for(client))
    assert exc.value.code=='PROVIDER_NETWORK' and len(calls)==1
    assert SECRET not in json.dumps(exc.value.diagnostics)


def test_failed_run_latest_attempt_and_job_keep_previous_success(client,monkeypatch):
    task,old=analyzed(client)
    class Failed:
        id='fixture';model='bad';is_mock=True;supported_media=('image/png',)
        def analyze(self,request):raise ProviderFailure('PROVIDER_OUTPUT_TRUNCATED')
    monkeypatch.setattr(service,'available_providers',lambda:{'failure':Failed()})
    job=jobs.start(task['id'],'analyze',{'expected_revision':task['revision'],'provider':'failure'})
    end=time.monotonic()+5
    while jobs.read(job['id'])['status'] in ('queued','running') and time.monotonic()<end:time.sleep(.01)
    final=jobs.read(job['id'])
    assert final['status']=='failed' and final['error']=='PROVIDER_OUTPUT_TRUNCATED'
    assert 'output' in final['message'].lower() and final['result']['run']['error_message']
    current=client.get('/api/ai-design/tasks/'+task['id']).json()
    assert current['latest_run']['id']==old['id'] and current['latest_attempt']['status']=='failed'
    rows=client.get('/api/ai-design/tasks').json()
    assert rows[0]['latest_attempt']['error']=='PROVIDER_OUTPUT_TRUNCATED'
    assert client.get(f"/api/ai-design/tasks/{task['id']}/runs/{current['latest_attempt']['id']}").json()['status']=='failed'
    assert not (store.OUTPUT/'builds').exists()


def test_usage_aliases_preserve_unknown_not_estimated():
    assert normalize_usage({'input_tokens':5,'output_tokens':6,'reasoning_tokens':3,'cache_read_input_tokens':0})==dict(input_tokens=5,output_tokens=6,reasoning_tokens=3,cached_tokens=0,total_tokens=None)
    assert all(v is None for v in normalize_usage({'prompt_tokens':True,'total_tokens':-1}).values())


def test_compact_prompt_keeps_existing_complexity_and_constraint_rules():
    original=CircuitReading.model_json_schema();compact=prompt_schema()
    assert len(json.dumps(compact))<len(json.dumps(original))
    assert compact['properties']['components']['maxItems']==original['properties']['components']['maxItems']
    assert compact['$defs']['Source']['properties']['page']['anyOf']==original['$defs']['Source']['properties']['page']['anyOf']


def test_alternate_token_parameter_and_large_reasoning_body(client,monkeypatch):
    data=response()
    data['choices'][0]['message']['reasoning_content']='x'*2_100_000
    async def handle(request):return httpx.Response(200,json=data)
    calls=transport(monkeypatch,handle)
    r=adapter(max_tokens=131072,max_tokens_parameter='max_completion_tokens').analyze(request_for(client))
    assert calls[0]['max_completion_tokens']==131072 and 'max_tokens' not in calls[0]
    assert r.diagnostics['attempts'][0]['reasoning_chars']==2_100_000


def test_render_failure_has_no_provider_attempt(client,monkeypatch):
    from manifold.ai_design import remote
    request=request_for(client)
    def bad(*args,**kwargs):raise ValueError(SECRET)
    monkeypatch.setattr(remote,'render',bad)
    with pytest.raises(ProviderFailure) as exc:adapter().analyze(request)
    assert exc.value.code=='DOCUMENT_RENDER_FAILED'
    assert exc.value.diagnostics['phase']=='document_render' and exc.value.diagnostics['request_count']==0
    assert SECRET not in json.dumps(exc.value.diagnostics)


def test_admission_failure_retains_reported_usage(client,monkeypatch):
    task,old=analyzed(client)
    class Bad:
        id='fixture';model='invalid-domain';is_mock=True;supported_media=('image/png',)
        def analyze(self,request):return ProviderResponse({'unexpected':SECRET},input_tokens=10,output_tokens=20,reasoning_tokens=9)
    monkeypatch.setattr(service,'available_providers',lambda:{'bad':Bad()})
    result=service.analyze(task['id'],task['revision'],'bad')
    assert result['run']['phase']=='admission' and result['run']['error']=='INVALID_PROVIDER_RESULT'
    assert result['run']['usage']['reasoning_tokens']==9 and result['run']['usage']['input_tokens']==10
    assert result['task']['latest_run']['id']==old['id'] and SECRET not in json.dumps(result)
