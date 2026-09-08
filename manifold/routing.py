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
                points[f'{f.id}:{z.id}'] = tuple(a + b * (z.start + z.end) / 2 for a, b in zip(p, axis))
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


def propose(design, net, order):
    points = terminal_points(design)
    pairs = spanning_pairs(sorted(set(points[m] for m in net.members if m in points)))
    lines = {}
    for a,b in pairs:
        p = list(a)
        for axis in order:
            if abs(p[axis]-b[axis]) < 1e-7:
                continue
            fixed = tuple(round(p[i], 6) for i in range(3) if i != axis)
            key = (axis, fixed)
            lo,hi = sorted((p[axis], b[axis]))
            old = lines.get(key, (lo,hi))
            lines[key] = (min(lo,old[0]), max(hi,old[1])); p[axis] = b[axis]
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
            preference = 0 if net.entry_preference == 'nearest' or (net.entry_preference == 'negative') == (sign > 0) else 10000
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


def resolve_design(design):
    resolved = resolve_parents(design)
    automatic = {n.id for n in resolved.nets if n.routing == 'automatic'}
    resolved.features = [f for f in resolved.features if f.route_net not in automatic]
    candidates = []
    for net in resolved.nets:
        if net.routing != 'automatic':
            continue
        orders = list(itertools.permutations(range(3)))
        if net.preferred_axis != 'auto':
            orders = [o for o in orders if o[0] == 'xyz'.index(net.preferred_axis)]
        choices = []
        for order in orders:
            route = propose(resolved, net, order)
            length = sum(f.depth for f in route)
            plugs = sum(f.plugged for f in route)
            score = length + len(route)*20 + plugs*(150 if design.constraints.priority == 'fewer_plugs' else 30)
            choices.append((score, order, route))
        score, order, route = min(choices, key=lambda c:(c[0],c[1]))
        resolved.features.extend(route)
        if len(resolved.features) > 120:
            raise ValueError('Generated design exceeds 120 physical features; reduce routing complexity')
        candidates.append(dict(net=net.id, axis_order=''.join('xyz'[i] for i in order),
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
