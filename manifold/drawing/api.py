"""Local drawing APIs; the existing middleware enforces origin and bounded bodies."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, FileResponse
from pydantic import Field
from ..schema import Strict
from .. import store, projects
from ..engineering import calculate_sync
from . import storage, jobs, templates
from .schema import Create, Save, Regenerate, Revision, Release, Edit, ID, Digest, Key
from .generate import snapshot, initial_edit, auto_annotations, add_tables, regenerate_edit, anchors, digest
from .render import scene, svg, check_drawing, font_path, table_metrics
from .pdf import export_pdf

router=APIRouter(prefix='/api/drawings')


def guarded(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except FileNotFoundError:raise HTTPException(404,'Drawing, project, or source artifact not found')
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc))


@router.get('/font/{kind}')
def font(kind:str):
    if kind not in ('default','cjk'):raise HTTPException(404)
    return FileResponse(font_path(kind=='cjk'),media_type='font/ttf')


@router.get('/templates')
def list_templates():return guarded(templates.listing)


@router.get('/{project_id}')
def listing(project_id:ID):return guarded(storage.listing,project_id)


def isolated_geometry(source,views,progress):
    result=calculate_sync('drawing-geometry',dict(project_id=source['project_id'],expected=source['design_revision'],views=[v.model_dump() for v in views]),progress)
    if result['source']['sha256']!=source['sha256']:
        raise ValueError('Source build changed during drawing generation. Refresh and retry; existing drawing retained.')
    return result['geometry']


@router.post('/{project_id}')
def create(project_id:ID,payload:Create):
    def operation(progress):
        source,solid=snapshot(project_id,payload.expected_source,load_solid=False)
        edit=templates.apply(payload.template_id,payload.kind,initial_edit(source,payload.kind,payload.number))
        edit.annotations=auto_annotations(source,edit)
        if not payload.template_id or payload.template_id.startswith('pmc-'):add_tables(source,edit,payload.kind)
        geometry=isolated_geometry(source,edit.views,progress)
        progress('Saving drawing')
        doc=progress.commit(lambda:storage.save_new(project_id,source,edit,geometry,payload.kind,expected_project=payload.expected_source))
        return dict(drawing_id=doc['id'])
    guarded(projects.read,project_id)
    return guarded(jobs.start,project_id,operation)


@router.get('/{project_id}/jobs/{job_id}')
def get_job(project_id:ID,job_id:ID):return guarded(jobs.get,project_id,job_id)


@router.post('/{project_id}/jobs/{job_id}/cancel')
def cancel_job(project_id:ID,job_id:ID):return guarded(jobs.cancel,project_id,job_id)


@router.get('/{project_id}/{drawing_id}')
def get_document(project_id:ID,drawing_id:ID):return guarded(lambda:storage.public(storage.read(project_id,drawing_id)))


@router.post('/{project_id}/{drawing_id}/save')
def save_document(project_id:ID,drawing_id:ID,payload:Save):
    return guarded(lambda:storage.public(storage.save_edit(project_id,drawing_id,payload.expected_revision,payload.edit)))


class Render(Strict):
    edit: Edit
    sheet: Key


@router.post('/{project_id}/{drawing_id}/render')
def render_document(project_id:ID,drawing_id:ID,payload:Render):
    def run():
        doc=storage.read(project_id,drawing_id)
        if doc['status']=='Released' and Edit.model_validate(doc['edit']).model_dump()!=payload.edit.model_dump():
            raise ValueError('Released drawing presentation is immutable. Create a new revision before editing.')
        doc['edit']=payload.edit.model_dump()
        metrics=table_metrics(doc['source'],payload.edit)
        drawing=scene(doc,payload.sheet)
        row_issues=[dict(code='table-rows:'+table.id,
                         message=f'Displayed rows must be at least {metrics[table.id]["required_physical_rows"]} for the selected source groups.',
                         item=table.id,severity='error') for table in payload.edit.tables
                    if table.display_rows is not None and table.display_rows<metrics[table.id]['required_physical_rows']]
        return dict(svg=svg(drawing),anchors=drawing['anchors'],table_metrics=metrics,
                    issues=check_drawing(doc,layouts=False)+row_issues+drawing['issues'])
    return guarded(run)


@router.post('/{project_id}/{drawing_id}/update')
def update(project_id:ID,drawing_id:ID,payload:Regenerate):
    original=guarded(storage.read,project_id,drawing_id)
    guarded(storage.check,original,payload.expected_revision)
    guarded(storage.editable_project,project_id)
    def operation(progress):
        source,solid=snapshot(project_id,payload.expected_source,load_solid=False)
        previous=payload.edit.model_copy(deep=True)
        ids={a.id for a in previous.annotations}
        previous.suppressed=list(dict.fromkeys([*previous.suppressed,*[a['id'] for a in original['edit']['annotations'] if a['automatic'] and a['id'] not in ids]]))
        edit,added=regenerate_edit(source,previous)
        before=anchors(original['source'])[0];after=anchors(source)[0]
        for item in edit.annotations:
            if item.automatic and item.kind in ('label','leader') and item.anchors and item.text==before.get(item.anchors[0],{}).get('label'):
                item.text='' # Legacy generated captions now follow their associated source label.
        broken={key:value for key,value in original.get('broken',{}).items() if key in ids}
        for item in edit.annotations:
            for key in item.anchors:
                if key not in after or key in before and before[key]['signature']!=after[key]['signature']:
                    broken[item.id]='Feature removed, replaced, or moved to another face; rebind explicitly.'
        candidate=deepcopy(original)
        candidate.update(source=source,edit=edit.model_dump(),geometry=isolated_geometry(source,edit.views,progress),broken=broken)
        progress('Preparing update preview')
        token=uuid.uuid4().hex
        progress.commit(lambda:store.atomic_json(storage.folder(project_id,drawing_id)/'candidates'/(token+'.json'),dict(expected=payload.expected_revision,document=candidate)))
        return dict(candidate_id=token,added=added,broken=broken,document=storage.public(candidate))
    return guarded(jobs.start,project_id,operation)


class Apply(Strict):
    candidate_id: ID
    expected_revision: Digest


class CandidatePreview(Apply):
    sheet: Key


def candidate_document(project_id,drawing_id,candidate_id,expected):
    path=storage.folder(project_id,drawing_id)/'candidates'/(candidate_id+'.json')
    if path.is_symlink() or path.parent.is_symlink():raise ValueError('Linked candidate cannot be used')
    candidate=json.loads(path.read_text(encoding='utf-8'))
    if candidate['expected']!=expected:raise ValueError('Update preview belongs to another drawing revision')
    document=candidate['document']
    if document['project_id']!=project_id or document['id']!=drawing_id:raise ValueError('Preview ownership mismatch')
    return document


@router.post('/{project_id}/{drawing_id}/preview-update')
def preview_update(project_id:ID,drawing_id:ID,payload:CandidatePreview):
    return guarded(lambda:dict(svg=svg(scene(candidate_document(project_id,drawing_id,payload.candidate_id,payload.expected_revision),payload.sheet))))


@router.post('/{project_id}/{drawing_id}/apply-update')
def apply_update(project_id:ID,drawing_id:ID,payload:Apply):
    def run():
        candidate=candidate_document(project_id,drawing_id,payload.candidate_id,payload.expected_revision)
        return storage.public(storage.commit_update(project_id,drawing_id,payload.expected_revision,candidate))
    return guarded(run)


class Rebind(Save):
    annotation: Key


@router.post('/{project_id}/{drawing_id}/rebind')
def rebind(project_id:ID,drawing_id:ID,payload:Rebind):
    def run():
        with storage.LOCK,store.project_lock():
            doc=storage.read(project_id,drawing_id);storage.check(doc,payload.expected_revision)
            storage.editable_project(project_id)
            item=next((a for a in payload.edit.annotations if a.id==payload.annotation),None)
            data=anchors(doc['source'])[0]
            if item is None or any(k not in data for k in item.anchors):raise ValueError('Choose valid source anchors before rebinding')
            doc=storage.write_edit(doc,payload.edit)
            doc.get('broken',{}).pop(item.id,None)
            doc['updated_at']=datetime.now(timezone.utc).isoformat()
            store.atomic_json(storage.folder(project_id,drawing_id)/'current.json',doc)
            return storage.public(doc)
    return guarded(run)


@router.post('/{project_id}/{drawing_id}/revision')
def new_revision(project_id:ID,drawing_id:ID,payload:Revision):
    return guarded(lambda:storage.public(storage.next_revision(project_id,drawing_id,payload.expected_revision,payload.revision,payload.note)))


class Expected(Strict):
    expected_revision: Digest


class SaveTemplate(Expected):
    name: str=Field(min_length=1,max_length=100)


@router.post('/{project_id}/{drawing_id}/template')
def save_template(project_id:ID,drawing_id:ID,payload:SaveTemplate):
    def run():
        doc=storage.read(project_id,drawing_id)
        if storage.revision(doc)!=payload.expected_revision:raise ValueError('Drawing changed; reopen before saving a template')
        return templates.save(payload.name,doc)
    return guarded(run)


@router.post('/{project_id}/{drawing_id}/duplicate')
def duplicate(project_id:ID,drawing_id:ID,payload:Expected):
    return guarded(lambda:storage.public(storage.duplicate(project_id,drawing_id,payload.expected_revision)))


@router.get('/{project_id}/{drawing_id}/revisions')
def history(project_id:ID,drawing_id:ID):return guarded(storage.revisions,project_id,drawing_id)


@router.get('/{project_id}/{drawing_id}/history')
def draft_history(project_id:ID,drawing_id:ID):return guarded(storage.history,project_id,drawing_id)


@router.get('/{project_id}/{drawing_id}/history/{history_id}/pdf')
def history_pdf(project_id:ID,drawing_id:ID,history_id:Digest):
    def run():
        doc=storage.history_document(project_id,drawing_id,history_id)
        if doc['status']=='Released':return FileResponse(storage.released_pdf(project_id,drawing_id,doc['release']['id']),media_type='application/pdf')
        return Response(export_pdf(doc),media_type='application/pdf')
    return guarded(run)


@router.post('/{project_id}/{drawing_id}/history/{history_id}/duplicate')
def copy_history(project_id:ID,drawing_id:ID,history_id:Digest):
    def run():
        doc=storage.history_document(project_id,drawing_id,history_id)
        edit=Edit.model_validate(doc['edit']);edit.metadata.number=edit.metadata.number[:90]+' HISTORY'
        edit.metadata.revision='A'
        return storage.public(storage.save_new(project_id,doc['source'],edit,doc['geometry'],doc['kind'],broken=doc.get('broken',{})))
    return guarded(run)


@router.get('/{project_id}/{drawing_id}/pdf')
def pdf_document(project_id:ID,drawing_id:ID):
    def run():
        doc=storage.read(project_id,drawing_id)
        if doc['status']=='Released':
            path=storage.released_pdf(project_id,drawing_id,doc['release']['id'])
            return FileResponse(path,media_type='application/pdf',filename='drawing.pdf')
        content=export_pdf(doc)
        return Response(content,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="drawing-draft.pdf"'})
    return guarded(run)


@router.get('/{project_id}/{drawing_id}/revisions/{release_id}/pdf')
def issued_pdf(project_id:ID,drawing_id:ID,release_id:ID):
    def run():
        path=storage.released_pdf(project_id,drawing_id,release_id)
        return FileResponse(path,media_type='application/pdf',filename='drawing-revision.pdf')
    return guarded(run)


@router.post('/{project_id}/{drawing_id}/release')
def release(project_id:ID,drawing_id:ID,payload:Release):
    def run():
        doc=storage.read(project_id,drawing_id);storage.check(doc,payload.expected_revision)
        storage.editable_project(project_id)
        problems=check_drawing(doc)
        errors=[i for i in problems if i['severity']=='error']
        warnings={i['code']:i for i in problems if i['severity']=='warning'}
        if errors:raise ValueError('Release blocked: '+'; '.join(i['message'] for i in errors[:8]))
        if set(payload.exceptions)-set(warnings):raise ValueError('Exception must refer to a current drawing warning')
        if set(warnings)-set(payload.exceptions):raise ValueError('Review all warnings and record an explicit decision for each exception before release')
        label=doc['edit']['metadata']['revision']
        if any(r['revision']==label for r in storage.revisions(project_id,drawing_id)):
            raise ValueError('This revision label has already been released; create a new revision')
        issued=deepcopy(doc)
        issued['status']='Released'
        issued['release']=dict(id=uuid.uuid4().hex,by=payload.released_by,date=datetime.now(timezone.utc).isoformat(),exceptions=payload.exceptions,checks=problems)
        content=export_pdf(issued)
        issued['release']['pdf_sha256']=digest(content)
        with storage.LOCK,store.project_lock():
            latest=storage.read(project_id,drawing_id);storage.check(latest,payload.expected_revision)
            storage.editable_project(project_id)
            if not storage.source_current(issued):raise ValueError('Source changed during release. Update the drawing before release.')
            root=storage.safe_folder(storage.folder(project_id,drawing_id)/'released',issued['release']['id'])
            root.mkdir(parents=True,exist_ok=False)
            (root/'drawing.pdf').write_bytes(content)
            store.atomic_json(root/'document.json',issued)
            issued['updated_at']=issued['release']['date']
            store.atomic_json(storage.folder(project_id,drawing_id)/'current.json',issued)
        return storage.public(issued)
    return guarded(run)
