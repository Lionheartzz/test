"""Source-bound construction closures, separate from hydraulic bore sizing."""
from functools import lru_cache
from contextlib import closing
import json
import math
import os

from .engineering_db import _connect,database_path


@lru_cache(maxsize=4)
def _catalog(path,mtime,size):
    with closing(_connect(path)) as db:
        rows=[]
        for raw in db.execute('''SELECT c.*,p.unit_system,p.active AS port_active,p.usable AS port_usable
            FROM closure_definitions c LEFT JOIN external_port_definitions p ON p.id=c.construction_port_definition_id'''):
            row=dict(raw);row['machining']=json.loads(row['machining_json']);row['envelope']=json.loads(row['envelope_json']);rows.append(row)
        return tuple(rows)


@lru_cache(maxsize=8)
def _configured_path(setting):
    return database_path()


def catalog():
    p=_configured_path(os.environ.get('PMC_ENGINEERING_DB',''));s=p.stat()
    return _catalog(p,s.st_mtime_ns,s.st_size)


@lru_cache(maxsize=4)
def _aliases(path,mtime,size):
    with closing(_connect(path)) as db:
        if db.execute('PRAGMA user_version').fetchone()[0]<7:return {}
        return dict(db.execute('SELECT alias_id,closure_definition_id FROM closure_definition_aliases'))


def aliases():
    p=_configured_path(os.environ.get('PMC_ENGINEERING_DB',''));s=p.stat()
    return _aliases(p,s.st_mtime_ns,s.st_size)


def profile(closure):
    return next((r for r in closure.get('machining',[]) if r.get('operation')=='SOURCE_EXPANDER_ENTRY'),None)


def compatible(feature,closure):
    p=profile(closure)
    if not closure['active'] or not closure['usable'] or not closure.get('port_active') or not closure.get('port_usable') or not p:
        return False
    values=[closure.get('engagement_mm'),p.get('diameter_mm'),p.get('depth_mm'),p.get('hydraulic_diameter_max_mm'),
            closure['envelope'].get('diameter_mm')]
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in values):return False
    height=closure['envelope'].get('height_mm')
    if not isinstance(height,(int,float)) or not math.isfinite(height) or height<0:return False
    if not feature.plugged or feature.kind!='drilling':return False
    if feature.direction:
        from .kinematics import FACE_AXES
        if abs(feature.direction[FACE_AXES[feature.face][2]])<1-1e-8:return False
    if feature.depth<=closure['engagement_mm'] or feature.diameter>p['hydraulic_diameter_max_mm']+1e-6:return False
    return p.get('transition_angle_degrees')==120 and p['diameter_mm']>feature.diameter and entry_depth(feature,closure)<feature.depth


def choices(feature,unit):
    return sorted((c for c in catalog() if compatible(feature,c)),key=lambda c:(c['unit_system']!=unit,
        profile(c).get('default_order',0),c['model'],c['id']))


def bound(feature):
    identifier=aliases().get(feature.closure_definition_id,feature.closure_definition_id) if feature.closure_definition_id else None
    return next((r for r in catalog() if r['id']==identifier),None) if identifier else None


def plug_diameter(feature):
    closure=bound(feature)
    return profile(closure)['diameter_mm'] if closure and compatible(feature,closure) else feature.diameter


def normalize(feature,closure):
    return feature.model_copy(update=dict(closure_definition_id=closure['id'],plug_length=closure['engagement_mm'],
        clearance_diameter=closure['envelope']['diameter_mm'],clearance_height=closure['envelope']['height_mm']))


def bind_route(design,features):
    result=[]
    for feature in features:
        if not feature.plugged or feature.suppressed:result.append(feature);continue
        if feature.closure_definition_id:
            closure=bound(feature)
            result.append(normalize(feature,closure) if closure and compatible(feature,closure) else feature);continue
        candidates=choices(feature,design.project_context)
        # Source entry machining must fit the actual block face. No closest-size
        # selection: each candidate has its own declared entry/interface profile.
        from .kinematics import FACE_AXES
        u,v,axis,_=FACE_AXES[feature.face];lengths=(design.block.length,design.block.width,design.block.height)
        for closure in candidates:
            # v7 explicitly preserves the established expander default. Other
            # technologies remain manual choices unless explicitly preferred.
            if profile(closure).get('automatic_default',True) is not True:continue
            radius=closure['envelope']['diameter_mm']/2+design.rules.minimum_wall
            if radius<=feature.u<=lengths[u]-radius and radius<=feature.v<=lengths[v]-radius:
                if feature.direction and abs(feature.direction[axis])<1-1e-8:continue
                feature=normalize(feature,closure);break
        result.append(feature)
    return result


def normalize_design(design,*,resolve_generated=False):
    """Pure copy: never rewrite stored JSON or authored unresolved closures."""
    target=design.model_copy(deep=True)
    target.features=[normalize(f,c) if (c:=bound(f)) and compatible(f,c) else f for f in target.features]
    if resolve_generated:
        automatic={n.id for n in target.nets if n.routing=='automatic'}
        target.features=[bind_route(target,[f])[0] if f.route_net in automatic and not f.frozen_net else f for f in target.features]
    return target


def entry_depth(feature,closure):
    p=profile(closure)
    return p['depth_mm']+(p['diameter_mm']-feature.diameter)/2/math.tan(math.radians(p['transition_angle_degrees']/2))
