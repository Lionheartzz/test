"""Optional unsupported identity cannot block topology or become library authority."""
import copy
import json
import httpx
import pytest
from test_provider_diagnostics import client, adapter, transport, request_for, response, reading
from test_ai_generation import analyzed
from manifold.ai_design import service, library_resolution as library, generation
from manifold.ai_design.models import TaskInput, ClaimReview
from manifold.ai_design.generation_models import GenerationOptions
from manifold.ai_design.intent import effective_result

FIELDS = ('manufacturer', 'model', 'cavity')
PRIVATE_VALUE = 'UNSUPPORTED_IDENTITY_VALUE'


def unsupported():
    raw = reading()
    for field in FIELDS:
        raw['components'][0][field] = dict(value=PRIVATE_VALUE, status='clear')
    return raw


def install(monkeypatch, raw):
    async def handle(request):
        return httpx.Response(200, json=response(json.dumps(raw)))
    return transport(monkeypatch, handle)


def test_real_three_field_failure_becomes_reviewable_analysis(client, monkeypatch, tmp_path):
    task, old = analyzed(client, 'USE SUN CARTRIDGES WHEN POSSIBLE')
    raw = unsupported()
    raw['requirements'] = [dict(quote='USE SUN CARTRIDGES WHEN POSSIBLE', category='component_selection',
        property='manufacturer', operator='prefer', strength='preference', value='SUN')]
    calls = install(monkeypatch, raw)
    monkeypatch.setattr(service, 'available_providers', lambda: {'fixture': adapter()})
    result = service.analyze(task['id'], task['revision'], 'fixture')
    run = service.load_run(task['id'], result['run']['id'])
    assert run['status'] == 'completed' and len(calls) == 1
    assert result['task']['latest_run']['id'] == run['id']
    claims = run['result']['claims']
    identities = [c for c in claims if c['subject_id'] == 'C1' and c['predicate'] in FIELDS]
    assert len(identities) == 3
    assert all(c['value'] is None and c['kind'] == 'unknown' and c['status'] == 'unresolved' for c in identities)
    assert len(run['result']['nets']) == 2 and len(run['result']['ports']) == 4
    assert run['result']['design_intent'][0]['strength'] == 'preference'
    assert any(c['subject_id'] == 'I1' and c['value'] == 'SUN' for c in claims)
    details = run['diagnostics']['attempts'][0]['validation_errors']
    assert [d['path'] for d in details] == [['components', 0, f] for f in FIELDS]
    assert all(d['action'] == 'normalized' for d in details)
    assert sum('unsupported model value discarded' in u['description'] for u in run['result']['unresolved']) == 3
    assert PRIVATE_VALUE not in json.dumps(service.export(task['id'], run['id']))
    assert all(not k['manufacturer'] and not k['model'] for k in run['result']['knowledge'])
    monkeypatch.setattr(library, 'saved_definitions', lambda inputs: [])
    monkeypatch.setattr(library, 'search', lambda *a, **kw: pytest.fail('Unknown identity must not search a cavity'))
    plan = generation.prepare(TaskInput.model_validate(task['inputs']), run['result'], GenerationOptions())
    assert plan['blocked'] and plan['components'][0]['choices'] == []
    assert plan['components'][0]['model'] == '' and plan['components'][0]['definition'] is None
    assert not (tmp_path/'projects'/'saved').exists() and not (tmp_path/'projects'/'library').exists()
    with pytest.raises(ValueError, match='Correct an unknown value'):
        service.review(task['id'], run['id'], result['task']['revision'],
            [ClaimReview(claim_id=identities[0]['id'], status='confirmed', decision='Cannot accept a missing value')])
    assert service.load_run(task['id'], old['id'])['status'] == 'completed'


@pytest.mark.parametrize('case', ['topology', 'shape', 'page', 'preference'])
def test_identity_recovery_never_hides_other_failures(client, monkeypatch, case):
    raw = unsupported()
    if case == 'topology':
        raw['components'][0]['ports'][0]['net']['source'] = {}
    elif case == 'shape':
        raw['components'][0]['model'] = PRIVATE_VALUE
    elif case == 'page':
        raw['components'][0]['ports'][0]['net']['source']['page'] = 999
    else:
        raw['requirements'][0].update(category='component_selection', operator='prefer', strength='preference')
        raw['components'][0]['model']['source'] = dict(kind='user_requirement', quote='P on left.')
    install(monkeypatch, raw)
    from manifold.ai_design.providers import ProviderFailure
    with pytest.raises(ProviderFailure) as exc:
        adapter().analyze(request_for(client))
    assert exc.value.code == ('NORMALIZATION_FAILED' if case == 'page' else 'INVALID_STRUCTURED_OUTPUT')


@pytest.mark.parametrize('kind,status', [('ai_inference', 'uncertain'), ('schematic', 'uncertain'), ('user_requirement', 'confirmed')])
def test_unaccepted_identity_never_drives_library_or_generated_model(client, monkeypatch, kind, status):
    from manifold.ai_design.semantic import CircuitReading, normalize
    request = request_for(client)
    result = normalize(CircuitReading.model_validate(reading()), request.inputs, {'DOC1': 1}).model_dump()
    for claim in result['claims']:
        if claim['subject_id'] == 'C1' and claim['predicate'] in FIELDS:
            claim.update(kind=kind, status=status)
    monkeypatch.setattr(library, 'saved_definitions', lambda inputs: [])
    monkeypatch.setattr(library, 'search', lambda *a, **kw: pytest.fail('Unaccepted identity used'))
    plan = generation.prepare(request.inputs, result, GenerationOptions())
    assert plan['components'][0]['model'] == '' and not plan['components'][0]['choices']
    model = next(c for c in result['claims'] if c['subject_id'] == 'C1' and c['predicate'] == 'model')
    reviewed = effective_result({'result': result}, {model['id']: dict(status='corrected', corrected_value='Engineer selection', corrected_unit='', decision='Verified separately')})
    assert library.identity_value(reviewed, 'C1', 'model') == 'Engineer selection'
    assert model['value'] != 'Engineer selection'  # Immutable original observation.
