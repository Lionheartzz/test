"""Private AI-only child; no provider call or Model operation is dispatched."""
import json
from pathlib import Path
import sys
from .. import store,timing
from . import execution


def main():
    control=Path(sys.argv[1]);request=execution.read(control/'request.json')
    store.PROJECT=Path(request['project']);store.OUTPUT=Path(request['output'])
    execution.configure(control);timing.configure(control/'timing.json');timing.trace_occt()
    def progress(value):
        store.atomic_json(control/'progress.json',value)
        with (control/'progress.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(value)+'\n')
        if value.get('initial_generation_id'):
            store.atomic_json(control/'identity.json',dict(generation_id=value['initial_generation_id']))
        timing.publish(force=True)
    try:
        payload=request['payload']
        if payload['operation']=='generate':
            from .generation import _generate
            from .generation_models import GenerationRequest
            result=_generate(payload['task_id'],GenerationRequest.model_validate(payload['request']),progress,
                cancelled=lambda:(control/'cancel.json').exists(),publish=False)
        elif payload['operation']=='plan-snapshot':
            # Trusted offline diagnostic entry, not an API or a second Router.
            from ..schema import Design,CavityDefinition
            from ..engineering_db import definitions_for_design
            from .layout_search import plan_new
            d=Design.model_validate(payload['design'])
            execution.checkpoint(d,status='UNVALIDATED_SOURCE_SNAPSHOT',priority=0)
            defs={k:CavityDefinition.model_validate(v) for k,v in payload.get('definitions',{}).items()} or definitions_for_design(d)
            result=plan_new(d,defs,movable_features={f.id for f in d.features},layout_limit=payload.get('layout_limit',1),
                exact_limit=payload.get('exact_limit',0),cancelled=lambda:(control/'cancel.json').exists(),
                progress=lambda stage,**detail:progress(dict(message=stage,progress=dict(stage=stage,**detail))))
        elif payload['operation']=='screen-snapshot':
            from ..schema import Design,Feature
            from ..engineering_db import definitions_for_design,thread_definitions_for_design,modifier_definitions_for_design
            from ..routing import route_obstructions
            from ..engineering_conditions import effective_net
            d=Design.model_validate(payload['design']);execution.span(0)
            execution.checkpoint(d,status='SAVED_SOURCE_SNAPSHOT_REQUIRES_RECHECK',priority=0)
            defs=definitions_for_design(d);threads=thread_definitions_for_design(d)
            modifiers=modifier_definitions_for_design(d) if any(f.machining_modifiers for f in d.features) else {}
            net=effective_net(d,next(n for n in d.nets if n.id==payload['net']))
            cuts=[Feature.model_validate(f) for f in payload['features']];cache=execution.cache()
            with timing.phase('snapshot.production_router_screen'):
                failures=route_obstructions(d,net,cuts,threads,defs,modifiers,cache)
            result=dict(status='MACHINING_REJECTED' if failures else 'ANALYTIC_CLEAR_REQUIRES_CONNECTIVITY',
                failures=sorted(failures),measurements=[dict(kind=k[0],value=v) for k,v in cache.get('local_measurements',{}).items()],
                cache_lookups=cache.counts,manufacturing_ready=False,timing=timing.summary())
        else:raise ValueError('Unsupported private AI operation')
        store.atomic_json(control/'result.json',result)
    except BaseException as exc:
        store.atomic_json(control/'failure.json',dict(error=type(exc).__name__,message=str(exc),
            cad_error=getattr(exc,'record',None),timing=timing.summary()))
    finally:timing.publish(force=True)


if __name__=='__main__':main()
