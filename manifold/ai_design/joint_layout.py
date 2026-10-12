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
             initial=None,evidence_dir=None):
    from ..engineering_db import thread_definitions_for_design,modifier_definitions_for_design,tool_definitions
    from ..layout_planning import _fits
    from ..routing import terminal_points,route_objective
    from ..store import revision,atomic_json
    from .layout_search import screen,_columns
    from .initialization import initial_candidates,route_feedback,constraint_conflicts
    from .route_catalog import Session
    if not 1<=layout_limit<=128 or not 0<=exact_limit<=8:raise ValueError('Invalid AI layout calculation budget')
    original=design.model_copy(deep=True);source_revision=revision(original)
    threads=thread_definitions_for_design(original);modifiers=modifier_definitions_for_design(original) if any(f.machining_modifiers for f in original.features) else {}
    tools=tool_definitions('drill');serial=itertools.count();queue=[];frames=[];seen=set();records=[];attempts=[]
    counters=dict(layouts=0,transforms=0,source_rejected=0,duplicate_transforms=0,exact_attempts=0)
    inspected=set();routing_rejections=[];hypotheses={};family_counts={};schedule=itertools.cycle(('size','face','group','individual','feedback'))
    route_session=Session();assessments={};feedback_queued=set();feedback_streak=0
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
        blocked=set((previous or {}).get('blocked_nets',[]))
        from .design_space import topology_cost_for
        cheap=(family!='initial-scaffold',not fits,len(conflicts),
            not bool(reason and reason.get('requires_route_regeneration')),
            len(blocked) if previous else len(target.nets),
            -len((previous or {}).get('partial_routing',{}).get('nets',[])),
            topology_cost_for(target,definitions,blocked) if blocked else topology_cost(target,definitions),
            math.prod(dimensions(target.block)))
        heapq.heappush(queue,(cheap,next(serial),target,family,parent,conflicts,fits))
    enqueue(original,'initial-scaffold')
    if initial:initial(original.model_copy(deep=True))
    # Retained source-column packing is one optional fast seed; it is no longer
    # the root or the sole placement family. Generic actions work without it.
    columns=_columns(original,definitions,domain.movable,domain.dimension_axes,domain.fixed_faces)
    if columns and domain.accepts(original,columns[0]):enqueue(columns[0],'source-columns')
    frames.append((original,iter(initial_candidates(original,definitions,domain,threads,modifiers))))
    frames.append((original,iter(actions(original,definitions,domain,threads,modifiers))))
    def expand_page():
        if not frames or counters['transforms']>=transform_limit:return False
        parent,iterator=frames.pop(0);exhausted=False
        for _ in range(4):
            if counters['transforms']>=transform_limit:break
            try:
                item=next(iterator);family,target=item[:2];reason=item[2] if len(item)>2 else None
            except StopIteration:exhausted=True;break
            emit('layout_alternate');counters['transforms']+=1;enqueue(target,family,parent,reason)
        if not exhausted:frames.append((parent,iterator))
        return True
    def bucket(row):
        target,family=row[2:4]
        if family=='initial-scaffold':return 'initial'
        if family.startswith('feedback-'):return 'feedback'
        if family=='face-arrangement':return 'face'
        if dimensions(target.block)!=dimensions(original.block):return 'size'
        if any(f.face!=g.face for f,g in zip(target.features,original.features)):return 'face'
        return 'group' if family in ('source-columns','connected-group','topology-repack') else 'individual'
    def pop_diverse():
        nonlocal feedback_streak
        available={bucket(row) for row in queue}
        measured=any(bucket(row)=='feedback' and hypotheses.get(signature(row[2]),{} ) and
            hypotheses[signature(row[2])].get('requires_route_regeneration') for row in queue)
        category=('initial' if 'initial' in available else 'feedback' if measured and feedback_streak<2
                  else next(c for c in schedule if c in available))
        feedback_streak=feedback_streak+1 if category=='feedback' else 0
        index=min((i for i,row in enumerate(queue) if bucket(row)==category),key=lambda i:queue[i][:2])
        row=queue.pop(index);heapq.heapify(queue);family_counts[category]=family_counts.get(category,0)+1
        return row
    def scan(until):
        while counters['layouts']<until and (queue or frames):
            emit('layout_alternate')
            expand_page()
            if not queue:
                if not frames or counters['transforms']>=transform_limit:break
                continue
            _,_,target,family,parent,conflicts,fits=pop_diverse();counters['layouts']+=1
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
                hypothesis=hypotheses.get(signature(target)),
                geometry_changes=dict(dimensions=[list(dimensions(original.block)),list(dimensions(target.block))],placements=changes))
            records.append(row)
            if evidence_dir:
                atomic_json(Path(evidence_dir)/'layouts'/f'{row["index"]:03}.json',row)
            assessments[signature(target)]=detail
            focus=_focus(target,detail.get('conflicts',[]))
            if counters['transforms']<transform_limit:
                if detail['status']=='SOURCE_LAYOUT_REJECTED':
                    frames.append((target,iter(actions(target,definitions,domain,threads,modifiers,focus))))
                elif not detail.get('compatible'):
                    frames.insert(0,(target,iter(route_feedback(target,detail,definitions,domain,threads,modifiers))))
                    feedback_queued.add(row['index'])
    def analytic_rank(row):
        a=row['assessment'];objective=a['score'][len(a['feasibility_score']):]
        # Across different stock sizes, material use precedes marginal extra
        # wall ABOVE the engineering minimum. Fixed-geometry Router priorities
        # are untouched; their plug/drill/depth/envelope order stays intact.
        return (a['status']=='SOURCE_LAYOUT_REJECTED',not a.get('compatible',False),tuple(a['feasibility_score']),
            -len(a.get('partial_routing',{}).get('nets',[])),
            tuple(objective[:-1]),math.prod(dimensions(Design.model_validate(row['design']).block)),objective[-1:] ,row['index'])
    # Spend cheap layout work before CAD, then revise layout after Exact failure
    # instead of exhausting increasingly elaborate fixed-geometry drillings.
    # React after a small layout batch, not after sixteen unrelated layouts.
    # This does not increase layouts, transforms, labels or Exact attempts.
    rounds=max(1,(layout_limit+3)//4);refinement_remaining=exact_limit*1024
    for turn in range(rounds):
        scan(max(1,layout_limit*(turn+1)//rounds))
        if not exact_limit or len(attempts)>=exact_limit:continue
        eligible=[r for r in records if r['index'] not in inspected and r['assessment']['status']!='SOURCE_LAYOUT_REJECTED']
        if not eligible:continue
        chosen=min(eligible,key=analytic_rank);target=Design.model_validate(chosen['design'])
        inspected.add(chosen['index'])
        if not chosen['assessment'].get('compatible') and refinement_remaining and (
                not chosen['assessment'].get('blocked_nets') or not chosen['assessment'].get('spatial_feedback')):
            points=terminal_points(target,definitions)
            lanes={n.id:sum(points[m][1] for m in n.members)/len(n.members) for n in target.nets if len(n.members)>=2}
            planes={n.id:sum(points[m][2] for m in n.members)/len(n.members) for n in target.nets if len(n.members)>=2}
            labels=min(1024,refinement_remaining);refinement_remaining-=labels
            chosen['assessment']=screen(target,definitions,threads,modifiers,tools,lanes,planes,
                lambda stage,**d:emit(stage,**d),include_routes=True,corridor_labels=labels,general_families=True,route_session=route_session)
            chosen['assessment']['routing_refinement']='SHARED_3D_PLANNER_BOUNDED_BEFORE_NEXT_LAYOUT_REVISION'
        route=[Feature.model_validate(f) for f in chosen['assessment']['route_features']]
        missing=[n.id for n in target.nets if n.routing=='automatic' and n.route_state in ('unresolved','proposal') and
                 len(n.members)>=2 and not any(f.route_net==n.id for f in route)]
        if missing:
            # An empty/missing machining network is not a complete Exact
            # candidate. Keep its corridor/retention evidence, revise geometry,
            # and leave the full CAD budget available rather than testing air.
            routing_rejections.append(dict(layout_index=chosen['index'],status='INCOMPLETE_ROUTING_PROPOSAL',missing_nets=missing,
                partial_routing=chosen['assessment'].get('partial_routing'),feedback=chosen['assessment'].get('layout_feedback')))
            if chosen['index'] not in feedback_queued:
                frames.insert(0,(target,iter(route_feedback(target,chosen['assessment'],definitions,domain,threads,modifiers))))
                feedback_queued.add(chosen['index'])
            continue
        if not chosen['assessment'].get('compatible'):
            routing_rejections.append(dict(layout_index=chosen['index'],status='INCOMPATIBLE_ROUTING_PROPOSAL',
                conflicts=chosen['assessment'].get('conflicts'),partial_routing=chosen['assessment'].get('partial_routing'),
                witnesses=chosen['assessment'].get('witnesses')))
            continue
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
            feedback={**chosen['assessment'], 'blocked_nets':[n.id for n in target.nets if {m.split(':')[0] for m in n.members}&focus],
                'exact_failures':result.get('failures',[])}
            source=Design.model_validate(chosen['design'])
            frames.insert(0,(source,iter(route_feedback(source,feedback,definitions,domain,threads,modifiers))))
    if not records:
        records=[dict(index=0,family='initial-scaffold',design=original.model_dump(),assessment=dict(status='SOURCE_LAYOUT_REJECTED',compatible=False,
            score=(1,),feasibility_score=(1,),blocked_nets=[],conflicts=[['source_envelope']],route_features=[]))]
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
    result['packing_diagnostics']=domain._packing_diagnostics
    result['hard_constraint_conflicts']=constraint_conflicts(original,definitions,domain,threads,modifiers)
    result['outcome_classification']='EXACT_FEASIBLE' if accepted else 'PROVEN_HARD_CONSTRAINT_CONFLICT' if result['hard_constraint_conflicts'] else 'UNRESOLVED_SEARCH_OR_ENGINEERING'
    if evidence_dir:atomic_json(Path(evidence_dir)/'layout-search.json',result)
    return result
