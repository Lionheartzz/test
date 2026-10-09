import json
import asyncio
from contextlib import asynccontextmanager
import re
from fastapi import FastAPI, HTTPException, Request, Query, Path as ApiPath
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from .schema import CavityDefinition, Design, Strict
from .routing import adopt_routes
from .workflow import save_asset, prepare_handoff, asset_path
from .interchange import inspect_project
from .store import ROOT, OUTPUT, read_design, revision, current, rebuild, engine_revision
from .engineering import calculate,CalculationError,executor,preview_stream
from .engine import engine_current
from .network import host_allowed, same_origin, endpoints

@asynccontextmanager
async def lifespan(app):
    from .engineering_db import validate_database
    validate_database()
    try:yield
    finally:await asyncio.to_thread(executor.close)


app = FastAPI(title='PMC Manifold', docs_url=None, redoc_url=None, openapi_url=None,lifespan=lifespan)
from .projects import router as project_router
app.include_router(project_router)
from .ai_design.api import router as ai_design_router
app.include_router(ai_design_router)
from .drawing.api import router as drawing_router
app.include_router(drawing_router)


@app.exception_handler(CalculationError)
async def calculation_failure(request,exc):
    return JSONResponse({'detail':str(exc)},status_code=exc.status)


@app.get('/api/engineering/status')
async def engineering_status():return await asyncio.to_thread(executor.status)


@app.get('/api/engineering/progress/{operation_id}')
async def engineering_progress(operation_id:str,project_id:str|None=Query(default=None,pattern=r'^[0-9a-f]{32}$')):
    if not re.fullmatch(r'[0-9a-f]{32}',operation_id):raise HTTPException(404,'Validate operation not found.')
    progress=await asyncio.to_thread(executor.progress,operation_id,project_id)
    if progress is None:raise HTTPException(404,'Validate operation not found.')
    return progress


class CancelPreview(Strict):
    owner:str=Field(min_length=1,max_length=80)
    version:int=Field(ge=0)


@app.post('/api/preview-cancel')
async def cancel_preview(payload:CancelPreview):
    await asyncio.to_thread(executor.cancel,payload.owner,payload.version)
    return {'status':'cancelled'}


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
    operation_id: str | None = Field(default=None,pattern=r'^[0-9a-f]{32}$')


@app.get('/api/health')
async def health():
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
                stale=not pointer or pointer['design_revision'] != rev or pointer.get('engine_revision') != engine_revision() or not engine_current())


@app.post('/api/build')
async def build(payload: BuildRequest):
    from . import store,projects
    calculated=False
    try:
        plan=projects.prepare_build(payload.project_id,payload.expected_revision,payload.design) if payload.project_id else store.prepare_rebuild(payload.design,payload.expected_revision)
        report=await calculate('build',dict(design=plan['target'].model_dump(),build_id=plan['build_id']),
                               operation_id=payload.operation_id,project_id=payload.project_id)
        calculated=True
        result=projects.finish_build(plan,report) if payload.project_id else store.finish_rebuild(plan,report)
        if payload.operation_id:
            await asyncio.to_thread(executor.authoritative_result,payload.operation_id,'complete')
            result['operation_id']=payload.operation_id
        return result
    except CalculationError:
        raise
    except FileNotFoundError:
        if calculated and payload.operation_id:await asyncio.to_thread(executor.authoritative_result,payload.operation_id,'failed')
        raise HTTPException(404,'Project no longer exists; build evidence retained.')
    except (ValueError,RuntimeError) as exc:
        if calculated and payload.operation_id:await asyncio.to_thread(executor.authoritative_result,payload.operation_id,'failed')
        raise HTTPException(409,str(exc))


@app.post('/api/check-design')
def check_design(design: Design):
    """Normalize an editor draft without saving or running CAD."""
    from .engineering_db import validate_references
    try:validate_references(design)
    except (ValueError,RuntimeError) as exc:raise HTTPException(422,str(exc)) from exc
    return design.model_dump()


@app.post('/api/engineering/conditions')
def effective_project_conditions(design:Design):
    from .engineering_conditions import project_engineering_context
    return project_engineering_context(design)


@app.get('/api/project-schema')
def project_schema():
    return Design.model_json_schema()


@app.post('/api/import-project')
def import_project(design: Design):
    """Validate a proposed import without replacing the current project or draft."""
    try:return inspect_project(design)
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc))


@app.post('/api/export-project')
def export_project(design: Design):
    """Export a normalized editable draft, independent of its latest build status."""
    return design.model_dump()


from .preview_routing import PreviewRequest


@app.post('/api/preview')
async def preview(design: Design|PreviewRequest,request:Request):
    return Response(await calculate('preview',design.model_dump(),request,transient=True,raw=True),media_type='application/json')


@app.post('/api/preview-solid')
async def preview_solid(design: Design|PreviewRequest,request:Request):
    if request.headers.get('accept')=='application/x-ndjson':
        return StreamingResponse(await preview_stream(design.model_dump(),request),media_type='application/x-ndjson')
    return Response(await calculate('preview-solid',design.model_dump(),request,transient=True,raw=True),media_type='application/json')


class PreviewLayerRequest(Strict):
    design_revision:str=Field(pattern=r'^[0-9a-f]{64}$')
    layer:str=Field(pattern=r'^(void|features)$')


@app.post('/api/preview-layer')
async def preview_layer(payload:PreviewLayerRequest,request:Request):
    return Response(await calculate('preview-layer',payload.model_dump(),request,transient=True,raw=True),media_type='application/json')


@app.post('/api/adopt-routing')
def adopt(design: Design):
    return adopt_routes(design).model_dump()


class OptimizeRequest(BuildRequest):
    max_attempts: int = Field(default=6,ge=1,le=12)


@app.post('/api/optimize-routes')
async def optimize(payload: OptimizeRequest):
    from . import store,projects
    def saved():return Design.model_validate(projects.read(payload.project_id)['design']) if payload.project_id else read_design()
    try:
        with store.project_lock():
            current_design=saved()
            if revision(current_design)!=payload.expected_revision:raise ValueError('Project changed on disk. Reload before optimizing.')
        result=await calculate('optimize',dict(design=(payload.design or current_design).model_dump(),max_attempts=payload.max_attempts))
        with store.project_lock():
            if revision(saved())!=payload.expected_revision:raise ValueError('Project changed during optimization. Candidate evidence retained; newer project preserved.')
        return result
    except CalculationError:raise
    except FileNotFoundError:raise HTTPException(404,'Project no longer exists; optimization evidence retained.')
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc))


class FreezeRequest(Strict):
    design: Design
    net: str
    proposal: Design | None = None


@app.post('/api/freeze-net')
async def freeze_net(payload: FreezeRequest):
    return await calculate('freeze',payload.model_dump())


class RefineRequest(Strict):
    design: Design
    feature_id: str
    u: float = Field(ge=0,le=2000,allow_inf_nan=False)
    v: float = Field(ge=0,le=2000,allow_inf_nan=False)


@app.post('/api/refine-route')
async def refine_route(payload:RefineRequest):
    return await calculate('refine',payload.model_dump())


@app.get('/api/library')
def library(include_deleted: bool = False, reusable_only: bool = True):
    from .engineering_db import search_definitions,get_definition
    rows=search_definitions(kind='cavity',limit=100,include_inactive=include_deleted)
    return [dict(definition=get_definition(row['id'],include_inactive=True).model_dump(),preferred=True,deleted=not row['active']) for row in rows['items']]


@app.get('/api/engineering-library/categories')
def engineering_library_categories():
    from .library_presentation import categories
    return categories()


@app.get('/api/engineering-library/knowledge')
def engineering_library_knowledge(category: str = Query(max_length=60), q: str = Query('',max_length=150),
                                  status: str = Query('',pattern=r'^(|VERIFIED|PARTIAL)$'),
                                  offset: int = Query(0,ge=0), limit: int = Query(40,ge=1,le=100)):
    from .library_presentation import browse
    try:return browse(category,q=q,status=status,offset=offset,limit=limit)
    except ValueError as exc:raise HTTPException(404,str(exc)) from None


@app.get('/api/engineering-library/knowledge/{key}')
def engineering_library_knowledge_detail(key: str = ApiPath(max_length=500)):
    from .library_presentation import detail
    try:return detail(key)
    except ValueError as exc:raise HTTPException(404,str(exc)) from None


@app.get('/api/engineering-library/cartridges/{identifier}')
def engineering_library_cartridge_data(identifier: str):
    from .library_presentation import cartridge_data
    return _technical_query(cartridge_data,identifier)


@app.get('/api/engineering-library/materials/{identifier}')
def engineering_library_material_data(identifier: str):
    from .library_presentation import material_data
    return material_data(identifier)


@app.get('/api/catalog')
def catalog_search(q: str = '', unit: str = '', kind: str = 'cavity', manufacturer: str = '',
                   cavity_type: str = '', thread: str = '', status: str = Query('all',pattern=r'^(all|usable|unavailable)$'),
                   scope: str = Query('all',pattern=r'^(all|master|custom)$'),
                   offset: int = Query(0,ge=0), limit: int = Query(40,ge=1,le=100),include_deleted: bool = False,
                   family: str = '', standard: str = ''):
    from .engineering_db import search_definitions
    return search_definitions(query=' '.join(x for x in (q,cavity_type) if x),unit=unit,kind=kind,
                              offset=offset,limit=limit,include_inactive=include_deleted,
                              family=family,manufacturer=manufacturer,thread=thread,status=status,scope=scope,standard=standard)


@app.get('/api/catalog/standards')
def catalog_standards(kind: str=Query('port',pattern=r'^port$')):
    from .engineering_db import _connect,normalized_port_family
    with _connect() as connection:
        rows=[dict(row) for row in connection.execute(
            'SELECT name,family,thread_spec FROM external_port_definitions WHERE active=1 AND usable=1')]
    return {'items':sorted({normalized_port_family(row) for row in rows})}


class CustomCavityRequest(Strict):
    definition: CavityDefinition

class CustomDefinitionEdit(CustomCavityRequest):
    id: str = Field(pattern=r'^(?:custom_|legacy_)[A-Za-z0-9_-]{1,32}$',max_length=40)
    expected_revision: str = Field(pattern=r'^[0-9a-f]{64}$')

class CustomDefinitionDelete(Strict):
    id: str = Field(pattern=r'^(?:custom_|legacy_)[A-Za-z0-9_-]{1,32}$',max_length=40)
    expected_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirm_name: str = Field(min_length=1,max_length=120)

@app.post('/api/catalog/custom-definition/edit')
def custom_definition_edit(payload:CustomDefinitionEdit):
    from .library_management import edit_custom
    try:return edit_custom(payload.id,payload.definition,payload.expected_revision).model_dump()
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc)) from None

@app.post('/api/catalog/custom-definition/delete')
def custom_definition_delete(payload:CustomDefinitionDelete):
    from .library_management import delete_custom
    try:return delete_custom(payload.id,payload.expected_revision,payload.confirm_name)
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc)) from None


@app.post('/api/catalog/custom-cavity')
def custom_cavity(payload:CustomCavityRequest):
    from .engineering_db import create_custom_cavity
    try:return create_custom_cavity(payload.definition).model_dump()
    except (ValueError,RuntimeError) as exc:raise HTTPException(422,str(exc))


@app.post('/api/catalog/custom-external-port')
def custom_external_port(payload:CustomCavityRequest):
    from .engineering_db import create_custom_external_port
    try:return create_custom_external_port(payload.definition).model_dump()
    except (ValueError,RuntimeError) as exc:raise HTTPException(422,str(exc))


@app.get('/api/catalog/manifest')
def catalog_manifest():
    from .engineering_db import validate_database
    return validate_database()


@app.get('/api/catalog/mapping-report')
def catalog_mapping_report():
    raise HTTPException(410,'Legacy mapping reports were removed; use the one-time import summary.')


@app.get('/api/catalog/resources')
def catalog_resources():
    return []


@app.get('/api/threads')
def threads(q: str='',unit: str='',family: str='',usable_only: bool=True,
            offset: int=Query(0,ge=0),limit: int=Query(200,ge=1,le=500)):
    from .engineering_db import browse_threads
    return browse_threads(q,unit,family=family,usable_only=usable_only,offset=offset,limit=limit)


@app.get('/api/materials')
def material_catalog(include_legacy:bool=False,current_id:str|None=None):
    from .engineering_db import materials
    return {'items':materials(include_legacy=include_legacy,current_id=current_id)}


@app.get('/api/tools')
def tooling_catalog(type: str=Query('drill',pattern=r'^(drill|flat-bottom-drill|spotface|form-port|tap)$'),
                    unit: str='',usable_only: bool=True):
    from .engineering_db import tool_definitions
    items=tool_definitions(type,unit=unit,usable_only=usable_only)
    return {'items':items,'total':len(items)}


@app.get('/api/machining-modifiers')
def machining_modifier_catalog(kind: str='',usable_only: bool=True):
    from .engineering_db import _connect
    with _connect() as connection:
        where="active=1";values=[]
        if usable_only:where+=" AND usable=1"
        if kind:where+=" AND kind=?";values.append(kind)
        rows=[dict(row) for row in connection.execute(
            f"SELECT * FROM machining_modifiers WHERE {where} ORDER BY kind,display_name,id",values)]
    return {'items':[row | {'primitives':json.loads(row['primitives_json']),
                            'machining':json.loads(row['machining_json'])} for row in rows],
            'total':len(rows)}


@app.get('/api/closures')
def closure_catalog():
    from .engineering_db import browse_closures
    items=browse_closures()
    return {'items':items,'total':len(items)}


@app.get('/api/closures/compatible')
def compatible_closure_choices(diameter:float=Query(gt=0,le=2000),depth:float=Query(gt=0,le=2000),unit:str=Query('metric',pattern=r'^(metric|inch)$')):
    from .closure_runtime import choices,aliases
    from .schema import Feature
    feature=Feature(id='closure-query',kind='drilling',face='top',u=0,v=0,circuit='P',diameter=diameter,depth=depth,
                    plugged=True,plug_length=min(8,depth/2))
    from .generic_closures import products
    from .engineering_db import _connect
    with _connect() as db:
        return {'items':[dict(id=r['id'],display_name=r['display_name'],engagement_mm=r['engagement_mm'],envelope=r['envelope'],
                             aliases=[old for old,current in aliases().items() if current==r['id']],
                             products=[dict(manufacturer=p['manufacturer'],part_number=p['part_number']) for p in products(db,r['id'])]) for r in choices(feature,unit)]}


@app.get('/api/catalog/resource')
def catalog_resource(id: str):
    raise HTTPException(410,'Independent legacy JSON resources are not runtime engineering data.')


class BoundaryAssignment(Strict):
    design: Design
    definition_id: str
    source_id: str
    category: str = Field(pattern=r'^(mounting-footprint|external-body|service|tool)$')
    height: float = Field(default=0,ge=0,le=2000,allow_inf_nan=False)
    decision: str = Field(min_length=5,max_length=1000)


@app.post('/api/assign-boundary')
def assign_boundary(payload:BoundaryAssignment):
    raise HTTPException(410,'Boundary editing is disabled until it writes a new stable SQLite definition ID.')


@app.get('/api/catalog/record')
def catalog_record(id: str):
    from .engineering_db import get_definition
    from .library_management import definition_revision
    try:
        definition=get_definition(id,include_inactive=True)
        return dict(definition=definition.model_dump(),revision=definition_revision(definition))
    except ValueError as exc:
        raise HTTPException(404,str(exc))


@app.get('/api/catalog/definition')
def catalog_definition(id: str):
    from .engineering_db import get_definition
    try:
        return get_definition(id).model_dump()
    except ValueError as exc:
        raise HTTPException(422,str(exc))


@app.get('/api/cartridges')
def cartridge_search(q: str = '',offset: int = Query(0,ge=0),limit: int = Query(40,ge=1,le=100)):
    from .engineering_db import search_cartridges
    return search_cartridges(q,offset,limit,technical=True)

@app.get('/api/cartridges/{cartridge_id}')
def cartridge_record(cartridge_id:str):
    from .engineering_db import _connect
    with _connect() as connection:
        row=connection.execute('SELECT id,manufacturer,model,function,ratings_json,active FROM cartridges WHERE id=?',(cartridge_id,)).fetchone()
    if row is None:raise HTTPException(404,'Cartridge not available.')
    return dict(row)


@app.get('/api/compatibility')
def compatibility(cartridge_id: str,cavity_id: str):
    from .engineering_db import compatible
    return dict(cartridge_id=cartridge_id,cavity_id=cavity_id,compatible=compatible(cartridge_id,cavity_id))


def _technical_query(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get('/api/cartridges/{cartridge_id}/engineering-facts')
def cartridge_engineering_facts(cartridge_id: str):
    from .engineering_facts import resolved_engineering_facts
    return _technical_query(resolved_engineering_facts, 'cartridge', cartridge_id)


@app.post('/api/engineering-facts/review')
def engineering_facts_review(design: Design):
    from .engineering_facts import engineering_review
    return engineering_review(design)


@app.get('/api/cartridges/{cartridge_id}/technical')
def cartridge_technical(cartridge_id: str):
    from .technical_knowledge import summary
    return _technical_query(summary, 'cartridge', cartridge_id)


@app.get('/api/cartridges/{cartridge_id}/technical/evidence')
def cartridge_technical_evidence(cartridge_id: str, property: str = Query('', max_length=150),
                                offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100)):
    from .technical_knowledge import evidence
    return _technical_query(evidence, 'cartridge', cartridge_id, property=property, offset=offset, limit=limit)


@app.get('/api/cartridges/{cartridge_id}/technical/conflicts')
def cartridge_technical_conflicts(cartridge_id: str, offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=20)):
    from .technical_knowledge import conflicts
    return _technical_query(conflicts, 'cartridge', cartridge_id, offset=offset, limit=limit)


@app.get('/api/materials/technical')
def material_technical_browse():
    from .technical_knowledge import materials
    return materials()


@app.get('/api/materials/technical/{material_id}')
def material_technical(material_id: str):
    from .technical_knowledge import summary
    return _technical_query(summary, 'material', material_id)


@app.get('/api/materials/technical/{material_id}/evidence')
def material_technical_evidence(material_id: str, property: str = Query('', max_length=150),
                               offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100)):
    from .technical_knowledge import evidence
    return _technical_query(evidence, 'material', material_id, property=property, offset=offset, limit=limit)


@app.get('/api/materials/technical/{material_id}/conflicts')
def material_technical_conflicts(material_id: str, offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=20)):
    from .technical_knowledge import conflicts
    return _technical_query(conflicts, 'material', material_id, offset=offset, limit=limit)


@app.get('/api/materials/technical/{material_id}/stock')
def material_supplier_stock(material_id: str, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    from .technical_knowledge import supplier_stock
    return _technical_query(supplier_stock, material_id, offset=offset, limit=limit)


@app.get('/api/cartridges/{cartridge_id}/cavities')
def cartridge_cavities(cartridge_id: str):
    from .engineering_db import compatible_cavity_ids,get_definition
    return [get_definition(identifier).model_dump() for identifier in compatible_cavity_ids(cartridge_id)]


@app.get('/api/cavities/{cavity_id}/cartridges')
def cavity_cartridges(cavity_id: str):
    from .engineering_db import get_definition,compatible_cartridges
    try:get_definition(cavity_id)
    except ValueError as exc:raise HTTPException(404,str(exc))
    return {'cavity_id':cavity_id,'items':compatible_cartridges(cavity_id)}


@app.get('/api/knowledge/cavity-supplements')
def knowledge_supplements(q: str = Query('', max_length=150), offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100)):
    from .engineering_db import cavity_supplements
    return cavity_supplements(q,offset,limit)


@app.get('/api/knowledge/pending-registry')
def knowledge_pending(q: str = Query('', max_length=150), status: str = Query('', max_length=50), offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100)):
    from .engineering_db import pending_registry
    return pending_registry(q,status,offset,limit)


@app.get('/api/knowledge/cartridges/{cartridge_id}/cavities')
def cartridge_knowledge(cartridge_id: str, offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100)):
    from .engineering_db import knowledge_relations
    try:
        return knowledge_relations(cartridge_id=cartridge_id, offset=offset, limit=limit)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get('/api/knowledge/cavities/{cavity_id}/cartridges')
def cavity_knowledge(cavity_id: str, offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100)):
    from .engineering_db import knowledge_relations
    try:
        return knowledge_relations(cavity_id=cavity_id, offset=offset, limit=limit)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get('/api/knowledge/relations/{relation_id}')
def relation_knowledge(relation_id: str):
    from .engineering_db import knowledge_relation
    try:
        return knowledge_relation(relation_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class LibraryVisibility(Strict):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
    deleted: bool


@app.post('/api/library/visibility')
def library_visibility(payload: LibraryVisibility):
    from .engineering_db import set_custom_active
    try:return set_custom_active(payload.id,not payload.deleted).model_dump()
    except ValueError as exc:raise HTTPException(422,str(exc))


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
    if not re.fullmatch('[0-9a-f]{32}', build_id) or name not in {'review.json', 'design.json', 'resolved_design.json', 'validation.json', 'validation.md', 'production.step','engineering.step','manufacturing.json','drill-chart.csv'}:
        raise HTTPException(404)
    folder = OUTPUT / 'builds' / build_id
    if not (folder / name).is_file():
        raise HTTPException(404)
    if name == 'production.step':
        report = json.loads((folder / 'validation.json').read_text(encoding='utf-8'))
        if report['status'] != 'PASS':
            raise HTTPException(409, 'STEP download requires PASS. Failed geometry is retained locally for diagnostics.')
    return FileResponse(folder / name, filename=name if name in {'production.step','engineering.step','validation.md','design.json'} else None)


if (ROOT / 'dist').exists():
    app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='console')
