"""Engineering regressions for the d58e907 review; fixtures are not vendor approval."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from manifold import catalog,store,workflow
from manifold.schema import Design,CavityDefinition
from manifold.geometry import build_geometry
from manifold.validation import validate
from manifold.server import app

HEADERS={'X-PMC-Request':'local-console'}

def source_port(depth):
    definition=catalog.definition('metric:lib167:cavity:3')
    return Design(name='Source window regression',block=dict(length=120,width=120,height=120,material='Test'),library=[definition],
        features=[dict(id='PORT_INTERNAL',kind='port',face='top',u=60,v=60,circuit='P',definition=definition.id),
                  dict(id='LATERAL',kind='drilling',face='left',u=60,v=120-depth,circuit='P',diameter=6,depth=64,
                       tip_angle=180,plugged=True,connects_to=['PORT_INTERNAL'])],
        nets=[dict(id='P',members=['PORT_INTERNAL'],routing='manual',flow_lpm=1)])

def test_source_port_shallow_machining_is_not_a_hydraulic_connection(tmp_path):
    bad=source_port(10);g=build_geometry(bad);r=validate(bad,g)
    assert g.cuts['PORT_INTERNAL'].intersect(g.cuts['LATERAL']).Volume()>10
    assert g.nodes['PORT_INTERNAL'].intersect(g.nodes['LATERAL']).Volume()<1e-6
    assert not r['graph']['PORT_INTERNAL']
    assert any(c['rule']=='expected_connection' and c['status']=='FAIL' for c in r['checks'])
    assert any(c['rule']=='port_protected_region' and c['status']=='FAIL' for c in r['checks'])
    assert not any(c['rule']=='connection_opening_area' for c in r['checks'])
    assert not any(c['rule']=='external_wall' and c['status']=='FAIL' for c in r['checks'])
    store.atomic_json(tmp_path/'shallow-fail.json',r)
    good=source_port(25);gg=build_geometry(good);rr=validate(good,gg)
    assert not [c for c in rr['checks'] if c['status']=='FAIL'],rr
    assert 'LATERAL' in rr['graph']['PORT_INTERNAL']
    assert any(c['rule']=='connection_opening_area' and c['status']=='PASS' for c in rr['checks'])
    assert gg.cuts['PORT_INTERNAL'].Volume()==pytest.approx(g.cuts['PORT_INTERNAL'].Volume())
    from manifold.cad import cq
    step=tmp_path/'source-port.step';cq.exporters.export(gg.production,str(step))
    restored=cq.importers.importStep(str(step)).val()
    assert restored.isValid() and restored.Volume()==pytest.approx(gg.production.Volume(),abs=.01)
    store.atomic_json(tmp_path/'window-pass.json',rr)

def test_usage_roles_are_explicit_in_schema_and_saved_library(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'PROJECT',tmp_path/'demo.json')
    native=catalog.definition('metric:lib167:cavity:3')
    assert native.usage_role=='external-port'
    d=source_port(25).model_dump()
    d['features']=[dict(id='CV1',kind='cavity',face='top',u=60,v=60,definition=native.id,circuits={'Port':'P'})]
    d['nets']=[]
    with pytest.raises(ValueError,match='not cartridge-cavity'):Design.model_validate(d)
    ordinary=native.model_dump();ordinary.update(native=None,usage_role=None,usage_decision='')
    definition=CavityDefinition.model_validate(ordinary)
    assert definition.usage_role=='cartridge-cavity' and len(definition.zones)==1
    d=source_port(25).model_dump();d['library']=[definition.model_dump()]
    with pytest.raises(ValueError,match='not external-port'):Design.model_validate(d)
    ordinary['usage_role']='external-port'
    with pytest.raises(ValueError,match='engineering decision'):CavityDefinition.model_validate(ordinary)
    ordinary['usage_decision']='QA engineer confirms external-port role and declared flow window.'
    confirmed=CavityDefinition.model_validate(ordinary)
    saved=workflow.save_library(confirmed)
    loaded=workflow.library_entries()[0]
    assert loaded['definition']['usage_role']=='external-port' and loaded['sha256']==saved['sha256']
    d['library']=[loaded['definition']];assert Design.model_validate(d).features[0].kind=='port'
    client=TestClient(app)
    d['library'][0]['usage_decision']=''
    assert client.post('/api/check-design',json=d,headers=HEADERS).status_code==422
    # A reviewed native role override retains the immutable source identity.
    override=native.model_dump();override.update(usage_role='cartridge-cavity',usage_decision='QA confirms cartridge use for this interpretation.')
    reviewed=CavityDefinition.model_validate(override)
    assert reviewed.native.record==native.native.record
    response=client.post('/api/library/project-native',json=reviewed.model_dump(),headers=HEADERS)
    assert response.status_code==200 and response.json()['usage_role']=='cartridge-cavity'

def test_role_search_preserves_native_unit_identity():
    for unit in ('metric','inch'):
        ports=catalog.search(kind='port_definition',unit=unit,limit=10000)['items']
        cavities=catalog.search(kind='cavity',unit=unit,limit=10000)['items']
        assert ports and cavities
        assert all(r['unit']==unit and r['id'].startswith(unit+':') and r['cavity_type'].upper() in ('P','PORT') for r in ports)
        assert all(r['cavity_type'].upper() not in ('P','PORT') for r in cavities)
        assert not {r['id'] for r in ports}&{r['id'] for r in cavities}

def test_default_route_exact_selection_prefers_simple_valid_machining(tmp_path,monkeypatch):
    from manifold.routing import route_options,resolve_design,authorize_generated_contacts
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    d=Design.model_validate_json((Path(__file__).parent/'fixtures'/'route-cost-vs-proxy.json').read_text())
    options=route_options(d,d.nets[0])
    simple=min(options,key=lambda o:o['cost'])
    proxy=min(options,key=lambda o:(o['risk'],o['cost'],o['key']))
    assert len(simple['route'])==1 and sum(f.plugged for f in simple['route'])==0
    assert len(proxy['route'])>1 and sum(f.plugged for f in proxy['route'])>0
    assert proxy['risk']<simple['risk'] and proxy['cost']>simple['cost']
    for name,option in [('simple',simple),('lower-proxy',proxy)]:
        candidate=d.model_copy(deep=True);candidate.features+=option['route']
        g=build_geometry(candidate);authorize_generated_contacts(candidate,g);r=validate(candidate,g)
        assert r['status']=='PASS',r
        store.atomic_json(tmp_path/(name+'.json'),r)
    # No explicit optimization request or routing_variant: exercise normal resolution.
    resolved,metadata=resolve_design(d,persist=True)
    assert len([f for f in resolved.features if f.route_net=='P'])==1
    g=build_geometry(resolved);authorize_generated_contacts(resolved,g)
    assert validate(resolved,g)['status']=='PASS'
    summary=json.loads((tmp_path/'route-selections'/metadata[0]['selection_evidence']/'summary.json').read_text())
    assert 1<=len(summary['attempts'])<=6
    assert len(summary['attempts'])+len(summary['skipped'])>1
    assert summary['attempts'][summary['selected_attempt']]['score']==min(a['score'] for a in summary['attempts'])
