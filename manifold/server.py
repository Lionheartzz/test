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

app = FastAPI(title='PMC Manifold', docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '')
    allowed = {'127.0.0.1:8765', 'localhost:8765', '192.168.253.117:8765', 'testserver'}
    if host not in allowed:
        return JSONResponse({'detail': 'Local host required'}, status_code=403)
    if request.method not in ('GET', 'HEAD'):
        origin = request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:8765', '192.168.253.117:8765', 'http://localhost:8765'}:
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


@app.get('/api/state')
def state():
    try:
        design = read_design()
        rev = revision(design)
    except (ValueError, OSError):
        raise HTTPException(422, 'Project JSON is invalid or missing. Correct projects/demo.json before rebuilding.')
    pointer = current()
    return dict(design=design.model_dump(), revision=rev, build=pointer,
                stale=not pointer or pointer['design_revision'] != rev or pointer.get('engine_revision') != engine_revision())


@app.post('/api/build')
def build(payload: BuildRequest):
    try:
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


@app.post('/api/adopt-routing')
def adopt(design: Design):
    return adopt_routes(design).model_dump()


class OptimizeRequest(BuildRequest):
    max_attempts: int = Field(default=6,ge=1,le=12)


@app.post('/api/optimize-routes')
def optimize(payload: OptimizeRequest):
    from .optimization import optimize_routes
    try:
        return optimize_routes(payload.design or read_design(),payload.expected_revision,payload.max_attempts)
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(409,str(exc))


class FreezeRequest(Strict):
    design: Design
    net: str


@app.post('/api/freeze-net')
def freeze_net(payload: FreezeRequest):
    from .geometry import build_geometry
    from .routing import authorize_generated_contacts
    resolved, _ = resolve_design(payload.design)
    geometry = build_geometry(resolved)
    authorize_generated_contacts(resolved, geometry)
    result = payload.design.model_copy(deep=True)
    result.features = [f for f in result.features if f.route_net != payload.net]
    for feature in resolved.features:
        if feature.route_net == payload.net:
            feature.route_net = None
            result.features.append(feature)
    for net in result.nets:
        if net.id == payload.net:
            net.routing = 'manual'
            net.construction_access = []
    return result.model_dump()


@app.get('/api/library')
def library(include_deleted: bool = False):
    return library_entries(include_deleted)


@app.get('/api/catalog')
def catalog_search(q: str = '', unit: str = '', kind: str = 'cavity', manufacturer: str = '',
                   cavity_type: str = '', thread: str = '', offset: int = Query(0,ge=0), limit: int = Query(40,ge=1,le=100),include_deleted: bool = False):
    from .catalog import search
    return search(q,unit,kind,manufacturer,cavity_type,thread,offset,limit,include_deleted)


@app.get('/api/catalog/manifest')
def catalog_manifest():
    from .catalog import manifest
    return manifest()


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
        mapped = map_record(definition.native.record.model_dump(),definition.native.related_records,definition.native.datum_mode)
        for key in ('id','label','source','manufacturer','cartridge_models','revision','provenance','machining_notes','tooling'):
            setattr(mapped,key,getattr(definition,key))
        mapped.native.source_sha256 = definition.native.source_sha256
        mapped.native.derived_from = definition.native.derived_from
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
    try: return prepare_handoff(payload.design or read_design(),payload.expected_revision)
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
