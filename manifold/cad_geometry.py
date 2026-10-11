"""Checked CAD contact operations. Empty geometry is not an unknown Boolean."""
from contextlib import contextmanager
import math
import traceback
from .cad import cq
from OCP.Standard import Standard_Failure
from . import timing


class GeometryEvaluationError(RuntimeError):
    def __init__(self,record):
        self.record=record
        self.public_message=('Source hydraulic geometry is invalid or unavailable. Inspect local calculation diagnostics.'
            if record.get('scope')=='source' else
            'Routing candidate geometry could not be evaluated. Inspect local calculation diagnostics.'
            if record.get('scope')=='candidate' else
            'Hydraulic geometry could not be evaluated. Inspect local calculation diagnostics.')
        super().__init__(self.public_message)


def local_traceback(exc):
    # Frames only: exception values/locals can contain whole validation inputs.
    return (''.join(traceback.format_tb(exc.__traceback__,limit=16))+type(exc).__name__)[-12000:]


def error_record(operation,context=None,*,reason,exception=None,states=None):
    source=timing.summary().get('diagnostics',{}).get('request_source',[])
    return {**(context or {}),'cad_operation':operation,'reason_code':reason,
        'phase':timing.summary()['phase'],'exception_type':type(exception).__name__ if exception is not None else 'GeometryEvaluationError',
        'source_revision':source[-1].get('source_revision') if source else None,
        'shape_states':states or {},'traceback':local_traceback(exception) if exception is not None else ''}


@contextmanager
def cad_operation(operation,context=None):
    """Contain only identified OCCT failures; unrelated Python errors propagate."""
    try:
        yield
    except GeometryEvaluationError as exc:
        for key,value in (context or {}).items():exc.record.setdefault(key,value)
        if not exc.record.get('traceback'):exc.record['traceback']=local_traceback(exc)
        raise
    except Standard_Failure as exc:
        raise GeometryEvaluationError(error_record(operation,context,reason='OCCT_FAILURE',exception=exc)) from exc
    except ValueError as exc:
        # The exact pinned CadQuery shapetype()/cast() null-topology error.
        # Do not swallow arbitrary ValueError or treat a failed Boolean as zero.
        if str(exc)!='Null TopoDS_Shape object':raise
        raise GeometryEvaluationError(error_record(operation,context,reason='NULL_SHAPE_CAST',exception=exc,
            states={'result':{'null':True,'valid':None}})) from exc


def checked_shape(shape,operation,context=None,*,allow_empty=True):
    state={'null':None,'valid':None,'empty':None}
    try:
        with cad_operation(operation+'.status',context):
            state['null']=True if shape is None else shape.isNull()
            if state['null']:
                raise GeometryEvaluationError(error_record(operation,context,reason='NULL_SHAPE',states={'shape':state}))
            # Compound.__bool__ uses TopoDS_Iterator.More(). Only use it AFTER null
            # checking; an empty non-null compound is a legitimate empty result.
            state['empty']=isinstance(shape,cq.Compound) and not bool(shape)
            state['valid']=shape.isValid()
            if not state['valid']:
                raise GeometryEvaluationError(error_record(operation,context,reason='INVALID_TOPOLOGY',states={'shape':state}))
            if state['empty'] and not allow_empty:
                raise GeometryEvaluationError(error_record(operation,context,reason='EMPTY_INPUT_SHAPE',states={'shape':state}))
    except GeometryEvaluationError as exc:
        exc.record.setdefault('shape_states',{}).setdefault('shape',dict(state))
        raise
    return state


def checked_intersection(a,b,operation,context=None):
    first=checked_shape(a,operation+'.left',context)
    second=checked_shape(b,operation+'.right',context)
    if first['empty']:return a
    if second['empty']:return b
    try:
        with cad_operation(operation,context):result=a.intersect(b)
        checked_shape(result,operation+'.result',context)
    except GeometryEvaluationError as exc:
        exc.record.setdefault('shape_states',{}).update(left=first,right=second)
        raise
    return result


def solid_volume(shape,operation,context=None):
    state=checked_shape(shape,operation,context)
    if state['empty']:return 0.0
    with cad_operation(operation+'.solids',context):solids=shape.Solids()
    # CadQuery Shape.Volume() calls dimension-dependent computeMass(): a face
    # can report surface area. Only actual solids supply hydraulic overlap.
    volume=0.0
    for solid in solids:
        checked_shape(solid,operation+'.solid',context,allow_empty=False)
        with cad_operation(operation+'.volume',context):value=solid.Volume()
        if not math.isfinite(value) or value<0:
            raise GeometryEvaluationError(error_record(operation,context,reason='INVALID_VOLUME'))
        volume+=value
    return volume


def require_fluid_solid(shape,operation,context=None):
    checked_shape(shape,operation,context,allow_empty=False)
    if solid_volume(shape,operation,context)<=1e-6:
        raise GeometryEvaluationError(error_record(operation,context,reason='NO_FLUID_SOLID'))
