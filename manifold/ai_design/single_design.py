"""One AI-owned work Design, measured process repairs, no layout portfolio.

The symbolic plan determines placement. Rejected cuts are diagnostic evidence,
never seeds for catalog search. Local repairs are transactions on the current
design; each is rebuilt and checked by the same production machining gates.
"""
from dataclasses import replace
import itertools
import math
import time

from .. import timing
from ..kinematics import FACE_AXES, dimensions, pose
from ..engineering_conditions import required_wall, effective_net
from ..routing import terminal_points, _manufacturing_cuts, cylinder_bounds
from .engineering_decisions import EngineeringDecisionController, DecisionState, contact_alternatives
from .engineering_plan import digest
from .placement_solver import Separation
from .initialization import source_extents
from .design_space import signature, source_conflicts, fit_violations


def cut_bounds(design, feature, plan):
    boxes=[cylinder_bounds(c['feature'],design.block,c['start'],c['end'],
        2*max(c['radius_start'],c['radius_end'])) for c in
        _manufacturing_cuts(feature,plan.definitions,plan.threads,plan.modifiers)]
    return [(min(b[a][0] for b in boxes),max(b[a][1] for b in boxes)) for a in range(3)]


class WorkDesign:
    def __init__(self, design, definitions, domain, threads, modifiers, tools):
        with timing.phase('single.compile'):
            self.engineer=EngineeringDecisionController(design,definitions,domain,threads,modifiers,tools)
        # Legacy alternative generators are not used by this controller.
        self.engineer.queue.clear()
        from .execution import cache
        self.engineer.cache=cache()
        self.e=self.engineer.plan;self.corridors=self.engineer.corridors;self.solver=self.engineer.placement
        self.design=design.model_copy(deep=True)
        poses={f.id:(domain.fixed_faces.get(f.id,f.face),domain.fixed_rotations.get(f.id,f.rotation)) for f in design.features
            if f.id in domain.fixed_faces or f.id in domain.fixed_rotations}
        for f in self.design.features:
            if f.id in poses:f.face,f.rotation=poses[f.id]
        self.state=DecisionState({},poses=poses,preserve=False)
        self.required_nets={r['net'] for r in self.e.nets}
        self.routes={};self.operations={};self.junctions={};self.records=[];self.failed_actions=set()
        self.failures={};self.witnesses=[];self.local={};self.reused=[];self.source_ready=False
        self.table={};self.versions=0;self.materialized_nets=[];self.process_gap=None
        self.source_shapes=cache();self.source_contact_cache=cache()
        self.process_choices={};self.process_trials=set();self.arranged=False
        self.choose_processes()

    def choose_processes(self,names=None):
        plans=dict(self.state.plans)
        with timing.phase('single.process_decision'):
            for row in self.e.nets:
                if names is not None and row['net'] not in names:continue
                ranked=self.corridors.ranked(row,self.design)
                self.process_choices[row['net']]=[dict(plan=p.diagnostics(),score=list(score),evidence=why) for score,p,why in ranked]
                if ranked:
                    score,p,why=ranked[0];plans[row['net']]=p
                    self.records.append(dict(kind='ENGINEERING_PROCESS_SELECTION',net=row['net'],selected=p.diagnostics(),
                        basis=why,alternatives_compared=len(ranked),source_geometry=digest([dimensions(self.design.block),[f.model_dump() for f in self.design.features]])))
        self.state=replace(self.state,plans=plans)

    def source_conflicts(self,target):
        """Keep the legacy fast bound for round sources; narrow real contours.

        A rectangular body's enclosing circle is NOT a manufacturing violation.
        This AI-only check uses production cut/envelope/boundary CAD and the
        unchanged production wall/access distances, without building a block.
        """
        broad=set(source_conflicts(target,self.e.definitions,self.e.threads,self.e.modifiers,self.e.domain._placement_cache))
        sources=[f for f in target.features if not f.suppressed and not f.route_net]
        irregular={f.id for f in sources if not self.circular(f,target)}
        if not irregular:return sorted(broad)
        from ..geometry import feature_geometry
        from ..cad_geometry import checked_shape
        from ..machining_predicates import exact_state,ContactState
        def shapes(f):
            definition=self.e.definitions.get(f.definition)
            key=digest([dimensions(target.block),f.model_dump(),definition.model_dump() if definition else None,self.e.threads,self.e.modifiers])
            if key not in self.source_shapes:
                g=feature_geometry(target.model_copy(update=dict(features=[f])),self.e.definitions,self.e.threads,self.e.modifiers)
                installed=list(g[3].values())+[b['shape'] for b in g[6].values()]
                for shape in [*g[0].values(),*installed]:checked_shape(shape,'ai.source_placement',dict(scope='source',feature_ids=[f.id]),allow_empty=False)
                self.source_shapes[key]=(g[0][f.id],installed)
            return key,self.source_shapes[key]
        for a,b in itertools.combinations(sources,2):
            if not {a.id,b.id}&irregular:continue
            token=tuple(sorted((a.id,b.id)));ka,(ca,ia)=shapes(a);kb,(cb,ib)=shapes(b)
            wall=required_wall(target,a,b,definitions=self.e.definitions);gap=target.rules.minimum_access_gap
            context=dict(feature_ids=[a.id,b.id],placement_stage='AI_SOURCE_LAYOUT')
            with timing.phase('single.source_envelopes'):
                violation=exact_state((ka,'cut'),ca,(kb,'cut'),cb,wall,self.source_contact_cache,context=context)==ContactState.VIOLATION
                left=[(('cut',),ca)]+[(('installed',i),shape) for i,shape in enumerate(ia)]
                right=[(('cut',),cb)]+[(('installed',i),shape) for i,shape in enumerate(ib)]
                violation=violation or any(exact_state((ka,ki),x,(kb,kj),y,gap,self.source_contact_cache,context=context)==ContactState.VIOLATION
                    for ki,x in left for kj,y in right if ki!=('cut',) or kj!=('cut',))
            if violation:broad.add(token)
            else:broad.discard(token)
        return sorted(broad)

    def bounds(self,f,d=None):return cut_bounds(d or self.design,f,self.e)

    def circular(self,f,target=None):
        d=target or self.design;o,_=pose(f,d.block);axes=FACE_AXES[f.face][:2]
        definition=self.e.definitions.get(f.definition)
        round_boundary=not definition or all(b.circle and abs(b.circle[0])+abs(b.circle[1])<1e-7 for b in definition.boundaries)
        return round_boundary and not f.direction and all(all(abs(pose(c['feature'],d.block)[0][a]-o[a])<1e-7 for a in axes)
            for c in _manufacturing_cuts(f,self.e.definitions,self.e.threads,self.e.modifiers))

    def fit(self,target):
        """Physical projected source bounds; production source CAD still gates.

        The old circular fit heuristic remains unchanged for explicit legacy
        tools. It is not a manufacturing rule for a rectangular source contour.
        """
        bad=[];sizes=dimensions(target.block)
        for a,size in enumerate(sizes):
            if target.constraints.envelope_min and size<target.constraints.envelope_min[a]-1e-7:bad.append(['envelope_min',a])
            if target.constraints.envelope_max and size>target.constraints.envelope_max[a]+1e-7:bad.append(['envelope_max',a])
        for f in target.features:
            if f.suppressed or f.route_net:continue
            ext=source_extents(target,f,self.e.definitions,self.e.threads,self.e.modifiers);origin,_=pose(f,target.block)
            for axis,(lo,hi) in ext['projected_supports'].items():
                if origin[axis]+lo<ext['wall']-1e-7 or origin[axis]+hi>sizes[axis]-ext['wall']+1e-7:
                    bad.append(['source_projected_bounds',f.id,axis,lo,hi,ext['wall']])
            axis=FACE_AXES[f.face][2]
            if ext['depth']+ext['wall']>sizes[axis]+1e-7:bad.append(['source_depth',f.id,axis])
        return bad

    def spacing(self):
        """Preserve the selected two-dimensional source arrangement.

        No opposite-depth sum: PlacementSolver imposes each source's own depth;
        opposite/cross-face overlap adds a measured separation only if present.
        """
        rows=self.e.features;index={r['feature']:i for i,r in enumerate(rows)}
        incident=lambda f:[n for n in self.e.nets if any(m.split(':')[0]==f.id for m in n['members'])]
        ordered=sorted((f for f in self.design.features if f.id in index),key=lambda f:(
            f.id in self.e.domain.movable,
            -len(self.e.domain.fixed_positions.get(f.id,{}))-int(f.id in self.e.domain.fixed_faces),
            -len(incident(f)),-len(next(r for r in rows if r['feature']==f.id)['windows']),
            -source_extents(self.design,f,self.e.definitions,self.e.threads,self.e.modifiers)['radius'],index[f.id]))
        self.order=[f.id for f in ordered];separations=[];spacing=[]
        for a,b in itertools.combinations(ordered,2):
            if a.face!=b.face:
                if not self.arranged:continue
                # Keep a measured cross-face source separation when origins
                # and stock become variables in the same constraint system.
                ba,bb=self.bounds(a),self.bounds(b)
                gap=max(required_wall(self.design,a,b,definitions=self.e.definitions),self.design.rules.minimum_access_gap)
                events=[]
                for axis in range(3):
                    for low,high,bl,bh in ((a,b,ba,bb),(b,a,bb,ba)):
                        if bl[axis][1]+gap<=bh[axis][0]+1e-7:
                            distance=bl[axis][1]-pose(low,self.design.block)[0][axis]-(bh[axis][0]-pose(high,self.design.block)[0][axis])+gap
                            events.append((bh[axis][0]-bl[axis][1]-gap,axis,low,high,distance))
                if events:
                    _,axis,low,high,distance=max(events,key=lambda r:(r[0],-r[1]))
                    reason=dict(rule='CROSS_FACE_SOURCE_SUPPORT_SEPARATION',features=[low.id,high.id],axis=axis,
                        required=distance,gap=gap,measured_bounds=[ba,bb],status='SUFFICIENT_DOMAIN_RECHECK_REQUIRED')
                    separations.append(Separation(self.solver.origin(high.id,axis),self.solver.origin(low.id,axis),distance,reason));spacing.append(reason)
                continue
            ra=source_extents(self.design,a,self.e.definitions,self.e.threads,self.e.modifiers)
            rb=source_extents(self.design,b,self.e.definitions,self.e.threads,self.e.modifiers)
            common={n['net'] for n in incident(a)}&{n['net'] for n in incident(b)}
            axes=FACE_AXES[a.face][:2]
            preferred=[self.state.plans[n].spine_axis for n in self.corridors.order if n in common]
            # Select a separating projection from the actual arrangement.
            # All pairs on a face need not have the same ordering axis.
            def slack(axis):
                return abs(pose(a,self.design.block)[0][axis]-pose(b,self.design.block)[0][axis])-(
                    max(abs(v) for v in ra['projected_supports'][axis])+max(abs(v) for v in rb['projected_supports'][axis]))
            axis=max(axes,key=lambda axis:(slack(axis),axis in preferred,-axis))
            # Preserve a physically separated authored/soft row's ordering.
            low,high=sorted((a,b),key=lambda f:(pose(f,self.design.block)[0][axis],self.order.index(f.id)))
            rlo,rhi=(ra,rb) if low==a else (rb,ra)
            gap=max(required_wall(self.design,a,b,definitions=self.e.definitions),self.design.rules.minimum_access_gap)
            circular=self.circular(a,self.design) and self.circular(b,self.design)
            olo=pose(low,self.design.block)[0][axis];ohi=pose(high,self.design.block)[0][axis]
            left=rlo['projected_supports'][axis][1]
            right=-rhi['projected_supports'][axis][0]
            distance=(ra['radius']+rb['radius'] if circular else left+right)+gap
            reason=dict(rule='INITIAL_ENGINEERING_SPACING',features=[low.id,high.id],axis=axis,
                formula='Ri + Rj + Gij' if circular else 'projected upper support - projected lower support + Gij',
                radii=[ra['radius'],rb['radius']],supports=[left,right],gap=gap,required=distance,
                source='executable source cuts/installation envelope + production required_wall/minimum_access_gap')
            separations.append(Separation(self.solver.origin(high.id,axis),self.solver.origin(low.id,axis),distance,reason))
            spacing.append(reason)
        self.table=dict(placement_order=self.order,spacing=spacing,
            depth_rule='Per-source full depth + production back wall; opposing depths are combined only for overlapping projections',
            groups=self.groups(),unknowns=self.e.diagnostics()['unknowns'])
        return tuple(separations)

    def groups(self):
        # Direct hyperedge groups overlap deliberately: transitive connectivity
        # does not impose an all-source packing row.
        return [r['features'] for r in self.e.associations()]

    def solve(self,state,*,working=None,fixed=None):
        with timing.phase('single.coordinates'):
            return self.solver.solve(state.plans,poses=state.poses,separations=state.separations,
                preserve=state.preserve,dimension_floor=state.dimension_floor,release=state.release,
                release_axes=state.release_axes,working=working or self.design,fixed_junctions=fixed,use_projected=True)

    def necessary_stock(self):
        """Retain necessary closure/stop space even if a process domain cycles.

        The two inequalities on a source-backed axial junction imply this
        thickness. It is a necessary lower bound, never a corridor approval.
        """
        floor=list(self.design.constraints.envelope_min or (1,1,1));facts=[]
        by_id={f.id:f for f in self.design.features}
        for row in self.e.nets:
            plan=self.state.plans.get(row['net'])
            if not plan:continue
            for member in plan.axial_members:
                profile=self.corridors.profile_access[member];axis=FACE_AXES[by_id[member.split(':')[0]].face][2]
                margin=row['diameter']/2+row['wall'];head=profile['plug_length']+margin
                stop=-profile['depth_minus_stock']+margin;required=head+stop
                floor[axis]=max(floor[axis],required)
                facts.append(dict(rule='AXIAL_PLUG_AND_SOURCE_STOP_STOCK',net=row['net'],member=member,axis=axis,
                    occupied_depth=profile['plug_length'],bore_radius=row['diameter']/2,wall=row['wall'],
                    source_stop_offset=profile['depth_minus_stock'],minimum_dimension=required,
                    formula='occupied_depth + radius + wall - source_stop_offset + radius + wall',
                    evidence=profile['evidence']))
        return tuple(floor),facts

    def initialize(self):
        def adjustable(f):
            locks=self.e.domain.fixed_positions.get(f.id,{})
            free=any(field not in locks and 'xyz'[axis] not in locks for axis,field in zip(FACE_AXES[f.face][:2],('u','v')))
            return f.kind=='cavity' and f.id in self.e.domain.movable and (len(self.e.domain.faces(f))>1 or free)
        if any(adjustable(f) for f in self.design.features):
            from .source_arrangement import arrange
            before=self.design.model_copy(deep=True)
            ok,decisions=arrange(self)
            self.records.append(dict(kind='HYPERGRAPH_SOURCE_ARRANGEMENT',decisions=decisions,constructed=ok))
            if not ok:self.design=before
            else:
                self.arranged=True
                self.state=replace(self.state,poses={f.id:(f.face,f.rotation) for f in self.design.features
                    if f.id in self.e.domain.movable or f.id in self.state.poses},dimension_floor=dimensions(self.design.block))
                self.choose_processes()
        self.state=replace(self.state,separations=self.spacing())
        solved,detail=self.replan_constraints()
        if not solved:
            self.process_gap=detail
            # A process-domain contradiction does not erase a valid source Draft.
            floor,stock_facts=self.necessary_stock()
            floor=tuple(max(a,b) for a,b in zip(floor,self.state.dimension_floor or (1,1,1)))
            self.state=replace(self.state,dimension_floor=floor)
            self.table['necessary_stock']=stock_facts
            solved,source_detail=self.solver.solve({},poses=self.state.poses,separations=self.state.separations,
                dimension_floor=floor,use_projected=True,working=self.design)
            self.records.append(dict(kind='SOURCE_ONLY_CONSTRAINTS',constraints=source_detail))
            if not solved:
                self.records.append(dict(kind='SOURCE_LAYOUT_UNRESOLVED',constraints=source_detail));return False
            target,_=solved;points=terminal_points(target,self.e.definitions)
            junctions={n['net']:tuple(sum(points[m][a] for m in n['members'])/len(n['members']) for a in range(3)) for n in self.e.nets}
            solved=target,junctions
        self.design,self.junctions=solved
        # Cross-face machining is screened in 3D, never by a circle formula.
        clashes=self.source_conflicts(self.design)
        seen=set()
        while clashes and tuple(clashes) not in seen:
            seen.add(tuple(clashes));repaired=self.source_separation(clashes)
            if not repaired:break
            self.design,self.junctions=repaired
            clashes=self.source_conflicts(self.design)
        violations=self.fit(self.design)
        clashes=self.source_conflicts(self.design)
        self.source_ready=not violations and not clashes
        if self.process_gap:
            points=terminal_points(self.design,self.e.definitions)
            self.junctions={n['net']:tuple(sum(points[m][a] for m in n['members'])/len(n['members']) for a in range(3)) for n in self.e.nets}
        self.records.append(dict(kind='INITIAL_SOURCE_CHECK',violations=violations,conflicts=clashes,source_ready=self.source_ready))
        active_detail=next((r['actual'] for r in reversed(self.records) if r['kind']=='SOURCE_REPAIR'),source_detail if self.process_gap else detail)
        self.table.update(dimensions=list(dimensions(self.design.block)),features=[dict(
            feature=f.id,definition=f.definition,face=f.face,rotation=f.rotation,u=f.u,v=f.v,
            extents=source_extents(self.design,f,self.e.definitions,self.e.threads,self.e.modifiers),
            windows=[dict(member=m,point=p) for m,p in terminal_points(self.design,self.e.definitions).items() if m.split(':')[0]==f.id],
            constraints=[c for c in active_detail.get('constraints',[]) if c['cause'].get('feature')==f.id or f.id in c['cause'].get('features',[])])
            for f in self.design.features],coordinate_constraints=active_detail,process_constraints=detail,process_gap=self.process_gap,
            dimension_basis='SOURCE_AND_NECESSARY_PROCESS_BOUNDS_FULL_DOMAIN_UNRESOLVED' if self.process_gap else 'SOURCE_AND_MACHINING_CORRIDOR_CONSTRAINTS')
        return self.source_ready

    def replan_constraints(self):
        """A minimal contradictory cycle is a process decision, not no-layout.

        Change one implicated machining domain on this work Design, propagate,
        and continue the next actual cycle. No Cartesian layout collection and
        no relaxed inequalities. The finite set of local process transitions
        prevents repeating a prior axis/order decision under identical facts.
        """
        solved,detail=self.solve(self.state)
        self.records.append(dict(kind='INITIAL_CONSTRAINT_PROPAGATION',constraints=detail))
        seen={digest({n:p.diagnostics() for n,p in self.state.plans.items()})}
        clauses=[]
        while not solved:
            cycle=detail.get('cycle',[])
            cycle_keys={digest(r) for r in cycle};rules={r.get('rule') for r in cycle}
            implicated={n for r in cycle for n in ([r['net']] if 'net' in r else r.get('nets',[]))}
            # This selected difference-domain cycle depends on these process
            # assignments and this source geometry. Retain that conditional
            # proof; never ban a process merely because it failed beside an
            # earlier, different assignment of the OTHER Nets.
            condition={n:digest(self.state.plans[n].diagnostics()) for n in implicated if n in self.state.plans}
            if condition and condition not in clauses:clauses.append(condition)
            alternatives=[]
            for name in self.corridors.order:
                if name not in implicated:continue
                row=next(r for r in self.e.nets if r['net']==name);old=self.state.plans[name]
                ranked=self.corridors.ranked(row,self.design)
                if 'WINDOW_LAYER' in rules and old.planar:
                    ranked=[((0,),replace(old,planar=False),dict(reason='Remove the planar equality implicated by actual rigid window offsets'))]
                elif 'COAXIAL_WINDOW_ALIGNMENT' in rules and old.access in ('coaxial','aligned-window'):
                    ranked=[r for r in ranked if r[1].access=='window' and not r[1].planar]
                elif 'SHARED_WINDOW_ESCAPE_ORDER' in rules:
                    ranked=[r for r in ranked if (r[1].spine_axis,r[1].layer_axis,r[1].orders)!=(old.spine_axis,old.layer_axis,old.orders)]
                elif 'SOURCE_BACKED_AXIAL_INTERVAL' in rules:
                    ranked=[r for r in ranked if not r[1].planar and (r[1].spine_axis!=old.spine_axis or r[1].axial_members!=old.axial_members)]
                if 'RADIAL_BRANCH_SOURCE_COLUMNS' in rules and old.reserve_columns:
                    ranked.append(((float('inf'),),replace(old,reserve_columns=False),dict(
                        reason='Replace contradictory sufficient all-source column ordering with full production machining screening',
                        safety_gate='Every source-protected cut, entry, plug and third-party route remains mandatory')))
                equivalent=set()
                for score,p,basis in ranked:
                    if p==old:continue
                    # An entry flip cannot alter a window-layer/escape cycle.
                    effect=replace(p,entry=old.entry).diagnostics() if not any('ENTRY' in (r or '') for r in rules) else p.diagnostics()
                    effect=digest(effect)
                    if effect in equivalent:continue
                    equivalent.add(effect)
                    plans={**self.state.plans,name:p};token=digest({n:q.diagnostics() for n,q in plans.items()})
                    if any(all(digest(plans[n].diagnostics())==value for n,value in clause.items()) for clause in clauses):continue
                    transition=digest([self.engineer.token(self.state),signature(self.design),name,p.diagnostics(),cycle])
                    if token in seen or transition in self.process_trials:continue
                    self.process_trials.add(transition)
                    state=replace(self.state,plans=plans)
                    result,why=self.solve(state)
                    # An escape cycle requires an axis/order/layer change;
                    # toggling planar alone cannot remove its positive edges.
                    same_escape=(p.spine_axis,p.layer_axis,p.orders)==(old.spine_axis,old.layer_axis,old.orders)
                    residual=why.get('cycle',[])
                    metric=(result is None,len(cycle_keys&{digest(r) for r in residual}),
                        sum(r.get('rule')=='SHARED_WINDOW_ESCAPE_ORDER' for r in residual),len(residual),same_escape,score)
                    alternatives.append((metric,state,result,why,name,p,basis,token))
                    if result:break
            if not alternatives:
                detail={**detail,'uncovered_process_domain':dict(nets=sorted(implicated),
                    reason='No unused local axis/entry/window-order transition in the supported production junction representation',
                    physical_infeasibility_proven=False)};break
            _,state,result,why,name,p,basis,token=min(alternatives,key=lambda r:r[0])
            if not result and cycle_keys=={digest(r) for r in why.get('cycle',[])}:
                detail={**detail,'uncovered_process_domain':dict(nets=sorted(implicated),
                    reason='Available local process transitions do not remove the measured contradictory relation',
                    physical_infeasibility_proven=False)};break
            self.records.append(dict(kind='CONTRADICTORY_PROCESS_REPLAN',cycle=cycle,net=name,
                conditional_assignments=condition,local_domains_checked=len(alternatives),
                dependency=self.engineer.token(self.state),
                previous=self.state.plans[name].diagnostics(),selected=p.diagnostics(),basis=basis,
                affected_nets=[name],source_moved=False,after=why,status='DOMAIN_SOLVED_REQUIRES_PRODUCTION_CHECK' if result else 'NEXT_CONDITIONAL_CYCLE'))
            self.state=state;seen.add(token);solved,detail=result,why
        self.process_gap=None if solved else detail
        return solved,detail

    def source_separation(self,pairs):
        by_id={f.id:f for f in self.design.features}
        witnesses=[dict(nets=[],features=[by_id[k].model_dump() for k in pair],failures=[['source_placement',*pair]]) for pair in pairs]
        for state,cause in self.separation_actions(witnesses):
            def solve_local():
                if self.process_gap:
                    return self.solver.solve({},working=self.design,separations=state.separations,
                        dimension_floor=state.dimension_floor,release=state.release,release_axes=state.release_axes,use_projected=True)
                return self.solve(state,working=self.design)
            solved,detail=solve_local()
            if solved:
                target,_=solved
                remaining=self.source_conflicts(target)
                # A transverse source translation may meet an opposite-side
                # source in the same column. Propagate its measured BACK wall
                # to that stock dimension before committing any movement.
                # This is one transaction, not a competing layout candidate.
                growth=[]
                for pair in sorted(set(remaining)-set(pairs)):
                    fs=[next(f for f in target.features if f.id==key) for key in pair]
                    for far,other in (fs,fs[::-1]):
                        axis,sign=FACE_AXES[far.face][2:]
                        if sign!=-1 or axis not in self.e.domain.dimension_axes or FACE_AXES[other.face][2]==axis:continue
                        fb,ob=self.bounds(far,target),self.bounds(other,target)
                        fo=pose(far,target.block)[0][axis];oo=pose(other,target.block)[0][axis]
                        wall=required_wall(target,far,other,definitions=self.e.definitions)
                        need=ob[axis][1]-oo-(fb[axis][0]-fo)+wall+.01
                        why=dict(rule='OPPOSITE_SOURCE_BACK_WALL_PROPAGATION',features=[far.id,other.id],axis=axis,
                            measured_bounds=[fb,ob],wall=wall,required=need,
                            source='new measured cross-face overlap in the current local transaction')
                        growth.append(Separation(self.solver.origin(far.id,axis),self.solver.origin(other.id,axis),need,why));break
                if growth:
                    state=replace(state,separations=(*state.separations,*growth));solved,detail=solve_local()
                    if not solved:continue
                    target,_=solved
                    remaining=self.source_conflicts(target)
                if len(remaining)<len(pairs) and not set(remaining)-set(pairs):
                    self.state=state;self.records.append(dict(kind='SOURCE_REPAIR',cause=cause,actual=detail,
                        stock_growth_constraints=[s.reason for s in growth]));return solved
        return None

    def materialize(self,affected=None):
        affected=set(self.state.plans) if affected is None else set(affected)
        with timing.phase('single.materialization'):
            changed=self.corridors.materialize(self.design,self.state.plans,self.junctions,self.engineer.cache,
                net_ids=affected,operation_records=self.operations)
        for name in affected:
            self.routes.pop(name,None);self.local.pop(name,None)
        self.routes.update(changed);self.materialized_nets.append(sorted(affected));self.versions+=1

    def precheck(self):
        # No catalogs and no path search. Production caches are dependency-bound.
        with timing.phase('single.precheck'):
            self.failures,self.witnesses=self.engineer.machining_screen(self.design,self.routes)
        for n in self.required_nets-set(self.routes):self.failures[n]=[['PROCESS_NOT_MATERIALIZED' if n in self.state.plans else 'PROCESS_NOT_EXPRESSIBLE',n]]
        self.records.append(dict(kind='PRODUCTION_MACHINING_PRECHECK',version=self.versions,
            failures=self.failures,witnesses=self.witnesses,
            measurements=[dict(key=repr(k),value=v) for k,v in self.engineer.cache.get('local_measurements',{}).items()],
            expensive_router_entered=False))
        return not self.failures

    def separation_actions(self,witnesses):
        choices=[]
        from ..schema import Feature
        normalized=[]
        for witness in witnesses:
            fs=[Feature.model_validate(f) for f in witness['features']]
            if len(fs)==2 and any(r[0]=='plug_cut' for r in witness.get('failures',[])):
                from ..machining_predicates import plug_violate
                for plug,other in (fs,fs[::-1]):
                    if plug.plugged and any(plug_violate(plug,c,self.design,self.e.definitions,self.e.threads,self.e.modifiers,self.engineer.cache)
                        for c in _manufacturing_cuts(other,self.e.definitions,self.e.threads,self.e.modifiers)):
                        normalized.append({**witness,'occupied_feature':plug.id})
            else:normalized.append(witness)
        for witness in normalized:
            fs=[Feature.model_validate(f) for f in witness['features']]
            if len(fs)<2:continue
            a,b=fs[:2];ba,bb=self.bounds(a),self.bounds(b)
            rules={r[0] for r in witness.get('failures',[])};envelopes={}
            if rules&{'plug_cut','installation_access'}:
                from ..machining_predicates import feature_shape,_bounds
                for f in (a,b):
                    kind='plug' if 'plug_cut' in rules and f.id==witness.get('occupied_feature') else 'envelope' if 'installation_access' in rules else None
                    if kind:
                        _,shape=feature_shape(f,self.design,self.e.definitions,self.e.threads,self.e.modifiers,kind,self.engineer.cache)
                        envelopes[f.id]=kind
                        if f==a:ba=_bounds(shape)
                        else:bb=_bounds(shape)
            wall=self.design.rules.minimum_access_gap if 'installation_access' in rules else 0 if 'plug_cut' in rules else required_wall(self.design,a,b,definitions=self.e.definitions)
            for axis in range(3):
                for low,high,blo,bhi in ((a,b,ba,bb),(b,a,bb,ba)):
                    lv,lc=self.engineer._bound(self.design,self.junctions,low,axis,blo[axis][1])
                    hv,hc=self.engineer._bound(self.design,self.junctions,high,axis,bhi[axis][0])
                    if lv==hv:continue
                    owners=[f.id for f in self.design.features if f.id in self.e.domain.movable and
                        axis!=FACE_AXES[f.face][2] and self.solver.origin(f.id,axis) in (lv,hv) and
                        not ({'xyz'[axis],'u' if FACE_AXES[f.face][0]==axis else 'v'}&
                             self.e.domain.fixed_positions.get(f.id,{}).keys())]
                    # A junction may move without moving any source.
                    lanes=[n for n in self.state.plans if self.solver.lane(n,axis) in (lv,hv)]
                    if not owners and not lanes:continue
                    need=lc-hc+wall+.01
                    cause=dict(rule='MEASURED_COMPLETE_CUT_SEPARATION',features=[low.id,high.id],nets=witness['nets'],axis=axis,
                        before=dict(low_upper=blo[axis][1],high_lower=bhi[axis][0],wall=wall),
                        required=need,owners=owners,lanes=lanes,engineering_rules=sorted(rules),
                        measured_envelopes=envelopes,status='CONDITIONAL_REBUILD_REQUIRED')
                    cut=Separation(hv,lv,need,cause)
                    if cut in self.state.separations:continue
                    # Direct/aligned processes constrain their source origins
                    # together. Release the coupled coordinates in the SAME
                    # transaction, never translate a shared cavity per Net.
                    release=set(owners)
                    for row in self.e.nets:
                        if self.state.plans[row['net']].access in ('coaxial','aligned-window') and any(m.split(':')[0] in release for m in row['members']):
                            release.update(m.split(':')[0] for m in row['members'] if m.split(':')[0] in self.e.domain.movable)
                    state=replace(self.state,separations=(*self.state.separations,cut),preserve=False,
                        dimension_floor=dimensions(self.design.block),release=tuple(sorted(release)),
                        release_axes={f.id:((axis,) if f.id in release else ()) for f in self.design.features})
                    choices.append((max(0,blo[axis][1]+wall+.01-bhi[axis][0]),state,cause))
        yield from ((state,cause) for _,state,cause in sorted(choices,key=lambda r:r[0]))

    def affected(self,before,after,plans):
        previous={f.id:f for f in before.features};current={f.id:f for f in after.features}
        changed={key for key in previous if previous[key]!=current.get(key)}
        affected=set(plans)
        affected.update(n['net'] for n in self.e.nets if any(m.split(':')[0] in changed for m in n['members']))
        if dimensions(before.block)!=dimensions(after.block):return set(self.state.plans),changed
        # A moved source can obstruct an unrelated Net: screen its swept bounds.
        old={f.id:f for f in before.features};new={f.id:f for f in after.features}
        def occupied(f,target):
            bounds=self.bounds(f,target);o,_=pose(f,target.block)
            ext=source_extents(target,f,self.e.definitions,self.e.threads,self.e.modifiers)
            for axis,(lo,hi) in ext['projected_supports'].items():bounds[axis]=(min(bounds[axis][0],o[axis]+lo),max(bounds[axis][1],o[axis]+hi))
            definition=self.e.definitions.get(f.definition)
            height=max([definition.clearance_height,*[b.height for b in definition.boundaries]]) if definition else f.clearance_height
            axis,sign=FACE_AXES[f.face][2:];outside=o[axis]-sign*height
            bounds[axis]=(min(bounds[axis][0],outside),max(bounds[axis][1],outside))
            return bounds
        for owner in changed:
            a=occupied(old[owner],before);b=occupied(new[owner],after)
            swept=[(min(a[i][0],b[i][0]),max(a[i][1],b[i][1])) for i in range(3)]
            for name,cuts in self.routes.items():
                for f in cuts:
                    box=self.bounds(f,before);gap=required_wall(after,f,new[owner],definitions=self.e.definitions)+after.rules.minimum_access_gap
                    if all(box[i][1]+gap>=swept[i][0] and box[i][0]-gap<=swept[i][1] for i in range(3)):affected.add(name);break
        return affected,changed

    def repair(self):
        """One causally selected transaction; no next global layout."""
        if self.process_gap:
            before=self.state
            solved,detail=self.replan_constraints()
            if solved:
                target,junctions=solved
                if not self.fit(target) and not self.source_conflicts(target):
                    affected,owners=self.affected(self.design,target,{n for n in self.state.plans if self.state.plans[n]!=before.plans[n]})
                    self.design,self.junctions=target,junctions;self.materialize(affected);self.precheck()
                    self.records.append(dict(kind='PROCESS_DOMAIN_RECOVERED',affected_nets=sorted(affected),moved_sources=sorted(owners)))
                    return True
            self.records.append(dict(kind='PROCESS_EXPRESSION_UNRESOLVED',constraints=detail,manufacturing_ready=False))
            return False
        if any(f[0]=='CAD_EVALUATION_ERROR' for rows in self.failures.values() for f in rows):return False
        # Entry and coordinate outcomes also depend on every retained cut.
        # An earlier third-party route must not veto a newly safe transaction.
        context=self.repair_dependency()
        # Full external entry change first. Only failing Net processes change.
        for name in self.corridors.order:
            if name not in self.failures:continue
            p=self.state.plans[name]
            for axis in sorted({FACE_AXES[f.face][2] for f in self.routes.get(name,[])}):
                current=dict(p.entry_axes).get(axis,p.entry)
                mode='positive' if current!='positive' else 'negative'
                updated=replace(p,entry_axes=tuple(sorted({**dict(p.entry_axes),axis:mode}.items())))
                cause=dict(rule='CHANGE_MEASURED_ENTRY',net=name,axis=axis,entry=mode,failures=self.failures[name])
                token=digest([context,name,updated.diagnostics()])
                if token in self.failed_actions:continue
                self.failed_actions.add(token)
                old=self.routes.get(name);old_operations=self.operations.get(name)
                candidate=self.corridors.materialize(self.design,{name:updated},self.junctions,self.engineer.cache,
                    net_ids={name},operation_records=self.operations).get(name)
                if not candidate or candidate==old:
                    if old_operations is None:self.operations.pop(name,None)
                    else:self.operations[name]=old_operations
                    continue
                routes={**self.routes,name:candidate}
                with timing.phase('single.local_repair_precheck'):
                    failures,witnesses=self.engineer.machining_screen(self.design,routes)
                # Only accept an entry repair if this Net passes ALL production
                # source/plug/third-party pair gates. Other failures stay intact.
                self.records.append(dict(kind='LOCAL_ENTRY_TRANSACTION',cause=cause,after=failures,
                    committed=name not in failures,affected_nets=[name],source_moved=False))
                if name not in failures:
                    self.state=replace(self.state,plans={**self.state.plans,name:updated});self.routes=routes
                    self.failures,self.witnesses=failures,witnesses;self.local.pop(name,None)
                    self.materialized_nets.append([name]);self.versions+=1;return True
                if old_operations is None:self.operations.pop(name,None)
                else:self.operations[name]=old_operations
        # Compare a measured alternative main axis before moving any source.
        # One representative per distinct process axis, not a Catalog family
        # or a new global layout. Every complete cut is screened against ALL
        # retained sources, plugs and third-party routes.
        for row in self.e.nets:
            name=row['net']
            if name not in self.failures:continue
            represented={(self.state.plans[name].spine_axis,self.state.plans[name].side)}
            for _,p,basis in self.corridors.ranked(row,self.design):
                if (p.spine_axis,p.side) in represented:continue
                represented.add((p.spine_axis,p.side))
                token=digest([context,name,p.diagnostics(),'measured-process'])
                if token in self.failed_actions:continue
                self.failed_actions.add(token)
                state=replace(self.state,plans={**self.state.plans,name:p},preserve=True)
                solved,detail=self.solve(state,working=self.design,fixed={n:j for n,j in self.junctions.items() if n!=name})
                if not solved:
                    self.records.append(dict(kind='PROCESS_AXIS_REJECTED',net=name,selected=p.diagnostics(),actual=detail));continue
                target,junctions=solved;operations=dict(self.operations)
                candidate=self.corridors.materialize(target,state.plans,junctions,self.engineer.cache,net_ids={name},operation_records=operations).get(name)
                if not candidate:continue
                routes={**self.routes,name:candidate}
                failures,witnesses=self.engineer.machining_screen(target,routes)
                improved=len(failures.get(name,[]))<len(self.failures.get(name,[])) and not set(failures)-set(self.failures) and not any(
                    f[0]=='CAD_EVALUATION_ERROR' for rows in failures.values() for f in rows)
                self.records.append(dict(kind='MEASURED_PROCESS_AXIS_TRANSACTION',net=name,basis=basis,selected=p.diagnostics(),
                    before=self.failures[name],after=failures,committed=improved,source_moved=False,affected_nets=[name]))
                if improved:
                    self.state=replace(state,preserve=False);self.junctions=junctions;self.routes,self.operations=routes,operations
                    self.failures,self.witnesses=failures,witnesses;self.local.pop(name,None)
                    self.materialized_nets.append([name]);self.versions+=1;return True
        # Measurements select a local coordinate inequality, not +/- nudges.
        for state,cause in self.separation_actions(self.witnesses):
            token=digest([context,cause])
            if token in self.failed_actions:continue
            self.failed_actions.add(token)
            release=set(state.release);incident={n['net'] for n in self.e.nets if any(m.split(':')[0] in release for m in n['members'])}
            active=incident|set(cause['nets'])|set(cause['lanes'])
            fixed={n:p for n,p in self.junctions.items() if n not in active}
            solved,detail=self.solve(state,working=self.design,fixed=fixed)
            if not solved:
                self.records.append(dict(kind='LOCAL_COORDINATE_ROLLBACK',cause=cause,actual=detail));continue
            target,junctions=solved
            if self.fit(target) or self.source_conflicts(target):continue
            affected,owners=self.affected(self.design,target,active)
            # Commit only a measured process improvement, never a competing
            # layout chosen by overall coverage. Unrelated positions stay fixed.
            routes={n:fs for n,fs in self.routes.items() if n not in affected}
            operations=dict(self.operations)
            routes.update(self.corridors.materialize(target,state.plans,junctions,self.engineer.cache,
                net_ids=affected,operation_records=operations))
            failures,witnesses=self.engineer.machining_screen(target,routes)
            old_bad={tuple(f) for n in active for f in self.failures.get(n,[])}
            new_bad={tuple(f) for n in active for f in failures.get(n,[])}
            introduced=set(failures)-set(self.failures)
            improved=bool(old_bad-new_bad) and not introduced and len(new_bad)<len(old_bad) and not any(
                f[0]=='CAD_EVALUATION_ERROR' for rows in failures.values() for f in rows)
            self.records.append(dict(kind='LOCAL_COORDINATE_TRANSACTION',cause=cause,actual=detail,after=failures,
                affected_nets=sorted(affected),moved_sources=sorted(owners),committed=improved,
                unchanged_nets=sorted(set(self.routes)-affected),new_failure_nets=sorted(introduced)))
            if improved:
                self.design,self.junctions,self.state=target,junctions,state
                self.routes,self.operations,self.failures,self.witnesses=routes,operations,failures,witnesses
                for n in affected:self.local.pop(n,None)
                self.materialized_nets.append(sorted(affected));self.versions+=1;return True
        return False

    def repair_dependency(self):
        return digest([self.e.dependency,self.engineer.token(self.state),signature(self.design),self.junctions,
            {n:[f.model_dump() for f in cuts] for n,cuts in self.routes.items()}])

    def diagnostics(self):
        return dict(scope='NEW_AI_GENERATE_ONLY',mode='SINGLE_WORK_DESIGN',engineering_plan=self.e.diagnostics(),
            initial_calculation=self.table,selected_processes={n:p.diagnostics() for n,p in self.state.plans.items()},
            process_comparisons=self.process_choices,
            operations=self.operations,actual_drillings={n:[f.model_dump(mode='json') for f in fs] for n,fs in self.routes.items()},
            junctions=self.junctions,decisions=self.records,failures=self.failures,local_admission=self.local,
            source_layout_ready=self.source_ready,process_gap=self.process_gap,versions=self.versions,
            materialized_net_batches=self.materialized_nets,global_layout_queue=0,catalog_searches=0,deep_labels=0,
            cache_lookups=dict(machining=getattr(self.engineer.cache,'counts',None),
                source_shapes=getattr(self.source_shapes,'counts',None),source_contacts=getattr(self.source_contact_cache,'counts',None),
                meaning='Dictionary lookups, not unique CAD operations or saved seconds'),
            actual_router_materializations=len(self.materialized_nets),timing=timing.summary(),
            manufacturing_ready=False,physical_infeasibility_proven=False)

    def repair_contact(self,name,admission,local_gate,core):
        """A deficient direct contact owes its own opening, even if connected.

        Re-express that junction as complete production operations, recheck ALL
        source/plug/pair gates, then obtain fresh dependency-bound local CAD.
        CAD errors retain UNKNOWN; no declarations are invented here.
        """
        contacts=(admission.get('connectivity') or {}).get('insufficient_direct_contacts',[])
        for route,cause in contact_alternatives(self.design,name,self.routes[name],contacts,self.e):
            proposed={**self.routes,name:route}
            failures,_=self.engineer.machining_screen(self.design,proposed)
            record=dict(kind='LOCAL_DIRECT_OPENING_TRANSACTION',cause=cause,after=failures,committed=False,affected_nets=[name])
            self.records.append(record)
            if name in failures:continue
            option=dict(key='measured-direct-junction:'+name,route=route,risk=0)
            net=effective_net(self.design,next(n for n in self.design.nets if n.id==name))
            revised={**core,name:option}
            result=local_gate.check(self.design,net,option,revised,self.e.definitions,self.e.threads,self.e.modifiers,self.e.tools)
            record['local_cad']=result
            if result['status']!='LOCAL_EXACT_ADMISSIBLE':continue
            self.routes[name]=route;self.local[name]=result;core[name]=option
            self.materialized_nets.append([name]);self.versions+=1;record['committed']=True
            return True
        return False
