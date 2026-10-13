"""Joint source-interface pose search, exclusively for new AI candidates.

Window alignment schedules hypotheses; full source cuts and the shared Router
still reject them. A shared source is one rigid feature, never one copy per Net.
"""
from collections import defaultdict
import itertools

from ..kinematics import FACE_AXES,pose,dimensions
from ..engineering_conditions import required_wall
from ..routing import terminal_points
from .design_space import anchored,signature,radius,source_conflicts,fit_violations


def interfaces(design,definitions):
    points=terminal_points(design,definitions);result=[]
    for f in design.features:
        if f.suppressed or f.kind not in ('cavity','port'):continue
        origin,normal=pose(f,design.block);axis=FACE_AXES[f.face][2]
        zones=definitions[f.definition].zones if f.definition else [None]
        for z in zones:
            key=f.id+':'+z.id if f.kind=='cavity' else f.id
            if key not in points:continue
            # A staged cylindrical window offers radial orthogonal approaches;
            # a face-open window also offers its source axis. These are proposed
            # directions only; protected machining decides each actual entry.
            axes=range(3) if z is None or z.start==0 else [i for i in range(3) if i!=axis]
            directions=[tuple(sign if i==a else 0 for i in range(3)) for a in axes for sign in (-1,1)]
            result.append(dict(terminal=key,feature=f.id,net=f.circuits.get(z.id) if f.kind=='cavity' else f.circuit,
                center=points[key],source_normal=normal,approach_normals=directions,
                diameter=z.diameter if z else f.diameter,depth_interval=[z.start,z.end] if z else [0,f.depth]))
    return result


def coupling_groups(design,assessment):
    owners={n.id:{m.split(':')[0] for m in n.members} for n in design.nets}
    implicated=set(assessment.get('unresolved_nets',[]))
    implicated.update(n for w in assessment.get('coordination_constraints',[]) for n in w['nets'])
    implicated.update(w['net'] for w in assessment.get('spatial_feedback',[]))
    groups={}
    for a,b in itertools.combinations(owners,2):
        shared=owners[a]&owners[b]
        if not shared or not ({a,b}&implicated):continue
        if len(shared)>=2:
            groups.setdefault(tuple(sorted(shared)),set()).update((a,b))
        else:
            # One shared source can require moving a supporting source too.
            # Keep each incident pair as an alternative, not the whole model.
            for other in (owners[a]|owners[b])-shared:
                groups.setdefault(tuple(sorted(shared|{other})),set()).update((a,b))
    return sorted(groups.items(),key=lambda row:(-len(row[0]),-len(row[1]&implicated),row[0]))


def _targets(design,frames,group,nets,assessment,definitions,threads,modifiers):
    anchors={}
    for net in design.nets:
        own=[f for f in frames if f['net']==net.id]
        outside=[f for f in own if f['feature'] not in group]
        used=outside or own
        if used:anchors[net.id]=tuple(sum(f['center'][i] for f in used)/len(used) for i in range(3))
    # Complete machining envelopes, not an arbitrary placement pitch, set the
    # channel spacing. This does not prescribe or authorize a drilling path.
    from ..routing import _manufacturing_cuts
    gap=max((n.diameter for n in design.nets if n.id in nets),default=0)+required_wall(design,definitions=definitions)
    for w in assessment.get('coordination_constraints',[]):
        if not set(w['nets'])&nets:continue
        from ..schema import Feature
        for raw in w.get('features',[]):
            bore=Feature.model_validate(raw)
            gap=max(gap,2*max((max(c['radius_start'],c['radius_end']) for c in
                _manufacturing_cuts(bore,definitions,threads,modifiers)),default=bore.diameter/2)+required_wall(design,bore,definitions=definitions))
    yield dict(anchors),dict(kind='existing_window_centroids',gap_mm=gap)
    for axis in range(3):
        ordered=sorted((n for n in nets if n in anchors),key=lambda n:(anchors[n][axis],n))
        if len(ordered)<2:continue
        center=sum(anchors[n][axis] for n in ordered)/len(ordered)
        for order in (ordered,list(reversed(ordered))):
            target=dict(anchors)
            for index,name in enumerate(order):
                point=list(anchors[name]);point[axis]=center+(index-(len(order)-1)/2)*gap;target[name]=tuple(point)
            yield target,dict(kind='window_channel_order',axis=axis,net_order=order,gap_mm=gap)


def _error(design,definitions,targets,group):
    frames=interfaces(design,definitions)
    total=0
    for f in frames:
        if f['feature'] not in group or f['net'] not in targets:continue
        delta=[abs(f['center'][i]-targets[f['net']][i]) for i in range(3)]
        # Moving a rigid source changes both window centers and available
        # approach axes. Prefer alignment on an actual radial/face-open axis;
        # this is a search cost, never a substitute for machining acceptance.
        approach=min(sum(d for d,n in zip(delta,normal) if not n) for normal in f['approach_normals'])
        total+=sum(delta)+approach
    return total


def _enclose(original,target,domain,definitions,threads,modifiers):
    from .initialization import source_extents
    sizes=list(dimensions(target.block));lower=target.constraints.envelope_min or (1,)*3
    upper=target.constraints.envelope_max or (2000,)*3
    for f in target.features:
        fact=source_extents(target,f,definitions,threads,modifiers);u,v,normal,_=FACE_AXES[f.face]
        margin=fact['radius']+fact['wall']
        if min(f.u,f.v)<margin:return None
        for coordinate,axis in ((f.u,u),(f.v,v),(fact['depth'],normal)):
            need=coordinate+(fact['wall'] if axis==normal else margin)
            if need>sizes[axis] and axis not in domain.dimension_axes:return None
            sizes[axis]=max(sizes[axis],need,lower[axis])
    if any(s>hi for s,hi in zip(sizes,upper)):return None
    for name,size in zip(('length','width','height'),sizes):setattr(target.block,name,size)
    return target


def _preserved_routes(design,target,assessment,definitions,threads,modifiers):
    """Rescreen only world-unchanged dependencies, never retain an approval."""
    from ..schema import Feature
    from ..routing import route_obstructions
    from .route_catalog import terminal_key,cut_locations
    from ..engineering_conditions import effective_net
    routes=defaultdict(list)
    for raw in assessment.get('partial_routing',{}).get('features',[]):
        f=Feature.model_validate(raw);routes[f.route_net].append(f)
    clear=[];lost=[];changed=[];cache={}
    for net in design.nets:
        if net.id not in routes:continue
        current=next(n for n in target.nets if n.id==net.id);route=routes[net.id]
        if terminal_key(design,effective_net(design,net))!=terminal_key(target,effective_net(target,current)) or cut_locations(design,route)!=cut_locations(target,route):
            changed.append(net.id);continue
        failures=route_obstructions(target,effective_net(target,current),route,threads,definitions,modifiers,cache)
        (lost if failures else clear).append(net.id)
    return dict(unchanged_source_clear_nets=clear,invalidated_unchanged_routes=lost,changed_terminal_nets=changed)


def _actions(design,assessment,definitions,domain,threads,modifiers,groups):
    """Finite beam of simultaneous source poses over coherent window targets."""
    frames=interfaces(design,definitions);by_id={f.id:f for f in design.features};seen={signature(design)}
    for members,shared_nets in groups:
        group=set(members)
        if len(group&domain.movable)<2:continue
        affected={n.id for n in design.nets if {m.split(':')[0] for m in n.members}&group}
        plans=list(_targets(design,frames,group,shared_nets,assessment,definitions,threads,modifiers))
        remaining=512*len(group);width=min(8,max(2,len(group)*2));used=0
        order=sorted(group,key=lambda k:(k not in domain.movable,-len(by_id[k].circuits),-radius(by_id[k],definitions),by_id[k].schematic_id or k))
        for pi,(targets,plan) in enumerate(plans):
            allowance=remaining//max(1,len(plans)-pi);spent=0
            beam=[(design.model_copy(deep=True),set())]
            for index,owner in enumerate(order):
                expanded=[];quota=max(1,(allowance-spent)//max(1,(len(order)-index)*len(beam)))
                for state,placed in beam:
                    feature=next(f for f in state.features if f.id==owner)
                    context=state.model_copy(update=dict(features=[f for f in state.features if f.id not in group or f.id in placed or f.id==owner]))
                    windows={f['terminal']:targets[f['net']] for f in frames if f['feature']==owner and f['net'] in targets}
                    trials=anchored(context,feature,definitions,domain,threads,modifiers,window_targets=windows) if owner in domain.movable else iter((feature,))
                    for trial in itertools.islice(trials,quota):
                        spent+=1;used+=1
                        target=state.model_copy(deep=True);target.features=[trial if f.id==owner else f for f in target.features]
                        target=_enclose(design,target,domain,definitions,threads,modifiers)
                        if target is None or not domain.accepts(design,target):continue
                        checked=target.model_copy(update=dict(features=[f for f in target.features if f.id not in group or f.id in placed or f.id==owner]))
                        if fit_violations(checked,definitions,domain) or source_conflicts(checked,definitions,threads,modifiers,domain._placement_cache):continue
                        expanded.append((_error(checked,definitions,targets,group),target,placed|{owner}))
                if not expanded:beam=[];break
                expanded.sort(key=lambda row:row[0]);kept=[];structures=set()
                for _,target,placed in expanded:
                    key=tuple((f.id,f.face,f.rotation) for f in target.features if f.id in placed)
                    if key in structures:continue
                    structures.add(key);kept.append((target,placed))
                    if len(kept)>=width:break
                beam=kept
            remaining-=spent
            for target,_ in beam:
                changed=[f.id for f in target.features if f.id in group and (f.face,f.u,f.v,f.rotation)!=(by_id[f.id].face,by_id[f.id].u,by_id[f.id].v,by_id[f.id].rotation)]
                if len(changed)<2 or signature(target) in seen:continue
                if fit_violations(target,definitions,domain) or source_conflicts(target,definitions,threads,modifiers,domain._placement_cache):continue
                seen.add(signature(target));reuse=_preserved_routes(design,target,assessment,definitions,threads,modifiers)
                yield 'feedback-coupled-interfaces',target,dict(rule='joint_source_window_arrangement',owners=sorted(group),
                    changed_features=changed,shared_nets=sorted(shared_nets),affected_nets=sorted(affected),
                    window_plan=plan,window_alignment_error=_error(target,definitions,targets,group),
                    interface_frames_before=[f for f in frames if f['feature'] in group],
                    interface_frames_after=[f for f in interfaces(target,definitions) if f['feature'] in group],
                    source_probes=used,source_probe_limit=512*len(group),**reuse,
                    requires_route_regeneration=True,exact_verified=False)


def actions(design,assessment,definitions,domain,threads,modifiers):
    # Exhausting all poses of one incident pair hides larger rigid-source
    # coupling groups. Each group retains its own count-bounded pose frontier.
    queues=[iter(_actions(design,assessment,definitions,domain,threads,modifiers,[group]))
            for group in coupling_groups(design,assessment)]
    while queues:
        active=[]
        for queue in queues:
            try:action=next(queue);active.append(queue)
            except StopIteration:continue
            yield action
        queues=active
