"""Local analysis persistence and admission. Never writes a Design or a library record."""
import hashlib
import json
import math
import re
import time
import uuid
from datetime import datetime,timezone
from .. import store
from ..workflow import asset_path
from .models import TaskInput,HydraulicRepresentation,ClaimReview,validate_context
from .providers import AnalysisRequest,DocumentContent,ProviderFailure,available_providers
from .knowledge import UnavailableKnowledgeResolver,resolve_knowledge


class Conflict(ValueError):pass

def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def folder():return store.PROJECT.parent/'ai-design'
def identifier(value):
    if not re.fullmatch('[0-9a-f]{32}',value):raise ValueError('Invalid analysis ID')
    return value
def path(key):return folder()/(identifier(key)+'.json')
def run_path(key,run_id):return store.OUTPUT/'ai-design'/identifier(key)/(identifier(run_id)+'.json')
def read(key):return json.loads(path(key).read_text(encoding='utf-8'))
def revision(record):return digest(record)
def check(record,expected):
    if revision(record)!=expected:raise Conflict('Analysis changed. Reopen it before saving; your input is preserved.')
def snapshot(record):
    latest=record.get('latest_run')
    return {**record,'revision':revision(record),'stale':bool(latest and latest['input_revision']!=digest(record['inputs']))}
def write(record,previous=None):
    if previous:store.atomic_json(folder()/'history'/record['id']/(uuid.uuid4().hex+'.json'),previous)
    record['updated_at']=now();store.atomic_json(path(record['id']),record)
    return snapshot(record)


def verified_documents(inputs):
    contents=[]
    for document in inputs.documents:
        asset=document.asset
        data=asset_path(asset).read_bytes()
        if len(data)!=asset.size or hashlib.sha256(data).hexdigest()!=asset.sha256:raise ValueError('Schematic asset identity mismatch')
        if asset.media_type=='application/pdf':
            if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]:raise ValueError('Invalid PDF asset')
        else:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(data)) as image:
                if image.format!={'image/png':'PNG','image/jpeg':'JPEG'}[asset.media_type] or image.width*image.height>40_000_000:raise ValueError('Invalid image asset')
                image.verify()
        contents.append(DocumentContent(document.id,asset.media_type,asset.sha256,data))
    return tuple(contents)


def save(inputs:TaskInput,key=None,expected=None):
    verified_documents(inputs)
    inputs=inputs.model_copy(deep=True)
    for document in inputs.documents:document.page_count=1 if document.asset.media_type.startswith('image/') else None
    if inputs.linked_project_id:
        from ..projects import read as read_project
        read_project(inputs.linked_project_id)  # Link only; no writes or geometry coupling.
    with store.project_lock():
        previous=read(key) if key else None
        if previous:check(previous,expected)
        record={**previous,'inputs':inputs.model_dump()} if previous else dict(schema_version=1,id=uuid.uuid4().hex,inputs=inputs.model_dump(),created_at=now(),runs=[],latest_run=None,reviews={})
        return write(record,previous)


def list_tasks():
    rows=[]
    for item in folder().glob('*.json'):
        try:
            record=read(item.stem);state=snapshot(record)
            rows.append(dict(id=record['id'],title=record['inputs']['title'],updated_at=record['updated_at'],documents=len(record['inputs']['documents']),stale=state['stale'],latest_run=record.get('latest_run')))
        except (ValueError,OSError,KeyError):continue
    return sorted(rows,key=lambda r:r['updated_at'],reverse=True)


def load_run(key,run_id):
    read(key)
    run=json.loads(run_path(key,run_id).read_text(encoding='utf-8'))
    if run['task_id']!=key or run['id']!=run_id:raise ValueError('Analysis run identity mismatch')
    return run


def analyze(key,expected,provider_key):
    with store.project_lock():
        record=read(key);check(record,expected)
    inputs=TaskInput.model_validate(record['inputs'])
    if not inputs.documents:raise ValueError('Add at least one schematic document before analysis')
    providers=available_providers()
    if provider_key not in providers:raise ValueError('Provider is not available')
    provider=providers[provider_key]
    documents=verified_documents(inputs)
    if any(d.media_type not in provider.supported_media for d in documents):raise ValueError('Provider does not support this document type')
    request=AnalysisRequest(inputs=inputs.model_copy(deep=True),documents=documents,result_schema=HydraulicRepresentation.model_json_schema())
    run_id=uuid.uuid4().hex
    run=dict(schema_version=1,id=run_id,task_id=key,created_at=now(),input_revision=digest(record['inputs']),inputs=record['inputs'],
             provider=dict(id=provider.id,model=provider.model,is_mock=provider.is_mock,contract_version=1),status='failed',result=None,error=None)
    started=time.perf_counter()
    try:
        response=provider.analyze(request)
        serialized=json.dumps(response.representation,allow_nan=False)
        if len(serialized.encode())>2_000_000:raise ProviderFailure('INVALID_PROVIDER_RESULT')
        result=validate_context(HydraulicRepresentation.model_validate(response.representation),inputs)
        result=resolve_knowledge(result,UnavailableKnowledgeResolver())
        validate_context(result,inputs,provider_output=False)
        usage=dict(input_tokens=response.input_tokens,output_tokens=response.output_tokens,cost=response.cost,currency=response.currency)
        if any(v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0) for k,v in usage.items() if k!='currency'):raise ProviderFailure('INVALID_PROVIDER_RESULT')
        if response.currency is not None and not re.fullmatch('[A-Z]{3}',response.currency):raise ProviderFailure('INVALID_PROVIDER_RESULT')
        run.update(status='completed',result=result.model_dump(),usage=usage)
        if response.metadata is not None:run['adapter']=response.metadata
    except ProviderFailure as exc:run['error']=exc.code
    except TimeoutError:run['error']='PROVIDER_TIMEOUT'
    except (ValueError,TypeError,KeyError):run['error']='INVALID_PROVIDER_RESULT'
    except Exception:run['error']='PROVIDER_FAILED'
    run['latency_ms']=round((time.perf_counter()-started)*1000,2)
    # Even stale/failed attempts retain immutable, bounded evidence; no raw model body.
    store.atomic_json(run_path(key,run_id),run)
    with store.project_lock():
        latest=read(key)
        if revision(latest)!=expected:raise Conflict('Analysis inputs changed during execution. Run '+run_id+' was retained without replacing the current result.')
        summary={k:run[k] for k in ('id','created_at','input_revision','provider','status','error','latency_ms')}
        updated={**latest,'runs':[*latest['runs'],summary][-100:]}
        if run['status']=='completed':updated['latest_run']=summary
        state=write(updated,latest)
    return dict(task=state,run=run)


def review(key,run_id,expected,decisions:list[ClaimReview]):
    run=load_run(key,run_id)
    if run['status']!='completed':raise ValueError('Only completed analyses can be reviewed')
    claims={c['id']:c for c in run['result']['claims']}
    if len({d.claim_id for d in decisions})!=len(decisions):raise ValueError('Duplicate review claim')
    for decision in decisions:
        if decision.claim_id not in claims:raise ValueError('Review claim is missing')
        if decision.status=='confirmed' and claims[decision.claim_id]['value'] is None:raise ValueError('Correct an unknown value before confirming it')
    with store.project_lock():
        current=read(key);check(current,expected)
        reviews={k:dict(v) for k,v in current['reviews'].items()}
        entries=reviews.setdefault(run_id,{})
        for decision in decisions:entries[decision.claim_id]={**decision.model_dump(),'reviewed_at':now(),'origin':'engineer_review'}
        return write({**current,'reviews':reviews},current)


def export(key,run_id=None):
    record=read(key)
    chosen=run_id or (record.get('latest_run') or {}).get('id')
    run=load_run(key,chosen) if chosen else None
    return dict(kind='pmc-ai-analysis',schema_version=1,task=snapshot(record),run=run,
                asset_transfer='Assets remain separate SHA-256 addressed files; this JSON contains no document binaries.',
                scope='Hydraulic understanding and proposed intent only. Not a manifold Design, CAD model or manufacturing approval.')
