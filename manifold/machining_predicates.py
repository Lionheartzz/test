"""Local narrow-phase machining checks; never a full design acceptance.

Enclosing profiles can prove separation, not intersection. Uncertain pairs
use the same finite primitives / installed plugs as production. Measurements
are cached by complete world geometry, independently of engineering thresholds.
"""
from enum import Enum
import math

from .kinematics import pose,dimensions
from .cad_geometry import cad_operation,checked_shape,checked_intersection,solid_volume


class ContactState(Enum):
    SAFE='safe'
    VIOLATION='violation'
    EXACT_REQUIRED='exact_required'


def _remember(cache,key,value,limit=1024):
    cache[key]=value
    if len(cache)>limit:cache.pop(next(iter(cache)))
    return value


def cut_key(cut,block):
    return (pose(cut['feature'],block),cut['start'],cut['end'],
            cut['radius_start'],cut['radius_end'],cut['inner_radius'])


def cut_shape(cut,block,cache):
    key=('primitive',cut_key(cut,block));shapes=cache.setdefault('local_shapes',{})
    if key in shapes:return shapes[key]
    from .geometry import cylinder,at
    from .cad import cq
    origin,direction=pose(cut['feature'],block)
    context=dict(scope='candidate',feature_ids=[cut['feature'].id])
    with cad_operation('routing.local_primitive',context):
        if abs(cut['radius_start']-cut['radius_end'])<1e-12:
            shape=cylinder(origin,direction,2*cut['radius_start'],cut['start'],cut['end'])
        else:
            shape=cq.Solid.makeCone(cut['radius_start'],cut['radius_end'],cut['end']-cut['start'],
                cq.Vector(*at(origin,direction,cut['start'])),cq.Vector(*direction))
        if cut['inner_radius']:
            shape=shape.cut(cylinder(origin,direction,2*cut['inner_radius'],cut['start'],cut['end']))
    checked_shape(shape,'routing.local_primitive',context)
    return _remember(shapes,key,shape)


def feature_shape(feature,design,definitions,threads,modifiers,kind,cache):
    # The caller owns an immutable source context. Include source definitions
    # as well as position/stock: changing a library/profile cannot inherit CAD.
    definition=definitions.get(feature.definition)
    key=(kind,dimensions(design.block),feature.model_dump_json(),
         definition.model_dump_json() if definition else None,repr(threads),repr(modifiers))
    shapes=cache.setdefault('local_shapes',{})
    if key not in shapes:
        from .geometry import feature_geometry
        context=dict(scope='candidate',feature_ids=[feature.id])
        with cad_operation('routing.local_'+kind,context):
            geometry=feature_geometry(design.model_copy(update=dict(features=[feature])),definitions,threads,modifiers)
            shape=geometry[4 if kind=='plug' else 3][feature.id]
        checked_shape(shape,'routing.local_'+kind,context,allow_empty=False)
        _remember(shapes,key,shape)
    return key,shapes[key]


def _bounds(shape):
    box=shape.BoundingBox()
    return ((box.xmin,box.xmax),(box.ymin,box.ymax),(box.zmin,box.zmax))


def bounds_state(first,second,clearance):
    gaps=[max(0,a[0]-b[1],b[0]-a[1]) for a,b in zip(first,second)]
    if clearance>0 and math.sqrt(sum(g*g for g in gaps))+1e-6>=clearance:return ContactState.SAFE
    if clearance==0 and any(a[1]<=b[0] or b[1]<=a[0] for a,b in zip(first,second)):return ContactState.SAFE
    return ContactState.EXACT_REQUIRED


def exact_state(first_key,first,second_key,second,clearance,cache,*,overlap=False,context=None):
    """Resolve uncertainty, or raise a checked CAD error; never fail open."""
    context=dict(scope='candidate',**(context or {}))
    checked_shape(first,'routing.local_contact.left',context,allow_empty=False)
    checked_shape(second,'routing.local_contact.right',context,allow_empty=False)
    with cad_operation('routing.local_contact.bounds',context):
        separated=bounds_state(_bounds(first),_bounds(second),clearance)==ContactState.SAFE
    if separated:return ContactState.SAFE
    measurements=cache.setdefault('local_measurements',{})
    key=('volume' if overlap or clearance==0 else 'distance',frozenset((first_key,second_key)))
    if key not in measurements:
        if key[0]=='volume':
            common=checked_intersection(first,second,'routing.local_contact',context)
            value=solid_volume(common,'routing.local_contact.volume',context)
        else:
            checked_shape(first,'routing.local_distance.left',context)
            checked_shape(second,'routing.local_distance.right',context)
            with cad_operation('routing.local_distance',context):value=first.distance(second)
            if not math.isfinite(value) or value<0:raise ValueError('Invalid local machining distance')
        _remember(measurements,key,value,2048)
        stats=cache.setdefault('local_exact_evaluations',{})
        stats[key[0]]=stats.get(key[0],0)+1
    value=measurements[key]
    violated=value>1e-6 if key[0]=='volume' else value+1e-6<clearance
    return ContactState.VIOLATION if violated else ContactState.SAFE


def cuts_violate(first,second,block,clearance,cache):
    return exact_state(('primitive',cut_key(first,block)),cut_shape(first,block,cache),
        ('primitive',cut_key(second,block)),cut_shape(second,block,cache),clearance,cache,
        context=dict(feature_ids=[first['feature'].id,second['feature'].id]))==ContactState.VIOLATION


def plug_violate(plug,cut,design,definitions,threads,modifiers,cache):
    key,shape=feature_shape(plug,design,definitions,threads,modifiers,'plug',cache)
    return exact_state(key,shape,('primitive',cut_key(cut,design.block)),cut_shape(cut,design.block,cache),
                       0,cache,overlap=True,context=dict(feature_ids=[plug.id,cut['feature'].id]))==ContactState.VIOLATION


def access_violate(first,second,design,definitions,threads,modifiers,cache):
    if design.rules.minimum_access_gap==0:return False
    a,aa=feature_shape(first,design,definitions,threads,modifiers,'envelope',cache)
    b,bb=feature_shape(second,design,definitions,threads,modifiers,'envelope',cache)
    return exact_state(a,aa,b,bb,design.rules.minimum_access_gap,cache,
                       context=dict(feature_ids=[first.id,second.id]))==ContactState.VIOLATION
