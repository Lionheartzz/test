"""Finite E3 continuation / E6 early-CAD replay from the saved real evidence.

No paid AI or complete Generate. --search performs the real 128+128 versus
256-label comparison. The reference shares only immutable geometry facts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from copy import deepcopy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from manifold.schema import Design,Feature
from manifold import engineering_db as db
from manifold.drilling_planner import plan_net
from manifold.routing_continuation import AISearchContext
from manifold.ai_design.route_catalog import Session
from manifold.ai_design.joint_routes import coordinate
from manifold.routing import route_obstructions
from types import SimpleNamespace

OUT=ROOT/'output/runtime-checks/phase-b-20261013/final'
RUN=ROOT/'output/runtime-checks/global-ai-20261013/fair-scheduling-generate'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(name,data):
    (OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def search():
    row=read(RUN/'layout-optimization/layouts/038.json');d=Design.model_validate(row['design'])
    defs=db.definitions_for_design(d);threads=db.thread_definitions_for_design(d);tools=db.tool_definitions('drill')
    partial=row['assessment']['partial_routing'];reserved=[Feature.model_validate(f) for f in partial['features']]
    net=next(n for n in d.nets if n.id not in partial['nets']);split=AISearchContext(trace=True);geometry={};runs=[]
    for labels in (128,128):
        started=time.monotonic()
        options,detail=plan_net(d,net,defs,threads,{},reserved=reserved,tools=tools,label_limit=labels,
            alternatives=2,ai_context=split,cache=geometry)
        runs.append(dict(seconds=time.monotonic()-started,detail=detail,candidates=[o['key'] for o in options]))
        print('E3 batch:',detail['labels'],detail['cumulative_labels'],detail['all_frontier_labels'],flush=True)
    saved=split.searches[split.last_key];write('e3-split-trace',saved.trace)
    # Independent search state, identical engineering and action ordering.
    # Reusing complete-cut facts cannot reuse seen/frontier/terminal trees.
    reference=AISearchContext(trace=True);started=time.monotonic()
    options,detail=plan_net(d,net,defs,threads,{},reserved=reserved,tools=tools,label_limit=256,
        alternatives=2,ai_context=reference,cache=geometry)
    continuous=reference.searches[reference.last_key];write('e3-continuous-trace',continuous.trace)
    first_states={json.dumps(r,sort_keys=True) for r in saved.trace[:128]}
    second_states={json.dumps(r,sort_keys=True) for r in saved.trace[128:256]}
    result=dict(net=net.id,runs=runs,continuous=dict(seconds=time.monotonic()-started,detail=detail,candidates=[o['key'] for o in options]),
        same_trace=saved.trace==continuous.trace,same_candidates=set(saved.candidates)==set(continuous.candidates),
        same_candidate_features=sorted(json.dumps([f.model_dump(mode='json') for f in o['route']],sort_keys=True) for o in saved.candidates.values())==
            sorted(json.dumps([f.model_dump(mode='json') for f in o['route']],sort_keys=True) for o in continuous.candidates.values()),
        second_batch_repeated_prefix=saved.trace[:128]==saved.trace[128:256],labels=len(saved.trace),
        independent_frontiers=saved is not continuous,geometry_only_cache_reused=saved.space.actions is continuous.space.actions,
        reference_new_machining_evaluations=continuous.space.generated)
    result.update(unique_first_batch=len(first_states),unique_second_batch=len(second_states),
                  repeated_states_between_batches=len(first_states&second_states))
    write('e3',result)
    assert result['same_trace'] and result['same_candidates'] and result['same_candidate_features'] and result['labels']==256
    assert not result['second_batch_repeated_prefix'] and result['independent_frontiers']
    assert result['repeated_states_between_batches']==0
    # Output batching does not lose routes: drain the real pending candidate
    # buffers without spending or repeating a single search label.
    pending_split,split_detail=plan_net(d,net,defs,threads,{},reserved=reserved,tools=tools,label_limit=0,
        alternatives=max(1,len(saved.candidates)),ai_context=split,cache=geometry)
    pending_ref,ref_detail=plan_net(d,net,defs,threads,{},reserved=reserved,tools=tools,label_limit=0,
        alternatives=max(1,len(continuous.candidates)),ai_context=reference,cache=geometry)
    assert split_detail['labels']==ref_detail['labels']==0
    assert saved.delivered==set(saved.candidates) and continuous.delivered==set(continuous.candidates)
    result.update(all_candidates_available=True,pending_drained=[len(pending_split),len(pending_ref)])
    write('e3',result)
    print('E3 comparison passed',flush=True)
    return result


def admission():
    row=read(RUN/'layout-optimization/layouts/045.json');d=Design.model_validate(row['design'])
    defs=db.definitions_for_design(d);threads=db.thread_definitions_for_design(d);tools=db.tool_definitions('drill')
    nets={n.id:n for n in d.nets};partial=row['assessment']['partial_routing']
    core={n:dict(key='saved-core:'+n,risk=0,route=[Feature.model_validate(f) for f in partial['features'] if f['route_net']==n])
          for n in partial['nets']}
    original={n:[f.model_dump_json() for f in o['route']] for n,o in core.items()}
    session=Session();session.catalogs={n:SimpleNamespace(definitions=defs,threads=threads,modifiers={},tools=tools) for n in core}
    def pair(a,ao,b,bo):
        context=d.model_copy(update=dict(features=[*d.features,*ao['route'],*bo['route']]))
        return route_obstructions(context,nets[a],ao['route'],threads,defs,{}, {})|route_obstructions(context,nets[b],bo['route'],threads,defs,{}, {})
    kept,detail=coordinate(session,d,nets,{n:[core[n]] if n in core else [] for n in nets},pair,core,
                           dict(states=0,limit=32),labels=0,fragments=False)
    records=session.local_records
    errors=[r for r in records.values() if r['status']=='CAD_EVALUATION_ERROR']
    assert len(errors)==1 and errors[0]['cad_error']['reason_code']=='INVALID_TOPOLOGY'
    assert errors[0]['physical_connectivity'] is None and len(kept)==5
    assert all(records[n]['status']=='LOCAL_EXACT_ADMISSIBLE' for n in kept)
    from manifold.routing import _verify_route_candidate,_ProposalSnapshot
    failed_name=errors[0]['net'];default=deepcopy(core[failed_name])
    context=d.model_copy(update=dict(features=[*d.features,*[f for o in core.values() for f in o['route']]]))
    admitted=_verify_route_candidate(context,nets[failed_name],default,_ProposalSnapshot(context,defs,threads,{}))
    assert not admitted and default['cad_geometry_error']['reason_code']=='INVALID_TOPOLOGY'
    assert default['cad_geometry_error']['node_pair']==errors[0]['cad_error']['node_pair']
    assert original=={n:[f.model_dump_json() for f in o['route']] for n,o in core.items()}
    used=session.local_admission.used
    assert set(session.admit_core(d,nets,core))==set(kept) and session.local_admission.used==used
    result=dict(records=records,confirmed_nets=sorted(kept),diagnostics=session.local_admission.diagnostics(),
        candidate_geometry_preserved=True,partial_not_full_design_approval=True,
        production_default_prune_check=dict(admitted=admitted,cad_error=default['cad_geometry_error']),
        coordination=dict(initial=detail['initial_compatible'],kept=detail['best_compatible'],missing=detail['missing_nets']))
    write('e6',result);print('E6 early admission passed',flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--search',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    protected=read(RUN/'protected-before.json');before={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in protected}
    assert before==protected;write('protected-before',before)
    e3=search() if args.search else read(OUT/'e3.json') if (OUT/'e3.json').exists() else None
    e6=admission()
    assert before=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
    write('protected-after',before)
    write('acceptance',dict(E3=e3,E6=e6,protected_files=len(before),protected_unchanged=True,
        E3_replayed_this_run=args.search,
        full_generate_run=False,full_complex_exact_brep_step_accepted=False,phase_c_implemented=False))
