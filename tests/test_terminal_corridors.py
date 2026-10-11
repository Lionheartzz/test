"""Source-safe terminal corridors must connect without changing authored geometry."""
import hashlib

import pytest

from manifold import engineering_db, routing, geometry
from manifold.cavity_access import _direct_axial_candidates
from manifold.schema import CavityDefinition, Design, Feature
from test_cavity_axial_access import source_window


@pytest.mark.parametrize('face', ['top', 'front'])
def test_parallel_deep_windows_share_a_real_common_corridor(face, monkeypatch):
    design, definitions = source_window(face)
    first = design.features[0]
    first.u = 45
    second = definitions['SOURCE'].model_copy(deep=True)
    second.id = 'DEEPER'
    second.stages[0].end = second.cutting_primitives[0].end = 65
    second.zones[1].start, second.zones[1].end = 55, 65
    definitions[second.id] = CavityDefinition.model_validate(second.model_dump())
    design.features.append(Feature(id='CV2', kind='cavity', face=face, u=85, v=60,
                                   cavity_id=second.id, interface_nets={'deep': 'P'}))
    design.nets[0].members = ['CV:deep', 'CV2:deep']
    design = Design.model_validate(design.model_dump())
    monkeypatch.setattr(engineering_db, 'definitions_for_design', lambda _: definitions)
    before = design.model_dump()
    net = design.nets[0]
    candidates = [(key, route) for key, route in _direct_axial_candidates(design, net, definitions)
                  if ':j' in key and not routing.route_obstructions(design, net, route, {}, definitions, {})]
    assert candidates
    key, route = candidates[0]
    snapshot = routing._ProposalSnapshot(design, definitions, {}, {})
    option = dict(key=key, route=route, risk=0, cost=0)
    assert routing._verify_route_candidate(design, net, option, snapshot), option
    assert routing._candidate_admitted(option, net)
    assert len([f for f in option['route'] if '-AX' in f.id]) == 2
    assert routing.route_from_variant(design, net, key, definitions, {}, {}) == route
    assert design.model_dump() == before


def test_coaxial_last_window_stop_has_exact_opening_and_preserves_saved_source(monkeypatch, tmp_path):
    design, definitions = source_window()
    design.features.append(Feature(id='PORT', kind='port', face='right', u=60, v=88,
                                   diameter=12, depth=16, circuit='P'))
    design.nets[0].members = ['CV:deep', 'PORT']
    design = Design.model_validate(design.model_dump())
    monkeypatch.setattr(engineering_db, 'definitions_for_design', lambda _: definitions)
    before = design.model_dump()
    saved = tmp_path / 'authored.json'
    saved.write_text(design.model_dump_json())
    digest = hashlib.sha256(saved.read_bytes()).hexdigest()
    net = design.nets[0]
    rows = routing.simple_routes(design, net, definitions)
    original = rows[0]
    assert any(f[0] == 'source_protected' for f in routing.route_obstructions(design, net, original, {}, definitions, {}))
    clear = [(i, route) for i, route in enumerate(rows) if len(route) == 1 and
             not routing.route_obstructions(design, net, route, {}, definitions, {})]
    assert clear
    i, route = clear[0]
    assert route[0].depth < original[0].depth
    assert route[0].diameter == original[0].diameter == 8
    assert (route[0].face, route[0].u, route[0].v) == ('right', 60, 88)
    snapshot = routing._ProposalSnapshot(design, definitions, {}, {})
    option = dict(key=f'simple_{i}', route=route, risk=0, cost=0)
    assert routing._verify_route_candidate(design, net, option, snapshot), option
    assert routing._candidate_admitted(option, net)
    assert routing.route_from_variant(design, net, option['key'], definitions, {}, {}) == route
    assert design.model_dump() == before
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == digest
    # Exact checks must not mutate a production solid sharing Boolean operands.
    from manifold.validation import validate
    target = design.model_copy(deep=True)
    target.features.extend(option['route'])
    g = geometry.build_geometry(target, definitions, {}, {})
    assert g.production.isValid()
    volume = g.production.Volume()
    routing.authorize_generated_contacts(target, g)
    validate(target, g)
    assert g.production.isValid()
    assert g.production.Volume() == pytest.approx(volume, abs=1e-6)
