"""General operation-space search and revisable multi-net corridor ownership.

Plans contain real Features. Fingerprints are diagnostics, never a project
format, path encoding, or a cross-process dependency.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import heapq
import itertools

from .routing_space import MachiningSpace,network_key
from .engineering_conditions import effective_net


def candidate(route):
    key='corridor3d:'+hashlib.sha256(repr(network_key(route)).encode()).hexdigest()[:24]
    return dict(key=key,route=route,risk=0,planner='corridor3d',candidate_id=key)


def materialized_proposal(authored,chosen,diagnostics=None):
    """Worker-safe handoff: explicit cuts and normal route state only."""
    from .routing import route_objective,_candidate_admitted
    if any(not _candidate_admitted(o) for o in chosen.values()):raise ValueError('Analytic candidates cannot be materialized as connected proposals')
    result=authored.model_copy(deep=True);owners=set(chosen)
    result.features=[f for f in result.features if f.route_net not in owners]
    result.features.extend(f.model_copy(deep=True) for o in chosen.values() for f in o['route'])
    rows=[]
    for net in result.nets:
        if net.id not in owners:continue
        option=chosen[net.id];route=[f for f in result.features if f.route_net==net.id]
        if route:net.diameter=route[0].diameter
        net.routing_variant=None;net.route_state='proposal';net.route_issue=''
        rows.append(dict(net=net.id,variant=None,planner='corridor3d',candidate_id=option['key'],
            route_state='proposal',connection_verified=option.get('connection_verified',False),
            admission=option.get('admission',{}),connectivity_detail=option.get('connectivity_detail',{}),
            drillings=len(route),plugs=sum(f.plugged for f in route),length_mm=sum(f.depth for f in route),
            objective=route_objective(result,route),status='CONNECTED_PROPOSAL_REQUIRES_FULL_VALIDATION',
            search_classification=(diagnostics or {}).get('classification')))
    return result,rows


def proposal_alternatives(source,target,eligible,excluded,snapshot,*,objective_ceiling=None):
    """Replan only explicitly released nets; return standalone Designs."""
    eligible={n.id for n in source.nets if n.id in eligible and n.routing=='automatic' and n.route_state=='unresolved' and not n.routing_variant}
    base=target.model_copy(deep=True)
    for net in base.nets:
        if net.id in eligible:net.route_state='unresolved';net.routing_variant=None
    selected={n:candidate([f for f in target.features if f.route_net==n]) for n in eligible}
    excluded_geometry=getattr(snapshot,'corridor_excluded',set())
    excluded_geometry.add(tuple(sorted((name,network_key(option['route'])) for name,option in selected.items())))
    snapshot.corridor_excluded=excluded_geometry
    chosen,detail=coordinate_routes(base,[n for n in base.nets if n.id in eligible],snapshot.definitions,snapshot.threads,snapshot.modifiers,
        seeds=selected,snapshot=snapshot,excluded=excluded_geometry,objective_ceiling=objective_ceiling)
    if not chosen:return []
    proposal,rows=materialized_proposal(base,chosen,detail)
    signature=tuple(sorted((r['net'],r['candidate_id']) for r in rows))
    if signature in excluded:return []
    from .routing import route_objective
    return [(route_objective(proposal,[f for f in proposal.features if f.route_net]),proposal,signature,'Alternative materialized 3D machining network')]


def _distance(a,b):return sum(abs(x-y) for x,y in zip(a,b))


class _PathSearch:
    """One real path frontier; a step completes exactly one label expansion."""
    def __init__(self,space,start,goal,route,forbidden,diagnostics,*,starts=None,trim=True,observe=None):
        from .routing import route_objective
        serial=itertools.count();queue=[];seen={};expanded=set();solutions=[]
        self.space=space;self.goal=goal;self.forbidden=forbidden;self.diagnostics=diagnostics
        self.trim=trim;self.done=False;self.observe=observe
        self.queue=queue;self.seen=seen;self.expanded=expanded;self.solutions=solutions
        def push(point,cuts,path,cursor=0):
            token=(point,network_key(cuts),cursor)
            if token in seen:return
            seen[token]=True
            objective=route_objective(space.design,cuts,definitions=space.definitions)
            axes=sum(abs(x-y)>1e-7 for x,y in zip(point,goal))
            heapq.heappush(queue,((len(cuts)+axes+cursor//24,_distance(point,goal),objective),next(serial),point,cuts,path,cursor))
        for point,cuts in starts if starts is not None else [(start,route)]:push(point,cuts,[])
        self.push=push

    def step(self,budget):
        from .routing import route_objective
        space=self.space;goal=self.goal;forbidden=self.forbidden;diagnostics=self.diagnostics
        queue=self.queue;seen=self.seen;expanded=self.expanded;solutions=self.solutions;push=self.push
        _,_,point,cuts,path,cursor=heapq.heappop(queue);budget['used']+=1
        expanded.add((point,network_key(cuts),cursor))
        if self.observe:self.observe(dict(point=point,goal=goal,cursor=cursor,
            geometry=hashlib.sha256(repr(network_key(cuts)).encode()).hexdigest(),
            last_segment=path[-1] if path else None))
        if point==goal:
            if network_key(cuts) not in forbidden:
                solutions.append((cuts,path))
                limit=budget.get('alternatives',4)
                if limit is not None and len(solutions)>=limit:self.done=True
            return
        per_axis={}
        for axis in sorted(range(3),key=lambda i:(point[i]==goal[i],-abs(point[i]-goal[i]),i)):
            # All event coordinates were offered by the preceding straight
            # action. Subdividing that SAME straight cut adds no machining.
            if path and all(abs(path[-1][0][i]-path[-1][1][i])<1e-7 for i in range(3) if i!=axis):continue
            per_axis[axis]=space.values(axis,point[axis],goal[axis])
        neighbours=[(axis,values[i]) for i in range(max((len(v) for v in per_axis.values()),default=0)) for axis,values in per_axis.items() if i<len(values)]
        found=False
        for axis,coordinate in neighbours[cursor:cursor+24]:
            end=list(point);end[axis]=coordinate;end=tuple(end)
            for trial in space.operations(point,end,cuts):found=True;push(end,trial,[*path,(point,end)])
        if cursor+24<len(neighbours):
            push(point,cuts,path,cursor+24)
            diagnostics['coordinate_pages_deferred']=diagnostics.get('coordinate_pages_deferred',0)+1
        elif not found and budget['used']%16==0:
            for axis in per_axis:space.refine(axis,(point[axis]+goal[axis])/2)
        if self.trim and len(queue)>budget['limit']*8:
            kept=heapq.nsmallest(budget['limit']*8,queue);ids={row[1] for row in kept}
            for row in queue:
                if row[1] not in ids:
                    token=(row[2],network_key(row[3]),row[5])
                    if token not in expanded:seen.pop(token,None)
                    samples=diagnostics.setdefault('deferred_label_examples',[])
                    if len(samples)<16:samples.append(dict(point=row[2],coordinate_cursor=row[5],cut_ids=[f.id for f in row[3]],
                        entry_faces=sorted({f.face for f in row[3]}),state='ANALYTIC_SCREENED_PARTIAL_NOT_EXACT'))
            diagnostics['deferred_labels']=diagnostics.get('deferred_labels',0)+len(queue)-len(kept)
            queue[:]=kept;heapq.heapify(queue)
        if budget['used']%32==0:
            from .timing import diagnostic,progress,summary
            status=dict(net=space.net.id,planner_labels=budget['used'],planner_label_limit=budget['limit'],machining_operations=space.generated)
            progress('access',summary()['progress'].get('percent',8),routing=status)
            diagnostic('corridor_search',dict(**status,labels=budget['used'],label_limit=budget['limit'],frontier=len(queue)))



def _path(space,start,goal,route,budget,forbidden,diagnostics,*,starts=None):
    # Manual/default callers retain their bounded one-shot search policy.
    search=_PathSearch(space,start,goal,route,forbidden,diagnostics,starts=starts)
    while search.queue and budget['used']<budget['limit'] and not search.done:search.step(budget)
    diagnostics.update(labels=budget['used'],label_limit=budget['limit'],frontier_labels=len(search.queue),
        termination='LABEL_BUDGET' if search.queue and budget['used']>=budget['limit'] else
            'SOLUTIONS_GENERATED' if search.solutions else 'EXPLORED_FRONTIER_EMPTY')
    return search.solutions


def _prepare_net(design,net,definitions,threads,modifiers,*,reserved=(),cache=None,tools=None):
    from .kinematics import resolve_parents
    design=resolve_parents(design)
    net=effective_net(design,net)
    space=MachiningSpace(design,net,definitions,threads,modifiers,reserved=reserved,cache=cache,tools=tools)
    members=sorted(net.members);detail=dict(net=net.id,planner='corridor3d',exact_verified=False,lifecycle=[])
    if any(m not in space.points for m in members) or len(members)<2 or space.failures.get('SOURCE_DATA_UNRESOLVED'):
        detail.update(classification='SOURCE_DATA_UNRESOLVED',termination='SOURCE_DATA_UNRESOLVED',missing_terminals=[m for m in members if m not in space.points],labels=0,generated_candidates=0);return space,members,detail,None,None
    barrier=space.barrier()
    if barrier:
        detail.update(space.diagnostics(barrier['rule']),classification=barrier['rule'],barrier=barrier,labels=0,generated_candidates=0);return space,members,detail,None,None
    # Source-derived face-open turns supplement actual zone centres. No source
    # dimensions or window numbering are inferred.
    from .branch_candidates import face_window_points
    windows=face_window_points(design,net,definitions,threads,modifiers)
    aliases={m:list(dict.fromkeys([space.points[m],*([windows[m]] if m in windows else [])])) for m in members}
    from .cavity_access import cavity_terminal_candidates
    from .closure_runtime import bind_route
    from .kinematics import pose,FACE_AXES
    seeds={}
    approaches={member:[bore] for member,bore in cavity_terminal_candidates(design,net,definitions,threads,modifiers).items()}
    for member,bores in space.narrow_window_seeds().items():approaches.setdefault(member,[]).extend(bores)
    for member,bores in approaches.items():
        for bore in bores:
            if bore.id=='AXIAL-PROBE':bore=bore.model_copy(update=dict(id='R3D_AX_'+hashlib.sha256(member.encode()).hexdigest()[:16]))
            bore=bind_route(design,[bore])[0];origin,direction=pose(bore,design.block);axis=FACE_AXES[bore.face][2]
            low=bore.plug_length+space.radius+space.wall;high=bore.depth-space.radius-space.wall
            possible=[]
            for coordinate in [*space.coordinates[axis],space.sizes[axis]/2]:
                depth=(coordinate-origin[axis])*direction[axis]
                if low<=depth<=high:
                    point=tuple(origin[i]+direction[i]*depth for i in range(3));possible.append(point);seeds[(member,point)]=[bore]
            centre=tuple(sum(space.points[m][i] for m in members if m!=member)/(len(members)-1) for i in range(3))
            aliases[member]=list(dict.fromkeys([*sorted(possible,key=lambda p:_distance(p,centre)),*aliases[member]]))
    return space,members,detail,aliases,seeds


def plan_net(design,net,definitions,threads,modifiers,*,reserved=(),label_limit=8192,alternatives=4,
             forbidden=(),cache=None,tools=None,ai_context=None):
    """Lazy sparse search; terminal order and attachment geometry are revisable."""
    if ai_context is not None:
        return ai_context.advance(design,net,definitions,threads,modifiers,reserved=reserved,
            label_limit=label_limit,alternatives=alternatives,forbidden=forbidden,cache=cache,tools=tools)
    space,members,detail,aliases,seeds=_prepare_net(design,net,definitions,threads,modifiers,
        reserved=reserved,cache=cache,tools=tools)
    if aliases is None:return [],detail
    design=space.design;net=space.net
    budget=dict(used=0,limit=label_limit,alternatives=alternatives)
    routes=[];orders=[members,list(reversed(members))] if len(members)>2 else [members]
    from .routing import route_objective
    for order in orders:
        frontier=[];visited=set();serial=itertools.count()
        def enqueue(index,cuts,root,paths,blocked=()):
            token=(index,network_key(cuts),root,blocked)
            if token in visited:return
            visited.add(token)
            heapq.heappush(frontier,(len(order)-index,route_objective(design,cuts,definitions=definitions),next(serial),index,cuts,root,paths,blocked))
        enqueue(1,[],None,[])
        while frontier and (budget['used']<label_limit or frontier[0][3]==len(order)):
            _,_,_,index,cuts,root,paths,blocked=heapq.heappop(frontier)
            if index==len(order):
                if network_key(cuts) not in set(forbidden):routes.append(candidate(cuts))
                if len(routes)>=alternatives:break
                continue
            member=order[index];attempted=set(blocked)
            for goal in aliases[member]:
                if root is None:
                    starters=[(point,seeds.get((order[0],point),[])) for point in aliases[order[0]]]
                else:
                    points={root,*space.junctions(cuts,goal),*[p for path in paths for segment in path for p in segment]}
                    starters=[(point,cuts) for point in sorted(points,key=lambda p:_distance(p,goal))]
                initial_states=[]
                for point,initial in starters:
                    for bore in seeds.get((member,goal),[]):initial=space.attach(initial,bore)
                    initial_states.append((point,initial))
                found=_path(space,None,goal,[],budget,set(forbidden)|set(blocked),detail,starts=initial_states)
                for r,path in found:
                    attempted.add(network_key(r))
                    enqueue(index+1,r,root if root is not None else path[0][0] if path else goal,[*paths,path])
                if budget['used']>=label_limit:break
            if attempted-set(blocked):enqueue(index,cuts,root,paths,tuple(sorted(attempted)))
        detail['deferred_tree_states']=len(frontier)
        detail['deferred_tree_examples']=[dict(next_terminal_index=row[3],cut_ids=[f.id for f in row[4]],root=row[5],
            state='ANALYTIC_PARTIAL_NOT_EXACT') for row in heapq.nsmallest(8,frontier)]
        if routes:
            detail['deferred_terminal_orders']=len(orders)-orders.index(order)-1
            break  # A resumable batch; do not optimize another order before CAD.
        if budget['used']>=label_limit:break
    unique={o['key']:o for o in routes}
    options=sorted(unique.values(),key=lambda o:(route_objective(design,o['route'],definitions=definitions),o['key']))
    detail.update(space.diagnostics(detail.get('termination','LABEL_BUDGET')))
    detail.update(labels=budget['used'],generated_candidates=len(options),
        lifecycle=[dict(candidate_id=o['key'],state='ANALYTIC_SCREENED_NOT_EXACT') for o in options],
        classification='CANDIDATE_ADMISSION_PENDING' if options else 'CORRIDOR_GENERATION_LIMIT' if budget['used']>=label_limit else 'NO_ADMISSIBLE_CORRIDOR_IN_EXPLORED_SPACE')
    return options,detail


def coordinate_routes(source,nets,definitions,threads,modifiers,*,seeds=None,snapshot=None,label_limit=8192,state_limit=1000,pair_limit=4000,excluded=(),label_total_limit=65536,exact_connectivity=True,objective_ceiling=None):
    """Rip up an implicated group, backtrack entries, never touch fixed cuts."""
    from .routing import route_obstructions,_conflict_objective,_verify_route_candidate,_candidate_admitted,route_objective,_ProposalSnapshot
    from .kinematics import resolve_parents
    source=resolve_parents(source)
    snapshot=snapshot or _ProposalSnapshot(source,definitions,threads,modifiers)
    if not hasattr(snapshot,'corridor_work'):
        snapshot.corridor_work=dict(states=0,pairs=0,labels=0)
        snapshot.corridor_limits=dict(states=state_limit,pairs=pair_limit,labels=label_total_limit)
    work=snapshot.corridor_work;limits=snapshot.corridor_limits
    state_limit=min(state_limit,max(0,limits['states']-work['states']))
    pair_limit=min(pair_limit,max(0,limits['pairs']-work['pairs']))
    state_limit=min(state_limit,max(0,1000-sum(r.get('states',0) for r in snapshot.combination_diagnostics)))
    pair_limit=min(pair_limit,max(0,4000-snapshot.combination_budget['used']))
    label_total_limit=min(label_total_limit,max(0,limits['labels']-work['labels']))
    nets={n.id:effective_net(source,n) for n in nets if n.routing=='automatic' and n.route_state=='unresolved' and not n.routing_variant}
    fixed=source.model_copy(update=dict(features=[f for f in source.features if f.route_net not in nets or f.frozen_net]))
    state={name:deepcopy(o) for name,o in (seeds or {}).items() if name in nets}
    stats=dict(planner='corridor3d',states=0,state_limit=state_limit,pair_screens=0,pair_limit=pair_limit,
        events=[],net_searches=[],search_history=[],deferred=[],exact_admitted=0,classification=None,labels=0,label_total_limit=label_total_limit,
        deferred_count=0,complete_candidates=0,candidate_batches=0,search_count=0)
    classifications=Counter()
    def finish(chosen):
        stats['work_used_before']=dict(work)
        work['states']+=stats['states'];work['pairs']+=stats['pair_screens'];work['labels']+=stats['labels']
        snapshot.combination_budget['used']+=stats['pair_screens']
        snapshot.combination_diagnostics.append(dict(planner='corridor3d',states=stats['states'],pair_screens=stats['pair_screens'],exit_reason=stats['classification']))
        stats['work_used_after']=dict(work);stats['operation_limits']=dict(limits)
        snapshot.corridor_last=stats
        from .timing import diagnostic
        diagnostic('corridor_coordination',stats)
        return chosen,stats
    if not nets or not state_limit or not pair_limit or not label_total_limit:
        stats['classification']='CORRIDOR_GENERATION_LIMIT' if not label_total_limit else 'MULTINET_COORDINATION_LIMIT'
        stats['remaining_conflicts']=[]
        return finish(None)
    def failures(chosen):
        context=fixed.model_copy(update=dict(features=[*fixed.features,*[f for o in chosen.values() for f in o['route']]]))
        result=set()
        for name,o in chosen.items():
            result|=route_obstructions(context,nets[name],o['route'],threads,definitions,modifiers,snapshot.obstructions)
        return result
    initial=failures(state);owners={f.id:name for name,o in state.items() for f in o['route']}
    implicated={owners[i] for row in initial for i in row[1:] if i in owners}|(set(nets)-set(state))
    if not implicated:implicated=set(nets)
    groups=[{name} for name in sorted(implicated)] if state else [set(nets)]
    # Actual conflicting cut ownership, not a preset circuit order. Try each
    # edge before releasing its connected component or the entire layout.
    edges={tuple(sorted({owners[i] for i in row[1:] if i in owners})) for row in initial}
    edges={edge for edge in edges if len(edge)>1}
    groups.extend(set(edge) for edge in sorted(edges))
    components=[];unvisited=set(implicated)
    while unvisited:
        component={min(unvisited)};pending=list(component)
        while pending:
            current=pending.pop()
            for edge in edges:
                if current in edge:
                    added=set(edge)-component;component.update(added);pending.extend(sorted(added))
        unvisited-=component
        if len(component)>2:components.append(component)
    groups.extend(components)
    if state and len(implicated)>1:groups.append(set(implicated))
    if state and implicated!=set(nets):groups.append(set(nets))
    groups=list({tuple(sorted(group)):group for group in groups}.values())
    # Small first probes cannot starve paired/component release. Failed probes
    # are revisited later with the remaining weighted share, all under the SAME
    # aggregate label/state/pair ceilings. These are scheduling batches only.
    jobs=[(group,True) for group in groups]
    if len(groups)>1:jobs.extend((group,False) for group in groups if len(group)<=2)
    stats['release_groups']=[dict(nets=sorted(g),initial_probe=probe) for g,probe in jobs]
    best=state;best_fail=initial;serial=itertools.count()
    def fingerprint(chosen):return tuple(sorted((name,network_key(o['route'])) for name,o in chosen.items()))
    def record_deferred(row):
        stats['deferred_count']+=1
        if len(stats['deferred'])<64:stats['deferred'].append(row)
    for name,option in state.items():
        if exact_connectivity and not _candidate_admitted(option,nets[name]):_verify_route_candidate(fixed,nets[name],option,snapshot,prune=False)
    for job_index,(group,probe) in enumerate(jobs):
        orders=[sorted(group,key=lambda n:(-len(nets[n].members),n)),sorted(group,reverse=True)]
        orders=list(dict.fromkeys(tuple(o) for o in orders))
        weight=sum(len(g) for g,_ in jobs[job_index:])
        allocation=max(1,(label_total_limit-stats['labels'])*len(group)//weight)
        if probe and len(groups)>1 and len(group)<=2:allocation=min(allocation,512*len(group))
        group_end=min(label_total_limit,stats['labels']+allocation)
        for order_index,order in enumerate(orders):
            retained={n:o for n,o in state.items() if n not in group}
            order_end=stats['labels']+max(0,(group_end-stats['labels'])//(len(orders)-order_index))
            stats['events'].append(dict(action='RIP_UP',nets=sorted(group),order=order,initial_probe=probe,label_allocation=order_end-stats['labels']))
            frontier=[];visited=set()
            def enqueue(index,partial,blocked=()):
                if len(fixed.features)+sum(len(o['route']) for o in partial.values())>120:
                    record_deferred(dict(state='SCHEMA_FEATURE_LIMIT',nets=sorted(partial),feature_count=len(fixed.features)+sum(len(o['route']) for o in partial.values())))
                    return
                token=(index,fingerprint(partial),tuple(sorted(blocked)))
                if token in visited:return
                visited.add(token)
                objective=route_objective(fixed,[f for o in partial.values() for f in o['route']],definitions=definitions)
                heapq.heappush(frontier,(len(order)-index,objective,next(serial),index,partial,blocked))
            enqueue(0,retained)
            while frontier and stats['states']<state_limit and stats['pair_screens']<pair_limit and (stats['labels']<order_end or frontier[0][3]==len(order)):
                _,_,_,index,partial,blocked=heapq.heappop(frontier);stats['states']+=1
                if index==len(order):
                    if set(partial)!=set(nets) or exact_connectivity and any(not _candidate_admitted(o,nets[n]) for n,o in partial.items()):continue
                    stats['complete_candidates']+=1;conflict=failures(partial)
                    if not conflict and fingerprint(partial) not in excluded:
                        all_drills=[f for f in fixed.features if f.kind=='drilling' and not f.suppressed]+[f for o in partial.values() for f in o['route']]
                        if objective_ceiling is not None and route_objective(fixed,all_drills,definitions=definitions)>=objective_ceiling:
                            record_deferred(dict(state='MANUFACTURING_OBJECTIVE_NOT_IMPROVED',candidates={n:o['key'] for n,o in partial.items()}));continue
                        stats.update(classification='ANALYTIC_AND_CONNECTIVITY_CLEAR_REQUIRES_PRODUCTION_CAD' if exact_connectivity else 'ANALYTIC_ONLY_NOT_VALIDATED',selected={n:o['key'] for n,o in partial.items()},pending_coordination_states=len(frontier))
                        return finish(partial)
                    if not conflict:record_deferred(dict(state='PRODUCTION_CANDIDATE_EXCLUDED',candidates={n:o['key'] for n,o in partial.items()}))
                    if _conflict_objective(conflict)<_conflict_objective(best_fail):best,best_fail=partial,conflict
                    continue
                name=order[index];reserved=[f for o in partial.values() for f in o['route']]
                stats['candidate_batches']+=1
                if blocked:stats['events'].append(dict(action='NEXT_CANDIDATE_BATCH',net=name,excluded=len(blocked)))
                options,detail=plan_net(fixed,nets[name],definitions,threads,modifiers,reserved=reserved,
                    label_limit=min(label_limit,max(1,(order_end-stats['labels'])//max(1,len(order)-index))),cache=snapshot.obstructions,tools=snapshot.tools,forbidden=blocked)
                stats['labels']+=detail.get('labels',0)
                stats['search_count']+=1;classifications[detail['classification']]+=1
                stats['net_searches']=(stats['net_searches']+[detail])[-32:]
                context=fixed.model_copy(update=dict(features=[*fixed.features,*reserved]))
                admitted=0
                attempted=set(blocked)
                for option in options:
                    lifecycle=next(row for row in detail['lifecycle'] if row['candidate_id']==option['key'])
                    fields={'id','face','u','v','depth','diameter','tip_angle','plugged','plug_length','closure_definition_id','route_net','circuit','connects_to'}
                    lifecycle['generated_drillings']=[f.model_dump(mode='json',include=fields) for f in option['route']]
                    attempted.add(network_key(option['route']))
                    required=max(1,len(partial))
                    if stats['pair_screens']+required>pair_limit:
                        lifecycle['state']='PAIR_BUDGET_ADMISSION_PENDING'
                        record_deferred(dict(candidate_id=option['key'],state='PAIR_BUDGET_ADMISSION_PENDING'));continue
                    stats['pair_screens']+=required
                    if exact_connectivity and not _verify_route_candidate(context,nets[name],option,snapshot):
                        lifecycle.update(state='EXACT_REJECTED',failures=option.get('conflicts',[]))
                        record_deferred(dict(candidate_id=option['key'],state='EXACT_REJECTED',failures=option.get('conflicts',[])));continue
                    if exact_connectivity:stats['exact_admitted']+=1
                    admitted+=1
                    lifecycle.update(state='EXACT_CONNECTIVITY_ADMITTED' if exact_connectivity else 'ANALYTIC_ONLY_NOT_VALIDATED',
                        retained_drillings=[f.model_dump(mode='json',include=fields) for f in option['route']])
                    enqueue(index+1,{**partial,name:option})
                # Keep every complete candidate lifecycle, including early
                # batches. Only the verbose space snapshots roll over at 32.
                stats['search_history'].append({k:detail.get(k) for k in ('net','classification','termination','labels',
                    'generated_operations','coordinate_events','unexpanded_coordinate_events','frontier_labels',
                    'deferred_tree_states','deferred_labels','lifecycle')})
                if not admitted:
                    stats['events'].append(dict(action='BACKTRACK_NET',net=name,reason=detail['classification']))
                if options and stats['labels']<order_end:
                    # Resumable parent generation is queued BEHIND its deeper
                    # children, even when the first batch was individually legal.
                    # A legal layer #17 must not disappear after four failures
                    # to allocate later nets against the earlier layers.
                    enqueue(index,partial,tuple(sorted(attempted)))
                # Frontier is a resumable queue, not queue[:4]. Later entrances
                # and layers remain available under the SAME state/pair budget.
                if len(frontier)>4:stats['pending_coordination_states']=len(frontier)
            if frontier:record_deferred(dict(state='COORDINATION_BUDGET_DEFERRED',states=len(frontier),nets=sorted(group),initial_probe=probe))
            if set(best)==set(nets) and _conflict_objective(best_fail)<_conflict_objective(failures(state)):
                state=deepcopy(best)
                stats['events'].append(dict(action='RETAIN_PARTIAL_CONFLICT_REDUCTION',selected={n:o['key'] for n,o in state.items()},
                    remaining_conflicts=[list(f) for f in sorted(best_fail)],status='UNRESOLVED_NOT_PRODUCTION_VALIDATED'))
            stats['events'].append(dict(action='BACKTRACK',nets=sorted(group)))
    pending=any(r['state'].endswith(('PENDING','DEFERRED')) for r in stats['deferred'])
    kinds=classifications
    stats.update(classification='CANDIDATE_TRUNCATION' if pending else 'CORRIDOR_GENERATION_LIMIT' if stats['labels']>=label_total_limit or kinds.get('CORRIDOR_GENERATION_LIMIT') else
        'FIXED_MACHINING_BLOCKED' if kinds.get('FIXED_MACHINING_BLOCKED') else 'SOURCE_DATA_UNRESOLVED' if kinds.get('SOURCE_DATA_UNRESOLVED') else
        'EXACT_CANDIDATE_REJECTED' if any(r['state']=='EXACT_REJECTED' for r in stats['deferred']) else 'MULTINET_COORDINATION_LIMIT',
        remaining_conflicts=[list(f) for f in sorted(best_fail)],search_classifications=dict(kinds))
    return finish(None)
