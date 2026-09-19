"""Atomic project-owned drawing storage; released snapshots are append-only."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
from threading import RLock
import uuid
from .. import store, projects
from ..schema import Design
from .schema import Edit

LOCK = RLock()


def saved_project_state(project_id):
    """Read only the saved project revision and build pointer for drawing ownership."""
    record = projects.read(project_id)
    revision = store.revision(Design.model_validate(record['design']))
    return record, revision


def linked(path):
    return path.is_symlink() or (path.exists() and bool(getattr(path.lstat(),'st_file_attributes',0)&0x400))


def safe_folder(root, key):
    if not re.fullmatch(r'[0-9a-f]{32}', key):
        raise ValueError('Invalid document or project ID')
    root = root.absolute()
    path = root / key
    if any(linked(p) for p in (path,*path.parents)) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Linked drawing storage is not supported')
    return path


def folder(project_id, drawing_id):
    projects.read(project_id)
    return safe_folder(safe_folder(store.PROJECT.parent / 'drawings', project_id), drawing_id)


def revision(document):
    from .generate import digest
    return digest(document)


def read(project_id, drawing_id):
    path = folder(project_id, drawing_id) / 'current.json'
    if path.is_symlink():
        raise ValueError('Linked drawing files are not supported')
    doc = json.loads(path.read_text(encoding='utf-8'))
    if doc['project_id'] != project_id or doc['id'] != drawing_id:
        raise ValueError('Drawing ownership is inconsistent')
    Edit.model_validate(doc['edit'])
    from .generate import digest
    source=doc['source']
    if digest({k:v for k,v in source.items() if k!='sha256'})!=source['sha256']:
        raise ValueError('Drawing source snapshot changed. Restore intact history; engineering evidence cannot be edited here.')
    return doc


def editable_project(project_id):
    if projects.read(project_id).get('archived'):
        raise ValueError('Restore the project before editing drawings')


def check(document, expected):
    if revision(document) != expected:
        raise ValueError('Drawing changed in another window. Your edits are preserved; reopen or recover before saving.')
    if document['status'] != 'Draft':
        raise ValueError('Released drawings are immutable. Create a new revision to edit.')


def source_current(doc):
    record, project_revision = saved_project_state(doc['project_id'])
    build = record.get('build')
    return (project_revision == doc['source']['design_revision'] and build is not None
            and build['build_id'] == doc['source']['build_id'])


def public(doc, with_checks=True):
    from .generate import anchors
    data = {k: deepcopy(doc[k]) for k in ('id', 'project_id', 'kind', 'status', 'edit', 'created_at', 'updated_at', 'release')}
    data['revision'] = revision(doc)
    data['source'] = {k:doc['source'][k] for k in ('build_id', 'design_revision', 'sha256', 'engine_revision')}
    data['source_current'] = source_current(doc)
    data['anchors'],rows,operations = anchors(doc['source'])
    data['table_sources'] = {
        'porting':[dict(id=r['id'],label=r['label']+' / '+r['face']) for r in rows],
        'machining':[dict(id=r['id'],label=f'{r["label"]} / {r["face"]} / operation {r["operation"]}') for r in operations],
    }
    from .render import table_metrics
    data['table_metrics'] = table_metrics(doc['source'], Edit.model_validate(doc['edit']))
    from .generate import schematic_assets
    data['assets'] = schematic_assets(doc['source']['authored'])
    if with_checks:
        from .render import check_drawing
        data['issues'] = check_drawing(doc)
    return data


def listing(project_id):
    projects.read(project_id)
    base = safe_folder(store.PROJECT.parent / 'drawings', project_id)
    result=[]
    for path in sorted(base.glob('*/current.json')):
        try:
            doc = read(project_id, path.parent.name)
            result.append(dict(id=doc['id'], kind=doc['kind'], status=doc['status'], metadata=doc['edit']['metadata'],
                               updated_at=doc['updated_at'], source_current=source_current(doc)))
        except (ValueError, OSError, KeyError):
            result.append(dict(id=path.parent.name, status='Unreadable', error='Drawing retained; inspect storage or restore a revision.'))
    return sorted(result,key=lambda d:d.get('updated_at',''),reverse=True)


def save_new(project_id, source, edit, geometry, kind, drawing_id=None, expected_project=None, broken=None):
    with LOCK, store.project_lock():
        record, project_revision = saved_project_state(project_id)
        if record.get('archived',False):
            raise ValueError('Restore the project before editing drawings')
        if expected_project and project_revision != expected_project:
            raise ValueError('Source project changed during generation. Retry with its new saved build.')
        now=datetime.now(timezone.utc).isoformat()
        doc=dict(schema_version=1,id=drawing_id or uuid.uuid4().hex,project_id=project_id,kind=kind,status='Draft',
                 edit=edit.model_dump(),source=source,geometry=geometry,created_at=now,updated_at=now,release=None,broken=deepcopy(broken or {}))
        path=folder(project_id,doc['id'])/'current.json'
        if path.exists():
            raise ValueError('Drawing already exists')
        store.atomic_json(path,doc)
        return doc


def save_edit(project_id,drawing_id,expected,edit):
    with LOCK, store.project_lock():
        doc=read(project_id,drawing_id)
        check(doc,expected)
        if projects.read(project_id).get('archived'):
            raise ValueError('Restore the project before editing drawings')
        from .render import validate_table_display_rows
        validate_table_display_rows(doc['source'], edit)
        return write_edit(doc,edit)


def write_edit(doc,edit):
    """Caller holds the project lock; avoids nesting the OS build lock."""
    ids={a.id for a in edit.annotations}
    edit=edit.model_copy(deep=True)
    edit.suppressed=list(dict.fromkeys([*edit.suppressed,*[a['id'] for a in doc['edit']['annotations'] if a['automatic'] and a['id'] not in ids]]))
    base=folder(doc['project_id'],doc['id'])
    store.atomic_json(base/'history'/(revision(doc)+'.json'),doc)
    doc['edit']=edit.model_dump()
    doc['broken']={k:v for k,v in doc.get('broken',{}).items() if k in ids}
    doc['updated_at']=datetime.now(timezone.utc).isoformat()
    store.atomic_json(base/'current.json',doc)
    return doc


def commit_update(project_id,drawing_id,expected,candidate):
    with LOCK, store.project_lock():
        current=read(project_id,drawing_id)
        editable_project(project_id)
        check(current,expected)
        if candidate['id']!=drawing_id or candidate['project_id']!=project_id or candidate['status']!='Draft':
            raise ValueError('Update preview does not belong to this draft')
        if not source_current(candidate):
            raise ValueError('Manifold changed during update preview. Regenerate again; the old drawing is retained.')
        store.atomic_json(folder(project_id,drawing_id)/'history'/(revision(current)+'.json'),current)
        candidate=deepcopy(candidate)
        candidate['updated_at']=datetime.now(timezone.utc).isoformat()
        store.atomic_json(folder(project_id,drawing_id)/'current.json',candidate)
        return candidate


def revisions(project_id,drawing_id):
    doc=read(project_id,drawing_id)
    rows=[]
    for path in sorted((folder(project_id,drawing_id)/'released').glob('*/document.json')):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        item=json.loads(path.read_text(encoding='utf-8'))
        rows.append(dict(id=path.parent.name,revision=item['edit']['metadata']['revision'],release=item['release']))
    return rows


def released_pdf(project_id,drawing_id,release_id):
    from .generate import digest
    root=safe_folder(folder(project_id,drawing_id)/'released',release_id)
    path=root/'drawing.pdf';record=root/'document.json'
    if linked(path) or linked(record):raise ValueError('Linked release files are not supported')
    doc=json.loads(record.read_text(encoding='utf-8'))
    if doc['project_id']!=project_id or doc['id']!=drawing_id or doc['release']['id']!=release_id or digest(path.read_bytes())!=doc['release']['pdf_sha256']:
        raise ValueError('Released PDF integrity check failed. Restore the original release; it cannot be regenerated as the same issued file.')
    return path


def next_revision(project_id,drawing_id,expected,label,note):
    with LOCK, store.project_lock():
        doc=read(project_id,drawing_id)
        editable_project(project_id)
        if revision(doc)!=expected:
            raise ValueError('Drawing changed; reopen before creating a revision')
        if any(r['revision']==label for r in revisions(project_id,drawing_id)):
            raise ValueError('That revision label has already been released')
        store.atomic_json(folder(project_id,drawing_id)/'history'/(revision(doc)+'.json'),doc)
        doc['edit']['metadata']['revision']=label
        doc['edit']['metadata']['revision_note']=note
        doc['edit']['metadata']['date']=datetime.now(timezone.utc).date().isoformat()
        doc['status']='Draft'
        doc['release']=None
        doc['updated_at']=datetime.now(timezone.utc).isoformat()
        store.atomic_json(folder(project_id,drawing_id)/'current.json',doc)
        return doc


def duplicate(project_id,drawing_id,expected):
    doc=read(project_id,drawing_id)
    if revision(doc)!=expected:
        raise ValueError('Drawing changed; reopen before duplicating')
    edit=Edit.model_validate(doc['edit'])
    edit.metadata.number=edit.metadata.number[:90]+' COPY'
    edit.metadata.revision='A'
    edit.metadata.revision_note='Copied drawing; review for the new document.'
    return save_new(project_id,deepcopy(doc['source']),edit,deepcopy(doc['geometry']),doc['kind'],broken=doc.get('broken',{}))


def history_document(project_id,drawing_id,key):
    if not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('Invalid drawing history ID')
    path=folder(project_id,drawing_id)/'history'/(key+'.json')
    if path.is_symlink() or path.parent.is_symlink():raise ValueError('Linked drawing history is not supported')
    doc=json.loads(path.read_text(encoding='utf-8'))
    if revision(doc)!=key or doc['id']!=drawing_id or doc['project_id']!=project_id:raise ValueError('Drawing history integrity check failed')
    return doc


def history(project_id,drawing_id):
    rows=[]
    root=folder(project_id,drawing_id)/'history'
    if root.is_symlink():raise ValueError('Linked drawing history is not supported')
    for path in sorted(root.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
        doc=history_document(project_id,drawing_id,path.stem)
        rows.append(dict(id=path.stem,updated_at=doc['updated_at'],status=doc['status'],revision=doc['edit']['metadata']['revision'],source_build=doc['source']['build_id']))
    return rows


def deletion_files(project_id):
    """Validate every owned path before the caller deletes any project data."""
    root=safe_folder(store.PROJECT.parent/'drawings',project_id)
    if not root.exists():return [],[]
    entries=[];pending=[root]
    while pending:
        for path in pending.pop().iterdir():
            if linked(path) or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Linked drawing storage cannot be deleted here')
            if path.is_file() and path.suffix not in ('.json','.pdf','.tmp'):
                raise ValueError('Unexpected drawing files; project retained')
            entries.append(path)
            if path.is_dir():pending.append(path)
    return [p for p in entries if p.is_file()],sorted([root,*[p for p in entries if p.is_dir()]],key=lambda p:len(p.parts),reverse=True)
