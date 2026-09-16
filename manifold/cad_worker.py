"""Private subprocess entrypoint. Only the server writes requests into owned temp dirs."""
import json
from pathlib import Path
import sys
from . import timing


def dispatch(operation,payload,engineering_complete=None,proposal_ready=None):
    from .schema import Design
    from .routing import resolve_design,authorize_generated_contacts
    from .geometry import build_geometry,review_model
    from .validation import validate
    from . import store
    if operation in ('preview','preview-solid'):
        design=Design.model_validate(payload)
        resolved,routes=resolve_design(design,exact=False)
        if operation=='preview':return dict(design=resolved.model_dump(),routes=routes,status='UNVALIDATED_PREVIEW')
        if proposal_ready:proposal_ready(dict(design=resolved.model_dump(),routes=routes,status='UNVALIDATED_PREVIEW'))
        geometry=build_geometry(resolved)
        try:model=review_model(resolved,geometry)
        except Exception as exc:raise RuntimeError('Exact BRep construction completed; display review unavailable: '+(str(exc) or type(exc).__name__)) from exc
        return dict(model=model,features=[f.model_dump() for f in resolved.features],
                    design_revision=store.revision(design),status='UNVALIDATED_EXACT_GEOMETRY',route_selection='CURRENT_PROPOSAL_NOT_OPTIMIZED')
    if operation=='build':
        return store.build_outputs(Design.model_validate(payload['design']),store.OUTPUT/'builds'/payload['build_id'],engineering_complete=engineering_complete)
    if operation=='optimize':
        from .optimization import search_routes
        return search_routes(Design.model_validate(payload['design']),payload['max_attempts'])
    if operation=='validate':
        resolved,routes,_,report=resolve_design(Design.model_validate(payload),prepared=True)
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


def main():
    work=Path(sys.argv[1]);request=json.loads((work/'request.json').read_text(encoding='utf-8'))
    timing.configure(request['trace'])
    try:
        with timing.phase('worker.startup'):
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
        with timing.phase('operation.'+request['operation']):result=dispatch(request['operation'],request['payload'],completed,proposal)
    except Exception as exc:
        result=dict(error=str(exc)[:2000] or type(exc).__name__,status=422)
    with timing.phase('result.serialization'):
        temp=work/'result.tmp';temp.write_text(json.dumps(result),encoding='utf-8');temp.replace(work/'result.json')
        # Small, separate protocol status lets the API return large preview JSON
        # verbatim without decoding/re-encoding every mesh coordinate on its loop.
        (work/'result-status.json').write_text(json.dumps({k:result[k] for k in ('error','status') if k in result and 'error' in result}),encoding='utf-8')
    timing.publish(force=True)


if __name__=='__main__':main()
