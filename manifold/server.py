import json
import re
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from .schema import Design, Strict, CavityDefinition
from .routing import resolve_design, adopt_routes
from .workflow import save_asset, save_library, library_entries, prepare_handoff, asset_path, set_library_deleted
from .interchange import inspect_project
from .store import ROOT, OUTPUT, read_design, revision, current, rebuild, engine_revision
from .network import host_allowed, same_origin, endpoints

app = FastAPI(title='PMC Manifold', docs_url=None, redoc_url=None, openapi_url=None)
from .projects import router as project_router
app.include_router(project_router)


@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '')
    if not host_allowed(host,request.client is not None and request.client.host=='testclient'):
        return JSONResponse({'detail': 'Host is not enabled for this server. Start with --lan for LAN access.'}, status_code=403)
    if request.method not in ('GET', 'HEAD'):
        origin = request.headers.get('origin')
        if origin and not same_origin(origin,request.url.scheme,host):
            return JSONResponse({'detail': 'Same-origin request required'}, status_code=403)
        if request.headers.get('x-pmc-request') != 'local-console':
            return JSONResponse({'detail': 'Local request header required'}, status_code=403)
        upload = request.url.path == '/api/assets'
        if not upload and request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'detail': 'JSON required'}, status_code=415)
        # Bound streamed bodies as well as Content-Length; no arbitrary uploads or paths.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > (20_000_000 if upload else 8_000_000):
                return JSONResponse({'detail': 'Design exceeds 8 MB'}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return response


class BuildRequest(Strict):
    expected_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    design: Design | None = None
    project_id: str | None = Field(default=None,pattern=r'^[0-9a-f]{32}$')


@app.get('/api/health')
def health():
    return dict(service='pmc-manifold',network=endpoints())


@app.get('/api/state')
def state():
    try:
        design = read_design()
        rev = revision(design)
    except (ValueError, OSError):
        raise HTTPException(422, 'Project JSON is invalid or missing. Correct projects/demo.json before rebuilding.')
    pointer = current()
    return dict(design=design.model_dump(), revision=rev, build=pointer, network=endpoints(),
                stale=not pointer or pointer['design_revision'] != rev or pointer.get('engine_revision') != engine_revision())


@app.post('/api/build')
def build(payload: BuildRequest):
    try:
        if payload.project_id:
            from .projects import build as project_build
            return project_build(payload.project_id,payload.expected_revision,payload.design)
        return rebuild(payload.design, payload.expected_revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    except Exception:
        import logging
        logging.exception('CAD build failed')
        raise HTTPException(422, 'CAD build failed; previous saved design/model retained. Check local server log.')


@app.post('/api/check-design')
def check_design(design: Design):
    """Normalize an editor draft without saving or running CAD."""
    return design.model_dump()


@app.get('/api/project-schema')
def project_schema():
    return Design.model_json_schema()


@app.post('/api/import-project')
def import_project(design: Design):
    """Validate a proposed import without replacing the current project or draft."""
    return inspect_project(design)


@app.post('/api/export-project')
def export_project(design: Design):
    """Export a normalized editable draft, independent of its latest build status."""
    return design.model_dump()


@app.post('/api/preview')
def preview(design: Design):
    try:
        resolved, routes = resolve_design(design)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return dict(design=resolved.model_dump(),routes=routes,status='UNVALIDATED_PREVIEW')


@app.post('/api/preview-solid')
def preview_solid(design: Design):
    from .geometry import build_geometry,review_model
    try:
        resolved,_=resolve_design(design)
        geometry=build_geometry(resolved)
        return dict(model=review_model(resolved,geometry),features=[f.model_dump() for f in resolved.features],
                    design_revision=revision(design),status='UNVALIDATED_EXACT_GEOMETRY')
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(422,'Exact draft geometry could not be constructed; review the dimensions and feature intersections.') from exc


@app.post('/api/adopt-routing')
def adopt(design: Design):
    return adopt_routes(design).model_dump()


class OptimizeRequest(BuildRequest):
    max_attempts: int = Field(default=6,ge=1,le=12)


@app.post('/api/optimize-routes')
def optimize(payload: OptimizeRequest):
    from .optimization import optimize_routes
    try:
        return optimize_routes(payload.design or read_design(),payload.expected_revision,payload.max_attempts,payload.project_id)
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(409,str(exc))


class FreezeRequest(Strict):
    design: Design
    net: str


@app.post('/api/freeze-net')
def freeze_net(payload: FreezeRequest):
    from .route_edit import freeze
    try:return freeze(payload.design,payload.net).model_dump()
    except ValueError as exc:raise HTTPException(422,str(exc))


class RefineRequest(Strict):
    design: Design
    feature_id: str
    u: float = Field(ge=0,le=2000,allow_inf_nan=False)
    v: float = Field(ge=0,le=2000,allow_inf_nan=False)


@app.post('/api/refine-route')
def refine_route(payload:RefineRequest):
    from .route_edit import refine
    from .geometry import build_geometry
    from .routing import authorize_generated_contacts
    from .validation import validate
    try:
        draft,adjusted,notes=refine(payload.design,payload.feature_id,payload.u,payload.v)
        resolved,_=resolve_design(draft)
        geometry=build_geometry(resolved);authorize_generated_contacts(resolved,geometry)
        report=validate(resolved,geometry)
        from datetime import datetime,timezone
        report['generated_at']=datetime.now(timezone.utc).isoformat()
        return dict(design=draft.model_dump(),report=report,adjusted_branches=adjusted,notes=notes,status='EXACT_DRAFT_CHECKS_NOT_SAVED')
    except (ValueError,RuntimeError) as exc:raise HTTPException(422,str(exc))


@app.get('/api/library')
def library(include_deleted: bool = False, reusable_only: bool = True):
    return library_entries(include_deleted,reusable_only)


@app.get('/api/catalog')
def catalog_search(q: str = '', unit: str = '', kind: str = 'cavity', manufacturer: str = '',
                   cavity_type: str = '', thread: str = '', offset: int = Query(0,ge=0), limit: int = Query(40,ge=1,le=100),include_deleted: bool = False, family: str = ''):
    from .catalog import search
    return search(q,unit,kind,manufacturer,cavity_type,thread,offset,limit,include_deleted,family)


@app.get('/api/catalog/manifest')
def catalog_manifest():
    from .catalog import manifest
    return manifest()


@app.get('/api/catalog/mapping-report')
def catalog_mapping_report():
    from .catalog import mapping_report
    return mapping_report()


@app.get('/api/catalog/resources')
def catalog_resources():
    from .catalog import shared_resources
    return shared_resources()


@app.get('/api/catalog/resource')
def catalog_resource(id: str):
    from .catalog import resource
    try:
        return resource(id)
    except ValueError as exc:
        raise HTTPException(404,str(exc))


class BoundaryAssignment(Strict):
    design: Design
    definition_id: str
    source_id: str
    category: str = Field(pattern=r'^(mounting-footprint|external-body|service|tool)$')
    height: float = Field(default=0,ge=0,le=2000,allow_inf_nan=False)
    decision: str = Field(min_length=5,max_length=1000)


@app.post('/api/assign-boundary')
def assign_boundary(payload:BoundaryAssignment):
    from .catalog import get_record,resource
    from .boundaries import boundary_source,boundary_shape
    from .schema import ComponentBoundary,EngineeringLibraryResource,EngineeringReview
    try:
        record=get_record(payload.source_id)
        if record.get('kind')!='assembly_envelope':raise ValueError('Choose an assembly envelope record')
        source=boundary_source(record)
        shape=boundary_shape(source['source_raw'],source['source_type'],25.4 if record.get('unit_system')=='inch' else 1)
        if not shape:raise ValueError('Source boundary syntax is preserved but not mapped. Enter a separately reviewed definition; no geometry has been guessed.')
        draft=payload.design.model_copy(deep=True)
        definition=next((d for d in draft.library if d.id==payload.definition_id),None)
        if definition is None:raise ValueError('Select a pinned cavity definition in this project')
        definition.boundaries.append(ComponentBoundary(**shape,**source,category=payload.category,height=payload.height,status='engineer-confirmed',association='engineer-selected'))
        if not any(r.id==payload.source_id for r in draft.library_resources):
            draft.library_resources.append(EngineeringLibraryResource.model_validate(resource(payload.source_id)))
        import uuid
        draft.review_items.append(EngineeringReview(id='ENV_'+uuid.uuid4().hex[:16],kind='source',subject=definition.id,
            description='Engineer associated an independent assembly envelope with this cavity. Verify orientation, role and height against the installation.',
            proposed_value=payload.category+'; '+payload.decision))
        if definition.lineage:definition.lineage.kind='pmc-derived'
        return Design.model_validate(draft.model_dump()).model_dump()
    except ValueError as exc:raise HTTPException(422,str(exc))


@app.get('/api/catalog/record')
def catalog_record(id: str):
    from .catalog import get_record, related, digest
    try:
        record = get_record(id)
        return dict(record=record,related_records=related(record),sha256=digest(record))
    except ValueError as exc:
        raise HTTPException(404,str(exc))


@app.get('/api/catalog/definition')
def catalog_definition(id: str):
    from .catalog import definition, pmc_id
    try:
        existing = [i['definition'] for i in library_entries() if i['preferred'] and i['definition']['id'] == pmc_id(id)]
        if existing:
            return existing[-1]
        return definition(id).model_dump()
    except ValueError as exc:
        raise HTTPException(422,str(exc))


@app.post('/api/library')
def library_save(definition: CavityDefinition):
    try:
        return save_library(definition)
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(409,str(exc))


@app.post('/api/library/project-native')
def library_project_native(definition: CavityDefinition):
    from .catalog import map_record
    if not definition.native:
        raise HTTPException(422,'Native source record is required')
    try:
        native=definition.native
        mapped = map_record((native.mapping_record or native.record).model_dump(),
                            native.mapping_related_records if native.mapping_related_records is not None else native.related_records,native.datum_mode)
        for key in ('id','label','source','manufacturer','cartridge_models','revision','provenance','machining_notes','tooling','lineage','compatible_cartridges'):
            setattr(mapped,key,getattr(definition,key))
        mapped.native.source_sha256 = definition.native.source_sha256
        mapped.native.derived_from = definition.native.derived_from
        mapped.native.record = native.record.model_copy(deep=True)
        mapped.native.related_records = native.model_copy(deep=True).related_records
        mapped.native.mapping_record = native.mapping_record.model_copy(deep=True) if native.mapping_record else None
        mapped.native.mapping_related_records = native.model_copy(deep=True).mapping_related_records
        return mapped.model_dump()
    except ValueError as exc:
        raise HTTPException(422,str(exc))


class LibraryVisibility(Strict):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
    deleted: bool


@app.post('/api/library/visibility')
def library_visibility(payload: LibraryVisibility):
    try:
        return set_library_deleted(payload.id,payload.deleted)
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(409,str(exc))


@app.post('/api/assets')
async def asset_upload(request: Request):
    from urllib.parse import unquote
    try:
        return save_asset(await request.body(),unquote(request.headers.get('x-file-name','schematic')),request.headers.get('content-type','').split(';')[0]).model_dump()
    except (ValueError,OSError) as exc:
        raise HTTPException(422,str(exc))


@app.get('/api/assets/{digest}')
def asset_download(digest: str):
    if not re.fullmatch('[0-9a-f]{64}',digest): raise HTTPException(404)
    from . import store
    for suffix,media in [('.png','image/png'),('.jpg','image/jpeg'),('.pdf','application/pdf')]:
        path=store.PROJECT.parent/'assets'/(digest+suffix)
        if path.is_file(): return FileResponse(path,media_type=media,filename=path.name if suffix=='.pdf' else None)
    raise HTTPException(404)


@app.post('/api/handoff')
def handoff(payload: BuildRequest):
    try: return prepare_handoff(payload.design or read_design(),payload.expected_revision,payload.project_id)
    except (ValueError,RuntimeError) as exc: raise HTTPException(409,str(exc))


@app.get('/api/artifacts/{build_id}/{name}')
def artifact(build_id: str, name: str):
    if not re.fullmatch('[0-9a-f]{32}', build_id) or name not in {'review.json', 'design.json', 'resolved_design.json', 'validation.json', 'validation.md', 'production.step','manufacturing.json','drill-chart.csv'}:
        raise HTTPException(404)
    folder = OUTPUT / 'builds' / build_id
    if not (folder / name).is_file():
        raise HTTPException(404)
    if name == 'production.step':
        report = json.loads((folder / 'validation.json').read_text(encoding='utf-8'))
        if report['status'] != 'PASS':
            raise HTTPException(409, 'STEP download requires PASS. Failed geometry is retained locally for diagnostics.')
    return FileResponse(folder / name, filename=name if name in {'production.step', 'validation.md', 'design.json'} else None)


if (ROOT / 'dist').exists():
    app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='console')
