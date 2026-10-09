"""Deterministic initial placement for explicitly created, editable projects.

This is an analytic starting arrangement, never a routing/clearance certificate.
It is not called by project load, Save, Validate, Build or Drawing.
"""
import math
from itertools import combinations
from .kinematics import FACE_AXES,dimensions,definition_planar_radius,clamp_placement


def machining_radius(definition):
    return max([definition_planar_radius(definition)]+[
        math.hypot(getattr(p,'offset_u',0),getattr(p,'offset_v',0))+
        max(p.diameter,getattr(p,'end_diameter',0))/2
        for p in definition.cutting_primitives or definition.stages])


def packing_dimensions(group,face,wall,gap,maximum,*,rectangular=False):
    radius=max(machining_radius(c['definition']) for c in group)
    pitch=2*radius+2*wall+gap
    u,v,_,_=FACE_AXES[face];choices=[]
    for cols in range(1,len(group)+1):
        rows=math.ceil(len(group)/cols);width,height=cols*pitch+2*wall,rows*pitch+2*wall
        if width<=maximum[u] and height<=maximum[v]:
            choices.append((max(width,height),width*height,cols,rows,width,height,pitch))
    if not choices and gap:return packing_dimensions(group,face,wall,0,maximum,rectangular=rectangular)
    if not choices:raise ValueError(f'{face}: source machining and installed footprints do not fit the requested block face.')
    chosen=min(choices,key=lambda r:(r[1],r[0],r[2:])) if rectangular else min(choices)
    return chosen[2:]


def initial_placement(design,definitions=None):
    """Place a NEW project using fixed faces, source windows and shared nets."""
    from .engineering_db import definitions_for_design
    from .engineering_conditions import required_wall
    from .routing import terminal_points
    if any(f.route_net or f.frozen_net or f.parent_id for f in design.features):
        raise ValueError('Initial placement is only available before routing and authored parent placement. Existing geometry is retained.')
    result=design.model_copy(deep=True)
    definitions=definitions if definitions is not None else definitions_for_design(result)
    dims=dimensions(result.block);cavities=[f for f in result.features if f.kind=='cavity' and not f.suppressed]
    def unresolved(feature_id,message):
        from .schema import EngineeringReview
        result.review_items.append(EngineeringReview(id='LAYOUT_'+feature_id[:32],kind='component',
            subject=feature_id,severity='blocking',description=message))
    def radius_for(feature):
        return machining_radius(definitions[feature.definition]) if feature.definition else max(feature.diameter or 0,feature.clearance_diameter)/2
    weights={f.id:{} for f in cavities}
    for net in result.nets:
        owners=sorted({m.split(':')[0] for m in net.members}&set(weights))
        for a,b in combinations(owners,2):
            weight=1/max(1,len(owners)-1)
            weights[a][b]=weights[a].get(b,0)+weight;weights[b][a]=weights[b].get(a,0)+weight
    # Faces are engineering choices, not inferred from the drawing. Respect hard
    # constraints and do not rotate or change source hydraulic-window identities.
    for f in result.features:
        if f.kind in ('port','cavity') and f.id in result.constraints.required_feature_faces:f.face=result.constraints.required_feature_faces[f.id]
    for face in FACE_AXES:
        group=[f for f in cavities if f.face==face]
        if not group:continue
        wall=max(required_wall(result,f,definitions=definitions) for f in group)
        radius=max(machining_radius(definitions[f.definition]) for f in group)
        margin=radius+wall;pitch=2*radius+max(2*wall,result.rules.minimum_access_gap)
        u,v,_,_=FACE_AXES[face]
        layouts=[]
        for cols in range(1,len(group)+1):
            rows=math.ceil(len(group)/cols)
            width=(cols-1)*pitch+2*margin;height=(rows-1)*pitch+2*margin
            if width<=dims[u] and height<=dims[v]:layouts.append((width*height,max(width,height),cols,rows))
        if not layouts:
            unresolved(group[0].id,f'{face}: source footprints and required wall do not fit. Enlarge the block or choose another mounting face; initial locations retained.')
            continue
        _,_,cols,rows=min(layouts)
        slots=[((dims[u]-(cols-1)*pitch)/2+i*pitch,(dims[v]-(rows-1)*pitch)/2+j*pitch)
               for j in range(rows) for i in range(cols)]
        remaining=sorted(group,key=lambda f:(-sum(weights[f.id].values()),-len(f.circuits),f.id))
        placed=[]
        while remaining:
            feature=min(remaining,key=lambda f:(-sum(weights[f.id].get(p.id,0) for p in placed),
                                                -sum(weights[f.id].values()),f.id))
            def cost(point):
                wired=sum(weights[feature.id].get(p.id,0)*math.dist(point,(p.u,p.v)) for p in placed)
                return (wired,math.dist(point,(dims[u]/2,dims[v]/2)),point)
            point=min(slots,key=cost);feature.u,feature.v=point
            slots.remove(point);placed.append(feature);remaining.remove(feature)
        # Source-defined zone offsets/depths are included in this wire-length
        # objective. A small deterministic swap pass improves the starting order.
        def objective():
            points=terminal_points(result,definitions);total=0
            for net in result.nets:
                terminals=[points[m] for m in net.members if m in points]
                if not terminals:continue
                center=tuple(sum(p[i] for p in terminals)/len(terminals) for i in range(3))
                total+=sum(sum(abs(p[i]-center[i]) for i in range(3)) for p in terminals)
            return total
        best=objective()
        for _ in range(2):
            improved=False
            for a,b in combinations(sorted(group,key=lambda f:f.id),2):
                a.u,b.u=b.u,a.u;a.v,b.v=b.v,a.v
                score=objective()
                if score+1e-6<best:best=score;improved=True
                else:a.u,b.u=b.u,a.u;a.v,b.v=b.v,a.v
            if not improved:break
    points=terminal_points(result,definitions)
    placed_ports=set()
    movable_ports={f.id for f in result.features if f.kind=='port' and any(
        f.id in n.members and any(m.split(':')[0] in weights for m in n.members) for n in result.nets)}
    for port in [f for f in result.features if f.kind=='port' and not f.suppressed]:
        net=next((n for n in result.nets if port.id in n.members),None)
        terminals=[points[m] for m in net.members if m in points and m.split(':')[0] in weights] if net else []
        if not terminals:continue
        u,v,_,_=FACE_AXES[port.face]
        center=tuple(sum(p[i] for p in terminals)/len(terminals) for i in range(3))
        radius=radius_for(port)
        wall=required_wall(result,port,definitions=definitions);margin=radius+wall
        preferred=clamp_placement(port,result,center[u],center[v],snap=0,definitions=definitions)
        occupied=[f for f in result.features if f.id!=port.id and f.face==port.face and not f.suppressed
                  and (f.kind!='port' or f.id in placed_ports or f.id not in movable_ports)]
        pitch=max(2*margin,result.rules.minimum_access_gap+2*radius)
        probes=[preferred]+[(margin+i*pitch,margin+j*pitch)
            for i in range(max(0,int((dims[u]-2*margin)/pitch)+1))
            for j in range(max(0,int((dims[v]-2*margin)/pitch)+1))]
        def legal(point):
            if not all(margin<=value<=dims[axis]-margin for value,axis in zip(point,(u,v))):return False
            for other in occupied:
                r=radius_for(other)
                gap=max(result.rules.minimum_access_gap,required_wall(result,port,other,definitions=definitions))
                if math.dist(point,(other.u,other.v))<radius+r+gap:return False
            return True
        available=[p for p in probes if legal(p)]
        if not available:
            unresolved(port.id,'No separated source port footprint fits the selected face. Edit placement or block dimensions; the draft remains unvalidated.')
            placed_ports.add(port.id)
            continue
        port.u,port.v=min(available,key=lambda p:(math.dist(p,preferred),p))
        placed_ports.add(port.id)
    return result
