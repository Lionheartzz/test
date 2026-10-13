"""AI-generation-owned layout search. Never called by Model or the Router.

All route cuts come from the shared Router. Analytic screens schedule geometry
revisions; plan_new delegates acceptance to disposable Exact CAD workers.
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


def screen(design, definitions, threads, modifiers, tools, lanes, junction_z, progress=None,*,include_routes=False,corridor_labels=1024,general_families=False,route_session=None,deep_limits=None):
    from ..routing import (route_from_variant, route_obstructions, terminal_points, segment_depth,
        route_objective, select_route_combination, _ProposalSnapshot, _route_pair_failures)
    from ..cavity_access import cavity_terminal_candidates
    source = design.model_copy(deep=True)
    owners = {n.id for n in source.nets if n.routing == 'automatic' and n.route_state in ('unresolved', 'proposal')}
    source.features = [f for f in source.features if f.route_net not in owners]
    nets = {n.id: effective_net(source, n) for n in source.nets if n.id in owners and len(n.members) >= 2}
    points = terminal_points(source, definitions)
    snapshot = _ProposalSnapshot(source, definitions, threads, modifiers)
    if deep_limits:snapshot.combination_budget['limit']=deep_limits['pairs']
    pools, diagnostics = {}, {}
    if general_families:
        # Reuse shared simple/direct/axial/detour/port/tree generation, rather
        # than requiring every layout to fit the old branch-column template.
        from .route_catalog import Session
        route_session=route_session or Session()
        general_pools=route_session.prepare(source,nets,definitions,threads,modifiers,tools,progress)
        route_session.solver.bind(source,nets,route_session.catalogs)
    for index, (name, net) in enumerate(nets.items()):
        if progress:
            progress('access', net=name, completed=index, total=len(nets))
        if general_families:
            pools[name]=general_pools[name]
            diagnostics[name]=route_session.catalogs[name].diagnostics(pools[name])
            continue
        eligible = cavity_terminal_candidates(source, net, definitions, threads, modifiers)
        mask = sum(1 << i for i, member in enumerate(sorted(net.members))
                   if member in eligible and eligible[member].face in ('top', 'bottom'))
        xs = [points[m][0] for m in net.members]
        positions = (sum(xs) / len(xs), min(xs) + net.diameter, max(xs) - net.diameter)
        clear, rejected, seen = [], [], set()
        # Same 32 analytic samples and eight retained choices as the previous
        # AI screen. Round-robin axes/entries before the next junction anchor.
        from ..branch_candidates import terminal_branch_candidates
        def custom():
            for entry,order,x in itertools.product(('negative','nearest','positive'),('yxz','xyz','yzx','xzy'),positions):
                z=junction_z[name] if isinstance(junction_z,dict) else junction_z
                key=f'branch_{mask}_{x:.6f}_{lanes[name]:.6f}_{z:.6f}:{order}:{entry}'
                yield key,route_from_variant(source,net,key,definitions,threads,modifiers,obstruction_cache=snapshot.obstructions)
        def strategies():
            common=iter(terminal_branch_candidates(source,net,definitions,threads,modifiers,snapshot.obstructions))
            for i,option in enumerate(custom()):
                if i%2==0:
                    try:yield next(common)
                    except StopIteration:pass
                yield option
        for key,route in itertools.islice(strategies(),32):
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
            groups[(o['key'].startswith('window:'),o['key'].split('_')[2],o['key'].rsplit(':',2)[1][0])].append(o)
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
        state=route_session.solver.current if general_families else None
        fact=state.pair_fact(a,ao,b,bo) if state else None
        if fact is not None:return {tuple(f) for f in fact['failures']}
        if general_families:
            from .route_catalog import geometry_key
            token=tuple(sorted(((a,geometry_key(ao['route'])),(b,geometry_key(bo['route'])))))
            cached=route_session.pair_evidence.get(token)
        else:cached=None
        failures=set(cached) if cached is not None else _route_pair_failures(source, nets[a], ao, nets[b], bo, snapshot, snapshot.combination_budget)
        if general_families and cached is None and not any(f[0]=='search_budget' for f in failures):
            route_session.pair_evidence[token]=frozenset(failures)
            if len(route_session.pair_evidence)>4096:route_session.pair_evidence.pop(next(iter(route_session.pair_evidence)))
        if state:state.pair_fact(a,ao,b,bo,failures)
        if failures and not any(f[0] == 'search_budget' for f in failures):
            key = tuple(sorted((a, b)))
            if key not in witnesses or len(failures) < len(witnesses[key]['failures']):
                ids = {v for f in failures for v in f[1:]}
                witnesses[key] = dict(nets=key, failures=sorted(failures),
                    features=[f.model_dump(mode='json') for f in ao['route'] + bo['route'] if f.id in ids])
        return failures
    if progress:
        progress('conflicts', completed=len(nets), total=len(nets))
    joint=None;preserved={}
    if general_families:
        from .joint_routes import coordinate
        if route_session.local_admission:route_session.local_admission.bind(source,nets,route_session.catalogs)
        preserved=route_session.compatible_core(source,nets,pair)
        pools={n:c.active(width=len(c.clear)) for n,c in route_session.catalogs.items()}
        work=dict(states=0,limit=deep_limits['states'] if deep_limits else 1000)
        partial,joint=coordinate(route_session,source,nets,pools,pair,preserved,work,labels=corridor_labels,
                                 fragments=bool(corridor_labels),limits=deep_limits)
        partial=route_session.admit_core(source,nets,partial)
        joint['local_admission']=route_session.local_admission.diagnostics()
        joint['local_core_records']=route_session.local_records
        joint['core_validation']=route_session.core_checks
        chosen=partial if len(partial)==len(nets) else None
        combination=dict(states=work['states'],state_limit=work['limit'],pair_screens=snapshot.combination_budget['used'],pair_limit=snapshot.combination_budget.get('limit',4000),
            exit_reason='clear_combination' if chosen else 'compatible_core_incomplete',pools={n:len(p) for n,p in pools.items()},
            preserved_core=sorted(preserved),best_partial=sorted(partial),empty_nets=sorted(n for n,p in pools.items() if not p))
    else:
        chosen, combination = select_route_combination(source, nets, pools, definitions, pair,
            pair_count=lambda: snapshot.combination_budget['used'])
    # AI joint insertion consumes all already screened alternatives; eight is
    # only the initial catalog batch. Manual/legacy selection remains unchanged.
    promotions=[dict(net=n,count=len(pool)-8) for n,pool in pools.items() if general_families and len(pool)>8]
    combination['deferred_promotions']=promotions
    if general_families:
        for name,catalog in route_session.catalogs.items():diagnostics[name]=catalog.diagnostics(pools[name])
    corridor=None
    if chosen is None and nets and corridor_labels and not general_families:
        from ..drilling_planner import coordinate_routes
        planned,corridor=coordinate_routes(source,list(nets.values()),definitions,threads,modifiers,
            label_limit=min(128,corridor_labels),label_total_limit=corridor_labels,state_limit=16,pair_limit=256,exact_connectivity=False)
        if planned:chosen=planned
    fixed = sorted({('source_wall', *sorted((f.id, other))) for f in source.features if f.kind in ('port', 'cavity')
                    for other in placement_conflicts(source, f, definitions, threads, modifiers)})
    blocked = sorted(name for name in nets if not pools[name] and (chosen is None or name not in chosen))
    compatible = chosen is not None
    if chosen is None and all(pools.values()):
        # Retain a complete, explicitly unresolved proposal for diagnostics and
        # offline Exact evaluation. It cannot become an admitted clear route.
        chosen={}
        for name in sorted(nets,key=lambda n:(len(pools[n]),n)):
            chosen[name]=min(pools[name],key=lambda o:(sum(len(pair(name,o,k,p)) for k,p in chosen.items()),
                route_objective(source,o['route'],definitions=definitions),o['key']))
    diagnostic = chosen if not compatible else {}
    if not general_families:partial={}
    if not compatible and not general_families:
        for name in sorted(nets,key=lambda n:(len(pools[n]),n)):
            for option in sorted(pools[name],key=lambda o:route_objective(source,o['route'],definitions=definitions)):
                if all(not pair(name,option,other,previous) for other,previous in partial.items()):
                    partial[name]=option;break
    if compatible:partial=chosen
    if general_families:route_session.remember(source,partial)
    route = [f for o in partial.values() for f in o['route']]
    # Attribute insertion failures against the FINAL compatible core. Earlier
    # CSP witnesses can describe displaced assignments, not this layout state.
    constraints=[];deferred_constraints=[]
    if general_families and not compatible:
        for name in sorted(set(nets)-set(partial)):
            arrangements={}
            for option in pools[name]:
                blockers={n:sorted(pair(name,option,n,p)) for n,p in partial.items() if pair(name,option,n,p)}
                if any(f[0]=='search_budget' for rows in blockers.values() for f in rows):
                    deferred_constraints.append(dict(net=name,candidate=option['key'],reason='PAIR_SCREEN_BUDGET'))
                    continue
                implicated={v for rows in blockers.values() for failure in rows for v in failure[1:]}
                token=(tuple(sorted(blockers)),tuple(sorted((f.face,f.u,f.v,f.depth) for f in option['route'] if f.id in implicated)))
                if token in arrangements:continue
                arrangements[token]=True
                for other,failures in blockers.items():
                    ids={v for f in failures for v in f[1:]}
                    constraints.append(dict(nets=[name,other],missing_net=name,candidate=option['key'],
                        retained_candidate=partial[other]['key'],failures=failures,
                        features=[f.model_dump(mode='json') for f in option['route']+partial[other]['route'] if f.id in ids],
                        evidence='CURRENT_COMPATIBLE_CORE_INSERTION',exact_verified=False))
    source_ids={f.id for f in source.features}
    from .route_feedback import obstruction_witnesses
    # An alternate entry can be essential to the GLOBAL combination even
    # when this Net already has an individually clear route (F7).
    feedback_diagnostics=({n:c.diagnostics(pools[n],all_rejections=True) for n,c in route_session.catalogs.items()}
                          if general_families else diagnostics)
    spatial=obstruction_witnesses(source,nets,feedback_diagnostics,definitions,threads,modifiers)
    feedback=[dict(net=name,terminals=list(nets[name].members),source_blockers=sorted({str(key).split(':')[0]
        for sample in diagnostics[name].get('rejected_samples',[]) for failure in sample['failures'] for key in failure[1:]
        if str(key).split(':')[0] in source_ids}),
        failures=[failure for sample in diagnostics[name].get('rejected_samples',[]) for failure in sample['failures']])
        for name in nets if not pools[name] or not compatible and name not in partial]
    from ..routing import _conflict_objective
    failures=set(fixed)
    diagnostic_failures=set()
    if diagnostic:
        for a,b in itertools.combinations(diagnostic,2):diagnostic_failures.update(pair(a,diagnostic[a],b,diagnostic[b]))
    if not compatible:failures.add(('route_combination',combination['exit_reason']))
    unresolved=sorted(set(nets)-set(partial))
    feasibility = (len(unresolved), *_conflict_objective(failures))
    if general_families:route_session.remember_context()
    result=dict(status='ANALYTIC_UNVALIDATED', score=(*feasibility, *route_objective(source, route, definitions=definitions)),
        feasibility_score=feasibility, blocked_nets=blocked, compatible=compatible, conflicts=sorted(failures),
        fixed_conflicts=fixed, selected={n:o['key'] for n,o in partial.items()}, pools=diagnostics,
        unresolved_nets=unresolved,coordination_constraints=constraints,deferred_constraints=deferred_constraints,
        diagnostic_combination=dict(status='INCOMPATIBLE_DIAGNOSTIC_ONLY',
            selected={n:o['key'] for n,o in (diagnostic or {}).items()},conflicts=sorted(diagnostic_failures)),
        combination=combination,joint_coordination=joint,corridor_planning=corridor,witnesses=list(witnesses.values()), drillings=len(route), plugs=sum(f.plugged for f in route),
        layout_feedback=feedback,spatial_feedback=spatial,partial_routing=dict(status='PARTIAL_REQUIRES_FULL_EXACT',nets=sorted(partial),
            local_admission=route_session.local_records if general_families else {},
            features=[f.model_dump(mode='json') for o in partial.values() for f in o['route']],connection_verified=False),
        **(dict(route_features=[f.model_dump(mode='json') for f in route]) if include_routes else {}))
    if general_families:route_session.solver.update(result)
    return result


def _scout(entry,definitions,threads,modifiers):
    """One regenerated hypothesis, not a second global/Exact layout search."""
    from ..routing import route_from_variant,route_obstructions,_conflict_objective,_fixed_strategy_source
    from ..branch_candidates import terminal_branch_candidates
    target,lanes,z=entry['candidate'];source=_fixed_strategy_source(target.model_copy(deep=True))
    routes={};missing=[];cache={}
    for net in source.nets:
        key=entry['parent'].get('selected',{}).get(net.id)
        if key and key.startswith(('branch_','window:branch_')):
            trunk,order,side=key.rsplit(':',2);tokens=trunk.split('_')
            tokens[3]=f'{lanes[net.id]:.6f}';tokens[4]=f'{(z[net.id] if isinstance(z,dict) else z):.6f}'
            key='_'.join(tokens)+':'+order+':'+side
            route=route_from_variant(source,net,key,definitions,threads,modifiers,obstruction_cache=cache)
        else:
            option=next(iter(terminal_branch_candidates(source,net,definitions,threads,modifiers,cache)),None)
            route=option[1] if option else None
        if route:routes[net.id]=route
        else:missing.append(net.id)
    context=source.model_copy(update=dict(features=source.features+[f for r in routes.values() for f in r]))
    failures={('source_wall',*sorted((f.id,other))) for f in source.features if f.kind in ('cavity','port')
              for other in placement_conflicts(source,f,definitions,threads,modifiers)}
    for net in source.nets:
        if net.id in routes:failures.update(route_obstructions(context,net,routes[net.id],threads,definitions,modifiers,cache))
    return (len(missing),*_conflict_objective(failures),math.prod(dimensions(target.block)))


def _rank_frontier(entries,definitions,threads,modifiers,cache):
    """Evaluate bounded family representatives before the two-parent beam."""
    groups=defaultdict(list)
    for entry in entries:
        target,lanes,z=entry['candidate']
        key=(target.model_dump_json(),tuple(sorted(lanes.items())),repr(sorted(z.items())) if isinstance(z,dict) else repr(z))
        entry={**entry,'signature':key}
        if any(e['signature']==key for e in groups[entry['family']]):continue
        groups[entry['family']].append(entry)
    raw=[]
    # Two representatives per transformation family; no append-order privilege.
    for family in groups:groups[family].sort(key=lambda e:(tuple(e['parent']['feasibility_score']),e['signature']))
    for level in range(2):
        for family in sorted(groups):
            if len(groups[family])>level and len(raw)<12:raw.append(groups[family][level])
    ranked=[]
    for entry in raw[:12]:
        key=entry['signature']
        if key not in cache:cache[key]=_scout(entry,definitions,threads,modifiers)
        ranked.append({**entry,'scout_score':cache[key]})
    ranked.sort(key=lambda e:(e['scout_score'],e['family'],e['signature']))
    if not ranked:return []
    first=ranked[0]
    second=next((e for e in ranked[1:] if e['family']!=first['family']),None)
    if second is None:second=next(iter(ranked[1:]),None)
    return [first,*([second] if second else [])]


def _children(target,definitions,movable,growth_axes,fixed_faces,lanes,z,result):
    """Conflict-directed proposals owned only by new AI generation."""
    from ..kinematics import FACE_AXES
    children=[]
    def add(family,child,child_lanes=None,planes=None):
        if _fits(child,definitions):children.append(dict(family=family,parent=result,
            candidate=(child,child_lanes or lanes.copy(),planes if planes is not None else z)))
    implicated={n for w in result['witnesses'] for n in w['nets']}|set(result['blocked_nets'])
    panels=[f for f in target.features if f.kind=='cavity' and f.face in ('front','left') and
            f.id in movable and _distributed_openings(definitions[f.definition])]
    for f in panels:
        if not set(f.circuits.values())&implicated:continue
        pitch=max((n.diameter for n in target.nets if n.id in f.circuits.values()),default=8)+required_wall(target,f,definitions=definitions)
        for turn in (90,180):
            child=target.model_copy(deep=True);item=next(c for c in child.features if c.id==f.id)
            item.rotation=(item.rotation+turn)%360;add('source-rotation',child)
        if f.face=='front' and f.id not in fixed_faces and all(p.id not in fixed_faces for p in target.features if p.kind=='port'):
            child=target.model_copy(deep=True);item=next(c for c in child.features if c.id==f.id)
            item.face='left';item.u=max(machining_radius(definitions[f.definition])+pitch,min(lanes.values())+pitch)
            for port in child.features:
                if port.kind=='port':port.face='right'
            add('mounting-face',child)
        for sign in (-1,1):
            child=target.model_copy(deep=True);item=next(c for c in child.features if c.id==f.id);item.u+=sign*pitch
            add('source-position',child)
    pairs=sorted(result['witnesses'],key=lambda w:(-len(w['failures']),w['nets']))[:2]
    for witness in pairs:
        for name in witness['nets']:
            net=next(n for n in target.nets if n.id==name);pitch=net.diameter+required_wall(target,definitions=definitions)
            for sign in (-1,1):
                planes=z.copy() if isinstance(z,dict) else dict.fromkeys(lanes,z)
                planes[name]+=sign*pitch
                if 0<planes[name]<target.block.height:add('branch-plane',target.model_copy(deep=True),planes=planes)
            child_lanes=lanes.copy();child_lanes[name]+=pitch
            child=target.model_copy(deep=True)
            for port in child.features:
                if port.kind=='port' and port.circuit==name and port.id in movable:
                    if FACE_AXES[port.face][0]==1:port.u=child_lanes[name]
            add('separate-corridors',child,child_lanes)
        # Relative group separation, with growth only to cover measured source
        # footprints. Moving a whole block boundary alone is not a repair.
        a,b=witness['nets'];owners={n:{m.split(':')[0] for m in next(net for net in target.nets if net.id==n).members} for n in (a,b)}
        group=(owners[a]-owners[b])&movable
        if group and 1 in growth_axes:
            child=target.model_copy(deep=True)
            members=[f for f in child.features if f.id in group and f.kind=='cavity' and f.face in ('top','bottom')]
            if members:
                pitch=max(2*machining_radius(definitions[f.definition]) for f in members)+max(n.diameter for n in target.nets)
                for item in members:item.v+=pitch
                needed=max(f.v+machining_radius(definitions[f.definition])+required_wall(child,f,definitions=definitions) for f in members)
                child.block.width=max(child.block.width,math.ceil(needed/5)*5)
                add('source-group-spacing',child)
    for port in target.features:
        if port.kind=='port' and port.circuit in implicated and port.id in movable and port.id not in fixed_faces:
            child=target.model_copy(deep=True);item=next(f for f in child.features if f.id==port.id)
            item.face={'left':'right','right':'left','front':'back','back':'front','top':'bottom','bottom':'top'}[item.face]
            add('port-entry-face',child)
    return children


def plan_legacy_analytic(design, definitions, *, movable_features, growth_axes, fixed_faces=None, progress=None):
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
    fixed_routes=any(n.routing_variant or n.route_state not in ('unresolved','proposal') for n in design.nets)
    seed = None if fixed_routes else _columns(design, definitions, movable, growth_axes if grow else (), fixed_faces or design.constraints.required_feature_faces)
    evaluated, proposals, seen, history = 1, [], set(), []
    queue = [dict(candidate=seed,family='source-columns',parent=baseline)] if seed else []
    scout_cache={};frontier_history=[]
    while queue and evaluated < limit:
        entry=queue.pop(0);target, lanes, z = entry['candidate']
        signature = (target.model_dump_json(exclude={'nets':{'__all__':{'routing_variant'}}}),tuple(sorted(z.items())) if isinstance(z,dict) else z)
        if signature in seen:
            continue
        seen.add(signature)
        evaluated += 1
        if progress:
            progress('layout_alternate', layout=evaluated, layout_limit=limit)
        result = screen(target, definitions, threads, modifiers, tools, lanes, z, report(evaluated))
        history.append(dict(layout=evaluated,family=entry['family'],dimensions=list(dimensions(target.block)),assessment=result))
        changes = [dict(id=f.id, before=[old.face, old.u, old.v], after=[f.face, f.u, f.v]) for f in target.features
                   for old in design.features if f.id == old.id and (f.face, f.u, f.v) != (old.face, old.u, old.v)]
        if result['score'] < baseline['score']:
            # Assessment selections are diagnostics, including incompatible
            # fallback samples. They grant no pin/commit authority in Model.
            proposals.append(dict(reason='Allocate source columns and coordinated hydraulic corridors', assessment=result,
                changes=changes, dimensions=list(dimensions(target.block)), design=target.model_dump(), affected_nets=sorted(lanes)))
        if not result['conflicts'] and not result['blocked_nets']:
            break
        children=_children(target,definitions,movable,growth_axes if grow else (),
                           fixed_faces or design.constraints.required_feature_faces,lanes,z,result)
        queue=_rank_frontier(queue+children,definitions,threads,modifiers,scout_cache)
        frontier_history.append(dict(layout=evaluated,scouted_total=len(scout_cache),
            selected=[dict(family=e['family'],score=e['scout_score']) for e in queue]))
    proposals.sort(key=lambda p: (p['assessment']['score'], math.prod(p['dimensions'])))
    return dict(source_revision=revision(design), baseline=baseline, proposals=proposals[:3], evaluated_layouts=evaluated,
                layout_limit=limit, evaluations=history, frontier=frontier_history,status='ANALYTIC_LAYOUT_PROPOSALS')


def plan_new(design,definitions,*,movable_features,growth_axes=(0,1,2),fixed_faces=None,
             fixed_positions=None,fixed_rotations=None,soft_faces=None,soft_dimensions=(),
             progress=None,cancelled=lambda:False,layout_limit=48,exact_limit=0,initial=None,evidence_dir=None,explicit_dimension_axes=None,seed_layouts=()):
    """New AI-owned joint design-space search; no Model call path."""
    from .design_space import LayoutDomain
    from .joint_layout import optimize
    if any(n.routing_variant or n.route_state in ('committed','stale') for n in design.nets) or any(
        f.route_net or f.frozen_net or f.kind=='drilling' for f in design.features):
        from ..store import revision
        return dict(scope='AI_GENERATION_ONLY',source_revision=revision(design),status='PROTECTED_EXISTING_GEOMETRY',
            baseline=dict(status='NOT_EVALUATED',score=(1,),feasibility_score=(1,),blocked_nets=[],conflicts=[]),
            proposals=[],evaluated_layouts=0,layout_limit=layout_limit,evaluations=[],attempts=[],validation=None,
            reason='Existing route choices or authored machining were not released by a new AI compilation.')
    domain=LayoutDomain.new_generation(design,movable_features,dimension_axes=growth_axes,fixed_faces=fixed_faces,
        fixed_positions=fixed_positions,fixed_rotations=fixed_rotations,soft_faces=soft_faces,soft_dimensions=soft_dimensions,
        explicit_dimension_axes=explicit_dimension_axes)
    return optimize(design,definitions,domain,layout_limit=layout_limit,exact_limit=exact_limit,
        progress=progress,cancelled=cancelled,initial=initial,evidence_dir=evidence_dir,seed_layouts=seed_layouts)
