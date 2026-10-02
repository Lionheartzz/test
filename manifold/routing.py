from .engineering_conditions import effective_net,required_wall,planning_wall,wall_unresolved
from .timing import timed,phase
"""Deterministic orthogonal route proposals. Only the BRep validator grants PASS."""
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


def propose(design, net, order, entry=None, detour='direct', definitions=None, safe_planes=None, *, terminal_overrides=None, connector_bends=None):
    net=effective_net(design,net)
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    points = terminal_points(design,definitions)
    points.update(terminal_overrides or {})
    pairs = spanning_pairs(sorted(set(points[m] for m in net.members if m in points)))
    ports_at = {points[f.id]:f for f in design.features if f.kind=='port' and not f.suppressed
                and f.id in net.members and f.id in points and f.circuit==net.id}
    def port_stem(feature, point):
        origin,direction=pose(feature,design.block)
        definition=definitions[feature.definition] if feature.definition else None
        window_end=definition.zones[0].end if definition else feature.depth
        cut_radius=(max(max(stage.diameter,getattr(stage,'end_diameter',0)) for stage in
                        (definition.cutting_primitives or definition.stages))/2 if definition else feature.diameter/2)
        current=sum((point[i]-origin[i])*direction[i] for i in range(3))
        # Turn away from the port only after clearing its protected machining
        # body. The coaxial terminal drilling itself remains open.
        depth=max(window_end,current)+cut_radius+net.diameter/2+planning_wall(design,net,definitions)
        return tuple(point[i]+direction[i]*(depth-current) for i in range(3))
    lines = {}
    for a,b in pairs:
        if b in ports_at and a not in ports_at:a,b=b,a
        start=port_stem(ports_at[a],a) if a in ports_at else a
        end=port_stem(ports_at[b],b) if b in ports_at else b
        waypoints = [a,start,end,b] if a in ports_at and b in ports_at else [a,start,end] if a in ports_at else [start,end,b] if b in ports_at else [a,b]
        if connector_bends and (end in connector_bends or start in connector_bends):
            reverse=end not in connector_bends
            bends,axial_axis=connector_bends[start if reverse else end]
            path=_axial_connector_path(end if reverse else start,start if reverse else end,
                                      order[::-1] if reverse else order,bends,axial_axis)
            if path is None:return None
            if reverse:path=path[::-1]
            waypoints=([a] if a in ports_at else [])+path+([b] if b in ports_at else [])
        if detour != 'direct':
            if safe_planes is None:
                safe_planes = obstacle_safe_planes(design, net, definitions)
            if isinstance(detour, str):
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
            for axis in order:
                if abs(p[axis]-end[axis]) < 1e-7:
                    continue
                fixed = tuple(round(p[i], 6) for i in range(3) if i != axis)
                key = (axis, fixed)
                lo,hi = sorted((p[axis], end[axis]))
                lines.setdefault(key,[]).append((lo,hi)); p[axis] = end[axis]
    sizes = dimensions(design.block)
    features = []
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
        _,_,face,depth,coaxial = min(options)
        u,v,_,_ = FACE_AXES[face]
        features.append(Feature(id=f'R-{digest}-{len(features)+1}', kind='drilling', face=face, u=p[u], v=p[v],
                                circuit=net.id, diameter=net.diameter, depth=max(depth,9), plugged=not coaxial,
                                route_net=net.id, clearance_diameter=max(16,net.diameter+8), clearance_height=15))
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


def obstacle_safe_planes(design, net, definitions, thread_definitions=None, modifier_definitions=None):
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
        if other.suppressed or other.route_net in automatic:
            continue
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


def simple_routes(design,net,definitions=None):
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
    if net.drilling_mode == 'orthogonal':
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
    if key.startswith('axial_'):return 'axial-detour' if key.count(':')==3 else 'axial'
    if key.startswith('simple_'):return 'simple'
    return 'direct' if key.endswith(':direct') else 'detour'


def _strategy_shortlist(design, options, definitions=None, limit=16, eligible=None):
    """Bounded Pareto layers per family, then round-robin strategy opportunities.

    Raw domination cannot justify removing a geometrically distinct strategy:
    it may prune better or clear a different sibling route. Keep those as later
    Pareto layers rather than deleting them before exact connectivity pruning.
    """
    buckets={family:[] for family in ('axial','axial-detour','simple','direct','detour')}
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
            strategy=(key.split(':')[0] if family=='axial' else key.split(':')[-1] if family in ('detour','axial-detour') else family,faces)
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


def _plug_cut_overlap(plug, cut, block, plug_bounds=None):
    """Return only witnessed finite-volume overlap; a proxy cannot certify clearance.

    Witnesses are strictly inside the plug and the actual axial/radial cut profile.
    This avoids end-cap and infinite-line false positives while exact BRep remains
    the authority for narrow intersections missed by this cheap candidate screen.
    """
    origin, direction = pose(plug, block)
    cut_origin, cut_direction = pose(cut['feature'], block)
    dot = lambda a, b: sum(x*y for x, y in zip(a, b))
    subtract = lambda a, b: tuple(x-y for x, y in zip(a, b))
    margin = 0.05
    if plug.plug_length <= 2*margin or cut['end']-cut['start'] <= 2*margin:
        return False
    plug_bounds = plug_bounds if plug_bounds is not None else cylinder_bounds(plug, block, 0, plug.plug_length, plug.diameter)
    if cut.get('_bounds') is None:
        cut['_bounds'] = cylinder_bounds(cut['feature'], block, cut['start'], cut['end'],
                                        2*max(cut['radius_start'], cut['radius_end']))
    cut_bounds = cut['_bounds']
    if any(min(a[1], b[1])-max(a[0], b[0]) <= margin for a, b in zip(plug_bounds, cut_bounds)):
        return False
    projected = [dot(subtract(tuple(cut_origin[i]+cut_direction[i]*depth for i in range(3)), origin), direction)
                 for depth in (cut['start'], (cut['start']+cut['end'])/2, cut['end'])]
    positions = {plug.plug_length*i/min(32, max(4, math.ceil(plug.plug_length)))
                 for i in range(1, min(32, max(4, math.ceil(plug.plug_length))))}
    positions.update(t+offset for t in projected for offset in (-0.25, 0, 0.25))
    reference = (1, 0, 0) if abs(direction[0]) < .9 else (0, 1, 0)
    first = tuple(direction[(i+1)%3]*reference[(i+2)%3]-direction[(i+2)%3]*reference[(i+1)%3] for i in range(3))
    norm = math.sqrt(dot(first, first))
    first = tuple(x/norm for x in first)
    second = tuple(direction[(i+1)%3]*first[(i+2)%3]-direction[(i+2)%3]*first[(i+1)%3] for i in range(3))
    radial = [(0, 0)] + [(fraction*math.cos(i*math.pi/4), fraction*math.sin(i*math.pi/4))
                         for fraction in (.5, .9) for i in range(8)]
    for depth in sorted(t for t in positions if margin < t < plug.plug_length-margin):
        center = tuple(origin[i]+direction[i]*depth for i in range(3))
        for x, y in radial:
            point = tuple(center[i]+plug.diameter/2*(x*first[i]+y*second[i]) for i in range(3))
            relative = subtract(point, cut_origin)
            axial = dot(relative, cut_direction)
            if not cut['start']+margin < axial < cut['end']-margin:
                continue
            radius = cut['radius_start']+(cut['radius_end']-cut['radius_start'])*(axial-cut['start'])/(cut['end']-cut['start'])
            squared = dot(relative, relative)-axial*axial
            if cut['inner_radius']+margin < math.sqrt(max(0, squared)) < radius-margin or (
                    cut['inner_radius'] == 0 and squared < (radius-margin)**2):
                return True
    return False


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


def _cuts_too_close(route_cuts, obstacle, block, clearance):
    """Broad-phase finite bounds, then tapered profile slices only near a cut."""
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
        return any(x[1]+clearance <= y[0]+1e-6 or y[1]+clearance <= x[0]+1e-6
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
        for cut in _cut_slices(obstacle):
            cut_bounds = bounds(cut)
            for part in _cut_slices(route_cut):
                if separated(bounds(part), cut_bounds):
                    continue
                a,b = endpoints(part)
                c,d = endpoints(cut)
                if (segment_distance(a,b,c,d)-max(part['radius_start'],part['radius_end'])
                        -max(cut['radius_start'],cut['radius_end']) < clearance-1e-6):
                    return True
    return False


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
            plug_bounds=cylinder_bounds(bore,design.block,0,bore.plug_length,bore.diameter)
            a,b = segment(bore, design.block, -bore.clearance_height, 0)
            for other in obstacles:
                if other.suppressed or other.id == bore.id or not (other.kind in ('port','cavity') or other.plugged):
                    continue
                definition = definitions[other.definition] if other.definition else None
                diameter = definition.clearance_diameter if other.kind == 'cavity' and definition else other.clearance_diameter
                height = definition.clearance_height if other.kind == 'cavity' and definition else other.clearance_height
                c,d = segment(other, design.block, -height, 0)
                if segment_distance(a,b,c,d)-(bore.clearance_diameter+diameter)/2 < design.rules.minimum_access_gap-1e-6:
                    failures.add(('installation_access', *sorted((bore.id, other.id))))
            for other in obstacles:
                if other.suppressed or other.id == bore.id:
                    continue
                if any(_plug_cut_overlap(bore, cut, design.block,plug_bounds) for cut in cuts(other)):
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
                if _cuts_too_close(route_cuts, whole_cut, design.block, threshold):
                    failures.add(('source_protected' if threshold==0 else 'source_wall',
                                  *sorted((bore.id, other.id))))
                    break
        for other in obstacles:
            if other.suppressed or other.id == bore.id or other.definition or other.circuit == net.id:
                continue
            for whole_cut in cuts(other):
                if _cuts_too_close(route_cuts, whole_cut, design.block, required_wall(design,bore,other,definitions=definitions)):
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
    return failures


class _ProposalSnapshot:
    """Lazy source BRep and pruning evidence owned by one proposal resolution."""
    def __init__(self, design, definitions, threads, modifiers):
        automatic={n.id for n in design.nets if n.routing=='automatic'}
        self.source=design.model_copy(deep=True)
        self.source.features=[f for f in self.source.features if f.route_net not in automatic]
        self.definitions,self.threads,self.modifiers=definitions,threads,modifiers
        self.geometry=None
        self.cache={}
        self.results={}
        self.options={}
        self.catalogs={}
        self.obstructions={}

    def simplify(self, design, net, route, *, known_failures=None):
        # Generated siblings affect obstruction screening, but not the same-net
        # fluid graph. Include every explicit outside contact in the cache key:
        # a later route declaring a required contact must protect that drilling.
        protected=tuple(sorted({key for f in design.features if f.route_net!=net.id for key in f.connects_to}))
        key=(net.model_dump_json(exclude={'routing_variant'}),
             tuple(f.model_dump_json() for f in route),protected)
        if key not in self.results:
            if self.geometry is None:
                from .geometry import build_geometry
                self.geometry=build_geometry(self.source,self.definitions,self.threads,self.modifiers)
            result,connected=simplify_generated_route(design,net,route,source_geometry=self.geometry,
                definitions=self.definitions,thread_definitions=self.threads,modifier_definitions=self.modifiers,
                cache=self.cache,known_failures=known_failures)
            self.results[key]=([f.model_copy(deep=True) for f in result],connected)
        result,connected=self.results[key]
        # Tool sizing and presentation can mutate a selected proposal afterwards.
        return [f.model_copy(deep=True) for f in result],connected


@timed('route.simplification')
def simplify_generated_route(design, net, route, *, source_geometry=None, definitions=None,
                             thread_definitions=None, modifier_definitions=None, cache=None, known_failures=None):
    """Prune only proven redundant automatic cuts using exact fluid-node contacts."""
    from .geometry import build_geometry,feature_geometry
    from .flow import required_area, opening_area
    if source_geometry is None:
        source=design.model_copy(update=dict(features=[f for f in design.features if f.route_net!=net.id]))
        source_geometry=build_geometry(source,definitions,thread_definitions,modifier_definitions)
    cache=cache if cache is not None else {}
    cuts=cache.setdefault('cuts',{});contacts=cache.setdefault('contacts',{});bounds=cache.setdefault('bounds',{})
    proxies=cache.setdefault('proxies',{})
    nodes={key:shape for key,shape in source_geometry.nodes.items() if source_geometry.circuits[key]==net.id}
    required=set(net.members)
    protected=required|{access.id for access in net.construction_access}
    for feature in design.features:
        if feature.route_net!=net.id:
            protected.update(feature.connects_to)
    possible={}
    from .engineering_db import definitions_for_design
    definitions=definitions if definitions is not None else definitions_for_design(design)
    points=terminal_points(design,definitions)
    by_id={f.id:f for f in design.features}
    for key,shape in nodes.items():
        signature='source:'+key
        if signature not in bounds:
            box=shape.BoundingBox()
            bounds[signature]=((box.xmin,box.xmax),(box.ymin,box.ymax),(box.zmin,box.zmax))
        possible[key]=bounds[signature]
        if signature not in proxies:
            owner=by_id[key.split(':')[0]]
            if owner.definition:
                definition=definitions[owner.definition]
                zone=next(z for z in definition.zones if z.id==key.split(':')[1]) if ':' in key else definition.zones[0]
                center=points[key];direction=source_geometry.placements[owner.id]['direction']
                a=tuple(center[i]-direction[i]*(zone.end-zone.start)/2 for i in range(3))
                b=tuple(center[i]+direction[i]*(zone.end-zone.start)/2 for i in range(3))
                radius=zone.diameter/2
                relevant=[c for c in _manufacturing_cuts(owner,definitions,thread_definitions or {},modifier_definitions or {})
                          if c['start']<zone.end and c['end']>zone.start]
                u,v=FACE_AXES[owner.face][:2]
                if ((definition.cutting_primitives or zone.clip_to_cut) and relevant and
                        all(abs(c['feature'].u-center[u])<1e-6 and abs(c['feature'].v-center[v])<1e-6 for c in relevant)):
                    radius=min(radius,max(max(c['radius_start'],c['radius_end']) for c in relevant))
                proxies[signature]=(a,b,radius)
            else:
                a,b=segment(owner,design.block,owner.plug_length if owner.plugged else 0)
                proxies[signature]=(a,b,owner.diameter/2)
    for feature in route:
        possible[feature.id]=cylinder_bounds(feature,design.block,feature.plug_length if feature.plugged else 0,
                                             segment_depth(feature),feature.diameter)
    graph={key:set() for key in possible}
    for a,b in itertools.combinations(possible,2):
        if all(min(x[1],y[1])>max(x[0],y[0]) for x,y in zip(possible[a],possible[b])):
            def proxy(key):
                if key in nodes:return proxies['source:'+key]
                feature=next(f for f in route if f.id==key)
                first,last=segment(feature,design.block,feature.plug_length if feature.plugged else 0)
                return first,last,feature.diameter/2
            first,second=proxy(a),proxy(b)
            if segment_distance(*first[:2],*second[:2])<first[2]+second[2]+1e-6:
                graph[a].add(b);graph[b].add(a)

    def connected(active):
        if not required.issubset(active) or not active:
            return False
        visited=set();pending=[min(active)]
        while pending:
            key=pending.pop()
            if key in visited:continue
            visited.add(key);pending.extend((graph[key]&active)-visited)
        return visited==active

    if not connected(set(possible)):
        return route,False
    eligible=[f for f in route if net.routing=='automatic' and f.route_net==net.id and not f.frozen_net and f.id not in protected]
    if not any(connected(set(possible)-{f.id}) for f in eligible):
        # Even the generous bounding-box contact graph has no removable node.
        # Its exact subgraph cannot justify a deletion, so skip optional CAD
        # cleanup; authoritative candidate validation still checks connectivity.
        return route,True
    signatures={key:'source:'+key for key in nodes}
    directions=dict(source_geometry.placements)
    for feature in route:
        signature=feature.model_dump_json(exclude={'id','connects_to','schematic_id','machining_id'})
        if signature not in cuts:
            candidate=design.model_copy(update=dict(features=[feature],engravings=[],block_modifiers=[]))
            _,fluid,_,_,_,placements,_=feature_geometry(candidate,definitions,thread_definitions or {},modifier_definitions or {})
            cuts[signature]=(fluid[feature.id],placements[feature.id])
        nodes[feature.id],directions[feature.id]=cuts[signature]
        signatures[feature.id]=signature
    if not required.issubset(nodes):
        return route,False
    graph={key:set() for key in nodes}
    area=required_area(net.flow_lpm,net.velocity_limit) if net.flow_lpm else None
    for a,b in itertools.combinations(nodes,2):
        key=(tuple(sorted((signatures[a],signatures[b]))),design.rules.minimum_overlap_volume,area)
        if key not in contacts:
            for node in (a,b):
                signature=signatures[node]
                if signature not in bounds:
                    box=nodes[node].BoundingBox()
                    bounds[signature]=((box.xmin,box.xmax),(box.ymin,box.ymax),(box.zmin,box.zmax))
            separated=any(min(x[1],y[1])<=max(x[0],y[0])
                          for x,y in zip(bounds[signatures[a]],bounds[signatures[b]]))
            contact=not separated and nodes[a].intersect(nodes[b]).Volume()+1e-6>=design.rules.minimum_overlap_volume
            if contact and area:
                contact=opening_area(nodes[a],nodes[b],
                    [directions[node.split(':')[0]]['direction'] for node in (a,b)])+1e-6>=area
            contacts[key]=contact
        if not contacts[key]:continue
        graph[a].add(b);graph[b].add(a)

    active=set(nodes)
    if not connected(active):
        return route,False
    remaining=list(route)
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
    return remaining,True


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


def route_options(design, net, *, expanded=False, definitions=None,thread_definitions=None,modifier_definitions=None,
                  snapshot=None, seed=None):
    from copy import deepcopy
    net=effective_net(design,net)
    cache_key=(design.model_dump_json(),net.model_dump_json(),tuple(net.members),expanded,
               (seed['key'],tuple(f.model_dump_json() for f in seed['route'])) if seed else None)
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
    source=snapshot.source
    catalog_key=(net.model_dump_json(exclude={'routing_variant'}),tuple(net.members),expanded)
    if catalog_key not in snapshot.catalogs:
        snapshot.catalogs[catalog_key]=route_candidate_catalog(source,net,definitions,thread_definitions,modifier_definitions,expanded=expanded,cache=snapshot.obstructions)
    options=deepcopy(snapshot.catalogs[catalog_key])
    # Connector detours see actual retained automatic routes during local/repair
    # evaluation. Plane coordinates are explicit in the key, so saved variants
    # regenerate independently of these temporary obstacle contexts.
    if any(f.route_net and f.route_net!=net.id for f in design.features):
        from .cavity_access import axial_connector_candidates
        known={option['key'] for option in options}
        for key,route in axial_connector_candidates(source,net,definitions,thread_definitions,modifier_definitions,design,snapshot.obstructions):
            if key in known:continue
            options.append(dict(key=key,route=route,risk=proximity_risk(source,net,route,definitions,thread_definitions,snapshot.obstructions),cost=route_cost(source,route)))
    # Keep an explicitly failing proposal if the constraint makes every candidate impossible.
    # The validator reports the conflict; never remove a required connection to hide it.
    def source_clear(option):
        option['hard_failures']=len(route_obstructions(source,net,option['route'],thread_definitions,definitions,modifier_definitions,snapshot.obstructions))
        return not option['hard_failures']
    fixed_failures={}
    for option in options:
        if _strategy_family(option['key'])!='axial-detour':continue
        bores=[f for f in option['route'] if '-AX' in f.id]
        token=tuple(f.model_dump_json(exclude={'connects_to'}) for f in bores)
        if token not in fixed_failures:
            fixed_failures[token]=len(route_obstructions(design,net,bores,thread_definitions,definitions,modifier_definitions,snapshot.obstructions))
        # No connector layout can repair an obstruction of this immutable bore.
        # Retain the failure for diagnostics, without spending pruning work on
        # an impossible local strategy or changing any protection threshold.
        option['fixed_failures']=fixed_failures[token]
    if not seed:
        for option in options:
            if option.get('fixed_failures'):option['hard_failures']=option['fixed_failures']
            else:source_clear(option)
    else:
        # A valid local seed permits lazy source screening in the SAME family /
        # Pareto queues. Invalid raw variants do not consume a family's quota.
        # Every shortlisted candidate is still fully screened before pruning.
        for option in options:option['hard_failures']=option.get('fixed_failures',0)
    rank=lambda o:(o['hard_failures'],route_objective(design,o['route'],o['risk'],definitions),o['key'])
    permitted=[o for o in options if all(f.face not in design.constraints.forbidden_drilling_faces for f in o['route'])]
    options=sorted(permitted or options,key=rank)
    # Source-safe strategies first, then bounded family/Pareto opportunities.
    # Sibling construction routes are checked again AFTER redundant cuts have
    # gone; a temporary connector may disappear, but retained nets never move.
    clear_options=[option for option in options if not option['hard_failures'] and (not seed or option['key']!=seed['key'])]
    clear=_strategy_shortlist(source,clear_options,definitions,limit=16-bool(seed),eligible=source_clear if seed else None)
    if clear:
        options=clear+[option for option in options if option['hard_failures'] and option not in clear]
        for option in clear:
            original=option['route']
            route,connected=snapshot.simplify(design,net,original,known_failures=set())
            option['route']=route
            option['pruned_ids']=sorted({f.id for f in original}-{f.id for f in route})
            option['hard_failures']=(len(route_obstructions(design,net,route,thread_definitions,definitions,modifier_definitions,snapshot.obstructions)) if connected else 1)
            option['risk']=proximity_risk(design,net,route,definitions,thread_definitions,snapshot.obstructions)
            option['cost']=route_cost(design,route)
            option['metrics']=manufacturing_metrics(design,route,option['risk'],definitions)
    if seed:
        preserved=deepcopy(seed)
        preserved['risk']=proximity_risk(design,net,preserved['route'],definitions,thread_definitions)
        preserved['cost']=route_cost(design,preserved['route'])
        preserved['metrics']=manufacturing_metrics(design,preserved['route'],preserved['risk'],definitions)
        options.append(preserved)
    permitted = [o for o in options if all(f.face not in design.constraints.forbidden_drilling_faces for f in o['route'])]
    if not expanded and all(o['hard_failures'] for o in (permitted or options)):
        result=route_options(design,net,expanded=True,definitions=definitions,thread_definitions=thread_definitions,
                             modifier_definitions=modifier_definitions,snapshot=snapshot)
    else:result=sorted(permitted or options,key=rank)
    if snapshot is not None:snapshot.options[cache_key]=deepcopy(result)
    return result


def route_from_variant(design, net, variant, definitions, threads=None, modifiers=None):
    net=effective_net(design,net)
    """Shared regeneration for global selection and incremental current templates."""
    if variant.startswith('axial_'):
        from .cavity_access import axial_route
        return axial_route(design,net,definitions,variant,threads=threads,modifiers=modifiers)
    if variant.startswith('simple_'):
        templates = simple_routes(design,net,definitions)
        index = int(variant.split('_')[1])
        return templates[index] if index < len(templates) else None
    order,entry,detour = variant.split(':')
    if sorted(order) != ['x','y','z']:
        raise ValueError('Routing variant must use each axis once')
    return propose(design,net,tuple('xyz'.index(i) for i in order),entry,detour,definitions)


def resize_route(design, net, option, diameter, definitions, threads=None, modifiers=None):
    # Axial stop depth includes the real radius/tip/contact requirement. A larger
    # selected tool must regenerate it; changing only diameter could cut a seat.
    if option['key'].startswith('axial_'):
        sized = net.model_copy(update=dict(diameter=diameter))
        route = route_from_variant(design,sized,option['key'],definitions,threads,modifiers)
        if route is None:raise ValueError(f'{net.id}: selected drill has no safe deep-end corridor')
        option['route'] = route
    else:
        for feature in option['route']:feature.diameter=diameter


def _complete_route_combination(design, definitions, thread_definitions, modifier_definitions, snapshot=None, net_ids=None, deadline=None, excluded=None):
    """Bounded backtracking across individually clear automatic routes."""
    nets = sorted((effective_net(design,n) for n in design.nets if n.routing == 'automatic' and (net_ids is None or n.id in net_ids)), key=lambda n:n.id)
    if len(nets)<2 or any(n.routing_variant or n.flow_lpm for n in nets):
        return None
    automatic = {n.id for n in nets}
    source = design.model_copy(update=dict(features=[f for f in design.features if f.route_net not in automatic]))
    snapshot=snapshot or _ProposalSnapshot(source,definitions,thread_definitions,modifier_definitions)
    pools = {}
    for net in nets:
        if deadline is not None:
            import time
            if time.monotonic()>=deadline:return None
        options = route_options(source, net, definitions=definitions,
                                thread_definitions=thread_definitions, modifier_definitions=modifier_definitions,snapshot=snapshot)
        pools[net.id] = [o for o in options if o['hard_failures']==0][:24]
        if not pools[net.id]:
            return None
    compatible = {}
    inspected = 0
    best=None;best_key=None;states=0
    def combination_key(chosen):
        route=[f for option in chosen.values() for f in option['route']]
        return (route_objective(source,route,sum(o['risk'] for o in chosen.values()),definitions),
                tuple(route_objective(source,option['route'],option['risk'],definitions) for _,option in sorted(chosen.items())),
                tuple((name,option['key']) for name,option in sorted(chosen.items())))
    minimum={net.id:dict(plugs=min(sum(f.plugged for f in o['route']) for o in pools[net.id]),
                        count=min(len(o['route']) for o in pools[net.id]),
                        maximum=min(max((f.depth for f in o['route']),default=0) for o in pools[net.id]),
                        total=min(sum(f.depth for f in o['route']) for o in pools[net.id])) for net in nets}

    def lower_bound(index,chosen):
        route=[f for option in chosen.values() for f in option['route']]
        remaining=[minimum[n.id] for n in nets[index:]]
        plugs=sum(f.plugged for f in route)+sum(m['plugs'] for m in remaining)
        count=len(route)+sum(m['count'] for m in remaining)
        maximum=max([f.depth for f in route]+[m['maximum'] for m in remaining],default=0)
        total=sum(f.depth for f in route)+sum(m['total'] for m in remaining)
        priority=design.constraints.priority
        if priority=='fewer_plugs':return (plugs,count,maximum,total)
        if priority=='short_drills':return (maximum,total,count,plugs)
        if priority=='simple_machining':return (count,len({f.face for f in route}),plugs,total)
        return (0,0,count,plugs,total)

    def pair_clear(a, ao, b, bo):
        nonlocal inspected
        key = (a.id,ao['key'],b.id,bo['key'])
        if key not in compatible:
            inspected += 1
            if inspected > 4000:
                return False
            context = source.model_copy(update=dict(features=ao['route']+bo['route']))
            compatible[key] = (not route_obstructions(context,a,ao['route'],thread_definitions,definitions,modifier_definitions)
                               and not route_obstructions(context,b,bo['route'],thread_definitions,definitions,modifier_definitions))
        return compatible[key]

    def search(index, chosen):
        nonlocal best,best_key,states
        if deadline is not None:
            import time
            if time.monotonic()>=deadline:return None
        states+=1
        if inspected > 4000 or states>1000:
            return None
        bound=lower_bound(index,chosen)
        if best_key and bound>best_key[0][:len(bound)]:
            return None
        if index == len(nets):
            if excluded and tuple(sorted((n,o['key']) for n,o in chosen.items())) in excluded:return None
            route=[f for option in chosen.values() for f in option['route']]
            if len(source.features)+len(route)>120:return None
            key=combination_key(chosen)
            if best_key is None or key<best_key:
                best,best_key=chosen,key
            return None
        net = nets[index]
        for option in pools[net.id]:
            if all(pair_clear(prior, chosen[prior.id], net, option) for prior in nets[:index]):
                search(index+1,{**chosen,net.id:option})
            if inspected>4000 or states>1000:break

    search(0,{})
    # The search is bounded, but its first complete combination is not a
    # manufacturing optimum. Remove obvious compatible single-net improvements
    # from the chosen combination using the same prepared pools/pair cache.
    if best:
        for _ in range(len(nets)):
            improved=False
            for net in nets:
                for option in pools[net.id]:
                    if all(pair_clear(other,best[other.id],net,option) for other in nets if other.id!=net.id):
                        chosen={**best,net.id:option}
                        if excluded and tuple(sorted((n,o['key']) for n,o in chosen.items())) in excluded:continue
                        route=[f for value in chosen.values() for f in value['route']]
                        key=combination_key(chosen)
                        if key<best_key:best,best_key=chosen,key;improved=True
                    if inspected>4000:break
            if not improved or inspected>4000:break
    return best


def _proposal_source_key(design):
    # Variants choose construction proposals; they do not alter source geometry.
    # Reuse its BRep/catalog/pruning caches across bounded exact attempts.
    automatic={n.id for n in design.nets if n.routing=='automatic'}
    source=design.model_copy(update=dict(features=[f for f in design.features if f.route_net not in automatic]))
    return source.model_dump_json(exclude={'nets':{'__all__':{'routing_variant'}}})


@timed('route.proposal')
def _resolve_proposals(design, *, snapshots=None):
    authored=design
    inherited={n.id:{k:getattr(n,k) for k in ("pressure_bar","flow_lpm","velocity_limit","drilling_mode")} for n in design.nets}
    design=design.model_copy(deep=True)
    design.nets=[effective_net(design,n) for n in design.nets]
    signature=_proposal_source_key(authored)
    resolved = resolve_parents(design)
    from .engineering_db import definitions_for_design,thread_definitions_for_design,modifier_definitions_for_design,tool_definitions
    definitions=definitions_for_design(resolved)
    thread_definitions=thread_definitions_for_design(resolved)
    modifier_definitions=modifier_definitions_for_design(resolved) if any(f.machining_modifiers for f in resolved.features) else {}
    from .sizing import route_sizing
    tools=tool_definitions('drill')
    sizing={n.id:route_sizing(n,tools=tools,required_depth=0,preferred_unit=resolved.project_context) for n in resolved.nets}
    for net in resolved.nets:
        if net.routing=='automatic':net.diameter=sizing[net.id]['diameter_mm']
    automatic = {n.id for n in resolved.nets if n.routing == 'automatic'}
    resolved.features = [f for f in resolved.features if f.route_net not in automatic]
    snapshots=snapshots if snapshots is not None else {}
    if signature not in snapshots:
        snapshots[signature]=_ProposalSnapshot(resolved,definitions,thread_definitions,modifier_definitions)
    snapshot=snapshots[signature]
    # Multi-net layouts commonly need a paired move. Build their independent
    # pools once instead of first exhausting a conflicting greedy layout and
    # then rebuilding the same pools for the bounded combination search.
    combination = (_complete_route_combination(resolved,definitions,thread_definitions,modifier_definitions,snapshot)
                   if len(automatic)>2 else None)
    candidates = []
    for net in sorted(resolved.nets,key=lambda n:n.id):
        if net.routing != 'automatic':
            continue
        def tool_size(option,context=resolved):
            if not net.flow_lpm:return sizing[net.id]
            actual=None
            for _ in range(12):
                required_depth=max((f.depth + (0 if f.tip_angle==180 else f.diameter/2/math.tan(math.radians(f.tip_angle/2)))
                                    for f in option['route']),default=0)
                actual=route_sizing(net,tools=tools,required_depth=required_depth,preferred_unit=resolved.project_context)
                if all(abs(f.diameter-actual['diameter_mm'])<=1e-9 for f in option['route']):break
                resize_route(context,net,option,actual['diameter_mm'],definitions,thread_definitions,modifier_definitions)
            else:
                raise ValueError(f'{net.id}: route sizing did not settle on a source-backed drill')
            option['tool_sizing']=actual
            option['hard_failures']=len(route_obstructions(context,net,option['route'],thread_definitions,definitions,modifier_definitions))
            option['risk']=proximity_risk(context,net,option['route'],definitions,thread_definitions)
            option['cost']=route_cost(context,option['route'])
            return actual
        # Pinned candidates are materialized directly; enumerating their entire
        # neighbourhood again would multiply the cost of each exact attempt.
        choices = ([combination[net.id]] if combination else [] if net.routing_variant else
                   route_options(resolved,net,definitions=definitions,thread_definitions=thread_definitions,
                                 modifier_definitions=modifier_definitions,snapshot=snapshot))
        if net.routing_variant:
            if net.routing_variant.startswith('axial_'):
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
        if net.routing_variant:
            original=route
            route,_=snapshot.simplify(resolved,net,route)
            selected['pruned_ids']=sorted({f.id for f in original}-{f.id for f in route})
            selected['cost']=route_cost(resolved,route)
            selected['risk']=proximity_risk(resolved,net,route,definitions,thread_definitions)
        resolved.features.extend(route)
        if len(resolved.features) > 120:
            raise ValueError('Generated design exceeds 120 physical features; reduce routing complexity')
        candidates.append(dict(net=net.id, axis_order=selected['key'].split(':')[0], variant=selected['key'], proximity_risk=selected['risk'],
                               objective=route_objective(resolved,route,selected['risk'],definitions),
                               pruned_drillings=selected.get('pruned_ids',[]),
                               sizing=sizing[net.id],
                               **route_margin(design,route),
                               candidates=max(1,len(choices)), drillings=len(route), plugs=sum(f.plugged for f in route),
                               length_mm=round(sum(f.depth for f in route),2), status='PROPOSAL_REQUIRES_EXACT_VALIDATION'))
    if len(automatic)<=2 and any(route_obstructions(resolved,n,[f for f in resolved.features if f.route_net==n.id],
                              thread_definitions,definitions,modifier_definitions)
           for n in resolved.nets if n.routing=='automatic'):
        combination = _complete_route_combination(resolved,definitions,thread_definitions,modifier_definitions,snapshot)
        if combination:
            resolved.features = [f for f in resolved.features if f.route_net not in automatic]
            for net in sorted((n for n in resolved.nets if n.routing=='automatic'),key=lambda n:n.id):
                option = combination[net.id]
                route = option['route']
                resolved.features.extend(route)
                metadata = next(r for r in candidates if r['net']==net.id)
                metadata.update(variant=option['key'],axis_order=option['key'].split(':')[0],
                                proximity_risk=option['risk'],drillings=len(route),
                                plugs=sum(f.plugged for f in route),
                                length_mm=round(sum(f.depth for f in route),2),
                                **route_margin(design,route))
    # One bounded repair sweep revisits BOTH sides of observed inter-net obstacles.
    # Explicit variants/frozen geometry are preserved. Reuse this snapshot's
    # pruning evidence; the sweep does not perform authoritative validation.
    for net in sorted(resolved.nets,key=lambda n:n.id):
        if net.routing!='automatic' or net.routing_variant:continue
        current=[f for f in resolved.features if f.route_net==net.id]
        failures=route_obstructions(resolved,net,current,thread_definitions,definitions,modifier_definitions)
        if not failures:continue
        context=resolved.model_copy(deep=True)
        context.features=[f for f in context.features if f.route_net!=net.id]
        option=route_options(context,net,definitions=definitions,thread_definitions=thread_definitions,
                             modifier_definitions=modifier_definitions,snapshot=snapshot)[0]
        if net.flow_lpm:
            try:
                actual=tool_size(option,context)
                net.diameter=actual['diameter_mm']
            except ValueError:
                continue
        if option['hard_failures']>=len(failures) or len(context.features)+len(option['route'])>120:continue
        resolved.features=context.features+option['route']
        metadata=next(r for r in candidates if r['net']==net.id)
        metadata.update(variant=option['key'],axis_order=option['key'].split(':')[0],proximity_risk=option['risk'],
                        sizing=actual if net.flow_lpm else metadata['sizing'],
                        drillings=len(option['route']),plugs=sum(f.plugged for f in option['route']),
                        length_mm=round(sum(f.depth for f in option['route']),2),**route_margin(design,option['route']))
    active = {f.id for f in resolved.features if not f.suppressed}
    for f in resolved.features:
        f.connects_to = [t for t in f.connects_to if t.split(':')[0] in active]
    for n in resolved.nets:
        for k,v in inherited[n.id].items():setattr(n,k,v)
    return resolved, candidates


def alternative_proposals(best, target, routes, report, eligible, inspected, *, repair_only=None, snapshot=None, cad_fallback=False):
    """Conflict-directed bounded neighbourhood, shared by save and optimization.

    Reconsider either implicated net, plus paired moves to escape a one-net local
    minimum. Screening allocates exact work; only exact FAIL/WARNING/cost selects.
    """
    selected={r['net']:r['variant'] for r in routes}
    if repair_only is None:repair_only=bool(report['counts']['FAIL'])
    from .engineering_db import definitions_for_design,thread_definitions_for_design,modifier_definitions_for_design
    definitions=definitions_for_design(target)
    threads=thread_definitions_for_design(target)
    modifiers=modifier_definitions_for_design(target) if any(f.machining_modifiers for f in target.features) else {}
    snapshot=snapshot or _ProposalSnapshot(target,definitions,threads,modifiers)
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
    warning_nets={owner.route_net for check in report['checks'] if check['status']=='WARNING' and check['rule']!='construction_closure'
                  for item in check.get('items',[]) for owner in [by_id.get(str(item).split(':')[0])]
                  if owner and owner.kind=='drilling' and owner.route_net in eligible}
    for net_id in net_ids:
        context=target.model_copy(deep=True)
        context.features=[f for f in context.features if f.route_net!=net_id]
        net=next(n for n in context.nets if n.id==net_id)
        options=[o for o in route_options(context,net,expanded=bool(report['counts']['FAIL']),definitions=definitions,
                                          thread_definitions=threads,modifier_definitions=modifiers,snapshot=snapshot) if o['key']!=selected[net_id]]
        screened=sorted(options,key=lambda o:(route_objective(context,o['route'],o['risk'],definitions),o['key']))
        feasible=[o for o in screened if o['hard_failures']==0]
        shortlist=_strategy_shortlist(context,feasible,definitions,limit=6) if cad_fallback else feasible[:6]
        pool={o['key']:o for o in shortlist}
        pools[net_id]=sorted(options,key=lambda o:(o['hard_failures'],
                                                  route_objective(context,o['route'],o['risk'],definitions),o['key']))[:3]
        moves.extend({net_id:o} for o in pool.values())
    for a,b in sorted(conflicts):
        moves.extend({a:x,b:y} for x,y in itertools.product(pools[a],pools[b]))
    if (not repair_only or cad_fallback) and len(net_ids)>1:
        combination_source=target.model_copy(deep=True)
        for net in combination_source.nets:
            if net.id in eligible:net.routing_variant=None
        combination=_complete_route_combination(combination_source,definitions,threads,modifiers,snapshot,net_ids=eligible,
                                               excluded=inspected if cad_fallback else None)
        if combination:moves.append(combination)
    proposals=[]
    for move in moves:
        variants=tuple(sorted({**selected,**{n:o['key'] for n,o in move.items()}}.items()))
        if variants in inspected:continue
        proposal=target.model_copy(deep=True)
        proposal.features=[f for f in proposal.features if f.route_net not in move]
        proposal.features.extend(f for o in move.values() for f in o['route'])
        if len(proposal.features)>120:continue
        failures=set();risk=0
        for net in proposal.nets:
            if net.routing!='automatic':continue
            route=[f for f in proposal.features if f.route_net==net.id]
            failures.update(route_obstructions(proposal,net,route,threads,definitions,modifiers))
            risk+=proximity_risk(proposal,net,route,definitions,threads)
        drillings=[f for f in proposal.features if f.kind=='drilling' and not f.suppressed]
        changed=[f for f in drillings if f.route_net in move]
        cost=route_cost(proposal,drillings)
        # Prefer bounded, shorter machining before cost-equivalent long/complex
        # alternatives.  A long multi-axis candidate can make an OCCT Boolean
        # disproportionately expensive even when the proxy obstruction count is
        # identical.  Exact checks still decide whether the candidate improves.
        if failures:
            continue
        objective=route_objective(proposal,drillings,definitions=definitions)
        if not repair_only and not cad_fallback:
            current=[f for f in target.features if f.kind=='drilling' and not f.suppressed]
            current_objective=route_objective(target,current,definitions=definitions)
            # Only truly better manufacturing moves spend optimization attempts.
            # Repair mode still considers more expensive routes to cure FAIL.
            if objective>=current_objective and not set(move)&warning_nets:continue
        ranking=(objective,variants)
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
    snapshots=snapshot_cache if snapshot_cache is not None else {}
    from .timing import progress
    if exact:progress('routes' if any(n.routing=='automatic' for n in design.nets) else 'preparing',8)
    target, routes = _resolve_proposals(design,snapshots=snapshots)
    # A stored automatic variant is a proposal, not a frozen engineering route.
    # Moving terminals can invalidate it; Save & Validate must reconsider it too.
    pending = [n for n in design.nets if n.routing == 'automatic']
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
    def evaluate(candidate, reason):
        index=len(attempts)
        base=15+60*index/max_attempts
        if pending:
            if index:progress('alternate',base,candidate=index+1,candidate_limit=max_attempts)
            progress('candidate',base,candidate=index+1,candidate_limit=max_attempts)
        resolved, metadata = _resolve_proposals(candidate,snapshots=snapshots)
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
    best=design.model_copy(deep=True)
    # Pin the baseline before varying one net, avoiding implicit nested searches.
    for net in best.nets:
        if net.routing=='automatic':net.routing_variant=next(r['variant'] for r in routes if r['net']==net.id)
    score,target,routes,chosen,report,geometry=evaluate(best,'Default baseline')
    inspected={tuple(sorted((r['net'],r['variant']) for r in routes))}
    eligible={n.id for n in pending}
    # Only untried, analytically clear candidates spend the exact budget. The
    # eight-candidate/240 s ceilings leave the worker's CAD watchdog intact.
    while True:
        cad_bad=geometry is None or not topology_clear(geometry) or any(
            c['rule']=='step_round_trip' and c['status']=='FAIL' for c in report['checks'])
        snapshot=snapshots.get(_proposal_source_key(best))
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
        elif (cad_fallback or not optimization_done) and len(attempts)<max_attempts and time.monotonic()-started<240:
            if pending:progress('alternate' if score[0] else 'comparison',15+60*len(attempts)/max_attempts)
            kwargs=dict(repair_only=bool(score[0]),snapshot=snapshot)
            if cad_fallback:kwargs['cad_fallback']=True
            proposals=alternative_proposals(best,target,routes,report,eligible,inspected,**kwargs)
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
                    if chosen!=step_exported or len(attempts)<max_attempts and time.monotonic()-started<240:
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
    for f in design.features:
        if not f.route_net or f.suppressed:
            continue
        allowed = nets[f.route_net] | {x.id for x in design.features if x.route_net == f.route_net}
        f.connects_to = sorted(n for n in geometry.nodes if n != f.id and n in allowed
                              and geometry.circuits[n] == f.circuit
                              and geometry.nodes[f.id].intersect(geometry.nodes[n]).Volume() > 1e-6)


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
