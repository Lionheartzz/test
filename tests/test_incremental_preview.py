import pytest
from manifold import engineering_db, routing, store, geometry
from manifold.schema import Design
from manifold.preview_routing import PreviewRequest,PreviewContext,PreviewEdit,resolve_preview,affected_nets
from manifold.cad_worker import dispatch
from test_routing_obstacles import observed


VARIANTS={'A':'yzx:nearest:offset_y_m','B':'xzy:nearest:offset_x_p','P':'simple_46','T':'yzx:nearest:offset_y_p'}


@pytest.fixture
def seeded(monkeypatch):
    source,definitions=observed()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    pinned=source.model_copy(deep=True)
    for net in pinned.nets:net.routing_variant=VARIANTS[net.id]
    proposal,_=routing.resolve_design(pinned,exact=False)
    return source,proposal


def request(source,proposal,identifier=None,*,kind='local'):
    return PreviewRequest(design=source.model_copy(deep=True),scope='project-epoch-1',context=PreviewContext(
        scope='project-epoch-1',source=source,source_revision=store.revision(source),proposal=proposal,
        edit=PreviewEdit(kind=kind,feature_ids=[identifier] if identifier else [])))


def routes(design,net):
    return [f.model_dump_json() for f in design.features if f.route_net==net]


def verify(target):
    from manifold.validation import validate
    g=geometry.build_geometry(target)
    routing.authorize_generated_contacts(target,g)
    report=validate(target,g)
    assert report['counts']['FAIL']==0,report


@pytest.mark.parametrize('identifier,expected',[('port',{'P'}),('CV1',{'P','A'})])
def test_move_only_dependent_nets_and_retain_other_routes(seeded,monkeypatch,identifier,expected):
    source,proposal=seeded
    if identifier=='port':identifier=next(f.id for f in source.features if f.kind=='port' and f.circuit=='P')
    req=request(source,proposal,identifier)
    feature=next(f for f in req.design.features if f.id==identifier)
    feature.u+=1 if feature.kind=='port' else -1
    called=[];original=routing.route_options
    def counted(d,n,**kwargs):called.append(n.id);return original(d,n,**kwargs)
    monkeypatch.setattr(routing,'route_options',counted)
    def forbidden(*args,**kwargs):raise AssertionError('No global search for a local move')
    monkeypatch.setattr(routing,'_complete_route_combination',forbidden)
    target,_,update=resolve_preview(req)
    assert set(called)==expected and set(update['recomputed'])==expected
    assert update['mode']=='LOCAL' and not update['expansions']
    for net in {'P','T','A','B'}-expected:assert routes(target,net)==routes(proposal,net)
    assert not any(f.route_net for f in req.design.features)
    verify(target)


def test_actual_port_conflict_expands_only_to_blocking_net(monkeypatch):
    # Controlled candidate neighbourhood with real cut/obstruction/contact
    # checks. Moving P1 raises the P route into A's old crossing bore. A's
    # alternate elevated route clears P; T/B stay at their original Z=130.
    from manifold.schema import Feature
    def port(id,face,u,v,net):return dict(id=id,kind='port',face=face,u=u,v=v,circuit=net,diameter=12,depth=24 if net=='A' else 16,tip_angle=180)
    source=Design(name='Pair expansion fixture',block=dict(length=120,width=120,height=160,material='Fixture'),
        features=[port('P1','left',60,50,'P'),port('P2','right',60,50,'P'),
                  port('A1','front',30,75,'A'),port('A2','back',30,75,'A'),
                  port('T1','left',60,130,'T'),port('T2','right',60,130,'T'),
                  port('B1','left',100,130,'B'),port('B2','right',100,130,'B')],
        nets=[dict(id=n,routing='automatic') for n in ('P','A','T','B')])
    def cut(id,net,face,u,v,depth,plugged=False):
        return Feature(id=id,kind='drilling',route_net=net,circuit=net,face=face,u=u,v=v,diameter=8,
                       depth=depth,tip_angle=180,plugged=plugged,plug_length=16)
    old=[cut('RP','P','left',60,50,106),cut('RA','A','front',30,75,106),
         cut('RT','T','left',60,130,106),cut('RB','B','left',100,130,106)]
    proposal=source.model_copy(deep=True);proposal.features.extend(old)
    req=request(source,proposal,'P1');req.design.features[0].v=75
    alternatives={'P':[cut('RP_NEW','P','left',60,75,106),cut('RP_RISE','P','bottom',104,60,75,True)],
                  'A':[cut('RA_NEW','A','front',30,110,106,True),cut('RA_FRONT','A','bottom',30,24,110,True),cut('RA_BACK','A','bottom',30,96,110,True)]}
    inspected=[]
    def options(d,n,**kwargs):
        inspected.append(n.id)
        route=[f.model_copy(deep=True) for f in alternatives[n.id]]
        failures=routing.route_obstructions(d,n,route,definitions={},thread_definitions={},modifier_definitions={})
        return [dict(key='controlled',route=route,hard_failures=len(failures),risk=0)]
    monkeypatch.setattr(routing,'route_options',options)
    target,_,update=resolve_preview(req)
    assert update['mode']=='LOCAL' and update['initial_affected']==['P']
    assert update['recomputed']==['A','P'] and update['retained']==['B','T']
    assert update['expansions'][0]['added']==['A']
    assert set(inspected)=={'P','A'}
    for net in ('B','T'):assert routes(target,net)==routes(proposal,net)
    verify(target)


def test_metadata_only_reuses_all_and_stale_or_global_context_falls_back(seeded,monkeypatch):
    source,proposal=seeded
    req=request(source,proposal,kind='none');req.design.name='Renamed'
    def forbidden(*args,**kwargs):raise AssertionError('Metadata edit must not search routes')
    monkeypatch.setattr(routing,'route_options',forbidden)
    target,_,update=resolve_preview(req)
    assert update['recomputed']==[] and update['mode']=='REUSED'
    assert all(routes(target,n)==routes(proposal,n) for n in VARIANTS)
    full=[]
    monkeypatch.setattr(routing,'resolve_design',lambda d,**k:(full.append(d) or d,[]))
    req.scope='other-project';assert resolve_preview(req)[2]['mode']=='GLOBAL'
    req.scope=req.context.scope;req.design.block.length+=1
    assert resolve_preview(req)[2]['mode']=='GLOBAL'
    req.design=source.model_copy(deep=True);req.context.source_revision='0'*64
    assert resolve_preview(req)[2]['mode']=='GLOBAL'
    assert len(full)==3


def test_manual_frozen_routes_are_fixed_and_moved_interface_is_explicit(seeded,monkeypatch):
    source,proposal=seeded
    source=source.model_copy(deep=True);proposal=proposal.model_copy(deep=True)
    for design in (source,proposal):next(n for n in design.nets if n.id=='P').routing='manual'
    fixed=[]
    for f in proposal.features:
        if f.route_net=='P':f.route_net=None;f.frozen_net='P';fixed.append(f.model_copy(deep=True))
    source.features.extend(fixed)
    identifier=next(f.id for f in source.features if f.kind=='port' and f.circuit=='P')
    req=request(source,proposal,identifier);next(f for f in req.design.features if f.id==identifier).u+=1
    def forbidden(*args,**kwargs):raise AssertionError('Manual route must not reroute')
    monkeypatch.setattr(routing,'route_options',forbidden)
    target,_,update=resolve_preview(req)
    assert update['fixed_nets_affected']==['P'] and update['recomputed']==[]
    assert [f.model_dump_json() for f in target.features if f.frozen_net=='P']==[f.model_dump_json() for f in fixed]


def test_one_streamed_proposal_then_one_final_geometry_without_second_resolution(seeded,monkeypatch):
    source,proposal=seeded
    req=request(source,proposal,kind='none');req.design.name='Metadata preview'
    import manifold.preview_routing as preview
    import manifold.validation as validation
    calls=[];original=preview.resolve_preview
    monkeypatch.setattr(preview,'resolve_preview',lambda r:(calls.append('resolve') or original(r)))
    build=geometry.build_geometry
    monkeypatch.setattr(geometry,'build_geometry',lambda d,*a,**k:(calls.append('geometry') or build(d,*a,**k)))
    def forbidden(*args,**kwargs):raise AssertionError('Preview never runs Validate')
    monkeypatch.setattr(validation,'validate',forbidden)
    result=dispatch('preview-solid',req.model_dump(),proposal_ready=lambda p:calls.append('proposal'))
    assert calls==['resolve','proposal','geometry']
    assert result['status']=='UNVALIDATED_EXACT_GEOMETRY'


def test_request_local_candidate_cache_is_not_mutable_or_shared_between_drafts(monkeypatch):
    from test_routing_priorities import straight_net
    d=straight_net();net=d.nets[0];snapshot=routing._ProposalSnapshot(d,{}, {}, {})
    original=routing.simple_routes;calls=[]
    monkeypatch.setattr(routing,'simple_routes',lambda *a:(calls.append(1) or original(*a)))
    first=routing.route_options(d,net,definitions={},thread_definitions={},modifier_definitions={},snapshot=snapshot)
    depth=first[0]['route'][0].depth;first[0]['route'][0].depth=1
    second=routing.route_options(d,net,definitions={},thread_definitions={},modifier_definitions={},snapshot=snapshot)
    assert len(calls)==1 and second[0]['route'][0].depth==depth
    d.features[0].u+=1
    routing.route_options(d,net,definitions={},thread_definitions={},modifier_definitions={},snapshot=routing._ProposalSnapshot(d,{}, {}, {}))
    assert len(calls)==2


def test_idle_gate_emits_proposal_before_waiting_and_does_not_resolve_again(monkeypatch):
    import time
    from test_v1_engineering_views import bores
    source=bores();req=request(source,source,kind='none')
    markers=[];build=geometry.build_geometry
    def measured(*args,**kwargs):markers.append(('geometry',time.monotonic()));return build(*args,**kwargs)
    monkeypatch.setattr(geometry,'build_geometry',measured)
    deadline=time.monotonic()+.25
    dispatch('preview-solid',req.model_dump(),proposal_ready=lambda p:markers.append(('proposal',time.monotonic())),exact_not_before=deadline)
    assert [key for key,_ in markers]==['proposal','geometry']
    assert markers[0][1]<deadline and markers[1][1]>=deadline-.01


@pytest.mark.parametrize('identifier,expected',[('port',['P']),('CV1',['A','P'])])
def test_matching_current_templates_compete_only_with_local_candidate_pools(seeded,monkeypatch,identifier,expected):
    source,proposal=seeded
    if identifier=='port':identifier=next(f.id for f in source.features if f.kind=='port' and f.circuit=='P')
    req=request(source,proposal,identifier);req.context.variants=VARIANTS
    feature=next(f for f in req.design.features if f.id==identifier)
    feature.u+=1 if feature.kind=='port' else -1
    inspected=[];original=routing.route_options
    def local_options(d,n,**kwargs):inspected.append(n.id);return original(d,n,**kwargs)
    monkeypatch.setattr(routing,'route_options',local_options)
    def forbidden(*args,**kwargs):raise AssertionError('Valid local edit must not run global combination search')
    monkeypatch.setattr(routing,'_complete_route_combination',forbidden)
    target,_,update=resolve_preview(req)
    assert update['recomputed']==expected
    assert set(inspected)==set(expected)
    for net in set(VARIANTS)-set(expected):assert routes(target,net)==routes(proposal,net)
    verify(target)


def test_preview_envelope_is_strict_preview_only_and_legacy_payload_still_works(seeded,monkeypatch):
    from fastapi.testclient import TestClient
    from manifold import server
    source,proposal=seeded;req=request(source,proposal,kind='none');received=[]
    async def calculate(operation,payload,*args,**kwargs):
        received.append((operation,payload,kwargs))
        return b'{"status":"UNVALIDATED_PREVIEW"}'
    monkeypatch.setattr(server,'calculate',calculate)
    headers={'X-PMC-Request':'local-console'}
    with TestClient(server.app) as client:
        assert client.post('/api/preview',json=req.model_dump(),headers=headers).status_code==200
        assert received[-1][1]['context']['source_revision']==req.context.source_revision
        assert received[-1][2]['transient'] is True
        assert client.post('/api/preview-solid',json=source.model_dump(),headers=headers).status_code==200
        assert 'context' not in received[-1][1]
        bad=req.model_dump();bad['context']['file_path']='not-a-preview-field'
        assert client.post('/api/preview',json=bad,headers=headers).status_code==422
        assert client.post('/api/check-design',json=req.model_dump(),headers=headers).status_code==422
