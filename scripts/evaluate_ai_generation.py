"""Offline production Generate from an already reviewed source-only Design.

Reuse accepted identities, interface dispositions and Nets without recognition.
Compile a NEW candidate through prepare/candidate, initialization, joint search
and the production Exact worker. Never publish or change the source project.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manifold import store,engineering_db as db
from manifold.schema import Design
from manifold.ai_design import generation,service
from manifold.ai_design.models import TaskInput,InputDocument
from manifold.ai_design.generation_models import GenerationOptions


def reviewed_inputs(source):
    if any(f.route_net or f.frozen_net or f.kind=='drilling' for f in source.features) or any(
        n.routing_variant or n.route_state!='unresolved' for n in source.nets):
        raise ValueError('Reviewed source-only requirements required, not existing authored routes')
    if not source.schematic_intent:raise ValueError('Reviewed component/interface intent is required')
    result=dict(components=[],ports=[],nets=[],design_intent=[],evidence=[],claims=[])
    bindings={};port_definitions={};terminals={};labels={c.placement_id:c for c in source.schematic_intent.components};external_count=0
    for f in source.features:
        if f.suppressed:continue
        if f.kind not in ('cavity','port'):raise ValueError('This offline adapter requires reviewed cavities/ports')
        definition=db.get_definition(f.definition) if f.definition else None
        if f.kind=='cavity':
            if definition is None:raise ValueError('Reviewed cavity definition is required')
            intent=labels[f.id];key=intent.id;mapping={z.id:key+'_I'+str(i) for i,z in enumerate(definition.zones,1)}
            product=db.cartridge(f.cartridge_id) if f.cartridge_id else {}
            facts=dict(cavity=definition.label,model=product.get('model'),manufacturer=product.get('manufacturer'))
            result['components'].append(dict(id=key,label=intent.label,port_ids=list(mapping.values()),facts=facts,
                identity_valid={k:bool(v) for k,v in facts.items()},observed_identity_annotations=[]))
            bindings[key]=dict(definition_key='db:'+definition.id,definition_sha256=service.digest(definition.model_dump()),
                zone_ports=mapping,decision='Existing reviewed source interface mapping')
            for z in definition.zones:
                disposition=intent.interface_dispositions.get(z.id,'unknown')
                if z.id in f.circuits:disposition='connected'
                result['ports'].append(dict(id=mapping[z.id],component_id=key,label=z.id,
                    disposition=disposition,facts={}))
                terminals[f.id+':'+z.id]=mapping[z.id]
        else:
            external_count+=1;key='EXT_'+str(external_count)
            result['ports'].append(dict(id=key,component_id=None,label=f.schematic_id or f.id,
                disposition='connected',facts=dict(port_specification=f.size) if f.thread_definition_id else {}))
            if definition:
                port_definitions[key]=dict(definition_key='db:'+definition.id,definition_sha256=service.digest(definition.model_dump()))
            elif not f.thread_definition_id:raise ValueError('Explicit unresolved custom-port intent cannot be guessed')
            terminals[f.id]=key
    for net in source.nets:
        result['nets'].append(dict(id=net.id,label=net.id,members=[terminals[m] for m in net.members],status='confirmed'))
    inputs=TaskInput(title=source.name[:120],project_context=source.project_context,project_engineering=source,
        documents=[InputDocument(id='DOC'+str(i),asset=a,page_count=1) for i,a in enumerate(source.schematic_intent.assets,1)])
    diameters={n.diameter for n in source.nets}
    if len(diameters)!=1:raise ValueError('Preserve per-Net bore requirements through the normalized input before replay')
    options=GenerationOptions(bindings=bindings,port_definitions=port_definitions,drilling_diameter=next(iter(diameters)))
    return inputs,result,options


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare-only',action='store_true');args=p.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(store.OUTPUT.resolve()):raise ValueError('Evidence must stay under output/')
    out.mkdir(parents=True,exist_ok=False)
    protected=[args.source.resolve(),db.database_path(),*sorted((store.PROJECT.parent/'saved').glob('*.json')),
               *sorted((store.PROJECT.parent/'ai-design').glob('*.json'))]
    hashes=lambda:{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in protected}
    before=hashes();store.atomic_json(out/'protected-before.json',before)
    source=Design.model_validate_json(args.source.read_text(encoding='utf-8'))
    inputs,result,options=reviewed_inputs(source)
    store.atomic_json(out/'reviewed-inputs.json',dict(inputs=inputs.model_dump(),result=result,options=options.model_dump()))
    started=time.monotonic();plan=generation.prepare(inputs,result,options)
    store.atomic_json(out/'preflight.json',dict(blocked=plan['blocked'],components=[dict(id=c['id'],definition=c['definition'].id if c['definition'] else None,
        cartridge_id=c.get('cartridge_id'),mapping=c['mapping']) for c in plan['components']]))
    if plan['blocked']:raise ValueError(plan['blocked'])
    if args.prepare_only:
        print(json.dumps(dict(ready=True,seconds=time.monotonic()-started,components=len(plan['components']),nets=len(result['nets']))));return
    events=[];last=[0.]
    def progress(value):
        elapsed=time.monotonic()-started
        if elapsed-last[0]<.3:return
        last[0]=elapsed;packet=dict(elapsed_s=elapsed,**value)
        store.atomic_json(out/'progress.json',packet)
        events.append(packet)
    target,feature_map,terminal_map=generation.candidate(plan,uuid.uuid4().hex,0,progress=progress,
        exact_limit=options.max_exact_attempts,initial=lambda d:store.atomic_json(out/'initial-draft.json',d.model_dump()),
        evidence_dir=out/'layout-optimization')
    planning=plan['settings']['layout_planning'];after=hashes()
    packet=dict(status=planning['status'],elapsed_s=time.monotonic()-started,planning=planning,design=target.model_dump(),
        feature_mapping=feature_map,terminal_mapping=terminal_map,protected_before=before,protected_after=after,
        protected_unchanged=before==after,call_chain='generation.prepare -> generation.candidate -> _plan_generated_layout -> plan_new -> optimize -> shared Router',
        exact_gate='Production Exact executor only after a complete compatible assignment')
    store.atomic_json(out/'result.json',packet);store.atomic_json(out/'events.json',events)
    print(json.dumps({k:packet[k] for k in ('status','elapsed_s','protected_unchanged')},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
