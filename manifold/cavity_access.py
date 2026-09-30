"""Analytic deep-side terminal proposals; ordinary cut screens and OCCT remain authoritative."""
import itertools
import math
from .kinematics import FACE_AXES, dimensions, pose
from .schema import Feature


def _axis_core(cut, depth, source):
    """Radius of a disk about the cavity axis wholly inside an actual machining cut."""
    if not cut['start'] <= depth <= cut['end']:
        return 0
    offset = math.hypot(cut['feature'].u-source.u, cut['feature'].v-source.v)
    radius = cut['radius_start']+(cut['radius_end']-cut['radius_start'])*(depth-cut['start'])/(cut['end']-cut['start'])
    core = radius-offset
    if cut['inner_radius']:
        core = min(core, offset-cut['inner_radius'])
    return max(0, core)


def _contact(cuts, source, zone, tip_start, shoulder, radius):
    """Conservative volume integral and inscribed section at its centroid, without BReps.

    Integrate the piecewise linear radius of an inscribed disk analytically.
    Source offsets, annuli and tapered bottoms are retained. Crossing points of
    the profiles are integration boundaries, so flow opening needs no sampled
    approximation or arbitrary drilling-depth allowance.
    """
    zone_core = zone.diameter/2-math.hypot(zone.offset_u, zone.offset_v)
    low, high = max(tip_start, zone.start), zone.end
    if zone_core <= 0 or high <= low:
        return 0, 0
    breaks = sorted({low, high, *(x for c in cuts for x in (c['start'], c['end']) if low < x < high),
                     *([shoulder] if low < shoulder < high else [])})
    volume = moment = 0
    for a,b in zip(breaks, breaks[1:]):
        active = [c for c in cuts if c['start'] <= a and b <= c['end']]
        tip_line = (0,radius) if a >= shoulder else (radius/(shoulder-tip_start),-tip_start*radius/(shoulder-tip_start))
        lines = [(0,0),(0,zone_core),tip_line]
        for cut in active:
            offset = math.hypot(cut['feature'].u-source.u,cut['feature'].v-source.v)
            slope = (cut['radius_end']-cut['radius_start'])/(cut['end']-cut['start'])
            lines.append((slope,cut['radius_start']-offset-slope*cut['start']))
            if cut['inner_radius']:lines.append((0,offset-cut['inner_radius']))
        crossings = {a,b}
        for (m,c),(n,d) in itertools.combinations(lines,2):
            if abs(m-n) > 1e-12:
                x = (d-c)/(m-n)
                if a < x < b:crossings.add(x)
        def profile(depth):
            core = max((_axis_core(c,depth,source) for c in active),default=0)
            return max(0,min(zone_core,core,tip_line[0]*depth+tip_line[1]))
        ordered = sorted(crossings)
        for first,last in zip(ordered,ordered[1:]):
            r0,r1 = profile(first),profile(last)
            width,delta = last-first,r1-r0
            part = math.pi*width*(r0*r0+r0*r1+r1*r1)/3
            volume += part
            moment += first*part+math.pi*width**2*(r0*r0/2+2*r0*delta/3+delta*delta/4)
    if not volume:
        return 0, 0
    center = moment/volume
    core = max((_axis_core(c,center,source) for c in cuts), default=0)
    tip_radius = radius if center >= shoulder else radius*max(0,center-tip_start)/(shoulder-tip_start)
    return volume, math.pi*min(zone_core,core,tip_radius)**2


def cavity_terminal_candidates(design, net, definitions, threads=None, modifiers=None):
    """Optional coaxial construction holes, keyed by their assigned hydraulic member.

    Only a source machining corridor reaching this window qualifies. In particular,
    no other assigned window is subtracted from protection during this calculation.
    A missing/offset opening, deeper cone, land or seat cannot be bypassed by ID or
    zone ordering. All other obstacles are still screened on the complete route.
    """
    from .routing import (_manufacturing_cuts, _protected_source_cuts, _cuts_too_close,
                          port_interface_diameter, route_margin)
    from .flow import required_area
    candidates = {}
    sizes = dimensions(design.block)
    radius = net.diameter/2
    tip = radius/math.tan(math.radians(118/2))
    area = required_area(net.flow_lpm,net.velocity_limit) if net.flow_lpm else 0
    for source in design.features:
        if source.suppressed or source.kind != 'cavity' or not source.definition:
            continue
        definition = definitions[source.definition]
        if not definition.usable or not definition.active:
            continue
        u,v,axis,sign = FACE_AXES[source.face]
        opposite = next(face for face,axes in FACE_AXES.items() if axes[2] == axis and axes[3] == -sign)
        if opposite in design.constraints.forbidden_drilling_faces:
            continue
        cuts = list(_manufacturing_cuts(source,definitions,threads or {},modifiers or {}))
        for zone in definition.zones:
            member = f'{source.id}:{zone.id}'
            if member not in net.members or source.circuits.get(zone.id) != net.id:
                continue
            # Actual cut/window intersection, not a nominal cavity-bottom depth.
            relevant = [c for c in cuts if c['start'] < zone.end and c['end'] > zone.start]
            if not relevant:
                continue
            contact = max(min(c['end'],zone.end) for c in relevant)
            low = sizes[axis]-contact-tip
            high = sizes[axis]-zone.start-tip-1e-5
            def sufficient(depth):
                volume,opening = _contact(relevant,source,zone,sizes[axis]-depth-tip,
                                          sizes[axis]-depth,radius)
                return volume >= design.rules.minimum_overlap_volume*1.001 and opening+1e-8 >= area
            if high <= low or not sufficient(high):
                continue
            for _ in range(28):
                middle = (low+high)/2
                if sufficient(middle): high = middle
                else: low = middle
            depth = math.ceil(high*1e6)/1e6
            if depth <= 9:
                continue
            coaxial = any(f.kind == 'port' and not f.suppressed and f.id in net.members
                          and f.circuit == net.id and f.face == opposite
                          and abs(f.u-source.u)<1e-6 and abs(f.v-source.v)<1e-6
                          and port_interface_diameter(f,definitions) >= net.diameter for f in design.features)
            probe = Feature(id='AXIAL-PROBE',kind='drilling',face=opposite,u=source.u,v=source.v,
                            diameter=net.diameter,depth=depth,circuit=net.id,route_net=net.id,
                            plugged=not coaxial,clearance_diameter=max(16,net.diameter+8),clearance_height=15)
            if route_margin(design,[probe])['estimated_min_wall_mm'] < design.rules.minimum_wall:
                continue
            probe_cuts = list(_manufacturing_cuts(probe,definitions,threads or {},modifiers or {}))
            assigned_only = net.model_copy(update=dict(members=[member]))
            if any(_cuts_too_close(probe_cuts,protected,design.block,0 if own else design.rules.minimum_wall)
                   for protected,own in _protected_source_cuts(source,assigned_only,definitions,threads or {},modifiers or {})):
                continue
            candidates[member] = probe
    return candidates


def axial_route(design, net, definitions, variant, candidates=None, threads=None, modifiers=None):
    """Regenerate a stable terminal strategy, including its true opposite-face access."""
    from .routing import propose, terminal_points, segment_depth, add_construction_access
    import hashlib
    strategy,order,entry = variant.split(':')
    _,mask,level = strategy.split('_')
    mask,level = int(mask),int(level)
    members = sorted(net.members)
    if sorted(order) != list('xyz') or mask <= 0 or mask >> len(members) or level not in (0,1):
        return None
    selected = [member for i,member in enumerate(members) if mask & (1 << i)]
    candidates = candidates if candidates is not None else cavity_terminal_candidates(design,net,definitions,threads,modifiers)
    if not selected or any(member not in candidates for member in selected):
        return None
    points = terminal_points(design,definitions)
    overrides = {}
    for member in selected:
        bore = candidates[member]
        origin,direction = pose(bore,design.block)
        # Junctions stay inside the bore's full cylinder, clear of the source
        # body and plug. One basic plane follows other terminals; the other is
        # the closest conservative transverse junction on the deep side.
        end = bore.depth-net.diameter/2-design.rules.minimum_wall
        start = (bore.plug_length if bore.plugged else 0)+net.diameter/2+design.rules.minimum_wall
        if end < start:
            return None
        desired = end
        others = [p for key,p in points.items() if key in net.members and key not in selected]
        if level == 1 and others:
            desired = min((sum((p[i]-origin[i])*direction[i] for i in range(3)) for p in others),
                          key=lambda depth:abs(depth-end))
        depth = min(end,max(start,desired))
        overrides[member] = tuple(origin[i]+direction[i]*depth for i in range(3))
    route = propose(design,net,tuple('xyz'.index(a) for a in order),entry,definitions=definitions,terminal_overrides=overrides)
    # Those accesses refer to the final trunk, which changes when its axial
    # connector becomes an opposite-face first-contact hole. Reapply them below.
    access_ids = {access.id for access in net.construction_access}
    route = [f for f in route if f.id not in access_ids]
    digest = hashlib.sha256(net.id.encode()).hexdigest()[:8]
    for member in selected:
        bore = candidates[member].model_copy(deep=True)
        bore.id = f'R-{digest}-AX{members.index(member)}'
        axis = FACE_AXES[bore.face][2]
        kept = []
        for feature in route:
            if (FACE_AXES[feature.face][2] == axis and not feature.direction
                    and abs(feature.u-bore.u)<1e-6 and abs(feature.v-bore.v)<1e-6):
                # Replace a coaxial connector by the genuine entry. Never
                # extend the stop to cover a connector beyond the safe window.
                p,d = pose(feature,design.block)
                origin,direction = pose(bore,design.block)
                depths = [sum((p[i]+d[i]*t-origin[i])*direction[i] for i in range(3))
                          for t in (0,segment_depth(feature))]
                if feature.face == bore.face and max(depths) > segment_depth(bore)+1e-6:
                    return None
                continue
            kept.append(feature)
        route = kept+[bore]
    return add_construction_access(design,net,route)


def axial_route_candidates(design, net, definitions, threads=None, modifiers=None):
    candidates = cavity_terminal_candidates(design,net,definitions,threads,modifiers)
    members = sorted(net.members)
    masks = {1 << members.index(member) for member in candidates}
    if masks: masks.add(sum(masks))
    orders = [o for o in itertools.permutations('xyz') if net.preferred_axis == 'auto' or o[0] == net.preferred_axis]
    entries = ('nearest','negative','positive') if net.entry_preference == 'nearest' else (net.entry_preference,)
    for mask,level,order,entry in itertools.product(sorted(masks),range(2),orders,entries):
        key = f'axial_{mask}_{level}:{"".join(order)}:{entry}'
        route = axial_route(design,net,definitions,key,candidates,threads,modifiers)
        if route is not None:
            yield key,route
