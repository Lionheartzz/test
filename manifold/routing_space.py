"""Sparse machining events and complete, externally accessible drilling actions.

No stock/source mutation and no CAD acceptance here. Coordinates describe
possible machining, never an invisible polyline passage inside the stock.
"""
from collections import Counter
import hashlib
import math

from .kinematics import FACE_AXES,dimensions,pose
from .engineering_conditions import effective_net,planning_wall
from .schema import Feature


def cut_key(feature):
    return feature.model_dump_json(exclude={'id','connects_to','schematic_id','machining_id'})


def network_key(route):
    return tuple(sorted(cut_key(f) for f in route))


class MachiningSpace:
    def __init__(self,design,net,definitions,threads,modifiers,*,reserved=(),cache=None,tools=None):
        from .routing import _manufacturing_cuts,cylinder_bounds,terminal_points
        from .engineering_db import tool_definitions
        self.design=design;self.net=effective_net(design,net);self.definitions=definitions
        self.threads=threads;self.modifiers=modifiers;self.cache=cache if cache is not None else {}
        self.tools=tools if tools is not None else tool_definitions('drill')
        self.sizes=dimensions(design.block);self.radius=self.net.diameter/2
        self.wall=planning_wall(design,self.net,definitions)
        self.context=design.model_copy(update=dict(features=[*design.features,*reserved]))
        self.reserved=list(reserved)
        self.failures=Counter();self.blockers={};self.actions={};self.generated=0;self.coordinates=[]
        self.points=terminal_points(design,definitions)
        from .closure_runtime import bind_route
        probe=bind_route(design,[Feature(id='SPACE_PROBE',kind='drilling',face='left',u=self.sizes[1]/2,v=self.sizes[2]/2,
            diameter=self.net.diameter,depth=self.sizes[0]/2,circuit=self.net.id,route_net=self.net.id,plugged=True)])[0]
        entry_radius=probe.clearance_diameter/2 if probe.closure_definition_id else self.radius
        events=[set() for _ in range(3)]
        for member in net.members:
            if member in self.points:
                for axis,value in enumerate(self.points[member]):events[axis].add(value)
        self.obstacles=[]
        for feature in self.context.features:
            if feature.suppressed:continue
            try:cuts=list(_manufacturing_cuts(feature,definitions,threads,modifiers))
            except (KeyError,TypeError,ValueError):
                self.failures['SOURCE_DATA_UNRESOLVED']+=1;self.blockers[feature.id]=['missing executable machining'];continue
            for cut in cuts:
                bounds=cylinder_bounds(cut['feature'],design.block,cut['start'],cut['end'],2*max(cut['radius_start'],cut['radius_end']))
                self.obstacles.append((feature.id,bounds))
                for axis,(lo,hi) in enumerate(bounds):
                    for value in (lo-self.radius-self.wall-.01,hi+self.radius+self.wall+.01):
                        if self.radius+self.wall<value<self.sizes[axis]-self.radius-self.wall:events[axis].add(value)
            if feature.kind in ('port','cavity') or feature.plugged:
                origin,_=pose(feature,design.block)
                radius=definitions[feature.definition].clearance_diameter/2 if feature.definition else feature.clearance_diameter/2
                for axis in FACE_AXES[feature.face][:2]:
                    for value in (origin[axis]-radius-entry_radius-design.rules.minimum_access_gap-.01,
                                  origin[axis]+radius+entry_radius+design.rules.minimum_access_gap+.01):
                        if 0<value<self.sizes[axis]:events[axis].add(value)
        for axis,size in enumerate(self.sizes):
            # Interior intervals are explicit and may be split on demand.
            low=self.radius+self.wall+.01;high=size-low
            events[axis].update((low,high,size/2))
            values=sorted(x for x in events[axis] if 0<x<size)
            self.coordinates.append(values)
        self.intervals=[[(a,b) for a,b in zip(values,values[1:])] for values in self.coordinates]
        self.refined=set();self.visited_coordinates=[set() for _ in range(3)]

    def barrier(self):
        """Prove a blocked centre plane using real parallel full cylinders.

        This is conditional on the current reservations, not a claim that the
        source layout is impossible. Rounded endpoint clearance is bounded
        conservatively from INSIDE the actual forbidden machining envelope.
        """
        groups={};points=[self.points[m] for m in self.net.members if m in self.points]
        for f in self.context.features:
            if f.suppressed or f.direction or f.definition or not f.diameter or f.kind not in ('drilling','mounting') or f.circuit==self.net.id:continue
            origin,direction=pose(f,self.design.block);axis=FACE_AXES[f.face][2]
            for plane_axis in range(3):
                if plane_axis==axis:continue
                third=3-axis-plane_axis;plane=origin[plane_axis]
                if not min(p[plane_axis] for p in points)<plane<max(p[plane_axis] for p in points):continue
                low=min(origin[axis],origin[axis]+direction[axis]*f.depth)
                high=max(origin[axis],origin[axis]+direction[axis]*f.depth)
                groups.setdefault((plane_axis,plane,axis,third),[]).append((low,high,origin[third],f.diameter/2,f.id))
        for (plane_axis,plane,axis,third),cuts in sorted(groups.items()):
            margin=self.radius+self.wall;owners=set();covered=True;proof=[]
            breaks=sorted({margin,self.sizes[axis]-margin,*(v for c in cuts for v in c[:2] if margin<v<self.sizes[axis]-margin)})
            for a,b in zip(breaks,breaks[1:]):
                intervals=[]
                for low,high,coordinate,radius,key in cuts:
                    gap=max(0,low-a,b-high)
                    if gap>=margin:continue
                    guaranteed=radius+math.sqrt(margin*margin-gap*gap)
                    intervals.append((coordinate-guaranteed,coordinate+guaranteed,key))
                end=margin;used=[]
                for lo,hi,key in sorted(intervals):
                    if lo>end+1e-7:break
                    if hi>end:end=hi;used.append(key)
                if end<self.sizes[third]-margin:covered=False;break
                owners.update(used);proof.append(dict(axial_interval=[a,b],covered_to=end))
            if covered:
                return dict(rule='RESERVED_CORRIDOR_BARRIER' if any(f.id in owners for f in self.reserved) else 'FIXED_MACHINING_BLOCKED',
                    plane_axis=plane_axis,plane=plane,parallel_axis=axis,covered_axis=third,
                    centre_domain=[margin,self.sizes[third]-margin],cut_ids=sorted(owners),interval_proof=proof,
                    scope='full-cylinder orthogonal centre corridors under current reservations')
        return None

    def values(self,axis,position,goal):
        values=self.coordinates[axis]
        # Wide free intervals and exact events are interleaved, not deleted.
        # Stage-D profiling found hundreds of near-identical stage events per
        # ray. The path frontier resumes later pages under the same budget.
        events=sorted(values,key=lambda v:(abs(v-goal),v))
        mids=[(a+b)/2 for a,b in sorted(self.intervals[axis],key=lambda p:(-(p[1]-p[0]),abs((p[0]+p[1])/2-goal),p))]
        ordered=[goal]
        for i in range(max(len(events),len(mids))):
            if i<len(mids):ordered.append(mids[i])
            if i<len(events):ordered.append(events[i])
        return list(dict.fromkeys(v for v in ordered if abs(v-position)>1e-7))

    def refine(self,axis,coordinate):
        for a,b in list(self.intervals[axis]):
            if a<coordinate<b and b-a>self.net.diameter+self.wall:
                marker=(axis,a,b)
                if marker in self.refined:return
                self.refined.add(marker);mid=(a+b)/2
                self.intervals[axis].remove((a,b));self.intervals[axis].extend(((a,mid),(mid,b)));return

    def attach(self,route,feature):
        # Same-face coaxial cuts all begin at the same external surface: their
        # intervals overlap. Opposite/disjoint bores are never merged here.
        result=[];chosen=feature
        for old in route:
            if old.face==feature.face and abs(old.u-feature.u)<1e-8 and abs(old.v-feature.v)<1e-8 and old.diameter==feature.diameter:
                if old.depth>chosen.depth:chosen=old
            else:result.append(old)
        return sorted([*result,chosen],key=lambda f:f.id)

    def rejected_measurement(self,route):
        """Reuse exact geometry measurements, never a stale acceptance PASS.

        Conditional on both actual cuts remaining present; releasing another
        Net removes its constraint. Current wall/overlap thresholds are applied
        anew, so changed engineering conditions cannot inherit an approval.
        """
        distances=self.cache.get('exact_cut_distances',{});volumes=self.cache.get('inadequate_contact_volumes',{})
        if not distances and not volumes:return False
        from .routing import _feature_key
        from .engineering_conditions import required_wall
        all_features=[*self.context.features,*route];keys={f.id:_feature_key(f) for f in all_features}
        for first in route:
            for second in all_features:
                if first.id==second.id:continue
                token=(self.sizes,tuple(sorted((keys[first.id],keys[second.id]))))
                if token in distances and distances[token]+1e-6<required_wall(self.design,first,second,definitions=self.definitions):
                    self.failures['exact_feature_wall_reused']+=1;return True
                if token in volumes and 1e-6<volumes[token]<self.design.rules.minimum_overlap_volume:
                    self.failures['insufficient_direct_contact_reused']+=1;return True
        return False

    def junctions(self,route,goal):
        """Attachment points on actual usable full cylinders, not only bends."""
        result=set()
        for f in route:
            origin,direction=pose(f,self.design.block);axis=FACE_AXES[f.face][2]
            low=(f.plug_length if f.plugged else 0)+self.radius+.01;high=f.depth-self.radius
            if high<low:continue
            desired=(goal[axis]-origin[axis])*direction[axis]
            depths={max(low,min(high,desired)),(low+high)/2}
            depths.update((x-origin[axis])*direction[axis] for x in self.coordinates[axis] if low<=(x-origin[axis])*direction[axis]<=high)
            result.update(tuple(origin[i]+direction[i]*d for i in range(3)) for d in depths)
        return result

    def narrow_window_seeds(self):
        """Real side-entry tip stops, for windows too narrow for a full bore.

        The source profile gives the FIRST contact, not a nominal cavity bottom.
        These remain unverified candidates until the existing exact fluid gate.
        """
        from .routing import _manufacturing_cuts,route_obstructions
        from .closure_runtime import bind_route
        by_id={f.id:f for f in self.design.features};result={}
        for member in self.net.members:
            owner,_,zone_id=member.partition(':');source=by_id.get(owner)
            if not zone_id or source is None or not source.definition or source.direction:continue
            zone=next((z for z in self.definitions[source.definition].zones if z.id==zone_id),None)
            if zone is None or zone.end-zone.start>=self.net.diameter+.2:continue
            normal=FACE_AXES[source.face][2];point=self.points[member];middle=(zone.start+zone.end)/2
            radii=[]
            for cut in _manufacturing_cuts(source,self.definitions,self.threads,self.modifiers):
                origin,direction=pose(cut['feature'],self.design.block)
                if not cut['start']<=middle<=cut['end'] or any(abs(origin[i]-point[i])>1e-6 for i in range(3) if i!=normal):continue
                t=(middle-cut['start'])/(cut['end']-cut['start'])
                radii.append(cut['radius_start']+t*(cut['radius_end']-cut['radius_start']))
            if not radii:continue
            for face,(u,v,axis,sign) in FACE_AXES.items():
                if axis==normal or face in self.design.constraints.forbidden_drilling_faces:continue
                distance=point[axis] if sign>0 else self.sizes[axis]-point[axis]
                first_contact=distance-max(radii)
                tip_length=self.radius/math.tan(math.radians(Feature.model_fields['tip_angle'].default/2))
                depth=first_contact-tip_length+.001
                if depth<=0 or depth>=self.sizes[axis]:continue
                identifier='R3D_SIDE_'+hashlib.sha256((member+face).encode()).hexdigest()[:16]
                # Bind actual engagement before validating a plugged short cut;
                # the schema's legacy 8 mm default is not an engineering limit.
                raw=Feature(id=identifier,kind='drilling',face=face,u=point[u],v=point[v],
                    depth=depth,diameter=self.net.diameter,circuit=self.net.id,route_net=self.net.id)
                bore=bind_route(self.design,[raw.model_copy(update=dict(plugged=True))])[0]
                if bore.plug_length>=depth:continue
                tip=self.radius/math.tan(math.radians(bore.tip_angle/2))
                if not bore.closure_definition_id or not any(abs(t['diameter_mm']-bore.diameter)<=.011 and t['max_depth_mm']>=depth+tip for t in self.tools):continue
                if route_obstructions(self.context,self.net,[bore],self.threads,self.definitions,self.modifiers,self.cache):continue
                # Collision is monotone as the same source-bound straight cut
                # deepens. Find its last protected-region-safe tip contact.
                lo=depth;hi=first_contact
                for _ in range(12):
                    middle=(lo+hi)/2;trial=bore.model_copy(update=dict(depth=middle))
                    if route_obstructions(self.context,self.net,[trial],self.threads,self.definitions,self.modifiers,self.cache):hi=middle
                    else:lo=middle
                bore=bore.model_copy(update=dict(depth=max(depth,lo-.01)))
                result.setdefault(member,[]).append(bore)
        return result

    def operations(self,a,b,route):
        from .closure_runtime import bind_route
        from .routing import route_obstructions
        differing=[i for i in range(3) if abs(a[i]-b[i])>1e-7]
        if len(differing)!=1:return []
        axis=differing[0];result=[];self.visited_coordinates[axis].add(b[axis])
        for face,(u,v,normal,sign) in FACE_AXES.items():
            if normal!=axis or face in self.design.constraints.forbidden_drilling_faces:continue
            distances=[p[axis] if sign>0 else self.sizes[axis]-p[axis] for p in (a,b)]
            functional=any(f.kind=='port' and not f.suppressed and f.id in self.net.members and
                f.face==face and abs(f.u-a[u])<1e-7 and abs(f.v-a[v])<1e-7 and
                (self.definitions[f.definition].zones[0].diameter if f.definition else f.diameter)>=self.net.diameter
                for f in self.design.features)
            # Free junctions use full-cylinder overlap; coincident cylinder ends
            # create fragile BRep contacts. Source first-contact stops are
            # supplied separately by the existing axial eligibility path.
            for extension in (self.radius,):
                depth=max(distances)+extension
                # A short functional continuation can be machinable. Stock,
                # actual tool reach, closure engagement and source protection
                # below determine feasibility, not a nominal minimum length.
                if min(distances)<0 or depth<=0 or depth>=self.sizes[axis]:continue
                digest=hashlib.sha256(repr((self.net.id,face,a[u],a[v],depth,self.net.diameter)).encode()).hexdigest()[:20]
                feature=Feature(id='R3D_'+digest,kind='drilling',face=face,u=a[u],v=a[v],diameter=self.net.diameter,
                    depth=depth,circuit=self.net.id,route_net=self.net.id).model_copy(update=dict(plugged=not functional))
                token=cut_key(feature)
                if token not in self.actions:
                    self.generated+=1
                    feature=bind_route(self.design,[feature])[0]
                    tip=self.radius/math.tan(math.radians(feature.tip_angle/2))
                    failures=set()
                    if not any(abs(t['diameter_mm']-feature.diameter)<=.011 and t['max_depth_mm']+1e-6>=depth+tip for t in self.tools):failures.add(('tool_reach',feature.id))
                    if feature.plugged and not feature.closure_definition_id:failures.add(('closure_unresolved',feature.id))
                    if feature.plugged and feature.plug_length>=depth:failures.add(('closure_engagement',feature.id))
                    failures|=route_obstructions(self.context,self.net,[feature],self.threads,self.definitions,self.modifiers,self.cache)
                    self.actions[token]=(feature,failures)
                    for failure in failures:
                        self.failures[failure[0]]+=1
                        if len(self.blockers)<64:self.blockers[str(failure)]=list(failure)
                feature,failures=self.actions[token]
                if failures:continue
                trial=self.attach(route,feature)
                actual=next(f for f in trial if f.face==feature.face and abs(f.u-feature.u)<1e-8
                            and abs(f.v-feature.v)<1e-8 and f.diameter==feature.diameter)
                # The same complete cut may serve different path segments.
                # Endpoint clearance is a transition condition, never a cached
                # property of the cut. A deeper existing coaxial cut may retain
                # a different closure after attach(), so inspect the actual cut.
                if min(distances)<= (actual.plug_length+self.radius if actual.plugged else 0):
                    self.failures['occupied_entry']+=1
                    continue
                if self.rejected_measurement(trial):continue
                if len(trial)+len(self.design.features)>120:continue
                own=self.design.model_copy(update=dict(features=[]))
                conflicts=route_obstructions(own,self.net,trial,self.threads,self.definitions,self.modifiers,self.cache)
                if not conflicts:result.append(trial)
        unique={network_key(r):r for r in result}
        return list(unique.values())

    def diagnostics(self,termination):
        return dict(termination=termination,coordinate_events=[len(v) for v in self.coordinates],
            coordinate_event_values=self.coordinates,
            unexpanded_events=[sorted(set(v)-used) for v,used in zip(self.coordinates,self.visited_coordinates)],
            unexpanded_coordinate_events=[len(set(v)-used) for v,used in zip(self.coordinates,self.visited_coordinates)],
            free_intervals=[len(v) for v in self.intervals],interval_bounds=self.intervals,refinements=len(self.refined),
            generated_operations=self.generated,screened_operations=len(self.actions),
            rejected_rules=dict(self.failures),blocked_constraints=list(self.blockers.values())[:32],
            remaining_space_not_proven_infeasible=True)
