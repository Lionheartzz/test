"""Deterministic initial placement for explicitly created, editable projects.

This is an analytic starting arrangement, never a routing/clearance certificate.
It is not called by project load, Save, Validate, Build or Drawing.
"""
import math
from itertools import combinations
from .kinematics import FACE_AXES,dimensions,definition_planar_radius,clamp_placement,pose


def machining_radius(definition):
    return max([definition_planar_radius(definition)]+[
        math.hypot(getattr(p,'offset_u',0),getattr(p,'offset_v',0))+
        max(p.diameter,getattr(p,'end_diameter',0))/2
        for p in definition.cutting_primitives or definition.stages])


def placement_conflicts(design, feature, definitions, threads, modifiers,*,cache=None):
    """Conservative 3D machining separation for a proposed NEW interface.

    Reuse the router's source profiles (offsets, cones, threads and modifiers),
    not a face footprint or an infinite nominal cylinder. This analytic screen
    authorizes no hydraulic contact. Exact acceptance remains independent.
    """
    from .routing import _manufacturing_cuts,_cuts_too_close
    from .engineering_conditions import required_wall
    def envelope(f):
        if not f.definition and f.kind!='port' and not f.plugged:return []
        definition=definitions.get(f.definition)
        height=max([definition.clearance_height,*[b.height for b in definition.boundaries]]) if definition else f.clearance_height
        radius=machining_radius(definition) if definition else f.clearance_diameter/2
        if height>0 and radius>0:
            return [dict(feature=f,start=-height,end=0,radius_start=radius,radius_end=radius,inner_radius=0)]
        return []  # Unknown installation height is not invented.
    # Optional operation-owned profile cache. No acceptance result is cached:
    # new positions, stock size and current wall/access rules are still tested.
    # Normal Model callers retain the default per-call lifetime.
    cache=cache if cache is not None else {}
    namespace=(tuple((k,id(v)) for k,v in sorted(definitions.items())),
        tuple((k,id(v)) for k,v in sorted(threads.items())),tuple((k,id(v)) for k,v in sorted(modifiers.items())))
    if cache.get('namespace')!=namespace:cache.clear();cache['namespace']=namespace
    profiles=cache.setdefault('profiles',{})
    def profile(f):
        key=(dimensions(design.block),f.model_dump_json(exclude={'connects_to'}))
        if key not in profiles:
            frozen=f.model_copy(deep=True)
            profiles[key]=(list(_manufacturing_cuts(frozen,definitions,threads,modifiers)),envelope(frozen))
            if len(profiles)>2048:profiles.pop(next(iter(profiles)))
        return profiles[key]
    cuts,installed=profile(feature)
    conflicts=[]
    for other in design.features:
        if other.id==feature.id or other.suppressed or other.route_net:continue
        clearance=required_wall(design,feature,other,definitions=definitions)
        other_cuts,other_installed=profile(other)
        if (any(_cuts_too_close(cuts,cut,design.block,clearance) for cut in other_cuts) or
            any(_cuts_too_close(installed,cut,design.block,design.rules.minimum_access_gap) for cut in other_cuts+other_installed) or
            any(_cuts_too_close(cuts,cut,design.block,design.rules.minimum_access_gap) for cut in other_installed)):
            conflicts.append(other.id)
    return conflicts


def source_safe_port_positions(design,port,definitions,threads,modifiers):
    """Reviewable positions on the SAME face/envelope; no project mutation."""
    from .engineering_conditions import required_wall
    u,v,_,_=FACE_AXES[port.face];dims=dimensions(design.block)
    def radius_for(f):
        from .routing import feature_bore_diameter
        return machining_radius(definitions[f.definition]) if f.definition else max(feature_bore_diameter(f,threads),f.clearance_diameter)/2
    radius=radius_for(port);margin=radius+required_wall(design,port,definitions=definitions)
    pitch=max(2*margin,2*radius+design.rules.minimum_access_gap)
    preferred=(port.u,port.v);probes={preferred}
    others=[f for f in design.features if f.id!=port.id and not f.suppressed and not f.route_net]
    # Source positions produce local escape planes as well as a finite face
    # grid. Offset machining and installed footprints contribute to the radius.
    for other in others:
        origin,_=pose(other,design.block)
        gap=radius+radius_for(other)+max(design.rules.minimum_access_gap,required_wall(design,port,other,definitions=definitions))
        for sign in (-1,1):
            probes.add((origin[u]+sign*gap,port.v));probes.add((port.u,origin[v]+sign*gap))
    probes.update((margin+i*pitch,margin+j*pitch)
        for i in range(max(0,int((dims[u]-2*margin)/pitch)+1))
        for j in range(max(0,int((dims[v]-2*margin)/pitch)+1)))
    for point in sorted(probes,key=lambda p:(math.dist(p,preferred),p)):
        if not all(margin<=value<=dims[axis]-margin for value,axis in zip(point,(u,v))):continue
        if any(other.face==port.face and math.dist(point,(other.u,other.v))<radius+radius_for(other)+
               max(design.rules.minimum_access_gap,required_wall(design,port,other,definitions=definitions)) for other in others):continue
        probe=port.model_copy(update=dict(u=point[0],v=point[1]))
        if not placement_conflicts(design,probe,definitions,threads,modifiers):yield point


def circle_layout(items,max_u,max_v,gap=0):
    """Variable-size source footprints; no largest-valve grid tax on every cell."""
    items=sorted(items,key=lambda row:(-row[1],row[0]));choices=[]
    for cols in range(1,len(items)+1):
        rows=[items[i:i+cols] for i in range(0,len(items),cols)]
        widths=[sum(2*r for _,r in row)+gap*(len(row)-1) for row in rows]
        heights=[2*max(r for _,r in row) for row in rows]
        width=max(widths);height=sum(heights)+gap*(len(rows)-1)
        if width>max_u+1e-6 or height>max_v+1e-6:continue
        positions={};y=0
        for row,w,h in zip(rows,widths,heights):
            x=(width-w)/2
            for key,r in row:positions[key]=(x+r,y+h/2);x+=2*r+gap
            y+=h+gap
        choices.append((width*height,max(width,height),cols,len(rows),width,height,positions))
    if not choices:raise ValueError('Source machining/installed footprints do not fit this mounting face.')
    return min(choices,key=lambda row:row[:3])


def packing_dimensions(group,face,wall,gap,maximum,*,rectangular=False):
    u,v,_,_=FACE_AXES[face]
    items=[(str(c.get('id',i)),machining_radius(c['definition'])+wall/2) for i,c in enumerate(group)]
    try:_,_,cols,rows,width,height,_=circle_layout(items,maximum[u]-wall,maximum[v]-wall,gap)
    except ValueError:
        if gap:return packing_dimensions(group,face,wall,0,maximum,rectangular=rectangular)
        raise
    return cols,rows,width+wall,height+wall,2*max(r for _,r in items)+gap


def propose_dimensions(design,definitions,preferred=None,*,preferred_is_soft=False):
    """Initial NEW-project envelope from source geometry and actual conditions.

    Routing allowance is a draft layout space based on the selected bore, not a
    wall rule or a pressure rating. Explicit dimensions/limits remain binding.
    """
    from .engineering_conditions import required_wall
    from .layout_planning import routing_gap
    bore=max((n.diameter for n in design.nets),default=0)
    allowance=max(bore,design.rules.minimum_access_gap)
    needed=[2*allowance]*3
    lower=design.constraints.envelope_min or (0,0,0);upper=design.constraints.envelope_max or (2000,2000,2000)
    packing_limit=[max(lower[i],min(upper[i],preferred[i])) if not preferred_is_soft and preferred and preferred[i] is not None else upper[i] for i in range(3)]
    for face in FACE_AXES:
        group=[f for f in design.features if f.kind in ('cavity','port') and f.face==face and not f.suppressed]
        if not group:continue
        wall=max(required_wall(design,f,definitions=definitions) for f in group)
        u,v,axis,_=FACE_AXES[face]
        footprints=[(f.id,(machining_radius(definitions[f.definition]) if f.definition else max(f.diameter or 0,f.clearance_diameter)/2)+wall/2) for f in group]
        limits=(packing_limit[u]-wall-2*allowance,packing_limit[v]-wall-2*allowance)
        try:layout=circle_layout(footprints,*limits,routing_gap(design,definitions,face))
        except ValueError:
            # A planning lane is a preference, not a new hard geometry rule.
            # Respect explicit/inherited dimensions and keep exact routing open.
            layout=circle_layout(footprints,*limits,design.rules.minimum_access_gap)
        _,_,_,_,width,height,_=layout
        needed[u]=max(needed[u],width+wall+2*allowance);needed[v]=max(needed[v],height+wall+2*allowance)
        depth=max(max(p.end for p in definitions[f.definition].cutting_primitives or definitions[f.definition].stages) if f.definition else f.depth for f in group)
        needed[axis]=max(needed[axis],depth+wall+2*allowance)
    for f in design.features:
        if f.suppressed or f.kind=='cavity':continue
        u,v,axis,_=FACE_AXES[f.face];wall=required_wall(design,f,definitions=definitions)
        definition=definitions.get(f.definition)
        radius=machining_radius(definition) if definition else max(f.diameter or 0,f.clearance_diameter)/2
        needed[u]=max(needed[u],2*(radius+wall)+2*allowance);needed[v]=max(needed[v],2*(radius+wall)+2*allowance)
        depth=max(p.end for p in definition.cutting_primitives or definition.stages) if definition else f.depth
        if not (f.kind=='mounting' and f.through):needed[axis]=max(needed[axis],depth+wall+2*allowance)
        if f.kind not in ('port','cavity'):
            needed[u]=max(needed[u],f.u+radius+wall);needed[v]=max(needed[v],f.v+radius+wall)
    sizes=[]
    for i in range(3):
        target=preferred[i] if preferred and preferred[i] is not None else math.ceil(needed[i]/5)*5
        if preferred_is_soft:target=max(target,math.ceil(needed[i]/5)*5)
        target=max(lower[i],min(upper[i],target))
        if target+1e-6<needed[i]:raise ValueError('Source geometry, stated pressure and routing allowance cannot fit the requested initial block dimensions.')
        sizes.append(target)
    return tuple(sizes)


def initial_placement(design,definitions=None,*,plan_routes=True,screen_source_geometry=False):
    """Place a NEW project using fixed faces, source windows and shared nets."""
    from .engineering_db import definitions_for_design
    from .engineering_conditions import required_wall
    from .routing import terminal_points
    from .layout_planning import routing_gap
    if any(f.route_net or f.frozen_net or f.parent_id for f in design.features):
        raise ValueError('Initial placement is only available before routing and authored parent placement. Existing geometry is retained.')
    result=design.model_copy(deep=True)
    definitions=definitions if definitions is not None else definitions_for_design(result)
    # Only the AI-owned compilation call opts into new cross-face placement.
    # Existing manual creation and every Model operation retain their behaviour.
    if screen_source_geometry:
        from .engineering_db import thread_definitions_for_design,modifier_definitions_for_design
        threads=thread_definitions_for_design(result)
        modifiers=modifier_definitions_for_design(result) if any(f.machining_modifiers for f in result.features) else {}
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
        u,v,_,_=FACE_AXES[face]
        footprints=[(f.id,machining_radius(definitions[f.definition])+wall/2) for f in group]
        try:
            try:layout=circle_layout(footprints,dims[u]-wall,dims[v]-wall,routing_gap(result,definitions,face))
            except ValueError:layout=circle_layout(footprints,dims[u]-wall,dims[v]-wall,result.rules.minimum_access_gap)
            _,_,_,_,width,height,positions=layout
        except ValueError:
            unresolved(group[0].id,f'{face}: source footprints and required wall do not fit. Enlarge the block or choose another mounting face; initial locations retained.')
            continue
        for feature in group:
            feature.u=positions[feature.id][0]+(dims[u]-width)/2
            feature.v=positions[feature.id][1]+(dims[v]-height)/2
        def fits():
            for f in group:
                r=machining_radius(definitions[f.definition])+wall
                if not(r<=f.u<=dims[u]-r and r<=f.v<=dims[v]-r):return False
            return all(math.dist((a.u,a.v),(b.u,b.v))+1e-6>=
                machining_radius(definitions[a.definition])+machining_radius(definitions[b.definition])+max(wall,result.rules.minimum_access_gap)
                for a,b in combinations(group,2))
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
                score=objective() if fits() else math.inf
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
            if screen_source_geometry:
                probe=port.model_copy(update=dict(u=point[0],v=point[1]))
                # Future movable ports are placed in turn. All cavities, fixed
                # ports and already placed ports are actual 3D obstacles.
                context=result.model_copy()
                context.features=[f for f in result.features if f.kind!='port' or
                                  f.id==port.id or f.id in placed_ports or f.id not in movable_ports]
                if placement_conflicts(context,probe,definitions,threads,modifiers):return False
            return True
        if screen_source_geometry:
            context=result.model_copy()
            context.features=[f for f in result.features if f.kind!='port' or
                              f.id==port.id or f.id in placed_ports or f.id not in movable_ports]
            preferred_port=port.model_copy(update=dict(u=preferred[0],v=preferred[1]))
            available=next(([p] for p in source_safe_port_positions(context,preferred_port,definitions,threads,modifiers) if legal(p)),[])
        else:
            available=[p for p in probes if legal(p)]
        if not available:
            unresolved(port.id,'No source-separated port placement was found on the selected face. Review the face/position constraints or block dimensions; the draft remains unvalidated.')
            placed_ports.add(port.id)
            continue
        port.u,port.v=min(available,key=lambda p:(math.dist(p,preferred),p))
        placed_ports.add(port.id)
    # AI generation owns its separate bounded planning call before handoff.
    # Default new/manual creation retains the existing fixed-size behaviour.
    if not plan_routes:return result
    # Four small analytic layouts at most, using the same source/window/cut
    # semantics as Model. No exact geometry or multi-layout CAD generation.
    from .layout_planning import plan
    from .schema import EngineeringReview
    try:planned=plan(result,definitions,initial=True)
    except ValueError as exc:
        result.review_items.append(EngineeringReview(id='LAYOUT_ROUTING_CORRIDORS',kind='connection',subject='project',
            description=('Analytic corridor planning could not complete: '+str(exc)+'. Editable layout retained; source/geometry review and Exact Preview remain required.')[:2000]))
        return result
    if planned['proposals']:
        result=type(result).model_validate(planned['proposals'][0]['design'])
    if planned['baseline']['blocked_nets'] or planned['baseline']['conflicts']:
        result.review_items.append(EngineeringReview(id='LAYOUT_ROUTING_CORRIDORS',kind='connection',subject='project',
            description='Initial placement considered source-window access and competing hydraulic circuits using a bounded analytic corridor sample. '
                        'This is not exact routing feasibility. Model can propose additional layout alternatives; Exact Preview and Validate remain required.'))
    return result
