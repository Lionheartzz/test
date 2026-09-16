"""Ordinary six-component editing: source-pinned stepped cavities and four nets."""
from concurrent.futures import ThreadPoolExecutor
import json
import time
import pytest
from fastapi.testclient import TestClient
from manifold import catalog,engineering,server,store
from manifold.schema import Design
from manifold.geometry import build_geometry,review_model
from manifold.routing import resolve_design


def editing_manifold():
    definition=catalog.definition('metric:lib130:cavity:273')
    return Design(name='Two cavity interactive regression',
        block=dict(length=160,width=100,height=150,material='Fixture'),library=[definition],
        features=[dict(id=n,kind='port',face='front',u=32*(i+1),v=75,circuit=n,
                       diameter=12,depth=16,tip_angle=118) for i,n in enumerate(('P','T','A','B'))]+
                 [dict(id='CV1',kind='cavity',face='top',u=53,v=50,definition=definition.id,circuits=dict(port1='P',port2='A')),
                  dict(id='CV2',kind='cavity',face='bottom',u=107,v=50,definition=definition.id,circuits=dict(port1='T',port2='B'))],
        nets=[dict(id=n,members=[n,member],routing='automatic') for n,member in
              [('P','CV1:port1'),('T','CV2:port1'),('A','CV1:port2'),('B','CV2:port2')]])


def test_moving_cavity_converges_below_watchdog_and_keeps_exact_layers(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    worker=engineering.Executor();monkeypatch.setattr(engineering,'executor',worker);monkeypatch.setattr(server,'executor',worker)
    d=editing_manifold();source=d.library[0].model_dump();evidence=[]
    with TestClient(server.app) as client,ThreadPoolExecutor(max_workers=2) as pool:
        for u,v in [(107,50),(106,50),(97,53),(107,50)]:
            d.features[-1].u=u;d.features[-1].v=v
            start=time.monotonic()
            pending=pool.submit(client.post,'/api/preview-solid',json=d.model_dump(),headers={'X-PMC-Request':'local-console','Accept':'application/x-ndjson'})
            while not pending.done():
                assert pool.submit(client.get,'/api/health').result(timeout=1).status_code==200
                time.sleep(.1)
            reply=pending.result();assert reply.status_code==200,reply.text
            elapsed=time.monotonic()-start
            assert elapsed<14, f'Ordinary exact preview must finish below the 15 second watchdog: {elapsed}'
            events=[json.loads(line) for line in reply.text.splitlines()]
            assert [e['type'] for e in events]==['proposal','exact'],events
            exact=events[-1]['result'];model=exact['model'];parts=model['parts']
            assert next(f for f in events[0]['result']['design']['features'] if f['id']=='CV2')['u']==u
            assert model['geometry_kind']=='machined-brep'
            assert {p['circuit'] for p in parts if p['kind']=='hydraulic-net'}=={'P','T','A','B'}
            assert any(p['kind']=='body' and p['triangles'] for p in parts)
            void=next(p for p in parts if p['kind']=='machined-void')
            assert void['volume_mm3']>0 and void['triangles']
            # Current proposals can have invalid topology (including the real
            # reproduction). Expose it; do not turn display success into PASS.
            assert isinstance(model['brep_valid'],bool)
            if model['brep_valid']:
                assert void['volume_mm3']==pytest.approx(160*100*150-model['volume_mm3'],abs=.01)
            assert next(f for f in exact['features'] if f['id']=='CV2')['u']==u
            trace=worker.history[-1]
            assert trace['limit_s']==15 and trace['state']=='completed'
            assert trace['operations']['geometry.construction']['count']==1
            assert trace['operations']['route.resolution']['count']==1
            # Separately budget CAD/review so variable cold interpreter startup
            # cannot disguise a return of the pathological review operation.
            assert trace['operations']['operation.preview-solid']['seconds']<8
            assert 'validation' not in trace['operations'] and 'step.export' not in trace['operations']
            evidence.append(dict(position=[u,v],elapsed_s=round(elapsed,3),operations=trace['operations']))
    assert d.library[0].model_dump()==source
    assert not (store.OUTPUT/'builds').exists() and not (store.OUTPUT/'route-selections').exists()
    print('INTERACTIVE_EDIT_EVIDENCE='+json.dumps(evidence))


def test_review_has_no_unification_and_preserves_exact_production_and_void(monkeypatch):
    from manifold.cad import cq
    from test_v1_engineering_views import bores
    d=bores();g=build_geometry(d)
    before=(g.production.Volume(),g.production.Area(),g.production.isValid())
    def forbidden(*args,**kwargs):raise AssertionError('Review must not run same-domain face unification')
    monkeypatch.setattr(cq.Shape,'clean',forbidden)
    monkeypatch.setattr(cq.Compound,'clean',forbidden)
    model=review_model(d,g)
    assert (g.production.Volume(),g.production.Area(),g.production.isValid())==pytest.approx(before)
    assert next(p for p in model['parts'] if p['kind']=='machined-void')['volume_mm3']==pytest.approx(g.block.Volume()-before[0])


@pytest.mark.parametrize('cross',[False,True])
def test_review_failure_keeps_full_validation_and_step_evidence(tmp_path,monkeypatch,cross):
    import manifold.geometry as geometry
    from test_v1_engineering_views import bores
    from manifold.cad import cq
    def fail(*args):raise RuntimeError('mesh fixture failed')
    monkeypatch.setattr(geometry,'review_model',fail)
    folder=tmp_path/'build';report=store.build_outputs(bores(cross=cross),folder)
    assert report['status']==('FAIL' if cross else 'PASS')
    assert next(c for c in report['checks'] if c['rule']=='step_round_trip')['status']=='PASS'
    assert json.loads((folder/'validation.json').read_text())['counts']==report['counts']
    assert cq.importers.importStep(str(folder/'production.step')).val().isValid()
    assert json.loads((folder/'review.json').read_text())['review_error']=='Review unavailable: mesh fixture failed'


def test_exact_preview_reports_display_failure_separately(monkeypatch):
    import manifold.geometry as geometry
    from manifold.cad_worker import dispatch
    from test_v1_engineering_views import bores
    def fail(*args):raise RuntimeError('tessellation fixture failed')
    monkeypatch.setattr(geometry,'review_model',fail)
    with pytest.raises(RuntimeError,match='Exact BRep construction completed; display review unavailable: tessellation fixture failed'):
        dispatch('preview-solid',bores().model_dump())
