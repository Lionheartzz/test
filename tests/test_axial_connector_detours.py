"""Local connector detours must preserve the certified bore and finite obstacles."""
import json
from pathlib import Path
import pytest
from manifold import engineering_db, routing as r, geometry, store
from manifold.schema import Design, Feature, HydraulicNet
from manifold.cavity_access import axial_route, axial_connector_candidates
from manifold.preview_routing import PreviewRequest, PreviewContext, PreviewEdit, resolve_preview
from test_cavity_axial_access import source_window, checked
from test_routing_obstacles import observed, signature


def blocked_connector():
    source,definitions=source_window()
    source.features.extend([
        Feature(id='P_PORT',kind='port',face='front',u=30,v=30,diameter=12,depth=16,circuit='P'),
        Feature(id='T_PORT',kind='port',face='back',u=45,v=30,diameter=12,depth=16,circuit='T'),
        Feature(id='T_FIXED',kind='drilling',face='back',u=45,v=30,diameter=8,depth=68,
                circuit='T',frozen_net='T',connects_to=['T_PORT'])])
    source.nets.append(HydraulicNet(id='T',routing='manual'))
    return Design.model_validate(source.model_dump()),definitions


@pytest.mark.parametrize('priority',['fewer_plugs','simple_machining'])
def test_fixed_cross_net_blocks_direct_connector_but_local_detour_passes(priority,monkeypatch):
    source,definitions=blocked_connector();source.constraints.priority=priority
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    net=source.nets[0]
    direct=axial_route(source,net,definitions,'axial_1_0:yxz:nearest')
    assert ('cross_net_wall','R-5c62e091-1','T_FIXED') in r.route_obstructions(source,net,direct,{},definitions,{})
    bore=next(f for f in direct if '-AX' in f.id)
    assert not r.route_obstructions(source,net,[bore],{},definitions,{})
    source_before=source.model_dump()
    candidates=list(axial_connector_candidates(source,net,definitions))
    assert 0<len(candidates)<=12
    clear=[]
    for key,route in candidates:
        assert next(f for f in route if '-AX' in f.id).model_dump()==bore.model_dump()
        if not r.route_obstructions(source,net,route,{},definitions,{}):clear.append((key,route))
    assert clear
    options=r.route_options(source,net,definitions=definitions,thread_definitions={},modifier_definitions={})
    winner=options[0]
    assert not winner['hard_failures']
    assert any(not o['hard_failures'] and r._strategy_family(o['key'])=='axial-detour' for o in options)
    assert all(r.route_objective(source,winner['route'],winner['risk'],definitions)<=r.route_objective(source,o['route'],o['risk'],definitions)
               for o in options if not o['hard_failures'])
    target,g,report=checked(source,definitions,winner['route'])
    assert report['counts']['FAIL']==0,report
    best_detour=min(clear,key=lambda row:r.route_objective(source,row[1],definitions=definitions))[1]
    _,detour_g,detour_report=checked(source,definitions,best_detour)
    assert detour_report['counts']['FAIL']==0,detour_report
    assert detour_g.cuts[bore.id].distance(detour_g.cuts['T_FIXED'])>=7-1e-6
    assert all(c['status']=='PASS' for c in report['checks'] if c['rule'] in {'connected_interface','circuit_connectivity','cavity_protected_region'})
    assert next(f for f in target.features if f.id=='T_FIXED').model_dump()==source_before['features'][-1]
    assert source.model_dump()==source_before


def test_explicit_planes_roundtrip_and_regenerate_without_original_obstacle_context(monkeypatch,tmp_path):
    source,definitions=blocked_connector()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    key,route=next((key,route) for key,route in axial_connector_candidates(source,source.nets[0],definitions)
                   if not r.route_obstructions(source,source.nets[0],route,{},definitions,{}))
    source.nets[0].routing_variant=key
    path=tmp_path/'project.json';path.write_text(source.model_dump_json())
    reloaded=Design.model_validate_json(path.read_text())
    regenerated=r.route_from_variant(reloaded,reloaded.nets[0],key,definitions,{}, {})
    assert [f.model_dump_json() for f in regenerated]==[f.model_dump_json() for f in route]
    context=source.model_copy(update=dict(features=[f for f in source.features if f.id!='T_FIXED']))
    assert [f.model_dump_json() for f in r.route_from_variant(context,context.nets[0],key,definitions,{}, {})]==[f.model_dump_json() for f in route]
    proposal=source.model_copy(deep=True);proposal.features.extend(route)
    preview=PreviewContext(scope='saved',source=source,source_revision=store.revision(source),proposal=proposal,
                           variants={'P':key},edit=PreviewEdit(kind='none'))
    assert PreviewContext.model_validate_json(preview.model_dump_json()).variants=={'P':key}
    rebuilt,_=r.resolve_design(reloaded,exact=False)
    assert [f.model_dump(exclude={'connects_to'}) for f in rebuilt.features if f.route_net=='P']==[f.model_dump(exclude={'connects_to'}) for f in route]


def test_generation_uses_no_brep_and_retains_distinct_bounded_strategy_families(monkeypatch):
    source,definitions=blocked_connector()
    def forbidden(*args,**kwargs):raise AssertionError('Analytic connector generation must not build BReps')
    monkeypatch.setattr(geometry,'build_geometry',forbidden)
    rows=list(axial_connector_candidates(source,source.nets[0],definitions))
    assert rows and len(rows)<=12
    assert all(r._strategy_family(key)=='axial-detour' for key,_ in rows)
    assert r._strategy_family('axial_1_0:yxz:nearest')=='axial'
    assert r._strategy_family('xyz:nearest:direct')=='direct'


def test_old_axial_keys_keep_the_original_geometry_for_both_levels(monkeypatch):
    source,definitions=observed()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    net=source.nets[0]
    for key in ('axial_1_0:yxz:nearest','axial_1_1:yxz:nearest'):
        route=r.route_from_variant(source,net,key,definitions)
        assert [(f.id,f.face,f.u,f.v,f.depth,f.plugged) for f in route]==[
            ('R-5c62e091-1','left',100,100,57,True),
            ('R-5c62e091-2','front',36,100,104,False),
            ('R-5c62e091-AX0','bottom',53,100,146.122133,True)]


def test_real_vertical_bores_are_clear_and_new_connector_family_is_screened(monkeypatch,tmp_path):
    source,definitions=observed()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    net_p=next(n for n in source.nets if n.id=='P');net_t=next(n for n in source.nets if n.id=='T')
    p=axial_route(source,net_p,definitions,'axial_1_0:yxz:nearest')
    t=axial_route(source,net_t,definitions,'axial_1_0:yxz:nearest')
    pa=next(f for f in p if '-AX' in f.id);ta=next(f for f in t if '-AX' in f.id)
    _,g,_=checked(source,definitions,p+t)
    assert g.cuts[pa.id].distance(g.cuts[ta.id])==pytest.approx(46)
    assert g.cuts[pa.id].intersect(g.cuts[ta.id]).Volume()<1e-6
    # The old transverse pair intersects; a separate, immutable P-bore/T-
    # connector wall failure also exists and cannot be repaired by moving P's
    # connector alone. Record these as different engineering facts.
    assert g.cuts['R-5c62e091-1'].intersect(g.cuts['R-e632b709-1']).Volume()==pytest.approx(4.2777228952,abs=1e-5)
    assert g.cuts[pa.id].distance(g.cuts['R-e632b709-1'])==pytest.approx(.5965575239,abs=1e-5)
    target,metadata,g,report=r.resolve_design(source,prepared=True,persist=True)
    assert report['counts']['FAIL']==0 and g.production.isValid()
    context=target.model_copy(update=dict(features=[f for f in target.features if f.route_net!='P']))
    snapshot=r._ProposalSnapshot(source,definitions,{}, {})
    selected=[f for f in target.features if f.route_net=='P']
    rows=[]
    for key,raw in axial_connector_candidates(source,net_p,definitions,context=context,cache=snapshot.obstructions):
        assert next(f for f in raw if '-AX' in f.id).model_dump(exclude={'connects_to'})==pa.model_dump(exclude={'connects_to'})
        if r.route_obstructions(source,net_p,raw,{},definitions,{}):continue
        route,connected=snapshot.simplify(source,net_p,raw,known_failures=set())
        if not connected:continue
        failures=r.route_obstructions(context,net_p,route,{},definitions,{})
        if not failures:
            assert r.route_objective(source,selected,definitions=definitions)<=r.route_objective(source,route,definitions=definitions)
        else:
            assert ('cross_net_wall',pa.id,'R-e632b709-1') in failures
        rows.append(dict(variant=key,metrics=r.manufacturing_metrics(source,route,definitions=definitions),obstructions=sorted(failures)))
    assert rows
    store.atomic_json(tmp_path/'real-axial-detours.json',dict(routes=metadata,counts=report['counts'],alternatives=rows))


def test_local_p_evaluates_retained_t_without_global_reroute(monkeypatch):
    source,definitions=observed()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    proposal,metadata=r.resolve_design(source,exact=False)
    identifier=next(f.id for f in source.features if f.kind=='port' and f.circuit=='P')
    request=PreviewRequest(design=source.model_copy(deep=True),scope='local',context=PreviewContext(
        source=source,scope='local',source_revision=store.revision(source),proposal=proposal,
        variants={m['net']:m['variant'] for m in metadata},edit=PreviewEdit(kind='local',feature_ids=[identifier])))
    next(f for f in request.design.features if f.id==identifier).u+=1
    def forbidden(*a,**k):raise AssertionError('Retained routes must remain local obstacles')
    monkeypatch.setattr(r,'_complete_route_combination',forbidden)
    called=[];original=r.route_options
    def options(d,n,**kwargs):called.append(n.id);return original(d,n,**kwargs)
    monkeypatch.setattr(r,'route_options',options)
    target,_,update=resolve_preview(request)
    assert update['mode']=='LOCAL' and update['recomputed']==['P'] and not update['expansions']
    assert set(called)=={'P'}
    for net in ('A','T','B'):
        assert [f.model_dump_json() for f in target.features if f.route_net==net]==[f.model_dump_json() for f in proposal.features if f.route_net==net]
    assert checked(request.design,definitions,[f for f in target.features if f.route_net])[2]['counts']['FAIL']==0


def test_local_p_discovers_clear_detour_around_retained_automatic_connector(monkeypatch):
    source,definitions=blocked_connector()
    fixed=next(f for f in source.features if f.id=='T_FIXED')
    source.features=[f for f in source.features if f.id!='T_FIXED']
    source.nets[1].routing='automatic'
    retained=fixed.model_copy(update=dict(id='T_ROUTE',frozen_net=None,route_net='T'))
    direct=axial_route(source,source.nets[0],definitions,'axial_1_0:yxz:nearest')
    proposal=source.model_copy(deep=True);proposal.features.extend(direct+[retained])
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    request=PreviewRequest(design=source.model_copy(deep=True),scope='retained',context=PreviewContext(
        source=source,scope='retained',source_revision=store.revision(source),proposal=proposal,
        variants={'P':'axial_1_0:yxz:nearest'},edit=PreviewEdit(kind='local',feature_ids=['P_PORT'])))
    next(f for f in request.design.features if f.id=='P_PORT').u+=1
    captured=[];original=r.route_options
    def options(d,n,**kwargs):
        assert n.id=='P' and any(f.id=='T_ROUTE' for f in d.features)
        result=original(d,n,**kwargs);captured.extend(result);return result
    monkeypatch.setattr(r,'route_options',options)
    monkeypatch.setattr(r,'_complete_route_combination',lambda *a,**k:pytest.fail('No global search required'))
    target,_,update=resolve_preview(request)
    assert update['recomputed']==['P'] and update['retained']==['T'] and not update['expansions']
    assert any(not o['hard_failures'] and r._strategy_family(o['key'])=='axial-detour' for o in captured)
    assert next(f for f in target.features if f.id=='T_ROUTE').model_dump_json()==retained.model_dump_json()
    assert checked(request.design,definitions,[f for f in target.features if f.route_net])[2]['counts']['FAIL']==0


def test_new_connector_variant_is_accepted_by_preview_api(monkeypatch):
    from fastapi.testclient import TestClient
    from manifold import server
    source,definitions=blocked_connector()
    key,route=next((k,rt) for k,rt in axial_connector_candidates(source,source.nets[0],definitions)
                   if not r.route_obstructions(source,source.nets[0],rt,{},definitions,{}))
    proposal=source.model_copy(deep=True);proposal.features.extend(route)
    request=PreviewRequest(design=source,scope='api',context=PreviewContext(source=source,scope='api',
        source_revision=store.revision(source),proposal=proposal,variants={'P':key},edit=PreviewEdit(kind='none')))
    received=[]
    async def calculate(operation,payload,*args,**kwargs):received.append(payload);return b'{"status":"UNVALIDATED_PREVIEW"}'
    monkeypatch.setattr(server,'calculate',calculate)
    with TestClient(server.app) as client:
        assert client.post('/api/preview',json=request.model_dump(),headers={'X-PMC-Request':'local-console'}).status_code==200
    assert received[0]['context']['variants']=={'P':key}
