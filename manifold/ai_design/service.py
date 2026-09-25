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
from .models import TaskInput,HydraulicRepresentation,validate_context
from .providers import AnalysisRequest,DocumentContent,ProviderFailure,available_providers
from .knowledge import UnavailableKnowledgeResolver,resolve_knowledge
from .diagnostics import Diagnostics, TOKENS, failure_help


class Conflict(ValueError):pass

def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def folder():return store.PROJECT.parent/'ai-design'
def identifier(value):
    if not re.fullmatch('[0-9a-f]{32}',value):raise ValueError('Invalid analysis ID')
    return value
def path(key):return folder()/(identifier(key)+'.json')
def run_path(key,run_id):
    identifier(run_id)
    return store.OUTPUT/'ai-design'/identifier(key)/'current.json'
def read(key):return json.loads(path(key).read_text(encoding='utf-8'))
def revision(record):return digest(record)
def check(record,expected):
    if revision(record)!=expected:raise Conflict('Analysis changed. Reopen it before saving; your input is preserved.')
def snapshot(record):
    latest=record.get('latest_run')
    attempt=record.get('runs',[])[-1] if record.get('runs') else None
    return {**record,'latest_attempt':attempt,'revision':revision(record),'stale':bool(latest and latest['input_revision']!=digest(record['inputs']))}
def write(record,previous=None):
    record['updated_at']=now();store.atomic_json(path(record['id']),record)
    return snapshot(record)


def compact_result(result:HydraulicRepresentation):
    """Drop transient observation provenance before persisting product intent."""
    claims={row.id:row for row in result.claims}
    def facts(ids):
        rows={}
        for key in ids:
            claim=claims[key]
            rows[claim.predicate]=claim.value if claim.status=='confirmed' else None
        return rows
    components=[]
    for row in result.components:
        values=facts(row.claim_ids)
        components.append(dict(id=row.id,port_ids=row.port_ids,label=values.pop('label',row.id),facts=values,
            identity_valid={name:bool(next((c for c in result.claims if c.subject_id==row.id and c.predicate==name and c.status=='confirmed' and c.kind in ('schematic','user_requirement')),None)) for name in ('manufacturer','model','cavity')}))
    ports=[]
    for row in result.ports:
        values=facts(row.claim_ids)
        ports.append(dict(id=row.id,component_id=row.component_id,label=values.pop('label',row.id),facts=values,disposition=row.disposition,
            fact_kinds={claims[key].predicate:claims[key].kind for key in row.claim_ids},
            fact_units={claims[key].predicate:claims[key].unit for key in row.claim_ids}))
    nets=[]
    for row in result.nets:
        values=facts(row.claim_ids)
        nets.append(dict(id=row.id,members=row.members,label=values.get('label') or row.id))
    intent=[]
    for row in result.design_intent:
        claim=claims[row.claim_id]
        intent.append(dict(id=row.id,category=row.category,target_labels=row.target_labels,property=row.property,
            operator=row.operator,strength=row.strength,bound_entity_ids=row.bound_entity_ids,
            value=claim.value if claim.status=='confirmed' else None,unit=claim.unit))
    return dict(schema_version=2,components=components,ports=ports,nets=nets,design_intent=intent,
                unresolved=[dict(id=row.id,subject_ids=row.subject_ids,reason=row.reason,description=row.description,question=row.question) for row in result.unresolved],
                warnings=list(result.warnings))


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
        record={**previous,'inputs':inputs.model_dump()} if previous else dict(schema_version=2,id=uuid.uuid4().hex,inputs=inputs.model_dump(),created_at=now(),runs=[],latest_run=None)
        return write(record,previous)


def list_tasks():
    rows=[]
    for item in folder().glob('*.json'):
        try:
            record=read(item.stem);state=snapshot(record)
            rows.append(dict(id=record['id'],title=record['inputs']['title'],updated_at=record['updated_at'],documents=len(record['inputs']['documents']),stale=state['stale'],latest_run=record.get('latest_run'),latest_attempt=state['latest_attempt']))
        except (ValueError,OSError,KeyError):continue
    return sorted(rows,key=lambda r:r['updated_at'],reverse=True)


def load_run(key,run_id):
    read(key)
    run=json.loads(run_path(key,run_id).read_text(encoding='utf-8'))
    if run['task_id']!=key or run['id']!=run_id:raise ValueError('Analysis run identity mismatch')
    if run.get('error'):run['error_message']=failure_help(run['error'])
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
    request=AnalysisRequest(inputs=inputs.model_copy(deep=True),documents=documents,result_schema=HydraulicRepresentation.model_json_schema())
    run_id=uuid.uuid4().hex
    run=dict(schema_version=1,id=run_id,task_id=key,created_at=now(),input_revision=digest(record['inputs']),inputs=record['inputs'],
             provider=dict(id=provider.id,model=provider.model,is_mock=provider.is_mock,contract_version=1),status='failed',result=None,error=None)
    started=time.perf_counter()
    phase='provider_call'
    try:
        if any(d.media_type not in provider.supported_media for d in documents):raise ProviderFailure('UNSUPPORTED_MEDIA')
        response=provider.analyze(request)
        # Persist reported usage before downstream admission can fail.
        usage={k:getattr(response,k) for k in TOKENS}
        usage.update(cost=response.cost,currency=response.currency)
        if any(v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0) for k,v in usage.items() if k!='currency'):raise ProviderFailure('INVALID_PROVIDER_RESULT')
        if response.currency is not None and not re.fullmatch('[A-Z]{3}',response.currency):raise ProviderFailure('INVALID_PROVIDER_RESULT')
        run['usage']=usage
        if response.diagnostics is not None:run['diagnostics']=Diagnostics.model_validate(response.diagnostics).model_dump()
        if response.metadata is not None:run['adapter']=response.metadata
        phase='admission'
        serialized=json.dumps(response.representation,allow_nan=False)
        result=validate_context(HydraulicRepresentation.model_validate(response.representation),inputs)
        phase='knowledge_resolution'
        result=resolve_knowledge(result,UnavailableKnowledgeResolver())
        validate_context(result,inputs,provider_output=False)
        run.update(status='completed',result=compact_result(result),usage=usage)
        phase='completed'
    except ProviderFailure as exc:
        run['error']=exc.code
        if exc.diagnostics is not None:
            try:
                run['diagnostics']=Diagnostics.model_validate(exc.diagnostics).model_dump()
                run['usage']={**run['diagnostics']['usage'],'cost':None,'currency':None}
                phase=run['diagnostics']['phase']
            except (ValueError,TypeError):pass
    except TimeoutError:run['error']='PROVIDER_TIMEOUT'
    except (ValueError,TypeError,KeyError):run['error']='INVALID_PROVIDER_RESULT'
    except Exception:run['error']='PROVIDER_FAILED'
    run['phase']=phase
    if run['error']:run['error_message']=failure_help(run['error'])
    run['latency_ms']=round((time.perf_counter()-started)*1000,2)
    # Persist only the current compact operational result; detailed observations
    # and evidence exist only inside this analyze call.
    store.atomic_json(run_path(key,run_id),run)
    with store.project_lock():
        latest=read(key)
        if revision(latest)!=expected:raise Conflict('Analysis inputs changed during execution. Run '+run_id+' was retained without replacing the current result.')
        summary={k:run[k] for k in ('id','created_at','input_revision','provider','status','error','latency_ms','phase')}
        for k in ('usage','diagnostics','error_message'):
            if k in run:summary[k]=run[k]
        updated={**latest,'runs':[summary]}
        if run['status']=='completed':updated['latest_run']=summary
        state=write(updated,latest)
    return dict(task=state,run=run)


def export(key,run_id=None):
    record=read(key)
    chosen=run_id or (record.get('latest_run') or {}).get('id')
    run=load_run(key,chosen) if chosen else None
    return dict(kind='pmc-ai-analysis',schema_version=2,task=snapshot(record),run=run,
                asset_transfer='Assets remain separate local files; this JSON contains no document binaries.',
                scope='Current normalized hydraulic intent only. Not a manifold Design, CAD model or manufacturing approval.')
