"""Trusted relationships advance automatically; missing coverage stays actionable."""
import copy
import pytest
from test_ai_generation import client, inputs, reading
from manifold import catalog
from manifold.schema import CartridgeCompatibility
from manifold.ai_design import library_resolution as library, generation
from manifold.ai_design.semantic import CircuitReading, normalize
from manifold.ai_design.models import TaskInput
from manifold.ai_design.generation_models import GenerationOptions


def fixture(client):
    task = TaskInput.model_validate(inputs(client, 'P on left.'))
    raw = reading()
    raw['components'][0]['cavity'] = {}
    result = normalize(CircuitReading.model_validate(raw), task, {'DOC1': 1}).model_dump()
    return task, result


def related_definition(status='documented'):
    definition = catalog.definition('metric:lib109:cavity:352').model_copy(deep=True)
    definition.compatible_cartridges = [CartridgeCompatibility(model='unverified fixture model',
        manufacturer='HydraForce', source='Synthetic test relationship only; not product compatibility evidence', status=status)]
    return definition


def test_unique_trusted_relationship_and_numbered_windows_auto_resolve(client, monkeypatch):
    task, result = fixture(client)
    definition = related_definition()
    monkeypatch.setattr(library, 'saved_definitions', lambda inputs: [('pmc:fixture', definition)])
    plan = generation.prepare(task, result, GenerationOptions())
    component = plan['components'][0]
    assert component['automatic'] and component['resolution']['code'] == 'resolved'
    assert component['mapping'] == {'port1': 'C1P1', 'port2': 'C1P2'}
    assert not plan['blocked']


@pytest.mark.parametrize('case,code', [('missing','relationship_missing'), ('unconfirmed','relationship_missing'),
    ('ambiguous','ambiguous_cavities'), ('geometry','geometry_needs_review'), ('windows','window_mapping_required')])
def test_resolution_explains_each_missing_boundary(client, monkeypatch, case, code):
    task, result = fixture(client)
    definition = related_definition('unconfirmed' if case == 'unconfirmed' else 'documented')
    rows = [('pmc:fixture', definition)]
    if case == 'missing': rows = []
    if case == 'ambiguous': rows.append(('pmc:other', definition.model_copy(deep=True)))
    if case == 'geometry': definition.native.geometry_status = 'draft-projection'
    if case == 'windows':
        for claim in result['claims']:
            if claim['predicate'] == 'label' and claim['subject_id'] in ('C1P1', 'C1P2'):
                claim['value'] = 'inlet' if claim['subject_id'] == 'C1P1' else 'outlet'
    monkeypatch.setattr(library, 'saved_definitions', lambda inputs: rows)
    plan = generation.prepare(task, result, GenerationOptions())
    component = plan['components'][0]
    assert not component['automatic'] and component['definition'] is None
    assert component['resolution']['code'] == code and component['resolution']['action']
    assert component['resolution']['message'] in plan['blocked'][0]


def test_actual_library_has_no_recognized_model_relationship(client, monkeypatch):
    task, result = fixture(client)
    monkeypatch.setattr(library, 'saved_definitions', lambda inputs: [])
    for model in ('RDHA-LCN', 'CA100'):
        item = copy.deepcopy(result)
        for claim in item['claims']:
            if claim['subject_id'] == 'C1' and claim['predicate'] == 'model': claim['value'] = model
        assert catalog.search(q=model, kind='cavity', unit='')['total'] == 0
        assert catalog.search(q=model, kind='footprint', unit='')['total'] == 0
        plan = generation.prepare(task, item, GenerationOptions())
        assert plan['components'][0]['resolution']['code'] == 'relationship_missing'
        assert not plan['components'][0]['choices']


def test_actual_source_cavity_can_resolve_without_product_guessing(client, monkeypatch):
    task, result = fixture(client)
    definition = catalog.definition('metric:lib109:cavity:352')
    for claim in result['claims']:
        if claim['subject_id'] == 'C1' and claim['predicate'] == 'cavity':
            claim.update(value=definition.label, kind='schematic', status='confirmed')
        if claim['subject_id'] == 'C1' and claim['predicate'] == 'manufacturer':
            claim.update(value=None, kind='unknown', status='unresolved')
    monkeypatch.setattr(library, 'saved_definitions', lambda inputs: [])
    plan = generation.prepare(task, result, GenerationOptions())
    assert plan['components'][0]['automatic'] and not plan['blocked']
