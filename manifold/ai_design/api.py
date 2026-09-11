from fastapi import APIRouter,HTTPException
from fastapi.responses import JSONResponse
from pydantic import Field
from ..schema import Strict
from .models import TaskInput,ClaimReview,Digest,RecordId,HydraulicRepresentation
from .providers import provider_info
from . import service

router=APIRouter(prefix='/api/ai-design')

def call(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except service.Conflict as exc:raise HTTPException(409,str(exc)) from None
    except FileNotFoundError:raise HTTPException(404,'Analysis or asset was not found') from None
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    except OSError:raise HTTPException(503,'Local analysis storage is unavailable') from None

class SaveRequest(Strict):
    inputs: TaskInput
    task_id: RecordId | None = None
    expected_revision: Digest | None = None

class RunRequest(Strict):
    expected_revision: Digest
    provider: str = Field(min_length=1,max_length=80)

class ReviewRequest(Strict):
    expected_revision: Digest
    decisions: list[ClaimReview] = Field(min_length=1,max_length=2000)

@router.get('/providers')
def providers():return provider_info()

@router.get('/schema')
def schema():return HydraulicRepresentation.model_json_schema()

@router.get('/tasks')
def tasks():return call(service.list_tasks)

@router.post('/tasks')
def save(payload:SaveRequest):return call(service.save,payload.inputs,payload.task_id,payload.expected_revision)

@router.get('/tasks/{key}')
def get(key:str):return call(lambda:service.snapshot(service.read(key)))

@router.post('/tasks/{key}/analyze')
def analyze(key:str,payload:RunRequest):return call(service.analyze,key,payload.expected_revision,payload.provider)

@router.get('/tasks/{key}/runs/{run_id}')
def run(key:str,run_id:str):return call(service.load_run,key,run_id)

@router.post('/tasks/{key}/runs/{run_id}/review')
def review(key:str,run_id:str,payload:ReviewRequest):return call(service.review,key,run_id,payload.expected_revision,payload.decisions)

@router.get('/tasks/{key}/export')
def export(key:str,run_id:str|None=None):
    return JSONResponse(call(service.export,key,run_id),headers={'Content-Disposition':'attachment; filename="pmc-ai-analysis.json"'})
