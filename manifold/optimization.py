"""Bounded exact search over deterministic route alternatives. Does not save the project."""
import uuid
from . import store
from .geometry import build_geometry
from .validation import validate
from .routing import resolve_design, route_cost, authorize_generated_contacts, alternative_proposals


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
        folder = store.OUTPUT/'optimizations'/uuid.uuid4().hex
        attempts = []

        def evaluate(candidate, reason):
            # This outer search owns the exact-attempt budget. Resolve one proposal only.
            target, routes = resolve_design(candidate,exact=False)
            index = len(attempts)
            attempt = folder/f'attempt-{index:02}'
            store.atomic_json(attempt/'design.json',candidate.model_dump())
            cad_error=False
            try:
                geometry = build_geometry(target)
                authorize_generated_contacts(target,geometry)
                report = validate(target,geometry)
            except Exception as exc:
                cad_error=True
                report=dict(status='FAIL',counts=dict(FAIL=1,WARNING=0,PASS=0),
                            checks=[dict(rule='cad_candidate_error',status='FAIL',error=type(exc).__name__)])
            cost = route_cost(candidate,[f for f in target.features if f.kind == 'drilling' and not f.suppressed])
            score = (1_000_000 if cad_error else report['counts']['FAIL'],report['counts']['WARNING'],cost)
            record = dict(index=index,reason=reason,status=report['status'],counts=report['counts'],cost=cost,
                          design_revision=store.revision(candidate),routes=routes)
            store.atomic_json(attempt/'resolved_design.json',target.model_dump())
            store.atomic_json(attempt/'validation.json',report)
            attempts.append(record)
            return score, target, routes, index, report

        best = design.model_copy(deep=True)
        score,target,routes,index,report = evaluate(best,'Baseline')
        for net in best.nets:
            if net.routing == 'automatic':
                net.routing_variant = next(r['variant'] for r in routes if r['net'] == net.id)
        chosen = index
        eligible={n.id for n in best.nets if n.routing=='automatic'}
        inspected={tuple(sorted((r['net'],r['variant']) for r in routes))}
        while len(attempts)<max_attempts:
            proposals=alternative_proposals(best,target,routes,report,eligible,inspected)
            if not proposals:break
            _,candidate,signature,reason=proposals[0]
            inspected.add(signature)
            trial,new_target,new_routes,new_index,new_report=evaluate(candidate,reason)
            if trial<score:
                best,score,target,routes,chosen,report=candidate,trial,new_target,new_routes,new_index,new_report
        if saved_revision() != expected_revision:
            raise ValueError('Project changed during optimization. Candidate evidence retained; newer project preserved.')
        summary = dict(optimization_id=folder.name, selected_attempt=chosen, attempts=attempts,
                       status=attempts[chosen]['status'], baseline=attempts[0]['counts'], final=attempts[chosen]['counts'],
                       improved=chosen != 0, message='Exact geometry search only. Save & Validate runs STEP round trip and saves the chosen editable project.')
        store.atomic_json(folder/'summary.json',summary)
        return dict(design=best.model_dump(),**summary)
