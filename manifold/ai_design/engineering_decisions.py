"""Engineering decisions own the AI layout frontier, Router owns real cuts.

Conditional sufficient separation domains are not physical nogoods. Every
solved domain is re-measured against full production machining. CAD errors
remain unknown; neither sampling nor a feasible constraint graph grants PASS.
"""
from collections import deque
from dataclasses import dataclass, field, replace
import itertools
import math
import time

from ..kinematics import FACE_AXES, dimensions, pose
from ..routing import _manufacturing_cuts, cylinder_bounds, terminal_points, route_obstructions
from .engineering_plan import EngineeringPlan, digest
from .corridor_planner import CorridorPlanner
from .placement_solver import PlacementSolver, Separation
from .design_space import signature, fit_violations, source_conflicts
from .initialization import source_extents


@dataclass
class DecisionState:
    plans: dict
    poses: dict = field(default_factory=dict)
    separations: tuple = ()
    preserve: bool = True
    parent: str | None = None
    cause: dict = field(default_factory=lambda:dict(rule='INITIAL_MACHINING_PLAN'))
    dimension_floor: tuple = ()
    release: tuple = ()
    route_overrides: dict = field(default_factory=dict)
    override_geometry: str | None = None
    release_axes: dict = field(default_factory=dict)


class EngineeringDecisionController:
    def __init__(self, design, definitions, domain, threads, modifiers, tools, *, limit=3072,progress=None):
        self.plan=EngineeringPlan.compile(design,definitions,domain,threads,modifiers,tools)
        self.corridors=CorridorPlanner(self.plan);self.placement=PlacementSolver(self.plan)
        self.placement.profile_access=self.corridors.profile_access
        self.queue=deque();self.seen=set();self.states={};self.by_decision={};self.records=[];self.expanded=set()
        self.cache={};self.limit=limit;self.started=time.monotonic();self.materializations=0
        self.source_checks=0;self.unexpressed=[];self.narrow_errors=[]
        self.partial=[];self.delivered_partial=False;self.pair_screens=0
        self.progress=progress
        initial=self.corridors.initial()
        if len(initial)==len(self.plan.nets):self.enqueue(DecisionState(initial))
        else:self.unexpressed=[r['net'] for r in self.plan.nets if r['net'] not in initial]

    def token(self,state):
        return digest([self.plan.dependency,[state.plans[n].diagnostics() for n in self.corridors.order if n in state.plans],
                       state.poses,[(s.high,s.low,s.distance) for s in state.separations],state.preserve,state.dimension_floor,state.release,
                       state.override_geometry,{n:[f.model_dump() for f in fs] for n,fs in state.route_overrides.items()},state.release_axes])

    def enqueue(self,state,*,first=False):
        key=self.token(state)
        if key in self.seen:return
        self.seen.add(key)
        (self.queue.appendleft if first else self.queue.append)((key,state))

    def alternatives(self,state,implicated,*,source=False):
        # The same process choices under different measured separations,
        # stock bounds or released coordinates are different feasible domains.
        # Reusing only a topology/pose key silently loses their alternatives.
        key=(self.token(state),tuple(sorted(implicated)))
        if key not in self.expanded:
            self.expanded.add(key)
            for plans,reason in self.corridors.alternatives(state.plans,implicated,poses=state.poses):
                self.enqueue(replace(state,plans=plans,route_overrides={},override_geometry=None,
                    parent=self.token(state),cause={**reason,'rule':'ALTERNATIVE_MANUFACTURING_DOMAIN'}))
        if state.preserve:
            # Source movement is a separate, reviewable decision domain. It is
            # reached after the alternative entry domains already in the queue.
            self.enqueue(replace(state,preserve=False,parent=self.token(state),cause=dict(rule='RELEASE_AI_SOURCE_COORDINATES',nets=list(implicated))))
        if source and not state.preserve:
            owners={m.split(':')[0] for r in self.plan.nets if r['net'] in implicated for m in r['members']}
            # Changing one rigid source affects EVERY incident Net, not only
            # the failing branch. Regenerate all symbolic access orders below.
            by_id={f.id:f for f in self.plan.source.features}
            for owner in sorted(owners,key=lambda f:self.placement.fi[f]):
                f=by_id[owner]
                if owner not in self.plan.domain.movable:continue
                for face in sorted(self.plan.domain.faces(f),key=lambda face:(
                        sum(FACE_AXES[face][2]==p.orders[0][1][0] for p in state.plans.values()),FACE_AXES[face])):
                    current=state.poses.get(owner,(f.face,f.rotation))
                    if face==current[0]:continue
                    poses={**state.poses,owner:(face,current[1])}
                    target=self.plan.source.model_copy(deep=True)
                    for g in target.features:
                        if g.id in poses:g.face,g.rotation=poses[g.id]
                    plans={}
                    for row in self.plan.nets:
                        choices=self.corridors.for_net(row,target);old=state.plans[row['net']]
                        selected=next((p for p in choices if p.access==old.access and p.spine_axis==old.spine_axis and
                            p.planar==old.planar and bool(p.axial_members)==bool(old.axial_members)),None)
                        if selected is None:selected=next((p for p in choices if p.spine_axis==old.spine_axis and p.planar==old.planar),None)
                        if selected is None:break
                        plans[row['net']]=replace(selected,entry=old.entry,side=old.side,entry_axes=old.entry_axes,reserve_columns=old.reserve_columns)
                    if len(plans)==len(state.plans):
                        self.enqueue(replace(state,plans=plans,poses=poses,parent=self.token(state),cause=dict(rule='RIGID_WINDOW_ACCESS_FACE',owners=[owner],
                            affected_nets=[r['net'] for r in self.plan.nets if any(m.split(':')[0]==owner for m in r['members'])])))
                if owner not in self.plan.domain.fixed_rotations:
                    definition=self.plan.definitions.get(f.definition)
                    offsets=[(z.offset_u,z.offset_v) for z in definition.zones] if definition else []
                    angles={math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])) for a,b in itertools.combinations(offsets,2) if a!=b}
                    for angle in sorted(angles):
                        for alignment in (0.,90.):
                            rotation=(alignment-angle)%360
                            self.enqueue(replace(state,poses={**state.poses,owner:(state.poses.get(owner,(f.face,f.rotation))[0],rotation)},parent=self.token(state),
                                cause=dict(rule='RIGID_WINDOW_AXIS_ALIGNMENT',owners=[owner],rotation=rotation)))

    def _source_separations(self,target,state,pairs):
        e=self.plan;by_id={f.id:f for f in target.features}
        for a,b in sorted(pairs,key=lambda pair:tuple(sorted(self.placement.fi[k] for k in pair))):
            a,b=sorted((a,b),key=lambda key:self.placement.fi[key])
            if a not in by_id or b not in by_id:continue
            ra=source_extents(target,by_id[a],e.definitions,e.threads,e.modifiers)
            rb=source_extents(target,by_id[b],e.definitions,e.threads,e.modifiers)
            wall=max(ra['wall'],rb['wall'],target.rules.minimum_access_gap)
            direct={p.spine_axis for p in state.plans.values() if p.access=='aligned-window'}
            for axis in sorted(range(3),key=lambda axis:axis in direct):
                for low,high,rlo,rhi in ((a,b,ra,rb),(b,a,rb,ra)):
                    # Includes installation disks and complete source cuts.
                    origin_lo=pose(by_id[low],target.block)[0][axis];origin_hi=pose(by_id[high],target.block)[0][axis]
                    def extent(row,origin,upper):
                        normal=FACE_AXES[by_id[row['feature']].face][2]
                        values=[b[axis][int(upper)]-origin for b in row['bounds']]
                        if axis!=normal:values.append(row['radius'] if upper else -row['radius'])
                        return (max if upper else min)(values or [0.])
                    distance=extent(rlo,origin_lo,True)-extent(rhi,origin_hi,False)+wall
                    cut=Separation(self.placement.origin(high,axis),self.placement.origin(low,axis),distance,
                        dict(rule='SOURCE_INSTALLATION_SEPARATION',features=[low,high],axis=axis,required=distance,
                             evidence='sufficient complete source/installation envelope separation'))
                    if cut not in state.separations:
                        self.enqueue(replace(state,separations=(*state.separations,cut),parent=self.token(state),
                            cause=cut.reason),first=True)

    def _bound(self, target, junctions, feature, axis, value):
        """Associate measured bounds with their manufacturing decision variable.

        The offset defines a conditional sufficient repair hypothesis. Geometry
        is rebuilt and re-screened afterwards; it is never a safety certificate.
        """
        if not feature.route_net:return self.placement.origin(feature.id,axis),value-pose(feature,target.block)[0][axis]
        nr=next(r for r in self.plan.nets if r['net']==feature.route_net)
        points=terminal_points(target,self.plan.definitions);by_id={f.id:f for f in target.features}
        candidates=[(abs(value-junctions[feature.route_net][axis]),self.placement.lane(feature.route_net,axis),
                     value-junctions[feature.route_net][axis])]
        for member in nr['members']:
            f=by_id[member.split(':')[0]];p=points[member]
            candidates.append((abs(value-p[axis]),self.placement.origin(f.id,axis),value-pose(f,target.block)[0][axis]))
        _,var,offset=min(candidates)
        return var,offset

    def measured_repairs(self,target,state,junctions,constraints):
        e=self.plan;by_id={f.id:f for f in target.features}
        for witness in constraints:
            raw=witness.get('features',[])
            from ..schema import Feature
            features=[Feature.model_validate(f) for f in raw]
            if len(features)<2:continue
            a,b=features[:2]
            def bounds(f):
                cuts=list(_manufacturing_cuts(f,e.definitions,e.threads,e.modifiers))
                boxes=[cylinder_bounds(c['feature'],target.block,c['start'],c['end'],2*max(c['radius_start'],c['radius_end'])) for c in cuts]
                return [(min(c[i][0] for c in boxes),max(c[i][1] for c in boxes)) for i in range(3)]
            ba,bb=bounds(a),bounds(b)
            from ..engineering_conditions import required_wall
            wall=required_wall(target,a,b,definitions=e.definitions)
            choices=[]
            for axis in range(3):
                for low,high,blo,bhi in ((a,b,ba,bb),(b,a,bb,ba)):
                    lv,lc=self._bound(target,junctions,low,axis,blo[axis][1])
                    hv,hc=self._bound(target,junctions,high,axis,bhi[axis][0])
                    need=lc-hc+wall+.01
                    if lv==hv:continue
                    cause=dict(rule='FULL_MACHINING_SEPARATION',features=[low.id,high.id],nets=witness.get('nets',[]),axis=axis,
                        before=dict(low_upper=blo[axis][1],high_lower=bhi[axis][0],wall=wall),
                        expected_geometric_effect=dict(high_minus_low_at_least=need),
                        status='CONDITIONAL_SUFFICIENT_DOMAIN_NOT_PHYSICAL_NOGOOD')
                    choices.append((max(0,blo[axis][1]+wall-bhi[axis][0]),Separation(hv,lv,need,cause)))
            for _,cut in sorted(choices,key=lambda r:r[0],reverse=True):
                if cut in state.separations:continue
                coaxial=all(state.plans[n].access=='coaxial' for n in witness.get('nets',[]) if n in state.plans)
                owners={m.split(':')[0] for r in e.nets if r['net'] in witness.get('nets',[]) for m in r['members']}
                self.enqueue(replace(state,separations=(*state.separations,cut),parent=self.token(state),cause=cut.reason,
                    preserve=False if coaxial else state.preserve,
                    dimension_floor=dimensions(target.block) if coaxial else state.dimension_floor,
                    release=tuple(sorted(set(state.release)|owners)) if coaxial else state.release),first=coaxial)
            self.alternatives(state,witness.get('nets',[]),source=True)

    def machining_screen(self,target,routes):
        """Production complete-cut checks, distinct from local fluid/CAD admission."""
        from ..engineering_conditions import effective_net
        from ..routing import _ProposalSnapshot, _route_pair_failures, segment_depth
        from ..schema import Feature
        from ..cad_geometry import GeometryEvaluationError
        e=self.plan;failures={};witnesses=[];nets={n.id:effective_net(target,n) for n in target.nets}
        for name,cuts in routes.items():
            try:bad=set(route_obstructions(target,nets[name],cuts,e.threads,e.definitions,e.modifiers,self.cache))
            except GeometryEvaluationError as exc:
                self.narrow_errors.append(exc.record);bad={('CAD_EVALUATION_ERROR',name)}
            for f in cuts:
                if f.plugged and not f.closure_definition_id:bad.add(('closure_unresolved',f.id))
                if f.face in target.constraints.forbidden_drilling_faces:bad.add(('forbidden_face',f.id))
                if not any(abs(t['diameter_mm']-f.diameter)<=.011 and t['max_depth_mm']+1e-6>=segment_depth(f) for t in e.tools):bad.add(('tool_reach',f.id))
                try:Feature.model_validate(f.model_dump())
                except ValueError:bad.add(('invalid_machining',f.id))
            if bad:
                failures[name]=sorted(bad)
                source={f.id:f for f in target.features};by_id={f.id:f for f in cuts}
                for failure in bad:
                    pair=[source.get(k) or by_id.get(k) for k in failure[1:]]
                    pair=[f for f in pair if f is not None]
                    if len(pair)==2:witnesses.append(dict(nets=[name],features=[f.model_dump() for f in pair],failures=[failure]))
        intrinsic=set(failures)
        snapshot=_ProposalSnapshot(target,e.definitions,e.threads,e.modifiers)
        budget=dict(used=0,limit=4000)
        for a,b in itertools.combinations(routes,2):
            if a in intrinsic or b in intrinsic:continue
            try:bad=_route_pair_failures(target,nets[a],dict(route=routes[a]),nets[b],dict(route=routes[b]),snapshot,budget)
            except GeometryEvaluationError as exc:
                self.narrow_errors.append(exc.record);bad={('CAD_EVALUATION_ERROR',a,b)}
            if bad:
                failures.setdefault(a,[]).extend(sorted(bad));failures.setdefault(b,[]).extend(sorted(bad))
                ids={k for f in bad for k in f[1:]}
                witnesses.append(dict(nets=[a,b],features=[f.model_dump() for f in routes[a]+routes[b] if f.id in ids],failures=sorted(bad)))
        self.pair_screens+=budget['used']
        return failures,witnesses

    def next_candidate(self):
        from .initialization import source_extents
        while self.queue and len(self.records)<self.limit:
            key,state=self.queue.popleft();solved,detail=self.placement.solve(state.plans,poses=state.poses,
                separations=state.separations,preserve=state.preserve,dimension_floor=state.dimension_floor,release=state.release,
                release_axes=state.release_axes)
            record=dict(id=key,parent=state.parent,cause=state.cause,responsible_constraints=detail,
                        selected_plan={n:p.diagnostics() for n,p in state.plans.items()},
                        decision_order='MACHINING_PLAN -> COORDINATE_CONSTRAINTS -> PRODUCTION_ROUTER -> CAD')
            self.records.append(record)
            if self.progress:self.progress(completed=len(self.records),total=self.limit,decision=key)
            if solved is None:
                record['outcome']='ROLLBACK_SELECTED_DOMAIN'
                if state.preserve and any(r['rule']=='SOFT_SEED_POSITION' for r in detail.get('cycle',[])):
                    self.enqueue(replace(state,preserve=False,parent=key,
                        cause=dict(rule='PROPAGATE_SOFT_SEED_CONTRADICTION',cycle=detail['cycle'])),first=True)
                    continue
                implicated={n for r in detail.get('cycle',[]) for n in ([r['net']] if 'net' in r else r.get('nets',[]))}
                aligned={n for n in implicated if state.plans[n].access in ('aligned-window','coaxial')}
                if aligned and any(r['rule']=='COAXIAL_WINDOW_ALIGNMENT' for r in detail.get('cycle',[])):
                    probe=self.plan.source.model_copy(deep=True)
                    for f in probe.features:
                        if f.id in state.poses:f.face,f.rotation=state.poses[f.id]
                    for name in reversed([n for n in self.corridors.order if n in aligned]):
                        row=next(r for r in self.plan.nets if r['net']==name)
                        for option in reversed(self.corridors.for_net(row,probe)):
                            if option.access in ('aligned-window','coaxial'):continue
                            self.enqueue(replace(state,plans={**state.plans,name:option},parent=key,
                                cause=dict(rule='PROPAGATE_ALIGNED_WINDOW_CYCLE',nets=[name],cycle=detail['cycle'])),first=True)
                    for name in self.corridors.order:
                        if name in implicated and name not in aligned and state.plans[name].reserve_columns:
                            self.enqueue(replace(state,plans={**state.plans,name:replace(state.plans[name],reserve_columns=False)},parent=key,
                                cause=dict(rule='PROPAGATE_CONDITIONAL_SOURCE_RESERVATION',nets=[name],cycle=detail['cycle'])),first=True)
                    continue
                window_cycles=[r for r in detail.get('cycle',[]) if r['rule']=='SHARED_WINDOW_ESCAPE_ORDER']
                if window_cycles:
                    # Opposing rigid window order can make an escape corridor
                    # assignment contradictory. Flip the actual source frame
                    # (when allowed), then rebuild ALL incident Net processes.
                    pose_repairs=[]
                    for owner in sorted({r['feature'] for r in window_cycles},key=lambda x:self.placement.fi[x]):
                        source=next(f for f in self.plan.source.features if f.id==owner)
                        face,rotation=state.poses.get(owner,(source.face,source.rotation));normal,sign=FACE_AXES[face][2:]
                        opposite=next(f for f,v in FACE_AXES.items() if v[2]==normal and v[3]==-sign)
                        if owner not in self.plan.domain.movable or opposite not in self.plan.domain.faces(source):continue
                        poses={**state.poses,owner:(opposite,rotation)};probe=self.plan.source.model_copy(deep=True)
                        for f in probe.features:
                            if f.id in poses:f.face,f.rotation=poses[f.id]
                        plans={}
                        for row in self.plan.nets:
                            old=state.plans[row['net']];options=self.corridors.for_net(row,probe)
                            plan=next((p for p in options if p.access==old.access and p.spine_axis==old.spine_axis and
                                p.planar==old.planar and bool(p.axial_members)==bool(old.axial_members)),None)
                            if plan is None:plan=next((p for p in options if p.spine_axis==old.spine_axis and p.planar==old.planar),None)
                            if plan is None:break
                            plans[row['net']]=replace(plan,entry=old.entry,side=old.side,entry_axes=old.entry_axes,reserve_columns=old.reserve_columns)
                        if len(plans)==len(state.plans):pose_repairs.append(replace(state,plans=plans,poses=poses,preserve=False,parent=key,
                            cause=dict(rule='PROPAGATE_SHARED_WINDOW_ORDER',owners=[owner],nets=sorted(implicated),cycle=detail['cycle'])))
                    probe=self.plan.source.model_copy(deep=True)
                    for f in probe.features:
                        if f.id in state.poses:f.face,f.rotation=state.poses[f.id]
                    for name in reversed([n for n in self.corridors.order if n in implicated]):
                        old=state.plans[name]
                        row=next(r for r in self.plan.nets if r['net']==name)
                        for option in reversed(self.corridors.for_net(row,probe)):
                            if option.spine_axis==old.spine_axis or option.planar!=old.planar:continue
                            self.enqueue(replace(state,plans={**state.plans,name:replace(option,entry=old.entry)},parent=key,
                                cause=dict(rule='PROPAGATE_PROCESS_CORRIDOR_CYCLE',nets=[name],cycle=detail['cycle'])),first=True)
                    # The cycle is across rigid window order, not an entry
                    # sign. Test its directly implicated source-frame changes
                    # before repeatedly changing one Net's spine. Retain all
                    # process siblings; no coverage-based pruning is implied.
                    for repair in reversed(pose_repairs):self.enqueue(repair,first=True)
                    continue
                # An equality-cycle cannot be repaired by changing an entry
                # sign. Propagate its coupled process variables immediately;
                # retain the single-decision siblings as alternative domains.
                releasable={n for n in implicated if state.plans[n].planar}
                if releasable:
                    for group in [*(set((n,)) for n in self.corridors.order if n in releasable),releasable]:
                        plans={n:replace(p,planar=False) if n in group else p for n,p in state.plans.items()}
                        self.enqueue(replace(state,plans=plans,parent=key,route_overrides={},override_geometry=None,
                            cause=dict(rule='PROPAGATE_RIGID_WINDOW_CYCLE',nets=sorted(group),cycle=detail['cycle'])),first=True)
                    continue
                self.alternatives(state,implicated or tuple(state.plans));continue
            target,junctions=solved
            violations=fit_violations(target,self.plan.definitions,self.plan.domain)
            clashes=source_conflicts(target,self.plan.definitions,self.plan.threads,self.plan.modifiers,self.plan.domain._placement_cache)
            self.source_checks+=1
            if violations or clashes:
                record.update(outcome='ROLLBACK_SOURCE_SCREEN',actual_measurement=dict(violations=violations,conflicts=clashes))
                if state.preserve:
                    self.enqueue(replace(state,preserve=False,parent=key,
                        cause=dict(rule='PROPAGATE_SOURCE_PLACEMENT_CONFLICT',conflicts=clashes,violations=violations)),first=True)
                else:
                    if state.release:
                        group=set(state.release)|{f for pair in clashes for f in pair if f in self.plan.domain.movable}
                        state=replace(state,release=tuple(sorted(group)))
                    self.alternatives(state,tuple(state.plans),source=True)
                    self._source_separations(target,state,clashes)
                continue
            routes=self.corridors.materialize(target,state.plans,junctions,self.cache);self.materializations+=1
            if state.override_geometry==digest(signature(target)):
                routes.update(state.route_overrides)
            record.update(outcome='ROUTER_SCREEN_PENDING',junctions=junctions,
                source_layout=dict(dimensions=dimensions(target.block),placements=[dict(feature=f.id,face=f.face,u=f.u,v=f.v,rotation=f.rotation) for f in target.features]),
                actual_drillings={n:[f.model_dump(mode='json') for f in cuts] for n,cuts in routes.items()})
            info=dict(state=state,junctions=junctions,routes=routes,record=record)
            self.states[signature(target)]=info
            self.by_decision[key]=info
            failures,witnesses=self.machining_screen(target,routes)
            record['actual_measurement']=dict(machining_failures=failures,physical_witnesses=witnesses)
            missing=set(state.plans)-set(routes)
            if failures or missing:
                record['outcome']='ROLLBACK_MANUFACTURING_DOMAIN'
                self.partial.append((len(set(routes)-set(failures)),target,info))
                self.alternatives(state,set(failures)|missing,source=True)
                self.measured_repairs(target,state,junctions,witnesses)
                # A solved source domain is a useful AI state even when its
                # first instantiation needs the shared resumable Router. The
                # manufacturing constraints, rather than a packing sampler,
                # own the next geometry revision and all its dependencies.
                continue
            # Different manufacturing plans at identical source positions MUST
            # remain different states, unlike a layout-only signature.
            return target,dict(rule='ENGINEERING_PLANNED',engineering_decision=key,
                               requires_route_regeneration=True),routes
        if self.partial and not self.delivered_partial:
            self.delivered_partial=True
            _,target,info=max(self.partial,key=lambda row:row[0])
            record=info['record'];record['outcome']='SOURCE_LAYOUT_READY_MACHINING_PENDING'
            self.states[signature(target)]=info
            # Source-only handoff. A rejected process is NEVER a Router seed.
            return target,dict(rule='ENGINEERING_PLANNED',engineering_decision=record['id'],
                               requires_route_regeneration=False,planning_status='SOURCE_LAYOUT_READY_MACHINING_PENDING'),{}
        return None

    def observe(self,target,assessment,decision=None):
        info=self.by_decision.get(decision) if decision else self.states.get(signature(target))
        if info is None:return
        state=info['state'];record=info['record'];e=self.plan
        record['actual_measurement'].update(compatible=assessment.get('compatible'),
            unresolved=assessment.get('unresolved_nets'),conflicts=assessment.get('conflicts'),
            local_cad=assessment.get('partial_routing',{}).get('local_admission'),
            full_exact=assessment.get('full_exact_outcome'))
        record['outcome']='RETAIN_ANALYTIC_REQUIRES_CAD' if assessment.get('compatible') else 'REPAIR_ENGINEERING_CONSTRAINTS'
        if (assessment.get('full_exact_outcome') or {}).get('status')=='EXACT_FEASIBLE':
            record['outcome']='FULL_EXACT_BREP_STEP_ACCEPTED';return
        admissions=dict(assessment.get('partial_routing',{}).get('local_admission',{}))
        admissions.update({n:dict(v,status='CAD_EVALUATION_ERROR' if v.get('cad_error') else 'LOCAL_EXACT_REJECTED')
                           for n,v in assessment.get('exact_connections',{}).items()})
        for name,admission in admissions.items():
            if admission['status']=='CAD_EVALUATION_ERROR':
                record.setdefault('unknown_cad',[]).append(admission)
                continue
            contacts=(admission.get('connectivity') or {}).get('insufficient_direct_contacts',[])
            cuts=info['routes'].get(name,[])
            if contacts and cuts:
                for repaired,measurement in contact_alternatives(target,name,cuts,contacts,e):
                    self.enqueue(replace(state,route_overrides={**state.route_overrides,name:repaired},
                        override_geometry=digest(signature(target)),parent=self.token(state),cause=measurement),first=True)
                by_id={f.id:f for f in cuts}
                for contact in contacts:
                    if any(n not in by_id for n in contact['nodes']):continue
                    a,b=[by_id[n] for n in contact['nodes']]
                    aa,ab=FACE_AXES[a.face][2],FACE_AXES[b.face][2]
                    if aa==ab:continue
                    third=3-aa-ab;oa=pose(a,target.block)[0][third];ob=pose(b,target.block)[0][third]
                    if abs(oa-ob)<1e-7:continue
                    av,ac=self._bound(target,info['junctions'],a,third,oa)
                    bv,bc=self._bound(target,info['junctions'],b,third,ob)
                    cause=dict(rule='DIRECT_CONTACT_AXIS_ALIGNMENT',nodes=contact['nodes'],net=name,axis=third,
                        actual_before_mm3=contact['volume_mm3'],required_mm3=target.rules.minimum_overlap_volume,
                        expected_geometric_effect=dict(transverse_offset_before=abs(oa-ob),transverse_offset_after=0),
                        acceptance='CONDITIONAL_REPAIR_REQUIRES_PRODUCTION_CAD')
                    alignment=(Separation(av,bv,bc-ac,cause),Separation(bv,av,ac-bc,cause))
                    owners=tuple(m.split(':')[0] for r in e.nets if r['net']==name for m in r['members'])
                    changed=next((owner for var in (av,bv) for owner in owners if
                        var==self.placement.origin(owner,third) and owner in e.domain.movable and
                        third!=FACE_AXES[next(f for f in target.features if f.id==owner).face][2]),None)
                    axes={changed:(third,)} if changed else {}
                    repair=replace(state,preserve=False,dimension_floor=dimensions(target.block),release=owners,release_axes=axes,
                        route_overrides={},override_geometry=None,separations=(*state.separations,*alignment),
                        cause=cause,parent=self.token(state))
                    solved,_=self.placement.solve(repair.plans,poses=repair.poses,separations=repair.separations,
                        preserve=False,dimension_floor=repair.dimension_floor,release=owners,release_axes=axes)
                    if solved and changed:
                        projected,_=solved;old=next(f for f in target.features if f.id==changed)
                        new=next(f for f in projected.features if f.id==changed)
                        old_coordinate=pose(old,target.block)[0][third]
                        delta=pose(new,projected.block)[0][third]-old_coordinate
                        rebuilt=[]
                        for f in cuts:
                            u,v,normal,_=FACE_AXES[f.face]
                            if normal!=third and abs(pose(f,target.block)[0][third]-old_coordinate)<1e-6:
                                f=f.model_copy(update={('u' if u==third else 'v'):getattr(f,'u' if u==third else 'v')+delta})
                            rebuilt.append(f)
                        repair=replace(repair,route_overrides={name:rebuilt},override_geometry=digest(signature(projected)))
                        cause['expected_geometric_effect'].update(moved_feature=changed,translation_mm=delta)
                    self.enqueue(repair,first=True)
        constraints=assessment.get('coordination_constraints',[])
        self.measured_repairs(target,state,info['junctions'],constraints)
        rejected={n for n,pool in assessment.get('pools',{}).items() if not pool.get('source_clear')}
        unresolved=assessment.get('unresolved_nets',[])
        self.alternatives(state,rejected or unresolved,source=bool(rejected))
        # Existing measured source witnesses are retained; route entry changes
        # precede moving a rigid source group. All its incident Nets are rechecked.
        for witness in assessment.get('spatial_feedback',[]):
            from ..schema import Feature
            f=Feature.model_validate(witness['drilling']);source=next((x for x in target.features if x.id==witness['source']),None)
            if source is not None:self.measured_repairs(target,state,info['junctions'],[
                dict(features=[f.model_dump(),source.model_dump()],nets=[witness['net']])])

    def diagnostics(self):
        return dict(scope='NEW_AI_GENERATE_ONLY',engineering_plan=self.plan.diagnostics(),
            corridor_domains=self.corridors.diagnostics(),decisions=self.records,
            logical_plans=len(self.seen),evaluated_domains=len(self.records),pending_domains=len(self.queue),
            actual_router_materializations=self.materializations,source_checks=self.source_checks,
            pair_screens=self.pair_screens,cad_errors=self.narrow_errors,
            source_data_or_expression_gaps=self.unexpressed,seconds=time.monotonic()-self.started,
            physical_infeasibility_proven=False,manufacturing_ready=False)


def contact_alternatives(design,name,cuts,contacts,engineering):
    """Re-express a tip-only junction as an actual full-cylinder intersection.

    Uses the production operation-space primitive, including source protection,
    closure, tool reach and occupied plug geometry. The returned candidate must
    again pass local CAD; calculated opening intent never counts as acceptance.
    """
    from ..routing_space import MachiningSpace
    from ..engineering_conditions import effective_net
    net=effective_net(design,next(n for n in design.nets if n.id==name))
    space=MachiningSpace(design,net,engineering.definitions,engineering.threads,engineering.modifiers,
        cache={},tools=engineering.tools)
    by_id={f.id:f for f in cuts}
    for row in contacts:
        if any(n not in by_id for n in row['nodes']):continue  # source windows require a different source-bound plan
        a,b=[by_id[n] for n in row['nodes']];oa,da=pose(a,design.block);ob,db=pose(b,design.block)
        aa=FACE_AXES[a.face][2];ab=FACE_AXES[b.face][2]
        if aa==ab:continue
        junction=[(x+y)/2 for x,y in zip(oa,ob)];junction[aa]=ob[aa];junction[ab]=oa[ab]
        route=list(cuts)
        for f,origin,axis in ((a,oa,aa),(b,ob,ab)):
            _,direction=pose(f,design.block)
            start=list(junction);start[axis]=origin[axis]+direction[axis]*max(f.plug_length if f.plugged else 0,net.diameter)
            options=space.operations(tuple(start),tuple(junction),route)
            candidate=next((r for r in options if any(x.face==f.face and abs(x.u-f.u)<1e-7 and abs(x.v-f.v)<1e-7 and
                x.depth+1e-7>=f.depth for x in r)),None)
            if candidate is None:break
            route=candidate
        else:
            yield route,dict(rule='DIRECT_CONTACT_FULL_CYLINDER_JUNCTION',nodes=row['nodes'],
                actual_before_mm3=row['volume_mm3'],required_mm3=design.rules.minimum_overlap_volume,
                expected_geometric_effect=dict(junction=junction,full_cylinder_crossing=True),
                acceptance='UNVERIFIED_REQUIRES_PRODUCTION_LOCAL_CAD')
