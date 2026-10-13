"""Joint AI-owned placement, stock and shared-Router search.

Analytic layouts schedule disposable Exact workers; only real engineering and
STEP checks can accept a layout. Nothing writes or revises a Model project.
"""
from pathlib import Path
import heapq
import itertools
import math
import time

from ..schema import Design,Feature
from ..kinematics import dimensions
from ..engineering_conditions import effective_net
from .design_space import signature,source_conflicts,topology_cost,actions,fit_violations


def exact_candidate(design,definitions,threads,modifiers,*,folder=None,cancelled=lambda:False):
    """Worker body: existing Router fluid gates, CAD, validator and STEP gate."""
    from ..routing import _ProposalSnapshot,_verify_route_candidate,authorize_generated_contacts,exact_route_score
    from ..geometry import build_geometry
    from ..validation import validate
    from ..cad_acceptance import topology_clear,production_topology,step_round_trip,add_step_check
    from .. import store,timing
    started=time.monotonic();target=design.model_copy(deep=True)
    pending={n.id for n in target.nets if n.routing=='automatic' and n.route_state=='proposal'}
    source=target.model_copy(update=dict(features=[f for f in target.features if f.route_net not in pending]))
    snapshot=_ProposalSnapshot(source,definitions,threads,modifiers);details={};failures=[]
    for index,net in enumerate(n for n in target.nets if n.id in pending):
        if cancelled():raise RuntimeError('AI generation cancelled; initial draft retained')
        timing.progress('connectivity',15+30*index/max(1,len(pending)))
        option=dict(key='explicit-ai-layout',route=[f for f in target.features if f.route_net==net.id],risk=0)
        if not _verify_route_candidate(target,effective_net(target,net),option,snapshot):
            failures.extend(option.get('conflicts',[]))
        details[net.id]=dict(admission=option.get('admission'),connectivity=option.get('connectivity_detail'))
        target.features=[f for f in target.features if f.route_net!=net.id]+option['route']
    if failures:
        result=dict(status='EXACT_ROUTING_REJECTED',design=target.model_dump(),validation=None,connections=details,
            failures=failures,rejection_reason='Exact source/route connectivity, opening or machining acceptance failed.',
            full_cad_evaluated=False,seconds=time.monotonic()-started)
    else:
        timing.progress('geometry',50);geometry=build_geometry(target,definitions,threads,modifiers)
        authorize_generated_contacts(target,geometry);timing.progress('rules',75)
        report=validate(target,geometry,definitions);timing.progress('step',88)
        step=step_round_trip(geometry,folder/'production.step' if folder else None);add_step_check(report,step)
        good=topology_clear(geometry) and step['status']=='PASS' and report['counts']['FAIL']==0
        result=dict(status='EXACT_FEASIBLE' if good else 'EXACT_ENGINEERING_REJECTED',design=target.model_dump(),validation=report,
            connections=details,failures=[dict(rule=c['rule'],items=c.get('items',[]),actual=c.get('actual')) for c in report['checks'] if c['status']=='FAIL'],
            topology=production_topology(geometry),step=step,full_cad_evaluated=True,manufacturing_ready=report.get('manufacturing_ready',False),
            exact_score=exact_route_score(target,report,[f for f in target.features if f.route_net],cad_error=not topology_clear(geometry)),
            seconds=time.monotonic()-started)
    if folder:
        folder.mkdir(parents=True,exist_ok=True)
        store.atomic_json(folder/'acceptance.json',result)
    return result


def run_exact(design,definitions,threads,modifiers,*,folder=None,cancelled=lambda:False,progress=None):
    """Production uses the existing disposable CAD executor and cancellation."""
    from ..engineering import calculate_sync
    from .. import store
    relative=str(folder.resolve().relative_to(store.OUTPUT.resolve())) if folder else None
    return calculate_sync('ai-layout-exact',dict(design=design.model_dump(),evidence_subdir=relative),
        cancelled=cancelled,on_progress=progress)


def _focus(design,failures):
    by_id={f.id:f for f in design.features};nets=set();owners=set()
    for row in failures:
        items=row.get('items',[]) if isinstance(row,dict) else row[1:]
        for key in items:
            feature=by_id.get(str(key).split(':')[0])
            if feature:
                if feature.route_net:nets.add(feature.route_net)
                else:owners.add(feature.id)
            if key in {n.id for n in design.nets}:nets.add(key)
    owners.update(m.split(':')[0] for n in design.nets if n.id in nets for m in n.members)
    return owners


def optimize(design,definitions,domain,*,layout_limit=48,exact_limit=2,progress=None,cancelled=lambda:False,
             initial=None,evidence_dir=None,seed_layouts=()):
    from ..engineering_db import thread_definitions_for_design,modifier_definitions_for_design,tool_definitions
    from ..layout_planning import _fits
    from ..routing import terminal_points,route_objective
    from ..store import revision,atomic_json
    from .layout_search import screen,_columns
    from .initialization import initial_candidates,route_feedback,constraint_conflicts
    from .route_catalog import Session
    from .joint_state import capture,rank as analytic_rank
    from .layout_resources import RefinementSchedule
    if not 1<=layout_limit<=128 or not 0<=exact_limit<=8:raise ValueError('Invalid AI layout calculation budget')
    original=design.model_copy(deep=True);source_revision=revision(original)
    threads=thread_definitions_for_design(original);modifiers=modifier_definitions_for_design(original) if any(f.machining_modifiers for f in original.features) else {}
    tools=tool_definitions('drill');serial=itertools.count();queue=[];frames=[];seen=set();records=[];attempts=[]
    counters=dict(layouts=0,transforms=0,source_rejected=0,duplicate_transforms=0,exact_attempts=0)
    counters.update(route_refinements=0,stalled_route_refinements=0)
    resources=RefinementSchedule(exact_limit,len(original.nets),layout_limit)
    inspected=set();routing_rejections=[];hypotheses={};family_counts={};schedule=itertools.cycle(('size','face','group','individual','feedback'))
    route_session=Session();assessments={};feedback_streak=0;frame_pages={};record_indices={};coupled_evaluations={}
    frame_schedule=itertools.cycle(('feedback','initial','feedback','explore'))
    feedback_schedule=itertools.cycle(('feedback-coupled','feedback-size','feedback-face','feedback-group','feedback-position'))
    transform_limit=layout_limit*64
    def emit(stage,**detail):
        if cancelled():
            from ..engineering import CalculationError
            raise CalculationError('AI generation cancelled; initial draft retained.',409)
        if progress:progress(stage,layout=max(1,min(layout_limit,counters['layouts']+int(stage=='layout_alternate'))),
            layout_limit=layout_limit,**detail)
    def enqueue(target,family,parent=None,reason=None):
        if not domain.accepts(original,target):return
        key=signature(target)
        if key in seen:counters['duplicate_transforms']+=1;return
        seen.add(key)
        hypotheses[key]=reason
        fits=_fits(target,definitions)
        conflicts=source_conflicts(target,definitions,threads,modifiers,domain._placement_cache) if fits else []
        previous=assessments.get(signature(parent)) if parent is not None else None
        blocked=set((previous or {}).get('unresolved_nets',(previous or {}).get('blocked_nets',[])))
        from .design_space import topology_cost_for
        cheap=(family!='initial-scaffold',not fits,len(conflicts),
            not bool(reason and reason.get('requires_route_regeneration')),
            len(blocked) if previous else len(target.nets),
            -len((previous or {}).get('partial_routing',{}).get('nets',[])),
            topology_cost_for(target,definitions,blocked) if blocked else topology_cost(target,definitions),
            math.prod(dimensions(target.block)))
        heapq.heappush(queue,(cheap,next(serial),target,family,parent,conflicts,fits))
    enqueue(original,'initial-scaffold')
    for seed in seed_layouts:
        enqueue(seed,'linked-source-layout',original,dict(rule='reviewed_source_poses',requires_route_regeneration=True))
    if initial:initial(original.model_copy(deep=True))
    # Retained source-column packing is one optional fast seed; it is no longer
    # the root or the sole placement family. Generic actions work without it.
    columns=_columns(original,definitions,domain.movable,domain.dimension_axes,domain.fixed_faces)
    if columns and domain.accepts(original,columns[0]):enqueue(columns[0],'source-columns')
    frames.append((original,iter(initial_candidates(original,definitions,domain,threads,modifiers)),'initial'))
    frames.append((original,iter(actions(original,definitions,domain,threads,modifiers)),'explore'))
    def record_state(row,target):
        row['joint_state']=capture(target,row['assessment'],definitions)
        row['routing_scale']=min((n.diameter for n in target.nets),default=1)
        parent=row.get('parent_layout_index')
        if parent is not None:
            previous=set(records[parent]['joint_state']['compatible_nets']);current=set(row['joint_state']['compatible_nets'])
            row['joint_transition']=dict(retained_compatible_nets=sorted(previous&current),
                lost_compatible_nets=sorted(previous-current),new_compatible_nets=sorted(current-previous))
        assessments[signature(target)]=row['assessment']
        if evidence_dir:atomic_json(Path(evidence_dir)/'layouts'/f'{row["index"]:03}.json',row)
    def feedback(row,target):
        # Replace stale actions for THIS geometry after routing or Exact updates.
        # Other compatible layouts keep their own action frontier.
        key=signature(target)
        frames[:]=[f for f in frames if f[2]!='feedback' or signature(f[0])!=key]
        frames.insert(0,(target,iter(route_feedback(target,row['assessment'],definitions,domain,threads,modifiers)),'feedback'))
    def expand_page():
        if not frames or counters['transforms']>=transform_limit:return False
        started=time.monotonic()
        kinds={f[2] for f in frames};kind=next(k for k in frame_schedule if k in kinds)
        # Expand valuable compatible parents, rather than recursively expanding
        # the last rejected descendant while its better siblings wait forever.
        def frame_rank(frame):
            key=signature(frame[0]);a=assessments.get(key,{})
            return (a.get('status')=='SOURCE_LAYOUT_REJECTED',len(a.get('unresolved_nets',original.nets)),
                    frame_pages.get((key,kind),0))
        index=min((i for i,f in enumerate(frames) if f[2]==kind),key=lambda i:frame_rank(frames[i]))
        parent,iterator,kind=frames.pop(index);exhausted=False
        token=(signature(parent),kind);frame_pages[token]=frame_pages.get(token,0)+1
        for _ in range(4):
            if counters['transforms']>=transform_limit:break
            try:
                item=next(iterator);family,target=item[:2];reason=item[2] if len(item)>2 else None
            except StopIteration:exhausted=True;break
            emit('layout_alternate');counters['transforms']+=1;enqueue(target,family,parent,reason)
        if not exhausted:frames.append((parent,iterator,kind))
        counters['transform_seconds']=counters.get('transform_seconds',0)+time.monotonic()-started
        return True
    def bucket(row):
        target,family,parent=row[2:5]
        if family in ('initial-scaffold','linked-source-layout'):return 'initial'
        if family=='feedback-coupled-interfaces':return 'feedback-coupled'
        if family.startswith('feedback-'):
            if parent is not None and dimensions(target.block)!=dimensions(parent.block):return 'feedback-size'
            old={f.id:f for f in (parent or original).features}
            changed=[f for f in target.features if (f.face,f.u,f.v,f.rotation)!=(old[f.id].face,old[f.id].u,old[f.id].v,old[f.id].rotation)]
            if any((f.face,f.rotation)!=(old[f.id].face,old[f.id].rotation) for f in changed):return 'feedback-face'
            return 'feedback-group' if len(changed)>1 else 'feedback-position'
        if family=='face-arrangement':return 'face'
        if dimensions(target.block)!=dimensions(original.block):return 'size'
        if any(f.face!=g.face for f,g in zip(target.features,original.features)):return 'face'
        return 'group' if family in ('source-columns','connected-group','topology-repack') else 'individual'
    def pop_diverse():
        nonlocal feedback_streak
        available={bucket(row) for row in queue}
        measured=any(bucket(row).startswith('feedback-') and hypotheses.get(signature(row[2]),{} ) and
            hypotheses[signature(row[2])].get('requires_route_regeneration') for row in queue)
        if 'initial' in available:category='initial'
        elif measured and feedback_streak<2:category=next(c for c in feedback_schedule if c in available)
        else:
            normal={c for c in available if not c.startswith('feedback-')}
            category=next(c for c in schedule if c in normal) if normal else next(c for c in feedback_schedule if c in available)
        feedback_streak=feedback_streak+1 if category.startswith('feedback-') else 0
        def queue_rank(i):
            row=queue[i];reason=hypotheses.get(signature(row[2])) or {}
            group=tuple(reason.get('owners',[]))
            return (coupled_evaluations.get(group,0) if category=='feedback-coupled' else 0,*row[:2])
        index=min((i for i,row in enumerate(queue) if bucket(row)==category),key=queue_rank)
        row=queue.pop(index);heapq.heapify(queue);family_counts[category]=family_counts.get(category,0)+1
        if category=='feedback-coupled':
            group=tuple((hypotheses.get(signature(row[2])) or {}).get('owners',[]))
            coupled_evaluations[group]=coupled_evaluations.get(group,0)+1
        return row
    def scan(until):
        while counters['layouts']<until and (queue or frames):
            emit('layout_alternate')
            expand_page()
            # Use the existing transform allowance to expose distinct action
            # classes before selection, rather than enlarging routing budgets.
            for _ in range(2):
                if len({bucket(row) for row in queue})>=3:break
                if not expand_page():break
            if not queue:
                if not frames or counters['transforms']>=transform_limit:break
                continue
            _,_,target,family,parent,conflicts,fits=pop_diverse();counters['layouts']+=1
            screen_started=time.monotonic()
            if not fits or conflicts:
                counters['source_rejected']+=1
                detail=dict(status='SOURCE_LAYOUT_REJECTED',compatible=False,blocked_nets=[],
                    conflicts=[['source_wall',*p] for p in conflicts]+fit_violations(target,definitions,domain),fixed_conflicts=conflicts,
                    feasibility_score=(1,len(conflicts)+int(not fits)),score=(1,len(conflicts)+int(not fits),topology_cost(target,definitions)),route_features=[])
            else:
                points=terminal_points(target,definitions);lanes={};planes={}
                for net in target.nets:
                    members=[points[m] for m in net.members if m in points]
                    if not members:continue
                    lanes[net.id]=sum(p[1] for p in members)/len(members);planes[net.id]=sum(p[2] for p in members)/len(members)
                detail=screen(target,definitions,threads,modifiers,tools,lanes,planes,
                    lambda stage,**d:emit(stage,**d),include_routes=True,corridor_labels=0,general_families=True,route_session=route_session)
            old={f.id:f for f in original.features}
            changes=[dict(feature=f.id,parameters={k:[getattr(old[f.id],k),getattr(f,k)] for k in ('face','u','v','rotation')
                if getattr(old[f.id],k)!=getattr(f,k)}) for f in target.features if f!=old[f.id]]
            row=dict(index=len(records),family=family,design=target.model_dump(),assessment=detail,
                parent_layout_index=record_indices.get(signature(parent)) if parent is not None else None,
                screen_seconds=time.monotonic()-screen_started,
                hypothesis=hypotheses.get(signature(target)),
                geometry_changes=dict(dimensions=[list(dimensions(original.block)),list(dimensions(target.block))],placements=changes))
            records.append(row)
            record_indices[signature(target)]=row['index']
            record_state(row,target)
            focus=_focus(target,detail.get('conflicts',[]))
            if counters['transforms']<transform_limit:
                if detail['status']=='SOURCE_LAYOUT_REJECTED':
                    frames.append((target,iter(actions(target,definitions,domain,threads,modifiers,focus)),'explore'))
                elif not detail.get('compatible'):
                    feedback(row,target)
    # Spend cheap layout work before CAD, then revise layout after Exact failure
    # instead of exhausting increasingly elaborate fixed-geometry drillings.
    # React after a small layout batch, not after sixteen unrelated layouts.
    # This does not increase layouts, transforms, labels or Exact attempts.
    rounds=max(1,(layout_limit+3)//4)
    for turn in range(rounds):
        scan(max(1,layout_limit*(turn+1)//rounds))
        if not exact_limit or len(attempts)>=exact_limit:continue
        complete=[r for r in records if r['index'] not in inspected and r['assessment'].get('compatible')]
        choice=None if complete else resources.select(records,counters['layouts'],final=turn==rounds-1)
        if not complete and choice is None:continue
        chosen=min(complete,key=analytic_rank) if complete else choice[0]
        target=Design.model_validate(chosen['design'])
        if not chosen['assessment'].get('compatible'):
            limits=choice[1]
            previous_coverage=len(chosen['joint_state']['compatible_nets'])
            before=(previous_coverage,tuple(chosen['joint_state']['repair_burden']))
            points=terminal_points(target,definitions)
            lanes={n.id:sum(points[m][1] for m in n.members)/len(n.members) for n in target.nets if len(n.members)>=2}
            planes={n.id:sum(points[m][2] for m in n.members)/len(n.members) for n in target.nets if len(n.members)>=2}
            refinement_started=time.monotonic()
            chosen['assessment']=screen(target,definitions,threads,modifiers,tools,lanes,planes,
                lambda stage,**d:emit(stage,**d),include_routes=True,corridor_labels=limits['labels'],general_families=True,
                route_session=route_session,deep_limits=limits)
            chosen['assessment']['routing_refinement']='SHARED_3D_PLANNER_BOUNDED_BEFORE_NEXT_LAYOUT_REVISION'
            chosen['refinement_seconds']=time.monotonic()-refinement_started
            record_state(chosen,target)
            counters['route_refinements']+=1
            improved=resources.charge(chosen,before,limits)
            counters['stalled_route_refinements']+=int(not improved)
            chosen['search_decision']=dict(action='EXACT' if chosen['assessment'].get('compatible') else 'REVISE_GEOMETRY',
                compatible_before=previous_coverage,compatible_after=len(chosen['joint_state']['compatible_nets']),
                reason=('Compatible coverage improved' if len(chosen['joint_state']['compatible_nets'])>previous_coverage else
                    'Actual insertion conflicts decreased') if improved else 'No compatible coverage or insertion constraint improvement',
                repair_burden_before=list(before[1]),repair_burden_after=chosen['joint_state']['repair_burden'],
                repeat_same_geometry=bool(chosen.get('deep_history')))
            chosen.setdefault('deep_history',[]).append(dict(**chosen['search_decision'],limits=limits,
                seconds=chosen['refinement_seconds'],resources_remaining=resources.remaining()))
            record_state(chosen,target)
            if not chosen['assessment'].get('compatible'):feedback(chosen,target)
        route=[Feature.model_validate(f) for f in chosen['assessment']['route_features']]
        missing=[n.id for n in target.nets if n.routing=='automatic' and n.route_state in ('unresolved','proposal') and
                 len(n.members)>=2 and not any(f.route_net==n.id for f in route)]
        if missing:
            # An empty/missing machining network is not a complete Exact
            # candidate. Keep its corridor/retention evidence, revise geometry,
            # and leave the full CAD budget available rather than testing air.
            routing_rejections.append(dict(layout_index=chosen['index'],status='INCOMPLETE_ROUTING_PROPOSAL',missing_nets=missing,
                partial_routing=chosen['assessment'].get('partial_routing'),feedback=chosen['assessment'].get('layout_feedback')))
            continue
        if not chosen['assessment'].get('compatible'):
            routing_rejections.append(dict(layout_index=chosen['index'],status='INCOMPATIBLE_ROUTING_PROPOSAL',
                conflicts=chosen['assessment'].get('conflicts'),partial_routing=chosen['assessment'].get('partial_routing'),
                witnesses=chosen['assessment'].get('witnesses')))
            continue
        inspected.add(chosen['index'])
        target.features.extend(route)
        for net in target.nets:
            if net.routing=='automatic' and net.route_state=='unresolved':net.route_state='proposal';net.routing_variant=None
        folder=Path(evidence_dir)/f'exact-{len(attempts):02}' if evidence_dir else None
        if folder:folder.mkdir(parents=True,exist_ok=True)
        emit('exact_layout',candidate=len(attempts)+1,candidate_limit=exact_limit)
        try:
            result=run_exact(target,definitions,threads,modifiers,folder=folder,cancelled=cancelled,
                progress=lambda d:emit('exact_layout',candidate=len(attempts)+1,candidate_limit=exact_limit,exact_progress=d))
        except RuntimeError as exc:
            if cancelled():raise
            result=dict(status='EXACT_UNAVAILABLE',validation=None,design=target.model_dump(),error=str(exc),failures=[],full_cad_evaluated=False)
        counters['exact_attempts']+=1;attempts.append(dict(layout_index=chosen['index'],index=len(attempts),**result))
        if result['status']!='EXACT_FEASIBLE':
            rejected=Design.model_validate(result['design']);focus=_focus(rejected,result.get('failures',[]))
            chosen['assessment']={**chosen['assessment'], 'blocked_nets':[n.id for n in target.nets if {m.split(':')[0] for m in n.members}&focus],
                'exact_failures':result.get('failures',[]),'exact_connections':result.get('connections',{})}
            from .route_feedback import exact_witnesses
            rejected_constraints,source_witnesses=exact_witnesses(rejected,result.get('failures',[]),definitions,threads,modifiers)
            chosen['assessment']['coordination_constraints']=rejected_constraints
            chosen['assessment']['spatial_feedback']=source_witnesses
            source=Design.model_validate(chosen['design'])
            record_state(chosen,source);feedback(chosen,source)
    if not records:
        records=[dict(index=0,family='initial-scaffold',design=original.model_dump(),assessment=dict(status='SOURCE_LAYOUT_REJECTED',compatible=False,
            score=(1,),feasibility_score=(1,),blocked_nets=[],conflicts=[['source_envelope']],route_features=[]))]
        record_state(records[0],original)
    full=[a for a in attempts if a.get('validation')]
    accepted=[a for a in full if a['status']=='EXACT_FEASIBLE']
    if full:
        best=min(accepted or full,key=lambda a:(tuple(a['exact_score'][:2]),tuple(a['exact_score'][2][:-1]),
            math.prod(dimensions(Design.model_validate(a['design']).block)),a['exact_score'][2][-1]))
        selected=records[best['layout_index']];output=Design.model_validate(best['design'])
        for net in output.nets:
            if net.routing=='automatic':net.route_state='proposal' if best['status']=='EXACT_FEASIBLE' else 'stale';net.routing_variant=None
        status=best['status'];validation=best['validation']
    else:
        selected=min(records,key=analytic_rank);output=Design.model_validate(selected['design']);validation=None
        status='ANALYTIC_UNVALIDATED' if not exact_limit else 'UNRESOLVED_LAYOUT'
        if exact_limit:
            for net in output.nets:
                if net.routing=='automatic':
                    net.route_state='stale';net.routing_variant=None
                    net.route_issue='AI layout/routing remains unresolved. Review retained constraints or explicitly Reroute; Model will preserve all source positions.'
    # The complete geometry is the handoff, never a variant/candidate registry.
    proposals=[dict(design=output.model_dump(),assessment={k:v for k,v in selected['assessment'].items() if k!='route_features'},
        reason='Joint source-constrained placement, dimensions and shared routing',dimensions=list(dimensions(output.block)))]
    result=dict(scope='AI_GENERATION_ONLY',source_revision=source_revision,status=status,baseline=records[0]['assessment'],
        proposals=proposals,evaluated_layouts=len(records),layout_limit=layout_limit,attempts=attempts,validation=validation,
        domain=domain.diagnostics(),counters=counters,deferred_layouts=len(queue),unexpanded_transform_generators=len(frames),
        transform_limit=transform_limit,physical_infeasibility_proven=False,routing_rejections=routing_rejections,
        evaluations=[{k:v for k,v in r.items() if k!='design'} for r in records],frontier=[],manufacturing_ready=bool(accepted and best.get('manufacturing_ready')))
    result['family_evaluations']=family_counts
    result['coupled_group_evaluations']=[dict(features=list(group),evaluations=count) for group,count in coupled_evaluations.items()]
    result['resource_schedule']=resources.diagnostics()
    result['resource_schedule']['ordinary_routing']=dict(state_limit_per_layout=1000,pair_limit_per_layout=4000)
    result['resource_schedule']['exact']=dict(limit=exact_limit,attempts=len(attempts))
    result['packing_diagnostics']=domain._packing_diagnostics
    result['hard_constraint_conflicts']=constraint_conflicts(original,definitions,domain,threads,modifiers)
    result['outcome_classification']='EXACT_FEASIBLE' if accepted else 'PROVEN_HARD_CONSTRAINT_CONFLICT' if result['hard_constraint_conflicts'] else 'UNRESOLVED_SEARCH_OR_ENGINEERING'
    if evidence_dir:atomic_json(Path(evidence_dir)/'layout-search.json',result)
    return result
