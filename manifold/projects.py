"""Local named projects. IDs select fixed files, never caller-provided paths."""
import json
import re
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import Field
from . import store
from .schema import Design, Strict

router = APIRouter(prefix='/api/projects')

def folder():
    return store.PROJECT.parent / 'saved'

def path(key):
    if not re.fullmatch(r'[0-9a-f]{32}',key):
        raise ValueError('Invalid project ID')
    return folder() / (key+'.json')

def read(key):
    return json.loads(path(key).read_text(encoding='utf-8'))

def snapshot(record):
    from .network import endpoints
    design=Design.model_validate(record['design'])
    revision=store.revision(design)
    pointer=record.get('build')
    return dict(project_id=record['id'],design=design.model_dump(),revision=revision,build=pointer,network=endpoints(),
                updated_at=record['updated_at'],archived=record.get('archived',False),
                stale=not pointer or pointer['design_revision']!=revision or pointer.get('engine_revision')!=store.engine_revision())

def write(record):
    record['updated_at']=datetime.now(timezone.utc).isoformat()
    store.atomic_json(path(record['id']),record)
    return snapshot(record)

def check(record,expected):
    if store.revision(Design.model_validate(record['design']))!=expected:
        raise ValueError('Saved project changed. Reopen it before saving; your draft is preserved.')

def save(design,key=None,expected=None):
    with store.project_lock():
        if key:
            record=read(key);check(record,expected)
            store.atomic_json(folder()/'history'/key/(uuid.uuid4().hex+'.json'),record)
            record['design']=design.model_dump()
        else:
            record=dict(id=uuid.uuid4().hex,design=design.model_dump(),build=None,archived=False)
        return write(record)

def build(key,expected,design=None):
    with store.project_lock():
        record=read(key);check(record,expected)
        target=design or Design.model_validate(record['design'])
        build_id=uuid.uuid4().hex
        report=store.build_outputs(target,store.OUTPUT/'builds'/build_id)
        latest=read(key);check(latest,expected)
        if latest!=record:raise ValueError('Project metadata changed during build. Reopen it; build evidence is retained.')
        store.atomic_json(folder()/'history'/key/(uuid.uuid4().hex+'.json'),record)
        record['design']=target.model_dump()
        record['build']=dict(build_id=build_id,design_revision=store.revision(target),engine_revision=store.engine_revision(),status=report['status'],counts=report['counts'])
        return write(record)

class SaveRequest(Strict):
    design: Design
    project_id: str | None = Field(default=None,pattern=r'^[0-9a-f]{32}$')
    expected_revision: str | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')

class ManageRequest(Strict):
    expected_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    action: str = Field(pattern=r'^(rename|archive|restore|duplicate)$')
    name: str | None = Field(default=None,min_length=1,max_length=120)

@router.get('')
def listing():
    entries=[]
    for p in folder().glob('*.json'):
        try:
            r=read(p.stem);s=snapshot(r);d=s['design']
            entries.append(dict(id=r['id'],name=d['name'],updated_at=s['updated_at'],revision=s['revision'],archived=s['archived'],
                                status='SAVED DRAFT' if s['stale'] else s['build']['status'],features=len(d['features']),context=d['project_context'],block=d['block']))
        except (ValueError,OSError,KeyError):
            entries.append(dict(id=p.stem,name=p.stem,status='UNREADABLE',archived=False,error='Project file requires repair; original retained.'))
    return sorted(entries,key=lambda r:r.get('updated_at',''),reverse=True)

@router.post('')
def save_request(payload:SaveRequest):
    try:return save(payload.design,payload.project_id,payload.expected_revision)
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc))
    except FileNotFoundError:raise HTTPException(404,'Project not found')

@router.get('/{key}')
def get_project(key:str):
    try:return snapshot(read(key))
    except (ValueError,FileNotFoundError):raise HTTPException(404,'Project not found or invalid')

@router.post('/{key}/manage')
def manage(key:str,payload:ManageRequest):
    try:
        with store.project_lock():
            r=read(key);check(r,payload.expected_revision)
            if payload.action=='duplicate':
                r['id']=uuid.uuid4().hex;r['build']=None;r['archived']=False
                r['design']['name']=payload.name or (r['design']['name'][:110]+' copy')
            else:
                store.atomic_json(folder()/'history'/key/(uuid.uuid4().hex+'.json'),r)
                if payload.action=='rename':
                    if not payload.name:raise ValueError('A project name is required')
                    r['design']['name']=payload.name
                else:r['archived']=payload.action=='archive'
            return write(r)
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc))
    except FileNotFoundError:raise HTTPException(404,'Project not found')
