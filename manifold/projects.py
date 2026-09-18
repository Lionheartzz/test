"""Local named projects. IDs select fixed files, never caller-provided paths."""
import json
import hashlib
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

def saved_revision(design):
    """Hash already-normalized saved project state without opening the project."""
    payload=json.dumps(design,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()

def snapshot(record):
    from .network import endpoints
    from .engineering_db import definitions_for_design,validate_references
    design=Design.model_validate(record['design'])
    validate_references(design)
    engineering={key:value.model_dump() for key,value in definitions_for_design(design).items()}
    revision=store.revision(design)
    pointer=record.get('build')
    return dict(project_id=record['id'],design=design.model_dump(),engineering=dict(definitions=engineering),revision=revision,build=pointer,network=endpoints(),
                updated_at=record['updated_at'],archived=record.get('archived',False),
                stale=not pointer or pointer['design_revision']!=revision or pointer.get('engine_revision')!=store.engine_revision() or not store.engine_current())

def write(record):
    record['updated_at']=datetime.now(timezone.utc).isoformat()
    store.atomic_json(path(record['id']),record)
    return snapshot(record)

def check(record,expected):
    if store.revision(Design.model_validate(record['design']))!=expected:
        raise ValueError('Saved project changed. Reopen it before saving; your draft is preserved.')

def save(design,key=None,expected=None):
    from .engineering_db import validate_references
    validate_references(design)
    with store.project_lock():
        if key:
            record=read(key);check(record,expected)
            store.atomic_json(folder()/'history'/key/(uuid.uuid4().hex+'.json'),record)
            record['design']=design.model_dump()
        else:
            record=dict(id=uuid.uuid4().hex,design=design.model_dump(),build=None,archived=False)
        return write(record)

def prepare_build(key,expected,design=None):
    with store.project_lock():
        record=read(key);check(record,expected)
        target=design or Design.model_validate(record['design'])
        from .engineering_db import validate_references
        validate_references(target)
        return dict(key=key,expected=expected,record=record,target=target,build_id=uuid.uuid4().hex)


def finish_build(plan,report):
    with store.project_lock():
        store.assert_engine_current()
        key=plan['key'];record=plan['record'];latest=read(key);check(latest,plan['expected'])
        if latest!=record:raise ValueError('Project metadata changed during build. Reopen it; build evidence is retained.')
        store.atomic_json(folder()/'history'/key/(uuid.uuid4().hex+'.json'),record)
        record['design']=plan['target'].model_dump()
        record['build']=dict(build_id=plan['build_id'],design_revision=store.revision(plan['target']),engine_revision=store.engine_revision(),status=report['status'],counts=report['counts'])
        return write(record)


def build(key,expected,design=None):
    plan=prepare_build(key,expected,design)
    report=store.build_outputs(plan['target'],store.OUTPUT/'builds'/plan['build_id'])
    return finish_build(plan,report)

class SaveRequest(Strict):
    design: Design
    project_id: str | None = Field(default=None,pattern=r'^[0-9a-f]{32}$')
    expected_revision: str | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')

class ManageRequest(Strict):
    expected_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    action: str = Field(pattern=r'^(rename|archive|restore|duplicate)$')
    name: str | None = Field(default=None,min_length=1,max_length=120)

class DeleteRequest(Strict):
    expected_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirm_name: str = Field(min_length=1,max_length=120)

@router.post('/{key}/delete')
def delete_project(key:str,payload:DeleteRequest):
    try:
        with store.project_lock():
            r=read(key);check(r,payload.expected_revision)
            if payload.confirm_name!=r['design']['name']:
                raise ValueError('Type the exact project name to confirm permanent deletion')
            # Fixed, validated ID under the project store; never follow directory links.
            root=folder().resolve();target=path(key);history=root/'history'/key
            from .drawing.storage import deletion_files
            drawing_files,drawing_dirs=deletion_files(key)
            if target.is_symlink() or target.resolve().parent!=root:
                raise ValueError('Linked project files cannot be deleted here')
            if history.exists():
                if history.is_symlink() or not history.resolve().is_relative_to(root) or history.resolve().parent!=(root/'history').resolve() or (root/'history').is_symlink():
                    raise ValueError('Linked project history cannot be deleted here')
                files=list(history.iterdir())
                if any(p.is_symlink() or not p.is_file() or p.suffix!='.json' for p in files):
                    raise ValueError('Unexpected history contents; project retained')
                for p in files:p.unlink()
                history.rmdir()
            for p in drawing_files:p.unlink()
            for p in drawing_dirs:p.rmdir()
            target.unlink()
            return dict(deleted=key,scope='Project, drawings and revision history deleted. Shared library, assets and immutable builds retained.')
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc))
    except FileNotFoundError:raise HTTPException(404,'Project not found')

@router.get('')
def listing():
    entries=[]
    loaded_engine_revision=store.engine_revision()
    loaded_engine_current=store.engine_current()
    for p in folder().glob('*.json'):
        try:
            r=read(p.stem);d=r['design'];revision=saved_revision(d);pointer=r.get('build')
            stale=bool(pointer) and (pointer['design_revision']!=revision or
                  pointer.get('engine_revision')!=loaded_engine_revision or not loaded_engine_current)
            status='SAVED DRAFT' if not pointer else 'STALE' if stale else pointer['status']
            entries.append(dict(id=r['id'],name=d['name'],updated_at=r['updated_at'],revision=revision,
                                archived=r.get('archived',False),status=status,features=len(d['features']),
                                project_context=d.get('project_context','metric'),block=d.get('block')))
        except (ValueError,OSError,KeyError,TypeError):
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
