"""Measured machining-conflict proposals for explicitly AI-owned geometry.

Bounds choose displacements, never authorize contact or modify source profiles.
Every yielded layout is re-screened and still requires Exact acceptance.
"""
import itertools

from ..kinematics import FACE_AXES, dimensions, pose
from ..engineering_conditions import required_wall
from ..schema import Feature


def _box(design,cut):
    from ..routing import cylinder_bounds
    return cylinder_bounds(cut['feature'],design.block,cut['start'],cut['end'],2*max(cut['radius_start'],cut['radius_end']))


def _installed(feature,definitions):
    definition=definitions.get(feature.definition)
    return dict(feature=feature,start=-(definition.clearance_height if definition else feature.clearance_height),end=0,
        radius_start=(definition.clearance_diameter if definition else feature.clearance_diameter)/2,
        radius_end=(definition.clearance_diameter if definition else feature.clearance_diameter)/2)


def obstruction_witnesses(design,nets,diagnostics,definitions,threads,modifiers):
    from ..routing import _manufacturing_cuts,_protected_source_cuts
    sources={f.id:f for f in design.features};result=[];seen=set()
    for name,detail in diagnostics.items():
        for sample in detail.get('rejected_samples',[]):
            bores={}
            for f in sample.get('features',[]):
                try:bores[f['id']]=Feature.model_validate(f)
                except ValueError:continue  # Already explicitly rejected invalid machining.
            for failure in sample['failures']:
                if len(failure)!=3 or failure[0] not in ('source_protected','source_wall','installation_access','plug_cut'):continue
                source=next((sources[k] for k in failure[1:] if k in sources),None)
                bore=next((bores[k] for k in failure[1:] if k in bores),None)
                if source is None or bore is None:continue
                if failure[0]=='installation_access':
                    cuts=[_installed(source,definitions)];route_cuts=[_installed(bore,definitions)]
                    clearance=design.rules.minimum_access_gap
                else:
                    cuts=[c for c,_ in _protected_source_cuts(source,nets[name],definitions,threads,modifiers)] if failure[0].startswith('source_') else list(_manufacturing_cuts(source,definitions,threads,modifiers))
                    route_cuts=list(_manufacturing_cuts(bore,definitions,threads,modifiers))
                    if failure[0]=='plug_cut':
                        from ..closure_runtime import plug_diameter
                        route_cuts=[dict(feature=bore,start=0,end=bore.plug_length,
                            radius_start=plug_diameter(bore)/2,radius_end=plug_diameter(bore)/2)]
                    clearance=0 if failure[0] in ('source_protected','plug_cut') else required_wall(design,bore,source,definitions=definitions)
                for a,b in itertools.product(route_cuts,cuts):
                    rb,sb=_box(design,a),_box(design,b)
                    if any(min(x[1],y[1])+clearance<max(x[0],y[0]) for x,y in zip(rb,sb)):continue
                    key=(name,source.id,bore.face,tuple(map(tuple,rb)),failure[0],tuple(map(tuple,sb)))
                    if key in seen:continue
                    seen.add(key)
                    result.append(dict(net=name,variant=sample['variant'],rule=failure[0],source=source.id,
                        drilling=bore.model_dump(mode='json'),route_bounds=rb,source_bounds=sb,clearance=clearance,
                        contact_location=[(max(x[0],y[0])+min(x[1],y[1]))/2 for x,y in zip(rb,sb)]))
    return result


def _translated(design,group,axis,delta,domain,definitions):
    """Translate only permitted face coordinates; grow measured needed axes."""
    from .design_space import radius
    target=design.model_copy(deep=True);moved=[]
    for f in target.features:
        if f.id not in group:continue
        u,v,normal,_=FACE_AXES[f.face]
        if axis==normal:return None
        field='u' if axis==u else 'v'
        if field in domain.fixed_positions.get(f.id,{}) or ('x','y','z')[axis] in domain.fixed_positions.get(f.id,{}):return None
        setattr(f,field,getattr(f,field)+delta);moved.append(f)
    if not moved:return None
    for f in moved:
        margin=radius(f,definitions)+required_wall(target,f,definitions=definitions)
        u,v,_,_=FACE_AXES[f.face]
        for coordinate,a in ((f.u,u),(f.v,v)):
            if coordinate<margin:return None
            need=coordinate+margin
            if need>dimensions(target.block)[a]:
                if a not in domain.dimension_axes or need>(target.constraints.envelope_max or (2000,)*3)[a]:return None
                setattr(target.block,('length','width','height')[a],need)
    return target


def exact_witnesses(design,failures,definitions,threads,modifiers):
    """Keep Exact attribution, not a guessed topology diagnosis or CAD repair."""
    nets={n.id:n for n in design.nets};sources={f.id:f for f in design.features if not f.route_net}
    constraints=[];diagnostics={}
    for failure in failures:
        rule=failure.get('rule') if isinstance(failure,dict) else failure[0]
        items=failure.get('items',[]) if isinstance(failure,dict) else failure[1:]
        ids={str(v).split(':')[0] for v in items}
        cuts=[f for f in design.features if f.route_net and (f.id in ids or f.route_net in ids)]
        for a,b in itertools.combinations(cuts,2):
            if a.route_net!=b.route_net:
                constraints.append(dict(nets=[a.route_net,b.route_net],failures=[failure],
                    features=[a.model_dump(mode='json'),b.model_dump(mode='json')],
                    evidence='EXACT_REJECTION',rule=rule,exact_verified=False))
        for bore in cuts:
            for key in ids&sources.keys():
                # Only recognized source-machining rules supply protected-cut
                # witnesses. Other engineering failures remain explicit review.
                mapping={'cavity_protected_region':'source_protected','cavity_wall':'source_wall',
                         'source_wall':'source_wall','source_protected':'source_protected'}
                if rule not in mapping:continue
                diagnostics.setdefault(bore.route_net,dict(rejected_samples=[]))['rejected_samples'].append(
                    dict(variant='exact-rejected',features=[bore.model_dump(mode='json')],
                         failures=[(mapping[rule],key,bore.id)]))
    return constraints,obstruction_witnesses(design,nets,diagnostics,definitions,threads,modifiers)


def _joint_translation(design,group,opponents,axis,delta,domain,definitions,threads,modifiers):
    """Expand a motion cluster by actual source collisions, with finite closure.

    If moving a group hits another movable installation, move it jointly. A
    fixed source or an opposing terminal stops this action, never relaxes it.
    """
    from .design_space import source_conflicts
    group=set(group)
    while group:
        target=_translated(design,group,axis,delta,domain,definitions)
        if target is None or not domain.accepts(design,target):return None,group
        clashes=source_conflicts(target,definitions,threads,modifiers,domain._placement_cache)
        if not clashes:return target,group
        additions={owner for pair in clashes if set(pair)&group for owner in pair}-group
        if not additions or additions&set(opponents) or not additions<=domain.movable:return None,group
        group.update(additions)
    return None,group


def _dilated(design,axis,split,amount,domain):
    """Insert measured stock space and move the sources on its far side.

    Opposite-face sources follow their boundary. Unowned/fixed coordinates are
    checked by LayoutDomain, so this cannot stretch a saved Model design.
    """
    if axis not in domain.dimension_axes:return None
    target=design.model_copy(deep=True)
    value=dimensions(design.block)[axis]+amount
    if value>(design.constraints.envelope_max or (2000,)*3)[axis]:return None
    setattr(target.block,('length','width','height')[axis],value)
    for old,f in zip(design.features,target.features):
        u,v,normal,_=FACE_AXES[f.face]
        if axis!=normal and pose(old,design.block)[0][axis]>split:
            if f.id not in domain.movable:return None
            field='u' if u==axis else 'v'
            setattr(f,field,getattr(f,field)+amount)
    return target if domain.accepts(design,target) else None


def _measured_actions(design,assessment,definitions,domain,threads,modifiers):
    from .design_space import signature,source_conflicts,fit_violations
    nets={n.id:n for n in design.nets};by_id={f.id:f for f in design.features};seen=set()
    def emit(target,reason):
        if target is None:return None
        key=signature(target)
        if key in seen or not domain.accepts(design,target):return None
        seen.add(key)
        # This is a cheap SOURCE check, never route or engineering approval.
        if fit_violations(target,definitions,domain) or source_conflicts(target,definitions,threads,modifiers,domain._placement_cache):return None
        return 'feedback-machining-separation',target,reason
    # The best rejected strategy's full cuts locate the specific blocked entry,
    # source seat or plug. Separate one measured boundary instead of a blind pitch.
    for witness in assessment.get('spatial_feedback',[]):
        source=by_id[witness['source']];net=nets[witness['net']]
        owners={m.split(':')[0] for m in net.members};sb,rb=witness['source_bounds'],witness['route_bounds']
        margin=witness['clearance']+.01
        axes=FACE_AXES[source.face][:2]
        displacements=sorted((abs(delta),axis,delta) for axis in axes for delta in (
            rb[axis][0]-margin-sb[axis][1],rb[axis][1]+margin-sb[axis][0]))
        for _,axis,delta in displacements:
            # Moving a terminal also changes its regenerated route. Try source
            # motion AND the complementary related group; neither clears it.
            group={source.id}&domain.movable
            result=emit(_translated(design,group,axis,delta,domain,definitions),
                dict(net=net.id,rule=witness['rule'],source=source.id,drilling=witness['drilling']['id'],
                     contact_location=witness['contact_location'],axis=axis,delta_mm=delta,owners=sorted(group),
                     measured_clearance_mm=margin,requires_route_regeneration=True))
            if result:yield result
            # Moving another network's fixed-space obstacle may be prohibited;
            # translating the affected terminals is the complementary action.
            other_owners=(owners-{source.id})&domain.movable
            if other_owners:
                result=emit(_translated(design,other_owners,axis,-delta,domain,definitions),
                    dict(net=net.id,rule=witness['rule'],source=source.id,axis=axis,delta_mm=-delta,
                         owners=sorted(other_owners),measured_clearance_mm=margin,requires_route_regeneration=True))
                if result:yield result
    # Cross-Net cut witnesses provide a separating plane for the exclusive
    # terminal group. Shared owners cannot be assigned contradictory motions.
    from ..routing import _manufacturing_cuts
    witnesses=assessment.get('coordination_constraints',assessment.get('witnesses',[]))
    for witness in witnesses:
        bores=[Feature.model_validate(f) for f in witness.get('features',[])]
        for a,b in itertools.combinations(bores,2):
            if a.route_net==b.route_net or a.route_net not in nets or b.route_net not in nets:continue
            oa={m.split(':')[0] for m in nets[a.route_net].members};ob={m.split(':')[0] for m in nets[b.route_net].members}
            ab=[_box(design,c) for c in _manufacturing_cuts(a,definitions,threads,modifiers)]
            bb=[_box(design,c) for c in _manufacturing_cuts(b,definitions,threads,modifiers)]
            wall=required_wall(design,a,b,definitions=definitions)+.01
            emitted_owners=set()
            for ra,rb in itertools.product(ab,bb):
                if any(min(x[1],y[1])+wall<max(x[0],y[0]) for x,y in zip(ra,rb)):continue
                contact=[(max(x[0],y[0])+min(x[1],y[1]))/2 for x,y in zip(ra,rb)]
                for axis in range(3):
                    for group,opponents,own,other in ((oa-ob,ob,ra,rb),(ob-oa,oa,rb,ra)):
                        # Do not translate only the unlocked half of a Net and
                        # pretend that its entire machining corridor moved.
                        if not group or not group<=domain.movable:continue
                        for delta in (other[axis][0]-wall-own[axis][1],other[axis][1]+wall-own[axis][0]):
                            target,moving=_joint_translation(design,group,opponents,axis,delta,domain,definitions,threads,modifiers)
                            result=emit(target,dict(nets=[a.route_net,b.route_net],rule='cross_net_wall',drillings=[a.id,b.id],
                                owners=sorted(moving),axis=axis,delta_mm=delta,contact_location=contact,
                                joint_motion=len(moving)>1,measured_clearance_mm=wall,requires_route_regeneration=True))
                            if result:yield result
                    # A measured separating interval can require more stock,
                    # and movement of several sources on both circuits. Insert
                    # that space at actual source events, not a fixed lane pitch.
                    points=sorted({pose(by_id[o],design.block)[0][axis] for o in oa|ob if o in by_id})
                    amount=min(abs(rb[axis][0]-wall-ra[axis][1]),abs(rb[axis][1]+wall-ra[axis][0]))
                    for x,y in zip(points,points[1:]):
                        target=_dilated(design,axis,(x+y)/2,amount,domain)
                        result=emit(target,dict(nets=[a.route_net,b.route_net],rule='machining_corridor_space',
                            drillings=[a.id,b.id],axis=axis,inserted_space_mm=amount,split=(x+y)/2,
                            contact_location=contact,requires_route_regeneration=True))
                        if result:yield result
                # Both circuits may use the SAME components. An exclusive-Net
                # translation then has an empty owner set; ignoring that case
                # made coupled multi-port valves immovable in old feedback.
                # Move/reorient a supporting source, preserving all its actual
                # window offsets and other Net assignments.
                for axis in set(range(3))-{FACE_AXES[a.face][2],FACE_AXES[b.face][2]}:
                    # Use the actual intersecting complete-cut boundaries,
                    # including entry/plug cuts, rather than nominal bore pitch.
                    deltas=(rb[axis][0]-wall-ra[axis][1],rb[axis][1]+wall-ra[axis][0])
                    for owner in sorted((oa|ob)&domain.movable):
                        if (owner,axis) in emitted_owners:continue
                        emitted_owners.add((owner,axis));feature=by_id[owner]
                        for face in domain.faces(feature):
                            if axis not in FACE_AXES[face][:2]:continue
                            from .design_space import projected,radius
                            probe=projected(feature,face,design)
                            u,v,_,_=FACE_AXES[face];sizes=dimensions(design.block)
                            margin=radius(probe,definitions)+required_wall(design,probe,definitions=definitions)
                            probe.u=max(margin,min(sizes[u]-margin,probe.u));probe.v=max(margin,min(sizes[v]-margin,probe.v))
                            context=design.model_copy(update=dict(features=[probe if f.id==owner else f for f in design.features]))
                            for delta in deltas:
                                result=emit(_translated(context,{owner},axis,delta,domain,definitions),
                                    dict(nets=[a.route_net,b.route_net],rule='cross_net_wall',drillings=[a.id,b.id],
                                         owners=[owner],axis=axis,delta_mm=delta,from_face=feature.face,to_face=face,
                                         shared_interface=owner in oa&ob,requires_route_regeneration=True))
                                if result:yield result
                            # Reorient asymmetric source windows, then align the
                            # actual window centres with their other terminals.
                            from .design_space import anchored
                            for trial in itertools.islice(anchored(design,feature,definitions,domain,threads,modifiers),len(FACE_AXES)*4):
                                if trial.face==feature.face and trial.rotation==feature.rotation:continue
                                target=design.model_copy(update=dict(features=[trial if f.id==owner else f for f in design.features]))
                                result=emit(target,dict(nets=[a.route_net,b.route_net],rule='window_orientation',owners=[owner],
                                    drillings=[a.id,b.id],from_face=feature.face,to_face=trial.face,
                                    rotation=trial.rotation,requires_route_regeneration=True))
                                if result:yield result


def _combined_actions(design,witnesses,definitions,domain,threads,modifiers):
    """Intersect signed separating constraints for an entire moving group."""
    from ..routing import _manufacturing_cuts
    from .design_space import source_conflicts,fit_violations
    nets={n.id:n for n in design.nets};moves={}
    for witness in witnesses:
        bores=[Feature.model_validate(f) for f in witness.get('features',[])]
        for a,b in itertools.combinations(bores,2):
            if a.route_net==b.route_net or a.route_net not in nets or b.route_net not in nets:continue
            oa={m.split(':')[0] for m in nets[a.route_net].members};ob={m.split(':')[0] for m in nets[b.route_net].members}
            wall=required_wall(design,a,b,definitions=definitions)+.01
            for ca,cb in itertools.product(_manufacturing_cuts(a,definitions,threads,modifiers),_manufacturing_cuts(b,definitions,threads,modifiers)):
                ra,rb=_box(design,ca),_box(design,cb)
                if any(min(x[1],y[1])+wall<max(x[0],y[0]) for x,y in zip(ra,rb)):continue
                for owners,opponents,own,other in ((oa-ob,ob,ra,rb),(ob-oa,oa,rb,ra)):
                    if not owners or not owners<=domain.movable:continue
                    for axis in range(3):
                        for delta in (other[axis][0]-wall-own[axis][1],other[axis][1]+wall-own[axis][0]):
                            key=(tuple(sorted(owners)),axis,delta>0)
                            state=moves.setdefault(key,dict(delta=delta,opponents=set(),pairs=set(),nets=set()))
                            if abs(delta)>abs(state['delta']):state['delta']=delta
                            state['opponents'].update(opponents);state['pairs'].add((a.id,b.id));state['nets'].update(witness['nets'])
    for (owners,axis,_),state in sorted(moves.items(),key=lambda r:(-len(r[1]['pairs']),abs(r[1]['delta']))):
        target,moving=_joint_translation(design,owners,state['opponents'],axis,state['delta'],domain,definitions,threads,modifiers)
        if target is None or fit_violations(target,definitions,domain) or source_conflicts(target,definitions,threads,modifiers,domain._placement_cache):continue
        yield 'feedback-machining-separation',target,dict(nets=sorted(state['nets']),rule='combined_machining_constraints',
            owners=sorted(moving),axis=axis,delta_mm=state['delta'],drilling_pairs=sorted(state['pairs']),
            joint_motion=len(moving)>1,requires_route_regeneration=True)


def measured_actions(design,assessment,definitions,domain,threads,modifiers):
    """Interleave actual constraint families; one witness cannot starve others."""
    from .design_space import signature
    witnesses=assessment.get('coordination_constraints',assessment.get('witnesses',[]))
    queues=[iter(_combined_actions(design,witnesses,definitions,domain,threads,modifiers))]
    queues.append(iter(_measured_actions(design,dict(spatial_feedback=assessment.get('spatial_feedback',[])),definitions,domain,threads,modifiers)))
    queues.extend(iter(_measured_actions(design,dict(coordination_constraints=[w]),definitions,domain,threads,modifiers)) for w in witnesses)
    seen={signature(design)}
    while queues:
        active=[]
        for queue in queues:
            try:action=next(queue);active.append(queue)
            except StopIteration:continue
            key=signature(action[1])
            if key not in seen:seen.add(key);yield action
        queues=active
