import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from manifold import catalog,store,workflow
from manifold.demo import demo
from manifold.schema import Design,EngineeringReview,Feature,HydraulicNet,Block,CavityDefinition
from manifold.server import app
from manifold.geometry import build_geometry,cylinder
from manifold.routing import resolve_design,authorize_generated_contacts,terminal_points
from manifold.validation import validate
from manifold.optimization import optimize_routes


def local_store(tmp_path,monkeypatch,design=None):
    project=tmp_path/'projects'/'demo.json'
    monkeypatch.setattr(store,'PROJECT',project)
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    read=store.read_design
    monkeypatch.setattr(store,'read_design',lambda:read(project))
    store.atomic_json(project,(design or demo()).model_dump())
    return project


def test_editable_project_round_trip_preserves_unconfirmed_draft(tmp_path,monkeypatch):
    project=local_store(tmp_path,monkeypatch)
    before=project.read_bytes()
    d=demo();d.review_items=[EngineeringReview(id='R1',subject='CV1',description='Confirm selected cartridge',proposed_value='Candidate A')]
    client=TestClient(app);headers={'X-PMC-Request':'local-console'}
    imported=client.post('/api/import-project',json=d.model_dump(),headers=headers)
    assert imported.status_code==200
    assert imported.json()['summary']['open_reviews']==1
    exported=client.post('/api/export-project',json=imported.json()['design'],headers=headers)
    assert Design.model_validate(exported.json())==d
    assert project.read_bytes()==before
    d.review_items[0].status='accepted'
    assert client.post('/api/import-project',json=d.model_dump(),headers=headers).status_code==422
    d.review_items[0].resolution='Checked against component drawing'
    assert client.post('/api/import-project',json=d.model_dump(),headers=headers).status_code==200


@pytest.mark.skipif(not catalog.ROOT.exists(),reason='Local converted vendor data is intentionally not checked into Git')
def test_native_catalog_units_counts_and_lossless_records():
    # Cartridge selection excludes external-port machining, without losing records.
    assert catalog.search(unit='metric')['total']+catalog.search(unit='metric',kind='port_definition')['total']==2477
    assert catalog.search(unit='inch')['total']+catalog.search(unit='inch',kind='port_definition')['total']==841
    assert catalog.search(unit='metric',kind='footprint')['total']==3915
    assert catalog.search(unit='inch',kind='footprint')['total']==1649
    d=catalog.definition('inch:lib45:cavity:57')
    original=catalog.get_record('inch:lib45:cavity:57')
    assert d.native.record.model_dump()==original
    assert d.native.record.unit_system=='inch'
    first=next(p for p in d.cutting_primitives if p.source_ref.endswith(':circle:0') and p.kind=='cylinder')
    assert first.diameter==pytest.approx(1.188*25.4)
    assert first.end==pytest.approx(.031*25.4)
    step2=next(p for p in d.cutting_primitives if p.source_ref.endswith(':circle:2') and p.kind=='cylinder')
    assert step2.end==pytest.approx((.031+.625)*25.4)
    # Zero-depth step 1 still contains its conical lead-in at the spot-face datum.
    seat=next(p for p in d.cutting_primitives if p.source_ref.endswith(':circle:1') and p.kind=='cone')
    assert seat.start==pytest.approx(.031*25.4)
    assert d.native.machining_status=='unresolved'
    assert d.native.geometry_status=='imported-dimensional'
    assert d.native.record.machining[0]['diameter_operand']['raw']=='$STEP12'
    assert CavityDefinition.model_validate_json(d.model_dump_json()).native.record.model_dump()==original


@pytest.mark.skipif(not catalog.ROOT.exists(),reason='Local converted vendor data')
def test_native_revision_delete_does_not_change_pinned_project(tmp_path,monkeypatch):
    local_store(tmp_path,monkeypatch)
    d=catalog.definition('metric:lib100:cavity:118')
    pin=d.model_dump()
    assert d.native.related_records and all(r['id']!=d.native.record.id for r in d.native.related_records)
    assert len(d.cutting_primitives)>len(d.stages)
    saved=workflow.save_library(d)
    d.label='PMC edited';d.revision='PMC-2'
    edited=workflow.save_library(d)
    assert saved['sha256']!=edited['sha256']
    workflow.set_library_deleted(d.id,True)
    assert not any(i['definition']['id']==d.id for i in workflow.library_entries())
    pinned=CavityDefinition.model_validate(pin)
    assert pinned.label!='PMC edited' and pinned.native.related_records==pin['native']['related_records']
    assert catalog.get_record(pinned.native.record.id)==pinned.native.record.model_dump()
    workflow.set_library_deleted(d.id,False)
    assert any(i['definition']['revision']=='PMC-2' and i['preferred'] for i in workflow.library_entries())


@pytest.mark.skipif(not catalog.ROOT.exists(),reason='Local converted vendor data')
def test_native_footprint_offsets_cut_real_solids_and_rotate():
    definition=catalog.definition('metric:lib100:cavity:118')
    f=Feature(id='FP1',kind='cavity',face='top',u=80,v=80,definition=definition.id,circuits={z.id:'P' for z in definition.zones})
    d=Design(name='Footprint QA',block=Block(length=160,width=160,height=100,material='Synthetic'),library=[definition],features=[f])
    g=build_geometry(d)
    assert g.production.isValid() and len(g.production.Solids())==1
    # First source footprint is a bolt hole at (-12, +20.25).
    probe=cylinder((68,100.25,100),(0,0,-1),1,0,5)
    assert probe.intersect(g.production).Volume()<1e-6
    f.rotation=90
    rotated=build_geometry(d)
    probe=cylinder((59.75,68,100),(0,0,-1),1,0,5)
    assert probe.intersect(rotated.production).Volume()<1e-6
    # Circuit coordinates use the same offset transform as CAD.
    points=terminal_points(d)
    assert len(points)==len(definition.zones)
    report=validate(d,rotated)
    assert not any(c['rule']=='native_geometry_mapping' and c['status']!='PASS' for c in report['checks'])
    assert report['unresolved_machining']==[definition.id]
    assert report['manufacturing_ready'] is False
    # Relabeling a changed source datum as imported cannot bypass mapping review.
    definition.native.datum_mode='surface-relative'
    changed=validate(d,rotated)
    assert any(c['rule']=='native_geometry_mapping' and c['status']=='WARNING' for c in changed['checks'])


def crossing_fixture():
    d=demo();d.block=Block(length=180,width=100,height=100,material='Synthetic routing fixture');d.features=[]
    for id,face,u,v,depth,net in [('P1','front',50,50,30,'P'),('P2','front',100,50,30,'P'),('T1','top',25,30,50,'T'),('T2','front',25,50,12,'T')]:
        d.features.append(Feature(id=id,kind='port',face=face,u=u,v=v,depth=depth,diameter=12,circuit=net,clearance_diameter=20,clearance_height=20))
    d.nets=[HydraulicNet(id='P',members=['P1','P2'],routing='automatic',diameter=8),HydraulicNet(id='T',members=['T1','T2'],routing='automatic',diameter=8)]
    return d


def test_route_search_avoids_short_cross_circuit_entry_and_preserves_evidence(tmp_path,monkeypatch):
    d=crossing_fixture()
    resolved,routes=resolve_design(d)
    assert routes[0]['variant']=='xyz:positive:direct'
    geometry=build_geometry(resolved);authorize_generated_contacts(resolved,geometry)
    assert validate(resolved,geometry)['status']=='PASS'
    d.nets[0].routing_variant='xyz:negative:direct'
    path=local_store(tmp_path,monkeypatch,d);before=path.read_bytes()
    result=optimize_routes(d,store.revision(d),max_attempts=3)
    assert result['baseline']['FAIL']==6 and result['final']['FAIL']==0 and result['improved']
    assert path.read_bytes()==before
    folder=store.OUTPUT/'optimizations'/result['optimization_id']
    assert json.loads((folder/'attempt-00'/'validation.json').read_text())['status']=='FAIL'
    assert (folder/'summary.json').is_file()
