from fastapi import APIRouter,HTTPException,Request,Query
from fastapi.responses import JSONResponse,Response
from pydantic import Field
from ..schema import Strict
from .models import TaskInput,ClaimReview,Digest,RecordId,HydraulicRepresentation
from .providers import provider_info
from . import service
from . import config,jobs,generation,library_resolution
from .generation_models import GenerationRequest

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


def operator_local(request):
    if not request.client or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'Configure AI on the server computer using its loopback URL')


@router.get('/settings')
def settings(request:Request):
    operator_local(request)
    return call(config.public)


@router.post('/settings')
async def save_settings(request:Request):
    operator_local(request)
    try:
        settings=config.ProviderSettings.model_validate(await request.json())
    except (ValueError,TypeError):
        raise HTTPException(422,'Invalid AI settings. Check base URL, model, limits and transport; credentials must not be embedded in URLs.') from None
    return call(config.save,settings)


@router.post('/settings/clear-key')
def clear_settings_key(request:Request):
    operator_local(request)
    return call(config.clear_key)


@router.get('/jobs/current')
def current_job():return jobs.current()


@router.get('/jobs/{job_id}')
def job(job_id:str):return call(jobs.read,job_id)


@router.post('/tasks/{key}/analyze-job')
def analyze_job(key:str,payload:RunRequest):
    return call(jobs.start,key,'analyze',payload.model_dump())


@router.post('/tasks/{key}/generation/preflight')
def generation_preflight(key:str,payload:GenerationRequest):
    return call(generation.preflight,key,payload)


@router.post('/tasks/{key}/generation/jobs')
def generate_job(key:str,payload:GenerationRequest):
    return call(jobs.start,key,'generate',payload.model_dump())


@router.get('/tasks/{key}/generations/{generation_id}')
def get_generation(key:str,generation_id:str):return call(generation.load_generation,key,generation_id)


@router.get('/tasks/{key}/generations/{generation_id}/project')
def generation_project(key:str,generation_id:str):
    packet=call(generation.load_generation,key,generation_id)
    if packet['status']!='draft':raise HTTPException(409,'This generation has no editable draft')
    return JSONResponse(packet['design'],headers={'Content-Disposition':'attachment; filename="ai-manifold-draft.pmc.json"'})


@router.get('/tasks/{key}/library-choices')
def library_choices(key:str,q:str=Query(default='',max_length=120),role:str=Query(default='cartridge-cavity',pattern='^(cartridge-cavity|external-port)$')):
    return call(library_resolution.search,TaskInput.model_validate(call(service.read,key)['inputs']),q,role)


@router.get('/tasks/{key}/runs/{run_id}/page')
def rendered_page(key:str,run_id:str,document_id:str,page:int=Query(ge=1,le=1000)):
    from .documents import render
    run=call(service.load_run,key,run_id)
    inputs=TaskInput.model_validate(run['inputs'])
    documents=call(service.verified_documents,inputs)
    document=next((d for d in documents if d.document_id==document_id),None)
    if document is None:raise HTTPException(404,'Source document not found')
    # Prefer exactly the raster sent to the provider, independent of later settings edits.
    entry=next((p for p in run.get('adapter',{}).get('document_pages',[]) if p['document_id']==document_id and p['page']==page),None)
    side=max(entry['width'],entry['height']) if entry else 2400
    # Renderer cache is keyed by requested size, not the possibly smaller result size.
    side=run.get('adapter',{}).get('image_max_side',side)
    pages=call(render,document,max_pages=24,max_side=side)
    if page>len(pages):raise HTTPException(404,'Source page not found')
    return Response(pages[page-1]['data'],media_type='image/png')
