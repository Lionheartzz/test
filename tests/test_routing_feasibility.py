"""Real OCCT P/T conflict: cost never buys permission for physical failure."""
import json
from pathlib import Path
import pytest
from manifold import store, optimization
from manifold.schema import Design
from manifold.routing import (resolve_design, route_options, route_cost,
                              authorize_generated_contacts, alternative_proposals)
from manifold.geometry import build_geometry
from manifold.validation import validate


def crossing(pinned=False):
    d=Design.model_validate_json(Path('tests/fixtures/automatic-cross-net.json').read_text())
    if pinned:
        for n in d.nets:n.routing_variant='xyz:nearest:direct'
    return d


def exact_report(design):
    g=build_geometry(design)
    authorize_generated_contacts(design,g)
    return g,validate(design,g)


def assert_feasible(d):
    g,r=exact_report(d)
    assert r['counts']['FAIL']==0,r
    for rule in ('circuit_intersection','circuit_connectivity','external_wall','minimum_feature_wall'):
        assert all(c['status']=='PASS' for c in r['checks'] if c['rule']==rule)
    assert sum(c['rule']=='circuit_connectivity' for c in r['checks'])==2
    for a in g.nodes:
        for b in g.nodes:
            if g.circuits[a]!=g.circuits[b]:assert g.nodes[a].intersect(g.nodes[b]).Volume()<1e-6
    return r


def signature(d):
    return sorted((f.id,f.face,f.u,f.v,f.depth,f.plugged) for f in d.features if f.route_net)


def test_current_proposal_rejects_already_generated_cheaper_collision():
    baseline,_=resolve_design(crossing(True),exact=False)
    _,bad=exact_report(baseline)
    assert any(c['rule']=='circuit_intersection' and c['status']=='FAIL' for c in bad['checks'])
    context=baseline.model_copy(deep=True)
    context.features=[f for f in context.features if f.route_net!='P']
    options=route_options(context,next(n for n in context.nets if n.id=='P'))
    old=min(options,key=lambda o:(o['cost']+o['risk'],o['cost'],o['key']))
    assert old['hard_failures']>0 and options[0]['hard_failures']==0
    assert options[0]['cost']>old['cost']
    current,_=resolve_design(crossing(),exact=False)
    assert_feasible(current)
    assert route_cost(current,[f for f in current.features if f.route_net])>route_cost(baseline,[f for f in baseline.features if f.route_net])
    assert sum(f.plugged for f in current.features)>sum(f.plugged for f in baseline.features)


def test_save_reconsiders_both_conflicting_automatic_variants_deterministically(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    d=crossing(True);baseline,routes=resolve_design(d,exact=False)
    _,bad=exact_report(baseline)
    proposals=alternative_proposals(d,baseline,routes,bad,{'P','T'},set())
    changed=[{n.id for n in c.nets if n.routing_variant!='xyz:nearest:direct'} for _,c,_,_ in proposals]
    assert {'P'} in changed and {'T'} in changed and {'P','T'} in changed
    resolved,metadata=resolve_design(d,persist=True)
    good=assert_feasible(resolved)
    store.atomic_json(tmp_path/'baseline-fail.json',bad)
    store.atomic_json(tmp_path/'selected-pass.json',good)
    assert any('2' in r['variant'] for r in metadata)
    assert route_cost(resolved,[f for f in resolved.features if f.route_net])>route_cost(baseline,[f for f in baseline.features if f.route_net])
    reverse=d.model_copy(deep=True);reverse.nets.reverse()
    repeated,_=resolve_design(reverse)
    assert signature(repeated)==signature(resolved)
    assert_feasible(repeated)
    evidence=json.loads((tmp_path/'route-selections'/metadata[0]['selection_evidence']/'summary.json').read_text())
    assert 1<len(evidence['attempts'])<=6
    assert evidence['attempts'][evidence['selected_attempt']]['score'][0]==0


def test_transient_can_revisit_net_routed_first():
    d=crossing();d.nets[1].routing_variant='xyz:nearest:direct'
    # P was proposed first, then T's current trunk makes it invalid. Revisit P.
    resolved,metadata=resolve_design(d,exact=False)
    assert next(r['variant'] for r in metadata if r['net']=='P')!='simple_0'
    assert next(r['variant'] for r in metadata if r['net']=='T')=='xyz:nearest:direct'
    assert_feasible(resolved)


def test_explicit_optimizer_spends_budget_on_conflict_and_preserves_evidence(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    monkeypatch.setattr(store,'PROJECT',tmp_path/'project.json')
    d=crossing(True);store.atomic_json(store.PROJECT,d.model_dump())
    monkeypatch.setattr(store,'read_design',lambda: Design.model_validate_json(store.PROJECT.read_text()))
    result=optimization.optimize_routes(d,store.revision(d),max_attempts=6)
    assert result['baseline']['FAIL']>0 and result['final']['FAIL']==0
    assert len(result['attempts'])<=6 and result['improved']
    resolved,_=resolve_design(Design.model_validate(result['design']),exact=False)
    assert_feasible(resolved)
    assert store.read_design()==d  # optimization does not save the user project


@pytest.mark.parametrize('priority',['fewer_plugs','short_drills','simple_machining','compact'])
def test_preferences_cannot_outvote_known_failure(priority):
    d=crossing();d.constraints.priority=priority
    resolved,_=resolve_design(d,exact=False)
    assert_feasible(resolved)
