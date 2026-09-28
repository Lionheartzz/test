"""Finite plug engagement must outrank cheap but physically blocked routes."""
from pathlib import Path

from manifold.schema import CavityDefinition, Design, Feature, HydraulicNet
from manifold.routing import route_obstructions, route_options
import manifold.routing as routing


def context():
    design = Design.model_validate_json(Path('tests/fixtures/automatic-cross-net.json').read_text())
    design.features = [Feature(id='CV1', kind='cavity', face='top', u=60, v=60,
                               cavity_id='fixture_cavity', interface_nets={'P': 'P'}),
                       Feature(id='PT1', kind='port', face='left', u=60, v=75,
                               circuit='P', diameter=10, depth=16)]
    design.nets = [HydraulicNet(id='P', members=['CV1:P', 'PT1'], routing='automatic')]
    definition = CavityDefinition(id='fixture_cavity', label='Mapped cavity',
                                  stages=[dict(start=0, end=30, diameter=18)],
                                  cutting_primitives=[dict(kind='cylinder', start=0, end=30,
                                                           diameter=18, offset_u=0, offset_v=0)],
                                  zones=[dict(id='P', start=22, end=26, diameter=8)],
                                  clearance_diameter=20, clearance_height=15)
    return design, {'fixture_cavity': definition}


def bore(id, face, u, v, depth, *, plugged=True, plug_length=8):
    return Feature(id=id, kind='drilling', face=face, u=u, v=v, circuit='P',
                   diameter=6, depth=depth, tip_angle=180, plugged=plugged,
                   plug_length=plug_length, route_net='P')


def plug_failures(design, route, definitions):
    return {failure for failure in route_obstructions(design, design.nets[0], route,
                                                       thread_definitions={}, definitions=definitions)
            if failure[0] == 'plug_cut'}


def test_bad_plug_is_hard_failure_and_clean_higher_cost_candidate_wins(monkeypatch):
    design, definitions = context()
    bad = bore('BAD', 'top', 60, 60, 30)
    clean = bore('CLEAN', 'top', 90, 60, 50)
    assert ('plug_cut', 'BAD', 'CV1') in plug_failures(design, [bad], definitions)
    assert not plug_failures(design, [clean], definitions)
    monkeypatch.setattr(routing, 'simple_routes', lambda *_: [[bad], [clean]])
    monkeypatch.setattr(routing, 'propose', lambda *_: [bad])
    choices = route_options(design, design.nets[0], definitions=definitions, thread_definitions={})
    assert choices[0]['route'][0].id == 'CLEAN'
    assert choices[0]['hard_failures'] == 0
    assert any(choice['route'][0].id == 'BAD' and choice['hard_failures'] > 0 for choice in choices)


def test_cross_face_plug_intrusion_uses_actual_cutting_primitive():
    design, definitions = context()
    design.features[0].u = 8
    design.features[0].v = 52
    design.features[0].rotation = 90
    definitions['fixture_cavity'].cutting_primitives[0].offset_u = 8
    cross = bore('CROSS', 'left', 60, 92, 35, plug_length=12)
    assert ('plug_cut', 'CROSS', 'CV1') in plug_failures(design, [cross], definitions)


def test_hydraulic_window_contact_after_plug_does_not_block_candidate():
    design, definitions = context()
    design.features = design.features[:1]
    connected = bore('CONNECTED', 'left', 60, 75, 70)
    assert not plug_failures(design, [connected], definitions)


def test_branch_inside_plug_is_blocked_but_deeper_branch_is_allowed():
    design, definitions = context()
    design.features = []
    plug = bore('PLUG', 'left', 50, 50, 60, plug_length=10)
    near = bore('NEAR', 'front', 5, 50, 60, plugged=False)
    far = bore('FAR', 'front', 25, 50, 60, plugged=False)
    assert ('plug_cut', 'NEAR', 'PLUG') in plug_failures(design, [plug, near], definitions)
    assert not plug_failures(design, [plug, far], definitions)


def test_source_port_mounting_and_modifier_cuts_block_plug_engagement():
    design, definitions = context()
    design.features = [Feature(id='SRC', kind='port', face='top', u=60, v=60,
                               port_definition_id='fixture_port', circuit='T')]
    definitions['fixture_port'] = CavityDefinition(
        id='fixture_port', label='Mapped external port', kind='external-port',
        stages=[dict(start=0, end=20, diameter=18)],
        zones=[dict(id='entry', start=12, end=16, diameter=8)],
        clearance_diameter=20, clearance_height=10)
    assert ('plug_cut', 'SRC', 'TEST') in plug_failures(
        design, [bore('TEST', 'top', 60, 60, 30)], definitions)
    design.features = [Feature(id='MNT', kind='mounting', face='top', u=80, v=60,
                               diameter=6, depth=30, machining_modifiers=[dict(modifier_id='fixture_mod', start=0)])]
    modifiers = {'fixture_mod': {'primitives': [dict(kind='cylinder', start=0, end=12, diameter=20)]}}
    plug = bore('TEST', 'top', 89, 60, 30)
    placement = design.features[0].machining_modifiers[0]
    design.features[0].machining_modifiers = []
    assert not plug_failures(design, [plug], definitions)
    design.features[0].machining_modifiers = [placement]
    assert ('plug_cut', 'MNT', 'TEST') in route_obstructions(
        design, design.nets[0], [plug], thread_definitions={}, definitions=definitions,
        modifier_definitions=modifiers)


def test_all_bad_candidates_still_return_failing_proposal(monkeypatch):
    design, definitions = context()
    bad = bore('BAD', 'top', 60, 60, 30)
    monkeypatch.setattr(routing, 'simple_routes', lambda *_: [])
    monkeypatch.setattr(routing, 'propose', lambda *_: [bad])
    choices = route_options(design, design.nets[0], definitions=definitions, thread_definitions={})
    assert choices and choices[0]['route'] and all(option['hard_failures'] > 0 for option in choices)
    from manifold.geometry import build_geometry
    from manifold.validation import validate
    design.features.extend(choices[0]['route'])
    report = validate(design, build_geometry(design, definitions=definitions, thread_definitions={},
                                             modifier_definitions={}), definitions=definitions)
    assert report['counts']['FAIL'] > 0
    assert any(check['rule'] == 'plug_engagement' and check['status'] == 'FAIL'
               for check in report['checks'])
