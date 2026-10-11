"""Count-bounded analytic layout proposals using the shared router's cuts.

No BRep construction, exact-route search, persistence or automatic acceptance.
The corridor score is evidence for a proposal, never proof of manufacturability.
"""
import itertools
import math
from .engineering_conditions import effective_net,required_wall
from .kinematics import FACE_AXES,dimensions,pose
from .layout import machining_radius


def saved_route_evidence(design,records=()):
    """Read bounded saved Exact attribution for this precise authored revision.

    No caller paths, CAD execution, or adoption of a historical route. Evidence
    only prioritizes explicit proposals; it never clears a safety check.
    """
    import json
    from .store import OUTPUT,revision
    source_revision=revision(design)
    def latest(value):
        return value[-1] if isinstance(value,list) and value else value if isinstance(value,dict) else {}
    def matching(record):
        diagnostics=record.get('diagnostics',{})
        exact=latest(diagnostics.get('exact_preview',{}))
        if record.get('state')!='completed' or exact.get('source_revision')!=source_revision:return None
        proposal=latest(diagnostics.get('route_proposal',{}))
        failures=[f for rows in proposal.get('conflicts',{}).values() for f in rows]
        combination=latest(diagnostics.get('route_combination',{}))
        return dict(trace_id=record.get('id'),source_revision=source_revision,
            collisions=exact.get('collisions',[])[:64],contact_features=exact.get('contact_features',{}),
            unresolved_nets=sorted({f[1] for f in failures if len(f)==2 and f[0]=='connectivity'}|set(combination.get('empty_nets',[]))))
    for record in reversed(records):
        result=matching(record)
        if result:return result
    directory=OUTPUT/'cad-diagnostics'
    if not directory.is_dir():return None
    # Restarts lose executor history but not the saved owned traces. Source hash
    # equality prevents another browser/project/revision from supplying hints.
    paths=[]
    for path in directory.glob('*.json'):
        try:paths.append((path.stat().st_mtime,path))
        except OSError:continue
    for _,path in sorted(paths,reverse=True)[:64]:
        try:
            if path.stat().st_size>4_000_000:continue
            result=matching(json.loads(path.read_text(encoding='utf-8')))
        except (OSError,ValueError):continue
        if result:return result
    return None


def _evidence_focus(design,evidence):
    by_id={f.id:f for f in design.features};nets={n.id:n for n in design.nets}
    affected=set();contacts=[];implicated=set((evidence or {}).get('unresolved_nets',[]))
    for collision in (evidence or {}).get('collisions',[]):
        if not collision.get('attribution_complete'):continue
        implicated.update(name for name in collision.get('nets',[]) if name in nets)
        for pair in collision.get('feature_pairs',[]):
            if pair.get('volume_mm3',0)<=0:continue
            features=pair.get('features',[])
            if len(features)!=2:continue
            rows=[(evidence.get('contact_features',{}).get(key.split(':')[0]) or {}) for key in features]
            if any(not row for row in rows):continue
            for key,row in zip(features,rows):
                if key.split(':')[0] in by_id:affected.add(key.split(':')[0])
                if row.get('route_net') in nets:implicated.add(row['route_net'])
            contacts.append((features,rows))
    affected.update(member.split(':')[0] for name in implicated if name in nets for member in nets[name].members)
    return affected,contacts,implicated


def _routing_owners(design):
    return {n.id for n in design.nets if n.routing=='automatic' and n.route_state in ('unresolved','proposal') and
            not any(f.frozen_net==n.id for f in design.features)}


def routing_gap(design,definitions,face):
    """Reserve a drilling lane where neighbouring different-net windows compete.

    The allowance follows actual bore sizes/window depth bands and shared wall
    rules. It is a layout reserve, not an invented minimum-wall requirement.
    """
    group=[f for f in design.features if f.face==face and f.kind=='cavity' and not f.suppressed]
    diameters={n.id:n.diameter for n in design.nets};gap=design.rules.minimum_access_gap
    for a,b in itertools.combinations(group,2):
        for za,zb in itertools.product(definitions[a.definition].zones,definitions[b.definition].zones):
            na,nb=a.circuits.get(za.id),b.circuits.get(zb.id)
            if not na or not nb or na==nb or min(za.end,zb.end)<=max(za.start,zb.start):continue
            width=(diameters.get(na,0)+diameters.get(nb,0))/2+required_wall(design,a,b,definitions=definitions)
            gap=max(gap,width)
    return gap


def _catalogs(design,definitions,threads,modifiers,tools,progress=None):
    from .routing import propose,obstacle_safe_planes,route_obstructions,segment_depth,port_approach_candidates,connection_topology_candidates,simple_routes,_conflict_objective,route_objective
    from .cavity_access import _direct_axial_candidates
    from .closure_runtime import bind_route
    source=design.model_copy(deep=True)
    released=_routing_owners(source)
    source.features=[f for f in source.features if f.route_net not in released]
    catalogs={};diagnostics={};cache={}
    nets=sorted((effective_net(source,n) for n in source.nets if n.id in released and len(n.members)>=2),key=lambda n:n.id)
    for index,net in enumerate(nets):
        if progress:progress('access',net=net.id,completed=index,total=len(nets))
        if len(net.members)<2:continue
        planes=obstacle_safe_planes(source,net,definitions,threads,modifiers)
        orders=[o for o in itertools.permutations(range(3)) if net.preferred_axis=='auto' or o[0]=='xyz'.index(net.preferred_axis)]
        entry=net.entry_preference
        # Fair, tiny analytic family sample. Unlike route_options(), this NEVER
        # performs connectivity pruning or creates exact geometry during Generate.
        direct=(( ''.join('xyz'[i] for i in o)+':'+entry+':direct',propose(source,net,o,entry,definitions=definitions)) for o in orders)
        detours=(( ''.join('xyz'[i] for i in o)+':'+entry+':offset_'+axis+'_'+side,
                   propose(source,net,o,entry,'offset_'+axis+'_'+side,definitions,planes))
                 for axis,side,o in itertools.product('xyz','mp',orders[:2]))
        def axial_sample():
            yield from _direct_axial_candidates(source,net,definitions,threads,modifiers)
        axial=axial_sample()
        def port_sample():
            bases=[dict(key=''.join('xyz'[i] for i in o)+':'+entry+':direct',route=propose(source,net,o,entry,definitions=definitions)) for o in orders[:2]]
            bases.extend(dict(key=key,route=route) for key,route in itertools.islice(axial_sample(),2) if route is not None)
            yield from port_approach_candidates(source,net,bases,definitions,threads,modifiers)
        def topology_sample():
            bases=[dict(key=''.join('xyz'[i] for i in o)+':'+entry+':direct',route=propose(source,net,o,entry,definitions=definitions)) for o in orders[:2]]
            yield from connection_topology_candidates(source,net,bases,definitions,threads,modifiers)
        simple=((f'simple_{i}',route) for i,route in sorted(enumerate(simple_routes(source,net,definitions)),key=lambda row:(len(row[1]),row[0])))
        queues=[iter(simple),iter(direct),iter(detours),iter(axial),iter(port_sample()),iter(topology_sample())];raw=[];rejected=[];seen=set();attempted=0;candidate_errors=0
        while queues and len(raw)<8 and attempted<32:
            active=[]
            for queue in queues:
                if attempted>=32:break
                try:key,route=next(queue)
                except StopIteration:continue
                except ValueError:candidate_errors+=1;attempted+=1;continue
                active.append(queue);attempted+=1
                if route is None:continue
                route=bind_route(source,route)
                signature=tuple((f.face,f.u,f.v,f.depth,f.diameter,f.plugged) for f in route)
                if signature in seen:continue
                seen.add(signature)
                failures=route_obstructions(source,net,route,threads,definitions,modifiers,cache)
                failures.update(('forbidden_face',f.id) for f in route if f.face in source.constraints.forbidden_drilling_faces)
                if any(not any(abs(t['diameter_mm']-f.diameter)<=.011 and t['max_depth_mm']+1e-6>=segment_depth(f) for t in tools) for f in route):
                    failures.add(('tool_reach',net.id))
                option=dict(key=key,route=route,failures=failures)
                (rejected if failures else raw).append(option)
                if len(raw)==8 or attempted>=32:break
            queues=active
        # An unsafe raw variant must not spend all eight retained slots before
        # a legal stopping/common-plane strategy is even sampled. The 32-attempt
        # count remains unchanged; keep rejected samples only as diagnostics or
        # fallback when a layout has no source-clear route.
        rejected.sort(key=lambda o:(_conflict_objective(o['failures']),route_objective(source,o['route'],definitions=definitions),o['key']))
        raw.extend(rejected[:8-len(raw)])
        catalogs[net.id]=raw
        diagnostics[net.id]=dict(analytic_candidates=len(raw),source_clear=sum(not o['failures'] for o in raw),candidate_errors=candidate_errors)
    return source,catalogs,diagnostics,cache


def assess(design,definitions,threads,modifiers,tools,progress=None):
    from .routing import route_obstructions,_conflict_objective,route_objective
    source,pools,diagnostics,cache=_catalogs(design,definitions,threads,modifiers,tools,progress)
    if progress:progress('conflicts',completed=len(pools),total=len(pools))
    nets={n.id:effective_net(source,n) for n in source.nets};context=source.model_copy(deep=True)
    selected={};failures=set();blocked=[]
    for name in sorted(pools,key=lambda n:(not bool(diagnostics[n]['source_clear']),diagnostics[n]['source_clear'],-len(nets[n].members),n)):
        ranked=[]
        for o in pools[name]:
            conflict=set(o['failures'])|route_obstructions(context,nets[name],o['route'],threads,definitions,modifiers,cache)
            ranked.append((_conflict_objective(conflict),route_objective(source,o['route'],definitions=definitions),o['key'],o))
        if not ranked:blocked.append(name);continue
        option=min(ranked,key=lambda row:row[:3])[3]
        selected[name]=option;context.features.extend(option['route'])
        if not diagnostics[name]['source_clear']:blocked.append(name)
    for name,o in selected.items():
        failures.update(o['failures']|route_obstructions(context,nets[name],o['route'],threads,definitions,modifiers,cache))
    fixed_conflicts=set()
    for name,net in nets.items():
        retained=[f for f in source.features if f.kind=='drilling' and f.circuit==name and not f.suppressed]
        if retained:fixed_conflicts.update(route_obstructions(source,net,retained,threads,definitions,modifiers,cache))
    failures.update(fixed_conflicts)
    route=[f for o in selected.values() for f in o['route']]
    if len(source.features)+len(route)>120:failures.add(('feature_budget',))
    feasibility=(len(blocked),*_conflict_objective(failures))
    score=(*feasibility,*route_objective(source,route,definitions=definitions))
    return dict(score=score,feasibility_score=feasibility,status='ANALYTIC_UNVALIDATED',blocked_nets=blocked,pools=diagnostics,
        conflicts=[list(f) for f in sorted(failures)][:64],fixed_conflicts=[list(f) for f in sorted(fixed_conflicts)],
        selected={n:o['key'] for n,o in selected.items()},
        drillings=len(route),plugs=sum(f.plugged for f in route),max_depth=max((f.depth for f in route),default=0),
        total_depth=sum(f.depth for f in route))


def _permissions(design):
    fixed_nets={n.id for n in design.nets if n.routing!='automatic' or n.route_state not in ('unresolved','proposal')}
    fixed_nets.update(f.frozen_net for f in design.features if f.frozen_net)
    # Authored/manual cuts also lock their circuit; moving its interfaces would
    # silently invalidate retained machining even without a formal freeze.
    fixed_nets.update(f.circuit for f in design.features if f.kind=='drilling' and not f.route_net and f.circuit)
    fixed_refs={key.split(':')[0] for f in design.features if not f.route_net for key in f.connects_to}
    parents={f.parent_id for f in design.features if f.parent_id}
    movable={f.id for f in design.features if not f.suppressed and f.kind in ('cavity','port') and
        not f.parent_id and f.direction is None and f.id not in parents|fixed_refs and not ({f.circuit,*f.circuits.values()}&fixed_nets)}
    grow=not design.block.stock_id and not design.engravings and not design.block_modifiers and all(f.id in movable or f.route_net and f.route_net not in fixed_nets for f in design.features if not f.suppressed)
    return movable,grow


def _fits(design,definitions):
    dims=dimensions(design.block)
    if design.constraints.envelope_max and any(a>b for a,b in zip(dims,design.constraints.envelope_max)):return False
    if design.constraints.envelope_min and any(a<b for a,b in zip(dims,design.constraints.envelope_min)):return False
    for f in design.features:
        if f.suppressed or f.kind not in ('cavity','port'):continue
        u,v,axis,_=FACE_AXES[f.face]
        radius=machining_radius(definitions[f.definition]) if f.definition else max(f.diameter or 0,f.clearance_diameter)/2
        margin=radius+required_wall(design,f,definitions=definitions)
        if not (margin<=f.u<=dims[u]-margin and margin<=f.v<=dims[v]-margin):return False
        depth=max(p.end for p in definitions[f.definition].cutting_primitives or definitions[f.definition].stages) if f.definition else f.depth
        if depth+required_wall(design,f,definitions=definitions)>dims[axis]:return False
    for a,b in itertools.combinations([f for f in design.features if not f.suppressed and f.kind in ('cavity','port')],2):
        if a.face!=b.face:continue
        radii=[machining_radius(definitions[f.definition]) if f.definition else max(f.diameter or 0,f.clearance_diameter)/2 for f in (a,b)]
        if math.dist((a.u,a.v),(b.u,b.v))+1e-6<sum(radii)+max(design.rules.minimum_access_gap,required_wall(design,a,b,definitions=definitions)):return False
    return True


def alternatives(design,definitions,baseline,*,allow_growth=True,evidence=None,movable_features=None,growth_axes=None):
    """Lazy strategy diversity: swap, port alignment, then a measured extra lane."""
    from .routing import terminal_points
    movable,grow=_permissions(design);by_id={f.id:f for f in design.features}
    if movable_features is not None:
        allowed=set(movable_features);grow=grow and movable<=allowed;movable&=allowed
    affected={key for f in baseline['conflicts'] for key in f[1:] if key in by_id}
    affected.update(f.id for f in design.features if set(f.circuits.values())&set(baseline['blocked_nets']))
    exact_affected,contacts,_=_evidence_focus(design,evidence)
    affected.update(exact_affected)
    cavities=sorted((f for f in design.features if f.kind=='cavity' and f.id in movable),key=lambda f:(f.id not in affected,f.schematic_id or f.id))
    def swaps():
        for a,b in itertools.combinations(cavities,2):
            if a.face!=b.face:continue
            if exact_affected and (a.id not in exact_affected or b.id not in exact_affected):continue
            target=design.model_copy(deep=True);items={f.id:f for f in target.features}
            items[a.id].u,items[b.id].u=b.u,a.u;items[a.id].v,items[b.id].v=b.v,a.v
            yield 'Rearrange neighbouring hydraulic interfaces',target
    def ports():
        points=terminal_points(design,definitions)
        for port in sorted((f for f in design.features if f.kind=='port' and f.id in movable),key=lambda f:(f.id not in exact_affected,f.circuit not in baseline['blocked_nets'],f.id)):
            if exact_affected and port.id not in exact_affected:continue
            net=next((n for n in design.nets if port.id in n.members),None)
            if not net:continue
            u,v,_,_=FACE_AXES[port.face]
            for member in net.members:
                if member==port.id or member not in points:continue
                target=design.model_copy(deep=True);f=next(f for f in target.features if f.id==port.id)
                f.u,f.v=points[member][u],points[member][v]
                if math.dist((f.u,f.v),(port.u,port.v))<1e-6:continue
                yield 'Align external access with an assigned hydraulic window',target
    def exact_local_moves():
        # Sample owners round-robin so one port cannot exhaust the seven layout
        # evaluations before an attributed cavity/connectivity owner is tried.
        collision_nets={row.get('route_net') for _,rows in contacts for row in rows}
        implicated_features=sorted((f for f in design.features if f.id in exact_affected&movable),
            key=lambda f:(f.kind!='port',not bool({f.circuit,*f.circuits.values()}&collision_nets),f.schematic_id or f.id))
        def moves(feature):
            own={feature.circuit,*feature.circuits.values()}
            u,v,_,_=FACE_AXES[feature.face]
            for _,rows in contacts:
                for row in rows:
                    if row.get('route_net') in own or row.get('kind')!='drilling':continue
                    ou,ov,_,_=FACE_AXES[row['face']]
                    fixed={ou:row['u'],ov:row['v']}
                    for coordinate in (v,u):
                        if coordinate not in fixed:continue
                        radius=machining_radius(definitions[feature.definition]) if feature.definition else max(feature.diameter or 0,feature.clearance_diameter)/2
                        gap=radius+row['diameter']/2+required_wall(design,feature,definitions=definitions)+design.rules.minimum_access_gap
                        for sign in (-1,1):
                            target=design.model_copy(deep=True);item=next(f for f in target.features if f.id==feature.id)
                            setattr(item,'u' if coordinate==u else 'v',fixed[coordinate]+sign*gap)
                            yield 'Separate interfaces implicated by saved Exact contact',target
            if feature.kind=='cavity':
                lane=max((n.diameter for n in design.nets if n.id in set(feature.circuits.values())),default=0)+required_wall(design,feature,definitions=definitions)
                for field,sign in itertools.product(('u','v'),(-1,1)):
                    target=design.model_copy(deep=True);item=next(f for f in target.features if f.id==feature.id)
                    setattr(item,field,getattr(item,field)+sign*lane)
                    yield 'Open a local corridor at an implicated hydraulic interface',target
        queues=[iter(moves(f)) for f in implicated_features]
        while queues:
            active=[]
            for queue in queues:
                try:proposal=next(queue)
                except StopIteration:continue
                active.append(queue);yield proposal
            queues=active
    def growth():
        if not allow_growth or not grow or not (baseline['blocked_nets'] or baseline['conflicts']):return
        # Missing source data/method or tooling alone cannot justify more stock.
        spatial={'external_wall','source_protected','source_wall','cross_net_wall','feature_wall','installation_access','plug_cut'}
        if not exact_affected and not any(row[0] in spatial for row in baseline['conflicts']):return
        dims=dimensions(design.block);upper=design.constraints.envelope_max or (2000,2000,2000)
        bore=max((effective_net(design,n).diameter for n in design.nets),default=0)
        wall=max((required_wall(design,f,definitions=definitions) for f in design.features if f.id in movable),default=0)
        lane=max([routing_gap(design,definitions,face) for face in FACE_AXES]+[bore+wall+design.rules.minimum_access_gap])
        for axis in (range(3) if growth_axes is None else sorted(set(growth_axes))):
            # Insert a real lane BETWEEN interface groups, not a uniform
            # recentering that preserves the colliding routes' relative layout.
            planar=[f for f in design.features if f.id in movable and FACE_AXES[f.face][2]!=axis]
            if not planar:continue
            def coordinate(f):return f.u if FACE_AXES[f.face][0]==axis else f.v
            coordinates=sorted(set(coordinate(f) for f in planar))
            focus=[coordinate(f) for f in planar if f.id in affected] or coordinates
            center=sum(focus)/len(focus)
            cuts=[(a+b)/2 for a,b in zip(coordinates,coordinates[1:])]
            cut=min(cuts,key=lambda p:(abs(p-center),p)) if cuts else None
            shifted={f.id for f in planar if coordinate(f)>cut} if cut is not None else {f.id for f in planar if f.id in affected}
            if not shifted:continue
            delta=lane
            if dims[axis]+delta>upper[axis]:continue
            target=design.model_copy(deep=True);setattr(target.block,('length','width','height')[axis],dims[axis]+delta)
            # No stock SKU or source blank is inferred for expanded dimensions.
            if target.block.stock_id:continue
            for f in target.features:
                if f.id not in shifted:continue
                u,v,_,_=FACE_AXES[f.face]
                if u==axis:f.u+=delta
                if v==axis:f.v+=delta
            translations={round(pose(f,target.block)[0][axis]-pose(by_id[f.id],design.block)[0][axis],9)
                          for f in target.features if f.id in movable}
            if len(translations)<2:continue  # Uniform translation opens no corridor.
            yield 'Insert a machining corridor along '+('X','Y','Z')[axis]+' and separate interfaces',target
    # Exact evidence prioritizes local owners; it does not disable growth.
    # Round-robin preserves strategy opportunities inside the existing bound.
    queues=([iter(exact_local_moves()),iter(ports()),iter(growth())] if exact_affected else [iter(swaps()),iter(ports()),iter(growth())])
    if growth_axes is not None:queues=[queues[2],*queues[:2]]  # Reserve X/Y/Z opportunities in the AI-owned bound.
    seen=set();examined=0
    while queues and examined<48:
        active=[]
        for queue in queues:
            if examined>=48:break
            try:reason,target=next(queue)
            except StopIteration:continue
            active.append(queue);examined+=1
            signature=(dimensions(target.block),tuple((f.id,f.u,f.v) for f in target.features))
            if signature in seen or not _fits(target,definitions):continue
            seen.add(signature);yield reason,target
            if examined>=48:break
        queues=active


def plan(design,definitions=None,*,initial=False,evidence=None,movable_features=None,growth_axes=None,progress=None):
    from .engineering_db import definitions_for_design,thread_definitions_for_design,modifier_definitions_for_design,tool_definitions
    from .store import revision
    if evidence and evidence.get('source_revision')!=revision(design):evidence=None
    definitions=definitions if definitions is not None else definitions_for_design(design)
    threads=thread_definitions_for_design(design)
    modifiers=modifier_definitions_for_design(design) if any(f.machining_modifiers for f in design.features) else {}
    tools=tool_definitions('drill');limit=4 if initial else 8
    def report(index):
        def update(stage,**detail):
            if progress:progress(stage,layout=index,layout_limit=limit,**detail)
        return update
    baseline=assess(design,definitions,threads,modifiers,tools,report(1))
    proposals=[];evaluated=1
    for reason,target in alternatives(design,definitions,baseline,allow_growth=not initial,evidence=evidence,
            movable_features=movable_features,growth_axes=growth_axes):
        if evaluated>=limit:break
        if progress:progress('layout_alternate',layout=evaluated+1,layout_limit=limit)
        result=assess(target,definitions,threads,modifiers,tools,report(evaluated+1));evaluated+=1
        if {tuple(f) for f in result['fixed_conflicts']}-{tuple(f) for f in baseline['fixed_conflicts']}:continue
        if result['score']>=baseline['score']:continue
        if dimensions(target.block)!=dimensions(design.block) and result['feasibility_score']>=baseline['feasibility_score']:continue
        original={f.id:f for f in design.features};changes=[]
        for f in target.features:
            before=original[f.id]
            if (f.u,f.v)!=(before.u,before.v):changes.append(dict(id=f.id,face=f.face,before=[before.u,before.v],after=[f.u,f.v]))
        # Removing only uncommitted generated proposals is part of the explicit
        # Apply operation. Committed, stale stored and frozen cuts stay intact.
        # The corridor comparison coordinated all editable route proposals, so
        # Apply releases those proposals together. Fixed route owners stay out.
        affected=_routing_owners(target) if changes or dimensions(target.block)!=dimensions(design.block) else set()
        target.features=[f for f in target.features if f.route_net not in affected]
        for n in target.nets:
            if n.id in affected:n.route_state='unresolved';n.route_issue='';n.routing_variant=None
        proposals.append(dict(reason=reason,assessment=result,changes=changes,dimensions=list(dimensions(target.block)),
            affected_nets=sorted(affected),design=target.model_dump()))
    proposals.sort(key=lambda p:(p['assessment']['score'],len(p['changes']),p['reason']))
    movable,grow=_permissions(design)
    if movable_features is not None:grow=grow and movable<=set(movable_features);movable&=set(movable_features)
    return dict(source_revision=revision(design),status='ANALYTIC_LAYOUT_PROPOSALS',baseline=baseline,evidence=evidence,
        proposals=proposals[:3],evaluated_layouts=evaluated,layout_limit=limit,
        movable_features=sorted(movable),block_growth_allowed=grow and not initial and growth_axes!=(),
        message=('Saved Exact contact and unresolved terminals prioritized these local proposals. ' if evidence else '')+
            'Review proposed changes before applying. Analytic corridor samples do not prove physical infeasibility or exact safety. Exact Preview and Validate remain required.')
