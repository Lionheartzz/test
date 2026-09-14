"""Drawing coordinator; isolated native projections can be terminated on cancellation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import RLock
import time
import uuid

POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pmc-drawing')
JOBS={}
LOCK=RLock()


def start(project_id,operation):
    with LOCK:
        for key,row in list(JOBS.items()):
            if row['state'] in ('completed','failed','cancelled') and time.time()-row['created']>3600:
                del JOBS[key]
        if sum(r['state'] in ('queued','running','committing') for r in JOBS.values())>=4:
            raise ValueError('Drawing queue is full. Wait for a drawing job to finish or cancel it.')
        key=uuid.uuid4().hex
        JOBS[key]=dict(id=key,project_id=project_id,state='queued',message='Queued',created=time.time(),cancel=False,result=None)
    def progress(message,*_):
        with LOCK:
            row=JOBS[key]
            if row['cancel']:
                raise InterruptedError('Drawing job cancelled; saved documents are retained.')
            row['state']='running'
            row['message']=message
    def commit(action):
        with LOCK:
            progress('Saving completed drawing')
            JOBS[key]['state']='committing'
            return action()
    progress.commit=commit
    def run():
        try:
            progress('Reading the saved build')
            result=operation(progress)
            with LOCK:
                JOBS[key].update(state='completed',message='Completed',result=result)
        except InterruptedError as exc:
            with LOCK:JOBS[key].update(state='cancelled',message=str(exc))
        except (ValueError,FileNotFoundError,RuntimeError) as exc:
            with LOCK:JOBS[key].update(state='failed',message=str(exc))
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Local drawing job failed')
            with LOCK:JOBS[key].update(state='failed',message='Drawing generation failed. The saved document is retained; check the local service log and retry.')
    POOL.submit(run)
    return dict(job_id=key)


def get(project_id,key):
    with LOCK:
        row=JOBS.get(key)
        if not row or row['project_id']!=project_id:
            raise FileNotFoundError('Drawing job not found')
        return deepcopy({k:v for k,v in row.items() if k!='cancel'})


def cancel(project_id,key):
    with LOCK:
        get(project_id,key)
        if JOBS[key]['state'] not in ('queued','running'):
            return get(project_id,key)
        JOBS[key]['cancel']=True
    return get(project_id,key)
