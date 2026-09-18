import copy
import json
import pytest
from pydantic import ValidationError
from manifold.demo import demo, invalid_demo
from manifold.schema import Design,CavityDefinition
from manifold.engineering_db import get_definition
from manifold.demo import CAVITY_ID
from manifold.geometry import build_geometry, placement
from manifold.validation import validate
from manifold.store import build_outputs, revision


def test_cad_process_exits_cleanly():
    import subprocess
    import sys
    process = subprocess.run([sys.executable, '-c',
        'from manifold.cad import cq; assert cq.Solid.makeBox(10,10,10).isValid()'], capture_output=True)
    assert process.returncode == 0, (process.returncode, process.stderr)


def checked(data):
    design = Design.model_validate(data)
    return validate(design, build_geometry(design))


def failure(report, rule):
    return [c for c in report['checks'] if c['rule'] == rule and c['status'] == 'FAIL']


def test_corrected_demo_passes_and_step_roundtrips(tmp_path):
    report = build_outputs(demo(), tmp_path / 'build')
    assert report['status'] == 'PASS'
    assert report['counts']['FAIL'] == report['counts']['WARNING'] == 0
    assert report['checks'][-1]['rule'] == 'step_round_trip'
    assert (tmp_path / 'build' / 'production.step').stat().st_size > 10000
    engineering = tmp_path / 'build' / 'engineering.step'
    assert engineering.stat().st_size > (tmp_path / 'build' / 'production.step').stat().st_size
    step_text = engineering.read_text(errors='ignore')
    assert 'MANIFOLD_FINISHED' in step_text
    from manifold.cad import cq
    assert len(cq.importers.importStep(str(engineering)).val().Solids()) > 1
    review = json.loads((tmp_path / 'build' / 'review.json').read_text())
    assert review['design_revision'] == report['design_revision'] == revision(demo())
    assert all(p['vertices'] and p['triangles'] for p in review['parts'])
    assert set(report['graph']['G-P']) == {'P', 'CV1:port2', 'RV1:port2', 'XD-P'}
    assert 'CV1:port1' not in report['graph']['CV1:port2']


def test_deliberate_cross_circuit_collision():
    report = checked(invalid_demo())
    assert failure(report, 'circuit_intersection')
    assert any(set(c['items']) == {'BAD-P', 'G-A'} for c in failure(report, 'circuit_intersection'))
    assert failure(report, 'expected_connection')


def test_true_six_mm_wall_is_detected():
    d = demo().model_dump()
    d['features'][-1]['u'] = 70
    report = checked(d)
    hit = [c for c in failure(report, 'minimum_feature_wall') if c['items'] == ['RV1', 'XD-P']]
    assert hit[0]['actual'] == pytest.approx(5.5)
    assert hit[0]['required'] == 7


def test_declared_pressure_changes_required_ligament_without_resizing_flow():
    d = demo();d.rules.allowable_stress_mpa=90;d.rules.pressure_safety_factor=2
    net=next(n for n in d.nets if n.id=='P');g=build_geometry(d)
    net.pressure_bar=100;low=validate(d,g)
    net.pressure_bar=350;high=validate(d,g)
    required=lambda report:max(float(c['required']) for c in report['checks']
        if c['rule'] in ('minimum_feature_wall','external_wall') and isinstance(c['required'],(int,float)))
    assert required(low)==7 and required(high)>required(low)
    assert not failure(low,'pressure_strength') and not failure(high,'pressure_strength')


def test_cavity_collision():
    d = demo().model_dump(); d['features'][1]['u'] = 50
    assert failure(checked(d), 'cavity_collision')


def test_protected_seal_region_cannot_be_cross_drilled():
    d = demo().model_dump()
    for f in d['features']:
        if f['id'] in ('P', 'G-P', 'XD-P'):
            f['v'] = 70
    assert failure(checked(d), 'cavity_protected_region')


def test_tip_included_in_remaining_wall():
    d = demo().model_dump()
    f = d['features'][-1]; f['depth'] = 112
    report = checked(d)
    hit = [c for c in failure(report, 'external_wall') if c['items'] == ['XD-P', 'back']]
    assert 5 < hit[0]['actual'] < 7  # Cylinder alone would leave 8 mm.


def test_outside_entry_and_excessive_depth():
    d = demo().model_dump(); d['features'][-1]['u'] = 181; d['features'][-1]['depth'] = 125
    assert failure(checked(d), 'external_face_entry')


def test_missing_plug_detected():
    d = demo().model_dump(); d['features'][-1]['plugged'] = False
    assert failure(checked(d), 'drilling_entry_closure')


def test_plug_cannot_block_connection():
    d = demo().model_dump(); d['features'][-1]['plug_length'] = 61
    report = checked(d)
    assert failure(report, 'plug_engagement')


def test_undeclared_same_circuit_contact_is_not_silently_allowed():
    d = demo().model_dump(); d['features'][-1]['connects_to'] = []
    assert failure(checked(d), 'declared_connection')


def test_disconnected_expected_connection():
    d = demo().model_dump(); d['features'][-1]['depth'] = 35
    report = checked(d)
    assert failure(report, 'expected_connection')
    assert failure(report, 'circuit_connectivity')


def test_installation_envelope_interference():
    d = demo().model_dump(); d['features'][1]['u'] = 70
    assert failure(checked(d), 'installation_access')


@pytest.mark.parametrize('face,origin,direction', [
    ('left', (0, 20, 30), (1, 0, 0)), ('right', (180, 20, 30), (-1, 0, 0)),
    ('front', (20, 0, 30), (0, 1, 0)), ('back', (20, 120, 30), (0, -1, 0)),
    ('bottom', (20, 30, 0), (0, 0, 1)), ('top', (20, 30, 100), (0, 0, -1)),
])
def test_face_coordinates(face, origin, direction):
    d = demo(); f = d.features[-1].model_copy(update=dict(face=face, u=20, v=30))
    assert placement(f, d.block) == (origin, direction)


@pytest.mark.parametrize('mutation', ['duplicate', 'unknown_target', 'nan', 'negative', 'unknown_field', 'zones'])
def test_schema_rejects_invalid_engineering_data(mutation):
    d = demo().model_dump()
    if mutation == 'duplicate': d['features'][1]['id'] = d['features'][0]['id']
    if mutation == 'unknown_target': d['features'][-1]['connects_to'] = ['MISSING']
    if mutation == 'nan': d['block']['width'] = float('nan')
    if mutation == 'negative': d['features'][-1]['diameter'] = -1
    if mutation == 'unknown_field': d['features'][-1]['execute'] = 'arbitrary code'
    if mutation == 'zones': d['features'][0]['circuits'] = {'upper': 'P'}
    with pytest.raises(ValidationError): Design.model_validate(d)


def test_schema_rejects_invalid_engineering_stage_gap():
    definition=get_definition(CAVITY_ID).model_dump()
    definition['stages'][1]['start']+=1
    with pytest.raises(ValidationError):CavityDefinition.model_validate(definition)
