"""Workspace ownership and queued/running deletion guards; no CAD/model calls."""
import json
import pytest
from test_ai_design import client,create,HEADERS
from manifold import store,projects
from manifold.ai_design import service,jobs

DELETE_HEADERS={**HEADERS,'Content-Type':'application/json'}

def test_management_summary_and_owned_delete_preserve_project_asset_and_other_task(client,tmp_path):
    task=create(client);other=create(client);key=task['id']
    saved=client.post('/api/projects',json={'design':{'schema_version':3,'name':'Saved manifold','block':{'length':80,'width':80,'height':80,'material':'QA'}}},headers=HEADERS).json()
    record=service.read(key);record['generations']=[dict(id='a'*32,status='draft',created_at=service.now())];service.write(record)
    output=store.OUTPUT/'ai-design'/key;store.atomic_json(output/'current.json',{'owned':True});store.atomic_json(output/'generations'/'draft'/'generation.json',{'owned':True})
    job=dict(id='b'*32,task_id=key,process=jobs._process,status='completed',result={'owned':True});store.atomic_json(jobs.path(job['id']),job)
    project_path=projects.path(saved['project_id']);project_bytes=project_path.read_bytes()
    assets={p:p.read_bytes() for p in (store.PROJECT.parent/'assets').glob('*') if p.is_file()}
    row=next(r for r in client.get('/api/ai-design/tasks').json() if r['id']==key)
    assert row['document_names']==['schematic.png'] and row['generated_draft_count']==1
    assert client.delete('/api/ai-design/tasks/'+key,headers=DELETE_HEADERS).status_code==200
    assert not service.path(key).exists() and not output.exists() and not jobs.path(job['id']).exists()
    assert service.path(other['id']).exists() and project_path.read_bytes()==project_bytes
    assert all(p.read_bytes()==data for p,data in assets.items())
    assert client.delete('/api/ai-design/tasks/'+key,headers=DELETE_HEADERS).status_code==404

@pytest.mark.parametrize('operation,status',[('analyze','queued'),('analyze','running'),('generate','queued'),('generate','running')])
def test_running_workspace_cannot_be_deleted(client,monkeypatch,operation,status):
    task=create(client);job=dict(id='c'*32,task_id=task['id'],operation=operation,status=status,process=jobs._process)
    store.atomic_json(jobs.path(job['id']),job);monkeypatch.setattr(jobs,'_active',job['id'])
    r=client.delete('/api/ai-design/tasks/'+task['id'],headers=DELETE_HEADERS)
    assert r.status_code==409 and service.path(task['id']).exists()

def test_delete_keeps_local_request_boundary_and_validated_identifier(client):
    task=create(client)
    assert client.delete('/api/ai-design/tasks/'+task['id']).status_code==403
    assert client.delete('/api/ai-design/tasks/not-an-id',headers=DELETE_HEADERS).status_code==422
    assert service.path(task['id']).exists()
