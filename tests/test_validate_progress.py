from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import pytest
from fastapi.testclient import TestClient
from manifold import engineering,projects,server,store,timing
from manifold.validation_progress import public_progress
from test_cad_execution import design

OP='a'*32
HEADERS={'X-PMC-Request':'local-console'}


@pytest.fixture
def lane(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects'/'demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    worker=engineering.Executor([sys.executable,str(Path(__file__).parent/'workers'/'validate_progress.py')])
    monkeypatch.setattr(engineering,'executor',worker);monkeypatch.setattr(server,'executor',worker)
    with TestClient(server.app,base_url='http://127.0.0.1:8765') as client:yield client,worker
    worker.close()


def active(worker):
    until=time.monotonic()+8
    while time.monotonic()<until:
        if worker.active and worker.describe(worker.active).get('progress',{}).get('candidate')==2:return worker.active
        time.sleep(.02)
    pytest.fail('Owned progress worker did not reach candidate 2')


def test_real_trace_milestones_are_monotonic_bounded_and_reset_per_request(tmp_path):
    timing.configure(tmp_path/'trace.json')
    values=[]
    for stage,percent in [('routes',8),('geometry',17),('topology',21),('alternate',22.5),('geometry',24.5),('step',85),('alternate',30),('geometry',32),('step_verified',93),('finalizing',99)]:
        timing.progress(stage,percent,candidate=2,candidate_limit=8);values.append(timing.summary()['progress']['percent'])
    assert values==sorted(values) and all(p<100 for p in values)
    assert values[6]>values[5]
    for _ in range(50):timing.progress('finalizing',99)
    assert len(timing.summary()['progress']['events'])==32
    timing.configure(tmp_path/'next.json');assert timing.summary()['progress']=={'events':[]}


def test_public_status_hides_internal_phase_and_waits_for_authoritative_commit():
    row=dict(id=OP,project_id='b'*32,operation='build',state='completed',phase='operation.build / boolean.cut',
             elapsed_s=42,progress=dict(stage='geometry',percent=99,candidate=2,candidate_limit=8,events=[]))
    result=public_progress(row)
    assert result['stage_text']=='Building exact geometry' and result['detail']=='Route candidate 2 of up to 8'
    assert result['state']=='running' and result['percent']==99 and 'phase' not in result
    row['result_state']='complete';assert public_progress(row)['percent']==100


def test_progress_is_owned_read_only_and_duplicate_id_does_not_rewrite_result(lane):
    client,worker=lane;project=projects.save(design())
    body=dict(project_id=project['project_id'],expected_revision=project['revision'],operation_id=OP)
    url='/api/engineering/progress/'+OP+'?project_id='+project['project_id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=pool.submit(client.post,'/api/build',json=body,headers=HEADERS);row=active(worker)
        progress=client.get(url).json()
        assert progress['operation_id']==OP and progress['candidate']==2 and progress['percent']<100
        assert client.get('/api/engineering/progress/'+OP+'?project_id='+'b'*32).status_code==404
        assert client.get('/api/engineering/progress/'+'c'*32).status_code==404
        assert client.post('/api/build',json=body,headers=HEADERS).status_code==409
        for _ in range(5):assert client.get(url).status_code==200
        assert worker.active is row and not row['closed']
        (row['work']/'release').write_text('')
        reply=pending.result(timeout=10);assert reply.status_code==200,reply.text
    assert reply.json()['operation_id']==OP
    completed=client.get(url).json();assert completed['state']=='complete' and completed['percent']==100
    assert client.post('/api/build',json=body,headers=HEADERS).status_code==409
    assert client.get(url).json()['state']=='complete'


def test_project_changed_during_build_marks_owned_progress_failed(lane):
    client,worker=lane;project=projects.save(design())
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(client.post,'/api/build',json=dict(project_id=project['project_id'],expected_revision=project['revision'],operation_id=OP),headers=HEADERS)
        row=active(worker)
        projects.save(design('newer project'),project['project_id'],project['revision'])
        (row['work']/'release').write_text('')
        assert pending.result(timeout=10).status_code==409
    progress=client.get('/api/engineering/progress/'+OP+'?project_id='+project['project_id']).json()
    assert progress['state']=='failed' and progress['percent']<100


def test_preview_is_not_exposed_as_validate_progress(lane):
    _,worker=lane
    row=worker.start('preview',design().model_dump(),transient=True,owner='preview-only',version=1)
    try:assert worker.progress(row['id']) is None
    finally:worker.stop(row,'Test complete')


def test_watchdog_error_ends_progress_without_completion(lane):
    _,worker=lane
    row=worker.start('build',dict(design=design().model_dump()),operation_id=OP,limit=.4)
    until=time.monotonic()+5
    while not row['closed'] and time.monotonic()<until:time.sleep(.02)
    assert row['closed']
    result=worker.progress(OP);assert result['state']=='failed' and result['percent']<100


def test_invalid_operation_id_cannot_be_used_as_trace_path(lane):
    client,_=lane;project=projects.save(design())
    result=client.post('/api/build',json=dict(project_id=project['project_id'],expected_revision=project['revision'],operation_id='../other'),headers=HEADERS)
    assert result.status_code==422
    assert client.get('/api/engineering/progress/bad').status_code==404
