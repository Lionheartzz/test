"""AI-only assembly search over real Router cuts, never full Design approval.

Keep compatible partial assignments, insert missing Nets, and release only
their actual blockers. No source placement or shared Model policy changes.
"""
import itertools
from collections import deque

from .route_catalog import geometry_key


def fingerprint(chosen):
    return tuple(sorted((n,geometry_key(o['route'])) for n,o in chosen.items()))


def extend(source,nets,pools,pair,seed,work,*,eligible=lambda core:True):
    """Maximum compatible partial CSP. A blocked Net is deferred, not fatal."""
    from ..routing import route_objective
    fits=lambda chosen:len(source.features)+sum(len(o['route']) for o in chosen.values())<=120
    seed={n:o for n,o in seed.items() if eligible({n:o})}
    best=dict(seed) if fits(seed) else {};seen=set();conflicts=[]
    def rank(chosen):
        return (-len(chosen),route_objective(source,[f for o in chosen.values() for f in o['route']]))
    def search(chosen,remaining):
        nonlocal best
        if not eligible(chosen):return
        if work['states']>=work['limit']:return
        if len(source.features)+sum(len(o['route']) for o in chosen.values())>120:return
        token=(fingerprint(chosen),tuple(sorted(remaining)))
        if token in seen:return
        seen.add(token);work['states']+=1
        if rank(chosen)<rank(best):best=dict(chosen)
        if len(best)==len(nets) or len(chosen)+len(remaining)<=len(best):return
        domains={};blocked={}
        for name in sorted(remaining):
            choices=[];rejected=[]
            for option in pools.get(name,[]):
                if not eligible({**chosen,name:option}):continue
                blockers={};unknown=False
                for other,previous in chosen.items():
                    failure=pair(name,option,other,previous)
                    if any(f[0]=='search_budget' for f in failure):unknown=True;break
                    if failure:blockers[other]=sorted(failure)
                if unknown:return
                if blockers:rejected.append((len(blockers),option['key'],blockers))
                else:choices.append(option)
            domains[name]=choices
            if not choices and rejected:blocked[name]=min(rejected,key=lambda row:row[:2])
        if not remaining:return
        # Continue other Nets when one has no current insertion. Retain the
        # blocking actual cut pairs for the next release/corridor batch.
        impossible={n for n,d in domains.items() if not d}
        for name,(_,key,blockers) in blocked.items():
            if len(conflicts)<64:conflicts.append(dict(missing_net=name,candidate=key,blockers=blockers))
        remaining=remaining-impossible
        if not remaining:return
        name=min(remaining,key=lambda n:(len(domains[n]),-len(nets[n].members),n))
        for option in domains[name]:
            search({**chosen,name:option},remaining-{name})
            if len(best)==len(nets) or work['states']>=work['limit']:return
        # A valid route for this Net might block two later Nets. Deferring it
        # is necessary to discover a better partial combination.
        search(chosen,remaining-{name})
    search(dict(seed),set(nets)-set(seed))
    return best,conflicts


def improve(source,nets,pools,pair,seed,work,*,eligible=lambda core:True):
    """Insert first; then finite conflict-directed release of retained Nets."""
    best,conflicts=extend(source,nets,pools,pair,seed,work,eligible=eligible)
    events=[];groups=set()
    for name in sorted(set(nets)-set(best)):
        for option in pools.get(name,[]):
            if not eligible({name:option}):continue
            blockers={other for other,previous in best.items() if pair(name,option,other,previous)}
            if blockers:groups.add(tuple(sorted({name,*blockers})))
    # Paired/small groups first. The released route is not irrevocably fixed;
    # every replacement is checked against ALL retained Nets.
    for group in sorted(groups,key=lambda g:(len(g),g)):
        if work['states']>=work['limit'] or len(best)==len(nets):break
        fixed={n:o for n,o in best.items() if n not in group}
        trial,failed=extend(source,nets,pools,pair,fixed,work,eligible=eligible)
        events.append(dict(action='RELEASE_AND_REINSERT',nets=list(group),retained=sorted(fixed),
                           before=len(best),after=len(trial)))
        conflicts.extend(failed)
        if len(trial)>len(best):best=trial
    return best,events,conflicts[:64]


def entry_alternatives(source,net,option,reserved,definitions,threads,modifiers,tools,cache):
    """Re-machine a real required span from either surface via MachiningSpace.

    Required source/own-cut contact coordinates determine depth. Complete
    entry, tip, plug, wall and all third-Net reservations are screened there.
    Exact still verifies every hydraulic opening of the resulting network.
    """
    from ..routing_space import MachiningSpace
    from ..routing import segment,segment_distance
    from ..kinematics import pose,FACE_AXES
    space=MachiningSpace(source,net,definitions,threads,modifiers,reserved=reserved,tools=tools,cache=cache)
    for bore in option['route']:
        if bore.direction or bore.frozen_net:continue
        origin,direction=pose(bore,source.block);axis=FACE_AXES[bore.face][2];contacts=[]
        for member in net.members:
            point=space.points.get(member)
            if point is None:continue
            projection=tuple(point[i] if i==axis else origin[i] for i in range(3))
            if sum((point[i]-projection[i])**2 for i in range(3))<=(net.diameter/2)**2+1e-6:
                contacts.append(projection)
        for other in option['route']:
            if other.id==bore.id or other.direction:continue
            other_axis=FACE_AXES[other.face][2]
            if other_axis==axis:continue
            if segment_distance(*segment(bore,source.block),*segment(other,source.block))>(bore.diameter+other.diameter)/2:continue
            point=list(origin);point[axis]=pose(other,source.block)[0][axis];contacts.append(tuple(point))
        if len(contacts)<2:continue
        low=min(contacts,key=lambda p:p[axis]);high=max(contacts,key=lambda p:p[axis])
        if low==high:continue
        retained=[f for f in option['route'] if f.id!=bore.id]
        for route in space.operations(low,high,retained):
            old_ids={f.id for f in retained}
            additions=[f for f in route if f.id not in old_ids]
            if len(additions)!=1:continue
            replacement=additions[0].model_copy(update=dict(id=bore.id,connects_to=bore.connects_to))
            yield dict(key='entry:'+option['key']+':'+bore.id+':'+replacement.face,
                       route=[*retained,replacement],risk=0,connection_verified=False)


def bypass_alternatives(source,net,option,reserved,definitions,threads,modifiers,tools,cache):
    """Replace an obstructed machining span with an event-derived branch tree.

    Every leg is an independently machinable full surface drilling. Required
    source/own-cut contact stations attach to the new trunk; no internal-only
    polyline, fake node, source modification or direct-contact waiver.
    """
    from ..routing_space import MachiningSpace
    from ..routing import route_obstructions,segment,segment_distance
    from ..kinematics import pose,FACE_AXES
    space=MachiningSpace(source,net,definitions,threads,modifiers,reserved=reserved,tools=tools,cache=cache)
    conflicts=route_obstructions(space.context,net,option['route'],threads,definitions,modifiers,cache)
    reserved_ids={f.id for f in reserved};source_ids={f.id:f for f in source.features}
    damaged={key for row in conflicts if any(k in reserved_ids for k in row[1:]) for key in row[1:] if key not in reserved_ids}
    for bore in option['route']:
        if bore.id not in damaged or bore.direction or bore.frozen_net or bore.connects_to or any(bore.id in f.connects_to for f in option['route']):continue
        origin,direction=pose(bore,source.block);axis=FACE_AXES[bore.face][2];stations=set()
        for member in net.members:
            point=space.points.get(member);owner,_,zone=member.partition(':');feature=source_ids.get(owner)
            if point is None or feature is None:continue
            definition=definitions.get(feature.definition)
            window=next((z for z in definition.zones if z.id==zone or feature.kind=='port'),None) if definition else None
            radius=window.diameter/2 if window else (feature.diameter or net.diameter)/2
            projection=tuple(point[i] if i==axis else origin[i] for i in range(3))
            along=(point[axis]-origin[axis])*direction[axis]
            if 0<=along<=bore.depth and sum((point[i]-projection[i])**2 for i in range(3))<(radius+net.diameter/2)**2:
                stations.add(projection)
        for other in option['route']:
            if other.id==bore.id or other.direction or FACE_AXES[other.face][2]==axis:continue
            if segment_distance(*segment(bore,source.block),*segment(other,source.block))<(bore.diameter+other.diameter)/2:
                point=list(origin);point[axis]=pose(other,source.block)[0][axis];stations.add(tuple(point))
        if len(stations)<2:continue
        remaining=[f for f in option['route'] if f.id!=bore.id]
        stations=sorted(stations,key=lambda p:p[axis]);queues=[]
        for transverse in set(range(3))-{axis}:
            def planes(transverse=transverse):
                coordinates=sorted(space.coordinates[transverse],key=lambda x:(abs(x-origin[transverse]),x))
                for coordinate_index,coordinate in enumerate(coordinates):
                    # Returning no route must still spend search work. Resume
                    # this exact iterator later; a checkpoint is NOT a route.
                    yield dict(checkpoint='BYPASS_PLANE',net=net.id,bore=bore.id,axis=transverse,coordinate=coordinate)
                    if coordinate_index%16==0:
                        from .. import timing
                        timing.progress('conflicts',timing.summary().get('progress',{}).get('percent',8),
                            routing=dict(net=net.id,fragment=bore.id,plane_events_checked=coordinate_index,plane_events_total=len(coordinates)))
                    if abs(coordinate-origin[transverse])<net.diameter/2:continue
                    points=[tuple(coordinate if i==transverse else p[i] for i in range(3)) for p in stations]
                    trunks=space.operations(points[0],points[-1],remaining)
                    for trunk in trunks:
                        frontier=[trunk]
                        for station,target in zip(stations,points):
                            next_states=[trial for route in frontier for trial in space.operations(station,target,route)]
                            frontier=next_states[:4]
                            if not frontier:break
                        for route in frontier:
                            yield dict(key='bypass:'+bore.id+':'+str(transverse)+':'+str(coordinate),
                                route=route,risk=0,connection_verified=False)
            queues.append(iter(planes()))
        while queues:
            active=[]
            for queue in queues:
                try:yield next(queue);active.append(queue)
                except StopIteration:pass
            queues=active


def corridor_alternatives(source,net,bases,reserved,definitions,threads,modifiers,tools,cache,excluded=None,allow_bypass=True):
    from ..routing import route_from_variant
    from ..routing_space import MachiningSpace
    from ..kinematics import FACE_AXES
    space=MachiningSpace(source,net,definitions,threads,modifiers,reserved=reserved,tools=tools,cache=cache)
    # A reservation is a read-only obstacle in this disposable generation
    # context. Stable variant construction otherwise strips every mutable
    # sibling route before choosing entries, defeating joint coordination.
    context=source.model_copy(deep=True)
    names={f.route_net for f in reserved}
    for n in context.nets:
        if n.id in names:n.route_state='committed'
    context.features.extend(reserved)
    # Real obstacle-boundary/free-interval events, multiple entry faces and
    # junction coordinates. No fixed offset or manifold-specific layer.
    queues=[];seen=set()
    for b in bases:
        if allow_bypass:queues.append(iter(bypass_alternatives(source,net,b,reserved,definitions,threads,modifiers,tools,cache)))
        queues.append(iter(entry_alternatives(source,net,b,reserved,definitions,threads,modifiers,tools,cache)))
    for base in bases:
        key=base['key'];parts=key.split(':');head=parts[1] if key.startswith('window:') else parts[0]
        if not head.startswith('branch_'):continue
        tokens=head.split('_');point=tuple(float(x) for x in tokens[2:])
        for axis in range(3):
            def moves(axis=axis,base=base,key=key,head=head,tokens=tokens,point=point,parts=parts):
                coordinates=[point[axis],*space.values(axis,point[axis],point[axis])]
                orders=[parts[-2],*(''.join(p) for p in itertools.permutations('xyz') if net.preferred_axis=='auto' or p[0]==net.preferred_axis)]
                modes=list(itertools.product(('nearest','negative','positive'),dict.fromkeys(orders)))
                # Diagonal scheduling exposes the next machining layer before
                # all eighteen duplicate order/entry modes of one layer.
                for diagonal in range(len(coordinates)+len(modes)-1):
                    for ci in range(max(0,diagonal-len(modes)+1),min(len(coordinates),diagonal+1)):
                        coordinate=coordinates[ci];entry,order=modes[diagonal-ci]
                        fields=tokens.copy();fields[axis+2]=f'{coordinate:.6f}'
                        variant=key.replace(head,'_'.join(fields),1).rsplit(':',2)[0]+':'+order+':'+entry
                        if variant in seen:continue
                        seen.add(variant)
                        route=route_from_variant(context,net,variant,definitions,threads,modifiers,obstruction_cache=cache)
                        if route:yield dict(key=variant,route=route,risk=0,connection_verified=False)
                        else:yield dict(checkpoint='EMPTY_VARIANT',net=net.id,variant=variant)
            queues.append(iter(moves()))
    produced=set();excluded=excluded if excluded is not None else set()
    while queues:
        active=[]
        for queue in queues:
            try:
                option=next(queue);active.append(queue)
                if 'checkpoint' in option:yield option;continue
                token=geometry_key(option['route'])
                if token in excluded or token in produced:
                    yield dict(checkpoint='DUPLICATE_GEOMETRY',net=net.id)
                    continue
                produced.add(token);yield option
            except StopIteration:pass
        queues=active


def coordinate(session,source,nets,pools,pair,seed,work,*,labels=0,fragments=True,limits=None):
    """Preserve a compatible core; repair missing Nets, then their blockers."""
    if session.local_admission:session.local_admission.bind(source,nets,session.catalogs)
    overall=work['limit'];work['limit']=min(overall,work['states']+max(32,overall//3))
    best,events,conflicts=improve(source,nets,pools,pair,seed,work,eligible=session.permits_core)
    best=session.admit_core(source,nets,best)
    work['limit']=overall
    start=len(seed);samples=0;generation=[];seen=set();pending=deque();core_states={fingerprint(best):best}
    for core in getattr(session,'validated_cores',[]):
        if not session.permits_core(core):continue
        if len(core)>=len(best)-1 and len(core_states)<max(4,len(nets)):core_states.setdefault(fingerprint(core),core)
    advanced=bool(fragments and (labels or len(seed)>=max(1,len(nets)-2)))
    jobs_seen=set();frontiers=session.corridor_frontiers
    if fragments:
        pending.extend(frontiers.pop(session.context,()))
        jobs_seen.update((name,fingerprint(outside),fingerprint(core)) for name,outside,_,core in pending)
    if len(best)>start:events.append(dict(action='EXTEND_FROM_EXISTING_POOLS',before=start,after=len(best),nets=sorted(best)))
    def jobs(core):
        for name in sorted(set(nets)-set(core),key=lambda n:(len(pools.get(n,[])),n)):
            candidates=sorted(pools.get(name,[]),key=lambda o:(sum(bool(pair(name,o,n,p)) for n,p in core.items()),o['key']))
            blockers=set()
            for o in candidates[:3]:
                blockers.update(n for n,p in core.items() if pair(name,o,n,p))
            # Missing Net alone first, then each actual blocker against all
            # other reservations. Joint pool search may replace both together.
            for released in [{name},*[{name,b} for b in sorted(blockers)],{name,*blockers}]:
                token=(tuple(sorted(released)),fingerprint(core))
                if token in seen:continue
                seen.add(token)
                outside={n:p for n,p in core.items() if n not in released}
                for owner in sorted(released,key=lambda n:n!=name):
                    job=(owner,fingerprint(outside),fingerprint(core))
                    if job in jobs_seen:continue
                    jobs_seen.add(job)
                    catalog=session.catalogs[owner]
                    bases=([core[owner]] if owner in core else [])+sorted(catalog.clear,key=lambda o:(
                        sum(bool(pair(owner,o,n,p)) for n,p in outside.items()),o['key']))[:3]
                    reserved=[f for o in outside.values() for f in o['route']]
                    yield owner,outside,iter(corridor_alternatives(source,nets[owner],bases,reserved,
                        catalog.definitions,catalog.threads,catalog.modifiers,catalog.tools,session.cache,
                        excluded=catalog.seen,allow_bypass=advanced)),core
    # Replay useful equal-coverage assignments directly from existing pools.
    # Do not require their already-known physical route to be generated again
    # before scheduling the displaced Net against its replacement.
    alternatives=[]
    for name in sorted(set(nets)-set(best)):
        for option in pools.get(name,[]):
            blockers={n for n,p in best.items() if pair(name,option,n,p)}
            core={n:p for n,p in best.items() if n not in blockers};core[name]=option
            if not session.permits_core(core):continue
            if len(core)>=len(best)-1 and len(source.features)+sum(len(o['route']) for o in core.values())<=120:
                alternatives.append((-len(core),len(blockers),name,option['key'],core,blockers))
    for _,_,name,_,core,blockers in sorted(alternatives,key=lambda r:r[:4]):
        token=fingerprint(core)
        if token in core_states or len(core_states)>=max(4,len(nets)):continue
        core_states[token]=core;session.seed_combination(source,core)
        events.append(dict(action='REPLAY_ALTERNATIVE_CORE',inserted=name,released=sorted(blockers),compatible_nets=sorted(core)))
    if fragments:
        for core in sorted(core_states.values(),key=lambda c:-len(c)):pending.extend(jobs(core))
    sample_limit=limits['samples'] if limits else session.remaining
    if limits:session.remaining=max(session.remaining,sample_limit)
    probes=0;duplicates=0;checkpoints={};probe_limit=limits['probes'] if limits else max(1,session.remaining)*4
    while pending and session.remaining and samples<sample_limit and work['states']<work['limit'] and len(best)<len(nets) and probes<probe_limit:
        name,outside,iterator,core=pending.popleft()
        try:option=next(iterator)
        except StopIteration:continue
        pending.append((name,outside,iterator,core));catalog=session.catalogs[name]
        probes+=1
        if 'checkpoint' in option:
            reason=option['checkpoint'];checkpoints[reason]=checkpoints.get(reason,0)+1
            continue
        if geometry_key(option['route']) in catalog.seen:duplicates+=1;continue
        before=len(catalog.clear);catalog.accept(option['key'],option['route'],'joint-corridor')
        session.remaining-=1;samples+=1
        if len(catalog.clear)==before:continue
        option=catalog.clear[-1]
        blocked={n:sorted(pair(name,option,n,p)) for n,p in outside.items() if pair(name,option,n,p)}
        generation.append(dict(net=name,key=option['key'],reserved_nets=sorted(outside),blockers=blocked))
        # A pair-local improvement that hits a third Net never enters the
        # preserved core. It may only be used after that Net is also released.
        pools[name]=catalog.active(width=len(catalog.clear))
        # Keep a genuinely compatible alternative CORE even when coverage is
        # unchanged: insert the missing Net, release its exact blockers, then
        # replan those blockers against the newly inserted complete machining.
        # Previously both sides were regenerated independently against the old
        # outside set, so the replacement never saw its new partner's cuts.
        actual_blockers={n for n,p in core.items() if n!=name and pair(name,option,n,p)}
        provisional={n:p for n,p in core.items() if n not in actual_blockers and n!=name}
        provisional[name]=option;token=fingerprint(provisional)
        valid=len(source.features)+sum(len(o['route']) for o in provisional.values())<=120 and session.permits_core(provisional)
        if valid and len(provisional)>=len(best)-1 and token not in core_states and len(core_states)<max(4,len(nets)):
            core_states[token]=provisional
            events.append(dict(action='RETAIN_ALTERNATIVE_CORE',inserted=name,released=sorted(actual_blockers),
                               compatible_nets=sorted(provisional),status='ANALYTIC_NOT_EXACT'))
            session.seed_combination(source,provisional)
            pending.extendleft(reversed(list(jobs(provisional))))
        # Source-clear alternatives for BOTH released Nets must accumulate
        # before another local CSP. Do not spend all states on every sample.
        if samples%4 and blocked:continue
        work['limit']=min(overall,work['states']+32)
        trial,moves,failed=improve(source,nets,pools,pair,provisional if valid and len(provisional)>=len(best) else best,work,
                                 eligible=session.permits_core)
        work['limit']=overall
        events.extend(moves);conflicts.extend(failed)
        trial=session.admit_core(source,nets,trial)
        if len(trial)>len(best):
            events.append(dict(action='EXTEND_COMPATIBLE_CORE',before=len(best),after=len(trial),nets=sorted(trial)))
            best=trial;pending.extend(jobs(best))
        if labels and work['states']>=overall*3//4:break
    searches=[];used_labels=0
    if labels and len(best)<len(nets) and work['states']<overall:
        from ..drilling_planner import plan_net
        missing=sorted(set(nets)-set(best));releases=[]
        for name in missing:
            releases.append((name,{name}))
            obstruction_sets=[]
            for option in pools.get(name,[]):
                blockers={n for n,p in best.items() if pair(name,option,n,p)}
                if blockers:obstruction_sets.append(blockers)
            for blockers in sorted(obstruction_sets,key=lambda s:(len(s),sorted(s)))[:2]:
                releases.append((name,{name,*blockers}))
        # Probe each missing Net, then its attributed release group. Retained
        # outside cuts remain full machining obstacles in the shared planner.
        releases.sort(key=lambda row:(len(row[1]),row[0]));unique=set()
        for index,(name,group) in enumerate(releases):
            if used_labels>=labels or len(best)==len(nets) or work['states']>=overall or limits and samples>=sample_limit:break
            if (name,tuple(sorted(group))) in unique:continue
            unique.add((name,tuple(sorted(group))))
            outside={n:o for n,o in best.items() if n not in group}
            reserved=[f for o in outside.values() for f in o['route']];catalog=session.catalogs[name]
            allowance=min(labels-used_labels,max(128,(labels-used_labels)//max(1,len(releases)-index)))
            options,detail=plan_net(source,nets[name],catalog.definitions,catalog.threads,catalog.modifiers,
                reserved=reserved,label_limit=allowance,alternatives=min(2,sample_limit-samples) if limits else 2,cache=session.cache,tools=catalog.tools,
                ai_context=session.search_context)
            used_labels+=detail.get('labels',0)
            searches.append({**detail,'released':sorted(group),'reserved_nets':sorted(outside)})
            for option in options:
                catalog.accept(option['key'],option['route'],'reserved-3d')
                if limits:samples+=1;session.remaining-=1
            pools[name]=catalog.active(width=len(catalog.clear))
            trial,moves,failed=improve(source,nets,pools,pair,best,work,eligible=session.permits_core)
            trial=session.admit_core(source,nets,trial)
            events.extend(moves);conflicts.extend(failed)
            if len(trial)>len(best):
                events.append(dict(action='EXTEND_WITH_RESERVED_3D',before=len(best),after=len(trial),nets=sorted(trial)))
                best=trial
    if pending and len(best)<len(nets):frontiers[session.context]=pending
    while len(frontiers)>max(4,len(nets)):frontiers.pop(next(iter(frontiers)))
    return best,dict(status='ANALYTIC_PARTIAL_NOT_EXACT',initial_compatible=start,best_compatible=len(best),
        generator_checkpoints=checkpoints,raw_probe_limit=probe_limit,
        pending_corridor_examples=[dict(net=n,reserved_nets=sorted(outside),compatible_core=sorted(core)) for n,outside,_,core in list(pending)[:8]],
        states=work['states'],state_limit=work['limit'],samples=samples,duplicate_probes=duplicates,raw_probes=probes,pending_corridor_batches=len(pending),
        events=events,advanced_fragment_search=advanced,
        compatible_cores=[dict(nets=sorted(c),selected={n:o['key'] for n,o in c.items()}) for c in core_states.values()],
        insert_failures=conflicts[:64],generated=generation,labels=used_labels,net_searches=searches,
        missing_nets=sorted(set(nets)-set(best)),source_positions_unchanged=True)
