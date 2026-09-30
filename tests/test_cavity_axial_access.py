"""Deep-side candidates must earn their window contact without protection exceptions."""
import pytest
from manifold import engineering_db, geometry, routing, store
from manifold.cavity_access import cavity_terminal_candidates, axial_route_candidates
from manifold.kinematics import FACE_AXES
from manifold.schema import CavityDefinition, Design, Feature
from manifold.validation import validate
from manifold.flow import opening_area, required_area
from manifold.preview_routing import PreviewRequest, PreviewContext, PreviewEdit, resolve_preview
from test_routing_obstacles import observed, signature


def source_window(face='top', zone='deep', offset=0):
    definition=CavityDefinition(id='SOURCE',label='Declared source machining test',
        stages=[dict(start=0,end=40,diameter=20)],
        cutting_primitives=[dict(source_ref='source:main',kind='cylinder',start=0,end=40,
                                 diameter=20,offset_u=offset)],
        zones=[dict(id='shallow',start=10,end=16,diameter=20,offset_u=offset,clip_to_cut=True),
               dict(id='deep',start=30,end=40,diameter=20,offset_u=offset,clip_to_cut=True)],
        clearance_diameter=24+2*abs(offset),clearance_height=20)
    design=Design(name='Source window access test',block=dict(length=120,width=120,height=120,material='Aluminum'),
        features=[dict(id='CV',kind='cavity',face=face,u=60,v=60,rotation=90,
                       cavity_id=definition.id,interface_nets={zone:'P'})],
        nets=[dict(id='P',routing='automatic',diameter=8)])
    return design,{definition.id:definition}


def checked(design, definitions, route):
    target=design.model_copy(deep=True);target.features.extend(route)
    g=geometry.build_geometry(target,definitions,{}, {})
    routing.authorize_generated_contacts(target,g)
    return target,g,validate(target,g)


@pytest.mark.parametrize('face',list(FACE_AXES))
def test_open_deep_window_has_real_opposite_face_and_passes_exact_protection(face,monkeypatch):
    design,definitions=source_window(face)
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    candidates=cavity_terminal_candidates(design,design.nets[0],definitions)
    bore=candidates['CV:deep']
    axes=FACE_AXES[face];opposite=FACE_AXES[bore.face]
    assert axes[2]==opposite[2] and axes[3]==-opposite[3]
    assert (bore.u,bore.v)==(60,60) and bore.plugged and bore.route_net=='P'
    assert bore.closure_definition_id is None and bore.tip_angle==118
    assert not routing.route_obstructions(design,design.nets[0],[bore],definitions=definitions)
    target,g,report=checked(design,definitions,[bore])
    assert report['counts']['FAIL']==0,report
    common=g.nodes[bore.id].intersect(g.nodes['CV:deep']).Volume()
    assert design.rules.minimum_overlap_volume <= common < .2
    assert routing.segment_depth(bore) < 120-35
    assert any(c['rule']=='construction_closure' and c['status']=='WARNING' for c in report['checks'])


def test_shallow_zone_and_a_deeper_source_cone_cannot_be_crossed():
    design,definitions=source_window(zone='shallow')
    assert not cavity_terminal_candidates(design,design.nets[0],definitions)
    # Largest zone.end alone would say "deep". A real tapered machining bottom
    # beyond that window is still protected and prevents this approach.
    design,definitions=source_window()
    from manifold.schema import CuttingPrimitive
    definitions['SOURCE'].cutting_primitives.append(CuttingPrimitive(
        source_ref='source:protected-bottom',kind='cone',start=40,end=45,diameter=20,end_diameter=0))
    assert not cavity_terminal_candidates(design,design.nets[0],definitions)
    forced=Feature(id='FORCED',kind='drilling',face='bottom',u=60,v=60,diameter=8,
                   depth=80,plugged=True,circuit='P',route_net='P')
    assert ('source_protected','CV','FORCED') in routing.route_obstructions(design,design.nets[0],[forced],definitions=definitions)


def test_offset_opening_is_not_snapped_to_the_cavity_axis(monkeypatch):
    design,definitions=source_window(offset=14)
    assert not cavity_terminal_candidates(design,design.nets[0],definitions)
    # A small genuine offset can contain the axis; rotation is retained in the
    # actual cut/window geometry and a real inscribed hydraulic contact exists.
    design,definitions=source_window(offset=3)
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    bore=cavity_terminal_candidates(design,design.nets[0],definitions)['CV:deep']
    assert (bore.u,bore.v)==(60,60)
    assert checked(design,definitions,[bore])[2]['counts']['FAIL']==0


def test_overdeep_and_thin_wall_attempts_still_fail_source_protection(monkeypatch):
    design,definitions=source_window()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    bore=cavity_terminal_candidates(design,design.nets[0],definitions)['CV:deep']
    bore.depth+=18
    assert ('source_protected','AXIAL-PROBE','CV') in routing.route_obstructions(design,design.nets[0],[bore],definitions=definitions)
    report=checked(design,definitions,[bore])[2]
    assert any(c['rule']=='cavity_protected_region' and c['status']=='FAIL' for c in report['checks'])
    # Unassigned approach owes the ordinary minimum wall, even if it is near a
    # known window. Evidence and geometry existence confer no authorization.
    unassigned=design.nets[0].model_copy(update=dict(members=[]))
    assert ('source_wall','AXIAL-PROBE','CV') in routing.route_obstructions(design,unassigned,[bore],definitions=definitions)


def test_tip_stop_satisfies_real_flow_opening_and_resize_recomputes_contact(monkeypatch):
    design,definitions=source_window()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    net=design.nets[0];net.flow_lpm=10
    key,route=next(axial_route_candidates(design,net,definitions))
    target,g,report=checked(design,definitions,route)
    bore=route[-1]
    assert report['counts']['FAIL']==0,report
    assert opening_area(g.nodes[bore.id],g.nodes['CV:deep'],[(0,0,1),(0,0,-1)]) >= required_area(10,net.velocity_limit)
    previous=bore.depth
    option=dict(key=key,route=route)
    routing.resize_route(design,net,option,10,definitions)
    assert option['route'][-1].diameter==10 and option['route'][-1].depth!=previous
    assert checked(design,definitions,option['route'])[2]['counts']['FAIL']==0
    # Equality with the full drill cross-section is also legal; eligibility
    # cannot demand an arbitrary extra flow area beyond a correctly sized tool.
    import math
    net.flow_lpm=math.pi*(net.diameter/2)**2*net.velocity_limit*1000*60/1_000_000
    assert cavity_terminal_candidates(design,net,definitions)
    net.flow_lpm=10000
    assert not cavity_terminal_candidates(design,net,definitions)


def test_generation_is_analytic_and_forbidden_faces_remain_effective(monkeypatch):
    design,definitions=source_window('front')
    def forbidden(*args,**kwargs):raise AssertionError('Eligibility must not build a BRep')
    monkeypatch.setattr(geometry,'build_geometry',forbidden)
    assert cavity_terminal_candidates(design,design.nets[0],definitions)['CV:deep'].face=='back'
    design.constraints.forbidden_drilling_faces=['back']
    assert not list(axial_route_candidates(design,design.nets[0],definitions))


def test_genuine_opposite_functional_port_closes_coaxial_drilling(monkeypatch):
    design,definitions=source_window()
    design.features.append(Feature(id='PORT',kind='port',face='bottom',u=60,v=60,
                                   diameter=12,depth=16,circuit='P'))
    design=Design.model_validate(design.model_dump())
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    bore=cavity_terminal_candidates(design,design.nets[0],definitions)['CV:deep']
    assert not bore.plugged
    assert checked(design,definitions,[bore])[2]['counts']['FAIL']==0


@pytest.mark.parametrize('face',['left','bottom'])
def test_authored_construction_access_is_never_removed_by_axial_replacement(face,monkeypatch):
    design,definitions=source_window()
    from manifold.schema import ConstructionAccess
    design.nets[0].construction_access=[ConstructionAccess(id='REQUIRED',face=face)]
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    _,route=next(axial_route_candidates(design,design.nets[0],definitions))
    assert {f.id for f in route}=={'R-5c62e091-AX0','REQUIRED'}
    if face=='left':
        assert checked(design,definitions,route)[2]['counts']['FAIL']==0
    else:
        # Coaxial duplicate plug accesses are a real authored conflict, not
        # permission to silently delete a required ID while simplifying.
        assert any(f[0]=='installation_access' for f in routing.route_obstructions(design,design.nets[0],route,definitions=definitions))


def test_real_t10a_uses_deep_access_shortens_routes_and_rebuilds_with_all_connections(monkeypatch,tmp_path):
    source,definitions=observed();before=source.model_dump()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    for net in source.nets:
        candidates=cavity_terminal_candidates(source,net,definitions)
        assert bool(candidates)==(net.id in {'P','T'})
        assert all(key.endswith(':port1') for key in candidates)
    target,routes,g,report=routing.resolve_design(source,prepared=True,persist=True)
    assert report['counts']['FAIL']==0,report
    bores=[f for f in target.features if f.route_net]
    assert len(bores)<16 and sum(f.plugged for f in bores)<13
    assert sum(f.depth for f in bores)<1476.0975
    assert any(r['variant'].startswith('axial_') for r in routes)
    assert all(c['status']=='PASS' for c in report['checks'] if c['rule'] in {'connected_interface','circuit_connectivity','cavity_protected_region'})
    pinned=source.model_copy(deep=True)
    for net in pinned.nets:net.routing_variant=next(r['variant'] for r in routes if r['net']==net.id)
    rebuilt,_=routing.resolve_design(pinned,exact=False)
    assert signature(rebuilt)==signature(target) and source.model_dump()==before
    for net in target.nets:
        assert not routing.route_obstructions(target,net,[f for f in bores if f.route_net==net.id],definitions=definitions)
    assert g.production.isValid() and len(g.production.Solids())==1
    store.atomic_json(tmp_path/'t10a-validation.json',report)


@pytest.mark.parametrize('identifier,expected',[('port',{'T'}),('CV2',{'T','B'})])
def test_incremental_axial_template_recomputes_only_moved_dependencies(monkeypatch,identifier,expected):
    source,definitions=observed()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    proposal,routes=routing.resolve_design(source,exact=False)
    variants={r['net']:r['variant'] for r in routes}
    assert variants['T'].startswith('axial_')
    if identifier=='port':identifier=next(f.id for f in source.features if f.kind=='port' and f.circuit=='T')
    req=PreviewRequest(design=source.model_copy(deep=True),scope='test',context=PreviewContext(
        source=source,scope='test',source_revision=store.revision(source),proposal=proposal,variants=variants,
        edit=PreviewEdit(kind='local',feature_ids=[identifier])))
    next(f for f in req.design.features if f.id==identifier).u-=1
    def forbidden(*args,**kwargs):raise AssertionError('Local valid templates must not run global routing')
    monkeypatch.setattr(routing,'_complete_route_combination',forbidden)
    target,routes,update=resolve_preview(req)
    assert update['mode']=='LOCAL' and set(update['recomputed'])==expected and not update['expansions']
    assert next(r for r in routes if r['net']=='T')['variant'].startswith('axial_')
    for net in {'P','T','A','B'}-expected:
        assert [f.model_dump_json() for f in target.features if f.route_net==net]==[f.model_dump_json() for f in proposal.features if f.route_net==net]
    assert checked(req.design,definitions,[f for f in target.features if f.route_net])[2]['counts']['FAIL']==0


def test_incremental_old_side_template_can_choose_basic_axial_without_pool_search(monkeypatch):
    # This proves the basic terminal strategy is visible even to the incremental
    # fast path; it is not conditional on failed direct routing or detour search.
    source,definitions=source_window()
    source.features.append(Feature(id='PORT',kind='port',face='front',u=30,v=30,
                                   diameter=12,depth=16,circuit='P'))
    source=Design.model_validate(source.model_dump())
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    variants={'P':'xyz:nearest:offset_y_m'}
    pinned=source.model_copy(deep=True)
    for net in pinned.nets:net.routing_variant=variants[net.id]
    proposal,_=routing.resolve_design(pinned,exact=False)
    assert checked(source,definitions,[f for f in proposal.features if f.route_net])[2]['counts']['FAIL']==0
    identifier='PORT'
    req=PreviewRequest(design=source.model_copy(deep=True),scope='test',context=PreviewContext(
        source=source,scope='test',source_revision=store.revision(source),proposal=proposal,variants=variants,
        edit=PreviewEdit(kind='local',feature_ids=[identifier])))
    next(f for f in req.design.features if f.id==identifier).u-=1
    monkeypatch.setattr(routing,'route_options',lambda *a,**k:pytest.fail('No complete neighbourhood needed'))
    target,routes,update=resolve_preview(req)
    assert update['recomputed']==['P'] and not update['retained']
    assert routes[0]['variant'].startswith('axial_')
    assert routes[0]['plugs'] < sum(f.plugged for f in proposal.features)
    assert checked(req.design,definitions,[f for f in target.features if f.route_net])[2]['counts']['FAIL']==0


def test_axial_variants_are_accepted_by_preview_api(monkeypatch):
    from fastapi.testclient import TestClient
    from manifold import server
    source,definitions=source_window()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    proposal=source.model_copy(deep=True)
    proposal.features.extend(next(axial_route_candidates(source,source.nets[0],definitions))[1])
    req=PreviewRequest(design=source,scope='test',context=PreviewContext(
        source=source,scope='test',source_revision=store.revision(source),proposal=proposal,
        variants={'P':'axial_1_0:xyz:nearest'},edit=PreviewEdit(kind='local',feature_ids=['CV'])))
    received=[]
    async def calculate(operation,payload,*args,**kwargs):
        received.append(payload);return b'{"status":"UNVALIDATED_PREVIEW"}'
    monkeypatch.setattr(server,'calculate',calculate)
    with TestClient(server.app) as client:
        assert client.post('/api/preview',json=req.model_dump(),headers={'X-PMC-Request':'local-console'}).status_code==200
        assert received[0]['context']['variants']=={'P':'axial_1_0:xyz:nearest'}
