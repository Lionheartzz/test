"""Production CAD gates shared by authoritative route selection and Build."""
from pathlib import Path
from tempfile import TemporaryDirectory
import math
from .cad import cq
from .timing import phase


def production_topology(geometry):
    return dict(valid=bool(geometry.production.isValid()), solids=len(geometry.production.Solids()))


def topology_clear(geometry):
    state=production_topology(geometry)
    return state['valid'] and state['solids']==1


def volume_comparison(native, imported):
    """Compare converged volumes, not non-adaptive quadrature approximations.

    STEP can reparameterize the same curved faces. OCCT's default fixed
    quadrature then gives different mass errors, accumulating with cavity count.
    Two adaptive integrations must agree within 0.001 mm³ on EACH solid; the
    existing absolute 0.01 mm³ serialization gate is unchanged.
    """
    box=native.BoundingBox()
    scale=max(1,box.xlen*box.ylen*box.zlen)
    tolerance=min(1e-8,1e-4/scale)
    pairs=[(solid.Volume(tolerance),solid.Volume(tolerance/100)) for solid in (native,imported)]
    convergence=[abs(coarse-fine) for coarse,fine in pairs]
    finite=all(math.isfinite(value) for pair in pairs for value in pair)
    return dict(delta=abs(pairs[0][1]-pairs[1][1]),converged=finite and max(convergence)<0.001,
                native_mm3=pairs[0][1],step_mm3=pairs[1][1],convergence_mm3=convergence,
                integration_tolerance=tolerance/100)


def step_round_trip(geometry, path=None):
    if path is None:
        with TemporaryDirectory(prefix='pmc-step-gate-') as temporary:
            return step_round_trip(geometry,Path(temporary)/'production.step')
    try:
        with phase('step.export'):
            cq.exporters.export(geometry.production,str(path))
        with phase('step.round_trip'):
            imported=cq.importers.importStep(str(path)).val()
            valid=bool(imported.isValid());solids=len(imported.Solids())
            volumes=volume_comparison(geometry.production,imported)
            delta=volumes['delta']
        passed=valid and solids==1 and volumes['converged'] and delta<0.01
        conditions=[]
        if not valid:conditions.append('invalid STEP solid')
        if solids!=1:conditions.append(f'{solids} STEP solids')
        if not volumes['converged']:conditions.append('volume integration did not converge')
        if delta>=0.01:conditions.append('volume outside tolerance')
        actual=round(delta,8) if passed else '; '.join(conditions)+f'; volume Δ {delta:.8f} mm³'
        return dict(rule='step_round_trip',items=['block'],status='PASS' if passed else 'FAIL',
                    actual=actual,required='Valid single solid; volume Δ < 0.01 mm³',unit='mm³' if passed else '',
                    valid=valid,solids=solids,volume_delta_mm3=delta,
                    volume_measurement=volumes,
                    message='STEP reimport: valid single solid and matching volume.')
    except Exception as exc:
        return dict(rule='step_round_trip',items=['block'],status='FAIL',actual='STEP export/reimport failed',
                    required='Valid single solid; volume Δ < 0.01 mm³',unit='',
                    valid=False,solids=None,volume_delta_mm3=None,message=str(exc)[:2000] or type(exc).__name__)


def add_step_check(report, check):
    """Replace a gate result without double counting it at Build."""
    report['checks']=[c for c in report['checks'] if c['rule']!='step_round_trip']+[check]
    report['counts']={s:sum(c['status']==s for c in report['checks']) for s in ('PASS','WARNING','FAIL')}
    report['status']='FAIL' if report['counts']['FAIL'] else 'WARNING' if report['counts']['WARNING'] else 'PASS'
