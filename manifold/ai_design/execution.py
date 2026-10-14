"""AI-owned execution deadlines; never used by Model or the shared Router.

The supervisor owns a ProcessJob, so a native Boolean cannot hold the service's
GIL or defeat cancellation. Checkpoints are explicit unaccepted Design values.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .. import store,timing
from ..process_job import ProcessJob

_channel=None
_stage={}
_last_work_write=0.


def enabled():return _channel is not None


def work_due():return enabled() and time.monotonic()-_last_work_write>=1


class DiagnosticCache(dict):
    """Count dictionary lookups, not invented saved-CAD-time estimates."""
    def __init__(self,values=(),counts=None):
        super().__init__(values);self.counts=counts if counts is not None else dict(hits=0,misses=0)
    def __contains__(self,key):
        found=dict.__contains__(self,key);self.counts['hits' if found else 'misses']+=1;return found
    def get(self,key,default=None):
        self.counts['hits' if dict.__contains__(self,key) else 'misses']+=1
        return dict.get(self,key,default)
    def __getitem__(self,key):
        self.counts['hits' if dict.__contains__(self,key) else 'misses']+=1
        return dict.__getitem__(self,key)
    def setdefault(self,key,default=None):
        if dict.__contains__(self,key):
            self.counts['hits']+=1;return dict.__getitem__(self,key)
        self.counts['misses']+=1
        value=DiagnosticCache(default,self.counts) if type(default) is dict else default
        dict.__setitem__(self,key,value);return value


def cache():return DiagnosticCache() if enabled() else {}


def cache_metrics(session):
    maps=[session.cache,*[c[1] for c in session.contexts.values()]];seen=set();counts=[]
    for c in maps:
        if isinstance(c,DiagnosticCache) and id(c.counts) not in seen:
            seen.add(id(c.counts));counts.append(dict(c.counts))
    return dict(meaning='dictionary lookup events; not unique geometric calculations',contexts=counts,
        hits=sum(c['hits'] for c in counts),misses=sum(c['misses'] for c in counts))


def read(path,default=None):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return default


def configure(folder):
    global _channel,_stage
    _channel=Path(folder);_stage={}


def span(layout,*,deep=False):
    global _stage
    if _channel is None:return
    _stage=dict(layout=layout,deep=deep)
    store.atomic_json(_channel/'stage.json',_stage)


def checkpoint(design,*,status,assessment=None,evidence=None,priority=0):
    if _channel is None:return
    old=read(_channel/'checkpoint.json',{})
    if old.get('priority',-1)>priority:return
    store.atomic_json(_channel/'checkpoint.json',dict(design=design.model_dump(mode='json'),status=status,
        assessment=assessment,evidence=evidence,priority=priority,manufacturing_ready=False,
        updated_at=time.time(),timing=timing.summary()))


def work_state(value):
    global _last_work_write
    if _channel is not None and time.monotonic()-_last_work_write>=1:
        store.atomic_json(_channel/'frontier.json',value);_last_work_write=time.monotonic()


class Deadlines:
    def __init__(self,total=600,layout=120,deep=90,*,clock=time.monotonic):
        self.clock=clock;self.started=self.last=clock();self.total=total or 600
        self.layout_limit=layout;self.deep_limit=deep;self.layouts={};self.deep=0.;self.active={}
    def advance(self,stage):
        now=self.clock();delta=now-self.last;self.last=now
        owner=self.active.get('layout')
        if owner is not None:self.layouts[owner]=self.layouts.get(owner,0)+delta
        if self.active.get('deep'):self.deep+=delta
        self.active=stage or {}
        if now-self.started>=self.total:return 'TOTAL_TIME_LIMIT'
        if owner is not None and self.layouts[owner]>=self.layout_limit:return 'LAYOUT_TIME_LIMIT'
        if self.deep>=self.deep_limit:return 'DEEP_ROUTING_TIME_LIMIT'
    def diagnostics(self):
        return dict(limits_s=dict(total=self.total,layout=self.layout_limit,deep=self.deep_limit),
            elapsed_s=self.clock()-self.started,layout_active_s=self.layouts,deep_active_s=self.deep)


def supervise(payload,*,limits,progress=lambda value:None,cancelled=lambda:False):
    """Private trusted worker protocol. Inputs and all evidence stay local."""
    from ..engineering_db import database_path
    control=store.OUTPUT/'ai-generation-execution'/uuid.uuid4().hex;control.mkdir(parents=True)
    store.atomic_json(control/'request.json',dict(payload=payload,project=str(store.PROJECT.resolve()),output=str(store.OUTPUT.resolve())))
    env={**os.environ,'PMC_ENGINEERING_DB':str(database_path()),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    runtime=sys.executable
    if os.name=='nt' and not getattr(sys,'frozen',False):
        runtime=str(Path(sys.base_prefix)/'python.exe');env['__PYVENV_LAUNCHER__']=sys.executable
    budget=Deadlines(**limits);reason=None;last_progress=None;stop_at=None;forced=False
    with (control/'worker.log').open('wb') as log:
        process=ProcessJob([runtime,'-m','manifold.ai_design.execution_worker',str(control.resolve())],
            cwd=str(store.ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
        try:
            while process.process.poll() is None:
                stage=read(control/'stage.json',budget.active)
                expired=budget.advance(stage)
                if reason is None and (cancelled() or expired):
                    reason='USER_CANCELLED' if cancelled() else expired;stop_at=time.monotonic()
                    store.atomic_json(control/'cancel.json',dict(reason=reason,**budget.diagnostics()))
                item=read(control/'progress.json')
                identity=read(control/'identity.json',{})
                if item and identity.get('generation_id') and payload.get('operation')=='generate':
                    item.update(initial_generation_id=identity['generation_id'],
                        initial_draft_url=f"/api/ai-design/tasks/{payload['task_id']}/generations/{identity['generation_id']}/project")
                if item and item!=last_progress:progress(item);last_progress=item
                if reason and time.monotonic()-stop_at>=1:
                    process.stop();forced=True;break
                time.sleep(.05)
            final_expiry=budget.advance(read(control/'stage.json',budget.active))
            if reason is None:reason='USER_CANCELLED' if cancelled() else final_expiry
            metrics=process.metrics();result=read(control/'result.json')
            summary=dict(reason=reason or ('COMPLETED' if result is not None else 'WORKER_ERROR'),
                forced_tree_stop=forced,pid=process.process.pid,exit_code=process.process.poll(),worker_metrics=metrics,
                **budget.diagnostics(),execution_grants_approval=False)
            summary['worker_failure']=read(control/'failure.json')
            store.atomic_json(control/'execution.json',summary)
        finally:
            if process.process.poll() is None:process.stop()
            process.close()
    return dict(result=result,checkpoint=read(control/'checkpoint.json'),progress=last_progress,
                execution=summary,evidence=str(control),frontier=read(control/'frontier.json'))


def generate(key,request,progress,*,cancelled):
    from . import generation,service
    _,run,_,_=generation.context(key,request.run_id,request.expected_revision)
    options=request.options
    outcome=supervise(dict(operation='generate',task_id=key,request=request.model_dump()),
        limits=dict(total=options.max_runtime_s or 600,layout=options.max_layout_runtime_s,deep=options.max_deep_runtime_s),
        progress=progress,cancelled=cancelled)
    result=outcome['result'];reason=outcome['execution']['reason'];saved=outcome['checkpoint']
    failure=outcome['execution'].get('worker_failure') or {}
    if reason=='WORKER_ERROR' and not saved:
        if failure.get('error')=='Conflict':raise service.Conflict(failure.get('message','Analysis changed'))
        raise ValueError('AI worker could not construct a draft: '+failure.get('message','Inspect execution evidence'))
    if reason=='COMPLETED' and result is not None:
        if 'id' not in result:return result
    else:
        # Initial draft events identify the owned generation even if the worker
        # was interrupted inside native CAD. Never overwrite a Model project.
        control=Path(outcome['evidence']);identity=read(control/'identity.json',{})
        gid=identity.get('generation_id')
        if not gid:return dict(status='cancelled' if reason=='USER_CANCELLED' else 'incomplete_draft',
            design=None,validation=None,manufacturing_ready=False,route_status=reason,
            message='Stopped before a draft was constructed. Analysis and source inputs retained.',execution=outcome['execution'],evidence=outcome['evidence'])
        folder=store.OUTPUT/'ai-design'/key/'generations'/gid
        result=read(folder/'generation.json',{})
        result.update(id=gid,task_id=key,run_id=run['id'],status='cancelled' if reason=='USER_CANCELLED' else 'incomplete_draft',
            route_status=reason,validation=None,attempts=[],manufacturing_ready=False,
            message=reason+'. Last safely checkpointed design retained; routing and manufacturing acceptance are incomplete.',
            created_at=service.now(),source_task_revision=request.expected_revision,input_revision=run['input_revision'],
            provider=run['provider'],options=options.model_dump(),engine_revision=store.engine_revision())
        if saved:
            result.update(design=saved['design'],layout_planning=dict(scope='AI_GENERATION_ONLY',status=saved['status'],
                selected=saved.get('assessment'),checkpoint=saved.get('evidence'),manufacturing_ready=False))
    result['execution']=outcome['execution'];result['execution_evidence']=outcome['evidence']
    folder=store.OUTPUT/'ai-design'/key/'generations'/result['id']
    return generation._publish_generation(key,request,run,result,folder)
