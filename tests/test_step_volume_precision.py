from pathlib import Path
from types import SimpleNamespace
from manifold.cad import cq
from manifold.schema import Design
from manifold.geometry import build_geometry
from manifold.cad_acceptance import step_round_trip


def test_eight_source_cavities_step_uses_converged_mass_without_changing_geometry(tmp_path):
    design=Design.model_validate_json((Path(__file__).parent/'fixtures'/'ai-eight-cavity-step.json').read_text(encoding='utf-8'))
    before=design.model_dump()
    g=build_geometry(design)
    assert g.production.isValid() and len(g.production.Solids())==1
    row=step_round_trip(g,tmp_path/'production.step')
    imported=cq.importers.importStep(str(tmp_path/'production.step')).val()
    # Same real solids, different parameterization: fixed quadrature is too
    # inaccurate for this existing absolute engineering gate.
    assert abs(imported.Volume()-g.production.Volume())>0.01
    assert row['status']=='PASS' and row['valid'] and row['solids']==1
    assert row['volume_delta_mm3']<0.000001
    assert row['volume_measurement']['converged']
    assert max(row['volume_measurement']['convergence_mm3'])<0.001
    assert design.model_dump()==before


def test_real_volume_loss_still_fails_the_unchanged_absolute_gate(tmp_path,monkeypatch):
    box=cq.Solid.makeBox(10,10,10)
    changed=box.cut(cq.Solid.makeBox(.02,1,1))
    assert changed.isValid() and len(changed.Solids())==1
    monkeypatch.setattr(cq.importers,'importStep',lambda _:cq.Workplane(obj=changed))
    row=step_round_trip(SimpleNamespace(production=box),tmp_path/'changed.step')
    assert row['status']=='FAIL' and row['volume_delta_mm3']>0.01
    assert row['volume_measurement']['converged']
