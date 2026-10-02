"""Project/net precedence and the shared thick-cylinder ligament screen.

Resolved values are views, never copied into authored Net overrides. This is a
PMC engineering calculation; source yield/proof is not vendor allowable stress.
"""
from functools import lru_cache
import math


def effective_conditions(design,net):
    defaults=design.project_defaults
    result={}
    for field,source in (('pressure_bar','pressure_source'),('flow_lpm','flow_source'),
                         ('velocity_limit','velocity_source'),('drilling_mode','drilling_mode_source')):
        override=getattr(net,field);value=override if override is not None else getattr(defaults,field)
        result[field]=value;result[source]='net' if override is not None else 'project' if value is not None else 'unspecified'
    return result


def effective_net(design,net):
    values=effective_conditions(design,net)
    return net.model_copy(update={key:values[key] for key in ('pressure_bar','flow_lpm','velocity_limit','drilling_mode')})


@lru_cache(maxsize=64)
def _material_basis(material_id,database_stamp):
    from .engineering_db import _connect
    from .engineering_facts import resolved_engineering_facts
    with _connect() as db:
        rows=db.execute("SELECT id FROM technical_identities WHERE domain='material' AND material_id=?",(material_id,)).fetchall()
        if len(rows)!=1:return None
        facts=resolved_engineering_facts('material',rows[0][0],connection=db)
    for property in ('yield_strength','yield_strength_Rp0.2'):
        fact=facts['facts'][property]
        if fact['status']=='SOURCE_BACKED' and fact.get('engineering_usable') and fact.get('value',0)>0:
            return dict(property=property,source_strength_mpa=fact['value'],identity_id=rows[0][0],
                        material_id=material_id,value_kind=fact.get('value_kind'),status='SOURCE_BACKED')
    return None


def material_strength(design):
    factor=design.rules.pressure_safety_factor
    if design.rules.allowable_stress_mpa is not None:
        # Preserve the legacy pre-factor input semantics exactly.
        return dict(status='LEGACY_OVERRIDE',property='legacy_stress_basis',
                    source_strength_mpa=design.rules.allowable_stress_mpa,
                    design_strength_mpa=design.rules.allowable_stress_mpa/factor,safety_factor=factor)
    from .engineering_db import database_path
    path=database_path()
    basis=_material_basis(design.block.material_id,(str(path),path.stat().st_mtime_ns)) if design.block.material_id else None
    if not basis:return dict(status='UNRESOLVED',source_strength_mpa=None,design_strength_mpa=None,safety_factor=factor)
    return {**basis,'design_strength_mpa':basis['source_strength_mpa']/factor,'safety_factor':factor}


def feature_ligament(design,feature,definitions=None,threads=None):
    ids={feature.circuit,feature.route_net,feature.frozen_net,*feature.circuits.values()}-{None}
    pressure=max((effective_conditions(design,n)['pressure_bar'] or 0 for n in design.nets if n.id in ids),default=0)
    if not pressure:return dict(automatic_mm=0.0,status='UNSPECIFIED_PRESSURE',pressure_bar=None)
    strength=material_strength(design);stress=strength['design_strength_mpa'];p=pressure/10
    if stress is None or stress<=p:
        return dict(automatic_mm=None,status='UNRESOLVED' if stress is None else 'PRESSURE_EXCEEDS_STRENGTH',pressure_bar=pressure)
    diameter=feature.diameter or 0
    if feature.definition:
        if definitions is None:
            from .engineering_db import definitions_for_design
            definitions=definitions_for_design(design)
        definition=definitions[feature.definition]
        diameter=max((z.diameter for z in definition.zones if feature.kind=='port' or feature.circuits.get(z.id) in ids),default=0)
    elif feature.kind=='mounting':return dict(automatic_mm=0.0,status='NON_HYDRAULIC',pressure_bar=None)
    return dict(automatic_mm=diameter/2*(math.sqrt((stress+p)/(stress-p))-1),status='CALCULATED',pressure_bar=pressure)


def required_wall(design,*features,definitions=None,threads=None):
    # Unresolved pressure is separately a hard engineering failure. Zero here
    # means only non-intersection, never an assumed pressure strength or 7 mm.
    return max([design.rules.minimum_wall or 0]+[
        feature_ligament(design,f,definitions,threads)['automatic_mm'] or 0 for f in features])


def wall_unresolved(design,*features,definitions=None):
    return any(feature_ligament(design,f,definitions)['automatic_mm'] is None for f in features)


def planning_wall(design,net=None,definitions=None):
    key=(design.rules.minimum_wall,design.rules.allowable_stress_mpa,design.rules.pressure_safety_factor,
         design.block.material_id,design.project_defaults.pressure_bar,
         tuple((n.id,n.pressure_bar,n.diameter) for n in design.nets),
         tuple((f.id,f.definition,f.diameter,f.circuit,f.route_net,f.frozen_net,f.suppressed,tuple(f.circuits.items())) for f in design.features),
         id(definitions),net.id if net else None,net.diameter if net else None)
    cached=getattr(design,'_planning_ligament',None)
    if cached and cached[0]==key:return cached[1]
    features=[f for f in design.features if not f.suppressed]
    if net is not None:
        from .schema import Feature
        features.append(Feature(id='ligament_probe',kind='drilling',face='top',u=0,v=0,diameter=net.diameter,depth=1,circuit=net.id))
    value=required_wall(design,*features,definitions=definitions)
    object.__setattr__(design,'_planning_ligament',(key,value))
    return value


def project_engineering_context(design):
    from .engineering_db import tool_definitions
    from .sizing import route_sizing
    tools=tool_definitions('drill')
    nets=[]
    for n in design.nets:
        try:sizing=route_sizing(n,tools=tools,preferred_unit=design.project_context,design=design)
        except ValueError as exc:sizing=dict(status='UNRESOLVED_TOOL',reason=str(exc))
        nets.append(dict(id=n.id,overrides={k:getattr(n,k) for k in ('pressure_bar','flow_lpm','velocity_limit','drilling_mode')},
                         effective=effective_conditions(design,n),sizing=sizing))
    return dict(project_defaults=design.project_defaults.model_dump(),project_unit_preference=design.project_context,
        criteria=dict(pressure_safety_factor=design.rules.pressure_safety_factor,envelope_max=design.constraints.envelope_max,
                      envelope_min=design.constraints.envelope_min,routing_priority=design.constraints.priority),material_strength=material_strength(design),
        project_minimum_wall=design.rules.minimum_wall,preferred_wall_margin=design.constraints.preferred_wall_margin,
        nets=nets)
