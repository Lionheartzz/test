"""Selection preferences cannot supply observed component identity."""
import pytest
from pydantic import ValidationError
from test_ai_generation import client, inputs
from manifold.ai_design.models import TaskInput
from manifold.ai_design.semantic import CircuitReading, normalize
from manifold.ai_design.validation_details import safe_validation_errors

PREFERENCE = 'USE SUN CARTRIDGES WHEN POSSIBLE'
FIELDS = ('manufacturer', 'model', 'cavity', 'functional_type')


def preference_reading():
    return dict(components=[dict(label=label, ports=[dict(label='1', net={})])
                            for label in ('V1', 'V2')],
                requirements=[dict(quote=PREFERENCE, category='component_selection',
                                   property='manufacturer', operator='prefer',
                                   strength='preference', value='SUN')])


def test_missing_component_sources_keep_preference_separate(client):
    reading = CircuitReading.model_validate(preference_reading())
    assert all(c.source.kind == 'unknown' for c in reading.components)
    result = normalize(reading, TaskInput.model_validate(inputs(client, PREFERENCE)), {'DOC1': 1})
    for component in result.components:
        claims = [c for c in result.claims if c.subject_id == component.id]
        label = next(c for c in claims if c.predicate == 'label')
        assert label.kind == 'ai_inference' and label.status == 'uncertain'
        for field in FIELDS:
            claim = next(c for c in claims if c.predicate == field)
            assert claim.value is None and claim.kind == 'unknown' and claim.status == 'unresolved'
    intent = result.design_intent[0]
    assert intent.category == 'component_selection' and intent.strength == 'preference'
    assert intent.operator == 'prefer'
    claim = next(c for c in result.claims if c.id == intent.claim_id)
    assert claim.value == 'SUN' and claim.kind == 'user_requirement'
    evidence = next(e for e in result.evidence if e.id in claim.evidence_ids)
    assert evidence.quote == PREFERENCE and evidence.requirement_span == (0, len(PREFERENCE))


def test_exact_two_component_scalar_manufacturer_case_stays_rejected():
    raw = preference_reading()
    for component in raw['components']:
        component['manufacturer'] = 'SUN'
    with pytest.raises(ValidationError) as exc:
        CircuitReading.model_validate(raw)
    errors = safe_validation_errors(exc.value)
    assert [e['path'] for e in errors] == [['components', i, 'manufacturer'] for i in range(2)]
    assert all(e['type'] == 'model_type' and e['action'] == 'rejected' for e in errors)


@pytest.mark.parametrize('field', FIELDS)
def test_identity_observations_still_require_provenance(field):
    raw = preference_reading()
    raw['components'][0][field] = dict(value='SUN', status='clear')
    with pytest.raises(ValidationError, match='needs a source'):
        CircuitReading.model_validate(raw)


@pytest.mark.parametrize('field', FIELDS)
def test_preference_quote_cannot_be_promoted_to_component_fact(field):
    raw = preference_reading()
    raw['components'][0][field] = dict(value='SUN', status='clear',
                                     source=dict(kind='user_requirement', quote=PREFERENCE))
    with pytest.raises(ValidationError) as exc:
        CircuitReading.model_validate(raw)
    error = safe_validation_errors(exc.value)[0]
    assert error['classification'] == 'semantic' and error['action'] == 'rejected'
    assert 'preferences in requirements' in error['explanation']


@pytest.mark.parametrize('manufacturer', ['SUN', 'HydraForce'])
def test_independent_schematic_manufacturer_is_preserved(client, manufacturer):
    raw = preference_reading()
    raw['components'][0]['manufacturer'] = dict(value=manufacturer, status='clear',
        source=dict(kind='schematic', document=1, page=1, quote=manufacturer))
    task = TaskInput.model_validate(inputs(client, PREFERENCE))
    result = normalize(CircuitReading.model_validate(raw), task, {'DOC1': 1})
    claim = next(c for c in result.claims if c.subject_id == 'C1' and c.predicate == 'manufacturer')
    assert claim.value == manufacturer and claim.kind == 'schematic'
    raw['components'][0]['manufacturer']['source']['page'] = 2
    with pytest.raises(ValueError, match='Source page does not exist'):
        normalize(CircuitReading.model_validate(raw), task, {'DOC1': 1})
