"""AI-generation-owned layout search. Never called by Model or the Router.

All route cuts come from the shared Router. These count-bounded analytic
screens allocate space; they do not certify connectivity or manufacturing.
"""
import itertools
import math
from collections import defaultdict

from ..engineering_conditions import effective_net, required_wall
from ..kinematics import dimensions
from ..layout import machining_radius, placement_conflicts
from ..layout_planning import assess, _permissions, _fits


def _distributed_openings(definition):
    """A geometric layout family, never a product/type classification.

    Offset alone does not make a cartridge cavity a mounting pattern. Require
    distinct face-open source windows rather than axial staged cavity zones.
    """
    zones=definition.zones
    return len(zones)>1 and all(abs(z.start)<1e-7 for z in zones) and all(
        math.dist((a.offset_u,a.offset_v),(b.offset_u,b.offset_v))>(a.diameter+b.diameter)/2
        for a,b in itertools.combinations(zones,2))


def _columns(design, definitions, movable, growth_axes, fixed_faces):
    """A coordinated source-column/rear-corridor family, not a packing grid.

    Opposing duplicate profiles may share depth bands but keep independent
    columns. Offset mounting interfaces get a transverse face when permitted.
    Other layouts retain the existing general face-aware proposal family.
    """
    from ..cavity_access import cavity_terminal_candidates
    from ..routing import planning_wall
    target = design.model_copy(deep=True)
    cavities = sorted((f for f in target.features if f.kind == 'cavity'), key=lambda f: f.schematic_id or f.id)
    if len(cavities) < 3 or any(f.id not in movable for f in target.features if not f.route_net):
        return None
    panels = [f for f in cavities if _distributed_openings(definitions[f.definition])]
    columns = [f for f in cavities if f not in panels]
    # This family needs a top/bottom source column and a front mounting panel.
    # No custom axis/direction is reinterpreted. General layouts still have the
    # original analytic proposal path, including all six supported faces.
    if not columns or any(f.direction or f.face not in ('top', 'bottom') for f in columns):
        return None
    groups = defaultdict(list)
    for f in columns:
        groups[f.definition].append(f)
    for group in groups.values():
        for i, f in enumerate(group):
            preferred = 'bottom' if i % 2 else 'top'
            f.face = fixed_faces.get(f.id, preferred)
            if f.face not in ('top', 'bottom'):
                return None
    for f in panels:
        f.face = fixed_faces.get(f.id, 'front')
        if f.face != 'front':
            return None
    bore = max((effective_net(target, n).diameter for n in target.nets), default=0)
    wall = max((planning_wall(target, effective_net(target, n), definitions) for n in target.nets), default=0)
    gap = max(bore + wall, target.rules.minimum_access_gap)
    depth = lambda f: max(p.end for p in definitions[f.definition].cutting_primitives or definitions[f.definition].stages)
    bottom = max((depth(f) for f in columns if f.face == 'bottom'), default=gap)
    top = max((depth(f) for f in columns if f.face == 'top'), default=gap)
    # Separate actual opposite-side source cuts, a common branch band and
    # transverse panel openings. Height grows only by those measured demands.
    height = math.ceil((bottom + top + 4 * gap) / 5) * 5
    if panels:
        spread = max(max(z.offset_v for z in definitions[f.definition].zones) -
                     min(z.offset_v for z in definitions[f.definition].zones) for f in panels)
        height = max(height, math.ceil((bottom + top + spread + 2 * gap) / 5) * 5)
    target.block.height = height
    eligibility = {n.id: cavity_terminal_candidates(target, effective_net(target, n), definitions) for n in target.nets}
    deep = {}
    for name, entries in eligibility.items():
        for member, cut in entries.items():
            if cut.face in ('top', 'bottom'):
                deep[member.split(':')[0]] = name
    counts = {name: sum(deep.get(f.id) == name for f in columns) for name in eligibility}
    major = sorted((name for name in counts if counts[name] > 1), key=lambda name: (-counts[name], name))
    # Keep independent branches of a multi-terminal deep net adjacent. Then
    # retain source order for profiles without deep access and remaining nets.
    columns.sort(key=lambda f: (0, major.index(deep[f.id]), f.schematic_id or f.id) if deep.get(f.id) in major
                 else (1 if f.id not in deep else 2, 0, f.schematic_id or f.id))
    x = gap
    for f in columns:
        radius = machining_radius(definitions[f.definition])
        f.u = x + radius
        x += 2 * radius + gap
    radius = max(machining_radius(definitions[f.definition]) for f in columns)
    row = radius + max((depth(f) for f in panels), default=0) + gap + wall
    for f in columns:
        f.v = row
    target.block.length = math.ceil(x / 5) * 5
    junction_z = (bottom + height - top) / 2
    for f in panels:
        neighbours = [c for c in columns if set(c.circuits.values()) & set(f.circuits.values())]
        f.u = sum(c.u for c in neighbours) / len(neighbours) if neighbours else target.block.length / 2
        offsets = [z.offset_v for z in definitions[f.definition].zones]
        f.v = junction_z + gap - min(offsets)
    lane_order = list(major)
    lane_order.extend(deep[f.id] for f in columns if f.id in deep and deep[f.id] not in lane_order)
    lane_order.extend(n.id for n in sorted(target.nets, key=lambda n: (-len(n.members), n.id)) if n.id not in lane_order)
    from ..closure_runtime import bind_route
    from ..schema import Feature
    probe = bind_route(target, [Feature(id='AI_CLOSURE_SPACE', kind='drilling', face='left', u=row, v=junction_z,
        diameter=bore, depth=max(20, bore * 3), plugged=True, circuit=target.nets[0].id, route_net=target.nets[0].id)])[0]
    # A panel's installed footprint can forbid front construction entries even
    # when its internal cuts clear the trunk plane. Reserve the real installed
    # radius AND the bound closure entry radius, otherwise every trunk is
    # forced to enter from the rear and crosses the other allocated lanes.
    if panels:
        needed=max(bottom-top+4*machining_radius(definitions[f.definition])+probe.clearance_diameter+
                   2*(target.rules.minimum_access_gap+required_wall(target,f,definitions=definitions)) for f in panels)
        target.block.height=max(target.block.height,math.ceil(needed/5)*5)
        junction_z=(bottom+target.block.height-top)/2
    for f in panels:
        f.v=max(junction_z+gap-min(s.offset_v for s in definitions[f.definition].zones),
            junction_z+machining_radius(definitions[f.definition])+probe.clearance_diameter/2+target.rules.minimum_access_gap)
    diameters = {name: max([probe.clearance_diameter, bore] + [f.diameter or 0 for f in target.features if f.kind == 'port' and f.circuit == name]) for name in lane_order}
    lanes = {}
    y = row + radius + gap
    for i, name in enumerate(lane_order):
        if i:
            previous = lane_order[i - 1]
            y += (diameters[previous] + diameters[name]) / 2 + max(wall, target.rules.minimum_access_gap)
        lanes[name] = y
    target.block.width = math.ceil((y + max(diameters.values()) + gap) / 5) * 5
    for f in target.features:
        if f.kind != 'port':
            continue
        if fixed_faces.get(f.id, 'left') != 'left':
            return None
        f.face, f.u, f.v = 'left', lanes[f.circuit], junction_z
    for axis, key in enumerate(('length', 'width', 'height')):
        value = getattr(target.block, key)
        if axis not in growth_axes and value > getattr(design.block, key):
            return None
        if axis not in growth_axes:
            setattr(target.block, key, getattr(design.block, key))
        if target.constraints.envelope_min:
            setattr(target.block, key, max(getattr(target.block, key), target.constraints.envelope_min[axis]))
    if not _fits(target, definitions):
        return None
    return target, lanes, junction_z


def screen(design, definitions, threads, modifiers, tools, lanes, junction_z, progress=None):
    from ..routing import (route_from_variant, route_obstructions, terminal_points, segment_depth,
        route_objective, select_route_combination, _ProposalSnapshot, _route_pair_failures)
    from ..cavity_access import cavity_terminal_candidates
    source = design.model_copy(deep=True)
    owners = {n.id for n in source.nets if n.routing == 'automatic' and n.route_state in ('unresolved', 'proposal')}
    source.features = [f for f in source.features if f.route_net not in owners]
    nets = {n.id: effective_net(source, n) for n in source.nets if n.id in owners and len(n.members) >= 2}
    points = terminal_points(source, definitions)
    snapshot = _ProposalSnapshot(source, definitions, threads, modifiers)
    pools, diagnostics = {}, {}
    for index, (name, net) in enumerate(nets.items()):
        if progress:
            progress('access', net=name, completed=index, total=len(nets))
        eligible = cavity_terminal_candidates(source, net, definitions, threads, modifiers)
        mask = sum(1 << i for i, member in enumerate(sorted(net.members))
                   if member in eligible and eligible[member].face in ('top', 'bottom'))
        xs = [points[m][0] for m in net.members]
        positions = (sum(xs) / len(xs), min(xs) + net.diameter, max(xs) - net.diameter)
        clear, rejected, seen = [], [], set()
        # Same 32 analytic samples and eight retained choices as the previous
        # AI screen. Round-robin axes/entries before the next junction anchor.
        choices = itertools.islice(itertools.product(('negative', 'nearest', 'positive'), ('yxz', 'xyz', 'yzx', 'xzy'), positions), 32)
        for entry, order, x in choices:
            z = junction_z[name] if isinstance(junction_z,dict) else junction_z
            key = f'branch_{mask}_{x:.6f}_{lanes[name]:.6f}_{z:.6f}:{order}:{entry}'
            route = route_from_variant(source, net, key, definitions, threads, modifiers, obstruction_cache=snapshot.obstructions)
            if route is None:
                continue
            signature = tuple((f.face, f.u, f.v, f.depth, f.diameter, f.plugged) for f in route)
            if signature in seen:
                continue
            seen.add(signature)
            failures = route_obstructions(source, net, route, threads, definitions, modifiers, snapshot.obstructions)
            failures.update(('forbidden_face',f.id) for f in route if f.face in source.constraints.forbidden_drilling_faces)
            if any(not any(abs(t['diameter_mm'] - f.diameter) <= .011 and t['max_depth_mm'] + 1e-6 >= segment_depth(f) for t in tools) for f in route):
                failures.add(('tool_reach', name))
            option = dict(key=key, route=route, risk=0, failures=failures)
            (rejected if failures else clear).append(option)
        clear.sort(key=lambda o: (route_objective(source, o['route'], definitions=definitions), o['key']))
        groups = defaultdict(list)
        for o in clear:
            groups[(o['key'].split('_')[2],o['key'].split(':')[1][0])].append(o)
        kept = []
        while groups and len(kept) < 8:
            for group in list(groups):
                kept.append(groups[group].pop(0))
                if not groups[group]:
                    del groups[group]
                if len(kept) == 8:
                    break
        pools[name] = kept
        diagnostics[name] = dict(source_clear=len(clear), retained=len(kept),
            rejected=[dict(variant=o['key'], failures=sorted(o['failures'])) for o in rejected[:3]])
    witnesses = {}
    def pair(a, ao, b, bo):
        failures = _route_pair_failures(source, nets[a], ao, nets[b], bo, snapshot, snapshot.combination_budget)
        if failures and not any(f[0] == 'search_budget' for f in failures):
            key = tuple(sorted((a, b)))
            if key not in witnesses or len(failures) < len(witnesses[key]['failures']):
                ids = {v for f in failures for v in f[1:]}
                witnesses[key] = dict(nets=key, failures=sorted(failures),
                    features=[f.model_dump(mode='json') for f in ao['route'] + bo['route'] if f.id in ids])
        return failures
    if progress:
        progress('conflicts', completed=len(nets), total=len(nets))
    chosen, combination = select_route_combination(source, nets, pools, definitions, pair,
        pair_count=lambda: snapshot.combination_budget['used'])
    fixed = sorted({('source_wall', *sorted((f.id, other))) for f in source.features if f.kind in ('port', 'cavity')
                    for other in placement_conflicts(source, f, definitions, threads, modifiers)})
    blocked = sorted(name for name in nets if not pools[name])
    compatible = chosen is not None
    if chosen is None and all(pools.values()):
        # Retain a complete, explicitly unresolved proposal for diagnostics and
        # offline Exact evaluation. It cannot become an admitted clear route.
        chosen={}
        for name in sorted(nets,key=lambda n:(len(pools[n]),n)):
            chosen[name]=min(pools[name],key=lambda o:(sum(len(pair(name,o,k,p)) for k,p in chosen.items()),
                route_objective(source,o['route'],definitions=definitions),o['key']))
    route = [f for o in (chosen or {}).values() for f in o['route']]
    from ..routing import _conflict_objective
    failures=set(fixed)
    if chosen and not compatible:
        for a,b in itertools.combinations(chosen,2):failures.update(pair(a,chosen[a],b,chosen[b]))
    if not compatible:failures.add(('route_combination',combination['exit_reason']))
    feasibility = (len(blocked), *_conflict_objective(failures))
    return dict(status='ANALYTIC_UNVALIDATED', score=(*feasibility, *route_objective(source, route, definitions=definitions)),
        feasibility_score=feasibility, blocked_nets=blocked, compatible=compatible, conflicts=sorted(failures),
        fixed_conflicts=fixed, selected={n: o['key'] for n, o in (chosen or {}).items()}, pools=diagnostics,
        combination=combination, witnesses=list(witnesses.values()), drillings=len(route), plugs=sum(f.plugged for f in route))


def plan_new(design, definitions, *, movable_features, growth_axes, fixed_faces=None, progress=None):
    """Only the new AI compiler calls this. Inputs are copied, never mutated."""
    from ..engineering_db import thread_definitions_for_design, modifier_definitions_for_design, tool_definitions
    from ..store import revision
    threads = thread_definitions_for_design(design)
    modifiers = modifier_definitions_for_design(design) if any(f.machining_modifiers for f in design.features) else {}
    tools = tool_definitions('drill')
    movable, grow = _permissions(design)
    movable &= set(movable_features)
    limit = 8
    def report(index):
        return lambda stage, **detail: progress(stage, layout=index, layout_limit=limit, **detail) if progress else None
    baseline = assess(design, definitions, threads, modifiers, tools, report(1))
    seed = _columns(design, definitions, movable, growth_axes if grow else (), fixed_faces or design.constraints.required_feature_faces)
    evaluated, proposals, seen, history = 1, [], set(), []
    queue = [seed] if seed else []
    while queue and evaluated < limit:
        target, lanes, z = queue.pop(0)
        signature = (target.model_dump_json(exclude={'nets':{'__all__':{'routing_variant'}}}),tuple(sorted(z.items())) if isinstance(z,dict) else z)
        if signature in seen:
            continue
        seen.add(signature)
        evaluated += 1
        if progress:
            progress('layout_alternate', layout=evaluated, layout_limit=limit)
        result = screen(target, definitions, threads, modifiers, tools, lanes, z, report(evaluated))
        history.append(dict(layout=evaluated,dimensions=list(dimensions(target.block)),assessment=result))
        changes = [dict(id=f.id, before=[old.face, old.u, old.v], after=[f.face, f.u, f.v]) for f in target.features
                   for old in design.features if f.id == old.id and (f.face, f.u, f.v) != (old.face, old.u, old.v)]
        if result['score'] < baseline['score']:
            for net in target.nets:
                net.routing_variant = result['selected'].get(net.id)
            proposals.append(dict(reason='Allocate source columns and coordinated hydraulic corridors', assessment=result,
                changes=changes, dimensions=list(dimensions(target.block)), design=target.model_dump(), affected_nets=sorted(lanes)))
        if not result['conflicts'] and not result['blocked_nets']:
            break
        # A progressive child retains ALL previous coordinated moves. Offset
        # panel approaches using the actual implicated route diameter/wall band;
        # avoid the old independent single-move-from-baseline search.
        panels = [f for f in target.features if f.kind == 'cavity' and f.face in ('front','left') and f.id in movable and
                  _distributed_openings(definitions[f.definition])]
        implicated = {name for w in result['witnesses'] for name in w['nets']} | set(result['blocked_nets'])
        for f in sorted(panels, key=lambda f: (not bool(set(f.circuits.values()) & implicated), f.id)):
            pitch = max((n.diameter for n in target.nets if n.id in f.circuits.values()), default=8)
            pitch += required_wall(target, f, definitions=definitions)
            # Rotate the actual offset source pattern to separate coincident
            # work-port heights. No port number, source offset or net changes.
            child=target.model_copy(deep=True)
            item=next(c for c in child.features if c.id==f.id);item.rotation=(item.rotation+90)%360
            if set(f.circuits.values())&implicated and _fits(child,definitions):
                queue.append((child,lanes.copy(),z))
            if f.face=='front' and f.id not in (fixed_faces or {}) and all(p.id not in (fixed_faces or {}) for p in target.features if p.kind=='port'):
                child=target.model_copy(deep=True)
                item=next(c for c in child.features if c.id==f.id)
                item.face='left';item.u=max(machining_radius(definitions[f.definition])+pitch,min(lanes.values())+pitch)
                for port in child.features:
                    if port.kind=='port':port.face='right'
                if _fits(child,definitions):queue.append((child,lanes.copy(),z))
        if result['witnesses']:
            name=result['witnesses'][0]['nets'][0]
            net=next(n for n in target.nets if n.id==name)
            planes=z.copy() if isinstance(z,dict) else dict.fromkeys(lanes,z)
            planes[name]+=net.diameter+required_wall(target,definitions=definitions)
            if 0<planes[name]<target.block.height:
                queue.append((target.model_copy(deep=True),lanes.copy(),planes))
        for f in panels:
            pitch=max((n.diameter for n in target.nets if n.id in f.circuits.values()),default=8)+required_wall(target,f,definitions=definitions)
            for sign in (-1,1):
                child=target.model_copy(deep=True);item=next(c for c in child.features if c.id==f.id);item.u+=sign*pitch
                if _fits(child,definitions):queue.append((child,lanes.copy(),z))
        # Keep a two-parent beam, rather than multiplying every arrangement.
        queue = queue[:2]
    proposals.sort(key=lambda p: (p['assessment']['score'], math.prod(p['dimensions'])))
    return dict(source_revision=revision(design), baseline=baseline, proposals=proposals[:3], evaluated_layouts=evaluated,
                layout_limit=limit, evaluations=history, status='ANALYTIC_LAYOUT_PROPOSALS')
