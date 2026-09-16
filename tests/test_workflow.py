import io
import json
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from manifold.demo import demo
from manifold.kinematics import clamp_placement, placement_bounds, resolve_parents
from manifold.routing import adopt_routes, resolve_design, authorize_generated_contacts
from manifold.geometry import build_geometry
from manifold.validation import validate
from manifold.schema import Design, SchematicIntent
from manifold import store, workflow
from manifold.server import app


@pytest.mark.parametrize('face',['top','bottom','front','back','left','right'])
def test_whole_envelope_clamps_all_faces(face):
    d=demo();f=d.features[0];f.face=face
    b=placement_bounds(f,d)
    assert clamp_placement(f,d,-100,-100)==(b['min_u'],b['min_v'])
    assert clamp_placement(f,d,5000,5000)==(b['max_u'],b['max_v'])
    assert clamp_placement(f,d,37.4,42.7)==(37,43)


def test_parent_rotation_and_cycle_rejection():
    d=demo();parent,child=d.features[:2];child.parent_id=parent.id;child.local_offset=(30,0);parent.rotation=90
    r=resolve_parents(d)
    assert (r.features[1].u,r.features[1].v)==pytest.approx((45,90))
    parent.parent_id=child.id
    with pytest.raises(ValueError,match='acyclic'):Design.model_validate(d.model_dump())


def test_auto_route_reproduces_demo_and_follows_terminals(tmp_path):
    d=adopt_routes(demo());r=store.build_outputs(d,tmp_path/'pass')
    assert r['status']=='PASS'
    before,_=resolve_design(d)
    d.features[0].u+=5
    after,_=resolve_design(d)
    a0=next(f for f in before.features if f.route_net=='A')
    a1=[f for f in after.features if f.route_net=='A']
    # A valid offset intersection may keep one drilling after the cavity moves.
    # Verify the moved hydraulic terminals still connect, rather than demanding extra holes.
    moved_geometry=build_geometry(after);authorize_generated_contacts(after,moved_geometry)
    moved_report=validate(after,moved_geometry)
    assert any(c['rule']=='circuit_connectivity' and c['message'].startswith('A:') and c['status']=='PASS' for c in moved_report['checks'])
    assert next(f for f in before.features if f.id=='XD-P').u==pytest.approx(67.5)
    manufacture=json.loads((tmp_path/'pass'/'manufacturing.json').read_text())
    assert manufacture['meet_list'] and len({row['feature'] for row in manufacture['drill_chart']})==12
    assert (tmp_path/'pass'/'resolved_design.json').exists()


def test_suppression_does_not_hide_required_net_failure():
    d=adopt_routes(demo());d.features[0].suppressed=True
    r,_=resolve_design(d);g=build_geometry(r);authorize_generated_contacts(r,g)
    result=validate(r,g)
    assert any(c['rule']=='net_intent' and c['status']=='FAIL' for c in result['checks'])


def test_asset_library_and_actual_handoff_identity(tmp_path,monkeypatch):
    path=tmp_path/'projects'/'demo.json';out=tmp_path/'output'
    monkeypatch.setattr(store,'PROJECT',path);monkeypatch.setattr(store,'OUTPUT',out)
    original=store.read_design;monkeypatch.setattr(store,'read_design',lambda:original(path))
    store.atomic_json(path,demo().model_dump())
    image=io.BytesIO();Image.new('RGB',(40,40),'white').save(image,format='PNG')
    client=TestClient(app);headers={'X-PMC-Request':'local-console','Content-Type':'image/png','X-File-Name':'../../schematic.png'}
    response=client.post('/api/assets',content=image.getvalue(),headers=headers)
    assert response.status_code==200
    asset=response.json();assert asset['name']=='schematic.png'
    d=demo();d.schematic_intent=SchematicIntent(assets=[workflow.SchematicAsset(**asset)],components=[])
    h=workflow.prepare_handoff(d,store.revision(demo()))
    manifest=json.loads((__import__('pathlib').Path(h['request_path']).parent/'manifest.json').read_text())
    assert manifest['assets'][0]['sha256']==asset['sha256']
    assert h['status']=='READY_FOR_CODEX'
    assert client.post('/api/assets',content=b'not an image',headers=headers).status_code==422
    assert client.post('/api/assets',content=image.getvalue(),headers={**headers,'Origin':'https://evil.example'}).status_code==403
    assert not (path.parent/'library').exists()
    with pytest.raises(ValueError,match='changed'):workflow.prepare_handoff(d,'0'*64)


def test_unknown_net_color_build(tmp_path):
    d=adopt_routes(demo())
    for f in d.features:
        if f.circuit=='P':f.circuit='SUPPLY'
        f.circuits={k:'SUPPLY' if v=='P' else v for k,v in f.circuits.items()}
    for n in d.nets:
        if n.id=='P':n.id='SUPPLY'
    assert store.build_outputs(d,tmp_path/'custom-net')['status']=='PASS'


def test_freeze_keeps_exact_contacts_and_roundtrips(tmp_path):
    d=adopt_routes(demo())
    response=TestClient(app).post('/api/freeze-net',json={'design':d.model_dump(),'net':'P'},headers={'X-PMC-Request':'local-console'})
    assert response.status_code==200
    frozen=Design.model_validate(response.json())
    assert next(n for n in frozen.nets if n.id=='P').routing=='manual'
    bores=[f for f in frozen.features if f.kind=='drilling' and f.circuit=='P']
    assert len(bores)==2 and all(f.route_net is None and f.connects_to for f in bores)
    assert store.build_outputs(frozen,tmp_path/'frozen')['status']=='PASS'
