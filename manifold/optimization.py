"""Bounded exact search over deterministic route alternatives. Does not save the project."""
import uuid
from . import store
from .routing import resolve_design, route_objective,exact_route_score


def optimize_routes(design, expected_revision, max_attempts=6, project_id=None):
    if not 1 <= max_attempts <= 12:
        raise ValueError('max_attempts must be between 1 and 12, including the baseline')
    def saved_revision():
        if project_id:
            from .projects import snapshot,read
            return snapshot(read(project_id))['revision']
        return store.revision(store.read_design())
    with store.project_lock():
        if saved_revision() != expected_revision:
            raise ValueError('Project changed on disk. Reload before optimizing.')
    result=search_routes(design,max_attempts)
    with store.project_lock():
        if saved_revision() != expected_revision:
            raise ValueError('Project changed during optimization. Candidate evidence retained; newer project preserved.')
    return result


def search_routes(design,max_attempts=6):
    if not 1 <= max_attempts <= 12:raise ValueError('max_attempts must be between 1 and 12')
    from .route_state import pending_nets,validate_current_design,merge_routes,route_metadata
    current=None
    if not pending_nets(design):
        cad_error=False
        try:current,_,_,current_report=validate_current_design(design)
        except Exception as exc:
            current=design.model_copy(deep=True);cad_error=True
            current_report=dict(status='FAIL',counts=dict(FAIL=1,WARNING=0,PASS=0),checks=[dict(rule='cad_candidate_error',status='FAIL',message=str(exc)[:2000])])
        current_score=exact_route_score(current,current_report,[f for f in current.features if f.kind=='drilling' and not f.suppressed],cad_error=cad_error)
    if current is not None and (max_attempts==1 or not any(n.routing=='automatic' for n in design.nets)):
        folder=store.OUTPUT/'optimizations'/uuid.uuid4().hex
        attempt=dict(index=0,reason='Current stored geometry',status=current_report['status'],counts=current_report['counts'],score=current_score,routes=route_metadata(current))
        summary=dict(optimization_id=folder.name,selected_attempt=0,attempts=[attempt],status=current_report['status'],baseline=current_report['counts'],final=current_report['counts'],improved=False,message='Current stored route retained; comparison budget contains only its exact baseline.')
        store.atomic_json(folder/'summary.json',summary)
        return dict(design=design.model_dump(),source_revision=store.revision(design),**summary)
    # Explicit design action: release only automatic cuts for bounded search.
    source=design.model_copy(deep=True)
    owners={n.id for n in source.nets if n.routing=='automatic'}
    source.features=[f for f in source.features if f.route_net not in owners]
    for net in source.nets:
        if net.id in owners:net.route_state='unresolved';net.route_issue='';net.routing_variant=None
    target,routes,_,report=resolve_design(source,prepared=True,persist=True,max_attempts=max_attempts-(1 if current is not None else 0))
    best=merge_routes(design,target)
    if routes:
        evidence=store.OUTPUT/'route-selections'/routes[0]['selection_evidence']
        import json
        selection=json.loads((evidence/'summary.json').read_text(encoding='utf-8'))
    else:
        selection=dict(selected_attempt=0,attempts=[dict(index=0,reason='Fixed geometry',status=report['status'],
            counts=report['counts'],cost=0,objective=route_objective(target,[]),routes=[])])
    folder=store.OUTPUT/'optimizations'/uuid.uuid4().hex
    attempts=selection['attempts'];chosen=selection['selected_attempt']
    if current is not None:
        target_score=exact_route_score(target,report,[f for f in target.features if f.kind=='drilling' and not f.suppressed])
        attempts=[dict(index=0,reason='Current stored geometry',status=current_report['status'],counts=current_report['counts'],score=current_score,routes=route_metadata(current)),
                  *[{**a,'index':a['index']+1} for a in attempts]]
        chosen+=1
        if current_score<=target_score:best=design.model_copy(deep=True);chosen=0
    summary=dict(optimization_id=folder.name,selected_attempt=chosen,attempts=attempts,
        status=attempts[chosen]['status'],baseline=attempts[0]['counts'],final=attempts[chosen]['counts'],
        improved=chosen!=0,message='Exact route and production STEP checked. Inspect the proposed model; Save Project commits these drillings.')
    if routes:summary['selection_evidence']=routes[0]['selection_evidence']
    store.atomic_json(folder/'summary.json',summary)
    return dict(design=best.model_dump(),source_revision=store.revision(best),**summary)
