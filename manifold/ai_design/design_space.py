"""Source-constrained geometry actions owned by ONE new AI generation.

No Model caller, origin flag, saved-project write or hydraulic path algorithm.
"""
from dataclasses import dataclass,field
from collections import defaultdict
import itertools
import math

from ..kinematics import FACE_AXES,dimensions,pose
from ..layout import machining_radius,placement_conflicts
from ..layout_planning import _permissions,_fits
from ..engineering_conditions import required_wall,effective_net


@dataclass
class LayoutDomain:
    movable: set
    dimension_axes: tuple=(0,1,2)
    fixed_faces: dict=field(default_factory=dict)
    fixed_rotations: dict=field(default_factory=dict)
    fixed_positions: dict=field(default_factory=dict)
    soft_faces: dict=field(default_factory=dict)
    soft_dimensions: tuple=()
    hard_dimensions: dict=field(default_factory=dict)
    protected: set=field(default_factory=set)
    _placement_cache: dict=field(default_factory=dict,repr=False)

    @classmethod
    def new_generation(cls,design,owned,*,dimension_axes=(0,1,2),fixed_faces=None,
                       fixed_positions=None,fixed_rotations=None,soft_faces=None,soft_dimensions=()):
        movable,resize=_permissions(design)
        # Passing AI-origin metadata cannot release authored cuts or parents.
        allowed=movable&set(owned)
        resize=resize and movable<=allowed
        positions=dict(fixed_positions or {})
        if set(positions)-{f.id for f in design.features}:raise ValueError('Fixed position refers to a missing feature')
        if any(k not in ('u','v','x','y','z') or not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v)
               for values in positions.values() for k,v in values.items()):raise ValueError('Fixed position requires finite face U/V or global X/Y/Z coordinates')
        faces={**{f.id:f.face for f in design.features if {'u','v'}&positions.get(f.id,{}).keys()},
            **design.constraints.required_feature_faces,**(fixed_faces or {})}
        # Local U/V fixes a mounting-face frame, not the normal stock size.
        # Only an explicit WORLD coordinate on a fixed opposite face implies
        # a fixed normal dimension. Protected/unowned geometry still disables
        # resizing above, independently of any AI-origin metadata.
        axes=tuple(i for i in dimension_axes if resize and not any(f.id in faces and
            FACE_AXES[faces[f.id]][2]==i and FACE_AXES[faces[f.id]][3]<0 and
            ('x','y','z')[i] in positions.get(f.id,{}) for f in design.features) and not (
            design.constraints.envelope_min and design.constraints.envelope_max and
            design.constraints.envelope_min[i]==design.constraints.envelope_max[i]))
        return cls(allowed,axes,faces,
            dict(fixed_rotations or {}),positions,dict(soft_faces or {}),tuple(soft_dimensions),
            dict(minimum=design.constraints.envelope_min,maximum=design.constraints.envelope_max),
            {f.id for f in design.features}-allowed)

    def faces(self,feature):
        return (self.fixed_faces[feature.id],) if feature.id in self.fixed_faces else tuple(FACE_AXES)

    def accepts(self,original,candidate):
        if original.model_dump(exclude={'block','features'})!=candidate.model_dump(exclude={'block','features'}):return False
        if original.block.model_dump(exclude={'length','width','height'})!=candidate.block.model_dump(exclude={'length','width','height'}):return False
        if any(dimensions(original.block)[i]!=dimensions(candidate.block)[i] for i in range(3) if i not in self.dimension_axes):return False
        previous={f.id:f for f in original.features}
        if set(previous)!={f.id for f in candidate.features}:return False
        for f in candidate.features:
            old=previous[f.id]
            if f.id not in self.movable and f!=old:return False
            # Only these four placement parameters are owned by this search.
            if f.model_dump(exclude={'face','u','v','rotation'})!=old.model_dump(exclude={'face','u','v','rotation'}):return False
            if f.id in self.fixed_faces and f.face!=self.fixed_faces[f.id]:return False
            if f.id in self.fixed_rotations and f.rotation!=self.fixed_rotations[f.id]:return False
            if not self.position_matches(f,candidate.block):return False
        return True

    def position_matches(self,feature,block):
        world,_=pose(feature,block)
        return all((getattr(feature,k) if k in ('u','v') else world[('x','y','z').index(k)])==v
                   for k,v in self.fixed_positions.get(feature.id,{}).items())

    def diagnostics(self):
        return dict(scope='NEW_AI_GENERATION_ONLY',movable=sorted(self.movable),dimension_axes=list(self.dimension_axes),
            fixed_faces=self.fixed_faces,fixed_positions=self.fixed_positions,fixed_rotations=self.fixed_rotations,
            soft_faces=self.soft_faces,soft_dimensions=self.soft_dimensions,
            hard_dimensions=self.hard_dimensions,protected_features=sorted(self.protected),
            authority='Explicit generation-owned feature set; never origin.method')


def radius(f,definitions):
    return machining_radius(definitions[f.definition]) if f.definition else max(f.diameter or 0,f.clearance_diameter)/2


def signature(design):
    return (dimensions(design.block),tuple((f.id,f.face,f.u,f.v,f.rotation) for f in design.features))


def topology_cost(design,definitions):
    from ..routing import terminal_points
    points=terminal_points(design,definitions);cost=0
    for net in design.nets:
        members=[points[m] for m in net.members if m in points]
        if len(members)<2:continue
        # Hyperedge spread schedules layout candidates only; it is NOT routing
        # feasibility, an invisible connection, or the final objective.
        cost+=sum(max(p[i] for p in members)-min(p[i] for p in members) for i in range(3))
    return cost


def source_conflicts(design,definitions,threads,modifiers,cache=None):
    return sorted({tuple(sorted((f.id,other))) for f in design.features if not f.suppressed and f.kind in ('cavity','port')
        for other in placement_conflicts(design,f,definitions,threads,modifiers,cache=cache)})


def fit_violations(design,definitions):
    """Actual offending source/envelope facts, not a generic 'no space' label."""
    sizes=dimensions(design.block);violations=[]
    for axis,size in enumerate(sizes):
        if design.constraints.envelope_min and size<design.constraints.envelope_min[axis]:
            violations.append(['explicit_envelope_min',('X','Y','Z')[axis],size,design.constraints.envelope_min[axis]])
        if design.constraints.envelope_max and size>design.constraints.envelope_max[axis]:
            violations.append(['explicit_envelope_max',('X','Y','Z')[axis],size,design.constraints.envelope_max[axis]])
    sources=[f for f in design.features if not f.suppressed and f.kind in ('cavity','port')]
    for f in sources:
        u,v,axis,_=FACE_AXES[f.face];wall=required_wall(design,f,definitions=definitions);margin=radius(f,definitions)+wall
        for coordinate,a in ((f.u,u),(f.v,v)):
            if not margin<=coordinate<=sizes[a]-margin:
                violations.append(['source_face_bounds',f.id,('X','Y','Z')[a],coordinate,margin,sizes[a]-margin])
        depth=max(p.end for p in definitions[f.definition].cutting_primitives or definitions[f.definition].stages) if f.definition else f.depth
        if depth+wall>sizes[axis]:violations.append(['source_depth',f.id,f.face,depth,wall,sizes[axis]])
    for a,b in itertools.combinations(sources,2):
        required=radius(a,definitions)+radius(b,definitions)+max(design.rules.minimum_access_gap,required_wall(design,a,b,definitions=definitions))
        if a.face==b.face and math.dist((a.u,a.v),(b.u,b.v))+1e-6<required:
            violations.append(['source_installation_spacing',a.id,b.id,required])
    return violations


def target_origins(design,feature,definitions):
    """Align actual source-window offsets with the other ends of each Net."""
    from ..routing import terminal_points
    points=terminal_points(design,definitions);origin,_=pose(feature,design.block);targets=[]
    for net in design.nets:
        own=[m for m in net.members if m.split(':')[0]==feature.id and m in points]
        others=[points[m] for m in net.members if m.split(':')[0]!=feature.id and m in points]
        if not own or not others:continue
        centre=tuple(sum(p[i] for p in others)/len(others) for i in range(3))
        for member in own:targets.append(tuple(centre[i]-(points[member][i]-origin[i]) for i in range(3)))
    return targets


def face_events(design,feature,definitions,threads=None,modifiers=None):
    u,v,_,_=FACE_AXES[feature.face];sizes=dimensions(design.block)
    margin=radius(feature,definitions)+required_wall(design,feature,definitions=definitions)
    coordinates=[{margin,sizes[a]-margin,getattr(feature,k)} for a,k in ((u,'u'),(v,'v'))]
    for other in design.features:
        if other.id==feature.id or other.suppressed or other.route_net:continue
        point,_=pose(other,design.block)
        gap=radius(feature,definitions)+radius(other,definitions)+max(
            design.rules.minimum_access_gap,required_wall(design,feature,other,definitions=definitions))+.01
        for values,axis in zip(coordinates,(u,v)):values.update((point[axis]-gap,point[axis]+gap))
        # A cross-face port's depth is a real obstacle boundary. Its entry
        # centre/nominal radius alone cannot locate a safe cavity corridor.
        from ..routing import _manufacturing_cuts,cylinder_bounds
        for cut in _manufacturing_cuts(other,definitions,threads or {},modifiers or {}):
            bounds=cylinder_bounds(cut['feature'],design.block,cut['start'],cut['end'],2*max(cut['radius_start'],cut['radius_end']))
            clearance=radius(feature,definitions)+required_wall(design,feature,other,definitions=definitions)+.01
            for values,axis in zip(coordinates,(u,v)):values.update((bounds[axis][0]-clearance,bounds[axis][1]+clearance))
    for point in target_origins(design,feature,definitions):
        for values,axis in zip(coordinates,(u,v)):values.add(point[axis])
    result=[]
    for values,axis in zip(coordinates,(u,v)):
        values=sorted(x for x in values if margin<=x<=sizes[axis]-margin)
        result.append(list(dict.fromkeys([*values,*[(a+b)/2 for a,b in zip(values,values[1:])]])))
    return result


def projected(feature,face,design):
    origin,_=pose(feature,design.block);u,v,_,_=FACE_AXES[face]
    return feature.model_copy(update=dict(face=face,u=origin[u],v=origin[v]))


def anchored(design,feature,definitions,domain,threads,modifiers):
    """Lazy source-event positions on every permitted face, no regular grid."""
    targets=target_origins(design,feature,definitions)
    queues=[]
    for face in sorted(domain.faces(feature),key=lambda f:(f!=(domain.soft_faces.get(feature.id) or feature.face),f)):
        item=projected(feature,face,design);u,v,_,_=FACE_AXES[face]
        rotations=[domain.fixed_rotations[feature.id]] if feature.id in domain.fixed_rotations else [feature.rotation]
        if feature.definition and feature.id not in domain.fixed_rotations:
            rotations.extend((feature.rotation+angle)%360 for angle in (90,180,270))
            for zone,target in itertools.product(definitions[feature.definition].zones,targets):
                if math.hypot(zone.offset_u,zone.offset_v)>1e-7:
                    rotations.append(math.degrees(math.atan2(target[v]-item.v,target[u]-item.u)-math.atan2(zone.offset_v,zone.offset_u))%360)
        for angle in dict.fromkeys(rotations):
            rotated=item.model_copy(update=dict(rotation=angle))
            probe=design.model_copy(update=dict(features=[rotated if f.id==item.id else f for f in design.features]))
            xs,ys=face_events(probe,rotated,definitions,threads,modifiers)
            events=itertools.chain([(item.u,item.v)],[(p[u],p[v]) for p in target_origins(probe,rotated,definitions)],
                ((x,item.v) for x in xs),((item.u,y) for y in ys),itertools.product(xs,ys))
            def variants(item,events):
                seen=set()
                for x,y in events:
                    if (x,y) in seen:continue
                    seen.add((x,y));placement=item.model_copy(update=dict(u=x,v=y))
                    if not domain.position_matches(placement,design.block):continue
                    yield placement
            queues.append(iter(variants(rotated,events)))
    # A large event list on the preferred face must not crowd other faces and
    # source-window rotations out of the first placement-probe batch.
    while queues:
        active=[]
        for queue in queues:
            try:yield next(queue);active.append(queue)
            except StopIteration:pass
        queues=active


def pack_topology(design,definitions,domain,threads,modifiers):
    """Repack by real Net adjacency; existing/fixed geometry is an obstacle."""
    weights=defaultdict(int)
    for net in design.nets:
        owners={m.split(':')[0] for m in net.members}
        for owner in owners:weights[owner]+=len(owners)-1
    anchored_ids=set(domain.fixed_positions)
    order=sorted((f for f in design.features if f.id in domain.movable and f.id not in anchored_ids),key=lambda f:(
        f.id not in domain.fixed_faces,-weights[f.id],-radius(f,definitions),f.id))
    result=design.model_copy(deep=True)
    placed=[f for f in result.features if f.id not in domain.movable or f.id in anchored_ids]
    for feature in order:
        context=result.model_copy(update=dict(features=[*placed,feature]))
        choices=[]
        # Count-bound placement probes are distinct from the outer search. All
        # missed actions remain eligible through its resumable action generators.
        for trial in itertools.islice(anchored(context,feature,definitions,domain,threads,modifiers),512):
            target=context.model_copy(update=dict(features=[*placed,trial]))
            if not _fits(target,definitions) or placement_conflicts(target,trial,definitions,threads,modifiers,cache=domain._placement_cache):continue
            choices.append((topology_cost(target,definitions),trial.face!=(domain.soft_faces.get(feature.id) or feature.face),
                math.dist((feature.u,feature.v),(trial.u,trial.v)),trial.face,trial.rotation,trial.u,trial.v,trial))
        if not choices:return None
        selected=min(choices,key=lambda row:row[:-1])[-1];placed.append(selected)
        result.features=[selected if f.id==selected.id else f for f in result.features]
    return result


def actions(design,definitions,domain,threads,modifiers,focus=()):
    """Round-robin geometry, connected-group and sizing actions; all resumable."""
    by_id={f.id:f for f in design.features};focus=set(focus)
    def placements():
        queues=[]
        for feature in sorted((f for f in design.features if f.id in domain.movable),key=lambda f:(f.id not in focus,f.id)):
            def moves(f):
                for trial in anchored(design,f,definitions,domain,threads,modifiers):
                    if trial==f:continue
                    target=design.model_copy(deep=True);target.features=[trial if x.id==f.id else x for x in target.features]
                    yield 'interface-placement',target
            queues.append(iter(moves(feature)))
        while queues:
            active=[]
            for queue in queues:
                try:yield next(queue);active.append(queue)
                except StopIteration:pass
            queues=active
    def groups():
        packed=pack_topology(design,definitions,domain,threads,modifiers)
        if packed:yield 'topology-repack',packed
        for net in sorted(design.nets,key=lambda n:(not bool({m.split(':')[0] for m in n.members}&focus),-len(n.members),n.id)):
            owners={m.split(':')[0] for m in net.members}&domain.movable
            if len(owners)<2:continue
            target=design.model_copy(deep=True)
            # Re-align one whole hyperedge using its actual current terminal
            # centroids, then let source-safe packing separate overlapping cuts.
            for owner in sorted(owners):
                f=next(x for x in target.features if x.id==owner);points=target_origins(target,f,definitions)
                if not points:continue
                u,v,_,_=FACE_AXES[f.face];point=points[0]
                if 'u' not in domain.fixed_positions.get(owner,{}):f.u=point[u]
                if 'v' not in domain.fixed_positions.get(owner,{}):f.v=point[v]
            packed=pack_topology(target,definitions,domain,threads,modifiers)
            if packed:yield 'connected-group',packed
    def sizing():
        sizes=dimensions(design.block);upper=design.constraints.envelope_max or (2000,)*3
        lower=design.constraints.envelope_min or (1,)*3
        bore=max((effective_net(design,n).diameter for n in design.nets),default=0)
        lane=max([bore+design.rules.minimum_access_gap]+[bore+required_wall(design,f,definitions=definitions) for f in design.features])
        for axis in domain.dimension_axes:
            planar=[f for f in design.features if f.id in domain.movable and axis in FACE_AXES[f.face][:2]]
            coords=sorted({pose(f,design.block)[0][axis] for f in planar})
            for cut in [(a+b)/2 for a,b in zip(coords,coords[1:])]:
                if sizes[axis]+lane>upper[axis]:continue
                target=design.model_copy(deep=True);setattr(target.block,('length','width','height')[axis],sizes[axis]+lane)
                for f in target.features:
                    if f.id in domain.movable and axis in FACE_AXES[f.face][:2] and pose(by_id[f.id],design.block)[0][axis]>cut:
                        field='u' if FACE_AXES[f.face][0]==axis else 'v'
                        if field not in domain.fixed_positions.get(f.id,{}):setattr(f,field,getattr(f,field)+lane)
                yield 'separate-machining-corridor',target
            # Depth growth enables opposite-face source arrangements. Repack
            # changes relative positions, rather than scaling the old collisions.
            if sizes[axis]+lane<=upper[axis]:
                target=design.model_copy(deep=True);setattr(target.block,('length','width','height')[axis],sizes[axis]+lane)
                packed=pack_topology(target,definitions,domain,threads,modifiers)
                if packed:yield 'resize-and-repack',packed
            needed=lower[axis]
            for f in design.features:
                u,v,normal,_=FACE_AXES[f.face];margin=radius(f,definitions)+required_wall(design,f,definitions=definitions)
                if axis==u:needed=max(needed,f.u+margin)
                elif axis==v:needed=max(needed,f.v+margin)
                else:
                    depth=max(p.end for p in definitions[f.definition].cutting_primitives or definitions[f.definition].stages) if f.definition else f.depth
                    needed=max(needed,depth+required_wall(design,f,definitions=definitions))
            if needed+1e-6<sizes[axis]:
                target=design.model_copy(deep=True);setattr(target.block,('length','width','height')[axis],needed)
                yield 'reduce-unused-stock',target
    queues=[iter(placements()),iter(groups()),iter(sizing())]
    while queues:
        active=[]
        for queue in queues:
            try:yield next(queue);active.append(queue)
            except StopIteration:pass
        queues=active
