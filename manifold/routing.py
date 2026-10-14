from .engineering_conditions import effective_net,required_wall,planning_wall,wall_unresolved
from .timing import timed,phase
"""Route within supplied fixed geometry. Only the BRep validator grants PASS.

Layout/size exploration belongs to AI-owned generation or explicit reviewable
layout proposals. Neither AI origin nor a route failure grants resize authority.
"""
import hashlib
import itertools
import math
from .schema import Feature, ConstructionAccess
from .kinematics import pose, dimensions, FACE_AXES, resolve_parents


def port_interface_diameter(feature, definitions):
    if feature.port_definition_id:
        return definitions[feature.port_definition_id].zones[0].diameter
    return feature.diameter


def terminal_points(design, definitions=None):
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions = definitions_for_design(design)
    points = {}
    for f in design.features:
        if f.suppressed or f.kind in ('drilling','mounting'):
            continue
        p, axis = pose(f, design.block)
        if f.kind == 'cavity':
            for z in definitions[f.definition].zones:
                point = [a + b * (z.start + z.end) / 2 for a, b in zip(p, axis)]
                angle = math.radians(f.rotation); u,v,_,_ = FACE_AXES[f.face]
                point[u] += z.offset_u*math.cos(angle)-z.offset_v*math.sin(angle)
                point[v] += z.offset_u*math.sin(angle)+z.offset_v*math.cos(angle)
                points[f'{f.id}:{z.id}'] = tuple(point)
        else:
            depth=(definitions[f.definition].zones[0].start+definitions[f.definition].zones[0].end)/2 if f.definition else f.depth
            points[f.id] = tuple(a + b * depth for a, b in zip(p, axis))
    return points


def spanning_pairs(points):
    if not points:
        return []
    visited, rest, pairs = [points[0]], points[1:], []
    while rest:
        _, a, b = min((sum(abs(x-y) for x, y in zip(a,b)), a, b) for a in visited for b in rest)
        pairs.append((a,b)); visited.append(b); rest.remove(b)
    return pairs


def _axial_connector_path(start, end, order, bends, axial_axis):
    """Move only the last transverse approach; the axial trunk is a fixed endpoint."""
    path=[start];point=list(start)
    for axis in order:
        if abs(point[axis]-end[axis])>1e-7:
            point[axis]=end[axis];path.append(tuple(point))
    # The final coaxial portion is already supplied by the physical axial bore.
    last=len(path)-1
    while last>0 and all(abs(path[last][i]-path[last-1][i])<1e-7 for i in range(3) if i!=axial_axis):last-=1
    if last==0:return path
    p,q=path[last-1],path[last]
    transverse=next(i for i in range(3) if abs(p[i]-q[i])>1e-7)
    if any(axis==transverse for axis,_ in bends):return None
    pp,qq=list(p),list(q)
    for axis,coordinate in bends:pp[axis]=qq[axis]=coordinate
    prefix=path[:last]
    # Shorten/extend an adjacent collinear leg instead of introducing a needless
    # out-and-back excursion along that same drilling.
    if len(prefix)>1 and sum(abs(prefix[-1][i]-prefix[-2][i])>1e-7 for i in range(3))==1:
        previous=next(i for i in range(3) if abs(prefix[-1][i]-prefix[-2][i])>1e-7)
        if all(abs(pp[i]-p[i])<1e-7 for i in range(3) if i!=previous):prefix.pop()
    result=prefix+[tuple(pp),tuple(qq)]
    # Return only in the non-axial directions. An offset along the bore axis is
    # another junction on its existing cylinder, not a deeper/shifted bore.
    for axis,_ in reversed(bends):
        if axis!=axial_axis:
            qq[axis]=q[axis];result.append(tuple(qq))
    result.extend(path[last+1:])
    if result[-1]!=end:result.append(end)
    return result


def port_turn_depth(design,net,feature,definitions,mode,threads=None,modifiers=None):
    """Alternative junctions derived from the actual port's machining/window.

    These only propose cuts. The ordinary protected-source, opening, wall and
    exact connectivity gates still decide whether the complete route is legal.
    """
    radius=net.diameter/2
    if feature.direction is not None:return None
    if mode=='window':
        if not feature.definition:
            # An authored straight bore has no protected seat. Keep the entire
            # transverse bore inside its full cylinder, away from its drill tip.
            diameter=threads[feature.thread_definition_id]['tap_diameter_mm'] if feature.thread_only and threads else feature.diameter
            # A thread-only draft has no declared sealing/window recipe. Never
            # promote its unqualified threaded segment to a side-entry window.
            start=(feature.thread_depth if feature.thread_depth is not None else feature.depth) if feature.thread_only else 0
            if diameter is None or diameter<net.diameter or feature.depth-start<2*radius+.2:return None
            return feature.depth-radius-.1
        zone=definitions[feature.definition].zones[0]
        if zone.end-zone.start<2*radius+.2:return None
        depth=zone.end-radius-.1
        from .cavity_access import _axis_core
        cuts=list(_manufacturing_cuts(feature,definitions,threads or {},modifiers or {}))
        # A full inscribed cylinder, including offsets/annuli/tapers, must exist
        # across the turn. Nominal thread/port diameter is not sufficient.
        low,high=depth-radius,depth+radius
        boundaries=sorted({low,high,*(x for c in cuts for x in (c['start'],c['end']) if low<x<high)})
        for a,b in zip(boundaries,boundaries[1:]):
            active=[c for c in cuts if c['start']<=a and c['end']>=b]
            if not any(min(_axis_core(c,a,feature),_axis_core(c,b,feature))>=radius for c in active):return None
        if zone.diameter/2-math.hypot(zone.offset_u,zone.offset_v)<radius:return None
        return depth
    if mode=='clear':
        cuts=list(_manufacturing_cuts(feature,definitions,threads or {},modifiers or {}))
        return max(c['end'] for c in cuts)+radius+planning_wall(design,net,definitions)
    raise ValueError('Unknown port terminal approach')


def _fixed_strategy_source(design):
    """Stable template construction; mutable compatibility is checked later."""
    mutable={n.id for n in design.nets if n.routing=='automatic' and n.route_state in ('unresolved','proposal')}
    mutable-={f.frozen_net for f in design.features if f.frozen_net}
    return design.model_copy(update=dict(features=[f for f in design.features if f.route_net not in mutable or f.frozen_net]))


def propose(design, net, order, entry=None, detour='direct', definitions=None, safe_planes=None, *, terminal_overrides=None, connector_bends=None, port_approaches=None, connection_topology=None, entry_safe=False, thread_definitions=None, modifier_definitions=None, obstruction_cache=None,junction_override=None,terminal_orders=None,operation_records=None):
    net=effective_net(design,net)
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    points = terminal_points(design,definitions)
    points.update(terminal_overrides or {})
    orders_at={points[m]:o for m,o in (terminal_orders or {}).items() if m in points}
    pairs = spanning_pairs(sorted(set(points[m] for m in net.members if m in points)))
    if junction_override is not None:
        if len(junction_override)!=3 or any(not math.isfinite(x) or not 0<=x<=dimensions(design.block)[i] for i,x in enumerate(junction_override)):return None
        pairs=[(points[m],tuple(junction_override)) for m in sorted(net.members) if m in points]
    elif connection_topology is not None:
        members=sorted(net.members)
        if len(members) not in (3,4) or any(m not in points for m in members):return None
        if connection_topology in range(3):
            root=points[members[connection_topology]]
            pairs=[(root,points[m]) for m in members if m!=members[connection_topology]]
        elif connection_topology==3:
            # A real drilling junction between the terminals, not a hydraulic
            # node declaration. All branches become external-face machining.
            junction=tuple((min(points[m][i] for m in members)+max(points[m][i] for m in members))/2 for i in range(3))
            pairs=[(points[m],junction) for m in members]
        elif connection_topology==4 and len(members)==4:
            root=points[members[3]]
            pairs=[(root,points[m]) for m in members[:3]]
        else:return None
    ports_at = {points[f.id]:f for f in design.features if f.kind=='port' and not f.suppressed
                and f.id in net.members and f.id in points and f.circuit==net.id}
    def port_stem(feature, point):
        origin,direction=pose(feature,design.block)
        if port_approaches and feature.id in port_approaches:
            depth=port_approaches[feature.id]
            return tuple(origin[i]+direction[i]*depth for i in range(3))
        definition=definitions[feature.definition] if feature.definition else None
        window_end=definition.zones[0].end if definition else feature.depth
        cut_radius=(max(max(stage.diameter,getattr(stage,'end_diameter',0)) for stage in
                        (definition.cutting_primitives or definition.stages))/2 if definition else feature.diameter/2)
        current=sum((point[i]-origin[i])*direction[i] for i in range(3))
        # Turn away from the port only after clearing its protected machining
        # body. The coaxial terminal drilling itself remains open.
        depth=max(window_end,current)+cut_radius+net.diameter/2+planning_wall(design,net,definitions)
        return tuple(point[i]+direction[i]*(depth-current) for i in range(3))
    lines = {};line_owners={}
    for a,b in pairs:
        if b in ports_at and a not in ports_at:a,b=b,a
        branch_order=orders_at.get(a,orders_at.get(b,order))
        start=port_stem(ports_at[a],a) if a in ports_at else a
        end=port_stem(ports_at[b],b) if b in ports_at else b
        # A junction already inside the real port's fluid cylinder needs no
        # generated coaxial extension. The authored port remains present, and
        # exact connectivity must prove the transverse opening into it.
        def needs_extension(point,junction):
            if point not in ports_at:return False
            feature=ports_at[point];origin,direction=pose(feature,design.block)
            window_end=definitions[feature.definition].zones[0].end if feature.definition else feature.depth
            return sum((junction[i]-origin[i])*direction[i] for i in range(3))>window_end
        prefix=[a] if needs_extension(a,start) else []
        suffix=[b] if needs_extension(b,end) else []
        waypoints=prefix+[start,end]+suffix
        if connector_bends and (end in connector_bends or start in connector_bends):
            reverse=end not in connector_bends
            bends,axial_axis=connector_bends[start if reverse else end]
            path=_axial_connector_path(end if reverse else start,start if reverse else end,
                                      order[::-1] if reverse else order,bends,axial_axis)
            if path is None:return None
            if reverse:path=path[::-1]
            waypoints=prefix+path+suffix
        if detour != 'direct':
            if safe_planes is None:
                safe_planes = obstacle_safe_planes(design, net, definitions)
            if isinstance(detour, str):
                if detour.startswith('planes_'):
                    values=detour.split('_')[1:]
                    if len(values) not in (2,4):raise ValueError('Invalid coordinated detour plane')
                    bends=tuple((int(values[i]),float(values[i+1])) for i in range(0,len(values),2))
                    if len({axis for axis,_ in bends})!=len(bends) or any(axis not in range(3) or not math.isfinite(coordinate) or not 0<=coordinate<=dimensions(design.block)[axis] for axis,coordinate in bends):
                        raise ValueError('Coordinated detour plane is outside the block')
                else:
                    _,name,side = detour.split('_')
                    axis = 'xyz'.index(name)
                    planes = safe_planes[axis][side[0]]
                    bends = ((axis,planes[min(1 if side.endswith('2') else 0, len(planes)-1)]),)
            else:
                bends = detour
            aa,bb = list(start),list(end)
            outward=[]; inward=[]
            for axis,coordinate in bends:
                aa[axis] = bb[axis] = coordinate
                outward.append(tuple(aa))
                inward.append(tuple(bb))
            insert=waypoints.index(start)+1
            waypoints[insert:insert]=outward+inward[::-1]
        for start,end in zip(waypoints,waypoints[1:]):
            p = list(start)
            for axis in branch_order:
                if abs(p[axis]-end[axis]) < 1e-7:
                    continue
                # Preserve the source/junction coordinate exactly. Rounding a
                # transverse hole off an axial access by sub-micron amounts can
                # make OCCT return an empty common or an invalid production
                # Boolean for otherwise intersecting cylinders.
                fixed = tuple(p[i] for i in range(3) if i != axis)
                key = (axis, fixed)
                lo,hi = sorted((p[axis], end[axis]))
                lines.setdefault(key,[]).append((lo,hi)); p[axis] = end[axis]
                if operation_records is not None:
                    line_owners.setdefault(key,set()).update(m for m in net.members if points.get(m) in (a,b))
    sizes = dimensions(design.block)
    features = []
    if entry_safe:
        from .engineering_db import thread_definitions_for_design,modifier_definitions_for_design
        from .closure_runtime import bind_route
        thread_definitions=thread_definitions if thread_definitions is not None else thread_definitions_for_design(design)
        modifier_definitions=modifier_definitions if modifier_definitions is not None else (
            modifier_definitions_for_design(design) if any(f.machining_modifiers for f in design.features) else {})
        obstruction_cache=obstruction_cache if obstruction_cache is not None else {}
        entry_source=_fixed_strategy_source(design)
        own_entries=entry_source.model_copy(update=dict(features=[]))
    digest = hashlib.sha256(net.id.encode()).hexdigest()[:8]
    segments=[]
    for key,intervals in lines.items():
        merged=[]
        for lo,hi in sorted(intervals):
            if merged and lo<=merged[-1][1]+1e-7:
                merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
            else:merged.append((lo,hi))
        segments.extend((key,interval) for interval in merged)
    for (axis, fixed), (lo,hi) in sorted(segments):
        neg,pos = [('left','right'),('front','back'),('bottom','top')][axis]
        p = list(fixed); p.insert(axis,0)
        options = []
        for face in (neg,pos):
            if face in design.constraints.forbidden_drilling_faces and any(x not in design.constraints.forbidden_drilling_faces for x in (neg,pos)):
                continue
            u,v,_,sign = FACE_AXES[face]
            coaxial = any(f.kind == 'port' and not f.suppressed and f.circuit == net.id and f.face == face
                          and abs(f.u-p[u]) < 1e-6 and abs(f.v-p[v]) < 1e-6
                          and port_interface_diameter(f,definitions) >= net.diameter for f in design.features)
            depth = hi + net.diameter/2 if sign > 0 else sizes[axis]-lo+net.diameter/2
            preference_value = entry or net.entry_preference
            preference = 0 if preference_value == 'nearest' or (preference_value == 'negative') == (sign > 0) else 10000
            options.append((not coaxial, preference + depth, face, depth, coaxial))
        def make(choice):
            _,_,face,depth,coaxial=choice
            u,v,_,_=FACE_AXES[face]
            return Feature(id=f'R-{digest}-{len(features)+1}',kind='drilling',face=face,u=p[u],v=p[v],
                circuit=net.id,diameter=net.diameter,depth=max(depth,9),plugged=not coaxial,
                route_net=net.id,clearance_diameter=max(16,net.diameter+8),clearance_height=15)
        if entry_safe:
            # Each line has its own two real entry faces. A single global
            # positive/negative choice cannot express a clear mixed-face tree.
            # Screen the complete source-bound closure cut, not its centreline.
            ranked=[]
            for choice in options:
                feature=bind_route(design,[make(choice)])[0]
                # A stable variant must regenerate the same geometry after
                # another mutable net has been selected. Compatibility with
                # those nets belongs to the complete combination screen.
                failures=route_obstructions(entry_source,net,[feature],thread_definitions,definitions,modifier_definitions,obstruction_cache)
                # Two individually clear entries may clash with each other's
                # plug machining. Compare real opposite-face cuts against the
                # already generated same-net cuts too, before discarding the
                # whole branching strategy. No mutable sibling net is pinned.
                if features:
                    failures|=route_obstructions(own_entries,net,[*features,feature],thread_definitions,definitions,modifier_definitions,obstruction_cache)
                ranked.append((_conflict_objective(failures),choice,feature))
            features.append(min(ranked,key=lambda row:row[:2])[2])
        else:
            features.append(make(min(options)))
        if operation_records is not None:
            operation_records.append(dict(feature=features[-1].id,axis=axis,fixed=list(fixed),required_interval=[lo,hi],
                source_members=sorted(line_owners.get((axis,fixed),())),source_bound=False))
    # A hydraulic window narrower than the drill diameter cannot accept the
    # full cylinder. Stop that terminal branch before the cavity and let its
    # conical drill tip make the declared window contact.
    for source in design.features:
        if source.suppressed or not source.definition or source.kind != 'cavity':
            continue
        definition = definitions[source.definition]
        _, source_direction = pose(source, design.block)
        for zone in definition.zones:
            if f'{source.id}:{zone.id}' not in net.members or source.circuits.get(zone.id) != net.id:
                continue
            if terminal_overrides and f'{source.id}:{zone.id}' in terminal_overrides:
                continue
            if zone.end-zone.start >= net.diameter + .2:
                continue
            center = points[f'{source.id}:{zone.id}']
            cut_radius = max((max(stage.diameter, getattr(stage, 'end_diameter', 0))/2
                              for stage in definition.cutting_primitives or definition.stages
                              if stage.start <= (zone.start+zone.end)/2 <= stage.end), default=zone.diameter/2)
            for feature in features:
                origin, direction = pose(feature, design.block)
                if abs(sum(a*b for a,b in zip(direction,source_direction))) > 1e-6:
                    continue
                axial = sum((center[i]-origin[i])*source_direction[i] for i in range(3))
                if abs(axial) > (zone.end-zone.start)/2+feature.diameter/2:
                    continue
                side = tuple(center[i]-origin[i]-axial*source_direction[i] for i in range(3))
                along = sum(side[i]*direction[i] for i in range(3))
                sideways = math.sqrt(max(0,sum(v*v for v in side)-along*along))
                if sideways >= cut_radius or along <= 0:
                    continue
                first_contact = along-math.sqrt(cut_radius*cut_radius-sideways*sideways)
                if 9 < first_contact < feature.depth-1:
                    feature.depth = round(first_contact-1, 6)
    return add_construction_access(design,net,features)


def add_construction_access(design, net, features):
    """Materialize authored accesses on the final manufacturing trunk, preserving their IDs."""
    access_ids={access.id for access in net.construction_access}
    features=[f for f in features if f.id not in access_ids]
    sizes=dimensions(design.block)
    for access in net.construction_access:
        if not features:
            continue
        trunk = max(features, key=lambda f:f.depth)
        p,d = pose(trunk, design.block)
        point = [a+b*trunk.depth*access.fraction for a,b in zip(p,d)]
        u,v,axis,sign = FACE_AXES[access.face]
        depth = point[axis] if sign > 0 else sizes[axis]-point[axis]
        features.append(Feature(id=access.id, kind='drilling', face=access.face, u=point[u],v=point[v],
                                circuit=net.id,diameter=net.diameter,depth=max(9,depth+net.diameter/4),plugged=True,route_net=net.id))
    return features


def obstacle_safe_planes(design, net, definitions, thread_definitions=None, modifier_definitions=None,*,include_routes=False,routes_only=False):
    """Finite machining bounds give repeatable, drillable detour planes."""
    if thread_definitions is None:
        from .engineering_db import thread_definitions_for_design
        thread_definitions = thread_definitions_for_design(design)
    if modifier_definitions is None:
        from .engineering_db import modifier_definitions_for_design
        modifier_definitions = modifier_definitions_for_design(design) if any(f.machining_modifiers for f in design.features) else {}
    points = terminal_points(design, definitions)
    terminals = [points[m] for m in net.members if m in points]
    center = [sum(p[i] for p in terminals)/len(terminals) for i in range(3)] if terminals else [v/2 for v in dimensions(design.block)]
    margin = max(12, net.diameter/2 + planning_wall(design,net,definitions) + .1)
    limits = dimensions(design.block)
    planes = [{side: [] for side in 'pm'} for _ in range(3)]
    automatic = {n.id for n in design.nets if n.routing == 'automatic'}
    for other in design.features:
        # Automatic proposals are screened as obstacles below, but must not
        # change the coordinate meaning of a stored variant during rebuild.
        if other.suppressed or other.route_net==net.id or other.route_net in automatic and not include_routes:
            continue
        if routes_only and not other.route_net:continue
        all_bounds = []
        for cut in _manufacturing_cuts(other, definitions, thread_definitions, modifier_definitions):
            all_bounds.append(cylinder_bounds(cut['feature'], design.block, cut['start'], cut['end'],
                                              2*max(cut['radius_start'], cut['radius_end'])))
        origin,_ = pose(other,design.block)
        transverse = FACE_AXES[other.face][:2]
        for axis in range(3):
            low = min(b[axis][0] for b in all_bounds)
            high = max(b[axis][1] for b in all_bounds)
            if axis in transverse:
                low = min(low, origin[axis]-other.clearance_diameter/2)
                high = max(high, origin[axis]+other.clearance_diameter/2)
            for side, edge in (('m', low), ('p', high)):
                coordinate = edge + (-1 if side == 'm' else 1)*(net.diameter/2 + planning_wall(design,net,definitions) + .1)
                if (margin <= coordinate <= limits[axis]-margin and
                        (coordinate < center[axis] if side == 'm' else coordinate > center[axis])):
                    planes[axis][side].append(round(coordinate, 6))
    for axis in range(3):
        for side in 'pm':
            values = sorted(set(planes[axis][side]), key=lambda v: (abs(v-center[axis]), v))
            boundary = margin if side == 'm' else limits[axis]-margin
            planes[axis][side] = values[:2] or [boundary]
    return planes


def segment_distance(a,b,c,d):
    """Finite 3D segment distance; analytic interior solution plus all four edges."""
    u=[y-x for x,y in zip(a,b)];v=[y-x for x,y in zip(c,d)];w=[x-y for x,y in zip(a,c)]
    dot=lambda x,y:sum(i*j for i,j in zip(x,y))
    aa,bb,cc,dd,ee=dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
    clamp=lambda x:max(0,min(1,x))
    if aa==0:
        t=clamp(ee/cc) if cc else 0
        return math.sqrt(sum((w[i]-t*v[i])**2 for i in range(3)))
    if cc==0:
        s=clamp(-dd/aa)
        return math.sqrt(sum((w[i]+s*u[i])**2 for i in range(3)))
    candidates=[(0,clamp(ee/cc) if cc else 0),(1,clamp((ee+bb)/cc) if cc else 0),
                (clamp(-dd/aa) if aa else 0,0),(clamp((bb-dd)/aa) if aa else 0,1)]
    det=aa*cc-bb*bb
    if det>1e-12:
        s,t=(bb*ee-cc*dd)/det,(aa*ee-bb*dd)/det
        if 0<=s<=1 and 0<=t<=1:candidates.append((s,t))
    return min(math.sqrt(sum((w[i]+s*u[i]-t*v[i])**2 for i in range(3))) for s,t in candidates)


def feature_bore_diameter(feature,thread_definitions=None):
    if feature.diameter is not None:return feature.diameter
    if feature.kind=='mounting' and feature.thread_definition_id:
        if thread_definitions is None:
            from .engineering_db import thread_definition
            return thread_definition(feature.thread_definition_id)['tap_diameter_mm']
        return thread_definitions[feature.thread_definition_id]['tap_diameter_mm']
    raise ValueError(f'{feature.id}: drilling diameter is unresolved')


def segment(feature, block, start=0, end=None,diameter=None):
    p,d = pose(feature,block)
    if end is None:
        diameter=feature_bore_diameter(feature) if diameter is None else diameter
        tip = 0 if feature.tip_angle == 180 else diameter/2/math.tan(math.radians(feature.tip_angle/2))
        end = feature.depth+tip
    return tuple(a+b*start for a,b in zip(p,d)), tuple(a+b*end for a,b in zip(p,d))


def cylinder_bounds(feature, block, start, end, diameter):
    a,b = segment(feature,block,start,end)
    _,direction=pose(feature,block)
    return [(min(a[i],b[i])-diameter/2*math.sqrt(max(0,1-direction[i]**2)),
             max(a[i],b[i])+diameter/2*math.sqrt(max(0,1-direction[i]**2))) for i in range(3)]


def _source_safe_coaxial_stops(design,net,routes,definitions):
    """Cap real single-entry drillings at the existing source safety boundary.

    A full bore to the terminal centre can cut a seat even though its drill tip
    can legally open into the assigned window. Keep the greatest safe prefix;
    ordinary exact connectivity/flow checks still have to prove every member.
    No junction or authored drilling is shortened here.
    """
    from .engineering_db import thread_definitions_for_design,modifier_definitions_for_design
    threads=thread_definitions_for_design(design)
    modifiers=modifier_definitions_for_design(design) if any(f.machining_modifiers for f in design.features) else {}
    cache={}
    for route in routes:
        if len(route)!=1:continue
        feature=route[0]
        if feature.plugged or feature.direction is not None or feature.frozen_net or feature.depth<=9:continue
        failures=route_obstructions(design,net,route,threads,definitions,modifiers,cache)
        if not failures or any(f[0] not in ('source_protected','source_wall','external_wall') for f in failures):continue
        low,high=9.0,feature.depth
        protected=[]
        for other in design.features:
            if other.suppressed or not other.definition:continue
            if (other.kind=='port' and other.id in net.members and other.circuit==net.id and
                other.face==feature.face and abs(other.u-feature.u)<1e-6 and abs(other.v-feature.v)<1e-6):continue
            for cut,own in _protected_source_cuts(other,net,definitions,threads,modifiers):
                protected.append((cut,0 if own else required_wall(design,feature,other,definitions=definitions)))
        def clear(depth):
            probe=feature.model_copy(update=dict(depth=depth))
            parts=list(_manufacturing_cuts(probe,definitions,threads,modifiers))
            if any(_cuts_too_close(parts,cut,design.block,wall) for cut,wall in protected):return False
            # The ordinary screen changes from stand-off wall to intentional
            # window contact as a tip approaches its assigned member. Search
            # the fixed protected cuts above, not that nonmonotonic proximity
            # switch. The FULL ordinary screen still gates the final candidate.
            return not any(f[0] not in ('source_protected','source_wall') for f in
                route_obstructions(design,net,[probe],threads,definitions,modifiers,cache))
        if not clear(low):continue
        # A deeper fixed-radius cylinder+tip contains its shallower prefix, so
        # protected-source/wall obstruction is monotonic. No BRep in this search.
        for _ in range(24):
            middle=(low+high)/2
            if clear(middle):low=middle
            else:high=middle
        stop=math.floor(low*1e6)/1e6
        # Bounds supply only a conservative first-contact lower bound. They
        # never authorize a connection: exact volume/opening verification does.
        # Prefer an interior stop to a cone tangent to the protection boundary;
        # retain the maximum safe prefix for cases needing more actual opening.
        origin,direction=pose(feature,design.block);axis=FACE_AXES[feature.face][2]
        first=[]
        for member in net.members:
            source=next((f for f in design.features if f.id==member.split(':')[0]),None)
            if source is None:continue
            zone=next((z for z in definitions[source.definition].zones if source.kind=='cavity' and member==f'{source.id}:{z.id}'),None) if source.definition else None
            boxes=[]
            for cut in _manufacturing_cuts(source,definitions,threads,modifiers):
                start,end=cut['start'],cut['end']
                if zone:
                    start,end=max(start,zone.start),min(end,zone.end)
                    if start>=end:continue
                boxes.append(cylinder_bounds(cut['feature'],design.block,start,end,2*max(cut['radius_start'],cut['radius_end'])))
            if boxes:first.append(min(min((box[axis][i]-origin[axis])*direction[axis] for i in (0,1)) for box in boxes))
        earliest=max(9,max(first,default=0)-feature.diameter/2/math.tan(math.radians(feature.tip_angle/2)))
        depths=[round((earliest+stop)/2,6),stop] if earliest<stop else [stop]
        for depth in dict.fromkeys(depths):
            revised=feature.model_copy(update=dict(depth=depth))
            if not route_obstructions(design,net,[revised],threads,definitions,modifiers,cache):yield [revised]


def simple_routes(design,net,definitions=None,*,include_detours=True):
    net=effective_net(design,net)
    """Single-entry proposals may exploit offset intersection; exact checks decide adequacy."""
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    points=terminal_points(design,definitions);targets=[points[m] for m in net.members if m in points]
    if len(targets)<2 or net.construction_access:
        return []
    routes=[];digest=hashlib.sha256(net.id.encode()).hexdigest()[:8]
    for port in design.features:
        if port.kind!='port' or port.suppressed or port.circuit!=net.id or port_interface_diameter(port,definitions)<net.diameter:
            continue
        origin,direction=pose(port,design.block)
        depths=[sum((p[i]-origin[i])*direction[i] for i in range(3)) for p in targets]
        if min(depths)<=0:continue
        radii={f.id:port_interface_diameter(f,definitions)/2 for f in design.features if f.kind=='port'}
        for f in design.features:
            if f.kind=='cavity':
                definition=definitions[f.definition]
                radii.update({f'{f.id}:{z.id}':z.diameter/2 for z in definition.zones})
        if any(math.dist(points[m],tuple(origin[i]+direction[i]*sum((points[m][j]-origin[j])*direction[j] for j in range(3)) for i in range(3)))>=radii[m]+net.diameter/2-1e-6 for m in net.members if m in points):
            continue
        routes.append([Feature(id=f'R-{digest}-1',kind='drilling',face=port.face,u=port.u,v=port.v,circuit=net.id,
                              diameter=net.diameter,depth=max(depths)+net.diameter/2,route_net=net.id)])
    coaxial=list(routes)
    if net.drilling_mode!='orthogonal' and len(set(targets))==2:
        a,b=targets;length=math.dist(a,b)
        if length>1e-6:
            for start,end in [(a,b),(b,a)]:
                direction=tuple((end[i]-start[i])/length for i in range(3))
                entries=[]
                for face,(u,v,axis,sign) in FACE_AXES.items():
                    if direction[axis]*sign<.25:continue
                    surface=0 if sign>0 else dimensions(design.block)[axis]
                    t=(start[axis]-surface)/direction[axis]
                    p=tuple(start[i]-t*direction[i] for i in range(3))
                    if t>8 and all(0<=p[i]<=dimensions(design.block)[i] for i in (u,v)):
                        entries.append((t,face,p))
                if entries:
                    t,face,p=min(entries);u,v,_,_=FACE_AXES[face]
                    routes.append([Feature(id=f'R-{digest}-1',kind='drilling',face=face,u=p[u],v=p[v],direction=direction,
                                           circuit=net.id,diameter=net.diameter,depth=t+length+net.diameter/2,plugged=True,route_net=net.id)])
    if net.drilling_mode == 'orthogonal' and include_detours:
        # These bounded two-plane candidates use only authored machining bounds,
        # so a persisted simple_N variant regenerates identically after other
        # automatic routes are rebuilt in a different order.
        automatic = {n.id for n in design.nets if n.routing == 'automatic'}
        source = design.model_copy(update=dict(features=[f for f in design.features if f.route_net not in automatic]))
        planes = obstacle_safe_planes(source, net, definitions)
        seen = {tuple((f.face,round(f.u,5),round(f.v,5),round(f.depth,5),f.plugged) for f in route)
                for route in routes}
        orders = [order for order in itertools.permutations(range(3))
                  if net.preferred_axis == 'auto' or order[0] == 'xyz'.index(net.preferred_axis)]
        entries = ('nearest','negative','positive') if net.entry_preference == 'nearest' else (net.entry_preference,)
        for axes in itertools.combinations(range(3),2):
            for sides in itertools.product('pm',repeat=2):
                for first in planes[axes[0]][sides[0]]:
                    for second in planes[axes[1]][sides[1]]:
                        bends = ((axes[0],first),(axes[1],second))
                        for order in orders:
                            for entry in entries:
                                route = propose(source,net,order,entry,bends,definitions,planes)
                                signature = tuple((f.face,round(f.u,5),round(f.v,5),round(f.depth,5),f.plugged) for f in route)
                                if len(route)>8 or signature in seen:
                                    continue
                                seen.add(signature)
                                routes.append(route)
    # Append so existing simple_N strategy indices remain stable.
    routes.extend(_source_safe_coaxial_stops(design,net,coaxial,definitions))
    return routes


def proximity_risk(design, net, route, definitions=None,thread_definitions=None,cache=None):
    """Conservative cylinder/centerline screen. This is a ranking estimate, never validation."""
    risk = 0.0
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    if thread_definitions is None:
        from .engineering_db import thread_definitions_for_design
        thread_definitions=thread_definitions_for_design(design)
    dims = dimensions(design.block)
    cache=cache if cache is not None else {}
    if cache.get('block') not in (None,dimensions(design.block)):cache.clear()
    cache['block']=dimensions(design.block)
    regions_cache=cache.setdefault('risk_regions',{})
    context_key=_routing_context_key(design,net)
    bore_risks=cache.setdefault('bore_risks',{})
    def regions(other,definition,allowed):
        key=(other.model_dump_json(exclude={'connects_to'}),net.id,tuple(net.members))
        if key not in regions_cache:
            result=[]
            for stage in definition.cutting_primitives or definition.stages:
                offset_u,offset_v=getattr(stage,'offset_u',0),getattr(stage,'offset_v',0)
                angle=math.radians(other.rotation)
                positioned=other.model_copy(update=dict(u=other.u+offset_u*math.cos(angle)-offset_v*math.sin(angle),
                                                       v=other.v+offset_u*math.sin(angle)+offset_v*math.cos(angle)))
                diameter=max(stage.diameter,getattr(stage,'end_diameter',0))
                windows=[z for z in allowed if abs(z.offset_u-offset_u)<1e-6 and abs(z.offset_v-offset_v)<1e-6]
                breaks=sorted({stage.start,stage.end,*[v for z in windows for v in (z.start,z.end) if stage.start<v<stage.end]})
                for start,end in zip(breaks,breaks[1:]):
                    if any(z.start<=start and end<=z.end for z in windows):continue
                    c,d=segment(positioned,design.block,start,end)
                    result.append((c,d,diameter,bool(windows),cylinder_bounds(positioned,design.block,start,end,diameter)))
            regions_cache[key]=result
        return regions_cache[key]
    for bore in route:
        risk_key=(context_key,_feature_key(bore))
        if risk_key in bore_risks:
            risk+=bore_risks[risk_key];continue
        previous_risk=risk
        a,b = segment(bore,design.block)
        radius = bore.diameter/2
        u,v,axis,sign = FACE_AXES[bore.face]
        rb=cylinder_bounds(bore,design.block,0,bore.depth,bore.diameter)
        for i in (u,v):
            risk += max(0,planning_wall(design,net,definitions)-min(a[i],dims[i]-a[i])+radius)*4
        risk += max(0,planning_wall(design,net,definitions)-(dims[axis]-b[axis] if sign>0 else b[axis]))*4
        for other in design.features:
            if other.suppressed or other.route_net == net.id:
                continue
            if other.definition:
                definition = definitions[other.definition]
                allowed = [z for z in definition.zones
                           if (other.circuits.get(z.id) if other.kind=='cavity' else other.circuit) == net.id
                           and (f'{other.id}:{z.id}' if other.kind=='cavity' else other.id) in net.members]
                # Rank complete mapped machining, not the port's hydraulic summary.
                # Cones/annuli use conservative outer cylinders in this proxy only.
                for c,d,diameter,own,cb in regions(other,definition,allowed):
                    clearance = segment_distance(a,b,c,d)-radius-diameter/2
                    if own:
                        # Same finite interval proxy, cached only within this source snapshot.
                        penetration = min(min(x[1],y[1])-max(x[0],y[0]) for x,y in zip(rb,cb))
                        risk += max(0,penetration)*8
                    else:
                        risk += max(0,planning_wall(design,net,definitions)-clearance)*(8 if clearance<0 else 1)
            else:
                if other.circuit == net.id:
                    continue
                other_diameter=feature_bore_diameter(other,thread_definitions)
                c,d = segment(other,design.block,diameter=other_diameter)
                clearance = segment_distance(a,b,c,d)-radius-other_diameter/2
                risk += max(0,planning_wall(design,net,definitions)-clearance)*(10 if clearance<0 else 1)
        if bore.plugged:
            for other in design.features:
                if other.suppressed or other.face != bore.face:
                    continue
                diameter = definitions[other.definition].clearance_diameter if other.kind == 'cavity' else other.clearance_diameter
                if other.kind == 'drilling' and not other.plugged:
                    continue
                gap = math.hypot(bore.u-other.u,bore.v-other.v)-(bore.clearance_diameter+diameter)/2
                risk += max(0,design.rules.minimum_access_gap-gap)*2
        bore_risks[risk_key]=risk-previous_risk
        if len(bore_risks)>8192:bore_risks.pop(next(iter(bore_risks)))
    return round(risk,6)


def route_margin(design, route):
    """Analytic outer-wall ranking for the entire drilled segment, excluding its entry plane.

    Not a clearance certificate: exact stock, other features and opening checks remain authoritative.
    """
    clearances=[]
    dims=dimensions(design.block)
    for f in route:
        _,_,entry_axis,sign=FACE_AXES[f.face]
        bounds=cylinder_bounds(f,design.block,0,f.depth,f.diameter)
        a,b=segment(f,design.block)
        for axis,(lo,hi) in enumerate(bounds):
            if axis!=entry_axis:
                clearances.extend([min(lo,a[axis],b[axis]),dims[axis]-max(hi,a[axis],b[axis])])
            else:
                clearances.append(dims[axis]-max(hi,b[axis]) if sign>0 else min(lo,b[axis]))
    target=max((required_wall(design,f) for f in route),default=design.rules.minimum_wall or 0)+(design.constraints.preferred_wall_margin or 0)
    penalty=sum(max(0,target-c)**2 for c in clearances)*2
    return dict(target_mm=target,estimated_min_wall_mm=min(clearances) if clearances else None,margin_penalty=round(penalty,6))


def route_cost(design, route):
    length = sum(f.depth for f in route)
    plugs = sum(f.plugged for f in route)
    return round(length + len(route)*(60 if design.constraints.priority == 'simple_machining' else 20)
                 + plugs*(150 if design.constraints.priority == 'fewer_plugs' else 30)
                 + route_margin(design,route)['margin_penalty'],6)


def route_objective(design, route, risk=0, definitions=None):
    """One deterministic lexicographic manufacturing objective for every selector."""
    active=[f for f in route if not f.suppressed]
    plugs=sum(f.plugged for f in active)
    operations=len(active)
    setups=len({f.face for f in active})
    maximum=round(max((f.depth for f in active),default=0),6)
    total=round(sum(f.depth for f in active),6)
    margin=route_margin(design,active)
    quality=(round(risk,6),margin['margin_penalty'],-round(margin['estimated_min_wall_mm'] or 0,6))
    priority=design.constraints.priority
    if priority=='fewer_plugs':return (plugs,operations,maximum,total,quality)
    if priority=='simple_machining':return (operations,setups,plugs,total,quality)
    if priority=='short_drills':return (maximum,total,operations,plugs,quality)
    points=terminal_points(design,definitions)
    owners={f.route_net or f.circuit for f in active}
    terminals=[points[member] for net in design.nets if net.id in owners
               for member in net.members if member in points]
    if not active or not terminals:return (0,0,operations,plugs,total,quality)
    bounds=[cylinder_bounds(f,design.block,0,segment_depth(f),f.diameter) for f in active]
    radius=max(f.diameter/2 for f in active)
    route_bounds=[(min(b[i][0] for b in bounds),max(b[i][1] for b in bounds)) for i in range(3)]
    terminal_bounds=[(min(p[i] for p in terminals)-radius,max(p[i] for p in terminals)+radius) for i in range(3)]
    excess=sum(max(0,b[0]-a[0])+max(0,a[1]-b[1]) for a,b in zip(route_bounds,terminal_bounds))
    spans=[max(a[1],b[1])-min(a[0],b[0]) for a,b in zip(route_bounds,terminal_bounds)]
    excess_volume=max(0,math.prod(spans)-math.prod(b[1]-b[0] for b in terminal_bounds))
    return (round(excess,6),round(excess_volume,6),operations,plugs,total,quality)


def manufacturing_metrics(design, route, risk=0, definitions=None):
    """Deterministic metrics; the priority objective remains lexicographic."""
    active=[f for f in route if not f.suppressed]
    objective=route_objective(design,active,risk,definitions)
    return dict(plugs=sum(f.plugged for f in active),drillings=len(active),
                setup_faces=len({f.face for f in active}),
                max_depth=round(max((f.depth for f in active),default=0),6),
                total_depth=round(sum(f.depth for f in active),6),
                compactness=objective[:2] if design.constraints.priority=='compact' else None,
                quality=objective[-1],objective=objective)


def route_dominates(design, better, worse, better_risk=0, worse_risk=0, definitions=None):
    """Manufacturing Pareto dominance, to be used only after compatibility checks.

    A different cut location is never declared interchangeable just because its
    cost is close. These metrics order opportunities; they do not grant geometry
    feasibility or override the exact engineering-facts score.
    """
    a=route_objective(design,better,better_risk,definitions)
    b=route_objective(design,worse,worse_risk,definitions)
    aa=(*a[:-1],*a[-1]);bb=(*b[:-1],*b[-1])
    return all(x<=y for x,y in zip(aa,bb)) and any(x<y for x,y in zip(aa,bb))


def _strategy_family(key):
    if key.startswith('window:'):return 'window-branch'
    if key.startswith('safe:'):return 'source-entry'
    if key.startswith('branch_'):return 'branch-topology'
    if key.startswith('tree_'):return 'branch-topology' if key.startswith('tree_3:') else 'terminal-tree'
    if key.startswith('port_'):return 'port-approach'
    if key.startswith('axial_'):return 'axial-detour' if key.count(':')==3 else 'axial'
    if key.startswith('simple_'):return 'simple'
    if ':planes_' in key:return 'coordinated-detour'
    return 'direct' if key.endswith(':direct') else 'detour'


def _strategy_shortlist(design, options, definitions=None, limit=16, eligible=None):
    """Bounded Pareto layers per family, then round-robin strategy opportunities.

    Raw domination cannot justify removing a geometrically distinct strategy:
    it may prune better or clear a different sibling route. Keep those as later
    Pareto layers rather than deleting them before exact connectivity pruning.
    """
    buckets={family:[] for family in ('axial','axial-detour','source-entry','window-branch','terminal-tree','branch-topology','port-approach','coordinated-detour','simple','direct','detour')}
    for option in options:
        option['metrics']=manufacturing_metrics(design,option['route'],option['risk'],definitions)
        buckets[_strategy_family(option['key'])].append(option)
    queues={}
    for family,group in buckets.items():
        # Pareto rank by the number of strict dominators, not a scalar score.
        vectors={o['key']:(*o['metrics']['objective'][:-1],*o['metrics']['quality']) for o in group}
        domination={o['key']:sum(all(x<=y for x,y in zip(v,vectors[o['key']])) and any(x<y for x,y in zip(v,vectors[o['key']]))
                                 for key,v in vectors.items() if key!=o['key']) for o in group}
        ranked=sorted(group,key=lambda o:(domination[o['key']],o['metrics']['objective'],o['key']))
        # Give different entry faces / detour planes a chance inside a family.
        seen=set();distinct=[];remaining=[]
        for option in ranked:
            key=option['key'];faces=tuple(sorted({f.face for f in option['route']}))
            strategy=(key.split(':')[0] if family in ('axial','port-approach','terminal-tree','branch-topology') else key.split(':')[-1] if family in ('detour','axial-detour','coordinated-detour') else family,faces)
            if family=='window-branch':strategy=(key.rsplit(':',1)[0],faces)
            (remaining if strategy in seen else distinct).append(option);seen.add(strategy)
        queues[family]=distinct+remaining
    selected=[]
    while len(selected)<limit and any(queues.values()):
        for family in buckets:
            while queues[family] and len(selected)<limit:
                option=queues[family].pop(0)
                if eligible is None or eligible(option):
                    selected.append(option);break
    return selected


def segment_depth(feature):
    return feature.depth+(0 if feature.tip_angle==180 else feature.diameter/2/math.tan(math.radians(feature.tip_angle/2)))


def exact_route_score(design, report, route, *, cad_error=False):
    """Engineering failures first, distinct unresolved facts, then user objective."""
    by_id={f.id:f for f in design.features}
    by_id.update({f.id:f for f in route})
    unresolved=set()
    for check in report['checks']:
        if check['status']!='WARNING':continue
        items=tuple(str(value) for value in check.get('items',[]))
        owner=by_id.get(items[0]) if items else None
        if check['rule']=='construction_closure' and owner and owner.route_net:
            # The same missing closure definition reported on several accesses
            # of one automatic net is one unresolved fact. Counting it per hole
            # would silently make every preference another plug-count objective.
            identity=(owner.route_net,owner.closure_definition_id)
        else:
            identity=items
        unresolved.add((check['rule'],identity,str(check.get('actual')),str(check.get('required'))))
    topology_failure=any(c['status']=='FAIL' and c['rule'] in {'solid_validity','solid_count','step_round_trip'}
                         for c in report['checks'])
    return (1_000_000+report['counts']['FAIL'] if cad_error or topology_failure else report['counts']['FAIL'],
            len(unresolved),route_objective(design,route))


def _plug_cut_overlap(plug, cut, block, plug_bounds=None, diameter=None, *,
                      design=None, definitions=None, threads=None, modifiers=None, cache=None):
    """Bounds can certify separation; otherwise inspect the actual installed plug.

    Finite sampling cannot certify safety, especially at shallow grazing cuts.
    Use the production plug contour, not a nominal cylinder approximation.
    """
    from .machining_predicates import bounds_state,ContactState,plug_violate
    from .closure_runtime import plug_diameter
    cache=cache if cache is not None else {}
    diameter=max(plug_diameter(plug) if diameter is None else diameter,plug.clearance_diameter)
    # Inclined legacy plugs occupy a small extension outside the entry plane.
    extension=0
    if plug.direction:
        cosine=abs(pose(plug,block)[1][FACE_AXES[plug.face][2]])
        extension=plug.diameter/2*math.sqrt(max(0,1-cosine*cosine))/cosine
    bounds=cylinder_bounds(plug,block,-extension,plug.plug_length,diameter)
    other_bounds=cylinder_bounds(cut['feature'],block,cut['start'],cut['end'],
                                 2*max(cut['radius_start'],cut['radius_end']))
    if bounds_state(bounds,other_bounds,0)==ContactState.SAFE:return False
    if design is None:
        from .schema import Design
        design=Design(name='Local machining contact',block=block)
    return plug_violate(plug,cut,design,definitions or {},threads or {},modifiers or {},cache)


def _manufacturing_cuts(feature, definitions, thread_definitions, modifier_definitions):
    if feature.definition:
        definition = definitions[feature.definition]
        for primitive in definition.cutting_primitives or definition.stages:
            angle = math.radians(feature.rotation)
            offset_u, offset_v = getattr(primitive, 'offset_u', 0), getattr(primitive, 'offset_v', 0)
            positioned = feature.model_copy(update=dict(
                u=feature.u+offset_u*math.cos(angle)-offset_v*math.sin(angle),
                v=feature.v+offset_u*math.sin(angle)+offset_v*math.cos(angle)))
            yield dict(feature=positioned, start=primitive.start, end=primitive.end,
                       radius_start=primitive.diameter/2,
                       radius_end=primitive.end_diameter/2 if getattr(primitive, 'kind', '') == 'cone' else primitive.diameter/2,
                       inner_radius=primitive.inner_diameter/2 if getattr(primitive, 'kind', '') == 'annulus' else 0)
    else:
        from .closure_runtime import bound,compatible,cutting_primitives
        closure=bound(feature) if feature.plugged else None
        if closure and compatible(feature,closure):
            # Use the SAME source contour as production and manufacturing,
            # including the larger local entry, seat and transition. Screening
            # only the hydraulic bore missed part of the actual cut volume.
            for p in cutting_primitives(feature,closure):
                yield dict(feature=feature,start=p['start'],end=p['end'],radius_start=p['diameter']/2,
                    radius_end=p.get('end_diameter',p['diameter'])/2 if p['kind']=='cone' else p['diameter']/2,
                    inner_radius=p.get('inner_diameter',0)/2 if p['kind']=='annulus' else 0)
        else:
            diameter = feature_bore_diameter(feature, thread_definitions)
            yield dict(feature=feature, start=0, end=feature.depth,
                       radius_start=diameter/2, radius_end=diameter/2, inner_radius=0)
            if feature.tip_angle != 180 and not feature.through:
                tip = diameter/2/math.tan(math.radians(feature.tip_angle/2))
                yield dict(feature=feature, start=feature.depth, end=feature.depth+tip,
                           radius_start=diameter/2, radius_end=0, inner_radius=0)
    for placement in feature.machining_modifiers:
        for primitive in modifier_definitions[placement.modifier_id]['primitives']:
            yield dict(feature=feature, start=placement.start+primitive['start'],
                       end=placement.start+primitive['end'], radius_start=primitive['diameter']/2,
                       radius_end=primitive['diameter']/2,
                       inner_radius=primitive.get('inner_diameter', 0)/2 if primitive['kind'] == 'annulus' else 0)


def _protected_source_cuts(other, net, definitions, thread_definitions, modifier_definitions):
    """Exclude only the assigned hydraulic window, not the entire source feature."""
    definition = definitions[other.definition]
    allowed = [z for z in definition.zones if
               (other.id if other.kind == 'port' else f'{other.id}:{z.id}') in net.members and
               (other.circuit if other.kind == 'port' else other.circuits.get(z.id)) == net.id]
    angle = math.radians(other.rotation)
    for cut in _manufacturing_cuts(other, definitions, thread_definitions, modifier_definitions):
        matching = []
        for zone in allowed:
            zu = other.u + zone.offset_u*math.cos(angle)-zone.offset_v*math.sin(angle)
            zv = other.v + zone.offset_u*math.sin(angle)+zone.offset_v*math.cos(angle)
            if abs(cut['feature'].u-zu)<1e-6 and abs(cut['feature'].v-zv)<1e-6:
                matching.append(zone)
        breaks = sorted({cut['start'], cut['end'], *(x for z in matching for x in (z.start, z.end)
                          if cut['start'] < x < cut['end'])})
        for start, end in zip(breaks, breaks[1:]):
            first = (start-cut['start'])/(cut['end']-cut['start'])
            last = (end-cut['start'])/(cut['end']-cut['start'])
            part = dict(cut, start=start, end=end,
                        radius_start=cut['radius_start']+(cut['radius_end']-cut['radius_start'])*first,
                        radius_end=cut['radius_start']+(cut['radius_end']-cut['radius_start'])*last)
            windows = [z for z in matching if z.start <= start+1e-6 and end <= z.end+1e-6]
            if windows:
                # The window cannot authorize machining outside its radial extent.
                part['inner_radius'] = max(part['inner_radius'],max(z.diameter/2 for z in windows))
                if part['inner_radius'] >= max(part['radius_start'],part['radius_end'])-1e-6:
                    continue
            yield part, bool(matching)


def _cut_slices(cut):
    if cut.get('_slices') is not None:
        yield from cut['_slices']
        return
    if abs(cut['radius_start']-cut['radius_end']) < 1e-7:
        yield cut
        return
    parts=[]
    for index in range(12):
        a, b = index/12, (index+1)/12
        parts.append(dict(cut,
                   start=cut['start']+(cut['end']-cut['start'])*a,
                   end=cut['start']+(cut['end']-cut['start'])*b,
                   radius_start=cut['radius_start']+(cut['radius_end']-cut['radius_start'])*a,
                   radius_end=cut['radius_start']+(cut['radius_end']-cut['radius_start'])*b,
                   _bounds=None,_segment=None,_slices=None))
    cut['_slices']=parts
    yield from parts


def _cuts_too_close(route_cuts, obstacle, block, clearance, cache=None):
    """Prove separation with outer bounds; resolve uncertain finite cuts locally."""
    from .machining_predicates import cuts_violate
    cache=cache if cache is not None else {}
    def bounds(cut):
        if cut.get('_bounds') is None:
            cut['_bounds']=cylinder_bounds(cut['feature'], block, cut['start'], cut['end'],
                                           2*max(cut['radius_start'], cut['radius_end']))
        return cut['_bounds']
    def endpoints(cut):
        if cut.get('_segment') is None:
            cut['_segment']=segment(cut['feature'],block,cut['start'],cut['end'])
        return cut['_segment']
    def separated(a, b):
        tolerance=1e-6 if clearance>0 else 0
        return any(x[1]+clearance <= y[0]+tolerance or y[1]+clearance <= x[0]+tolerance
                   for x,y in zip(a,b))
    outer_bounds = bounds(obstacle)
    for route_cut in route_cuts:
        if separated(bounds(route_cut), outer_bounds):
            continue
        if obstacle['inner_radius']:
            origin,direction = pose(obstacle['feature'],block)
            radial = []
            for point in segment(route_cut['feature'],block,route_cut['start'],route_cut['end']):
                delta = tuple(point[i]-origin[i] for i in range(3))
                axial = sum(delta[i]*direction[i] for i in range(3))
                radial.append(math.sqrt(max(0,sum(v*v for v in delta)-axial*axial)))
            if max(radial)+max(route_cut['radius_start'],route_cut['radius_end'])+clearance <= obstacle['inner_radius']:
                continue
        uncertain=False
        for cut in _cut_slices(obstacle):
            cut_bounds = bounds(cut)
            for part in _cut_slices(route_cut):
                if separated(bounds(part), cut_bounds):
                    continue
                a,b = endpoints(part)
                c,d = endpoints(cut)
                if (segment_distance(a,b,c,d)-max(part['radius_start'],part['radius_end'])
                        -max(cut['radius_start'],cut['radius_end']) < clearance-(1e-6 if clearance>0 else 0)):
                    uncertain=True
                    break
            if uncertain:break
        if uncertain and cuts_violate(route_cut,obstacle,block,clearance,cache):return True
    return False


def _feature_key(feature):
    return feature.model_dump_json(exclude={'connects_to','schematic_id'})


def _routing_context_key(design,net=None):
    # Neither source documents nor review/provenance text affect cut screening.
    # Retain every rule, condition, authored cut and stable ID that does.
    return (design.block.model_dump_json(),design.rules.model_dump_json(),
            design.project_defaults.model_dump_json(),design.constraints.model_dump_json(),design.project_context,
            tuple(n.model_dump_json(exclude={'routing_variant','route_state','route_issue'}) for n in design.nets),
            tuple(_feature_key(f) for f in design.features if not f.suppressed),
            net.model_dump_json(exclude={'routing_variant','route_state','route_issue'}) if net else None)


def route_obstructions(design, net, route,thread_definitions=None,definitions=None,modifier_definitions=None,cache=None):
    """Conservative finite-cut, wall, plug and access screen; OCCT grants feasibility."""
    if thread_definitions is None:
        from .engineering_db import thread_definitions_for_design
        thread_definitions=thread_definitions_for_design(design)
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    if modifier_definitions is None:
        from .engineering_db import modifier_definitions_for_design
        modifier_definitions=modifier_definitions_for_design(design) if any(f.machining_modifiers for f in design.features) else {}
    cache=cache if cache is not None else {}
    if cache.get('block') not in (None,dimensions(design.block)):cache.clear()
    cache['block']=dimensions(design.block)
    results=cache.setdefault('screens',{})
    result_key=(_routing_context_key(design,net),tuple(_feature_key(f) for f in route))
    if result_key in results:return set(results[result_key])
    cuts_cache=cache.setdefault('cuts',{});protected_cache=cache.setdefault('protected',{})
    signatures={}
    def signature(feature):
        key=id(feature)
        if key not in signatures:signatures[key]=feature.model_dump_json(exclude={'connects_to'})
        return signatures[key]
    def cuts(feature):
        key=signature(feature)
        if key not in cuts_cache:cuts_cache[key]=list(_manufacturing_cuts(feature,definitions,thread_definitions,modifier_definitions))
        return cuts_cache[key]
    def protected(feature):
        key=(signature(feature),net.id,tuple(net.members))
        if key not in protected_cache:protected_cache[key]=list(_protected_source_cuts(feature,net,definitions,thread_definitions,modifier_definitions))
        return protected_cache[key]
    failures = set()
    obstacles=[f for f in design.features if f.route_net!=net.id]+route
    for bore in route:
        if wall_unresolved(design,bore,definitions=definitions):failures.add(('pressure_strength',bore.id))
        if route_margin(design,[bore])['estimated_min_wall_mm'] < required_wall(design,bore,definitions=definitions)-1e-6:
            failures.add(('external_wall',bore.id))
        if bore.plugged:
            from .closure_runtime import plug_diameter
            plug_diameter_value=plug_diameter(bore)
            plug_bounds=cylinder_bounds(bore,design.block,0,bore.plug_length,plug_diameter_value)
            a,b = segment(bore, design.block, -bore.clearance_height, 0)
            for other in obstacles:
                if other.suppressed or other.id == bore.id or not (other.kind in ('port','cavity') or other.plugged):
                    continue
                # A thread-only placeholder declares no installation envelope
                # in production. Its real tap cut is still screened below.
                if other.kind=='port' and other.thread_only and not other.definition:continue
                definition = definitions[other.definition] if other.definition else None
                diameter = definition.clearance_diameter if definition else other.clearance_diameter
                height = definition.clearance_height if definition else other.clearance_height
                c,d = segment(other, design.block, -height, 0)
                if segment_distance(a,b,c,d)-(bore.clearance_diameter+diameter)/2 < design.rules.minimum_access_gap-1e-6:
                    from .machining_predicates import access_violate
                    if not access_violate(bore,other,design,definitions,thread_definitions,modifier_definitions,cache):continue
                    failures.add(('installation_access', *sorted((bore.id, other.id))))
            for other in obstacles:
                if other.suppressed or other.id == bore.id:
                    continue
                if any(_plug_cut_overlap(bore, cut, design.block,plug_bounds,plug_diameter_value,
                        design=design,definitions=definitions,threads=thread_definitions,modifiers=modifier_definitions,cache=cache) for cut in cuts(other)):
                    failures.add(('plug_cut', *sorted((bore.id, other.id))))
        radius=bore.diameter/2
        route_cuts = cuts(bore)
        for other in obstacles:
            if other.suppressed or other.id == bore.id or not other.definition:
                continue
            # Exact validation permits a coaxial continuation through its inlet.
            if (other.kind == 'port' and other.id in net.members and other.circuit == net.id
                    and other.face == bore.face and abs(other.u-bore.u)<1e-6 and abs(other.v-bore.v)<1e-6):
                continue
            definition = definitions[other.definition]
            assigned = [z for z in definition.zones if
                        (other.id if other.kind == 'port' else f'{other.id}:{z.id}') in net.members and
                        (other.circuit if other.kind == 'port' else other.circuits.get(z.id)) == net.id]
            near_assigned = False
            for zone in assigned:
                angle = math.radians(other.rotation)
                placed = other.model_copy(update=dict(
                    u=other.u+zone.offset_u*math.cos(angle)-zone.offset_v*math.sin(angle),
                    v=other.v+zone.offset_u*math.sin(angle)+zone.offset_v*math.cos(angle)))
                c,d = segment(placed, design.block, zone.start, zone.end)
                window_radius = max((max(stage.diameter,getattr(stage,'end_diameter',0))/2
                                     for stage in definition.cutting_primitives or definition.stages
                                     if stage.start <= (zone.start+zone.end)/2 <= stage.end
                                     and abs(getattr(stage,'offset_u',0)-zone.offset_u)<1e-6
                                     and abs(getattr(stage,'offset_v',0)-zone.offset_v)<1e-6), default=zone.diameter/2)
                for route_cut in route_cuts:
                    a,b = segment(route_cut['feature'], design.block, route_cut['start'], route_cut['end'])
                    if segment_distance(a,b,c,d) < max(route_cut['radius_start'],route_cut['radius_end'])+window_radius-1e-6:
                        near_assigned = True
                        break
            for whole_cut, own_window in protected(other):
                threshold = 0 if own_window and near_assigned else required_wall(design,bore,other,definitions=definitions)
                if _cuts_too_close(route_cuts, whole_cut, design.block, threshold,cache):
                    failures.add(('source_protected' if threshold==0 else 'source_wall',
                                  *sorted((bore.id, other.id))))
                    break
        for other in obstacles:
            if other.suppressed or other.id == bore.id or other.definition or other.circuit == net.id:
                continue
            for whole_cut in cuts(other):
                if _cuts_too_close(route_cuts, whole_cut, design.block, required_wall(design,bore,other,definitions=definitions),cache):
                    failures.add(('cross_net_wall', *sorted((bore.id, other.id))))
                    break
        if bore.depth < 2*radius:continue
        a,b=segment(bore,design.block,radius,bore.depth-radius)
        for other in obstacles:
            if other.suppressed or other.definition or other.id==bore.id:
                continue
            if other.circuit==net.id:
                # Same-net intersections are intentional, but separated cuts still
                # owe a minimum wall. Outer bounds prove separation before applying
                # the inner-capsule upper bound on their distance.
                bounds=[]
                for f in (bore,other):
                    diameter=feature_bore_diameter(f,thread_definitions)
                    tip=0 if f.tip_angle==180 else diameter/2/math.tan(math.radians(f.tip_angle/2))
                    bounds.append(cylinder_bounds(f,design.block,0,f.depth+tip,diameter))
                if not any(x[1]<y[0]-1e-6 or y[1]<x[0]-1e-6 for x,y in zip(*bounds)):
                    continue
            r=feature_bore_diameter(other,thread_definitions)/2
            if other.depth < 2*r:continue
            c,d=segment(other,design.block,r,other.depth-r)
            clearance=segment_distance(a,b,c,d)-radius-r
            if clearance < required_wall(design,bore,other,definitions=definitions)-1e-6:
                failures.add(('feature_wall' if other.circuit==net.id else 'cross_net_wall',*sorted((bore.id,other.id))))
    results[result_key]=frozenset(failures)
    if len(results)>2048:results.pop(next(iter(results)))
    return failures


class _ProposalSnapshot:
    """Lazy source BRep and pruning evidence owned by one proposal resolution."""
    def __init__(self, design, definitions, threads, modifiers):
        from .route_state import pending_nets
        automatic=pending_nets(design)
        self.source=design.model_copy(deep=True)
        self.source.features=[f for f in self.source.features if f.route_net not in automatic]
        self.definitions,self.threads,self.modifiers=definitions,threads,modifiers
        self.geometry=None
        self.pruning_geometry=None
        self.cache={}
        self.results={}
        self.options={}
        self.catalogs={}
        self.obstructions={}
        self.tools=None
        self.sizing={}
        self.pools={};self.pair_failures={};self.repair_states={};self.repair_diagnostics=[]
        self.pool_diagnostics={};self.combination_diagnostics=[];self.combination_budget={'used':0}
        self.last_connectivity={}
        self.candidate_errors={};self.cad_error_records=[]
        # Single-terminal circuits also produce candidate pools (e.g. pilots).
        # Count the same domain in both numerator and denominator.
        self.progress_nets=set(automatic)
        self.completed_nets=set()

    def route_progress(self,stage,net=None,completed=0,total=0,*,finished=False):
        """Actual bounded pool work in the existing request-owned trace."""
        from .timing import progress
        if net is not None:self.progress_nets.add(net.id)  # Actual local conflict expansion may add a pool.
        if finished and net is not None:self.completed_nets.add(net.id)
        count=len(self.progress_nets)
        fraction=min(1,completed/max(1,total)) if net is not None and net.id not in self.completed_nets else 0
        progress(stage,8+32*min(1,(len(self.completed_nets)+fraction)/max(1,count)),routing=dict(
            net=net.id if net else None,completed_candidates=completed,candidate_limit=total,
            completed_nets=len(self.completed_nets),net_count=count))

    def cut_shape(self,design,feature):
        from .geometry import feature_geometry
        key=_feature_key(feature)
        shapes=self.cache.setdefault('machining_cut_shapes',{})
        if key not in shapes:
            context=design.model_copy(update=dict(features=[feature],engravings=[],block_modifiers=[]))
            cuts,_,_,_,_,_,_=feature_geometry(context,self.definitions,self.threads,self.modifiers)
            shapes[key]=cuts[feature.id]
        return shapes[key]

    def simplify(self, design, net, route, *, known_failures=None,preserve_generated=False):
        # Generated siblings affect obstruction screening, but not the same-net
        # fluid graph. Include every explicit outside contact in the cache key:
        # a later route declaring a required contact must protect that drilling.
        protected=tuple(sorted({key for f in design.features if f.route_net!=net.id for key in f.connects_to}))
        key=(net.model_dump_json(exclude={'routing_variant'}),
             tuple(f.model_dump_json() for f in route),protected,preserve_generated)
        if key not in self.results:
            if self.pruning_geometry is None:
                from .geometry import feature_geometry
                from types import SimpleNamespace
                from .cad_geometry import cad_operation,require_fluid_solid
                context=dict(scope='source',net_id=net.id,source_features=[f.id for f in self.source.features][:16])
                with cad_operation('geometry.feature_geometry.source',context):
                    source_cuts,nodes,circuits,_,_,placements,_=feature_geometry(self.source,self.definitions,self.threads,self.modifiers)
                for label,items in (('cut',source_cuts),('node',nodes)):
                    for node,shape in items.items():
                        require_fluid_solid(shape,'routing.source_'+label,dict(context,node_pair=[node]))
                self.pruning_geometry=SimpleNamespace(nodes=nodes,circuits=circuits,placements=placements)
                shapes=self.cache.setdefault('machining_cut_shapes',{})
                shapes.update({_feature_key(f):source_cuts[f.id] for f in self.source.features if f.id in source_cuts})
            detail={}
            result,connected=simplify_generated_route(design,net,route,source_geometry=self.pruning_geometry,
                definitions=self.definitions,thread_definitions=self.threads,modifier_definitions=self.modifiers,
                cache=self.cache,known_failures=known_failures,diagnostics=detail,preserve_generated=preserve_generated)
            self.results[key]=([f.model_copy(deep=True) for f in result],connected,detail)
        result,connected,detail=self.results[key]
        self.last_connectivity[net.id]=detail
        # Tool sizing and presentation can mutate a selected proposal afterwards.
        return [f.model_copy(deep=True) for f in result],connected


@timed('route.simplification')
def simplify_generated_route(design, net, route, *, source_geometry=None, definitions=None,
                             thread_definitions=None, modifier_definitions=None, cache=None, known_failures=None, diagnostics=None,preserve_generated=False):
    """Prune only proven redundant automatic cuts using exact fluid-node contacts."""
    from .geometry import build_geometry,feature_geometry
    from .flow import required_area, opening_area
    from .cad_geometry import cad_operation,require_fluid_solid,checked_shape,checked_intersection,solid_volume,GeometryEvaluationError
    if source_geometry is None:
        source=design.model_copy(update=dict(features=[f for f in design.features if f.route_net!=net.id]))
        with cad_operation('routing.source_geometry',dict(scope='source',net_id=net.id)):
            source_geometry=build_geometry(source,definitions,thread_definitions,modifier_definitions)
    cache=cache if cache is not None else {}
    cuts=cache.setdefault('cuts',{});bounds=cache.setdefault('bounds',{})
    nodes={key:shape for key,shape in source_geometry.nodes.items() if source_geometry.circuits[key]==net.id}
    source_keys=set(nodes)
    validated=cache.setdefault('validated_fluid_nodes',set())
    for node,shape in nodes.items():
        if 'source:'+node not in validated:
            require_fluid_solid(shape,'routing.source_node',dict(scope='source',net_id=net.id,node_pair=[node]))
            validated.add('source:'+node)
    required=set(net.members)
    protected=required|{access.id for access in net.construction_access}
    if preserve_generated:protected.update(f.id for f in route)
    for feature in design.features:
        if feature.route_net!=net.id:protected.update(feature.connects_to)
    from .engineering_db import definitions_for_design
    definitions=definitions if definitions is not None else definitions_for_design(design)
    diagnostics=diagnostics if diagnostics is not None else {}
    diagnostics.update(required=sorted(required),stage='exact_fluid_contacts',
        fluid_connectivity_verified=False,all_fluid_nodes_connected=False,flow_opening_verified=False if net.flow_lpm else None,
        full_engineering_validation_passed=None,
        drillings=[{key:getattr(f,key) for key in ('id','face','u','v','diameter','depth','tip_angle','plug_length','closure_definition_id')} for f in route])
    if not required.issubset(nodes):
        diagnostics.update(missing_required=sorted(required-set(nodes)),connected=False)
        return route,False
    # A capsule ending at cylinder depth omits the conical drill tip. It is not
    # a conservative disconnection test. Nor can a coarse contact prove flow.
    # Reuse cached per-feature fluid solids/edges for BOTH admission and pruning.
    signatures={key:'source:'+key for key in nodes}
    directions=dict(source_geometry.placements)
    for feature in route:
        # Identity/net ownership are graph labels, not fluid solid geometry.
        # Keep every effective cut/closure/placement field and the fixed block;
        # identical machining can reuse its exact measurement across variants.
        signature=repr(dimensions(design.block))+':'+feature.model_dump_json(
            exclude={'id','connects_to','schematic_id','machining_id','route_net','frozen_net','circuit'})
        if signature not in cuts:
            candidate=design.model_copy(update=dict(features=[feature],engravings=[],block_modifiers=[]))
            context=dict(scope='candidate',net_id=net.id,node_pair=[feature.id])
            with cad_operation('geometry.feature_geometry.generated',context):
                machining,fluid,_,_,_,placements,_=feature_geometry(candidate,definitions,thread_definitions or {},modifier_definitions or {})
            cache.setdefault('machining_cut_shapes',{})[_feature_key(feature)]=machining[feature.id]
            require_fluid_solid(fluid[feature.id],'routing.generated_node',context)
            cuts[signature]=(fluid[feature.id],placements[feature.id])
        nodes[feature.id],directions[feature.id]=cuts[signature]
        signatures[feature.id]=signature
    if not required.issubset(nodes):
        return route,False
    graph={key:set() for key in nodes};fluid_graph={key:set() for key in nodes}
    area=required_area(net.flow_lpm,net.velocity_limit) if net.flow_lpm else None
    fluid_contacts=cache.setdefault('fluid_contacts',{})
    measurements=cache.setdefault('fluid_contact_measurements',{})
    contact_errors=cache.setdefault('fluid_contact_errors',{})
    for a,b in itertools.combinations(nodes,2):
        pair=tuple(sorted((signatures[a],signatures[b])))
        key=(pair,design.rules.minimum_overlap_volume,area)
        context=dict(scope='source' if a in source_keys and b in source_keys else 'candidate',net_id=net.id,node_pair=[a,b])
        if key in contact_errors:
            raise GeometryEvaluationError({**contact_errors[key],**context,'cached_rejection':True})
        if key not in fluid_contacts:
            try:
                for node in (a,b):
                    signature=signatures[node]
                    if signature not in bounds:
                        node_context=dict(scope='source' if node in source_keys else 'candidate',net_id=net.id,node_pair=[node])
                        checked_shape(nodes[node],'routing.bounds_input',node_context,allow_empty=False)
                        with cad_operation('routing.node_bounds',node_context):box=nodes[node].BoundingBox()
                        bounds[signature]=((box.xmin,box.xmax),(box.ymin,box.ymax),(box.zmin,box.zmax))
                # Measurements belong to unchanged individual fluid geometry;
                # flow area and overlap thresholds only decide acceptance.
                # Different sizing/flow checks reuse the same exact measurement.
                common=None
                if pair not in measurements:
                    separated=any(min(x[1],y[1])<=max(x[0],y[0]) for x,y in zip(bounds[signatures[a]],bounds[signatures[b]]))
                    common=None if separated else checked_intersection(nodes[a],nodes[b],'routing.fluid_intersection',context)
                    volume=0 if separated else solid_volume(common,'routing.common_volume',context)
                    measurements[pair]=(volume,None)
                volume,opening=measurements[pair]
                contact=volume>0 and volume+1e-6>=design.rules.minimum_overlap_volume
                if contact and opening is None:
                    if common is None:common=checked_intersection(nodes[a],nodes[b],'routing.fluid_intersection',context)
                    opening=opening_area(nodes[a],nodes[b],
                        [directions[node.split(':')[0]]['direction'] for node in (a,b)],common=common,context=context)
                    measurements[pair]=(volume,opening)
                if not contact:opening=0
            except GeometryEvaluationError as exc:
                contact_errors[key]=dict(exc.record)
                raise
            # Finite tip overlap still requires a real positive opening. With
            # unknown flow there is no invented flow/velocity area requirement.
            physical=contact and opening>1e-6
            fluid_contacts[key]=(physical,physical and (area is None or opening+1e-6>=area))
        physical,adequate=fluid_contacts[key]
        if physical:fluid_graph[a].add(b);fluid_graph[b].add(a)
        if adequate:graph[a].add(b);graph[b].add(a)

    def reachable(active,edges=None):
        edges=graph if edges is None else edges
        visited=set();pending=[min(required)] if required else []
        while pending:
            key=pending.pop()
            if key in visited:continue
            visited.add(key);pending.extend((edges[key]&active)-visited)
        return visited

    def connected(active):
        return bool(required) and required.issubset(active) and reachable(active)==active

    active=set(nodes);visited=reachable(active);physical_reachable=reachable(active,fluid_graph)
    components=[];unseen=set(nodes)
    while unseen:
        pending=[min(unseen)];component=set()
        while pending:
            node=pending.pop()
            if node in component:continue
            component.add(node);pending.extend(fluid_graph[node]-component)
        unseen-=component;components.append(sorted(component))
    diagnostics.update(exact_edges=[list(edge) for edge in sorted((a,b) for a in fluid_graph for b in fluid_graph[a] if a<b)],
                       flow_edges=[list(edge) for edge in sorted((a,b) for a in graph for b in graph[a] if a<b)] if area is not None else None,
                       fluid_components=components,unreachable_required=sorted(required-physical_reachable),
                       fluid_connectivity_verified=bool(required) and required.issubset(physical_reachable),
                       all_fluid_nodes_connected=bool(required) and required.issubset(physical_reachable) and physical_reachable==active,
                       flow_opening_verified=(bool(required) and required.issubset(visited)) if area is not None else None,
                       full_engineering_validation_passed=None)
    terminal_groups=[sorted(required&set(component)) for component in components if required&set(component)]
    diagnostics['disconnected_terminal_groups']=terminal_groups if len(terminal_groups)>1 else []
    missing=[]
    terminal_components=[component for component in components if required&set(component)]
    for first,second in itertools.combinations(terminal_components,2):
        def gap(a,b):
            return sum(max(0,x[0]-y[1],y[0]-x[1])**2 for x,y in zip(bounds[signatures[a]],bounds[signatures[b]]))
        distance,a,b=min((gap(a,b),a,b) for a in first for b in second)
        missing.append(dict(terminals=[sorted(required&set(first)),sorted(required&set(second))],
            nearest_nodes=[a,b],bounds_gap_mm=math.sqrt(distance),reason='no_verified_fluid_contact_between_components'))
    diagnostics['missing_component_links']=missing[:16]
    if not required.issubset(visited):
        diagnostics.update(connected=False,unreachable_flow_required=sorted(required-visited) if area is not None else [])
        return route,False
    # A disconnected redundant GENERATED island must not invalidate a connected
    # terminal tree. Keep every authored/frozen/explicitly referenced node.
    removable={f.id for f in route if net.routing=='automatic' and f.route_net==net.id and not f.frozen_net and f.id not in protected}
    islands=active-visited
    if not islands<=removable:
        diagnostics.update(connected=False,unreachable_protected=sorted(islands-removable))
        return route,False
    remaining=[f for f in route if f.id not in islands];active-=islands
    diagnostics['discarded_islands']=sorted(islands)
    failures=(route_obstructions(design,net,remaining,thread_definitions,definitions,modifier_definitions)
              if known_failures is None else known_failures)
    while True:
        removals=[]
        for feature in remaining:
            if (net.routing!='automatic' or feature.route_net!=net.id or feature.frozen_net
                    or feature.id in protected):
                continue
            # Removing a cut cannot change the other individual fluid solids.
            # Recompute their contact graph from cached exact edges, excluding
            # the proposed node; every remaining node must still reach a terminal.
            if not connected(active-{feature.id}):
                continue
            trial=[f for f in remaining if f.id!=feature.id]
            # These hard rules are per cut or cut pair. With every remaining
            # solid unchanged, deletion only removes rules involving this ID;
            # it cannot introduce a new wall, protected-region, plug or access
            # conflict. Connectivity is independently recomputed above.
            obstruction={failure for failure in failures if feature.id not in failure[1:]}
            removals.append((route_objective(design,trial,definitions=definitions),feature.id,trial,obstruction))
        if not removals:break
        _,removed,remaining,failures=min(removals,key=lambda item:item[:2])
        active.remove(removed)
    removed={f.id for f in route}-{f.id for f in remaining}
    if removed:
        remaining=[f.model_copy(update=dict(connects_to=[key for key in f.connects_to if key not in removed]))
                   for f in remaining]
    # Every incidental same-net contact must also meet the direct-contact rule.
    # Another adequate path through the graph cannot excuse a sliver contact.
    diagnostics['insufficient_direct_contacts']=[dict(nodes=[a,b],volume_mm3=measurements[tuple(sorted((signatures[a],signatures[b])))][0])
        for a,b in itertools.combinations(sorted(active),2) if a.split(':')[0]!=b.split(':')[0]
        and 1e-6<measurements.get(tuple(sorted((signatures[a],signatures[b]))),(0,None))[0]<design.rules.minimum_overlap_volume]
    diagnostics.update(connected=True,all_fluid_nodes_connected=True,retained_drillings=[f.id for f in remaining])
    return remaining,True


def _verify_route_candidate(design,net,option,snapshot,*,known_failures=None,prune=True):
    """Reject recoverable generated-candidate CAD failures, never source failures."""
    from .cad_geometry import cad_operation,GeometryEvaluationError
    from copy import deepcopy
    from .timing import diagnostic
    if option.get('cad_geometry_error'):return False
    context=dict(scope='candidate',net_id=net.id,candidate_variant=option['key'])
    key=(effective_net(design,net).model_dump_json(),tuple(_feature_key(f) for f in option['route']))
    try:
        if key in snapshot.candidate_errors:
            raise GeometryEvaluationError({**snapshot.candidate_errors[key],**context,'cached_rejection':True})
        with cad_operation('routing.verify_candidate',context):
            return _verify_route_candidate_impl(design,net,option,snapshot,known_failures=known_failures,prune=prune)
    except GeometryEvaluationError as exc:
        exc.record.setdefault('net_id',net.id);exc.record.setdefault('candidate_variant',option['key'])
        if exc.record.get('scope')=='source':
            diagnostic('cad_source_error',exc.record)
            raise
        record=deepcopy(exc.record);record.update(context)
        snapshot.candidate_errors[key]=record
        snapshot.cad_error_records=(snapshot.cad_error_records+[{k:v for k,v in record.items() if k!='traceback'}])[-32:]
        diagnostic('cad_candidate_error',record)
        # Do not pass a potentially malformed generated cut to production CAD.
        # Other candidates continue; only this rejected candidate loses its cuts.
        option.update(route=[],connection_verified=False,cad_geometry_error=record,
            admission=dict(source_obstruction_safe=None,fluid_connectivity_verified=False,all_fluid_nodes_connected=False,
                           flow_opening_adequate=None,full_engineering_validation_passed=None),
            connectivity_detail=dict(connected=False,missing_required=list(net.members),cad_geometry_error={k:v for k,v in record.items() if k!='traceback'}),
            conflicts=[['candidate_geometry_error',net.id],['connectivity',net.id]],hard_failures=2,risk=0,cost=0)
        option.pop('_connectivity_geometry',None);option.pop('_connectivity_conditions',None)
        return False


def _verify_route_candidate_impl(design,net,option,snapshot,*,known_failures=None,prune=True):
    """Independent source, fluid, optional flow, and full-validation facts.

    This gate uses cached individual BReps, never a full production build. It is
    mandatory after final sizing/binding even when actual flow is unknown.
    """
    from .closure_runtime import bind_route
    from copy import deepcopy
    net=effective_net(design,net)
    option['connection_verified']=False
    option.pop('_connectivity_geometry',None)
    option.pop('_connectivity_conditions',None)
    option.pop('admission',None)
    option.pop('connectivity_detail',None)
    original=option['route'];bound=bind_route(design,original)
    route,connected=snapshot.simplify(design,net,bound,known_failures=known_failures,preserve_generated=not prune)
    detail=deepcopy(snapshot.last_connectivity.get(net.id,{}))
    failures=route_obstructions(design,net,route,snapshot.threads,snapshot.definitions,snapshot.modifiers,snapshot.obstructions)
    # Broad-phase overlap is not authorization: non-connected SAME-net cuts
    # still owe the exact wall. Reuse individual machining BReps and the same
    # pair engine as validation, without constructing a production block.
    from .spatial import ExactPairs
    if not hasattr(snapshot,'cut_pairs'):snapshot.cut_pairs=ExactPairs()
    pairs=snapshot.cut_pairs
    fixed=[f for f in design.features if f.route_net!=net.id and not f.suppressed]
    for first,second in itertools.chain(itertools.combinations(route,2),itertools.product(route,fixed)):
        if first.id==second.id:continue
        required=required_wall(design,first,second,definitions=snapshot.definitions)
        a=snapshot.cut_shape(design,first);b=snapshot.cut_shape(design,second)
        if pairs.lower_bound(a,b)>=required:continue
        volume=pairs.volume(a,b)
        if volume<=1e-6 or first.kind=='mounting' or second.kind=='mounting':
            distance,separated=pairs.separation(a,b,required)
            if not separated:
                failures.add(('exact_feature_wall',*sorted((first.id,second.id))))
                token=(dimensions(design.block),tuple(sorted((_feature_key(first),_feature_key(second)))))
                snapshot.obstructions.setdefault('exact_cut_distances',{})[token]=distance
    failures.update(('forbidden_face',f.id) for f in route if f.face in design.constraints.forbidden_drilling_faces)
    source_safe=not failures
    direct=not detail.get('insufficient_direct_contacts',[])
    failures.update(('insufficient_direct_contact',*row['nodes']) for row in detail.get('insufficient_direct_contacts',[]))
    by_id={f.id:f for f in [*design.features,*route]}
    for contact in detail.get('insufficient_direct_contacts',[]):
        first,second=(by_id[node.split(':')[0]] for node in contact['nodes'])
        token=(dimensions(design.block),tuple(sorted((_feature_key(first),_feature_key(second)))))
        snapshot.obstructions.setdefault('inadequate_contact_volumes',{})[token]=contact['volume_mm3']
    physical=detail.get('fluid_connectivity_verified',False)
    flow=detail.get('flow_opening_verified') if net.flow_lpm else None
    if not physical or not detail.get('all_fluid_nodes_connected',False):failures.add(('connectivity',net.id))
    if flow is False:failures.add(('flow_opening',net.id))
    admission=dict(source_obstruction_safe=source_safe,fluid_connectivity_verified=physical,
        all_fluid_nodes_connected=detail.get('all_fluid_nodes_connected',False),direct_contact_adequate=direct,
        flow_opening_adequate=flow,full_engineering_validation_passed=None)
    option.update(route=route,connection_verified=physical,connectivity_detail=detail,admission=admission,
        conflicts=[list(f) for f in sorted(failures)],hard_failures=len(failures),
        pruned_ids=sorted(set(option.get('pruned_ids',[]))|({f.id for f in original}-{f.id for f in route})),
        risk=proximity_risk(design,net,route,snapshot.definitions,snapshot.threads,snapshot.obstructions),
        cost=route_cost(design,route),
        _connectivity_geometry=tuple(_feature_key(f) for f in route),
        _connectivity_conditions=(net.flow_lpm,net.velocity_limit))
    return connected and source_safe and physical and direct and flow is not False


def _candidate_admitted(option,net=None):
    """Fail closed on absent, failed, or stale proof. Not full validation PASS."""
    facts=option.get('admission',{})
    conditions=option.get('_connectivity_conditions')
    if not isinstance(conditions,tuple) or len(conditions)!=2:return False
    flow=net.flow_lpm if net is not None else conditions[0]
    return (option.get('connection_verified') is True and facts.get('source_obstruction_safe') is True and
        facts.get('direct_contact_adequate') is True and
        facts.get('fluid_connectivity_verified') is True and facts.get('all_fluid_nodes_connected') is True and
        (facts.get('flow_opening_adequate') is True if flow is not None else facts.get('flow_opening_adequate') is None) and
        option.get('_connectivity_geometry')==tuple(_feature_key(f) for f in option['route']) and
        (net is None or option.get('_connectivity_conditions')==(net.flow_lpm,net.velocity_limit)))


def route_candidate_catalog(design, net, definitions, thread_definitions, modifier_definitions, *, expanded=False, cache=None):
    net=effective_net(design,net)
    """Raw source strategies, before any shortlist or simplification."""
    orders = list(itertools.permutations(range(3)))
    if net.preferred_axis != 'auto':
        orders = [o for o in orders if o[0] == 'xyz'.index(net.preferred_axis)]
    entries = ['nearest','negative','positive'] if net.entry_preference == 'nearest' else [net.entry_preference]
    options, seen = [],set()
    from .cavity_access import axial_route_candidates
    for key,route in axial_route_candidates(design,net,definitions,thread_definitions,modifier_definitions,None,cache):
        signature = tuple((f.face,round(f.u,5),round(f.v,5),round(f.depth,5),f.plugged) for f in route)
        if signature in seen:continue
        seen.add(signature)
        options.append(dict(key=key,route=route,risk=proximity_risk(design,net,route,definitions,thread_definitions,cache),cost=route_cost(design,route)))
    for i,route in enumerate(simple_routes(design,net,definitions)):
        signature = tuple((f.face,round(f.u,5),round(f.v,5),round(f.depth,5),f.plugged) for f in route)
        if signature in seen:
            continue
        seen.add(signature)
        options.append(dict(key=f'simple_{i}',route=route,risk=proximity_risk(design,net,route,definitions,thread_definitions,cache),cost=route_cost(design,route)))
    sides=('p','m','p2','m2') if expanded else ('p','m')
    detours = ['direct'] + [f'offset_{axis}_{side}' for axis in 'xyz' for side in sides]
    safe_planes = obstacle_safe_planes(design, net, definitions, thread_definitions, modifier_definitions)
    for order,entry,detour in itertools.product(orders,entries,detours):
        key = ''.join('xyz'[i] for i in order)+':'+entry+':'+detour
        route = propose(design,net,order,entry,detour,definitions,safe_planes)
        signature = tuple((f.face,round(f.u,5),round(f.v,5),round(f.depth,5),f.plugged) for f in route)
        if signature in seen:
            continue
        seen.add(signature)
        risk = proximity_risk(design,net,route,definitions,thread_definitions,cache)
        options.append(dict(key=key,route=route,risk=risk,cost=route_cost(design,route)))
    return options


def coordinated_detours(source,net,context,definitions,threads,modifiers,cache):
    """Explicit-coordinate orthogonal approaches around OTHER active routes.

    Stored variants must not depend on reroute order. Dynamic obstacle planes
    are therefore encoded, not looked up again from a changing route catalog.
    """
    if net.drilling_mode!='orthogonal' or not any(f.route_net and f.route_net!=net.id for f in context.features):return []
    key=(_routing_context_key(context,net),'coordinated_detours')
    catalogs=cache.setdefault('coordinated_catalogs',{})
    if key not in catalogs:
        planes=obstacle_safe_planes(context,net,definitions,threads,modifiers,include_routes=True,routes_only=True)
        orders=[o for o in itertools.permutations(range(3)) if net.preferred_axis=='auto' or o[0]=='xyz'.index(net.preferred_axis)]
        entries=('nearest','negative','positive') if net.entry_preference=='nearest' else (net.entry_preference,)
        options=[];seen=set()
        for axis in range(3):
            for side in 'mp':
                # Both nearest source/route-safe planes are kept. The existing
                # family/Pareto budget decides which get exact pruning work.
                for coordinate in planes[axis][side]:
                    detour=f'planes_{axis}_{coordinate:.6f}'
                    for order,entry in itertools.product(orders,entries):
                        route=propose(source,net,order,entry,detour,definitions,planes)
                        signature=tuple((f.face,f.u,f.v,f.depth,f.diameter,f.plugged) for f in route)
                        if signature in seen:continue
                        seen.add(signature)
                        options.append(dict(key=''.join('xyz'[i] for i in order)+':'+entry+':'+detour,
                            route=route,risk=proximity_risk(source,net,route,definitions,threads,cache),cost=route_cost(source,route)))
        catalogs[key]=options
        if len(catalogs)>32:catalogs.pop(next(iter(catalogs)))
    from copy import deepcopy
    return deepcopy(catalogs[key])


def port_approach_candidates(design,net,options,definitions,threads=None,modifiers=None):
    """Bounded terminal strategies, shared by global/local/layout proposals.

    Give each port and route family a turn; keep the existing 16 exact pruning
    slots. Explicit mode/index keys regenerate against the current source.
    """
    from collections import defaultdict
    groups=defaultdict(list)
    for option in options:
        # Coordinate-bound branches already define their terminal strategy.
        # They cannot be wrapped by the legacy port:<axis-order> grammar.
        if not option['key'].startswith(('simple_','port_','branch_','window:')):groups[_strategy_family(option['key'])].append(option)
    bases=[]
    for family in sorted(groups):
        bases.extend(sorted(groups[family],key=lambda o:(route_objective(design,o['route'],definitions=definitions),o['key']))[:2])
    ports=sorted((f for f in design.features if f.kind=='port' and not f.suppressed and f.id in net.members),key=lambda f:f.id)
    queues=[]
    for index,port in enumerate(ports):
        modes=[mode for mode in ('window','clear') if port_turn_depth(design,net,port,definitions,mode,threads,modifiers) is not None]
        queues.append(iter([f'port_{index}_{mode}:'+base['key'] for base in bases for mode in modes]))
    attempted=0
    while queues and attempted<48:
        active=[]
        for queue in queues:
            if attempted>=48:break
            try:key=next(queue)
            except StopIteration:continue
            active.append(queue);attempted+=1
            if len(key)>80:continue
            route=route_from_variant(design,net,key,definitions,threads,modifiers)
            if route is not None:yield key,route
        queues=active


def connection_topology_candidates(design,net,options,definitions,threads=None,modifiers=None):
    """Terminal-root trees plus one common junction; same pruning budget.

    A nearest-terminal MST fixes a cavity as a transit junction. A narrow source
    window may accept a terminating branch while correctly forbidding that
    through drilling. Try alternate trees without changing its stop/protection.
    """
    if len(net.members) not in (3,4):return
    groups={}
    for option in options:
        if option['key'].startswith(('simple_','tree_')):continue
        groups.setdefault(_strategy_family(option['key']),[]).append(option)
    bases=[]
    # Retain both entry directions: a terminating narrow-window cut may need
    # the farther entry face to reach its branch without passing the cavity.
    families=[f for f in ('axial','direct','detour','port-approach','axial-detour','coordinated-detour') if f in groups][:4]
    for family in families:
        ranked=sorted(groups[family],key=lambda o:(route_objective(design,o['route'],definitions=definitions),o['key']))
        entries=set();chosen=[]
        for option in ranked:
            entry=next(p for p in option['key'].split(':') if p in ('nearest','negative','positive'))
            if entry in entries:continue
            entries.add(entry);chosen.append(option)
        bases.extend((chosen+[o for o in ranked if o not in chosen])[:3])
    indices=range(5) if len(net.members)==4 else range(4)
    indices=list(indices)
    # Expose root AND common-junction strategies early, including to the cheap
    # 32-attempt layout sampler. All first-family slots must not be root zero.
    queues=[iter([f'tree_{index}:'+base['key'] for index in indices[i%len(indices):]+indices[:i%len(indices)]]) for i,base in enumerate(bases)]
    # Do not spend the topology family's slots on the existing MST under a new
    # name. Other terminal roots and the common junction must get those slots.
    seen={tuple(_feature_key(f) for f in option['route']) for option in options};attempted=0
    while queues and attempted<48:
        active=[]
        for queue in queues:
            if attempted>=48:break
            try:key=next(queue)
            except StopIteration:continue
            active.append(queue);attempted+=1
            if len(key)>80:continue
            route=route_from_variant(design,net,key,definitions,threads,modifiers)
            if route is None:continue
            signature=tuple(_feature_key(f) for f in route)
            if signature in seen:continue
            seen.add(signature);yield key,route
        queues=active


def source_entry_candidates(design,net,options,definitions,threads,modifiers,cache=None):
    """Bounded refinement of existing connection geometry, no layout movement."""
    # Refine multi-terminal trees without crowding the established two-terminal
    # axial/direct shortlist with equivalent mixed-entry adaptations.
    if len(net.members)<3:return
    groups={}
    for option in options:
        if option['key'].startswith(('simple_','safe:','branch_','window:')):continue
        groups.setdefault(_strategy_family(option['key']),[]).append(option)
    queues=[]
    for family in ('branch-topology','terminal-tree','axial','direct','port-approach','detour','axial-detour'):
        group=sorted(groups.get(family,[]),key=lambda o:(route_objective(design,o['route'],definitions=definitions),o['key']))
        seen=set();diverse=[];rest=[]
        for option in group:
            axis_order=next((p for p in option['key'].split(':') if len(p)==3 and sorted(p)==list('xyz')),'')
            strategy=(option['key'].split(':')[0],axis_order[0:1])
            (rest if strategy in seen else diverse).append(option);seen.add(strategy)
        if group:queues.append(iter(diverse+rest))
    count=0;seen=set()
    while queues and count<12:
        active=[]
        for queue in queues:
            if count>=12:break
            try:base=next(queue)
            except StopIteration:continue
            active.append(queue);count+=1;key='safe:'+base['key']
            if len(key)>80:continue
            route=route_from_variant(design,net,key,definitions,threads,modifiers,obstruction_cache=cache)
            if route is None:continue
            signature=tuple(_feature_key(f) for f in route)
            if signature in seen:continue
            seen.add(signature);yield key,route
        queues=active


def route_options(design, net, *, expanded=False, definitions=None,thread_definitions=None,modifier_definitions=None,
                  snapshot=None, seed=None,strategy_context=None):
    from copy import deepcopy
    net=effective_net(design,net)
    cache_key=(_routing_context_key(design,net),tuple(net.members),expanded,
               (seed['key'],tuple(f.model_dump_json() for f in seed['route'])) if seed else None,
               _routing_context_key(strategy_context,net) if strategy_context is not None else None)
    if snapshot is not None and cache_key in snapshot.options:
        return deepcopy(snapshot.options[cache_key])
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    if thread_definitions is None:
        from .engineering_db import thread_definitions_for_design
        thread_definitions=thread_definitions_for_design(design)
    if modifier_definitions is None:
        from .engineering_db import modifier_definitions_for_design
        modifier_definitions=modifier_definitions_for_design(design) if any(f.machining_modifiers for f in design.features) else {}
    snapshot=snapshot or _ProposalSnapshot(design,definitions,thread_definitions,modifier_definitions)
    snapshot.route_progress('access',net)
    source=snapshot.source
    catalog_key=(net.model_dump_json(exclude={'routing_variant'}),tuple(net.members),expanded)
    if catalog_key not in snapshot.catalogs:
        snapshot.catalogs[catalog_key]=route_candidate_catalog(source,net,definitions,thread_definitions,modifier_definitions,expanded=expanded,cache=snapshot.obstructions)
        from .branch_candidates import terminal_branch_candidates
        for key,route in terminal_branch_candidates(source,net,definitions,thread_definitions,modifier_definitions,snapshot.obstructions):
            snapshot.catalogs[catalog_key].append(dict(key=key,route=route,
                risk=proximity_risk(source,net,route,definitions,thread_definitions),cost=route_cost(source,route)))
    options=deepcopy(snapshot.catalogs[catalog_key])
    options.extend(coordinated_detours(source,net,strategy_context or design,definitions,thread_definitions,modifier_definitions,snapshot.obstructions))
    # Connector detours see actual retained automatic routes during local/repair
    # evaluation. Plane coordinates are explicit in the key, so saved variants
    # regenerate independently of these temporary obstacle contexts.
    connector_context=strategy_context or design
    if any(f.route_net and f.route_net!=net.id for f in connector_context.features):
        from .cavity_access import axial_connector_candidates
        known={option['key'] for option in options}
        for key,route in axial_connector_candidates(source,net,definitions,thread_definitions,modifier_definitions,connector_context,snapshot.obstructions):
            if key in known:continue
            options.append(dict(key=key,route=route,risk=proximity_risk(source,net,route,definitions,thread_definitions,snapshot.obstructions),cost=route_cost(source,route)))
    for key,route in port_approach_candidates(source,net,options,definitions,thread_definitions,modifier_definitions):
        options.append(dict(key=key,route=route,risk=proximity_risk(source,net,route,definitions,thread_definitions,snapshot.obstructions),cost=route_cost(source,route)))
    for key,route in connection_topology_candidates(source,net,options,definitions,thread_definitions,modifier_definitions):
        options.append(dict(key=key,route=route,risk=proximity_risk(source,net,route,definitions,thread_definitions,snapshot.obstructions),cost=route_cost(source,route)))
    for key,route in source_entry_candidates(source,net,options,definitions,thread_definitions,modifier_definitions,snapshot.obstructions):
        options.append(dict(key=key,route=route,risk=proximity_risk(source,net,route,definitions,thread_definitions,snapshot.obstructions),cost=route_cost(source,route)))
    from .closure_runtime import bind_route
    for option in options:option['route']=bind_route(design,option['route'])
    # Keep an explicitly failing proposal if the constraint makes every candidate impossible.
    # The validator reports the conflict; never remove a required connection to hide it.
    def source_clear(option):
        failures=route_obstructions(source,net,option['route'],thread_definitions,definitions,modifier_definitions,snapshot.obstructions)
        option['source_conflicts']=[list(f) for f in sorted(failures)]
        option['hard_failures']=len(failures)
        return not option['hard_failures']
    fixed_failures={}
    for option in options:
        if _strategy_family(option['key'])!='axial-detour':continue
        bores=[f for f in option['route'] if '-AX' in f.id]
        token=tuple(f.model_dump_json(exclude={'connects_to'}) for f in bores)
        if token not in fixed_failures:
            fixed_failures[token]=[list(f) for f in sorted(route_obstructions(design,net,bores,thread_definitions,definitions,modifier_definitions,snapshot.obstructions))]
        # No connector layout can repair an obstruction of this immutable bore.
        # Retain the failure for diagnostics, without spending pruning work on
        # an impossible local strategy or changing any protection threshold.
        option['fixed_failures']=len(fixed_failures[token])
        if fixed_failures[token]:option['source_conflicts']=fixed_failures[token]
    if not seed:
        for option in options:
            if option.get('fixed_failures'):option['hard_failures']=option['fixed_failures']
            else:source_clear(option)
    else:
        # A valid local seed permits lazy source screening in the SAME family /
        # Pareto queues. Invalid raw variants do not consume a family's quota.
        # Every shortlisted candidate is still fully screened before pruning.
        for option in options:option['hard_failures']=option.get('fixed_failures',0)
    def rank(option):
        failures={tuple(f) for f in option.get('conflicts',option.get('source_conflicts',[]))}
        if not option.get('connection_verified',False):failures.add(('connectivity',net.id))
        return (_conflict_objective(failures),option['hard_failures'],
                route_objective(design,option['route'],option['risk'],definitions),option['key'])
    permitted=[o for o in options if all(f.face not in design.constraints.forbidden_drilling_faces for f in o['route'])]
    options=sorted(permitted or options,key=rank)
    # Source-safe strategies first, then bounded family/Pareto opportunities.
    # Sibling construction routes are checked again AFTER redundant cuts have
    # gone; a temporary connector may disappear, but retained nets never move.
    clear_options=[option for option in options if not option['hard_failures'] and (not seed or option['key']!=seed['key'])]
    clear=_strategy_shortlist(source,clear_options,definitions,limit=16-bool(seed),eligible=source_clear if seed else None)
    # An empty raw clear pool is not proof that every final route is blocked:
    # redundant connector cuts can disappear after connectivity pruning. Give
    # failing strategy families the SAME unused 16-slot pruning opportunity.
    recover=expanded and not clear and not seed
    shortlist=clear or (_strategy_shortlist(source,options,definitions,limit=16) if recover else [])
    def simplify_options(candidates,recovery):
        for index,option in enumerate(candidates):
            snapshot.route_progress('connectivity',net,index,len(candidates))
            _verify_route_candidate(design,net,option,snapshot,known_failures=None if recovery else set())
            option['connectivity_recovery']=recovery
            option['metrics']=manufacturing_metrics(design,option['route'],option['risk'],definitions)
            snapshot.route_progress('connectivity',net,index+1,len(candidates))
    if shortlist:
        options=shortlist+[option for option in options if option['hard_failures'] and option not in shortlist]
        simplify_options(shortlist,recover)
        # Raw-clear is not connected-clear. If every screened candidate fails
        # connectivity, allow redundant-cut recovery within the UNUSED slots.
        remaining_budget=16-bool(seed)-len(shortlist)
        if expanded and not seed and remaining_budget>0 and not any(not o['hard_failures'] for o in shortlist):
            recovery=_strategy_shortlist(source,[o for o in options if o not in shortlist and not o.get('fixed_failures')],definitions,limit=remaining_budget)
            simplify_options(recovery,True)
    if seed:
        preserved=deepcopy(seed)
        _verify_route_candidate(design,net,preserved,snapshot)
        preserved['metrics']=manufacturing_metrics(design,preserved['route'],preserved['risk'],definitions)
        options.append(preserved)
    permitted = [o for o in options if all(f.face not in design.constraints.forbidden_drilling_faces for f in o['route'])]
    if not expanded and all(o['hard_failures'] for o in (permitted or options)):
        result=route_options(design,net,expanded=True,definitions=definitions,thread_definitions=thread_definitions,
                             modifier_definitions=modifier_definitions,snapshot=snapshot,strategy_context=strategy_context)
    else:result=sorted(permitted or options,key=rank)
    if snapshot is not None:snapshot.options[cache_key]=deepcopy(result)
    return result


def prune_branch_connectors(design,net,route,definitions,threads,modifiers,cache=None):
    """Cheap branch candidate preparation, NEVER a connectivity acceptance gate.

    Keep every cut that could touch a required source window. Only redundant
    connectors may go; witnessed contacts between inscribed fluid capsules
    keep those source branches together. Exact contacts/openings still verify
    every resulting candidate, including all source-terminal connections.
    """
    if not route:return route
    from .closure_runtime import bind_route
    route=bind_route(design,route)
    by_id={f.id:f for f in design.features};source_bounds=[]
    for member in net.members:
        owner,_,zone_id=member.partition(':');source=by_id.get(owner)
        if source is None:continue
        if zone_id:
            zone=next((z for z in definitions[source.definition].zones if z.id==zone_id),None)
            if zone is None:continue
            angle=math.radians(source.rotation)
            placed=source.model_copy(update=dict(u=source.u+zone.offset_u*math.cos(angle)-zone.offset_v*math.sin(angle),
                v=source.v+zone.offset_u*math.sin(angle)+zone.offset_v*math.cos(angle)))
            source_bounds.append(cylinder_bounds(placed,design.block,zone.start,zone.end,zone.diameter))
        else:
            source_bounds.extend(cylinder_bounds(c['feature'],design.block,c['start'],c['end'],2*max(c['radius_start'],c['radius_end']))
                for c in _manufacturing_cuts(source,definitions,threads or {},modifiers or {}))
    protected={a.id for a in net.construction_access}
    capsules={};graph={f.id:set() for f in route}
    for f in route:
        bounds=cylinder_bounds(f,design.block,0,segment_depth(f),f.diameter)
        if any(all(min(a[1],b[1])>max(a[0],b[0]) for a,b in zip(bounds,s)) for s in source_bounds):protected.add(f.id)
        radius=f.diameter/2;start=(f.plug_length if f.plugged else 0)+radius;end=f.depth-radius
        if end>start:capsules[f.id]=(*segment(f,design.block,start,end),radius)
    for a,b in itertools.combinations(capsules,2):
        aa,ab,ar=capsules[a];ba,bb,br=capsules[b]
        distance=segment_distance(aa,ab,ba,bb)
        # Overlap of two spheres inscribed in the full fluid cylinders is a
        # conservative lower bound. A near-tangent capsule contact must not
        # replace the sole connector that supplies the required opening.
        volume=0
        if distance<=abs(ar-br):volume=4*math.pi*min(ar,br)**3/3
        elif distance<ar+br:
            volume=math.pi*(ar+br-distance)**2*(distance**2+2*distance*(ar+br)-3*(ar-br)**2)/(12*distance)
        if volume>=max(design.rules.minimum_overlap_volume,1e-6):
            graph[a].add(b);graph[b].add(a)
    protected&=set(graph)
    if not protected:return route
    def reachable(active):
        visited=set();pending=[min(protected)]
        while pending:
            key=pending.pop()
            if key in visited:continue
            visited.add(key);pending.extend((graph[key]&active)-visited)
        return visited
    active=set(graph)
    if not protected<=reachable(active):return route
    failures=route_obstructions(design,net,route,threads,definitions,modifiers,cache)
    for f in sorted(route,key=lambda f:(-sum(f.id in failure[1:] for failure in failures),-f.depth,f.id)):
        if f.id in protected or f.route_net!=net.id or f.frozen_net:continue
        remaining=active-{f.id}
        if protected<=reachable(remaining):active=remaining
    return [f for f in route if f.id in active]


def route_from_variant(design, net, variant, definitions, threads=None, modifiers=None,*,obstruction_cache=None):
    net=effective_net(design,net)
    """Shared regeneration for global selection and incremental current templates."""
    entry_safe=variant.startswith('safe:')
    if entry_safe:variant=variant[5:]
    window_approach=variant.startswith('window:')
    if window_approach:variant=variant[7:]
    if variant.startswith('branch_'):
        design=_fixed_strategy_source(design)
        trunk,order,entry=variant.split(':')
        _,mask,*coordinates=trunk.split('_');junction=tuple(float(x) for x in coordinates)
        if sorted(order)!=list('xyz') or len(junction)!=3:return None
        overrides={};orders={}
        if window_approach:
            from .branch_candidates import face_window_points
            selected={m for i,m in enumerate(sorted(net.members)) if int(mask)&(1<<i)}
            overrides={m:p for m,p in face_window_points(design,net,definitions,threads or {},modifiers or {}).items() if m not in selected}
            base=tuple('xyz'.index(i) for i in order);by_id={f.id:f for f in design.features}
            orders={m:(base[1],base[0],base[2]) if FACE_AXES[by_id[m.split(':')[0]].face][2]==base[0] else base for m in overrides}
        if int(mask):
            from .cavity_access import axial_route
            route=axial_route(design,net,definitions,f'axial_{int(mask)}_0:'+order+':'+entry,
                threads=threads,modifiers=modifiers,entry_safe=True,obstruction_cache=obstruction_cache,junction_override=junction,
                terminal_overrides=overrides,terminal_orders=orders)
        else:
            route=propose(design,net,tuple('xyz'.index(i) for i in order),entry,definitions=definitions,
                entry_safe=True,thread_definitions=threads,modifier_definitions=modifiers,obstruction_cache=obstruction_cache,junction_override=junction,
                terminal_overrides=overrides,terminal_orders=orders)
        return prune_branch_connectors(design,net,route,definitions,threads,modifiers,obstruction_cache) if route is not None else None
    connection_topology=None
    if variant.startswith('tree_'):
        topology,variant=variant.split(':',1)
        connection_topology=int(topology.split('_')[1])
    port_approaches=None
    if variant.startswith('port_'):
        approach,variant=variant.split(':',1)
        _,index,mode=approach.split('_')
        ports=sorted((f for f in design.features if f.kind=='port' and not f.suppressed and f.id in net.members),key=lambda f:f.id)
        if int(index)>=len(ports):return None
        port=ports[int(index)]
        depth=port_turn_depth(design,net,port,definitions,mode,threads,modifiers)
        if depth is None:return None
        port_approaches={port.id:depth}
    if variant.startswith('axial_'):
        from .cavity_access import axial_route
        return axial_route(design,net,definitions,variant,threads=threads,modifiers=modifiers,port_approaches=port_approaches,connection_topology=connection_topology,entry_safe=entry_safe,obstruction_cache=obstruction_cache)
    if variant.startswith('simple_'):
        if port_approaches is not None or connection_topology is not None or entry_safe:return None
        templates = simple_routes(design,net,definitions)
        index = int(variant.split('_')[1])
        return templates[index] if index < len(templates) else None
    order,entry,detour = variant.split(':')
    if sorted(order) != ['x','y','z']:
        raise ValueError('Routing variant must use each axis once')
    return propose(design,net,tuple('xyz'.index(i) for i in order),entry,detour,definitions,port_approaches=port_approaches,connection_topology=connection_topology,entry_safe=entry_safe,thread_definitions=threads,modifier_definitions=modifiers,obstruction_cache=obstruction_cache)


def resize_route(design, net, option, diameter, definitions, threads=None, modifiers=None):
    # Axial stop depth includes the real radius/tip/contact requirement. A larger
    # selected tool must regenerate it; changing only diameter could cut a seat.
    option['connection_verified']=False
    option.pop('_connectivity_geometry',None)
    option.pop('_connectivity_conditions',None)
    option.pop('admission',None)
    option.pop('connectivity_detail',None)
    if option['key'].startswith(('axial_','port_','tree_','safe:','branch_','window:')):
        sized = net.model_copy(update=dict(diameter=diameter))
        route = route_from_variant(design,sized,option['key'],definitions,threads,modifiers)
        if route is None:raise ValueError(f'{net.id}: selected drill has no safe terminal approach')
        option['route'] = route
    else:
        for feature in option['route']:feature.diameter=diameter


def _route_pool(source,net,snapshot,*,expanded=False,strategy_context=None):
    """Source-safe simplified strategies, with the normal flow/tool sizing loop."""
    from copy import deepcopy
    net=effective_net(source,net)
    key=(_routing_context_key(source,net),expanded,_routing_context_key(strategy_context,net) if strategy_context is not None else None)
    if key not in snapshot.pools:
        from .sizing import route_sizing
        options=route_options(source,net,expanded=expanded,definitions=snapshot.definitions,
            thread_definitions=snapshot.threads,modifier_definitions=snapshot.modifiers,snapshot=snapshot,strategy_context=strategy_context)
        usable=[]
        for index,option in enumerate(options):
            if option['hard_failures']:continue
            option=deepcopy(option)
            options[index]=option
            try:
                if net.flow_lpm:
                    if snapshot.tools is None:
                        from .engineering_db import tool_definitions
                        snapshot.tools=tool_definitions('drill')
                    for _ in range(12):
                        from .geometry import tip_depth
                        depth=max((f.depth+tip_depth(f) for f in option['route']),default=0)
                        sizing_key=(net.model_dump_json(exclude={'routing_variant'}),depth,source.project_context)
                        if sizing_key not in snapshot.sizing:
                            snapshot.sizing[sizing_key]=route_sizing(net,tools=snapshot.tools,required_depth=depth,preferred_unit=source.project_context)
                        size=snapshot.sizing[sizing_key]
                        if all(abs(f.diameter-size['diameter_mm'])<1e-9 for f in option['route']):break
                        resize_route(source,net,option,size['diameter_mm'],snapshot.definitions,snapshot.threads,snapshot.modifiers)
                    else:continue
                    option['tool_sizing']=size
                # Flow determines sizing, never whether connectivity is checked.
                # Every admitted final contour has its own exact fluid proof.
                if not _verify_route_candidate(source,net,option,snapshot):continue
                usable.append(option)
            except ValueError:
                option.update(connection_verified=False,hard_failures=max(1,option.get('hard_failures',0)),
                              conflicts=[['candidate_geometry_error',net.id]])
                continue
        snapshot.pools[key]=sorted(usable,key=lambda o:(route_objective(source,o['route'],o['risk'],snapshot.definitions),o['key']))
        from collections import Counter
        snapshot.pool_diagnostics[net.id]=dict(retained_clear=len(usable),considered=len(options),
            geometry_errors=[r for r in snapshot.cad_error_records if r['net_id']==net.id][-8:],
            connectivity_candidates=[dict(variant=o['key'],admission=o.get('admission',{}),detail=o['connectivity_detail']) for o in options if 'connectivity_detail' in o],
            rejected_candidates=[dict(variant=o['key'],failures=o.get('conflicts',o.get('source_conflicts',[]))) for o in options if o['hard_failures']][:16],
            rejected_rules=dict(Counter(f[0] for o in options if o['hard_failures'] for f in o.get('conflicts',o.get('source_conflicts',[])))))
        snapshot.route_progress('connectivity',net,finished=True)
    return deepcopy([o for o in snapshot.pools[key] if _candidate_admitted(o,net)])


def _route_pair_failures(source,a,ao,b,bo,snapshot,budget):
    first=(a.id,tuple(_feature_key(f) for f in ao['route']))
    second=(b.id,tuple(_feature_key(f) for f in bo['route']))
    key=tuple(sorted((first,second)))
    if key not in snapshot.pair_failures:
        if budget['used']>=budget.get('limit',4000):
            # Unknown compatibility is never admitted as a clear combination.
            return {('search_budget',a.id,b.id)}
        budget['used']+=1
        context=source.model_copy(update=dict(features=ao['route']+bo['route']))
        snapshot.pair_failures[key]=frozenset(
            route_obstructions(context,a,ao['route'],snapshot.threads,snapshot.definitions,snapshot.modifiers,snapshot.obstructions)|
            route_obstructions(context,b,bo['route'],snapshot.threads,snapshot.definitions,snapshot.modifiers,snapshot.obstructions))
        if len(snapshot.pair_failures)>8192:snapshot.pair_failures.pop(next(iter(snapshot.pair_failures)))
    return set(snapshot.pair_failures[key])


def _conflict_objective(failures):
    protected={'source_protected','source_wall'}
    cross={'cross_net_wall'}
    connectivity={'connectivity'}
    return (sum(f[0] in connectivity for f in failures),sum(f[0] in cross for f in failures),
            sum(f[0] in protected for f in failures),
            sum(f[0] not in protected|cross|connectivity for f in failures),len(failures))


def _progressive_route_repair(target,selected,eligible,snapshot,*,expanded=True,unconnected=()):
    """A count-bounded beam of complete layouts; partial repairs stay unapproved.

    Search uses source-safe pools and cached symmetric pair conflicts. Every
    state includes ALL active routes, including unchanged/manual/frozen cuts.
    Up to 256 analytic states and 4000 pair screens; no extra exact CAD attempts.
    """
    from copy import deepcopy
    eligible={n.id for n in target.nets if n.id in eligible and n.routing=='automatic'
              and not any(f.frozen_net==n.id for f in target.features)}
    if not eligible:return []
    source=target.model_copy(deep=True)
    source.features=[f for f in source.features if f.route_net not in eligible]
    nets={n.id:effective_net(target,n) for n in target.nets if n.id in eligible}
    pools={}
    baseline={name:dict(key=selected[name],route=[f for f in target.features if f.route_net==name and not f.suppressed]) for name in sorted(eligible)}
    changed=False
    for name,option in baseline.items():
        before=tuple(_feature_key(f) for f in option['route'])
        _verify_route_candidate(source,nets[name],option,snapshot)
        changed|=before!=tuple(_feature_key(f) for f in option['route'])
    source_key=_routing_context_key(source);pair_budget={'used':0}
    def signature(state):return tuple((name,o.get('connection_verified',False),o.get('admission',{}).get('flow_opening_adequate'),tuple(_feature_key(f) for f in o['route'])) for name,o in sorted(state.items()))
    def evaluate(state):
        key=(source_key,signature(state))
        if key not in snapshot.repair_states:
            failures=set()
            for name,option in state.items():
                failures.update(route_obstructions(source,nets[name],option['route'],snapshot.threads,snapshot.definitions,snapshot.modifiers,snapshot.obstructions))
                facts=option.get('admission',{})
                if not option.get('connection_verified',False) or not facts.get('all_fluid_nodes_connected',False):failures.add(('connectivity',name))
                if option.get('admission',{}).get('flow_opening_adequate') is False:failures.add(('flow_opening',name))
            for a,b in itertools.combinations(sorted(state),2):
                failures.update(_route_pair_failures(source,nets[a],state[a],nets[b],state[b],snapshot,pair_budget))
            route=[f for o in state.values() for f in o['route']]
            if len(source.features)+len(route)>120:failures.add(('feature_budget',))
            value=(_conflict_objective(failures),frozenset(failures),route_objective(source,route,definitions=snapshot.definitions))
            if any(f[0]=='search_budget' for f in failures):return value
            snapshot.repair_states[key]=value
        return snapshot.repair_states[key]
    initial=evaluate(baseline)
    if not initial[1]:return [(initial,baseline)] if changed else []
    for name,net in sorted(nets.items()):
        pools[name]=[o for o in _route_pool(source,net,snapshot,expanded=expanded,strategy_context=target) if _candidate_admitted(o,net)]
        # Current geometry is retained as a state even when it has conflicts;
        # it does not become a newly admitted source-safe strategy.
    diverse={name:_strategy_shortlist(source,pool,snapshot.definitions,limit=len(pool)) for name,pool in pools.items()}
    frontier=[(initial,baseline,False)];seen={signature(baseline)};improvements=[];states=1;plateau_states=0
    history=[initial[0]]
    from .timing import progress
    while frontier and states<256:
        next_frontier=[]
        for (objective,failures,_),state,plateau_used in frontier:
            by_id={f.id:name for name,o in state.items() for f in o['route']}
            owners={by_id[item] for failure in failures for item in failure[1:] if item in by_id}
            owners.update(item for failure in failures for item in failure[1:] if item in eligible)
            # Round-robin strategies across implicated nets, so a large pool on
            # the first net cannot consume the entire repair budget.
            queues={name:list(diverse[name]) for name in sorted(owners)}
            start_states=states
            local_strict=False
            batch_limit=64 if len(frontier)==1 else 16
            while any(queues.values()) and states<256 and states-start_states<batch_limit:
                for name,queue in queues.items():
                    if not queue or states>=256 or states-start_states>=batch_limit:continue
                    option=queue.pop(0)
                    trial={**state,name:option};sig=signature(trial)
                    if sig in seen:continue
                    seen.add(sig);states+=1
                    score=evaluate(trial)
                    if any(f[0]=='search_budget' for f in score[1]):continue
                    if score[0]<objective:
                        next_frontier.append((score,trial,False));local_strict=True
                        if score[0]<initial[0]:improvements.append((score,trial))
                    elif score[0]==objective and not plateau_used and failures-score[1]:
                        # One equal-conflict lookahead may relocate an actual
                        # obstruction so the next implicated net can clear it.
                        # It is NEVER returned as an improvement on its own.
                        next_frontier.append((score,trial,True));plateau_states+=1
            if not local_strict and states<256:
                # Escape a strict one-net local minimum with coordinated moves.
                # Both options remain source-safe; complete-layout scoring is
                # required before the pair can enter the beam.
                for a,b in itertools.combinations(sorted(owners),2):
                    for ao,bo in itertools.product(diverse[a][:3],diverse[b][:3]):
                        if states>=256 or states-start_states>=batch_limit+24:break
                        trial={**state,a:ao,b:bo};sig=signature(trial)
                        if sig in seen:continue
                        seen.add(sig);states+=1;score=evaluate(trial)
                        if any(f[0]=='search_budget' for f in score[1]):continue
                        if score[0]>=objective:continue
                        next_frontier.append((score,trial,False))
                        if score[0]<initial[0]:improvements.append((score,trial))
                    if states>=256 or states-start_states>=batch_limit+24:break
        if not next_frontier:break
        next_frontier.sort(key=lambda row:(row[0][0],row[0][2],signature(row[1])))
        strict=[row for row in next_frontier if not row[2]]
        plateau=[row for row in next_frontier if row[2]]
        frontier=(strict[:3]+plateau[:1]) if plateau and (not strict or strict[0][0][1]) else strict[:4]
        history.append(frontier[0][0][0]);progress('repair',12)
        if not frontier[0][0][1]:break
    best_score,best_state=min(improvements,key=lambda row:(row[0][0],row[0][2],signature(row[1]))) if improvements else (initial,baseline)
    exit_reason=('clear_combination' if not best_score[1] else 'pair_budget' if pair_budget['used']>=4000 else
                 'state_budget' if states>=256 else 'bounded_neighbourhood_exhausted')
    from collections import Counter
    diagnostic=dict(states=states,state_limit=256,pair_screens=pair_budget['used'],pair_limit=4000,
        conflict_history=history,plateau_states=plateau_states,exit_reason=exit_reason,
        pools={name:dict(count=len(pool),families=dict(Counter(_strategy_family(o['key']) for o in pool))) for name,pool in pools.items()},
        selected={name:o['key'] for name,o in best_state.items()},remaining_conflicts=[list(f) for f in sorted(best_score[1])][:64])
    snapshot.repair_diagnostics.append(diagnostic)
    from .timing import diagnostic as record_diagnostic
    record_diagnostic('route_repair',diagnostic)
    improvements.sort(key=lambda row:(row[0][0],row[0][2],signature(row[1])))
    unique=[];variants=set()
    for score,state in improvements:
        key=tuple((name,o['key']) for name,o in sorted(state.items()))
        if key in variants:continue
        variants.add(key);unique.append((score,deepcopy(state)))
        if len(unique)==4:break
    return unique


def select_route_combination(source,nets,pools,definitions,pair_failures,*,pair_count=lambda:0,excluded=None,state_limit=1000,pair_limit=4000):
    """Bounded compatibility/objective search over supplied pools.

    This function approves NO candidate. Exact routing passes admitted pools;
    AI layout screening passes analytic pools and keeps its unvalidated status.
    """
    states=0;best=None;best_key=None;dead_ends=0;budget_blocked=False
    def combination_key(chosen):
        route=[f for option in chosen.values() for f in option['route']]
        return (route_objective(source,route,sum(o.get('risk',0) for o in chosen.values()),definitions),
                tuple(route_objective(source,o['route'],o.get('risk',0),definitions) for _,o in sorted(chosen.items())),
                tuple((name,o['key']) for name,o in sorted(chosen.items())))
    minimum={name:dict(plugs=min(sum(f.plugged for f in o['route']) for o in pool),
        count=min(len(o['route']) for o in pool),maximum=min(max((f.depth for f in o['route']),default=0) for o in pool),
        total=min(sum(f.depth for f in o['route']) for o in pool)) for name,pool in pools.items() if pool}
    def lower_bound(chosen,remaining):
        route=[f for option in chosen.values() for f in option['route']];rest=[minimum[n] for n in remaining]
        plugs=sum(f.plugged for f in route)+sum(m['plugs'] for m in rest)
        count=len(route)+sum(m['count'] for m in rest)
        maximum=max([f.depth for f in route]+[m['maximum'] for m in rest],default=0)
        total=sum(f.depth for f in route)+sum(m['total'] for m in rest)
        if source.constraints.priority=='fewer_plugs':return (plugs,count,maximum,total)
        if source.constraints.priority=='short_drills':return (maximum,total,count,plugs)
        if source.constraints.priority=='simple_machining':return (count,len({f.face for f in route}),plugs,total)
        return (0,0,count,plugs,total)
    def pair_clear(a,ao,b,bo):
        nonlocal budget_blocked
        failures=pair_failures(a,ao,b,bo)
        if any(f[0]=='search_budget' for f in failures):budget_blocked=True
        return not failures
    def search(chosen,remaining):
        nonlocal states,best,best_key,dead_ends
        if states>=state_limit or budget_blocked:return
        states+=1
        bound=lower_bound(chosen,remaining)
        if best_key and bound>best_key[0][:len(bound)]:return
        if not remaining:
            if excluded and tuple(sorted((n,o['key']) for n,o in chosen.items())) in excluded:return
            if len(source.features)+sum(len(o['route']) for o in chosen.values())>120:return
            key=combination_key(chosen)
            if best_key is None or key<best_key:best,best_key=dict(chosen),key
            return
        # Reject a branch as soon as ANY remaining net loses its last clear
        # choice; alphabetical traversal used to discover this only at the end.
        domains={}
        for name in sorted(remaining,key=lambda n:(len(pools[n]),n)):
            domains[name]=[o for o in pools[name] if all(pair_clear(prior,po,name,o) for prior,po in chosen.items())]
            if budget_blocked:return
            if not domains[name]:dead_ends+=1;return
        name=min(domains,key=lambda n:(len(domains[n]),-len(nets[n].members),n))
        for option in domains[name]:
            search({**chosen,name:option},remaining-{name})
            if states>=state_limit or budget_blocked:break
    empty=sorted(name for name,pool in pools.items() if not pool)
    if not empty:search({},set(nets))
    # Keep global objective ordering after feasibility; cached compatible moves
    # can still improve a complete result without raising either search budget.
    if best:
        for _ in range(len(nets)):
            improved=False
            for name in sorted(nets,key=lambda n:(len(pools[n]),n)):
                for option in pools[name]:
                    if not all(pair_clear(other,po,name,option) for other,po in best.items() if other!=name):continue
                    trial={**best,name:option}
                    if excluded and tuple(sorted((n,o['key']) for n,o in trial.items())) in excluded:continue
                    key=combination_key(trial)
                    if key<best_key:best,best_key=trial,key;improved=True
                    if budget_blocked:break
                if budget_blocked:break
            if not improved or budget_blocked:break
    reason=('no_retained_source_safe_candidate' if empty else 'pair_budget' if budget_blocked else
            'state_budget' if states>=state_limit else 'clear_combination' if best else 'retained_pools_incompatible')
    diagnostic=dict(states=states,state_limit=state_limit,pair_screens=pair_count(),pair_limit=pair_limit,
        dead_ends=dead_ends,exit_reason=reason,empty_nets=empty,pools={n:len(p) for n,p in pools.items()},
        selected={n:o['key'] for n,o in best.items()} if best else {})
    return best,diagnostic


def _complete_route_combination(design, definitions, thread_definitions, modifier_definitions, snapshot=None, net_ids=None, deadline=None, excluded=None,*,state_limit=1000,pair_limit=4000):
    """Bounded, most-constrained-first global routing with forward checking."""
    nets={n.id:effective_net(design,n) for n in design.nets if n.routing=='automatic' and
          (n.route_state=='unresolved' if net_ids is None else n.id in net_ids)}
    if len(nets)<2 or any(n.routing_variant for n in nets.values()):return None
    source=design.model_copy(update=dict(features=[f for f in design.features if f.route_net not in nets]))
    snapshot=snapshot or _ProposalSnapshot(source,definitions,thread_definitions,modifier_definitions)
    state_limit=min(state_limit,max(0,1000-sum(r.get('states',0) for r in snapshot.combination_diagnostics)))
    pools={name:[o for o in _route_pool(source,net,snapshot) if _candidate_admitted(o,net)][:24] for name,net in sorted(nets.items())}
    snapshot.route_progress('global_conflicts')
    pair_budget=snapshot.combination_budget
    pair_budget['limit']=pair_limit
    best,diagnostic=select_route_combination(source,nets,pools,definitions,
        lambda a,ao,b,bo:_route_pair_failures(source,nets[a],ao,nets[b],bo,snapshot,pair_budget),
        pair_count=lambda:pair_budget['used'],excluded=excluded,state_limit=state_limit,pair_limit=pair_limit)
    pair_budget['limit']=4000
    diagnostic['pools']=dict(snapshot.pool_diagnostics)
    snapshot.combination_diagnostics.append(diagnostic)
    from .timing import diagnostic as record_diagnostic
    record_diagnostic('route_combination',diagnostic)
    return best


def _coordinated_fallback(source,automatic,snapshot):
    """Best-effort COMPLETE seed, never an admission of conflicting geometry.

    Clear constrained nets claim corridors first. Nets without a retained clear
    candidate are considered last and keep their actual unresolved failures.
    """
    nets={n.id:effective_net(source,n) for n in source.nets if n.id in automatic}
    pools={name:[o for o in _route_pool(source,net,snapshot) if _candidate_admitted(o,net)] for name,net in sorted(nets.items())}
    order=sorted(nets,key=lambda n:(not bool(pools[n]),len(pools[n]),-len(nets[n].members),n))
    chosen={};pair_budget=snapshot.combination_budget
    for name in order:
        net=nets[name]
        options=pools[name] or route_options(source,net,expanded=True,definitions=snapshot.definitions,
            thread_definitions=snapshot.threads,modifier_definitions=snapshot.modifiers,snapshot=snapshot)
        if not pools[name]:options=_strategy_shortlist(source,options,snapshot.definitions,limit=16)
        ranked=[]
        for option in options:
            failures=route_obstructions(source,net,option['route'],snapshot.threads,snapshot.definitions,snapshot.modifiers,snapshot.obstructions)
            if not option.get('connection_verified',False):failures.add(('connectivity',name))
            for prior,po in chosen.items():
                failures.update(_route_pair_failures(source,nets[prior],po,net,option,snapshot,pair_budget))
            ranked.append((_conflict_objective(failures),route_objective(source,option['route'],option.get('risk',0),snapshot.definitions),option['key'],option))
        if not ranked:return None,order
        chosen[name]=min(ranked,key=lambda row:row[:3])[3]
    return chosen,order


def _proposal_source_key(design):
    # Variants choose construction proposals; they do not alter source geometry.
    # Reuse its BRep/catalog/pruning caches across bounded exact attempts.
    from .route_state import pending_nets
    automatic=pending_nets(design)
    source=design.model_copy(update=dict(features=[f for f in design.features if f.route_net not in automatic]))
    return source.model_dump_json(exclude={'nets':{'__all__':{'routing_variant'}}})


@timed('route.proposal')
def _resolve_proposals(design, *, snapshots=None):
    from .route_state import pending_nets,route_metadata
    if not pending_nets(design):
        target=resolve_parents(design.model_copy(deep=True))
        return target,route_metadata(target)
    authored=design
    inherited={n.id:{k:getattr(n,k) for k in ("pressure_bar","flow_lpm","velocity_limit","drilling_mode")} for n in design.nets}
    design=design.model_copy(deep=True)
    design.nets=[effective_net(design,n) for n in design.nets]
    signature=_proposal_source_key(authored)
    resolved = resolve_parents(design)
    from .engineering_db import definitions_for_design,thread_definitions_for_design,modifier_definitions_for_design,tool_definitions
    snapshots=snapshots if snapshots is not None else {}
    previous=snapshots.get(signature)
    definitions=previous.definitions if previous else definitions_for_design(resolved)
    thread_definitions=previous.threads if previous else thread_definitions_for_design(resolved)
    modifier_definitions=previous.modifiers if previous else modifier_definitions_for_design(resolved) if any(f.machining_modifiers for f in resolved.features) else {}
    from .sizing import route_sizing
    from .route_state import pending_nets,route_metadata
    automatic=pending_nets(resolved)
    sizing={}
    tools=previous.tools if previous and previous.tools is not None else tool_definitions('drill')
    size_cache=previous.sizing if previous else {}
    def sized(net,depth=0):
        key=(net.model_dump_json(exclude={'routing_variant'}),depth,resolved.project_context)
        if key not in size_cache:size_cache[key]=route_sizing(net,tools=tools,required_depth=depth,preferred_unit=resolved.project_context)
        return size_cache[key]
    sizing={n.id:sized(n) for n in resolved.nets if n.id in automatic}
    for net in resolved.nets:
        if net.id in automatic:net.diameter=sizing[net.id]['diameter_mm']
    resolved.features = [f for f in resolved.features if f.route_net not in automatic]
    if signature not in snapshots:
        snapshots[signature]=_ProposalSnapshot(resolved,definitions,thread_definitions,modifier_definitions)
    snapshot=snapshots[signature]
    snapshot.tools=tools;snapshot.sizing=size_cache
    # Multi-net layouts commonly need a paired move. Build their independent
    # pools once instead of first exhausting a conflicting greedy layout and
    # then rebuilding the same pools for the bounded combination search.
    combination = (_complete_route_combination(resolved,definitions,thread_definitions,modifier_definitions,snapshot,state_limit=128,pair_limit=512)
                   if len(automatic)>2 else None)
    if not combination and len(automatic)>2 and not any(n.routing_variant for n in resolved.nets if n.id in automatic):
        from .drilling_planner import coordinate_routes,materialized_proposal
        seeds={}
        for n in resolved.nets:
            if n.id not in automatic:continue
            pool=_route_pool(resolved,n,snapshot)
            if pool:seeds[n.id]=pool[0]
        planned,detail=coordinate_routes(resolved,[n for n in resolved.nets if n.id in automatic],definitions,thread_definitions,modifier_definitions,
            seeds=seeds,snapshot=snapshot,state_limit=max(0,1000-sum(r.get('states',0) for r in snapshot.combination_diagnostics)),
            pair_limit=max(0,4000-snapshot.combination_budget['used']))
        if planned:return materialized_proposal(authored,planned,detail)
    seed=None;seed_order=[]
    if not combination and len(automatic)>2 and not any(n.routing_variant for n in resolved.nets if n.id in automatic):
        seed,seed_order=_coordinated_fallback(resolved,automatic,snapshot)
    candidates = []
    sequence={name:i for i,name in enumerate(seed_order)}
    for net in sorted(resolved.nets,key=lambda n:(sequence.get(n.id,len(sequence)),n.id)):
        if net.id not in automatic:
            continue
        def tool_size(option,context=resolved):
            if not net.flow_lpm:return sizing[net.id]
            actual=None
            for _ in range(12):
                required_depth=max((f.depth + (0 if f.tip_angle==180 else f.diameter/2/math.tan(math.radians(f.tip_angle/2)))
                                    for f in option['route']),default=0)
                actual=sized(net,required_depth)
                if all(abs(f.diameter-actual['diameter_mm'])<=1e-9 for f in option['route']):break
                resize_route(context,net,option,actual['diameter_mm'],definitions,thread_definitions,modifier_definitions)
            else:
                raise ValueError(f'{net.id}: route sizing did not settle on a source-backed drill')
            option['tool_sizing']=actual
            _verify_route_candidate(context,net,option,snapshot)
            return actual
        # Pinned candidates are materialized directly; enumerating their entire
        # neighbourhood again would multiply the cost of each exact attempt.
        choices = ([combination[net.id]] if combination else [seed[net.id]] if seed else [] if net.routing_variant else
                   route_options(resolved,net,definitions=definitions,thread_definitions=thread_definitions,
                                 modifier_definitions=modifier_definitions,snapshot=snapshot))
        if net.routing_variant:
            if net.routing_variant.startswith(('axial_','port_','tree_','safe:','branch_','window:')):
                route=route_from_variant(resolved,net,net.routing_variant,definitions,thread_definitions,modifier_definitions)
                if route is None:
                    choices=route_options(resolved,net,definitions=definitions,thread_definitions=thread_definitions,
                                          modifier_definitions=modifier_definitions,snapshot=snapshot)
                    selected=choices[0]
                    route=selected['route']
                else:
                    selected=dict(key=net.routing_variant,route=route,risk=proximity_risk(resolved,net,route,definitions,thread_definitions),cost=route_cost(resolved,route))
            elif net.routing_variant.startswith('simple_'):
                choices=[dict(key=f'simple_{i}',route=r,risk=proximity_risk(resolved,net,r,definitions,thread_definitions),cost=route_cost(resolved,r))
                         for i,r in enumerate(simple_routes(resolved,net,definitions))]
                selected=next((o for o in choices if o['key']==net.routing_variant),None)
                if selected is None:
                    choices=route_options(resolved,net,definitions=definitions,thread_definitions=thread_definitions,
                                          modifier_definitions=modifier_definitions,snapshot=snapshot)
                    selected=choices[0]  # Moved/reassigned terminals invalidate the old proposal.
                route=selected['route']
            else:
                order,entry,detour = net.routing_variant.split(':')
                if sorted(order) != ['x','y','z']:
                    raise ValueError('Routing variant must use each axis once')
                route = propose(resolved,net,tuple('xyz'.index(i) for i in order),entry,detour,definitions)
                selected = dict(key=net.routing_variant,route=route,risk=proximity_risk(resolved,net,route,definitions,thread_definitions),cost=route_cost(resolved,route))
        else:
            if net.flow_lpm:
                usable=[];errors=[]
                for option in choices:
                    try:tool_size(option);usable.append(option)
                    except ValueError as exc:errors.append(exc)
                if not usable:raise errors[0]
                choices=sorted(usable,key=lambda o:(o['hard_failures'],
                               route_objective(resolved,o['route'],o['risk'],definitions),o['key']))
            selected = choices[0]
            route = selected['route']
        if net.flow_lpm:
            # Tool reach uses the actual candidate depth. Unreachable candidates are excluded before
            # ranking; pinned variants fail clearly instead of silently changing.
            actual=selected.get('tool_sizing') or tool_size(selected)
            net.diameter=actual['diameter_mm']
            sizing[net.id]=actual
            route=selected['route']
        # Pinned, fallback, sized and unknown-flow paths all share this final
        # gate. Binding/sizing cannot carry a proof from a different contour.
        selected['route']=route
        _verify_route_candidate(resolved,net,selected,snapshot)
        route=selected['route']
        resolved.features.extend(route)
        if len(resolved.features) > 120:
            raise ValueError('Generated design exceeds 120 physical features; reduce routing complexity')
        candidates.append(dict(net=net.id, axis_order=selected['key'].split(':')[0], variant=selected['key'], proximity_risk=selected['risk'],
                               objective=route_objective(resolved,route,selected['risk'],definitions),
                               pruned_drillings=selected.get('pruned_ids',[]),
                               sizing=sizing[net.id],
                               connection_verified=selected.get('connection_verified',False),
                               admission=selected.get('admission',{}),connectivity_detail=selected.get('connectivity_detail',{}),
                               **route_margin(design,route),
                               candidates=max(1,len(choices)), drillings=len(route), plugs=sum(f.plugged for f in route),
                               length_mm=round(sum(f.depth for f in route),2), status='PROPOSAL_REQUIRES_EXACT_VALIDATION'))
    if len(automatic)<=2 and any(route_obstructions(resolved,n,[f for f in resolved.features if f.route_net==n.id],
                              thread_definitions,definitions,modifier_definitions)
           for n in resolved.nets if n.id in automatic):
        combination = _complete_route_combination(resolved,definitions,thread_definitions,modifier_definitions,snapshot)
        if combination:
            resolved.features = [f for f in resolved.features if f.route_net not in automatic]
            for net in sorted((n for n in resolved.nets if n.id in automatic),key=lambda n:n.id):
                option = combination[net.id]
                route = option['route']
                resolved.features.extend(route)
                metadata = next(r for r in candidates if r['net']==net.id)
                metadata.update(variant=option['key'],axis_order=option['key'].split(':')[0],
                                connection_verified=option.get('connection_verified',False),
                                admission=option.get('admission',{}),connectivity_detail=option.get('connectivity_detail',{}),
                                proximity_risk=option['risk'],drillings=len(route),
                                plugs=sum(f.plugged for f in route),
                                length_mm=round(sum(f.depth for f in route),2),
                                **route_margin(design,route))
    # Complete-layout progressive repair is shared by global proposals, local
    # conflict expansion and authoritative exact search. Pinned alternatives,
    # committed/manual/frozen geometry are never silently moved here.
    mutable={n.id for n in resolved.nets if n.id in automatic and not n.routing_variant}
    selected={r['net']:r['variant'] for r in candidates}
    # Expand geometry before spending another template-only repair search.
    # Existing stored/frozen/manual cuts and explicit variants stay obstacles.
    failed=any(not row.get('connection_verified') or row.get('hard_failures',0) or
        row.get('admission',{}).get('direct_contact_adequate') is False for row in candidates)
    failed=failed or any(route_obstructions(resolved,n,[f for f in resolved.features if f.route_net==n.id],
        thread_definitions,definitions,modifier_definitions,snapshot.obstructions) for n in resolved.nets if n.id in mutable)
    corridor_diagnostic=getattr(snapshot,'corridor_last',None)
    if failed and mutable and corridor_diagnostic is None:
        from .drilling_planner import coordinate_routes,candidate,materialized_proposal
        source=resolved.model_copy(deep=True)
        for n in source.nets:
            if n.id in mutable:n.route_state='unresolved';n.routing_variant=None
        seeds={n:candidate([f for f in resolved.features if f.route_net==n]) for n in mutable}
        planned,corridor_diagnostic=coordinate_routes(source,[n for n in source.nets if n.id in mutable],definitions,thread_definitions,modifier_definitions,
            seeds=seeds,snapshot=snapshot,state_limit=max(0,1000-sum(r.get('states',0) for r in snapshot.combination_diagnostics)),
            pair_limit=max(0,4000-snapshot.combination_budget['used']))
        if planned:
            ready,rows=materialized_proposal(authored,planned,corridor_diagnostic)
            # Keep any pinned or immutable automatic proposal outside the group.
            ready.features.extend(f.model_copy(deep=True) for f in resolved.features if f.route_net in automatic-mutable)
            for n in ready.nets:
                if n.id not in automatic-mutable:continue
                row=next(r for r in candidates if r['net']==n.id)
                facts=row.get('admission',{})
                safe=(row.get('connection_verified') and facts.get('source_obstruction_safe') and
                      facts.get('all_fluid_nodes_connected') and facts.get('direct_contact_adequate') and
                      facts.get('flow_opening_adequate') is not False and not route_obstructions(ready,effective_net(ready,n),
                          [f for f in ready.features if f.route_net==n.id],thread_definitions,definitions,modifier_definitions,snapshot.obstructions))
                n.route_state='proposal' if safe else 'stale'
                n.routing_variant=row['variant']
                n.route_issue='' if safe else n.id+': retained explicit route has unresolved engineering conditions.'
                row.update(route_state=n.route_state,status='CONNECTED_PROPOSAL_REQUIRES_FULL_VALIDATION' if safe else 'UNRESOLVED_EDITABLE_GEOMETRY')
            rows.extend(row for row in candidates if row['net'] not in mutable)
            return ready,rows
    repairs=_progressive_route_repair(resolved,selected,mutable,snapshot,expanded=True,
        unconnected={r['net'] for r in candidates if not r.get('connection_verified',False)})
    if repairs:
        _,chosen=repairs[0]
        resolved.features=[f for f in resolved.features if f.route_net not in chosen]
        resolved.features.extend(f for option in chosen.values() for f in option['route'])
        for net in resolved.nets:
            if net.id not in chosen:continue
            option=chosen[net.id];route=option['route']
            if option.get('tool_sizing'):net.diameter=option['tool_sizing']['diameter_mm']
            metadata=next(r for r in candidates if r['net']==net.id)
            metadata.update(variant=option['key'],axis_order=option['key'].split(':')[0],
                connection_verified=option.get('connection_verified',False),
                admission=option.get('admission',{}),connectivity_detail=option.get('connectivity_detail',{}),
                proximity_risk=option.get('risk',0),drillings=len(route),plugs=sum(f.plugged for f in route),
                sizing=option.get('tool_sizing',metadata['sizing']),pruned_drillings=option.get('pruned_ids',[]),
                length_mm=round(sum(f.depth for f in route),2),**route_margin(design,route))
    active = {f.id for f in resolved.features if not f.suppressed}
    for f in resolved.features:
        f.connects_to = [t for t in f.connects_to if t.split(':')[0] in active]
    final_failures={n.id:route_obstructions(resolved,effective_net(resolved,n),
        [f for f in resolved.features if f.route_net==n.id and not f.suppressed],
        thread_definitions,definitions,modifier_definitions,snapshot.obstructions)
        for n in resolved.nets if n.id in automatic}
    for row in candidates:
        facts=row.get('admission',{})
        if not row.get('connection_verified',False) or not facts.get('all_fluid_nodes_connected',False):final_failures[row['net']].add(('connectivity',row['net']))
        if facts.get('flow_opening_adequate') is False:final_failures[row['net']].add(('flow_opening',row['net']))
        if facts.get('direct_contact_adequate') is False:
            final_failures[row['net']].update(('insufficient_direct_contact',*c['nodes']) for c in row.get('connectivity_detail',{}).get('insufficient_direct_contacts',[]))
    for n in resolved.nets:
        for k,v in inherited[n.id].items():setattr(n,k,v)
        if n.id in automatic:
            failures=final_failures[n.id]
            # Keep the actual conflicting cuts available for editing/Validate.
            # stale means unresolved engineering, with NO implicit reroute on
            # load/Save/Validate; proposal alone is eligible for explicit commit.
            n.route_state='stale' if failures else 'proposal'
            by_feature={f.id:f for f in resolved.features}
            peers=sorted({by_feature[item].circuit for failure in failures for item in failure[1:]
                          if item in by_feature and by_feature[item].circuit and by_feature[item].circuit!=n.id})
            pool=snapshot.pool_diagnostics.get(n.id,{})
            search=snapshot.combination_diagnostics[-1] if snapshot.combination_diagnostics else {}
            repair=snapshot.repair_diagnostics[-1] if snapshot.repair_diagnostics else {}
            cause=('Some routing candidates could not be evaluated by CAD. Inspect local calculation diagnostics; no connected route was accepted.'
                   if pool.get('retained_clear')==0 and pool.get('geometry_errors') else
                   'No source-safe connected route remains in the retained candidate families. Review layout alternatives; source access or candidate coverage is limiting.'
                   if pool.get('retained_clear')==0 else
                   'The bounded route search exhausted its '+('pair' if 'pair_budget' in (search.get('exit_reason'),repair.get('exit_reason')) else 'state')+' budget. Review layout alternatives or reroute after adjustment.'
                   if any(r in ('pair_budget','state_budget') for r in (search.get('exit_reason'),repair.get('exit_reason'))) else
                   'Retained route families remain incompatible in this arrangement. Review layout alternatives; physical infeasibility is not proven.')
            n.route_issue=(f'{n.label or n.id}: unresolved route conflicts ('+
                ', '.join(sorted({failure[0].replace('_',' ') for failure in failures}))+')'+
                (' with '+', '.join(peers) if peers else '')+'. '+cause)[:500] if failures else ''
            metadata=next(r for r in candidates if r['net']==n.id)
            actual_route=[f for f in resolved.features if f.route_net==n.id and not f.suppressed]
            risk=proximity_risk(resolved,effective_net(resolved,n),actual_route,definitions,thread_definitions,snapshot.obstructions)
            n.routing_variant=metadata['variant']
            metadata.update(route_state=n.route_state,hard_failures=len(failures),
                failure_cause=cause if failures else None,layout_repair_suggested=bool(failures),
                proximity_risk=risk,objective=route_objective(resolved,actual_route,risk,definitions),
                conflicts=[list(f) for f in sorted(failures)],
                status='UNRESOLVED_EDITABLE_GEOMETRY' if failures else 'CONNECTED_PROPOSAL_REQUIRES_FULL_VALIDATION')
            if failures and corridor_diagnostic:
                metadata['corridor_diagnostic']=corridor_diagnostic
                metadata['failure_cause']=corridor_diagnostic['classification']
                explanation={'CANDIDATE_TRUNCATION':'Additional machining arrangements remain unevaluated within the search budget.',
                    'CORRIDOR_GENERATION_LIMIT':'Some machining corridors remain unexplored; no connected route was verified.',
                    'FIXED_MACHINING_BLOCKED':'Retained machining blocks the checked full-bore corridors.',
                    'SOURCE_DATA_UNRESOLVED':'Required source machining data is incomplete.',
                    'MULTINET_COORDINATION_LIMIT':'No compatible combination was verified for the explored hydraulic networks.'}.get(corridor_diagnostic['classification'],'The explored machining candidates did not pass engineering acceptance.')
                n.route_issue=(n.id+': '+explanation+' Current cuts retained for review.')[:500]
    candidates.extend(r for r in route_metadata(resolved) if r['net'] not in automatic)
    from .timing import diagnostic
    diagnostic('route_proposal',dict(selected={n.id:n.routing_variant for n in resolved.nets if n.id in automatic},
        admission={r['net']:{**r.get('admission',{}),'global_obstruction_clear':not final_failures[r['net']],
            'status':r['status']} for r in candidates if r['net'] in automatic},
        connectivity={r['net']:r.get('connectivity_detail',{}) for r in candidates if r['net'] in automatic and not r.get('connection_verified',False)},
        conflicts={name:[list(f) for f in sorted(failures)][:64] for name,failures in final_failures.items() if failures}))
    return resolved, candidates


def alternative_proposals(best, target, routes, report, eligible, inspected, *, repair_only=None, snapshot=None, cad_fallback=False):
    """Conflict-directed bounded neighbourhood, shared by save and optimization.

    Reconsider either implicated net, plus paired moves to escape a one-net local
    minimum. Screening allocates exact work; only exact FAIL/WARNING/cost selects.
    """
    eligible={n.id for n in target.nets if n.id in eligible and n.routing=='automatic'
              and not any(f.frozen_net==n.id for f in target.features)}
    selected={r['net']:r['variant'] for r in routes}
    if repair_only is None:repair_only=bool(report['counts']['FAIL'])
    from .engineering_db import definitions_for_design,thread_definitions_for_design,modifier_definitions_for_design
    definitions=snapshot.definitions if snapshot else definitions_for_design(target)
    threads=snapshot.threads if snapshot else thread_definitions_for_design(target)
    modifiers=snapshot.modifiers if snapshot else modifier_definitions_for_design(target) if any(f.machining_modifiers for f in target.features) else {}
    if snapshot is None:
        source=target.model_copy(deep=True)
        source.features=[f for f in source.features if f.route_net not in eligible]
        snapshot=_ProposalSnapshot(source,definitions,threads,modifiers)
    by_id={f.id:f for f in target.features}
    conflicts=set(); affected=set()
    for check in report['checks']:
        if check['status']!='FAIL' or repair_only and check.get('repair_domain')!='routing':continue
        owners=set()
        for item in check.get('items',[]):
            f=by_id.get(item.split(':')[0])
            if f:
                owners.update(({f.route_net,f.circuit}|set(f.circuits.values())) & set(eligible))
        affected.update(owners)
        conflicts.update(itertools.combinations(sorted(owners),2))
    # A failure without an automatic-net owner cannot be repaired by routing.
    # Never expand metadata, schematic, library-reference or fixed-geometry
    # failures into a search across every otherwise eligible net.
    net_ids=sorted(eligible if cad_fallback else affected if repair_only else eligible)
    if not net_ids:
        return []
    pools={}; moves=[]
    baseline_failures=set()
    for net in target.nets:
        if net.routing=='automatic':baseline_failures.update(route_obstructions(target,effective_net(target,net),
            [f for f in target.features if f.route_net==net.id and not f.suppressed],threads,definitions,modifiers,snapshot.obstructions))
    baseline_conflicts=_conflict_objective(baseline_failures)
    warning_nets={owner.route_net for check in report['checks'] if check['status']=='WARNING' and check['rule']!='construction_closure'
                  for item in check.get('items',[]) for owner in [by_id.get(str(item).split(':')[0])]
                  if owner and owner.kind=='drilling' and owner.route_net in eligible}
    for net_id in net_ids:
        context=target.model_copy(deep=True)
        context.features=[f for f in context.features if f.route_net!=net_id]
        net=next(n for n in context.nets if n.id==net_id)
        if repair_only and not cad_fallback:
            options=[o for o in _route_pool(snapshot.source,net,snapshot,expanded=True) if o['key']!=selected[net_id]]
        else:
            options=[o for o in route_options(context,net,expanded=bool(report['counts']['FAIL']),definitions=definitions,
                                              thread_definitions=threads,modifier_definitions=modifiers,snapshot=snapshot) if o['key']!=selected[net_id]]
        screened=sorted(options,key=lambda o:(route_objective(context,o['route'],o['risk'],definitions),o['key']))
        feasible=[o for o in screened if o['hard_failures']==0 and _candidate_admitted(o,effective_net(context,net))]
        shortlist=_strategy_shortlist(context,feasible,definitions,limit=6)
        pool={o['key']:o for o in shortlist}
        verified=[o for o in options if _candidate_admitted(o,effective_net(context,net))]
        pools[net_id]=sorted(verified,key=lambda o:(o['hard_failures'],
                                                  route_objective(context,o['route'],o['risk'],definitions),o['key']))[:3]
        moves.extend({net_id:o} for o in pool.values())
    for a,b in sorted(conflicts):
        moves.extend({a:x,b:y} for x,y in itertools.product(pools[a],pools[b]))
    if repair_only and baseline_failures:
        moves.extend(state for _,state in _progressive_route_repair(target,selected,set(net_ids),snapshot))
    if (not repair_only or cad_fallback) and len(net_ids)>1:
        combination_source=target.model_copy(deep=True)
        for net in combination_source.nets:
            if net.id in eligible:net.routing_variant=None
        combination=_complete_route_combination(combination_source,definitions,threads,modifiers,snapshot,net_ids=eligible,
                                               excluded=inspected if cad_fallback else None)
        if combination:moves.append(combination)
    proposals=[]
    for move in moves:
        if any(not _candidate_admitted(o,effective_net(target,next(n for n in target.nets if n.id==name))) for name,o in move.items()):continue
        variants=tuple(sorted({**selected,**{n:o['key'] for n,o in move.items()}}.items()))
        if variants in inspected:continue
        proposal=target.model_copy(deep=True)
        proposal.features=[f for f in proposal.features if f.route_net not in move]
        proposal.features.extend(f for o in move.values() for f in o['route'])
        if len(proposal.features)>120:continue
        failures=set()
        for net in proposal.nets:
            if net.routing!='automatic':continue
            route=[f for f in proposal.features if f.route_net==net.id]
            failures.update(route_obstructions(proposal,effective_net(proposal,net),route,threads,definitions,modifiers,snapshot.obstructions))
        drillings=[f for f in proposal.features if f.kind=='drilling' and not f.suppressed]
        # Prefer bounded, shorter machining before cost-equivalent long/complex
        # alternatives.  A long multi-axis candidate can make an OCCT Boolean
        # disproportionately expensive even when the proxy obstruction count is
        # identical.  Exact checks still decide whether the candidate improves.
        if failures and (not repair_only or cad_fallback or _conflict_objective(failures)>=baseline_conflicts):
            continue
        objective=route_objective(proposal,drillings,definitions=definitions)
        if not repair_only and not cad_fallback:
            current=[f for f in target.features if f.kind=='drilling' and not f.suppressed]
            current_objective=route_objective(target,current,definitions=definitions)
            # Only truly better manufacturing moves spend optimization attempts.
            # Repair mode still considers more expensive routes to cure FAIL.
            if objective>=current_objective and not set(move)&warning_nets:continue
        ranking=(_conflict_objective(failures),objective,variants)
        candidate=best.model_copy(deep=True)
        for net in candidate.nets:
            if net.id in move:net.routing_variant=move[net.id]['key']
        proposals.append((ranking,candidate,variants,', '.join(f'{n}: {o["key"]}' for n,o in sorted(move.items()))))
    return sorted(proposals,key=lambda p:p[0])


@timed('route.resolution')
def resolve_design(design, *, exact=True, persist=False, prepared=False, snapshot_cache=None,
                   max_attempts=8, step_path=None):
    """Check a bounded set of distinct clear proposals, preserving frozen/manual cuts.

    Exact selection is pure unless an explicit build/engineering decision opts into evidence.
    Proxy risk schedules proposals only. Exact failures, warnings, then machining
    cost determine selection, with the complete multi-net design as context.
    """
    from .closure_runtime import normalize_design
    design=normalize_design(design,resolve_generated=True)
    snapshots=snapshot_cache if snapshot_cache is not None else {}
    from .route_state import pending_nets,route_metadata,validate_current_design
    if not pending_nets(design):
        if exact and prepared:return validate_current_design(design,step_path=step_path)
        target=resolve_parents(design.model_copy(deep=True))
        return target,route_metadata(target)
    from .timing import progress
    if exact:progress('routes' if any(n.routing=='automatic' for n in design.nets) else 'preparing',8)
    target, routes = _resolve_proposals(design,snapshots=snapshots)
    # Search only explicitly unresolved nets. Committed/stale cuts are obstacles,
    # never candidates; normal Save/Validate uses validate_current_design instead.
    pending = [n for n in design.nets if n.id in pending_nets(design)]
    if not exact or not pending and not prepared:
        return target, routes
    from .geometry import build_geometry
    from .validation import validate
    from .cad_acceptance import production_topology,topology_clear,step_round_trip,add_step_check
    from . import store
    import uuid
    import time
    started = time.monotonic()
    folder = store.OUTPUT/'route-selections'/uuid.uuid4().hex if persist else None
    attempts=[]
    skipped=[]
    evaluations=[]
    fixed_topology=None
    step_exported=None
    optimization_done=False
    if not 1<=max_attempts<=12:raise ValueError('max_attempts must be between 1 and 12')
    def evaluate(candidate, reason, proposal=None):
        index=len(attempts)
        base=15+60*index/max_attempts
        if pending:
            if index:progress('alternate',base,candidate=index+1,candidate_limit=max_attempts)
            progress('candidate',base,candidate=index+1,candidate_limit=max_attempts)
        resolved, metadata = proposal if proposal is not None else _resolve_proposals(candidate,snapshots=snapshots)
        geometry=None
        try:
            progress('geometry',base+2)
            geometry=build_geometry(resolved)
            progress('rules',base+4)
            authorize_generated_contacts(resolved,geometry)
            report=validate(resolved,geometry)
        except Exception as exc:
            geometry=None
            report=dict(status='FAIL',counts=dict(FAIL=1,WARNING=0,PASS=0),checks=[dict(rule='cad_candidate_error',status='FAIL',error=type(exc).__name__,message=str(exc)[:2000])])
        cost=route_cost(resolved,[f for f in resolved.features if f.kind=='drilling' and not f.suppressed])
        progress('topology',base+6)
        score=exact_route_score(resolved,report,
               [f for f in resolved.features if f.kind=='drilling' and not f.suppressed],
               cad_error=geometry is None or not topology_clear(geometry))
        if folder:
            store.atomic_json(folder/f'attempt-{index:02}'/'resolved_design.json',resolved.model_dump())
            store.atomic_json(folder/f'attempt-{index:02}'/'validation.json',report)
        attempts.append(dict(index=index,reason=reason,score=score,routes=metadata,cost=cost,objective=score[2],
                             status=report['status'],counts=report['counts'],
                             production=production_topology(geometry) if geometry else None,
                             design_revision=store.revision(candidate)))
        evaluations.append([score,resolved,metadata,index,report,geometry,candidate])
        return score,resolved,metadata,index,report,geometry
    materialized=any(r.get('planner')=='corridor3d' for r in routes)
    best=target.model_copy(deep=True) if materialized else design.model_copy(deep=True)
    # Pin the baseline before varying one net, avoiding implicit nested searches.
    for net in best.nets:
        if net.id in pending_nets(design) and not materialized:net.routing_variant=next(r['variant'] for r in routes if r['net']==net.id)
    score,target,routes,chosen,report,geometry=evaluate(best,'Default baseline',(target,routes))
    inspected={tuple(sorted((r['net'],r.get('candidate_id') or r['variant']) for r in routes))}
    eligible={n.id for n in pending}
    # Only untried, analytically clear candidates spend the exact budget. The
    # candidate-count ceiling bounds search without killing slow exact geometry.
    while True:
        cad_bad=geometry is None or not topology_clear(geometry) or any(
            c['rule']=='step_round_trip' and c['status']=='FAIL' for c in report['checks'])
        snapshot=snapshots.get(_proposal_source_key(design)) if materialized else snapshots.get(_proposal_source_key(best))
        if cad_bad and eligible and fixed_topology is None:
            # Diagnose the fixed stock/cavities/manual/frozen machining once.
            # No net ownership is required for a route-dependent topology FAIL.
            try:
                fixed=best.model_copy(deep=True)
                fixed.features=[f for f in fixed.features if f.route_net not in eligible or f.frozen_net]
                fixed_geometry=snapshot.geometry if snapshot and snapshot.geometry is not None else build_geometry(fixed)
                fixed_topology=production_topology(fixed_geometry)
            except Exception as exc:
                fixed_topology=dict(valid=False,solids=None,error=type(exc).__name__)
        cad_fallback=cad_bad and bool(eligible) and fixed_topology['valid'] and fixed_topology['solids']==1
        if cad_bad and eligible and not cad_fallback:
            skipped.append(dict(reason='Production topology already fails without automatic generated routes',production=fixed_topology))
            proposals=[]
        elif (cad_fallback or not optimization_done) and len(attempts)<max_attempts:
            if pending:progress('alternate' if score[0] else 'comparison',15+60*len(attempts)/max_attempts)
            kwargs=dict(repair_only=bool(score[0]),snapshot=snapshot)
            if cad_fallback:kwargs['cad_fallback']=True
            if materialized:
                from .drilling_planner import proposal_alternatives
                proposals=proposal_alternatives(design,target,eligible,inspected,snapshot,objective_ceiling=score[2] if score[:2]==(0,0) else None)
            else:proposals=alternative_proposals(best,target,routes,report,eligible,inspected,**kwargs)
        else:
            skipped.append(dict(reason='Distinct candidate/execution budget exhausted'))
            proposals=[]
        if not proposals:
            # STEP is lazy: test the otherwise selected exact candidate only.
            # Failed serializations remain rejected in the same bounded pool.
            step_check=next((c for c in report['checks'] if c['rule']=='step_round_trip'),None)
            if geometry is not None and (step_check is None or step_path and step_exported!=chosen):
                progress('step',85)
                check=step_round_trip(geometry,step_path)
                if check['status']=='PASS':progress('step_verified',93)
                step_exported=chosen
                add_step_check(report,check)
                score=exact_route_score(target,report,[f for f in target.features if f.kind=='drilling' and not f.suppressed],
                                        cad_error=not topology_clear(geometry))
                evaluations[chosen][0]=score
                attempts[chosen].update(score=score,status=report['status'],counts=report['counts'],step=check)
                if folder:store.atomic_json(folder/f'attempt-{chosen:02}'/'validation.json',report)
                if check['status']=='FAIL':
                    # Reuse exact candidates already evaluated before spending
                    # another OCCT attempt. A worse objective can be CAD-safe.
                    selected=min(evaluations,key=lambda value:(value[0],value[3]))
                    score,target,routes,chosen,report,geometry,best=selected
                    if chosen!=step_exported or len(attempts)<max_attempts:
                        continue
            break
        _,candidate,signature,reason=proposals[0]
        inspected.add(signature)
        proposal,_=_resolve_proposals(candidate,snapshots=snapshots)
        cost=route_cost(proposal,[f for f in proposal.features if f.kind=='drilling' and not f.suppressed])
        objective=route_objective(proposal,[f for f in proposal.features if f.kind=='drilling' and not f.suppressed])
        if score[:2]==(0,0) and objective>=score[2]:
            skipped.append(dict(variants=signature,cost=cost,reason='Cannot improve exact PASS under the selected design priority'))
            # Finalize the selected serialization gate before returning.
            optimization_done=True
            continue
        trial,new_target,new_routes,index,new_report,new_geometry=evaluate(candidate,reason)
        if trial<score:
            best,score,target,routes,chosen,report,geometry=candidate,trial,new_target,new_routes,index,new_report,new_geometry
    if folder:
        store.atomic_json(folder/'summary.json',dict(selected_attempt=chosen,attempts=attempts,skipped=skipped,
                                                   progressive_repair=[row for snapshot in snapshots.values() for row in snapshot.repair_diagnostics],
                                                   fixed_production=fixed_topology,seconds=time.monotonic()-started))
    for route in routes:
        if folder:route['selection_evidence']=folder.name
        route['exact_attempts']=len(attempts)
        route['status']='EXACT_CANDIDATE_CHECKED_REQUIRES_FINAL_VALIDATION'
    if prepared:
        if geometry is None:raise RuntimeError('No usable exact solid was produced; '+report['checks'][0].get('message','inspect candidate failure evidence.'))
        return target,routes,geometry,report
    return target,routes


@timed('hydraulic.contacts')
def authorize_generated_contacts(design, geometry):
    """Authorize only declared net members and generated bores of that net; retain all other rules."""
    nets = {n.id:set(n.members) for n in design.nets}
    from .spatial import geometry_pairs
    pairs=geometry_pairs(geometry)
    for f in design.features:
        if not f.route_net or f.suppressed:
            continue
        allowed = nets[f.route_net] | {x.id for x in design.features if x.route_net == f.route_net}
        f.connects_to = sorted(n for n in geometry.nodes if n != f.id and n in allowed
                              and geometry.circuits[n] == f.circuit
                              and pairs.volume(geometry.nodes[f.id],geometry.nodes[n]) > 1e-6)


def adopt_routes(design):
    result = design.model_copy(deep=True)
    for net in result.nets:
        for f in result.features:
            if f.kind != 'drilling' or not f.plugged or f.circuit != net.id or f.route_net:
                continue
            trunks = [t for t in result.features if t.id in f.connects_to and t.kind == 'drilling' and not t.plugged and t.circuit == net.id]
            if len(trunks) == 1 and not any(a.id == f.id for a in net.construction_access):
                trunk = trunks[0]
                p,d = pose(trunk, result.block); q,_ = pose(f,result.block)
                distance = sum((b-a)*axis for a,b,axis in zip(p,q,d))
                if .1 <= distance/trunk.depth <= .9:
                    net.construction_access.append(ConstructionAccess(id=f.id,face=f.face,fraction=distance/trunk.depth))
    # Explicit migration: all manual drillings are replaced, primary components are preserved.
    result.features = [f for f in result.features if f.kind != 'drilling']
    for f in result.features:
        f.connects_to = []
    for net in result.nets:
        net.routing = 'automatic'
    return result
