"""Single local AI job at a time, with bounded progress and restart-visible failure."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import uuid
from .. import store
from . import service

_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pmc-ai')
_guard=threading.Lock()
_active=None
_process=uuid.uuid4().hex


def path(key):return store.OUTPUT/'ai-jobs'/(service.identifier(key)+'.json')


def read(key):
    record=json.loads(path(key).read_text(encoding='utf-8'))
    if record['status'] in ('queued','running') and record['process']!=_process:
        record.update(status='interrupted',message='The local service restarted. Inputs and completed evidence are retained; rerun the operation.')
    return {k:v for k,v in record.items() if k not in ('process','request')}


def current():
    with _guard:
        return read(_active) if _active else None


def start(task_id,operation,payload):
    global _active
    service.identifier(task_id)
    with _guard:
        if _active:
            raise service.Conflict('Another AI operation is running. Wait for it to finish before starting a new one.')
        service.check(service.read(task_id),payload['expected_revision'])
        key=uuid.uuid4().hex
        record=dict(id=key,task_id=task_id,operation=operation,status='queued',created_at=service.now(),
                    process=_process,request=payload,message='Queued locally',result=None)
        store.atomic_json(path(key),record)
        _active=key
    _executor.submit(_execute,record)
    return read(key)


def _execute(record):
    global _active
    def update(message):
        record.update(status='running',message=message)
        store.atomic_json(path(record['id']),record)
    try:
        if record['operation']=='analyze':
            update('Rendering documents and calling the selected provider. Waiting for a validated hydraulic result.')
            result=service.analyze(record['task_id'],record['request']['expected_revision'],record['request']['provider'])
        else:
            from .generation import generate
            from .generation_models import GenerationRequest
            result=generate(record['task_id'],GenerationRequest.model_validate(record['request']),update)
        record.update(status='completed',message='Operation completed',result=result)
    except service.Conflict:
        record.update(status='conflict',message='Analysis changed while the operation ran. Earlier inputs and completed run/candidate evidence are retained; reopen the analysis.')
    except (ValueError,FileNotFoundError):
        record.update(status='failed',message='Inputs, source files or selected library revisions need review. Reopen the analysis and run the generation preflight.')
    except RuntimeError:
        record.update(status='failed',message='Another local CAD operation holds the build lock. Retry after it finishes.')
    except Exception:
        record.update(status='failed',message='The local operation could not complete. Inputs are retained; check configuration or simplify the circuit.')
    finally:
        record['completed_at']=service.now()
        store.atomic_json(path(record['id']),record)
        with _guard:
            if _active==record['id']:_active=None
