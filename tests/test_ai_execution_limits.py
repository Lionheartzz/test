"""AI-only clock accounting and real owned-process interruption."""
import json
import time
from pathlib import Path
import pytest
from manifold.ai_design.execution import Deadlines,supervise
from manifold.ai_design.generation_models import GenerationOptions
from test_engineering_layout_planner import shared_sources
from test_ai_generation import client,analyzed,selection_request


def test_finite_defaults_and_per_layout_cumulative_time():
    now=[0.];b=Deadlines(total=20,layout=4,deep=3,clock=lambda:now[0])
    b.advance(dict(layout=1,deep=False));now[0]=2;b.advance(dict(layout=2,deep=False))
    now[0]=4;b.advance(dict(layout=1,deep=False));now[0]=6
    assert b.advance(dict(layout=1,deep=False))=='LAYOUT_TIME_LIMIT'
    assert b.layouts=={1:4,2:2}
    now[0]=0;b=Deadlines(total=20,layout=10,deep=3,clock=lambda:now[0])
    b.advance(dict(layout=0,deep=True));now[0]=3
    assert b.advance(dict(layout=0,deep=True))=='DEEP_ROUTING_TIME_LIMIT'
    now[0]=0;b=Deadlines(total=2,clock=lambda:now[0]);now[0]=2
    assert b.advance({})=='TOTAL_TIME_LIMIT'
    assert GenerationOptions().max_runtime_s is None and GenerationOptions().max_layout_runtime_s==120
    with pytest.raises(ValueError):GenerationOptions(max_deep_runtime_s=0)


def test_real_native_work_is_timeboxed_and_source_checkpoint_retained(monkeypatch,tmp_path):
    from manifold import store
    d,defs=shared_sources();before=d.model_dump_json()
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output');monkeypatch.setattr(store,'PROJECT',tmp_path/'projects/demo.json')
    started=time.monotonic()
    out=supervise(dict(operation='plan-snapshot',design=d.model_dump(),definitions={k:v.model_dump() for k,v in defs.items()},
        layout_limit=1,exact_limit=0),limits=dict(total=12,layout=.4,deep=.3))
    assert time.monotonic()-started<17,out
    assert out['execution']['reason'] in ('LAYOUT_TIME_LIMIT','TOTAL_TIME_LIMIT'),out
    assert out['checkpoint'] and out['checkpoint']['manufacturing_ready'] is False
    assert out['checkpoint']['design']['features']
    assert out['execution']['exit_code'] is not None
    assert d.model_dump_json()==before
    (tmp_path/'time-limit-evidence.json').write_text(json.dumps(out,indent=2),encoding='utf-8')


def test_real_worker_cancellation_uses_owned_process_and_keeps_evidence(monkeypatch,tmp_path):
    from manifold import store
    d,defs=shared_sources();monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects/demo.json')
    events=[]
    out=supervise(dict(operation='plan-snapshot',design=d.model_dump(),definitions={k:v.model_dump() for k,v in defs.items()},
        layout_limit=1,exact_limit=0),limits=dict(total=12,layout=10,deep=10),
        cancelled=lambda:bool(list((tmp_path/'output').glob('ai-generation-execution/*/checkpoint.json'))))
    assert out['execution']['reason']=='USER_CANCELLED' and out['checkpoint']
    assert out['execution']['exit_code'] is not None
    assert Path(out['evidence'],'timing.json').is_file()
    (tmp_path/'cancellation-evidence.json').write_text(json.dumps(out,indent=2),encoding='utf-8')


def test_normal_generate_time_limit_publishes_checkpoint_without_touching_model(client,tmp_path):
    from manifold.ai_design import generation,service
    task,run=analyzed(client);original_run=service.run_path(task['id'],run['id']).read_bytes()
    request=selection_request(task,run,max_runtime_s=12,max_layout_runtime_s=.4,max_deep_runtime_s=.3)
    result=generation.generate(task['id'],request)
    assert result['status']=='incomplete_draft',result
    assert result['route_status'] in ('LAYOUT_TIME_LIMIT','TOTAL_TIME_LIMIT','DEEP_ROUTING_TIME_LIMIT'),result
    assert result['design'] and result['validation'] is None and result['manufacturing_ready'] is False
    assert service.run_path(task['id'],run['id']).read_bytes()==original_run
    assert len(service.read(task['id'])['generations'])==1
    assert not (tmp_path/'projects/saved').exists()
    restored=generation.load_generation(task['id'],result['id'])
    assert restored['design']==result['design']
    (tmp_path/'normal-deadline.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


def test_existing_job_cancel_event_stops_real_ai_worker_and_retains_draft(client,tmp_path):
    from manifold.ai_design import jobs,service
    task,run=analyzed(client);before=service.run_path(task['id'],run['id']).read_bytes()
    request=selection_request(task,run,max_runtime_s=12,max_layout_runtime_s=10,max_deep_runtime_s=3)
    job=jobs.start(task['id'],'generate',request.model_dump());started=time.monotonic();cancel_sent=False
    while time.monotonic()-started<16:
        current=jobs.read(job['id'])
        if current.get('initial_generation_id') and not cancel_sent:
            jobs.cancel(job['id']);cancel_sent=True
        if current['status'] not in ('queued','running'):break
        time.sleep(.05)
    assert cancel_sent and current['status']=='completed',current
    result=current['result'];assert result['status']=='cancelled' and result['design']
    assert result['execution']['reason']=='USER_CANCELLED' and result['execution']['exit_code'] is not None
    assert result['validation'] is None and result['manufacturing_ready'] is False
    assert service.run_path(task['id'],run['id']).read_bytes()==before
    assert len(service.read(task['id'])['generations'])==1
    (tmp_path/'job-cancellation.json').write_text(json.dumps(current,indent=2),encoding='utf-8')


def test_owned_worker_keeps_nested_production_exact_brep_step_gate(monkeypatch,tmp_path):
    from manifold import store
    from test_corridor_planner import crossing
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output');monkeypatch.setattr(store,'PROJECT',tmp_path/'projects/demo.json')
    out=supervise(dict(operation='plan-snapshot',design=crossing().model_dump(),layout_limit=2,exact_limit=1),
        limits=dict(total=12,layout=8,deep=2))
    assert out['execution']['reason']=='COMPLETED',out
    assert out['result']['status']=='EXACT_FEASIBLE',out
    attempt=out['result']['attempts'][0]
    assert attempt['full_cad_evaluated'] and attempt['topology']==dict(valid=True,solids=1)
    assert attempt['step']['status']=='PASS'
    (tmp_path/'nested-exact.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
