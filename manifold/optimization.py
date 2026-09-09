"""Bounded exact search over deterministic route alternatives. Does not save the project."""
import uuid
from . import store
from .geometry import build_geometry
from .validation import validate
from .routing import resolve_design, route_options, route_cost, authorize_generated_contacts
from .kinematics import resolve_parents


def optimize_routes(design, expected_revision, max_attempts=6):
    with store.project_lock():
        if store.revision(store.read_design()) != expected_revision:
            raise ValueError('Project changed on disk. Reload before optimizing.')
        folder = store.OUTPUT/'optimizations'/uuid.uuid4().hex
        attempts = []

        def evaluate(candidate, reason):
            target, routes = resolve_design(candidate)
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
            return score, target, routes, index

        best = design.model_copy(deep=True)
        score,target,routes,index = evaluate(best,'Baseline')
        chosen = index
        # Try the most promising alternatives for one net at a time; accept only lexicographic improvements.
        net_ids = [n.id for n in best.nets if n.routing == 'automatic']
        inspected = set()
        changed = True
        while len(attempts) < max_attempts and changed:
            changed = False
            proposals = []
            for net_id in net_ids:
                context = resolve_parents(best)
                context.features = [f for f in target.features if f.route_net != net_id]
                net = next(n for n in context.nets if n.id == net_id)
                selected = next(r['variant'] for r in routes if r['net'] == net_id)
                for option in route_options(context,net):
                    key = (store.revision(best),net_id,option['key'])
                    if key in inspected or option['key'] == selected:
                        continue
                    proposals.append((option['risk'],option['cost'],net_id,option['key'],key))
                    # Keep alternatives across nets rather than exhaust one net before considering the others.
                    break
            if not proposals:
                break
            for _,_,net_id,variant,key in sorted(proposals):
                if len(attempts) >= max_attempts:
                    break
                inspected.add(key)
                candidate = best.model_copy(deep=True)
                next(n for n in candidate.nets if n.id == net_id).routing_variant = variant
                trial,new_target,new_routes,new_index = evaluate(candidate,f'{net_id}: {variant}')
                changed = True
                if trial < score:
                    best,score,target,routes,chosen = candidate,trial,new_target,new_routes,new_index
                    break
        if store.revision(store.read_design()) != expected_revision:
            raise ValueError('Project changed during optimization. Candidate evidence retained; newer project preserved.')
        summary = dict(optimization_id=folder.name, selected_attempt=chosen, attempts=attempts,
                       status=attempts[chosen]['status'], baseline=attempts[0]['counts'], final=attempts[chosen]['counts'],
                       improved=chosen != 0, message='Exact geometry search only. Save & Validate runs STEP round trip and saves the chosen editable project.')
        store.atomic_json(folder/'summary.json',summary)
        return dict(design=best.model_dump(),**summary)
