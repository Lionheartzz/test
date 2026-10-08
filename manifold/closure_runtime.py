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
        threads={r['id']:dict(r) for r in db.execute('SELECT * FROM thread_definitions')}
        tools={r['id']:dict(r) for r in db.execute('SELECT * FROM tool_definitions')}
        rows=[]
        for raw in db.execute('''SELECT c.*,p.unit_system,p.active AS port_active,p.usable AS port_usable,p.unusable_reason AS port_reason
            FROM closure_definitions c LEFT JOIN external_port_definitions p ON p.id=c.construction_port_definition_id'''):
            row=dict(raw);row['machining']=json.loads(row['machining_json']);row['envelope']=json.loads(row['envelope_json'])
            p=profile(row)
            row['closure_thread']=threads.get(p.get('thread_definition_id')) if p else None
            row['closure_tools']={op['tool_id']:tools.get(op['tool_id']) for op in row['machining'] if op.get('tool_id')}
            rows.append(row)
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
    return next((r for r in closure.get('machining',[]) if r.get('operation') in ('SOURCE_EXPANDER_ENTRY','SOURCE_FORM_PORT_ENTRY')),None)


def compatible(feature,closure):
    p=profile(closure)
    if not closure['active'] or not closure['usable'] or not closure.get('port_active') or not p:
        return False
    if not closure.get('port_usable') and not (p.get('independent_machining_interface') and closure.get('port_reason')=='External port requires one executable hydraulic interface'):
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
    if p['operation']=='SOURCE_FORM_PORT_ENTRY':
        thread=closure.get('closure_thread')
        return bool(thread and thread['usable'] and thread['active'] and thread['tap_diameter_mm']>0
                    and closure_tooling(closure) and entry_depth(feature,closure)<feature.depth)
    return p.get('transition_angle_degrees')==120 and p['diameter_mm']>feature.diameter and entry_depth(feature,closure)<feature.depth


def closure_tooling(closure):
    for op in closure['machining']:
        if not op.get('tool_id'):continue
        tool=closure.get('closure_tools',{}).get(op['tool_id'])
        if not tool or not tool['active'] or not tool['usable'] or tool['tool_type']!=op['tool_type']:
            return False
        if abs(tool['diameter_mm']-op['diameter_mm'])>1e-6 or tool['max_depth_mm']+1e-6<op['depth_mm']:return False
    return True


def choices(feature,unit):
    # Keep the established expander/SAE defaults when new qualified families are
    # added. This is an engineering technology order, never a product preference.
    family_order={'expander':0,'sae-short-port':1,'sae-standard-port':1,'metric-iso6149':2}
    return sorted((c for c in catalog() if compatible(feature,c)),key=lambda c:(family_order.get(profile(c).get('closure_type','expander'),2),c['unit_system']!=unit,
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
        if feature.closure_selection_mode=='manual' or feature.frozen_net:
            result.append(feature);continue
        candidates=choices(feature,design.project_context)
        # Source entry machining must fit the actual block face. No closest-size
        # selection: each candidate has its own declared entry/interface profile.
        from .kinematics import FACE_AXES
        from .engineering_conditions import required_wall
        u,v,axis,_=FACE_AXES[feature.face];lengths=(design.block.length,design.block.width,design.block.height)
        for closure in candidates:
            # v7 explicitly preserves the established expander default. Other
            # technologies remain manual choices unless explicitly preferred.
            if profile(closure).get('automatic_default',True) is not True:continue
            radius=closure['envelope']['diameter_mm']/2+required_wall(design,feature)
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
    if p['operation']=='SOURCE_FORM_PORT_ENTRY':
        r=p['source_profile_row'];scale=p['source_scale']
        pilot=p.get('pilot_circle',3)
        return r[f'Circle{pilot}Depth']*scale+(float(r[f'Circle{pilot}Dia'])*scale-feature.diameter)/2/math.tan(math.radians(r[f'Circle{pilot}Angle']))
    return p['depth_mm']+(p['diameter_mm']-feature.diameter)/2/math.tan(math.radians(p['transition_angle_degrees']/2))


def formed_cutting_primitives(diameter,depth,tip_angle,source,scale):
    """One normalized contour for production geometry and machining output."""
    from .import_mdtools import profile as source_profile
    row=dict(source)
    row.update(Circle12Dia=str(diameter/scale),Circle12Depth=depth/scale,Circle12Angle=tip_angle/2)
    return source_profile(row,scale)[1]


def cutting_primitives(feature,closure):
    p=profile(closure)
    if p['operation']=='SOURCE_FORM_PORT_ENTRY':
        return formed_cutting_primitives(feature.diameter,feature.depth,feature.tip_angle,p['source_profile_row'],p['source_scale'])
    end=entry_depth(feature,closure)
    result=[dict(kind='cylinder',start=0,end=feature.depth,diameter=feature.diameter),
            dict(kind='cylinder',start=0,end=p['depth_mm'],diameter=p['diameter_mm']),
            dict(kind='cone',start=p['depth_mm'],end=end,diameter=p['diameter_mm'],end_diameter=feature.diameter)]
    if feature.tip_angle!=180:
        result.append(dict(kind='cone',start=feature.depth,
                           end=feature.depth+feature.diameter/2/math.tan(math.radians(feature.tip_angle/2)),
                           diameter=feature.diameter,end_diameter=0))
    return result
