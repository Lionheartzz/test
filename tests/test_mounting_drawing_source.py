"""Non-hydraulic plain installation holes required by the PMC drawing samples."""
import math
import pytest
from manifold.schema import Design,Feature
from manifold.geometry import build_geometry
from manifold.validation import validate
from manifold.routing import terminal_points


def source():
    return Design(name='Plain mounting example',block=dict(length=105,width=95,height=50,material='S50C'),
        features=[dict(id='H1',kind='mounting',face='top',u=20,v=20,diameter=12,depth=50,tip_angle=180,through=True),
                  dict(id='H2',kind='mounting',face='top',u=85,v=75,diameter=12,depth=50,tip_angle=180,through=True)])


def test_mounting_is_exact_stock_removal_without_hydraulic_nodes():
    design=source();g=build_geometry(design);report=validate(design,g)
    assert report['status']=='PASS',[c for c in report['checks'] if c['status']=='FAIL']
    assert not g.nodes and not g.circuits and not terminal_points(design)
    assert g.block.Volume()-g.production.Volume()==pytest.approx(2*math.pi*6**2*50,abs=1e-6)
    assert len(g.production.Solids())==1 and g.production.isValid()


def test_mounting_collision_and_unintentional_exit_remain_rejected():
    design=source();design.features[1].u=20;design.features[1].v=20
    report=validate(design,build_geometry(design))
    assert any(c['rule']=='mounting_separation' and c['status']=='FAIL' for c in report['checks'])
    design=source();design.features[0].through=False
    report=validate(design,build_geometry(design))
    assert any(c['rule']=='external_wall' and c['items']==['H1','bottom'] and c['status']=='FAIL' for c in report['checks'])
    design=source();design.features.append(Feature(id='P',kind='port',face='front',u=20,v=25,diameter=8,depth=40,circuit='P'))
    report=validate(design,build_geometry(design))
    assert any(c['rule']=='mounting_separation' and 'P' in c['items'] and c['status']=='FAIL' for c in report['checks'])


def test_mounting_contract_and_legacy_design_serialization():
    feature=Feature(id='P',kind='port',face='top',u=30,v=30,diameter=8,depth=20,circuit='P')
    assert 'through' not in feature.model_dump()
    assert Feature.model_validate(feature.model_dump()).model_dump()==feature.model_dump()
    for change in (dict(circuit='P'),dict(connects_to=['P']),dict(plugged=True),dict(tip_angle=118)):
        with pytest.raises(ValueError):Feature.model_validate({**source().features[0].model_dump(),**change})
    with pytest.raises(ValueError,match='thickness'):
        d=source().model_dump();d['block']['height']=60;Design.model_validate(d)


def test_resolved_parent_face_cannot_turn_a_through_hole_into_a_blind_cut():
    from manifold.kinematics import resolve_parents
    design=source()
    design.features[0].parent_id='H2'
    design.features[1].face='front';design.features[1].through=False;design.features[1].depth=10;design.features[1].v=20
    # Authored H1 is a valid 50 mm top through hole. Parent resolution moves it to a 95 mm axis.
    design=Design.model_validate(design.model_dump())
    resolved=resolve_parents(design)
    report=validate(resolved,build_geometry(resolved))
    assert any(c['rule']=='mounting_through_extent' and c['items']==['H1'] and c['status']=='FAIL' for c in report['checks'])
