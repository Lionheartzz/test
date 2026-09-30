"""Manufacturing dominance, fair pre-pruning retention and bounded exact optimization."""
import json
from pathlib import Path
import pytest
from manifold import routing as r, engineering_db, store
from manifold.schema import Design
from manifold.geometry import build_geometry
from manifold.validation import validate
from test_routing_priorities import straight_net, drilling, exact_report
from test_routing_obstacles import observed


def test_candidate_below_old_top16_survives_family_shortlist_and_real_pruning(monkeypatch):
    design=straight_net();net=design.nets[0]
    alternatives=[[drilling(f'L{i}','left',70+i/2),drilling(f'R{i}','right',70+i/2)] for i in range(20)]
    late=[drilling('LONG','left',106),drilling('SHORT','left',60),
          drilling('DEAD','front',65,plugged=True),drilling('DEAD2','back',75,plugged=True)]
    key='axial_1_0:xyz:nearest'
    # The label exercises retention only; no synthetic eligibility is exposed
    # to production. Every pruning/contact/clearance check uses real OCCT cuts.
    import manifold.cavity_access as access
    monkeypatch.setattr(access,'axial_route_candidates',lambda *a:[(key,late)])
    monkeypatch.setattr(r,'simple_routes',lambda *a:alternatives)
    monkeypatch.setattr(r,'propose',lambda *a:alternatives[0])
    raw=r.route_candidate_catalog(design,net,{}, {}, {})
    ordered=sorted(raw,key=lambda o:(r.route_objective(design,o['route']),o['key']))
    assert next(i for i,o in enumerate(ordered) if o['key']==key)>=16
    snapshot=r._ProposalSnapshot(design,{}, {}, {})
    inspected=[];simplify=snapshot.simplify
    def measured(d,n,route,**kwargs):
        inspected.append(tuple(f.id for f in route));return simplify(d,n,route,**kwargs)
    monkeypatch.setattr(snapshot,'simplify',measured)
    options=r.route_options(design,net,definitions={},thread_definitions={},modifier_definitions={},snapshot=snapshot)
    assert options[0]['key']==key and [f.id for f in options[0]['route']]==['LONG']
    assert {'SHORT','DEAD','DEAD2'}==set(options[0]['pruned_ids'])
    assert len(inspected)<=16 and tuple(f.id for f in late) in inspected
    assert options[0]['metrics']['plugs']==0 and options[0]['metrics']['drillings']==1
    assert exact_report(design,options[0]['route'])['counts']['FAIL']==0


def test_prepared_first_zero_fail_is_compared_with_better_clear_objective(monkeypatch,tmp_path):
    design=straight_net();design.nets[0].routing_variant='simple_1'
    long=[drilling('LONG','left',106)]
    short=[drilling('L','left',70),drilling('R','right',70)]
    monkeypatch.setattr(r,'simple_routes',lambda *a:[long,short])
    monkeypatch.setattr(r,'propose',lambda *a:long)
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    target,metadata,g,report=r.resolve_design(design,prepared=True,persist=True)
    assert report['counts']['FAIL']==0 and metadata[0]['variant']=='simple_0'
    evidence=json.loads((tmp_path/'route-selections'/metadata[0]['selection_evidence']/'summary.json').read_text())
    assert len(evidence['attempts'])==2 and evidence['attempts'][0]['score'][0]==0
    assert evidence['attempts'][1]['score']<evidence['attempts'][0]['score']
    assert g.production.isValid() and len([f for f in target.features if f.route_net])==1


def test_exact_optimization_keeps_eight_attempt_ceiling_with_further_real_improvements(monkeypatch,tmp_path):
    design=straight_net();design.nets[0].routing_variant='simple_0'
    routes=[[drilling(f'R{i}','left',110-i/10)] for i in range(20)]
    monkeypatch.setattr(r,'simple_routes',lambda *a:routes)
    monkeypatch.setattr(r,'propose',lambda *a:routes[0])
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    modes=[]
    def next_move(best,target,metadata,report,eligible,inspected,**kwargs):
        modes.append(kwargs['repair_only'])
        index=int(metadata[0]['variant'].split('_')[1])+1
        candidate=best.model_copy(deep=True);candidate.nets[0].routing_variant=f'simple_{index}'
        return [((),candidate,(('P',f'simple_{index}'),),'Next actual clear shorter bore')]
    monkeypatch.setattr(r,'alternative_proposals',next_move)
    _,metadata,_,report=r.resolve_design(design,prepared=True,persist=True)
    assert report['counts']['FAIL']==0 and metadata[0]['exact_attempts']==8
    assert metadata[0]['variant']=='simple_7' and modes==[False]*7


def test_explicit_optimizer_improves_feasible_baseline_using_shared_pools(monkeypatch,tmp_path):
    from manifold.optimization import search_routes
    design=straight_net();design.nets[0].routing_variant='simple_1'
    before=design.model_dump()
    long=[drilling('LONG','left',106)]
    short=[drilling('L','left',70),drilling('R','right',70)]
    monkeypatch.setattr(r,'simple_routes',lambda *a:[long,short])
    monkeypatch.setattr(r,'propose',lambda *a:long)
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    result=search_routes(design,max_attempts=3)
    assert result['baseline']['FAIL']==result['final']['FAIL']==0
    assert result['selected_attempt']==1 and len(result['attempts'])==2
    assert result['attempts'][1]['objective']<result['attempts'][0]['objective']
    assert result['design']['nets'][0]['routing_variant']=='simple_0' and design.model_dump()==before


def test_pareto_dominance_respects_tradeoffs_and_all_lexicographic_priorities():
    design=straight_net()
    better=[drilling('B','left',50,plugged=True)]
    worse=[drilling('W','left',60,plugged=True),drilling('W2','right',60,plugged=True)]
    for priority in ('fewer_plugs','simple_machining','short_drills','compact'):
        design.constraints.priority=priority
        assert r.route_dominates(design,better,worse)
        assert not r.route_dominates(design,worse,better)
    long=[drilling('LONG','left',106)]
    short=[drilling('L','left',70),drilling('R','right',70)]
    design.constraints.priority='fewer_plugs'
    assert r.route_objective(design,long)<r.route_objective(design,short)
    assert not r.route_dominates(design,long,short)  # Worse maximum depth is a real tradeoff.
    design.constraints.priority='short_drills'
    assert r.route_objective(design,short)<r.route_objective(design,long)
    near=[drilling('N','left',106)]
    far=[drilling('F','left',106,u=100)]
    design.constraints.priority='compact'
    assert r.manufacturing_metrics(design,near)['compactness']<r.manufacturing_metrics(design,far)['compactness']


def test_real_t10a_selected_nets_have_no_compatible_clear_pareto_dominator(monkeypatch,tmp_path):
    source,definitions=observed();before=source.model_dump()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    target,metadata,g,report=r.resolve_design(source,prepared=True,persist=True)
    assert report['counts']['FAIL']==0,report
    assert 1<=metadata[0]['exact_attempts']<=8
    assert g.production.isValid() and source.model_dump()==before
    snapshot=r._ProposalSnapshot(source,definitions,{}, {})
    rows={}
    for net in source.nets:
        current=[f for f in target.features if f.route_net==net.id]
        context=target.model_copy(update=dict(features=[f for f in target.features if f.route_net!=net.id]))
        legal=[];dominators=[]
        # Audit the entire generated source catalog, not merely the selected
        # shortlist. All options share one source BRep/individual-cut cache.
        for option in r.route_candidate_catalog(source,net,definitions,{}, {}):
            raw=option['route']
            if r.route_obstructions(source,net,raw,{},definitions,{}):continue
            simplified,connected=snapshot.simplify(source,net,raw,known_failures=set())
            if not connected:continue
            failures=r.route_obstructions(context,net,simplified,{},definitions,{})
            record=dict(variant=option['key'],before=r.manufacturing_metrics(source,raw,definitions=definitions),
                        after=r.manufacturing_metrics(source,simplified,definitions=definitions),obstructions=sorted(failures))
            legal.append(record)
            if not failures and r.route_dominates(source,simplified,current,definitions=definitions):dominators.append(record)
        assert not dominators,(net.id,dominators)
        if net.id=='P':assert any(row['variant'].startswith('axial_') for row in legal)
        rows[net.id]=dict(selected=next(m for m in metadata if m['net']==net.id),alternatives=legal)
    store.atomic_json(tmp_path/'real-candidate-dominance.json',dict(counts=report['counts'],nets=rows))
    assert all(check['status']=='PASS' for check in report['checks'] if check['rule'] in {'connected_interface','circuit_connectivity','cavity_protected_region'})


def test_snapshot_analytic_cache_matches_uncached_and_invalidates_changed_geometry(monkeypatch):
    source,definitions=observed();net=next(n for n in source.nets if n.id=='P')
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    cache={}
    for option in r.route_candidate_catalog(source,net,definitions,{}, {})[:10]:
        route=option['route']
        assert r.route_obstructions(source,net,route,{},definitions,{})==r.route_obstructions(source,net,route,{},definitions,{},cache)
        assert r.proximity_risk(source,net,route,definitions,{})==r.proximity_risk(source,net,route,definitions,{},cache)
    source.block.height+=10
    route[0].diameter+=2
    assert r.route_obstructions(source,net,route,{},definitions,{})==r.route_obstructions(source,net,route,{},definitions,{},cache)
