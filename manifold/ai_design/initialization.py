"""Geometry-derived envelopes and route feedback for NEW AI candidates only.

These are placement hypotheses, never machining definitions or acceptance.
No circle packing, Model mutation, or alternative hydraulic path algorithm.
"""
import itertools
import math
from collections import defaultdict

from ..kinematics import FACE_AXES,dimensions,pose
from ..engineering_conditions import required_wall,effective_net
from .design_space import radius,pack_topology,signature


def source_extents(design,feature,definitions,threads,modifiers):
    from ..routing import _manufacturing_cuts,cylinder_bounds
    origin,inward=pose(feature,design.block);axis=FACE_AXES[feature.face][2]
    bounds=[]
    for cut in _manufacturing_cuts(feature,definitions,threads,modifiers):
        bounds.append(cylinder_bounds(cut['feature'],design.block,cut['start'],cut['end'],
            2*max(cut['radius_start'],cut['radius_end'])))
    wall=required_wall(design,feature,definitions=definitions)
    depth=max([0]+[(b[axis][1]-origin[axis]) if inward[axis]>0 else origin[axis]-b[axis][0] for b in bounds])
    radial=radius(feature,definitions) if feature.kind in ('cavity','port') else max([0.]+[
        max(abs(b[i][j]-origin[i]) for i in FACE_AXES[feature.face][:2] for j in (0,1)) for b in bounds])
    clearance=(definitions[feature.definition].clearance_diameter if feature.definition else feature.clearance_diameter)/2 if feature.kind in ('cavity','port') else 0
    spans={i:max([clearance]+[b[i][1]-origin[i] for b in bounds])-min([-clearance]+[b[i][0]-origin[i] for b in bounds])
           for i in FACE_AXES[feature.face][:2]}
    return dict(feature=feature.id,face=feature.face,radius=radial,depth=depth,
        wall=wall,bounds=bounds,origin=origin,planar_spans=spans)


def envelope(design,definitions,domain,threads,modifiers,*,row_axis=0,corridors=False):
    """Measured face rows/opposite depths, fixed machining and route allowance.

    Row size is a constructive seed, not a proof of minimum packing volume.
    A different face arrangement can require much less stock.
    """
    sizes=dimensions(design.block);need=[1.,1.,1.];groups=defaultdict(list);depths=defaultdict(float)
    facts=[source_extents(design,f,definitions,threads,modifiers) for f in design.features
           if not f.suppressed and not f.route_net]
    by_id={f.id:f for f in design.features}
    for fact in facts:
        f=by_id[fact['feature']];u,v,axis,sign=FACE_AXES[f.face];margin=fact['radius']+fact['wall']
        need[u]=max(need[u],2*margin);need[v]=max(need[v],2*margin)
        depths[(axis,sign)]=max(depths[(axis,sign)],fact['depth']+fact['wall'])
        if f.id not in domain.movable or f.id in domain.fixed_positions:
            need[u]=max(need[u],f.u+margin);need[v]=max(need[v],f.v+margin)
        else:groups[f.face].append(fact)
    for axis in range(3):need[axis]=max(need[axis],depths[(axis,1)]+depths[(axis,-1)])
    for face,rows in groups.items():
        u,v,_,_=FACE_AXES[face];along,across=(u,v) if row_axis==0 else (v,u)
        # Fixed source cuts on a transverse face occupy real machining depth,
        # not just the nominal port entry radius.
        fixed_end=max([0.]+[max(b[along][1] for b in r['bounds']) for r in facts
            if r['feature'] not in domain.movable and r['bounds'] and FACE_AXES[r['face']][2]==along and FACE_AXES[r['face']][3]>0])
        gap=max(design.rules.minimum_access_gap,max(r['wall'] for r in rows))
        need[along]=max(need[along],fixed_end+sum(2*(r['radius']+r['wall']) for r in rows)+gap*max(0,len(rows)-1))
        need[across]=max(need[across],max(2*(r['radius']+r['wall']) for r in rows))
    if corridors:
        bore=max((effective_net(design,n).diameter for n in design.nets),default=0)
        lane=bore+2*max((r['wall'] for r in facts),default=0)+design.rules.minimum_access_gap
        for axis in domain.dimension_axes:need[axis]+=lane
    lower=design.constraints.envelope_min or (1,)*3
    upper=design.constraints.envelope_max or (2000,)*3
    target=tuple(max(lower[i],min(upper[i],math.ceil(need[i]*100)/100)) if i in domain.dimension_axes else sizes[i] for i in range(3))
    return target,dict(measured_requirements=need,source_extents=facts,route_corridor_allowance=corridors,
        limited_axes=[i for i in range(3) if need[i]>upper[i] or i not in domain.dimension_axes and need[i]>sizes[i]],
        limits_source=domain.hard_dimensions['explicit_axes'],supported_maximum_mm=2000)


def with_dimensions(design,sizes):
    target=design.model_copy(deep=True)
    for name,value in zip(('length','width','height'),sizes):setattr(target.block,name,value)
    return target


def occupied_dimensions(design,definitions,domain,threads,modifiers):
    need=[1.]*3;current=dimensions(design.block)
    for f in design.features:
        if f.suppressed or f.route_net:continue
        r=source_extents(design,f,definitions,threads,modifiers);u,v,axis,_=FACE_AXES[f.face]
        margin=r['radius']+r['wall']
        need[u]=max(need[u],f.u+margin);need[v]=max(need[v],f.v+margin)
        need[axis]=max(need[axis],r['depth']+r['wall'])
    lower=design.constraints.envelope_min or (1,)*3
    return tuple(max(lower[i],need[i]) if i in domain.dimension_axes else current[i] for i in range(3))


def dimension_proposals(design,definitions,domain,threads,modifiers):
    seen=set()
    for row_axis,corridors in itertools.product((0,1),(False,True)):
        sizes,reason=envelope(design,definitions,domain,threads,modifiers,row_axis=row_axis,corridors=corridors)
        if sizes in seen:continue
        seen.add(sizes)
        target=with_dimensions(design,sizes)
        # Repacking may fail as one heuristic. Keep the measured hypothesis so
        # other placement actions/faces can repair it; never abort initialization.
        packed=pack_topology(target,definitions,domain,threads,modifiers)
        if packed:
            tight=occupied_dimensions(packed,definitions,domain,threads,modifiers)
            if tight!=dimensions(packed.block):yield 'measured-envelope',with_dimensions(packed,tight),dict(**reason,reduction='actual_placed_machining_bounds')
        yield 'measured-envelope',packed or target,reason


def initial_candidates(design,definitions,domain,threads,modifiers):
    yield from dimension_proposals(design,definitions,domain,threads,modifiers)
    seen={signature(design)}
    # Six source-constrained face arrangements, with actual source-window
    # packing afterward. Inherited faces have no veto over these hypotheses.
    for face in FACE_AXES:
        target=design.model_copy(deep=True)
        for f in target.features:
            if f.kind=='cavity' and f.id in domain.movable and face in domain.faces(f) and f.id not in domain.fixed_positions:
                f.face=face
        key=signature(target)
        if key in seen:continue
        seen.add(key)
        yield from (( 'face-arrangement',d,dict(**reason,arrangement_face=face)) for _,d,reason in
            itertools.islice(dimension_proposals(target,definitions,domain,threads,modifiers),2))


def constraint_conflicts(design,definitions,domain,threads,modifiers):
    """Only individual, measured lower-bound contradictions are proven here."""
    conflicts=[];upper=design.constraints.envelope_max
    if not upper:return conflicts
    for f in design.features:
        if f.suppressed or f.kind not in ('cavity','port'):continue
        faces=domain.faces(f) if f.id in domain.movable else (f.face,);facts=[]
        for face in faces:
            probe=f.model_copy(update=dict(face=face));r=source_extents(design,probe,definitions,threads,modifiers)
            u,v,axis,_=FACE_AXES[face];need=[1.]*3
            # Current asymmetric bounds are NOT a lower bound over rotations.
            # Only a fixed rotation or the declared circular installation
            # envelope supports a planar impossibility claim here.
            circular=definitions[f.definition].clearance_diameter if f.definition else f.clearance_diameter
            need[u]=(r['planar_spans'][u] if f.id in domain.fixed_rotations else circular)+2*r['wall']
            need[v]=(r['planar_spans'][v] if f.id in domain.fixed_rotations else circular)+2*r['wall']
            need[axis]=r['depth']+r['wall']
            facts.append(dict(face=face,required=need,exceeded_axes=[i for i in range(3) if need[i]>upper[i]]))
        explicit=set(domain.hard_dimensions['explicit_axes']['maximum'])
        if facts and all(explicit.intersection(r['exceeded_axes']) for r in facts):
            conflicts.append(dict(feature=f.id,rule='explicit_envelope_and_source_machining',maximum=list(upper),permitted_faces=facts))
    return conflicts


def route_feedback(design,assessment,definitions,domain,threads,modifiers):
    """Convert actual missing/obstructed routes to interface/group hypotheses."""
    failed=set(assessment.get('blocked_nets',[]))
    failed.update(row['net'] for row in assessment.get('layout_feedback',[]))
    owners={m.split(':')[0] for n in design.nets if n.id in failed for m in n.members}
    owners.update(k for row in assessment.get('layout_feedback',[]) for k in row.get('source_blockers',[]))
    for n in design.nets:
        group={m.split(':')[0] for m in n.members}&domain.movable
        if n.id not in failed or not group:continue
        seen=set()
        for face in FACE_AXES:
            target=design.model_copy(deep=True)
            for f in target.features:
                if f.id in group and face in domain.faces(f) and f.id not in domain.fixed_positions:
                    f.face=face
            key=signature(target)
            if key in seen:continue
            seen.add(key)
            # Real group depth/port penetration determines the new envelope;
            # this is not a retry of the same fixed-geometry Router state.
            size,reason=envelope(target,definitions,domain,threads,modifiers)
            target=with_dimensions(target,size)
            packed=pack_topology(target,definitions,domain,threads,modifiers)
            if packed:yield 'feedback-connected-group',packed,dict(net=n.id,owners=sorted(group),cause=assessment.get('conflicts'),**reason)
    # Targeted individual and lane moves remain useful when changing a whole
    # group face conflicts with explicit ownership or another hydraulic circuit.
    from .design_space import actions
    for family,target in itertools.islice(actions(design,definitions,domain,threads,modifiers,owners),16):
        yield 'feedback-'+family,target,dict(owners=sorted(owners),blocked_nets=sorted(failed))
