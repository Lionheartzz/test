"""Private subprocess entrypoint. Only the server writes requests into owned temp dirs."""
import json
from pathlib import Path
import sys
import time
from . import timing

_preview_state=None
_process_started=time.monotonic()


def dispatch(operation,payload,engineering_complete=None,proposal_ready=None,*,exact_not_before=None):
    global _preview_state
    from .schema import Design
    from .routing import resolve_design,authorize_generated_contacts
    from .geometry import build_geometry,review_model,review_layer
    from .validation import validate
    from . import store
    if operation in ('preview','preview-solid'):
        _preview_state=None
        from .preview_routing import PreviewRequest,resolve_preview
        request=PreviewRequest.model_validate(payload) if 'design' in payload else PreviewRequest(design=Design.model_validate(payload))
        design=request.design
        resolved,routes,update=resolve_preview(request)
        proposal=dict(design=resolved.model_dump(),routes=routes,routing_update=update,
                      source_revision=store.revision(design),status='UNVALIDATED_PREVIEW')
        if operation=='preview':return proposal
        condition_resize=update['mode']=='CONDITIONS' and bool(update.get('resized_nets'))
        if proposal_ready and not condition_resize:proposal_ready(proposal)
        if exact_not_before is not None:
            with timing.phase('preview.exact_idle'):
                time.sleep(max(0,exact_not_before-time.monotonic()))
        geometry=build_geometry(resolved)
        # Presentation may identify terminal route branches from exact contacts.
        # This mutates only the worker's resolved preview copy; it is never saved
        # into the authored project. Condition resizing uses the same BRep for
        # its acceptance check below; ordinary drag preview stays unvalidated.
        authorize_generated_contacts(resolved,geometry)
        if condition_resize:
            # One exact check of resized stored cuts, reusing this preview BRep.
            # A failed resize restores the old topology, never searches another.
            checked=validate(resolved,geometry)
            resized=set(update['resized_nets'])
            by_id={f.id:f for f in resolved.features}
            rejected=set()
            for check in checked['checks']:
                if check['status']!='FAIL':continue
                if check['rule'] in ('solid_validity','solid_count'):rejected.update(resized)
                for item in check.get('items',[]):
                    if item in resized:rejected.add(item)
                    feature=by_id.get(str(item).split(':')[0])
                    if feature and feature.route_net in resized:rejected.add(feature.route_net)
            if rejected:
                resolved.features=[f for f in resolved.features if f.route_net not in rejected]
                resolved.features.extend(f.model_copy(deep=True) for f in request.design.features if f.route_net in rejected)
                for net in resolved.nets:
                    if net.id in rejected:
                        net.route_state='stale';net.route_issue=f'Route {net.id} cannot be safely resized for these conditions. Previous drillings retained; Reroute this net.'
                geometry=build_geometry(resolved);authorize_generated_contacts(resolved,geometry)
            from .route_state import route_metadata
            proposal.update(design=resolved.model_dump(),routes=route_metadata(resolved))
            if proposal_ready:proposal_ready(proposal)
        try:model=review_model(resolved,geometry,core_only=True)
        except Exception as exc:raise RuntimeError('Exact BRep construction completed; display review unavailable: '+(str(exc) or type(exc).__name__)) from exc
        design_revision=store.revision(design)
        _preview_state=dict(design_revision=design_revision,design=resolved,geometry=geometry)
        return dict(model=model,features=[f.model_dump() for f in resolved.features],routing_update=update,
                    design_revision=design_revision,status='UNVALIDATED_EXACT_GEOMETRY',route_selection='CURRENT_PROPOSAL_NOT_OPTIMIZED')
    if operation=='preview-layer':
        if _preview_state is None or _preview_state['design_revision']!=payload['design_revision']:
            raise ValueError('Exact preview layer is stale. Wait for the current exact preview and retry.')
        parts=review_layer(_preview_state['design'],_preview_state['geometry'],payload['layer'])
        return dict(design_revision=payload['design_revision'],layer=payload['layer'],parts=parts)
    if operation=='build':
        return store.build_outputs(Design.model_validate(payload['design']),store.OUTPUT/'builds'/payload['build_id'],engineering_complete=engineering_complete)
    if operation=='optimize':
        from .optimization import search_routes
        return search_routes(Design.model_validate(payload['design']),payload['max_attempts'])
    if operation=='validate':
        from .route_state import validate_current_design
        resolved,routes,_,report=validate_current_design(Design.model_validate(payload))
        return dict(design=resolved.model_dump(),routes=routes,report=report)
    if operation=='freeze':
        from .route_edit import freeze
        return freeze(Design.model_validate(payload['design']),payload['net'],Design.model_validate(payload['proposal']) if payload.get('proposal') else None).model_dump()
    if operation=='refine':
        from .route_edit import refine
        from datetime import datetime,timezone
        draft,adjusted,notes=refine(Design.model_validate(payload['design']),payload['feature_id'],payload['u'],payload['v'])
        resolved,_=resolve_design(draft,exact=False);geometry=build_geometry(resolved);authorize_generated_contacts(resolved,geometry)
        report=validate(resolved,geometry);report['generated_at']=datetime.now(timezone.utc).isoformat()
        return dict(design=draft.model_dump(),report=report,adjusted_branches=adjusted,notes=notes,status='EXACT_DRAFT_CHECKS_NOT_SAVED')
    if operation=='drawing-geometry':
        from .drawing.generate import snapshot,geometry_for
        from .drawing.schema import View
        source,solid=snapshot(payload['project_id'],payload['expected'])
        views=[View.model_validate(v) for v in payload['views']]
        with timing.phase('drawing.projection'):geometry=geometry_for(source,solid,views,lambda *_:None)
        return dict(source=source,geometry=geometry)
    raise ValueError('Unknown engineering operation')


def run(work,bootstrap_s=None):
    work=Path(work);request=json.loads((work/'request.json').read_text(encoding='utf-8'))
    timing.configure(request['trace'])
    if request['operation']=='build':timing.progress('preparing',2)
    if bootstrap_s is not None:timing.record('worker.startup',bootstrap_s)
    try:
        with timing.phase('worker.request_setup' if bootstrap_s is not None else 'worker.startup'):
            from . import store
            from .engine import engine_revision
            if engine_revision()!=request['engine_revision']:raise RuntimeError('Engineering code changed. Restart the local server before calculating.')
            store.OUTPUT=Path(request['output']);store.PROJECT=Path(request['project'])
            timing.trace_occt()
        def completed(report):
            store.atomic_json(work/'engineering-complete.json',report)
        def proposal(result):
            temp=work/'proposal.tmp'
            temp.write_text(json.dumps(result),encoding='utf-8');temp.replace(work/'proposal.json')
        with timing.phase('operation.'+request['operation']):result=dispatch(request['operation'],request['payload'],completed,proposal,exact_not_before=request.get('exact_not_before'))
    except Exception as exc:
        result=dict(error=str(exc)[:2000] or type(exc).__name__,status=422)
    if request['operation']=='build':timing.progress('finalizing',99)
    with timing.phase('result.serialization'):
        temp=work/'result.tmp';temp.write_text(json.dumps(result),encoding='utf-8');temp.replace(work/'result.json')
        # Small, separate protocol status lets the API return large preview JSON
        # verbatim without decoding/re-encoding every mesh coordinate on its loop.
        (work/'result-status.json').write_text(json.dumps({k:result[k] for k in ('error','status') if k in result and 'error' in result}),encoding='utf-8')
    timing.publish(force=True)
    (work/'done').write_text('',encoding='utf-8')


def main():
    run(Path(sys.argv[1]))


def warm_preview_main():
    # Import the expensive CAD runtime once. Engineering definitions are still
    # resolved from SQLite for every new immutable preview snapshot.
    from . import cad,engineering_db,geometry,routing,store,engine  # noqa: F401
    bootstrap_s=time.monotonic()-_process_started
    for line in sys.stdin:
        path=line.strip()
        if path:
            run(Path(path),bootstrap_s)
            bootstrap_s=None


if __name__=='__main__':
    warm_preview_main() if len(sys.argv)==2 and sys.argv[1]=='--warm-preview' else main()
