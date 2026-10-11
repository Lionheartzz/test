"""Source-bound review adoption and ownership; no paid provider or CAD."""
import copy
import pytest
from test_ai_design import client, create, analyze, HEADERS
from manifold.ai_design import service
from manifold.ai_design.intent import effective_result
from manifold.ai_design.generation_models import PortCorrections


def packet(run):
    p=next(p for p in run['result']['ports'] if p['component_id'])
    return dict(schema_version=1,task_id=run['task_id'],run_id=run['id'],input_revision=run['input_revision'],
        result_sha256=service.digest(run['result']),port_labels={p['id']:'Reviewed interface'},port_dispositions={},
        net_assignments={p['id']:'Reviewed real connection'},reasons={p['id']:'Source line traced by reviewer'})


def test_review_preview_then_explicit_apply_preserves_immutable_run(client):
    task=create(client); response=analyze(client,task);run=response['run'];record=service.read(task['id'])
    before=copy.deepcopy(run['result']);source=service.run_path(task['id'],run['id']).read_bytes()
    review=packet(run);payload=dict(expected_revision=service.digest(record),run_id=run['id'],topology_review=review,preview_only=True)
    path=f"/api/ai-design/tasks/{task['id']}/port-corrections"
    preview=client.post(path,json=payload,headers=HEADERS)
    assert preview.status_code==200,preview.text
    assert service.read(task['id'])==record
    result=preview.json()['reviewed_result'];key=next(iter(review['port_labels']))
    assert next(p for p in result['ports'] if p['id']==key)['label']=='Reviewed interface'
    assert any(n['label']=='Reviewed real connection' and key in n['members'] for n in result['nets'])
    payload['preview_only']=False
    adopted=client.post(path,json=payload,headers=HEADERS)
    assert adopted.status_code==200,adopted.text
    assert service.run_path(task['id'],run['id']).read_bytes()==source
    assert run['result']==before and 'port_corrections' in service.read(task['id'])
    assert client.post(path,json=payload,headers=HEADERS).status_code==409


def test_review_rejects_other_revision_missing_reason_and_functional_termination(client):
    task=create(client);run=analyze(client,task)['run'];review=packet(run)
    for field in ('task_id','run_id','input_revision','result_sha256'):
        bad=copy.deepcopy(review);bad[field]='a'*len(bad[field])
        with pytest.raises(ValueError,match='different analysis'):
            effective_result(run,PortCorrections(run_id=run['id'],input_revision=run['input_revision'],topology_review=bad).model_dump())
    bad=copy.deepcopy(review);bad['reasons']={}
    with pytest.raises(ValueError,match='reason'):
        effective_result(run,PortCorrections(run_id=run['id'],input_revision=run['input_revision'],topology_review=bad).model_dump())
    boundary=next(p for p in run['result']['ports'] if not p['component_id'])['id']
    bad=copy.deepcopy(review);bad['port_dispositions'][boundary]='terminated';bad['reasons'][boundary]='Unsupported shortcut'
    with pytest.raises(ValueError,match='external functional'):
        effective_result(run,PortCorrections(run_id=run['id'],input_revision=run['input_revision'],topology_review=bad).model_dump())


def test_termination_retains_interface_without_a_fake_net():
    result=dict(components=[dict(id='C',port_ids=['P1','P2'])],ports=[dict(id='P1',component_id='C',label='1'),
        dict(id='P2',component_id='C',label='2')],nets=[dict(id='N',label='N',members=['P1','P2'])])
    run=dict(task_id='a'*32,id='b'*32,input_revision='c'*64,result=result)
    review=dict(schema_version=1,task_id=run['task_id'],run_id=run['id'],input_revision=run['input_revision'],
        result_sha256=service.digest(result),port_dispositions={'P1':'terminated'},reasons={'P1':'Source: nose not used'})
    new=effective_result(run,PortCorrections(run_id=run['id'],input_revision=run['input_revision'],topology_review=review).model_dump())
    assert new['components'][0]['port_ids']==['P1','P2']
    assert new['ports'][0]['disposition']=='terminated' and new['nets'][0]['members']==['P2']
    assert result['nets'][0]['members']==['P1','P2']
