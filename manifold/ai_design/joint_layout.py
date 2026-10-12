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
    if not 1<=layout_limit<=128 or not 0<=exact_limit<=8:raise ValueError('Invalid AI layout calculation budget')
    original=design.model_copy(deep=True);source_revision=revision(original)
    threads=thread_definitions_for_design(original);modifiers=modifier_definitions_for_design(original) if any(f.machining_modifiers for f in original.features) else {}
    tools=tool_definitions('drill');serial=itertools.count();queue=[];frames=[];seen=set();records=[];attempts=[]
    counters=dict(layouts=0,transforms=0,source_rejected=0,duplicate_transforms=0,exact_attempts=0)
    inspected=set();routing_rejections=[]
    transform_limit=layout_limit*64
    def emit(stage,**detail):
        if cancelled():
            from ..engineering import CalculationError
            raise CalculationError('AI generation cancelled; initial draft retained.',409)
        if progress:progress(stage,layout=max(1,min(layout_limit,counters['layouts']+int(stage=='layout_alternate'))),
            layout_limit=layout_limit,**detail)
    def enqueue(target,family,parent=None):
        if not domain.accepts(original,target):return
        key=signature(target)
        if key in seen:counters['duplicate_transforms']+=1;return
        seen.add(key)
        fits=_fits(target,definitions)
        conflicts=source_conflicts(target,definitions,threads,modifiers,domain._placement_cache) if fits else []
        cheap=(family!='initial-scaffold',not fits,len(conflicts),topology_cost(target,definitions),math.prod(dimensions(target.block)))
        heapq.heappush(queue,(cheap,next(serial),target,family,parent,conflicts,fits))
    enqueue(original,'initial-scaffold')
    if initial:initial(original.model_copy(deep=True))
    # Retained source-column packing is one optional fast seed; it is no longer
    # the root or the sole placement family. Generic actions work without it.
    columns=_columns(original,definitions,domain.movable,domain.dimension_axes,domain.fixed_faces)
    if columns and domain.accepts(original,columns[0]):enqueue(columns[0],'source-columns')
    frames.append((original,iter(actions(original,definitions,domain,threads,modifiers))))
    def expand_page():
        if not frames or counters['transforms']>=transform_limit:return False
        parent,iterator=frames.pop(0);exhausted=False
        for _ in range(16):
            if counters['transforms']>=transform_limit:break
            try:family,target=next(iterator)
            except StopIteration:exhausted=True;break
            counters['transforms']+=1;enqueue(target,family,parent)
        if not exhausted:frames.append((parent,iterator))
        return True
    def scan(until):
        while counters['layouts']<until and (queue or frames):
            emit('layout_alternate')
            expand_page()
            if not queue:
                if not frames or counters['transforms']>=transform_limit:break
                continue
            _,_,target,family,parent,conflicts,fits=heapq.heappop(queue);counters['layouts']+=1
            if not fits or conflicts:
                counters['source_rejected']+=1
                detail=dict(status='SOURCE_LAYOUT_REJECTED',compatible=False,blocked_nets=[],
                    conflicts=[['source_wall',*p] for p in conflicts]+fit_violations(target,definitions),fixed_conflicts=conflicts,
                    feasibility_score=(1,len(conflicts)+int(not fits)),score=(1,len(conflicts)+int(not fits),topology_cost(target,definitions)),route_features=[])
            else:
                points=terminal_points(target,definitions);lanes={};planes={}
                for net in target.nets:
                    members=[points[m] for m in net.members if m in points]
                    if not members:continue
                    lanes[net.id]=sum(p[1] for p in members)/len(members);planes[net.id]=sum(p[2] for p in members)/len(members)
                detail=screen(target,definitions,threads,modifiers,tools,lanes,planes,
                    lambda stage,**d:emit(stage,**d),include_routes=True,corridor_labels=0,general_families=True)
            old={f.id:f for f in original.features}
            changes=[dict(feature=f.id,parameters={k:[getattr(old[f.id],k),getattr(f,k)] for k in ('face','u','v','rotation')
                if getattr(old[f.id],k)!=getattr(f,k)}) for f in target.features if f!=old[f.id]]
            row=dict(index=len(records),family=family,design=target.model_dump(),assessment=detail,
                geometry_changes=dict(dimensions=[list(dimensions(original.block)),list(dimensions(target.block))],placements=changes))
            records.append(row)
            focus=_focus(target,detail.get('conflicts',[]))
            if counters['transforms']<transform_limit:
                frames.append((target,iter(actions(target,definitions,domain,threads,modifiers,focus))))
    def analytic_rank(row):
        a=row['assessment'];objective=a['score'][len(a['feasibility_score']):]
        # Across different stock sizes, material use precedes marginal extra
        # wall ABOVE the engineering minimum. Fixed-geometry Router priorities
        # are untouched; their plug/drill/depth/envelope order stays intact.
        return (a['status']=='SOURCE_LAYOUT_REJECTED',not a.get('compatible',False),tuple(a['feasibility_score']),
            tuple(objective[:-1]),math.prod(dimensions(Design.model_validate(row['design']).block)),objective[-1:] ,row['index'])
    # Spend cheap layout work before CAD, then revise layout after Exact failure
    # instead of exhausting increasingly elaborate fixed-geometry drillings.
    rounds=max(1,exact_limit)
    for turn in range(rounds):
        scan(max(1,layout_limit*(turn+1)//rounds))
        if not exact_limit:break
        eligible=[r for r in records if r['index'] not in inspected and r['assessment']['status']!='SOURCE_LAYOUT_REJECTED']
        if not eligible:continue
        chosen=min(eligible,key=analytic_rank);target=Design.model_validate(chosen['design'])
        inspected.add(chosen['index'])
        if not chosen['assessment'].get('compatible'):
            points=terminal_points(target,definitions)
            lanes={n.id:sum(points[m][1] for m in n.members)/len(n.members) for n in target.nets if len(n.members)>=2}
            planes={n.id:sum(points[m][2] for m in n.members)/len(n.members) for n in target.nets if len(n.members)>=2}
            chosen['assessment']=screen(target,definitions,threads,modifiers,tools,lanes,planes,
                lambda stage,**d:emit(stage,**d),include_routes=True,corridor_labels=1024,general_families=True)
            chosen['assessment']['routing_refinement']='SHARED_3D_PLANNER_BOUNDED_BEFORE_NEXT_LAYOUT_REVISION'
        route=[Feature.model_validate(f) for f in chosen['assessment']['route_features']]
        missing=[n.id for n in target.nets if n.routing=='automatic' and n.route_state in ('unresolved','proposal') and
                 len(n.members)>=2 and not any(f.route_net==n.id for f in route)]
        if missing:
            # An empty/missing machining network is not a complete Exact
            # candidate. Keep its corridor/retention evidence, revise geometry,
            # and leave the full CAD budget available rather than testing air.
            routing_rejections.append(dict(layout_index=chosen['index'],status='INCOMPLETE_ROUTING_PROPOSAL',missing_nets=missing))
            frames.insert(0,(target,iter(actions(target,definitions,domain,threads,modifiers,
                {m.split(':')[0] for n in target.nets if n.id in missing for m in n.members}))))
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
            frames.insert(0,(target,iter(actions(Design.model_validate(chosen['design']),definitions,domain,threads,modifiers,focus))))
    if not records:
        records=[dict(index=0,family='initial-scaffold',design=original.model_dump(),assessment=dict(status='SOURCE_LAYOUT_REJECTED',compatible=False,
            score=(1,),feasibility_score=(1,),blocked_nets=[],conflicts=[['source_envelope']],route_features=[]))]
    full=[a for a in attempts if a.get('validation')]
    accepted=[a for a in full if a['status']=='EXACT_FEASIBLE']
    if full:
        best=min(full,key=lambda a:(tuple(a['exact_score'][:2]),tuple(a['exact_score'][2][:-1]),
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
    if evidence_dir:atomic_json(Path(evidence_dir)/'layout-search.json',result)
    return result
