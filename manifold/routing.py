"""Deterministic orthogonal route proposals. Only the BRep validator grants PASS."""
import hashlib
import itertools
import math
from .schema import Feature, ConstructionAccess
from .kinematics import pose, dimensions, FACE_AXES, resolve_parents


def terminal_points(design):
    lib = {d.id: d for d in design.library}
    points = {}
    for f in design.features:
        if f.suppressed or f.kind == 'drilling':
            continue
        p, axis = pose(f, design.block)
        if f.kind == 'cavity':
            for z in lib[f.definition].zones:
                point = [a + b * (z.start + z.end) / 2 for a, b in zip(p, axis)]
                angle = math.radians(f.rotation); u,v,_,_ = FACE_AXES[f.face]
                point[u] += z.offset_u*math.cos(angle)-z.offset_v*math.sin(angle)
                point[v] += z.offset_u*math.sin(angle)+z.offset_v*math.cos(angle)
                points[f'{f.id}:{z.id}'] = tuple(point)
        else:
            points[f.id] = tuple(a + b * f.depth for a, b in zip(p, axis))
    return points


def spanning_pairs(points):
    if not points:
        return []
    visited, rest, pairs = [points[0]], points[1:], []
    while rest:
        _, a, b = min((sum(abs(x-y) for x, y in zip(a,b)), a, b) for a in visited for b in rest)
        pairs.append((a,b)); visited.append(b); rest.remove(b)
    return pairs


def propose(design, net, order, entry=None, detour='direct'):
    points = terminal_points(design)
    pairs = spanning_pairs(sorted(set(points[m] for m in net.members if m in points)))
    lines = {}
    for a,b in pairs:
        waypoints = [a,b]
        if detour != 'direct':
            _,name,side = detour.split('_')
            axis = 'xyz'.index(name)
            offset = (net.diameter + design.rules.minimum_wall) * (1 if side == 'p' else -1)
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
            u,v,_,sign = FACE_AXES[face]
            coaxial = any(f.kind == 'port' and not f.suppressed and f.circuit == net.id and f.face == face
                          and abs(f.u-p[u]) < 1e-6 and abs(f.v-p[v]) < 1e-6 and f.diameter >= net.diameter for f in design.features)
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
    """Minimum distance between finite orthogonal centerline segments, no CAD imports."""
    ai = next((i for i in range(3) if abs(a[i]-b[i]) > 1e-7),0)
    ci = next((i for i in range(3) if abs(c[i]-d[i]) > 1e-7),0)
    if ai == ci:
        gap = max(0, min(a[ai],b[ai])-max(c[ci],d[ci]), min(c[ci],d[ci])-max(a[ai],b[ai]))
        return math.sqrt(gap*gap + sum((a[i]-c[i])**2 for i in range(3) if i != ai))
    pa,pb = list(a),list(c)
    pa[ai] = max(min(a[ai],b[ai]),min(max(a[ai],b[ai]),c[ai]))
    pb[ci] = max(min(c[ci],d[ci]),min(max(c[ci],d[ci]),a[ci]))
    return math.dist(pa,pb)


def segment(feature, block, start=0, end=None):
    p,d = pose(feature,block)
    if end is None:
        tip = 0 if feature.tip_angle == 180 else feature.diameter/2/math.tan(math.radians(feature.tip_angle/2))
        end = feature.depth+tip
    return tuple(a+b*start for a,b in zip(p,d)), tuple(a+b*end for a,b in zip(p,d))


def cylinder_bounds(feature, block, start, end, diameter):
    a,b = segment(feature,block,start,end)
    axis = FACE_AXES[feature.face][2]
    return [(min(a[i],b[i])-(diameter/2 if i != axis else 0),
             max(a[i],b[i])+(diameter/2 if i != axis else 0)) for i in range(3)]


def proximity_risk(design, net, route):
    """Conservative cylinder/centerline screen. This is a ranking estimate, never validation."""
    risk = 0.0
    lib = {d.id:d for d in design.library}
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
            if other.kind == 'cavity':
                definition = lib[other.definition]
                allowed = [z for z in definition.zones if other.circuits[z.id] == net.id and f'{other.id}:{z.id}' in net.members]
                for stage in definition.stages:
                    breaks = sorted({stage.start,stage.end,*[v for z in allowed for v in (z.start,z.end) if stage.start < v < stage.end]})
                    for start,end in zip(breaks,breaks[1:]):
                        if any(z.start <= start and end <= z.end for z in allowed):
                            continue
                        c,d = segment(other,design.block,start,end)
                        clearance = segment_distance(a,b,c,d)-radius-stage.diameter/2
                        if allowed:
                            # Flat axial interval bounds avoid falsely extending a sealing land as a spherical cap.
                            rb = cylinder_bounds(bore,design.block,0,bore.depth,bore.diameter)
                            cb = cylinder_bounds(other,design.block,start,end,stage.diameter)
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
                diameter = lib[other.definition].clearance_diameter if other.kind == 'cavity' else other.clearance_diameter
                if other.kind == 'drilling' and not other.plugged:
                    continue
                gap = math.hypot(bore.u-other.u,bore.v-other.v)-(bore.clearance_diameter+diameter)/2
                risk += max(0,design.rules.minimum_access_gap-gap)*2
    return round(risk,6)


def route_cost(design, route):
    length = sum(f.depth for f in route)
    plugs = sum(f.plugged for f in route)
    return round(length + len(route)*(60 if design.constraints.priority == 'simple_machining' else 20)
                 + plugs*(150 if design.constraints.priority == 'fewer_plugs' else 30),6)


def route_options(design, net):
    orders = list(itertools.permutations(range(3)))
    if net.preferred_axis != 'auto':
        orders = [o for o in orders if o[0] == 'xyz'.index(net.preferred_axis)]
    entries = ['nearest','negative','positive'] if net.entry_preference == 'nearest' else [net.entry_preference]
    options, seen = [],set()
    detours = ['direct'] + [f'offset_{axis}_{side}' for axis in 'xyz' for side in 'pm']
    for order,entry,detour in itertools.product(orders,entries,detours):
        key = ''.join('xyz'[i] for i in order)+':'+entry+':'+detour
        route = propose(design,net,order,entry,detour)
        signature = tuple((f.face,round(f.u,5),round(f.v,5),round(f.depth,5),f.plugged) for f in route)
        if signature in seen:
            continue
        seen.add(signature)
        risk = proximity_risk(design,net,route)
        options.append(dict(key=key,route=route,risk=risk,cost=route_cost(design,route)))
    return sorted(options,key=lambda o:(o['risk'],o['cost'],o['key']))


def resolve_design(design):
    resolved = resolve_parents(design)
    automatic = {n.id for n in resolved.nets if n.routing == 'automatic'}
    resolved.features = [f for f in resolved.features if f.route_net not in automatic]
    candidates = []
    for net in resolved.nets:
        if net.routing != 'automatic':
            continue
        choices = route_options(resolved,net)
        if net.routing_variant:
            order,entry,detour = net.routing_variant.split(':')
            if sorted(order) != ['x','y','z']:
                raise ValueError('Routing variant must use each axis once')
            route = propose(resolved,net,tuple('xyz'.index(i) for i in order),entry,detour)
            selected = dict(key=net.routing_variant,route=route,risk=proximity_risk(resolved,net,route),cost=route_cost(resolved,route))
        else:
            selected = choices[0]
            route = selected['route']
        resolved.features.extend(route)
        if len(resolved.features) > 120:
            raise ValueError('Generated design exceeds 120 physical features; reduce routing complexity')
        candidates.append(dict(net=net.id, axis_order=selected['key'].split(':')[0], variant=selected['key'], proximity_risk=selected['risk'],
                               candidates=len(choices), drillings=len(route), plugs=sum(f.plugged for f in route),
                               length_mm=round(sum(f.depth for f in route),2), status='PROPOSAL_REQUIRES_EXACT_VALIDATION'))
    active = {f.id for f in resolved.features if not f.suppressed}
    for f in resolved.features:
        f.connects_to = [t for t in f.connects_to if t.split(':')[0] in active]
    return resolved, candidates


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
