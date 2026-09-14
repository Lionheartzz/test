"""Real process/HTTP regression for CAD that monopolizes CPU and the Python GIL."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import pytest
from fastapi.testclient import TestClient
from manifold import store,projects,engineering,server
from manifold.schema import Design

HEADERS={'X-PMC-Request':'local-console'}


def design(name='feasible-cad'):
    return Design(name=name,block=dict(length=120,width=100,height=100,material='QA'),
        features=[dict(id=key,kind='port',face=face,u=50,v=50,circuit='P',diameter=20,depth=20,tip_angle=180)
                  for key,face in [('P1','left'),('P2','right')]],
        nets=[dict(id='P',members=['P1','P2'],routing='automatic',flow_lpm=40,velocity_limit=6)])


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects'/'demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    worker=engineering.Executor([sys.executable,str(Path(__file__).parent/'workers'/'slow_cad.py')])
    monkeypatch.setattr(engineering,'executor',worker);monkeypatch.setattr(server,'executor',worker)
    with TestClient(server.app) as client:
        yield client,worker
    worker.close()


def started(worker):
    until=time.monotonic()+12
    while time.monotonic()<until:
        row=worker.status()['active']
        if row and row.get('phase')=='fixture.native_cpu':return row
        time.sleep(.03)
    pytest.fail('Synthetic native CPU worker did not start')


def gone(pid):
    if sys.platform=='win32':
        import ctypes
        kernel=ctypes.WinDLL('kernel32');kernel.OpenProcess.restype=ctypes.c_void_p
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return True
        code=ctypes.c_ulong();kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        kernel.GetExitCodeProcess(handle,ctypes.byref(code))
        kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle(handle)
        return code.value!=259
    import os
    try:os.kill(pid,0);return False
    except ProcessLookupError:return True


def test_slow_preview_does_not_block_apis_save_or_exact_build(isolated):
    client,worker=isolated;project=projects.save(design());metrics={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending=pool.submit(client.post,'/api/preview-solid',json=design('slow-cad').model_dump(),headers=HEADERS)
        active=started(worker)
        time.sleep(.6)
        if sys.platform=='win32':
            assert active['busy_pid']==active['pid'] # actual interpreter, not a Store activation proxy
            metrics['preview_cpu_delta_s']=round(worker.status()['active']['cpu_s']-active['cpu_s'],4)
            assert metrics['preview_cpu_delta_s']>0
        for path in ['/api/health','/api/projects','/api/engineering/status']:
            start=time.monotonic();reply=pool.submit(client.get,path).result(timeout=1)
            metrics[path]=round(time.monotonic()-start,4);assert reply.status_code==200
        changed=design('saved while CAD busy')
        start=time.monotonic()
        reply=pool.submit(client.post,'/api/projects',json=dict(design=changed.model_dump(),project_id=project['project_id'],expected_revision=project['revision']),headers=HEADERS).result(timeout=1)
        metrics['save']=round(time.monotonic()-start,4);assert reply.status_code==200
        saved=reply.json()
        start=time.monotonic()
        build=client.post('/api/build',json=dict(project_id=saved['project_id'],expected_revision=saved['revision']),headers=HEADERS)
        metrics['build']=round(time.monotonic()-start,4)
        assert build.status_code==200,build.text
        assert build.json()['build']['status']=='PASS'
        assert pending.result(timeout=2).status_code==409
        assert gone(active['busy_pid']) and gone(active['pid'])
        log=worker.status()['recent'][-1]
        operations=log['operations']
        assert operations['geometry.construction']['count']==1
        assert operations['validation']['count']==1
        assert operations['step.export']['count']==operations['step.round_trip']['count']==1
        assert operations['review.generation']['count']==1
        report=json.loads((store.OUTPUT/'builds'/build.json()['build']['build_id']/'validation.json').read_text())
        assert next(c for c in report['checks'] if c['rule']=='step_round_trip')['status']=='PASS'
        assert all(c['status']!='FAIL' for c in report['checks'])
        selection=list((store.OUTPUT/'route-selections').glob('*/summary.json'))
        assert len(selection)==1 and len(json.loads(selection[0].read_text())['attempts'])==1
        metrics['execution']=log
    print('CAD_RESPONSIVENESS_EVIDENCE='+json.dumps(metrics))
    assert worker.status()['active'] is None


def test_superseded_preview_cancel_race_and_authoritative_priority(isolated):
    client,worker=isolated
    headers={**HEADERS,'X-PMC-Preview-Owner':'qa','X-PMC-Preview-Version':'1'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        old=pool.submit(client.post,'/api/preview-solid',json=design('slow-cad').model_dump(),headers=headers)
        active=started(worker)
        cancel=client.post('/api/preview-cancel',json=dict(owner='qa',version=1),headers=HEADERS)
        assert cancel.status_code==200 and old.result(timeout=2).status_code==409
        assert gone(active['busy_pid']) and worker.active is None
        # A cancel arriving before its delayed request cannot resurrect old work.
        assert client.post('/api/preview-solid',json=design().model_dump(),headers=headers).status_code==409
        fresh=client.post('/api/preview-solid',json=design().model_dump(),headers={**headers,'X-PMC-Preview-Version':'2'})
        assert fresh.status_code==200,fresh.text
        assert fresh.json()['model']['geometry_kind']=='machined-brep'
        assert 'validation' not in worker.history[-1]['operations']
        # A transient request must never evict authoritative work.
        row=worker.start('preview-solid',design('slow-cad').model_dump(),transient=False)
        started(worker)
        assert client.post('/api/preview',json=design().model_dump(),headers=headers).status_code==409
        assert worker.active is row and not row['closed']
        worker.stop(row,'End test')


def test_watchdog_kills_orphaned_work_and_recovers_after_native_exit(isolated):
    client,worker=isolated
    row=worker.start('preview-solid',design('slow-cad').model_dump(),transient=True,limit=4)
    active=started(worker)
    until=time.monotonic()+6
    while not row['closed'] and time.monotonic()<until:time.sleep(.03)
    assert row['closed'] and gone(active['busy_pid']) and worker.active is None
    with pytest.raises(engineering.CalculationError,match='exceeded'):worker.poll(row)
    assert worker.history[-1]['state']=='timeout' and not row['work'].exists()
    crashed=client.post('/api/preview',json=design('crash-cad').model_dump(),headers=HEADERS)
    assert crashed.status_code==422 and 'code 9; result rejected' in crashed.json()['detail']
    assert worker.active is None
    recovered=client.post('/api/preview',json=design().model_dump(),headers=HEADERS)
    assert recovered.status_code==200,recovered.text


def test_failed_check_is_never_reused_as_a_prepared_success(tmp_path,monkeypatch):
    import manifold.validation as validation
    d=design()
    monkeypatch.setattr(validation,'validate',lambda *a:(_ for _ in ()).throw(RuntimeError('exact check failed')))
    with pytest.raises(RuntimeError,match='No usable exact solid'):
        store.build_outputs(d,tmp_path/'build')
    assert not (tmp_path/'build'/'validation.json').exists()


def test_save_during_authoritative_calculation_rejects_stale_commit(isolated):
    _,worker=isolated;p=projects.save(design());plan=projects.prepare_build(p['project_id'],p['revision'])
    newer=projects.save(design('newer engineering decision'),p['project_id'],p['revision'])
    with pytest.raises(ValueError,match='changed'):
        projects.finish_build(plan,dict(status='PASS',counts={}))
    current=projects.snapshot(projects.read(p['project_id']))
    assert current['revision']==newer['revision'] and current['build'] is None


def test_engine_code_identity_is_stable_across_cold_and_warm_bytecode(tmp_path,monkeypatch):
    from manifold import engine
    # A new file forces the same cold-compile vs worker-cache transition as an update.
    source=engine.ROOT/'server.py'
    (tmp_path/'server.py').write_bytes(source.read_bytes())
    monkeypatch.setattr(engine,'ROOT',tmp_path)
    cold=engine.code_manifest();warm=engine.code_manifest()
    assert cold==warm
    (tmp_path/'server.py').write_text('value = 123456789\n')
    assert engine.code_manifest()!=warm


def test_explicit_optimization_preempts_transient_without_saving(isolated):
    client,worker=isolated;p=projects.save(design());before=projects.path(p['project_id']).read_bytes()
    row=worker.start('preview-solid',design('slow-cad').model_dump(),transient=True)
    active=started(worker)
    response=client.post('/api/optimize-routes',json=dict(project_id=p['project_id'],expected_revision=p['revision'],max_attempts=1),headers=HEADERS)
    assert response.status_code==200,response.text
    assert len(response.json()['attempts'])==1 and response.json()['status']=='PASS'
    assert row['closed'] and gone(active['busy_pid'])
    assert projects.path(p['project_id']).read_bytes()==before


def test_drawing_calculation_cancel_kills_native_work(isolated):
    _,worker=isolated
    def progress(message):
        if 'fixture.native_cpu' in message:raise InterruptedError('User cancelled drawing')
    with pytest.raises(InterruptedError,match='cancelled drawing'):
        engineering.calculate_sync('preview-solid',design('slow-cad').model_dump(),progress)
    assert worker.active is None and worker.history[-1]['state']=='cancelled'
    assert gone(worker.history[-1]['busy_pid'])


def test_large_preview_transfer_does_not_reencode_mesh_on_api_loop(isolated):
    client,_=isolated
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=pool.submit(client.post,'/api/preview-solid',json=design('large-cad').model_dump(),headers=HEADERS)
        probes=0
        while not pending.done():
            assert pool.submit(client.get,'/api/health').result(timeout=1).status_code==200
            probes+=1;time.sleep(.02)
        response=pending.result(timeout=2)
    assert response.status_code==200,response.text[:300]
    assert probes>1 and len(response.json()['vertices'])==1_000_000


def test_diagnostic_file_lock_does_not_abort_or_skip_engineering(tmp_path,monkeypatch):
    from manifold import timing
    for key in ('_path','_started','_counts','_stack','_last_write','_write_errors'):
        monkeypatch.setattr(timing,key,getattr(timing,key))
    def locked(*args):raise PermissionError('Windows status reader holds destination')
    monkeypatch.setattr(Path,'replace',locked)
    timing.configure(tmp_path/'trace.json')
    calls=[]
    with timing.phase('exact.check'):calls.append('performed')
    assert calls==['performed'] and timing.summary()['operations']['exact.check']['count']==1
    assert timing.summary()['diagnostic_write_errors']>=1
    with pytest.raises(ValueError,match='real engineering failure'):
        with timing.phase('exact.check'):raise ValueError('real engineering failure')
