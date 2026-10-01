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
    parts=variant.split(':')
    if len(parts) not in (3,4):return None
    strategy,order,entry=parts[:3]
    changes=parts[3].split('+') if len(parts)==4 else []
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
    connector_bends={}
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
        bends=[]
        for change in changes:
            tokens=change.split('_');owner=tokens[0]
            if int(owner[1:])!=members.index(member):continue
            coordinate=float(tokens[-1])
            if owner.startswith('j'):
                axis=FACE_AXES[bore.face][2]
                depth=(coordinate-origin[axis])*direction[axis]
                if not start<=depth<=end:return None
            elif owner.startswith('c') and len(tokens)==3:
                axis='xyz'.index(tokens[1]);bends.append((axis,coordinate))
                if axis==FACE_AXES[bore.face][2] and not start<=(coordinate-origin[axis])*direction[axis]<=end:return None
            else:return None
        overrides[member] = tuple(origin[i]+direction[i]*depth for i in range(3))
        if bends:connector_bends[overrides[member]]=(tuple(bends),FACE_AXES[bore.face][2])
    if any(int(change.split('_')[0][1:]) not in [members.index(member) for member in selected] for change in changes):return None
    route = propose(design,net,tuple('xyz'.index(a) for a in order),entry,definitions=definitions,
                    terminal_overrides=overrides,connector_bends=connector_bends or None)
    if route is None:return None
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


def _direct_axial_candidates(design, net, definitions, threads=None, modifiers=None):
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


def _axial_direct_catalog(design, net, definitions, threads, modifiers, cache):
    from .routing import route_objective
    automatic={n.id for n in design.nets if n.routing=='automatic'}
    source=design.model_copy(update=dict(features=[f for f in design.features if f.route_net not in automatic]))
    token=(dimensions(source.block),net.model_dump_json(exclude={'routing_variant'}),tuple(net.members),
           tuple(f.model_dump_json(exclude={'connects_to'}) for f in source.features))
    catalogs=cache.setdefault('axial_direct_catalogs',{})
    if token not in catalogs:
        rows=list(_direct_axial_candidates(source,net,definitions,threads,modifiers))
        clear=[];seen=set()
        for key,route in rows:
            signature=tuple(sorted((f.face,f.u,f.v,f.depth,f.diameter,f.plugged,f.tip_angle) for f in route))
            if signature in seen:continue
            seen.add(signature)
            # Eligibility has already certified the fixed cavity approach. A
            # blocked direct connector is precisely the anchor we must detour.
            clear.append((key,route))
        clear.sort(key=lambda row:(route_objective(source,row[1],definitions=definitions),row[0]))
        catalogs[token]=(rows,clear[:2])
    return source,catalogs[token]


def _axial_obstacle_context(source, context, net, definitions, threads, modifiers, cache):
    """Use retained routes when present; otherwise explore real peer axial proposals.

    Peer proposals are hypothetical obstacles for global candidate generation,
    never compatibility facts or selected engineering geometry. Explicit plane
    coordinates in the new variant make regeneration independent of that context.
    """
    context=context.model_copy(update=dict(features=[f for f in context.features if f.route_net!=net.id]))
    present={f.route_net for f in context.features if f.route_net}
    for other in source.nets:
        if (other.id==net.id or other.routing!='automatic' or other.id in present
                or any(f.frozen_net==other.id for f in context.features)):continue
        _,(_,anchors)=_axial_direct_catalog(source,other,definitions,threads,modifiers,cache)
        if anchors:context.features.extend(anchors[0][1])
    return context


def _connector_planes(context, net, route, definitions, threads, modifiers, failures, order):
    from .routing import _manufacturing_cuts,cylinder_bounds,segment_depth,segment,segment_distance
    by_id={f.id:f for f in context.features}
    connectors={f.id:f for f in route if '-AX' not in f.id}
    bores={int(f.id.split('-AX')[-1]):f for f in route if '-AX' in f.id}
    approaches={}
    for member,bore in bores.items():
        axial=FACE_AXES[bore.face][2]
        touching={FACE_AXES[f.face][2] for f in connectors.values() if FACE_AXES[f.face][2]!=axial
                  and segment_distance(*segment(f,context.block),*segment(bore,context.block,end=bore.depth))<(f.diameter+bore.diameter)/2}
        approaches[member]=next(("xyz".index(axis) for axis in reversed(order) if "xyz".index(axis) in touching),None)
    sizes=dimensions(context.block)
    # Orthogonal branches extend their cylinder by one radius past the logical
    # junction, followed by the real drill tip. Reserve that tip when deriving
    # a boundary plane; a centerline-only offset would still leave thin walls.
    tip=net.diameter/2/math.tan(math.radians(118/2))
    margin=net.diameter/2+context.rules.minimum_wall+tip+.1
    rows=set()
    for failure in sorted(failures):
        for key in failure[1:]:
            if key not in connectors:continue
            connector=connectors[key]
            others=[by_id[item] for item in failure[1:] if item in by_id]
            bounds=cylinder_bounds(connector,context.block,0,segment_depth(connector),connector.diameter)
            for other in others:
                pieces=list(_manufacturing_cuts(other,definitions,threads,modifiers))
                regions=[cylinder_bounds(c['feature'],context.block,c['start'],c['end'],2*max(c['radius_start'],c['radius_end'])) for c in pieces]
                if failure[0]=='installation_access':
                    definition=definitions[other.definition] if other.definition else None
                    diameter=definition.clearance_diameter if other.kind=='cavity' and definition else other.clearance_diameter
                    height=definition.clearance_height if other.kind=='cavity' and definition else other.clearance_height
                    regions.append(cylinder_bounds(other,context.block,-height,0,diameter))
                regions=[region for region in regions if not any(a[1]+margin<b[0] or b[1]+margin<a[0] for a,b in zip(bounds,region))]
                for region in regions:
                    for member,bore in bores.items():
                        for axis in range(3):
                            if axis in (FACE_AXES[connector.face][2],approaches[member]):continue
                            center=pose(connector,context.block)[0][axis]
                            for coordinate in (region[axis][0]-margin,region[axis][1]+margin):
                                # An internal cylinder/tip or stage boundary is
                                # not a safe plane inside another relevant cut.
                                if any(r[axis][0]-margin+1e-6<coordinate<r[axis][1]+margin-1e-6 for r in regions):continue
                                if margin<=coordinate<=sizes[axis]-margin:
                                    if axis==FACE_AXES[bore.face][2]:
                                        p,d=pose(bore,context.block)
                                        depth=(coordinate-p[axis])*d[axis]
                                        first=(bore.plug_length if bore.plugged else 0)+margin-.1
                                        last=bore.depth-margin+.1
                                        if not first<=depth<=last:continue
                                    rows.add((round(abs(coordinate-center),6),member,axis,round(coordinate,6)))
    return sorted(rows)


def axial_connector_candidates(design, net, definitions, threads=None, modifiers=None, context=None, cache=None):
    """At most twelve conflict-derived local connector/junction alternatives."""
    from .routing import route_obstructions
    threads,modifiers=threads or {},modifiers or {}
    cache=cache if cache is not None else {}
    source,(_,anchors)=_axial_direct_catalog(design,net,definitions,threads,modifiers,cache)
    if not anchors:return
    context=_axial_obstacle_context(source,context or design,net,definitions,threads,modifiers,cache)
    context_token=(net.id,tuple(f.model_dump_json(exclude={'connects_to'}) for f in context.features),
                   tuple(key for key,_ in anchors))
    plans=cache.setdefault('axial_connector_plans',{})
    if context_token in plans:
        yield from plans[context_token];return
    result=[];seen=set()
    for key,direct in anchors:
        failures=route_obstructions(context,net,direct,threads,definitions,modifiers,cache)
        if not failures:continue
        planes=_connector_planes(context,net,direct,definitions,threads,modifiers,failures,key.split(':')[1])
        # The nearest safe boundary on each perpendicular axis, plus one opposite
        # side. No plane Cartesian product and no arbitrary depth sampling.
        selected=[];axes=set()
        for row in planes:
            if row[2] not in axes:selected.append(row);axes.add(row[2])
            if len(selected)==2:break
        for row in planes:
            if row not in selected and row[2] in axes:selected.append(row);break
        suffixes=[]
        for _,member,axis,coordinate in selected:
            token=f'{coordinate:.6f}'.rstrip('0').rstrip('.')
            suffixes.append(f'c{member}_{"xyz"[axis]}_{token}')
            bore=next(f for f in direct if f.id.endswith(f'-AX{member}'))
            if axis==FACE_AXES[bore.face][2]:suffixes.append(f'j{member}_{token}')
        if len(selected)>=2 and selected[0][1]==selected[1][1]:
            tokens=[f'c{m}_{"xyz"[axis]}_{coord:.6f}'.rstrip('0').rstrip('.') for _,m,axis,coord in selected[:2]]
            suffixes.append('+'.join(tokens))
        for suffix in suffixes:
            parts=key.split(':')
            entries=[parts[2]]
            if parts[2]=='nearest':entries.append('positive')
            for entry in entries:
                variant=':'.join(parts[:2]+[entry,suffix])
                if variant in seen or len(variant)>80:continue
                seen.add(variant)
                route=axial_route(source,net,definitions,variant,threads=threads,modifiers=modifiers)
                if route is not None:
                    result.append((variant,route))
                    if len(result)==12:break
            if len(result)==12:break
        if len(result)==12:break
    plans[context_token]=result
    yield from result


def axial_route_candidates(design, net, definitions, threads=None, modifiers=None, context=None, cache=None):
    yield from _direct_axial_candidates(design,net,definitions,threads,modifiers)
    yield from axial_connector_candidates(design,net,definitions,threads,modifiers,context,cache)
