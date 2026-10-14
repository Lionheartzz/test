"""Reduce saved cancelled evidence. Never run Generate, CAD or a provider."""
import collections
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'output/runtime-checks/engineering-planner-20261014'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    raw=RUN/'complex-frozen-final';cancellation=read(raw/'cancelled-evidence.json')
    rows=[read(p) for p in sorted(raw.rglob('layouts/*.json'))];layouts=[]
    for row in rows:
        a=row['assessment'];solver=a.get('joint_solver',{});joint=a.get('joint_coordination',{})
        layouts.append(dict(index=row['index'],family=row['family'],source_status=row['joint_state']['source_layout_status'],
            screen_seconds=row['screen_seconds'],refinement_seconds=row.get('refinement_seconds'),
            geometry_changes=row['geometry_changes'],source_revision=solver.get('dependency'),
            retained_analytic=a.get('partial_routing',{}).get('nets'),
            local_status={n:v['status'] for n,v in a.get('partial_routing',{}).get('local_admission',{}).items()},
            pools={n:dict(source_clear=p['source_clear'],attempted=p.get('attempted'),
                planned_rejections=[s for s in p.get('rejected_samples',[]) if s['variant'].startswith('engineering-plan:')],
                sampled_rejection_rules=collections.Counter(f[0] for s in p.get('rejected_samples',[]) for f in s['failures']))
                for n,p in a['pools'].items()},completed_refinements=row.get('deep_history',[]),
            pending={k:joint.get(k) for k in ('pending_corridor_batches','unexpanded_compatible_cores','states','samples','labels','raw_probes')},
            continuation=[{k:v.get(k) for k in ('dependency','labels','pending','candidate_count')} for v in solver.get('continuation',[])],
            repair_transactions=[{k:v.get(k) for k in ('released','outside','pending_jobs','independent_states','labels','calls','generated_candidates',
                'fragment_probes','delivered_completions','deferred_pair_candidates')} for v in solver.get('repair_transactions',[])],
            conditional_constraint_count=len(solver.get('conditional_constraints',[])),
            full_saved_layout=dict(path=str(next(raw.rglob(f'layouts/{row["index"]:03}.json')).relative_to(ROOT)),
                sha256=sha(next(raw.rglob(f'layouts/{row["index"]:03}.json'))))))
    generic=[]
    for p in sorted((RUN/'submission-focused').glob('*/**/acceptance.json')):
        e=read(p);generic.append(dict(case=p.parent.parent.name,path=str(p.relative_to(ROOT)),sha256=sha(p),
            status=e['status'],counts=(e.get('validation') or {}).get('counts'),topology=e.get('topology'),step=e.get('step')))
    tests=[]
    for name in ('submission-focused','frozen-isolation','stop-and-limits','normal-deadline','delivery-safe','final-owned-execution','bounded-nested-cad'):
        x=ET.parse(RUN/(name+'.xml')).getroot()[0];tests.append(dict(evidence=name,**x.attrib))
    protected=read(RUN/'protected-reference.json');after={p:sha(Path(p)) for p in protected}
    measured=sum(r['screen_seconds']+(r.get('refinement_seconds') or 0) for r in rows)
    nested=read(next((RUN/'bounded-nested-cad').glob('*/nested-exact.json')))
    nested_acceptance=nested['result']['attempts'][0]
    out=dict(baseline='12409be9e0866f34ccab66a68cb532e5cd6a3836',scope='IMPLEMENTATION_AND_CANCELLED_FAILURE_ANALYSIS',
        complex=dict(status='CANCELLED_AT_USER_REQUEST',last_progress=cancellation['progress'],layouts=layouts,
            evaluated_layouts=len(rows),independent_geometries=len({json.dumps([r['joint_state']['dimensions'],r['joint_state']['placements']],sort_keys=True) for r in rows}),
            peak_recorded_analytic=max(len(r['assessment'].get('partial_routing',{}).get('nets',[])) for r in rows),total_elapsed_lower_bound_s=cancellation['progress']['elapsed_s'],
            completed_screen_and_refinement_s=measured,unassigned_or_inflight_s=cancellation['progress']['elapsed_s']-measured,
            last_observed_process_cpu_s=2451.62,cpu_scope='OS snapshot before interruption, not final CPU and not exclusive Router/CAD time',
            full_exact_attempts=cancellation['full_exact_attempts'],manufacturing_ready=False,
            unavailable_after_interrupt=cancellation['unavailable_after_interrupt'],cache_hits_for_cancelled_run=None,
            exclusive_router_seconds=None,exclusive_cad_seconds=None,source_sha256=sha(next(raw.rglob('authored-draft.json'))),
            source_frozen_manifest=read(raw/'generate-started.json')['source_frozen'],cancellation_mechanism=cancellation['mechanism']),
        bounded_source_rechecks=[read(RUN/n/'result.json') for n in ('bounded-source-recheck','bounded-plug-recheck')],
        generic_witnesses=generic,tests=tests,
        execution_limits=dict(total_s=600,per_layout_active_s=120,total_deep_active_s=90,
            cooperative_grace_s=1,process_stop_wait_max_s=5,scope='NEW_AI_GENERATE_ONLY'),
        deadline_and_cancellation=[read(p) for p in sorted((RUN/'final-owned-execution').glob('*/**/execution.json'))],
        bounded_nested_cad=dict(execution=nested['execution'],status=nested['result']['status'],
            full_cad_evaluated=nested_acceptance['full_cad_evaluated'],topology=nested_acceptance['topology'],
            step=nested_acceptance['step'],counts=nested_acceptance['validation']['counts']),
        previous_aborted=[read(RUN/n/'interrupted.json') for n in ('complex','complex-final','complex-delivery')],
        alternate_dependency=dict(before=read(RUN/'alternative-dependency-before.json'),after=read(RUN/'alternative-dependency-after.json')),
        protected_before=protected,protected_after=after,protected_unchanged=protected==after,
        full_complex_rerun_authorized=False,valid_corridor_and_search_efficiency_gate_demonstrated=False,
        blockers=['Full external machining rays and occupied closures are not completely constrained by current symbolic placement domains',
            'A source-valid domain with a rejected machining plan still falls through to expensive general catalogs and deep routing',
            'MA/MB/P/T have no retained source-clear routes in these layouts; source access is unresolved',
            'Historical original process intents and in-flight cache/frontier counters were incompletely checkpointed',
            'The new timed supervisor has only focused/limited verification; no new complete complex Generate was run'],
        physical_infeasibility_proven=False)
    path=ROOT/'docs/engineering/engineering-layout-planner-evidence.json'
    path.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(dict(layouts=len(rows),screen_and_refinement_s=measured,size=path.stat().st_size,protected_unchanged=protected==after)))


if __name__=='__main__':main()
