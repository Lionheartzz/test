"""Unattributed symbol interpretations stay uncertain, never observed product facts."""
import copy
import json
import httpx
import pytest
from pydantic import ValidationError
from test_component_preferences import preference_reading, PREFERENCE
from test_provider_diagnostics import client, adapter, transport, response, request_for
from manifold.ai_design.semantic import CircuitReading, normalize


@pytest.mark.parametrize('source', [None, {}, {'kind': 'unknown'}])
def test_two_unattributed_functional_types_are_uncertain_inferences(client, source):
    raw = preference_reading()
    for component, function in zip(raw['components'], ('pressure_relief', 'check')):
        component['functional_type'] = dict(value=function, status='clear')
        if source is not None:
            component['functional_type']['source'] = source
    original = copy.deepcopy(raw)
    reading = CircuitReading.model_validate(raw)
    assert raw == original
    request = request_for(client)
    inputs = request.inputs.model_copy(update={'engineering_requirements': PREFERENCE})
    result = normalize(reading, inputs, {'DOC1': 1})
    functions = [c for c in result.claims if c.predicate == 'functional_type']
    assert [c.value for c in functions] == ['pressure_relief', 'check']
    assert all(c.kind == 'ai_inference' and c.status == 'uncertain' for c in functions)
    assert all(c.functional_type.status == 'uncertain' for c in reading.components)
    for claim in functions:
        assert all(e.kind == 'ai_inference' for e in result.evidence if e.id in claim.evidence_ids)
    assert all(c.value is None for c in result.claims
               if c.subject_id in ('C1', 'C2') and c.predicate in ('manufacturer', 'model', 'cavity'))


def test_real_provider_shape_passes_adapter_without_retry(client, monkeypatch):
    from test_ai_generation import reading
    raw = reading()
    raw['components'].append(copy.deepcopy(raw['components'][0]))
    raw['components'][1]['label'] = 'RV2'
    for component in raw['components']:
        component['functional_type'].pop('source')
    async def handle(request):
        return httpx.Response(200, json=response(json.dumps(raw)))
    calls = transport(monkeypatch, handle)
    result = adapter().analyze(request_for(client))
    assert len(calls) == 1
    assert result.diagnostics['attempts'][0]['status'] == 'completed'
    functions = [c for c in result.representation['claims'] if c['predicate'] == 'functional_type']
    assert len(functions) == 2
    assert all(c['kind'] == 'ai_inference' and c['status'] == 'uncertain' for c in functions)
    prompt = calls[0]['messages'][0]['content']
    assert 'source.kind = ai_inference and status = uncertain' in prompt


@pytest.mark.parametrize('observation', [
    'pressure_relief', {'value': 'check', 'status': 'unknown'},
    {'value': 'check', 'status': 'clear', 'source': None},
    {'value': 'check', 'status': 'clear', 'source': {'kind': 'invalid'}},
])
def test_malformed_functional_types_are_not_repaired(observation):
    raw = preference_reading()
    raw['components'][0]['functional_type'] = observation
    with pytest.raises(ValidationError):
        CircuitReading.model_validate(raw)


def test_explicit_schematic_source_and_unknown_value_are_preserved(client):
    raw = preference_reading()
    raw['components'][0]['functional_type'] = dict(value='check', status='clear',
        source=dict(kind='schematic', document=1, page=1, quote='CHECK VALVE'))
    reading = CircuitReading.model_validate(raw)
    assert reading.components[1].functional_type.source.kind == 'unknown'
    request = request_for(client)
    inputs = request.inputs.model_copy(update={'engineering_requirements': PREFERENCE})
    result = normalize(reading, inputs, {'DOC1': 1})
    claim = next(c for c in result.claims if c.subject_id == 'C1' and c.predicate == 'functional_type')
    assert claim.kind == 'schematic' and claim.status == 'confirmed'
    raw['components'][0]['functional_type']['source']['page'] = 2
    with pytest.raises(ValueError, match='Source page does not exist'):
        normalize(CircuitReading.model_validate(raw), inputs, {'DOC1': 1})
