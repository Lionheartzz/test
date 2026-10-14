"""Prepare existing reviewed inputs; retain the historical replay harness.

Only storage is isolated. No solver, Router, CAD, scheduler or recognition
function is replaced. --prepare validates the exact input without Generate.
The full replay is suspended after the user's stop instruction. Only bounded
source-snapshot checks are currently authorized; do not use this as a retry loop.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manifold import store, timing
from manifold.ai_design import generation,service
from manifold.ai_design.generation_models import GenerationRequest


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-complex',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'output/runtime-checks/engineering-planner-20261014/preflight-after-cancel')
    args=parser.parse_args()
    if args.run_complex:raise RuntimeError('Full complex Generate is suspended by user instruction. Valid machining corridors and reduced ineffective search must be demonstrated and reviewed first.')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    reviewed=ROOT/'output/runtime-checks/phase-c-closure-20261013/normal-generate-final-verified/reviewed-inputs.json'
    inputs=read(reviewed);key='343f91fdb98c435296b6e78322157433'
    task_path=ROOT/'projects/ai-design'/f'{key}.json';run_path=ROOT/'output/ai-design'/key/'current.json'
    protected=read(ROOT/'output/runtime-checks/phase-c-closure-20261013/protected-before.json')
    before={p:sha(Path(p)) for p in protected};assert before==protected,'Protected inputs changed before replay'
    frozen={str(p.relative_to(ROOT)):sha(p) for p in [*sorted((ROOT/'manifold').rglob('*.py')),Path(__file__).resolve()]}
    if args.run_complex:
        marker=out/'generate-started.json'
        if marker.exists():raise RuntimeError('This complex replay has already started; preserve its evidence instead of rerunning')
    # Local copies are the normal service's read/write roots. The real Model
    # project directory and original task/run remain untouched.
    store.PROJECT=out/'projects/demo.json';store.OUTPUT=out/'output'
    record=read(task_path);raw_run=read(run_path)
    store.atomic_json(out/'original-analysis-run.json',raw_run)
    record['inputs']=inputs['inputs'];record.pop('port_corrections',None);record['generations']=[]
    replay={**raw_run,'inputs':inputs['inputs'],'result':inputs['result'],
            'input_revision':service.digest(inputs['inputs'])}
    record['latest_run']={**record['latest_run'],'input_revision':replay['input_revision']}
    store.atomic_json(service.path(key),record)
    store.atomic_json(service.run_path(key,replay['id']),replay)
    for document in inputs['inputs']['documents']:
        asset=document['asset'];suffix={'image/png':'.png','image/jpeg':'.jpg','application/pdf':'.pdf'}[asset['media_type']]
        source=ROOT/'projects/assets'/(asset['sha256']+suffix)
        destination=store.PROJECT.parent/'assets'/source.name
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        assert sha(destination)==asset['sha256']
    request=GenerationRequest(expected_revision=service.revision(record),run_id=replay['id'],options=inputs['options'])
    check=generation.preflight(key,request)
    provenance=dict(reviewed_input=str(reviewed),reviewed_sha256=sha(reviewed),original_task_sha256=sha(task_path),
        original_run_sha256=sha(run_path),offline_reviewed_result_sha256=service.digest(inputs['result']),
        source_frozen=frozen,protected_before=before,provider_called=False,
        storage_scope=str(out),algorithm_replacements=[],preflight=check)
    store.atomic_json(out/'preflight.json',provenance)
    if not check['ready']:raise RuntimeError('Existing reviewed input failed normal preflight: '+str(check['blocked']))
    if not args.run_complex:
        print(json.dumps(dict(ready=True,components=len(check['components']),protected_count=len(before))));return
    store.atomic_json(marker,dict(source_frozen=frozen,input_sha256=sha(reviewed),started_at=service.now()))
    start=time.monotonic();cpu_start=time.process_time();last=-30.;events=out/'progress.jsonl'
    def progress(value):
        nonlocal last
        now=time.monotonic()-start;item=dict(elapsed_s=round(now,3),**value)
        with events.open('a',encoding='utf-8') as f:f.write(json.dumps(item,ensure_ascii=False)+'\n')
        store.atomic_json(out/'latest-progress.json',item)
        if now-last>=30:
            p=value.get('progress',{});print(json.dumps(dict(elapsed_s=round(now,1),stage=p.get('stage'),layout=p.get('layout'),message=value.get('message')),ensure_ascii=False),flush=True);last=now
    try:
        result=generation.generate(key,request,progress=progress)
        after={p:sha(Path(p)) for p in before};current={p:sha(ROOT/p) for p in frozen}
        store.atomic_json(out/'result.json',result)
        from manifold.engineering import executor
        worker_metrics=[{k:j.get(k) for k in ('id','cpu_s','elapsed_s','exit_code','state')}
                        for j in executor.history if j.get('operation')=='ai-layout-exact']
        store.atomic_json(out/'acceptance-summary.json',dict(status=result['status'],elapsed_s=round(time.monotonic()-start,3),
            parent_cpu_s=time.process_time()-cpu_start,worker_metrics=worker_metrics,
            route_status=result.get('route_status'),manufacturing_ready=(result.get('validation') or {}).get('manufacturing_ready',False),
            protected_before=before,protected_after=after,protected_unchanged=before==after,
            source_frozen_through_run=frozen==current,call_chain=['generation.generate','context','prepare','candidate',
                '_plan_generated_layout','plan_new','optimize','EngineeringDecisionController','shared Router','LocalAdmission'],
            generation_id=result['id'],diagnostics=timing.summary()))
        assert before==after and frozen==current
        print(json.dumps(dict(status=result['status'],route_status=result.get('route_status'),elapsed_s=round(time.monotonic()-start,3)),ensure_ascii=False),flush=True)
    except Exception as exc:
        store.atomic_json(out/'failure.json',dict(error=type(exc).__name__,message=str(exc),elapsed_s=time.monotonic()-start,
            protected_unchanged=before=={p:sha(Path(p)) for p in before},source_frozen_through_run=frozen=={p:sha(ROOT/p) for p in frozen}))
        raise


if __name__=='__main__':main()
