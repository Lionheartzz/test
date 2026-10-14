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
    if folder:folder.mkdir(parents=True,exist_ok=True)
    pending={n.id for n in target.nets if n.routing=='automatic' and n.route_state=='proposal'}
    source=target.model_copy(update=dict(features=[f for f in target.features if f.route_net not in pending]))
    snapshot=_ProposalSnapshot(source,definitions,threads,modifiers);details={};failures=[]
    for index,net in enumerate(n for n in target.nets if n.id in pending):
        if cancelled():raise RuntimeError('AI generation cancelled; initial draft retained')
        timing.progress('connectivity',15+30*index/max(1,len(pending)))
        option=dict(key='explicit-ai-layout',route=[f for f in target.features if f.route_net==net.id],risk=0)
        if not _verify_route_candidate(target,effective_net(target,net),option,snapshot,prune=False):
            failures.extend(option.get('conflicts',[]))
        details[net.id]=dict(admission=option.get('admission'),connectivity=option.get('connectivity_detail'),
                            cad_error=option.get('cad_geometry_error'))
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


def admit_final_cores(records,session,record_state,emit):
    """Re-rank after real rejection; spend the reserve on the actual handoff.

    Each source state is visited once. Cached facts remain usable even when
    fresh CAD is exhausted; unknown results never become accepted evidence.
    """
    from .joint_state import rank
    from .route_catalog import geometry_key
    inspected=set()
    candidates=[r for r in records if r['assessment']['status']!='SOURCE_LAYOUT_REJECTED']
    while candidates:
        row=min(candidates,key=rank);a=row['assessment']
        dependency=a.get('joint_solver',{}).get('dependency')
        state=session.solver.states.get(dependency)
        if state is None or dependency in inspected:break
        inspected.add(dependency)
        cuts=[Feature.model_validate(f) for f in a.get('partial_routing',{}).get('features',[])]
        core={n:next(o for o in state.catalogs[n].clear if geometry_key(o['route'])==
                geometry_key([f for f in cuts if f.route_net==n]))
              for n in a.get('partial_routing',{}).get('nets',[])}
        session.solver.current=state;session.catalogs=state.catalogs
        session.local_allocation=None
        emit('local_admission',layout_index=row['index'],nets=sorted(core))
        kept=session.admit_core(state.source,state.nets,core)
        a['partial_routing'].update(nets=sorted(kept),features=[f.model_dump(mode='json') for o in kept.values() for f in o['route']],
            local_admission={n:session.local_records[n] for n in core})
        a['route_features']=a['partial_routing']['features']
        a['compatible']=len(kept)==len(state.nets)
        a['unresolved_nets']=sorted(set(state.nets)-set(kept))
        session.solver.update(a,state=state);record_state(row,state.source)


def optimize(design,definitions,domain,*,layout_limit=None,exact_limit=2,progress=None,cancelled=lambda:False,
             initial=None,evidence_dir=None,seed_layouts=()):
    """Normal Generate owns ONE work Design; legacy budgets do not select layouts.

    ``layout_limit``/``seed_layouts`` remain accepted for old diagnostic callers,
    but never open a layout portfolio or seed source geometry from another project.
    """
    from ..engineering_db import thread_definitions_for_design,modifier_definitions_for_design,tool_definitions
    from ..store import revision,atomic_json
    from .single_design import WorkDesign
    from .local_admission import LocalAdmission,ADMISSIBLE
    from . import execution
    from .. import timing
    if not 0<=exact_limit<=8:raise ValueError('Invalid Exact calculation budget')
    execution.span(0)
    execution.checkpoint(design,status='UNVALIDATED_SOURCE_COMPILATION',priority=0)
    if initial:initial(design.model_copy(deep=True))
    def emit(stage,**detail):
        if cancelled():
            from ..engineering import CalculationError
            raise CalculationError('AI generation cancelled; current work Draft retained.',409)
        if progress:progress(stage,layout=1,layout_limit=1,**detail)
    emit('engineering_plan',completed=0,total=1)
    threads=thread_definitions_for_design(design)
    modifiers=modifier_definitions_for_design(design) if any(f.machining_modifiers for f in design.features) else {}
    tools=tool_definitions('drill');work=WorkDesign(design,definitions,domain,threads,modifiers,tools)
    ready=work.initialize();attempts=[];validation=None;exact=None
    def source_checkpoint():
        execution.checkpoint(work.design,status='SOURCE_LAYOUT_READY_MACHINING_PENDING' if work.source_ready else 'SOURCE_LAYOUT_REJECTED',
            evidence=work.diagnostics(),priority=1)
        if evidence_dir:atomic_json(Path(evidence_dir)/'work-design.json',dict(design=work.design.model_dump(),evidence=work.diagnostics()))
    source_checkpoint()
    if initial:initial(work.design.model_copy(deep=True))
    if ready:
        emit('access',completed=0,total=1)
        work.materialize();work.precheck();source_checkpoint()
        # A finite sequence of measured local transactions, not competing
        # layouts. A stalled/unknown constraint terminates immediately.
        for step in range(2*len(work.state.plans)):
            if not work.failures or work.process_gap:break
            emit('engineering_plan',completed=step,total=max(1,2*len(work.state.plans)),decision='LOCAL_PROCESS_REPAIR')
            with timing.phase('single.local_repair'):
                changed=work.repair()
            source_checkpoint()
            if not changed:break
            work.precheck()
    clear={n:dict(key='engineering-process:'+n,route=fs,risk=0) for n,fs in work.routes.items() if n not in work.failures}
    admission=LocalAdmission(max(8,2*len(work.state.plans)))
    nets={n.id:effective_net(work.design,n) for n in work.design.nets}
    # Rejected process never enters Session.prepare, coordinate, or plan_net.
    # Valid partial routes may receive local CAD; that cannot accept the Design.
    for i,name in enumerate(list(clear)):
        emit('local_admission',net=name,completed=i,total=len(clear))
        with timing.phase('single.local_cad'):
            work.local[name]=admission.check(work.design,nets[name],clear[name],clear,definitions,threads,modifiers,tools)
            if work.local[name]['status']=='LOCAL_EXACT_REJECTED':
                work.repair_contact(name,work.local[name],admission,clear)
        if work.local[name]['status']!=ADMISSIBLE:clear.pop(name,None)
    # Removing a rejected/unknown cut changes the retained dependency set.
    # Re-bind surviving local proofs; unchanged full sets hit Phase B's cache.
    for name in list(clear):
        with timing.phase('single.local_cad'):
            work.local[name]=admission.check(work.design,nets[name],clear[name],clear,definitions,threads,modifiers,tools)
    kept={n:o for n,o in clear.items() if work.local[n]['status']==ADMISSIBLE}
    output=work.design.model_copy(deep=True)
    output.features.extend(Feature.model_validate(f) for n in kept for f in work.local[n]['verified_geometry'])
    # A sufficient symbolic-domain cycle is not a physical nogood. If the
    # actual complete cuts pass production machining and local fluid gates,
    # final Exact remains authoritative for every hard engineering condition.
    complete=ready and len(kept)==len(work.required_nets) and not work.failures
    for n in output.nets:
        if n.routing=='automatic':
            n.routing_variant=None;n.route_state='proposal' if n.id in kept else 'unresolved'
            n.route_issue='' if complete else 'Current engineering plan is incomplete. Saved source positions remain user-owned; review failed constraints or explicitly Reroute.'
    if complete and exact_limit:
        emit('exact_layout',completed=0,total=1)
        with timing.phase('single.full_exact'):
            from ..engineering import CalculationError
            try:
                exact=run_exact(output,definitions,threads,modifiers,folder=Path(evidence_dir)/'exact' if evidence_dir else None,
                    cancelled=cancelled,progress=lambda p:emit('exact_layout',exact_progress=p))
            except CalculationError as exc:
                if cancelled():raise
                exact=dict(status='CAD_EVALUATION_ERROR',design=output.model_dump(),validation=None,full_cad_evaluated=False,
                    cad_error=dict(operation='ai-layout-exact',message=str(exc),retry_conditions=['Changed geometry or explicit fresh CAD retry']),
                    manufacturing_ready=False,physical_infeasibility_proven=False)
        attempts.append(exact);validation=exact.get('validation')
        output=Design.model_validate(exact['design'])
    accepted=bool(exact and exact['status']=='EXACT_FEASIBLE')
    status=exact['status'] if exact else 'SOURCE_LAYOUT_READY_ROUTING_PENDING' if ready else 'SOURCE_LAYOUT_REJECTED'
    if exact and not accepted:
        for n in output.nets:
            if n.routing=='automatic':n.route_issue='Full Exact acceptance has not passed. Review the retained engineering/CAD evidence.'
    unresolved=sorted(work.required_nets-set(kept))
    assessment=dict(status=status,compatible=complete,blocked_nets=unresolved,unresolved_nets=unresolved,
        conflicts=[f for rows in work.failures.values() for f in rows],score=(len(unresolved),),feasibility_score=(len(unresolved),),
        partial_routing=dict(nets=sorted(kept),features=[f.model_dump() for f in output.features if f.route_net],local_admission=work.local),
        route_features=[f.model_dump() for f in output.features if f.route_net],full_exact_outcome=exact,
        engineering_status='FULL_EXACT_ACCEPTED' if accepted else 'LOCAL_EXACT_PARTIAL' if kept else 'MACHINING_REJECTED' if work.failures else 'SOURCE_LAYOUT_ONLY')
    result=dict(scope='AI_GENERATION_ONLY',mode='SINGLE_WORK_DESIGN',source_revision=revision(design),status=status,
        baseline=assessment,proposals=[dict(design=output.model_dump(),assessment=assessment,
            reason='One engineering work Design; source-backed spacing and measured local process repairs',dimensions=list(dimensions(output.block)))],
        evaluated_layouts=1,layout_limit=1,evaluations=[dict(index=0,family='engineering-plan',assessment=assessment)],
        attempts=attempts,validation=validation,engineering_planner=work.diagnostics(),domain=domain.diagnostics(),
        local_admission_summary=admission.diagnostics(),deferred_layouts=0,unexpanded_transform_generators=0,
        counters=dict(layouts=1,local_work_revisions=work.versions,catalog_searches=0,deep_labels=0,exact_attempts=len(attempts)),
        hard_constraint_conflicts=[],frontier=[],manufacturing_ready=bool(accepted and exact.get('manufacturing_ready')),
        outcome_classification='EXACT_FEASIBLE' if accepted else 'UNRESOLVED_ENGINEERING_CONSTRAINT',physical_infeasibility_proven=False,
        resource_schedule=dict(mode='MEASURED_LOCAL_TRANSACTIONS',legacy_layout_budget_ignored=layout_limit))
    execution.checkpoint(output,status=status,assessment=assessment,evidence=work.diagnostics(),priority=2)
    if evidence_dir:atomic_json(Path(evidence_dir)/'layout-search.json',result)
    return result


def optimize_legacy_layout_portfolio(design,definitions,domain,*,layout_limit=48,exact_limit=2,progress=None,cancelled=lambda:False,
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
    from . import execution
    if not 1<=layout_limit<=128 or not 0<=exact_limit<=8:raise ValueError('Invalid AI layout calculation budget')
    original=design.model_copy(deep=True);source_revision=revision(original)
    threads=thread_definitions_for_design(original);modifiers=modifier_definitions_for_design(original) if any(f.machining_modifiers for f in original.features) else {}
    tools=tool_definitions('drill');serial=itertools.count();queue=[];frames=[];seen=set();records=[];attempts=[]
    counters=dict(layouts=0,transforms=0,source_rejected=0,duplicate_transforms=0,exact_attempts=0)
    counters.update(route_refinements=0,stalled_route_refinements=0)
    resources=RefinementSchedule(exact_limit,len(original.nets),layout_limit)
    inspected=set();routing_rejections=[];hypotheses={};family_counts={};schedule=itertools.cycle(('size','face','group','individual','feedback'))
    route_session=Session();route_session.solver.domain=domain.diagnostics()
    # Cheap layout sampling cannot consume local CAD. Half of the unchanged
    # admission budget serves selected deep cores; the rest serves the final
    # best partial core, including geometry discovered late in the run.
    route_session.local_allocation=0
    assessments={};feedback_streak=0;frame_pages={};record_indices={};coupled_evaluations={}
    frame_schedule=itertools.cycle(('feedback','initial','feedback','explore'))
    feedback_schedule=itertools.cycle(('feedback-coupled','feedback-size','feedback-face','feedback-group','feedback-position'))
    transform_limit=layout_limit*64
    from .engineering_decisions import EngineeringDecisionController
    engineering=EngineeringDecisionController(original,definitions,domain,threads,modifiers,tools,limit=transform_limit,
        progress=lambda **detail:emit('engineering_plan',**detail))
    manufacturing_plans={};decision_keys={};fallback_started=False
    def emit(stage,**detail):
        if cancelled():
            from ..engineering import CalculationError
            raise CalculationError('AI generation cancelled; initial draft retained.',409)
        searches=list(route_session.search_context.searches.values()) if execution.work_due() else []
        if execution.work_due():execution.work_state(dict(stage=stage,detail=detail,layouts=counters['layouts'],
            newly_expanded_labels=sum(s.budget['used'] for s in searches),
            continuation=[dict(net=s.space.net.id,labels=s.budget['used'],tree_frontier=len(s.frontier),
                path_frontier=len(s.path.queue) if s.path else 0,geometry=s.space.diagnostics('CHECKPOINT')) for s in searches],
            transactions=[dict(dependency=k,release=list(t.group),completed=len(t.completed),pending=sum(len(j['pending']) for j in t.queue),queue=len(t.queue))
                for k,state in route_session.solver.states.items() for t in state.transactions.values()],
            cache=execution.cache_metrics(route_session),
            timing=__import__('manifold.timing',fromlist=['summary']).summary()))
        if progress:progress(stage,layout=max(1,min(layout_limit,counters['layouts']+int(stage=='layout_alternate'))),
            layout_limit=layout_limit,**detail)
    def enqueue(target,family,parent=None,reason=None):
        if not domain.accepts(original,target):return
        layout_key=signature(target)
        key=(layout_key,(reason or {}).get('engineering_decision'))
        if key in seen:counters['duplicate_transforms']+=1;return
        seen.add(key)
        hypotheses[layout_key]=reason
        fits=_fits(target,definitions)
        conflicts=source_conflicts(target,definitions,threads,modifiers,domain._placement_cache) if fits else []
        previous=assessments.get(signature(parent)) if parent is not None else None
        blocked=set((previous or {}).get('unresolved_nets',(previous or {}).get('blocked_nets',[])))
        from .design_space import topology_cost_for
        cheap=(family!='engineering-plan',family!='initial-scaffold',not fits,len(conflicts),
            not bool(reason and reason.get('requires_route_regeneration')),
            len(blocked) if previous else len(target.nets),
            -len((previous or {}).get('partial_routing',{}).get('nets',[])),
            topology_cost_for(target,definitions,blocked) if blocked else topology_cost(target,definitions),
            math.prod(dimensions(target.block)))
        heapq.heappush(queue,(cheap,next(serial),target,family,parent,conflicts,fits))
    if initial:initial(original.model_copy(deep=True))
    def next_engineering():
        nonlocal fallback_started
        execution.span(counters['layouts'])
        emit('engineering_plan')
        before=len(engineering.records)
        row=engineering.next_candidate()
        counters['transforms']+=len(engineering.records)-before
        counters['engineering_domains']=len(engineering.records)
        if row:
            target,reason,routes=row;key=signature(target)
            execution.checkpoint(target,status='SOURCE_LAYOUT_READY_ROUTING_PENDING',priority=1,
                evidence=dict(engineering_decision=reason['engineering_decision'],engineering=engineering.diagnostics()))
            manufacturing_plans[key]=routes;decision_keys[key]=reason['engineering_decision']
            enqueue(target,'engineering-plan',reason=reason)
            return True
        # Existing packing is a fallback when the selected manufacturing
        # language/domain frontier was exhausted, never a competing scheduler.
        if not fallback_started:
            fallback_started=True
            for seed in seed_layouts:enqueue(seed,'linked-source-layout',original)
            enqueue(original,'initial-scaffold')
            if engineering.unexpressed:
                frames.append((original,iter(initial_candidates(original,definitions,domain,threads,modifiers)),'initial'))
        return False
    def record_state(row,target):
        state=route_session.solver.states.get(row['assessment'].get('joint_solver',{}).get('dependency'))
        if state is not None and state.assessment is not row['assessment']:
            # Full Exact may evaluate an earlier layout while another source
            # state is current. Feedback must use that layout's NEW outcome,
            # not its cached pre-CAD assessment or the most recent layout.
            route_session.solver.update(row['assessment'],state=state)
        row['joint_state']=capture(target,row['assessment'],definitions)
        row['routing_scale']=min((n.diameter for n in target.nets),default=1)
        parent=row.get('parent_layout_index')
        if parent is not None:
            previous=set(records[parent]['joint_state']['compatible_nets']);current=set(row['joint_state']['compatible_nets'])
            row['joint_transition']=dict(retained_compatible_nets=sorted(previous&current),
                lost_compatible_nets=sorted(previous-current),new_compatible_nets=sorted(current-previous))
        assessments[signature(target)]=row['assessment']
        if evidence_dir:atomic_json(Path(evidence_dir)/'layouts'/f'{row["index"]:03}.json',row)
        viable=[r for r in records if r.get('joint_state',{}).get('source_layout_status')=='SOURCE_LAYOUT_READY']
        if viable and execution.enabled():
            best=min(viable,key=analytic_rank);a=best['assessment'];saved=Design.model_validate(best['design'])
            saved.features.extend(Feature.model_validate(f) for f in a.get('partial_routing',{}).get('features',[]))
            for n in saved.nets:
                if n.routing=='automatic':
                    n.route_state='proposal' if any(f.route_net==n.id for f in saved.features) else 'unresolved'
                    n.routing_variant=None;n.route_issue='AI execution is incomplete; retained cuts require review or explicit Reroute.'
            execution.checkpoint(saved,status='SOURCE_LAYOUT_READY_ROUTING_PENDING',assessment=a,
                # The authoritative rank may prefer fewer CAD-admitted cuts.
                # Do not let an older, larger analytic core block its update.
                priority=2,
                evidence=dict(selected_layout=best['index'],evaluations=[dict(index=r['index'],family=r['family'],
                    screen_seconds=r['screen_seconds'],refinement_seconds=r.get('refinement_seconds')) for r in records],
                    engineering=engineering.diagnostics()))
    def feedback(row,target):
        if row['family']=='engineering-plan':
            engineering.observe(target,row['assessment'],row.get('engineering_decision'))
            return
        if not engineering.unexpressed:
            return  # fallback source seed cannot restart the old pose sampler
        # Replace stale actions for THIS geometry after routing or Exact updates.
        # Other compatible layouts keep their own action frontier.
        key=signature(target)
        frames[:]=[f for f in frames if f[2]!='feedback' or signature(f[0])!=key]
        state=route_session.solver.states.get(row['joint_state'].get('joint_dependency'))
        frames.insert(0,(target,iter(route_feedback(target,state.assessment if state else row['assessment'],
            definitions,domain,threads,modifiers,joint_state=state)),'feedback'))
    def expand_page():
        if engineering.queue and len(engineering.records)<engineering.limit:
            return next_engineering()
        if not frames or counters['transforms']>=transform_limit:return False
        started=time.monotonic()
        kinds={f[2] for f in frames};kind=next(k for k in frame_schedule if k in kinds)
        # Expand valuable compatible parents, rather than recursively expanding
        # the last rejected descendant while its better siblings wait forever.
        def frame_rank(frame):
            key=signature(frame[0]);a=assessments.get(key,{})
            # A geometry with temporarily fewer routed Nets must still expose
            # its different source/window space. Age precedes soft coverage.
            return (a.get('status')=='SOURCE_LAYOUT_REJECTED',frame_pages.get((key,kind),0),
                    len(a.get('unresolved_nets',original.nets)))
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
        if family=='engineering-plan':return 'engineering'
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
        if 'engineering' in available:category='engineering'
        elif 'initial' in available:category='initial'
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
        while counters['layouts']<until and (queue or frames or engineering.queue or not fallback_started):
            emit('layout_alternate')
            if not queue:
                if engineering.queue or not fallback_started:next_engineering()
                else:expand_page()
            # Use the existing transform allowance to expose distinct action
            # classes before selection, rather than enlarging routing budgets.
            for _ in range(0 if engineering.queue or queue and bucket(queue[0])=='engineering' else 2):
                if len({bucket(row) for row in queue})>=3:break
                if not expand_page():break
            if not queue:
                if not frames or counters['transforms']>=transform_limit:break
                continue
            _,_,target,family,parent,conflicts,fits=pop_diverse();counters['layouts']+=1
            execution.span(len(records))
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
                    lambda stage,**d:emit(stage,**d),include_routes=True,corridor_labels=0,general_families=True,route_session=route_session,
                    planned_routes=manufacturing_plans.get(signature(target)))
            old={f.id:f for f in original.features}
            changes=[dict(feature=f.id,parameters={k:[getattr(old[f.id],k),getattr(f,k)] for k in ('face','u','v','rotation')
                if getattr(old[f.id],k)!=getattr(f,k)}) for f in target.features if f!=old[f.id]]
            row=dict(index=len(records),family=family,design=target.model_dump(),assessment=detail,
                engineering_decision=decision_keys.get(signature(target)),
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
    # Once layout sampling finishes, use the SAME remaining resource ledger.
    # Net count is not a bound on conditional branch depth or batch count.
    # Every refinement must charge real states/work; no allocation => stop.
    for turn in itertools.count():
        scan(min(layout_limit,max(1,layout_limit*(turn+1)//rounds)))
        if not exact_limit or len(attempts)>=exact_limit:
            if turn>=rounds-1:break
            continue
        complete=[r for r in records if r['index'] not in inspected and r['assessment'].get('compatible')]
        choice=None if complete else resources.select(records,counters['layouts'],final=turn>=rounds-1)
        if not complete and choice is None:
            if turn>=rounds-1:break
            continue
        chosen=min(complete,key=analytic_rank) if complete else choice[0]
        target=Design.model_validate(chosen['design'])
        if not chosen['assessment'].get('compatible'):
            execution.span(chosen['index'],deep=True)
            limits=choice[1]
            previous_coverage=len(chosen['joint_state']['compatible_nets'])
            before=(previous_coverage,tuple(chosen['joint_state']['repair_burden']))
            points=terminal_points(target,definitions)
            lanes={n.id:sum(points[m][1] for m in n.members)/len(n.members) for n in target.nets if len(n.members)>=2}
            planes={n.id:sum(points[m][2] for m in n.members)/len(n.members) for n in target.nets if len(n.members)>=2}
            refinement_started=time.monotonic()
            admission_used=route_session.local_admission.used if route_session.local_admission else 0
            admission_limit=max(8,2*len(target.nets))
            route_session.local_allocation=min(2,max(0,admission_limit//2-admission_used))
            chosen['assessment']=screen(target,definitions,threads,modifiers,tools,lanes,planes,
                lambda stage,**d:emit(stage,**d),include_routes=True,corridor_labels=limits['labels'],general_families=True,
                route_session=route_session,deep_limits=limits,
                planned_routes=(engineering.by_decision.get(chosen.get('engineering_decision')) or {}).get('routes'))
            execution.span(chosen['index'])
            route_session.local_allocation=0
            chosen['assessment']['routing_refinement']='SHARED_3D_PLANNER_BOUNDED_BEFORE_NEXT_LAYOUT_REVISION'
            chosen['refinement_seconds']=time.monotonic()-refinement_started
            record_state(chosen,target)
            counters['route_refinements']+=1
            improved=resources.charge(chosen,before,limits)
            counters['stalled_route_refinements']+=int(not improved)
            chosen['search_decision']=dict(action='EXACT' if chosen['assessment'].get('compatible') else 'REVISE_GEOMETRY',
                compatible_before=previous_coverage,compatible_after=len(chosen['joint_state']['compatible_nets']),
                reason=('Compatible coverage improved' if len(chosen['joint_state']['compatible_nets'])>previous_coverage else
                    'Actual insertion conflicts decreased' if tuple(chosen['joint_state']['repair_burden'])<before[1] else
                    'New conditional branches or completed repair arrangements') if improved else 'No compatible coverage or insertion constraint improvement',
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
        execution.span(chosen['index'])
        emit('exact_layout',candidate=len(attempts)+1,candidate_limit=exact_limit)
        try:
            result=run_exact(target,definitions,threads,modifiers,folder=folder,cancelled=cancelled,
                progress=lambda d:emit('exact_layout',candidate=len(attempts)+1,candidate_limit=exact_limit,exact_progress=d))
        except RuntimeError as exc:
            if cancelled():raise
            result=dict(status='EXACT_UNAVAILABLE',validation=None,design=target.model_dump(),error=str(exc),failures=[],full_cad_evaluated=False)
        counters['exact_attempts']+=1;attempts.append(dict(layout_index=chosen['index'],index=len(attempts),**result))
        chosen['assessment']={**chosen['assessment'],'full_exact_status':result['status'],
            'full_exact_outcome':{k:result.get(k) for k in ('status','topology','step','error','full_cad_evaluated')}}
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
        else:
            record_state(chosen,Design.model_validate(chosen['design']))
            engineering.observe(Design.model_validate(chosen['design']),chosen['assessment'],chosen.get('engineering_decision'))
            # A real complete manufacturing witness has been found. Do not
            # spend the rest of the layout batch cycling alternative poses.
            break
    if not records:
        records=[dict(index=0,family='initial-scaffold',design=original.model_dump(),assessment=dict(status='SOURCE_LAYOUT_REJECTED',compatible=False,
            score=(1,),feasibility_score=(1,),blocked_nets=[],conflicts=[['source_envelope']],route_features=[]))]
        record_state(records[0],original)
    # Spend the reserved LOCAL admission on the best actual partial geometry,
    # not on an early diagnostic assignment. Full acceptance remains separate.
    if not any(a['status']=='EXACT_FEASIBLE' for a in attempts):
        admit_final_cores(records,route_session,record_state,emit)
        for row in records:
            if row.get('engineering_decision'):
                engineering.observe(Design.model_validate(row['design']),row['assessment'],row['engineering_decision'])
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
        ready=selected['joint_state']['source_layout_status']=='SOURCE_LAYOUT_READY'
        status='SOURCE_LAYOUT_READY_ROUTING_PENDING' if ready else 'SOURCE_LAYOUT_REJECTED'
        # Preserve the useful layout AND real compatible partial machining.
        # These are proposals, not manufacturing approval or implicit Model
        # permission to resize/replan. Missing Nets remain explicitly pending.
        cuts=[Feature.model_validate(f) for f in selected['assessment'].get('partial_routing',{}).get('features',[])]
        output.features.extend(cuts)
        for net in output.nets:
            if net.routing=='automatic':
                net.route_state='proposal' if any(f.route_net==net.id for f in cuts) else 'unresolved'
                net.routing_variant=None
                net.route_issue='AI routing is not fully accepted. Review retained constraints or explicitly Reroute; Model preserves source positions.'
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
    result['engineering_planner']=engineering.diagnostics()
    result['joint_solver_summary']=dict(geometry_states=len(route_session.solver.states),
        conditional_constraints=sum(len(s.constraints) for s in route_session.solver.states.values()),
        repair_transactions=sum(len(s.transactions) for s in route_session.solver.states.values()),
        completed_transactions=sum(len(t.completed) for s in route_session.solver.states.values() for t in s.transactions.values()),
        delivered_transaction_results=sum(len(t.delivered) for s in route_session.solver.states.values() for t in s.transactions.values()),
        conditional_fragment_probes=sum(t.probes for s in route_session.solver.states.values() for t in s.transactions.values()),
        continuation_states=len(route_session.search_context.searches),
        newly_expanded_labels=sum(s.budget['used'] for s in route_session.search_context.searches.values()),
        source_layout_status=selected['joint_state']['source_layout_status'],
        routing_status='FULL_EXACT_ACCEPTED' if accepted else selected['joint_state']['routing_status'])
    result['local_admission_summary']=route_session.local_admission.diagnostics() if route_session.local_admission else None
    result['hard_constraint_conflicts']=constraint_conflicts(original,definitions,domain,threads,modifiers)
    result['outcome_classification']='EXACT_FEASIBLE' if accepted else 'PROVEN_HARD_CONSTRAINT_CONFLICT' if result['hard_constraint_conflicts'] else 'UNRESOLVED_SEARCH_OR_ENGINEERING'
    if evidence_dir:atomic_json(Path(evidence_dir)/'layout-search.json',result)
    return result
