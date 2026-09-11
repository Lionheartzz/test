import json
import pytest
from pydantic import ValidationError
from test_provider_diagnostics import client,adapter,transport,response,request_for,reading,SECRET
from manifold.ai_design.semantic import CircuitReading
from manifold.ai_design.validation_details import safe_validation_errors
from manifold.ai_design.providers import ProviderFailure
import httpx


def test_sanitized_errors_keep_paths_and_types_without_inputs_or_context():
    raw=reading();raw['components'][0]['model']['status']='PRIVATE_STATUS_SECRET';raw['components'][0][SECRET]={'api_key':SECRET}
    with pytest.raises(ValidationError) as exc:CircuitReading.model_validate(raw)
    details=safe_validation_errors(exc.value)
    assert any(e['path']==['components',0,'model','status'] and e['type']=='literal_error' for e in details)
    assert any(e['type']=='extra_forbidden' and e['path_redacted'] for e in details)
    assert SECRET not in json.dumps(details) and 'PRIVATE_STATUS_SECRET' not in json.dumps(details)
    assert all('input' not in e and 'ctx' not in e for e in details)


def test_semantic_invariants_stay_rejected_with_safe_explanation():
    raw=reading();raw['components'][0]['model']['status']='unknown'
    with pytest.raises(ValidationError) as exc:CircuitReading.model_validate(raw)
    details=safe_validation_errors(exc.value)
    assert details[0]['classification']=='semantic' and details[0]['action']=='rejected'
    assert 'null' in details[0]['explanation']


def test_retry_carries_exact_sanitized_errors_and_no_failed_body(client,monkeypatch):
    bad=reading();bad['components'][0]['model']['status']=SECRET
    replies=[response(json.dumps(bad)),response()]
    async def handle(request):return httpx.Response(200,json=replies.pop(0))
    calls=transport(monkeypatch,handle)
    r=adapter(contract_retries=1).analyze(request_for(client))
    detail=r.diagnostics['attempts'][0]['validation_errors'][0]
    assert detail['path']==['components',0,'model','status'] and detail['type']=='literal_error'
    prompt=calls[1]['messages'][-1]['content']
    assert json.dumps(detail,ensure_ascii=False,separators=(',',':')) in prompt
    assert SECRET not in prompt and SECRET not in json.dumps(r.diagnostics)
    assert len(calls)==2


def test_default_retry_off_preserves_error_details(client,monkeypatch):
    bad=reading();bad['components'][0]['model']['status']=SECRET
    async def handle(request):return httpx.Response(200,json=response(json.dumps(bad)))
    calls=transport(monkeypatch,handle)
    with pytest.raises(ProviderFailure) as exc:adapter().analyze(request_for(client))
    assert len(calls)==1 and exc.value.diagnostics['attempts'][0]['validation_errors'][0]['type']=='literal_error'

def test_validation_details_survive_failed_run_persistence(client,monkeypatch):
    from manifold.ai_design import service
    from test_ai_generation import analyzed
    task,old=analyzed(client)
    bad=reading();bad['components'][0]['model']['status']=SECRET
    async def handle(request):return httpx.Response(200,json=response(json.dumps(bad)))
    transport(monkeypatch,handle);a=adapter()
    monkeypatch.setattr(service,'available_providers',lambda:{'fixture':a})
    result=service.analyze(task['id'],task['revision'],'fixture');run=result['run']
    loaded=service.load_run(task['id'],run['id'])
    detail=loaded['diagnostics']['attempts'][0]['validation_errors'][0]
    assert detail['path']==['components',0,'model','status']
    assert detail['type']=='literal_error' and detail['action']=='rejected'
    assert result['task']['latest_run']['id']==old['id']
    assert SECRET not in json.dumps(service.export(task['id'],run['id']))
