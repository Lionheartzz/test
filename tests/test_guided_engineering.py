import math
import pytest
from fastapi.testclient import TestClient
from manifold import catalog
from manifold.demo import demo
from manifold.schema import Feature,Design
from manifold.geometry import build_geometry,cylinder
from manifold.flow import opening_area,required_area
from manifold.validation import validate
from manifold.server import app
from manifold.boundaries import source_boundary


def test_real_tool_and_material_filters_keep_full_source_records():
    client=TestClient(app)
    for kind,family,count in [('tool','drill',305),('tool','flat_bottom_drill',43),('tool','spot_face',64),('material_stock','',268)]:
        response=client.get('/api/catalog',params=dict(kind=kind,family=family))
        assert response.status_code==200
        data=response.json();assert data['total']==count
        record=catalog.get_record(data['items'][0]['id'])
        assert record['kind']==kind and record.get('provenance')
        if family:assert record['family']==family


def test_source_boundaries_only_accept_closed_explicit_lines():
    assert source_boundary('L;0;0;20;0;L;20;10;0;10;L;20;0;20;10;L;0;10;0;0;')==[(0,0),(20,0),(20,10),(0,10)]
    assert source_boundary('L;0;0;20;0;') is None
    assert source_boundary('C;0;0;20;') is None
    d=catalog.definition('metric:lib100:cavity:118')
    assert d.boundaries and d.boundaries[0].source
    assert d.boundaries[0].height==0
    assert not d.compatible_cartridges and not d.cartridge_models
    assert d.lineage.kind=='imported-mdtools'
    restored=Design.model_validate(demo().model_dump())
    assert restored.schema_version==1 and restored.project_context=='metric'


def test_exact_connection_sections_reject_grazing_contact():
    a=cylinder((0,0,0),(1,0,0),10,0,40)
    b=cylinder((20,-20,0),(0,1,0),10,0,40)
    grazing=cylinder((20,-20,9.5),(0,1,0),10,0,40)
    full=opening_area(a,b,[(1,0,0),(0,1,0)])
    small=opening_area(a,grazing,[(1,0,0),(0,1,0)])
    assert full==pytest.approx(math.pi*25)
    assert grazing.intersect(a).Volume()>.1
    assert 0<small<required_area(5,6)<full


def test_angled_exact_entry_and_breakout_remain_authoritative():
    d=demo();d.features=[];d.nets=[]
    f=Feature(id='ANGLE',kind='drilling',face='front',u=50,v=50,circuit='P',diameter=8,depth=35,
              direction=(.3,1,.1),plugged=True)
    d.features=[f]
    g=build_geometry(d)
    assert g.production.isValid() and len(g.production.Solids())==1
    assert g.cuts[f.id].Volume()-g.cuts[f.id].intersect(g.block).Volume()<1e-6
    assert g.placements[f.id]['direction'][0]>0
    assert not [c for c in validate(d,g)['checks'] if c['rule'] in ('external_wall','external_face_entry') and c['status']=='FAIL']
    d.features[0].depth=400
    bad=validate(d,build_geometry(d))
    assert any(c['rule']=='external_wall' and c['status']=='FAIL' for c in bad['checks'])
    with pytest.raises(ValueError):
        Feature(id='BAD',kind='drilling',face='front',u=50,v=50,circuit='P',diameter=8,depth=35,direction=(1,-1,0))


def test_old_saved_library_hash_survives_additive_schema_fields(tmp_path,monkeypatch):
    import hashlib,json
    from manifold import store,workflow
    project=tmp_path/'demo.json';monkeypatch.setattr(store,'PROJECT',project)
    d=demo();monkeypatch.setattr(store,'read_design',lambda:d)
    old=d.library[0].model_dump();old['id']='LEGACY';old.pop('lineage');old.pop('boundaries');old.pop('compatible_cartridges')
    digest=hashlib.sha256(json.dumps(old,sort_keys=True).encode()).hexdigest()
    store.atomic_json(tmp_path/'library'/'LEGACY'/(digest+'.json'),old)
    entries=workflow.library_entries()
    match=next(e for e in entries if e['definition']['id']=='LEGACY')
    assert match['sha256']==digest and match['definition']['lineage']['kind']=='demo-provisional'


def test_angled_route_connects_two_windows_and_step_round_trip(tmp_path):
    from manifold.schema import CavityDefinition,HydraulicNet
    from manifold.routing import authorize_generated_contacts
    from manifold.cad import cq
    d=demo();d.features=[]
    definition=CavityDefinition(id='SYNTHETIC',label='Synthetic angle fixture',source='Test geometry, not manufacturer data',
        thread_note='',stages=[dict(start=0,end=60,diameter=16)],zones=[dict(id='window',start=45,end=55,diameter=16)],
        clearance_diameter=20,clearance_height=20)
    d.library=[definition]
    d.features=[Feature(id=id,kind='cavity',face='top',u=x,v=y,definition=definition.id,circuits={'window':'P'}) for id,x,y in [('C1',50,50),('C2',100,60)]]
    d.features.append(Feature(id='ANGLE',kind='drilling',face='left',u=40,v=50,circuit='P',diameter=8,depth=112,
                              direction=(1,.2,0),plugged=True,route_net='P'))
    d.nets=[HydraulicNet(id='P',members=['C1:window','C2:window'],routing='automatic',flow_lpm=5)]
    g=build_geometry(d);authorize_generated_contacts(d,g);r=validate(d,g)
    assert r['status']=='PASS',[(c['rule'],c['items'],c['actual']) for c in r['checks'] if c['status']!='PASS']
    assert len([c for c in r['checks'] if c['rule']=='connection_opening_area' and c['status']=='PASS'])==2
    path=tmp_path/'angle.step';cq.exporters.export(g.production,str(path))
    restored=cq.importers.importStep(str(path)).val()
    assert restored.isValid() and len(restored.Solids())==1
    assert restored.Volume()==pytest.approx(g.production.Volume(),abs=.01)
