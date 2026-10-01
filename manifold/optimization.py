"""Bounded exact search over deterministic route alternatives. Does not save the project."""
import uuid
from . import store
from .routing import resolve_design, route_objective


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
    # Optimize, Validate and Build use the same authoritative CAD/STEP gates.
    # This request owns one bounded search, never a nested resolver per trial.
    target,routes,_,report=resolve_design(design,prepared=True,persist=True,max_attempts=max_attempts)
    best=design.model_copy(deep=True)
    for net in best.nets:
        if net.routing=='automatic':net.routing_variant=next(r['variant'] for r in routes if r['net']==net.id)
    if routes:
        evidence=store.OUTPUT/'route-selections'/routes[0]['selection_evidence']
        import json
        selection=json.loads((evidence/'summary.json').read_text(encoding='utf-8'))
    else:
        selection=dict(selected_attempt=0,attempts=[dict(index=0,reason='Fixed geometry',status=report['status'],
            counts=report['counts'],cost=0,objective=route_objective(target,[]),routes=[])])
    folder=store.OUTPUT/'optimizations'/uuid.uuid4().hex
    attempts=selection['attempts'];chosen=selection['selected_attempt']
    summary=dict(optimization_id=folder.name,selected_attempt=chosen,attempts=attempts,
        status=attempts[chosen]['status'],baseline=attempts[0]['counts'],final=attempts[chosen]['counts'],
        improved=chosen!=0,message='CAD-safe exact route and production STEP checked. Validate saves the chosen editable project.')
    if routes:summary['selection_evidence']=routes[0]['selection_evidence']
    store.atomic_json(folder/'summary.json',summary)
    return dict(design=best.model_dump(),**summary)
