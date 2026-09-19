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


def propose(design, net, order, entry=None, detour='direct', definitions=None):
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    points = terminal_points(design,definitions)
    pairs = spanning_pairs(sorted(set(points[m] for m in net.members if m in points)))
    lines = {}
    for a,b in pairs:
        waypoints = [a,b]
        if detour != 'direct':
            _,name,side = detour.split('_')
            axis = 'xyz'.index(name)
            offset = (net.diameter + design.rules.minimum_wall) * (1 if side[0] == 'p' else -1) * (2 if side.endswith('2') else 1)
            coordinate = (a[axis] + b[axis])/2 + offset
            margin = max(12, net.diameter/2 + design.rules.minimum_wall)
            coordinate = max(margin,min(dimensions(design.block)[axis]-margin,coordinate))
            aa,bb = list(a),list(b)
            aa[axis] = bb[axis] = coordinate
            waypoints = [a,tuple(aa),tuple(bb),b]
        for start,end in zip(waypoints,waypoints[1:]):
            p = list(start)
            for axis in order:
                if abs(p[axis]-end[axis]) < 1e-7:
                    continue
                fixed = tuple(round(p[i], 6) for i in range(3) if i != axis)
                key = (axis, fixed)
                lo,hi = sorted((p[axis], end[axis]))
                old = lines.get(key, (lo,hi))
                lines[key] = (min(lo,old[0]), max(hi,old[1])); p[axis] = end[axis]
    sizes = dimensions(design.block)
    features = []
    digest = hashlib.sha256(net.id.encode()).hexdigest()[:8]
    for (axis, fixed), (lo,hi) in sorted(lines.items()):
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
            options.append((preference + depth + (0 if coaxial else 200), face, depth, coaxial))
        _,face,depth,coaxial = min(options)
        u,v,_,_ = FACE_AXES[face]
        features.append(Feature(id=f'R-{digest}-{len(features)+1}', kind='drilling', face=face, u=p[u], v=p[v],
                                circuit=net.id, diameter=net.diameter, depth=max(depth,9), plugged=not coaxial,
                                route_net=net.id, clearance_diameter=max(16,net.diameter+8), clearance_height=15))
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


def segment(feature, block, start=0, end=None):
    p,d = pose(feature,block)
    if end is None:
        tip = 0 if feature.tip_angle == 180 else feature.diameter/2/math.tan(math.radians(feature.tip_angle/2))
        end = feature.depth+tip
    return tuple(a+b*start for a,b in zip(p,d)), tuple(a+b*end for a,b in zip(p,d))


def cylinder_bounds(feature, block, start, end, diameter):
    a,b = segment(feature,block,start,end)
    _,direction=pose(feature,block)
    return [(min(a[i],b[i])-diameter/2*math.sqrt(max(0,1-direction[i]**2)),
             max(a[i],b[i])+diameter/2*math.sqrt(max(0,1-direction[i]**2))) for i in range(3)]


def simple_routes(design,net,definitions=None):
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
    return routes


def proximity_risk(design, net, route, definitions=None):
    """Conservative cylinder/centerline screen. This is a ranking estimate, never validation."""
    risk = 0.0
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    dims = dimensions(design.block)
    for bore in route:
        a,b = segment(bore,design.block)
        radius = bore.diameter/2
        u,v,axis,sign = FACE_AXES[bore.face]
        for i in (u,v):
            risk += max(0,design.rules.minimum_wall-min(a[i],dims[i]-a[i])+radius)*4
        risk += max(0,design.rules.minimum_wall-(dims[axis]-b[axis] if sign>0 else b[axis]))*4
        for other in design.features:
            if other.suppressed or other.route_net == net.id:
                continue
            if other.definition:
                definition = definitions[other.definition]
                allowed = [z for z in definition.zones
                           if (other.circuits[z.id] if other.kind=='cavity' else other.circuit) == net.id
                           and (f'{other.id}:{z.id}' if other.kind=='cavity' else other.id) in net.members]
                # Rank complete mapped machining, not the port's hydraulic summary.
                # Cones/annuli use conservative outer cylinders in this proxy only.
                for stage in definition.cutting_primitives or definition.stages:
                    offset_u,offset_v=getattr(stage,'offset_u',0),getattr(stage,'offset_v',0)
                    angle=math.radians(other.rotation)
                    positioned=other.model_copy(update=dict(u=other.u+offset_u*math.cos(angle)-offset_v*math.sin(angle),
                                                           v=other.v+offset_u*math.sin(angle)+offset_v*math.cos(angle)))
                    diameter=max(stage.diameter,getattr(stage,'end_diameter',0))
                    windows=[z for z in allowed if abs(z.offset_u-offset_u)<1e-6 and abs(z.offset_v-offset_v)<1e-6]
                    breaks = sorted({stage.start,stage.end,*[v for z in windows for v in (z.start,z.end) if stage.start < v < stage.end]})
                    for start,end in zip(breaks,breaks[1:]):
                        if any(z.start <= start and end <= z.end for z in windows):
                            continue
                        c,d = segment(positioned,design.block,start,end)
                        clearance = segment_distance(a,b,c,d)-radius-diameter/2
                        if windows:
                            # Flat axial interval bounds avoid falsely extending a sealing land as a spherical cap.
                            rb = cylinder_bounds(bore,design.block,0,bore.depth,bore.diameter)
                            cb = cylinder_bounds(positioned,design.block,start,end,diameter)
                            penetration = min(min(x[1],y[1])-max(x[0],y[0]) for x,y in zip(rb,cb))
                            risk += max(0,penetration)*8
                        else:
                            risk += max(0,design.rules.minimum_wall-clearance)*(8 if clearance<0 else 1)
            else:
                if other.circuit == net.id:
                    continue
                c,d = segment(other,design.block)
                clearance = segment_distance(a,b,c,d)-radius-other.diameter/2
                risk += max(0,design.rules.minimum_wall-clearance)*(10 if clearance<0 else 1)
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
    target=design.rules.minimum_wall+design.constraints.preferred_wall_margin
    penalty=sum(max(0,target-c)**2 for c in clearances)*2
    return dict(target_mm=target,estimated_min_wall_mm=min(clearances) if clearances else None,margin_penalty=round(penalty,6))


def route_cost(design, route):
    length = sum(f.depth for f in route)
    plugs = sum(f.plugged for f in route)
    return round(length + len(route)*(60 if design.constraints.priority == 'simple_machining' else 20)
                 + plugs*(150 if design.constraints.priority == 'fewer_plugs' else 30)
                 + route_margin(design,route)['margin_penalty'],6)


def route_obstructions(design, net, route):
    """Cheap, sufficient evidence of hard failure, never a feasibility certificate.

    Capsules INSIDE straight cylindrical cuts prove contact/insufficient wall without
    treating the usual outer capsule proxy (especially its end caps) as exact geometry.
    Source profiles, tips, hydraulic openings and connectivity still need OCCT.
    """
    failures = set()
    obstacles=[f for f in design.features if f.route_net!=net.id]+route
    for bore in route:
        if route_margin(design,[bore])['estimated_min_wall_mm'] < design.rules.minimum_wall-1e-6:
            failures.add(('external_wall',bore.id))
        radius=bore.diameter/2
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
                    tip=0 if f.tip_angle==180 else f.diameter/2/math.tan(math.radians(f.tip_angle/2))
                    bounds.append(cylinder_bounds(f,design.block,0,f.depth+tip,f.diameter))
                if not any(x[1]<y[0]-1e-6 or y[1]<x[0]-1e-6 for x,y in zip(*bounds)):
                    continue
            r=other.diameter/2
            if other.depth < 2*r:continue
            c,d=segment(other,design.block,r,other.depth-r)
            clearance=segment_distance(a,b,c,d)-radius-r
            if clearance < design.rules.minimum_wall-1e-6:
                failures.add(('feature_wall' if other.circuit==net.id else 'cross_net_wall',*sorted((bore.id,other.id))))
    return failures


def route_options(design, net, *, expanded=False, definitions=None):
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    orders = list(itertools.permutations(range(3)))
    if net.preferred_axis != 'auto':
        orders = [o for o in orders if o[0] == 'xyz'.index(net.preferred_axis)]
    entries = ['nearest','negative','positive'] if net.entry_preference == 'nearest' else [net.entry_preference]
    options, seen = [],set()
    for i,route in enumerate(simple_routes(design,net,definitions)):
        options.append(dict(key=f'simple_{i}',route=route,risk=proximity_risk(design,net,route,definitions),cost=route_cost(design,route)))
    sides=('p','m','p2','m2') if expanded else ('p','m')
    detours = ['direct'] + [f'offset_{axis}_{side}' for axis in 'xyz' for side in sides]
    for order,entry,detour in itertools.product(orders,entries,detours):
        key = ''.join('xyz'[i] for i in order)+':'+entry+':'+detour
        route = propose(design,net,order,entry,detour,definitions)
        signature = tuple((f.face,round(f.u,5),round(f.v,5),round(f.depth,5),f.plugged) for f in route)
        if signature in seen:
            continue
        seen.add(signature)
        risk = proximity_risk(design,net,route,definitions)
        options.append(dict(key=key,route=route,risk=risk,cost=route_cost(design,route)))
    permitted = [o for o in options if all(f.face not in design.constraints.forbidden_drilling_faces for f in o['route'])]
    # Keep an explicitly failing proposal if the constraint makes every candidate impossible.
    # The validator reports the conflict; never remove a required connection to hide it.
    for option in options:
        option['hard_failures']=len(route_obstructions(design,net,option['route']))
    if not expanded and all(o['hard_failures'] for o in (permitted or options)):
        return route_options(design,net,expanded=True,definitions=definitions)
    return sorted(permitted or options,key=lambda o:(o['hard_failures'],o['cost']+o['risk'],o['cost'],o['key']))


@timed('route.proposal')
def _resolve_proposals(design):
    resolved = resolve_parents(design)
    from .engineering_db import definitions_for_design,tool_definitions
    definitions=definitions_for_design(resolved)
    from .sizing import route_sizing
    tools=tool_definitions('drill',unit=resolved.project_context)
    sizing={n.id:route_sizing(n,tools=tools,required_depth=max(dimensions(resolved.block))) for n in resolved.nets}
    for net in resolved.nets:
        if net.routing=='automatic':net.diameter=sizing[net.id]['diameter_mm']
    automatic = {n.id for n in resolved.nets if n.routing == 'automatic'}
    resolved.features = [f for f in resolved.features if f.route_net not in automatic]
    candidates = []
    for net in sorted(resolved.nets,key=lambda n:n.id):
        if net.routing != 'automatic':
            continue
        # Pinned candidates are materialized directly; enumerating their entire
        # neighbourhood again would multiply the cost of each exact attempt.
        choices = [] if net.routing_variant else route_options(resolved,net,definitions=definitions)
        if net.routing_variant:
            if net.routing_variant.startswith('simple_'):
                choices=[dict(key=f'simple_{i}',route=r,risk=proximity_risk(resolved,net,r,definitions),cost=route_cost(resolved,r))
                         for i,r in enumerate(simple_routes(resolved,net,definitions))]
                selected=next((o for o in choices if o['key']==net.routing_variant),None)
                if selected is None:
                    choices=route_options(resolved,net,definitions=definitions)
                    selected=choices[0]  # Moved/reassigned terminals invalidate the old proposal.
                route=selected['route']
            else:
                order,entry,detour = net.routing_variant.split(':')
                if sorted(order) != ['x','y','z']:
                    raise ValueError('Routing variant must use each axis once')
                route = propose(resolved,net,tuple('xyz'.index(i) for i in order),entry,detour,definitions)
                selected = dict(key=net.routing_variant,route=route,risk=proximity_risk(resolved,net,route,definitions),cost=route_cost(resolved,route))
        else:
            selected = choices[0]
            route = selected['route']
        resolved.features.extend(route)
        if len(resolved.features) > 120:
            raise ValueError('Generated design exceeds 120 physical features; reduce routing complexity')
        candidates.append(dict(net=net.id, axis_order=selected['key'].split(':')[0], variant=selected['key'], proximity_risk=selected['risk'],
                               sizing=sizing[net.id],
                               **route_margin(design,route),
                               candidates=max(1,len(choices)), drillings=len(route), plugs=sum(f.plugged for f in route),
                               length_mm=round(sum(f.depth for f in route),2), status='PROPOSAL_REQUIRES_EXACT_VALIDATION'))
    # One bounded repair sweep revisits BOTH sides of observed inter-net obstacles.
    # Explicit variants/frozen geometry are preserved. No CAD or exact search here.
    for net in sorted(resolved.nets,key=lambda n:n.id):
        if net.routing!='automatic' or net.routing_variant:continue
        current=[f for f in resolved.features if f.route_net==net.id]
        failures=route_obstructions(resolved,net,current)
        if not failures:continue
        context=resolved.model_copy(deep=True)
        context.features=[f for f in context.features if f.route_net!=net.id]
        option=route_options(context,net,definitions=definitions)[0]
        if option['hard_failures']>=len(failures) or len(context.features)+len(option['route'])>120:continue
        resolved.features=context.features+option['route']
        metadata=next(r for r in candidates if r['net']==net.id)
        metadata.update(variant=option['key'],axis_order=option['key'].split(':')[0],proximity_risk=option['risk'],
                        drillings=len(option['route']),plugs=sum(f.plugged for f in option['route']),
                        length_mm=round(sum(f.depth for f in option['route']),2),**route_margin(design,option['route']))
    active = {f.id for f in resolved.features if not f.suppressed}
    for f in resolved.features:
        f.connects_to = [t for t in f.connects_to if t.split(':')[0] in active]
    return resolved, candidates


def alternative_proposals(best, target, routes, report, eligible, inspected, *, repair_only=True):
    """Conflict-directed bounded neighbourhood, shared by save and optimization.

    Reconsider either implicated net, plus paired moves to escape a one-net local
    minimum. Screening allocates exact work; only exact FAIL/WARNING/cost selects.
    """
    selected={r['net']:r['variant'] for r in routes}
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
    net_ids=sorted(affected if repair_only else eligible)
    if not net_ids:
        return []
    pools={}; moves=[]
    for net_id in net_ids:
        context=target.model_copy(deep=True)
        context.features=[f for f in context.features if f.route_net!=net_id]
        net=next(n for n in context.nets if n.id==net_id)
        options=[o for o in route_options(context,net,expanded=bool(report['counts']['FAIL'])) if o['key']!=selected[net_id]]
        screened=sorted(options,key=lambda o:(o['hard_failures'],o['risk'],o['cost'],o['key']))
        economical=sorted(options,key=lambda o:(o['cost'],o['key']))
        pool={o['key']:o for o in screened[:3]+economical[:3]}
        pools[net_id]=screened[:2]
        moves.extend({net_id:o} for o in pool.values())
    for a,b in sorted(conflicts):
        moves.extend({a:x,b:y} for x,y in itertools.product(pools[a],pools[b]))
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
            failures.update(route_obstructions(proposal,net,route))
            risk+=proximity_risk(proposal,net,route)
        drillings=[f for f in proposal.features if f.kind=='drilling' and not f.suppressed]
        changed=[f for f in drillings if f.route_net in move]
        cost=route_cost(proposal,drillings)
        # Prefer bounded, shorter machining before cost-equivalent long/complex
        # alternatives.  A long multi-axis candidate can make an OCCT Boolean
        # disproportionately expensive even when the proxy obstruction count is
        # identical.  Exact checks still decide whether the candidate improves.
        complexity=(max((f.depth for f in changed),default=0),len(changed))
        ranking=(len(failures),risk,*complexity,cost,variants) if report['counts']['FAIL'] else (cost,len(failures),risk,*complexity,variants)
        candidate=best.model_copy(deep=True)
        for net in candidate.nets:
            if net.id in move:net.routing_variant=move[net.id]['key']
        proposals.append((ranking,candidate,variants,', '.join(f'{n}: {o["key"]}' for n,o in sorted(move.items()))))
    return sorted(proposals,key=lambda p:p[0])


@timed('route.resolution')
def resolve_design(design, *, exact=True, persist=False, prepared=False):
    """Compare up to six automatic proposals exactly, preserving frozen/manual cuts.

    Exact selection is pure unless an explicit build/engineering decision opts into evidence.
    Proxy risk schedules proposals only. Exact failures, warnings, then machining
    cost determine selection, with the complete multi-net design as context.
    """
    target, routes = _resolve_proposals(design)
    # A stored automatic variant is a proposal, not a frozen engineering route.
    # Moving terminals can invalidate it; Save & Validate must reconsider it too.
    pending = [n for n in design.nets if n.routing == 'automatic']
    if not exact or not pending and not prepared:
        return target, routes
    from .geometry import build_geometry
    from .validation import validate
    from . import store
    import uuid
    folder = store.OUTPUT/'route-selections'/uuid.uuid4().hex if persist else None
    attempts=[]
    skipped=[]
    def evaluate(candidate, reason):
        resolved, metadata = _resolve_proposals(candidate)
        geometry=None
        try:
            geometry=build_geometry(resolved)
            authorize_generated_contacts(resolved,geometry)
            report=validate(resolved,geometry)
            failed=report['counts']['FAIL']
        except Exception as exc:
            geometry=None
            failed=1_000_000
            report=dict(counts=dict(FAIL=1,WARNING=0),checks=[dict(rule='cad_candidate_error',status='FAIL',error=type(exc).__name__,message=str(exc)[:2000])])
        cost=route_cost(resolved,[f for f in resolved.features if f.kind=='drilling' and not f.suppressed])
        index=len(attempts)
        score=(failed,report['counts']['WARNING'],cost)
        if folder:
            store.atomic_json(folder/f'attempt-{index:02}'/'resolved_design.json',resolved.model_dump())
            store.atomic_json(folder/f'attempt-{index:02}'/'validation.json',report)
        attempts.append(dict(reason=reason,score=score,routes=metadata))
        return score,resolved,metadata,index,report,geometry
    best=design.model_copy(deep=True)
    # Pin the baseline before varying one net, avoiding implicit nested searches.
    for net in best.nets:
        if net.routing=='automatic':net.routing_variant=next(r['variant'] for r in routes if r['net']==net.id)
    score,target,routes,chosen,report,geometry=evaluate(best,'Default baseline')
    inspected={tuple(sorted((r['net'],r['variant']) for r in routes))}
    eligible={n.id for n in pending}
    # Authoritative Validate performs the exact baseline plus one focused repair.
    # Broader cost/alternative exploration belongs to the explicit Optimize action;
    # it must not let one pathological OCCT candidate consume the 300 s watchdog.
    attempt_limit=2 if prepared else 6
    while len(attempts)<attempt_limit and not (prepared and score[0]==0):
        proposals=alternative_proposals(best,target,routes,report,eligible,inspected)
        if not proposals:break
        _,candidate,signature,reason=proposals[0]
        inspected.add(signature)
        proposal,_=_resolve_proposals(candidate)
        cost=route_cost(proposal,[f for f in proposal.features if f.kind=='drilling' and not f.suppressed])
        if score[:2]==(0,0) and cost>=score[2]:
            skipped.append(dict(variants=signature,cost=cost,reason='Cannot improve exact PASS at lower machining cost'))
            break
        trial,new_target,new_routes,index,new_report,new_geometry=evaluate(candidate,reason)
        if trial<score:
            best,score,target,routes,chosen,report,geometry=candidate,trial,new_target,new_routes,index,new_report,new_geometry
    if folder:
        store.atomic_json(folder/'summary.json',dict(selected_attempt=chosen,attempts=attempts,skipped=skipped))
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
