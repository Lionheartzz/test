"""One disposable CAD process. Previews are expendable; authoritative work has priority.

No OCCT calls run here. Killing the owned process tree is essential: cancelling a
Python future/thread cannot interrupt a native Boolean that holds the GIL.
"""
import asyncio
import atexit
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from .process_job import ProcessJob


class CalculationError(RuntimeError):
    def __init__(self,message,status=422):super().__init__(message);self.status=status


class Executor:
    def __init__(self,command=None):
        self.lock=threading.RLock();self.active=None;self.history=[];self.versions={};self.cancelled={}
        self.command=command or [sys.executable,'-m','manifold.cad_worker']

    def status(self):
        with self.lock:
            row=self.active
            return dict(active=self.describe(row) if row else None,recent=self.history[-12:])

    def describe(self,row):
        try:detail=json.loads(row['trace'].read_text(encoding='utf-8'))
        except (OSError,ValueError):detail={}
        return {**detail,**row['process'].metrics(),'id':row['id'],'operation':row['operation'],'pid':row['process'].process.pid,
                'elapsed_s':round(time.monotonic()-row['start'],3),'limit_s':row['limit'],'exit_code':row['process'].process.poll()}

    def start(self,operation,payload,*,transient=False,owner='',version=0,limit=None):
        from . import store
        from .engine import assert_engine_current,engine_revision
        assert_engine_current()
        limit=limit or (15 if transient else 300)
        with self.lock:
            if transient and owner:
                if version<self.versions.get(owner,-1) or version<=self.cancelled.get(owner,-1):raise CalculationError('Preview superseded by a newer draft.',409)
                self.versions[owner]=version
                if len(self.versions)>256:self.versions.pop(next(iter(self.versions)))
            if self.active:
                if self.active['transient']:
                    self.stop(self.active,'Preview superseded by newer work.',409)
                else:raise CalculationError('An authoritative engineering calculation is running. Try again when it finishes.',409)
            key=uuid.uuid4().hex;work=Path(tempfile.mkdtemp(prefix='pmc-cad-'))
            traces=store.OUTPUT/'cad-diagnostics';traces.mkdir(parents=True,exist_ok=True)
            trace=traces/(key+'.json')
            request=dict(operation=operation,payload=payload,output=str(store.OUTPUT.resolve()),project=str(store.PROJECT.resolve()),
                         engine_revision=engine_revision(),trace=str(trace.resolve()))
            (work/'request.json').write_text(json.dumps(request),encoding='utf-8')
            env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
            command=[*self.command,str(work)]
            if os.name=='nt' and command[0]==sys.executable and not getattr(sys,'frozen',False):
                # Store/venv aliases can activate a Python process outside the job.
                # Launch the actual interpreter, using CPython's venv redirect
                # contract to retain precisely this environment and dependencies.
                runtime=Path(sys.base_prefix)/'python.exe'
                if not runtime.is_file():
                    shutil.rmtree(work)
                    raise CalculationError('Unable to locate the actual Python runtime for isolated CAD.',503)
                command[0]=str(runtime);env['__PYVENV_LAUNCHER__']=sys.executable
            try:process=ProcessJob(command,cwd=str(store.ROOT),env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except BaseException:shutil.rmtree(work);raise
            row=dict(id=key,operation=operation,process=process,work=work,trace=trace,start=time.monotonic(),limit=limit,
                     transient=transient,owner=owner,version=version,error=None,closed=False)
            self.active=row
            row['timer']=threading.Timer(limit,self.expire,args=(row,));row['timer'].daemon=True;row['timer'].start()
            return row

    def expire(self,row):
        with self.lock:
            if not row['closed']:
                completed=self.completed_engineering(row)
                if completed is not None:
                    # Only a build checkpoint written AFTER every engineering
                    # check and STEP/manufacturing artifact can survive review.
                    row['process'].stop();row['fallback']=completed
                    row['warning']='Display review exceeded its time budget; exact engineering evidence retained.'
                    self.finish(row,'engineering-complete-review-timeout')
                    return
                self.stop(row,f'{"Exact preview" if row["transient"] else "Engineering calculation"} exceeded {row["limit"]:g} seconds; worker stopped. '
                          'Last usable view and saved project retained. Inspect calculation diagnostics or retry after revising the draft.',504)

    def completed_engineering(self,row):
        if row['operation']!='build':return None
        try:return json.loads((row['work']/'engineering-complete.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):return None

    def stop(self,row,message,status=409):
        with self.lock:
            if row['closed']:return
            row['error']=CalculationError(message,status);row['process'].stop();self.finish(row,'cancelled' if status!=504 else 'timeout')

    def finish(self,row,state):
        if row['closed']:return
        row['timer'].cancel();record={**self.describe(row),'state':state}
        if row['error']:record['reason']=str(row['error'])
        if row.get('warning'):record['reason']=row['warning']
        self.history.append(record);self.history=self.history[-12:]
        row['process'].close();row['closed']=True
        if self.active is row:self.active=None
        # Only our explicitly created temporary directory; no caller path participates.
        try:
            shutil.rmtree(row['work'])
            row['trace'].with_suffix('.tmp').unlink(missing_ok=True)
            row['trace'].write_text(json.dumps(record),encoding='utf-8')
            files=sorted(row['trace'].parent.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
            for old in files[100:]:old.unlink(missing_ok=True)
        except OSError as exc:
            # A full disk or diagnostic retention error must not leave the lane busy.
            record['diagnostic_error']=type(exc).__name__

    def poll(self,row,*,raw=False):
        with self.lock:
            if row['error']:raise row['error']
            if 'fallback' in row:return row['fallback']
            if row['process'].process.poll() is None:
                if not row.get('review_deadline') and self.completed_engineering(row) is not None:
                    row['review_deadline']=True;row['timer'].cancel()
                    remaining=max(.01,min(15,row['limit']-(time.monotonic()-row['start'])))
                    row['timer']=threading.Timer(remaining,self.expire,args=(row,));row['timer'].daemon=True;row['timer'].start()
                return None
            try:
                if row['process'].process.returncode!=0:
                    raise CalculationError(f'CAD worker exited with code {row["process"].process.returncode}; result rejected. Inspect calculation diagnostics and retry.',422)
                path=row['work']/'result.json'
                if path.stat().st_size>64_000_000:raise CalculationError('Exact result exceeds the interactive transfer limit; saved engineering evidence is retained.',422)
                status=json.loads((row['work']/'result-status.json').read_text(encoding='utf-8'))
                if 'error' in status:raise CalculationError(status['error'],status.get('status',422))
                result=path.read_bytes() if raw else json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError) as exc:
                row['error']=CalculationError('CAD worker exited without a usable result. Inspect calculation diagnostics and retry.',422)
                self.finish(row,'failed');raise row['error'] from exc
            except CalculationError as exc:
                row['error']=exc;self.finish(row,'failed');raise
            self.finish(row,'completed');return result

    def cancel(self,owner,version):
        with self.lock:
            self.cancelled[owner]=max(version,self.cancelled.get(owner,-1))
            if len(self.cancelled)>256:self.cancelled.pop(next(iter(self.cancelled)))
            if self.active and self.active['transient'] and self.active['owner']==owner and self.active['version']<=version:
                self.stop(self.active,'Preview cancelled because its draft is no longer current.',409)

    def proposal(self,row):
        with self.lock:
            if row['closed']:return None
            try:return (row['work']/'proposal.json').read_bytes()
            except OSError:return None

    def close(self):
        with self.lock:
            if self.active:self.stop(self.active,'Service stopped.',503)


executor=Executor();atexit.register(executor.close)


async def calculate(operation,payload,request=None,*,transient=False,limit=None,raw=False):
    owner=request.headers.get('x-pmc-preview-owner','')[:80] if request else ''
    try:version=int(request.headers.get('x-pmc-preview-version','0')) if request else 0
    except ValueError:raise CalculationError('Invalid preview version',422)
    row=await asyncio.to_thread(executor.start,operation,payload,transient=transient,owner=owner,version=version,limit=limit)
    try:
        while True:
            result=await asyncio.to_thread(executor.poll,row,raw=raw)
            if result is not None:return result
            if transient and request and await request.is_disconnected():
                await asyncio.to_thread(executor.stop,row,'Preview client disconnected.',409)
            await asyncio.sleep(.05)
    finally:
        if not row['closed']:await asyncio.to_thread(executor.stop,row,'Request cancelled; saved project retained.',409)


async def preview_stream(payload,request):
    """One snapshot/process: early proposal then exact result, never a second resolve."""
    owner=request.headers.get('x-pmc-preview-owner','')[:80]
    try:version=int(request.headers.get('x-pmc-preview-version','0'))
    except ValueError:raise CalculationError('Invalid preview version',422)
    row=await asyncio.to_thread(executor.start,'preview-solid',payload,transient=True,owner=owner,version=version)
    async def events():
        sent=False
        try:
            while True:
                if not sent:
                    proposal=await asyncio.to_thread(executor.proposal,row)
                    if proposal is not None:
                        yield b'{"type":"proposal","result":'+proposal+b'}\n';sent=True
                result=await asyncio.to_thread(executor.poll,row,raw=True)
                if result is not None:
                    # Mesh JSON was serialized in the CAD process. Do not walk
                    # every coordinate on the API event loop a second time.
                    yield b'{"type":"exact","result":'+result+b'}\n'
                    return
                await asyncio.sleep(.05)
        except CalculationError as exc:
            yield (json.dumps(dict(type='error',detail=str(exc),status=exc.status))+'\n').encode()
        finally:
            if not row['closed']:await asyncio.to_thread(executor.stop,row,'Preview stream disconnected.',409)
    return events()


def calculate_sync(operation,payload,progress=None):
    row=executor.start(operation,payload)
    try:
        while True:
            result=executor.poll(row)
            if result is not None:return result
            if progress:progress('Exact CAD: '+executor.describe(row).get('phase','starting isolated worker'))
            time.sleep(.1)
    finally:
        if not row['closed']:executor.stop(row,'Calculation no longer relevant.',409)
