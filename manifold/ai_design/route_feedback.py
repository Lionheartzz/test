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


def measured_actions(design,assessment,definitions,domain,threads,modifiers):
    from .design_space import signature,source_conflicts
    nets={n.id:n for n in design.nets};by_id={f.id:f for f in design.features};seen=set()
    def emit(target,reason):
        if target is None:return None
        key=signature(target)
        if key in seen or not domain.accepts(design,target):return None
        seen.add(key)
        # This is a cheap SOURCE check, never route or engineering approval.
        if source_conflicts(target,definitions,threads,modifiers,domain._placement_cache):return None
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
    for witness in assessment.get('witnesses',[]):
        bores=[Feature.model_validate(f) for f in witness.get('features',[])]
        for a,b in itertools.combinations(bores,2):
            if a.route_net==b.route_net or a.route_net not in nets or b.route_net not in nets:continue
            oa={m.split(':')[0] for m in nets[a.route_net].members};ob={m.split(':')[0] for m in nets[b.route_net].members}
            ab=[_box(design,c) for c in _manufacturing_cuts(a,definitions,threads,modifiers)]
            bb=[_box(design,c) for c in _manufacturing_cuts(b,definitions,threads,modifiers)]
            wall=required_wall(design,a,b,definitions=definitions)+.01
            emitted_owners=set()
            for ra,rb in itertools.product(ab,bb):
                for axis in range(3):
                    for delta in (rb[axis][0]-wall-ra[axis][1],rb[axis][1]+wall-ra[axis][0]):
                        group=(oa-ob)&domain.movable
                        result=emit(_translated(design,group,axis,delta,domain,definitions),
                            dict(nets=[a.route_net,b.route_net],rule='cross_net_wall',drillings=[a.id,b.id],
                                 owners=sorted(group),axis=axis,delta_mm=delta,measured_clearance_mm=wall,requires_route_regeneration=True))
                        if result:yield result
                # Both circuits may use the SAME components. An exclusive-Net
                # translation then has an empty owner set; ignoring that case
                # made coupled multi-port valves immovable in old feedback.
                # Move/reorient a supporting source, preserving all its actual
                # window offsets and other Net assignments.
                for axis in set(range(3))-{FACE_AXES[a.face][2],FACE_AXES[b.face][2]}:
                    gap=(a.diameter+b.diameter)/2+wall
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
                            for delta in (-gap,gap):
                                result=emit(_translated(context,{owner},axis,delta,domain,definitions),
                                    dict(nets=[a.route_net,b.route_net],rule='cross_net_wall',drillings=[a.id,b.id],
                                         owners=[owner],axis=axis,delta_mm=delta,from_face=feature.face,to_face=face,
                                         shared_interface=owner in oa&ob,requires_route_regeneration=True))
                                if result:yield result
