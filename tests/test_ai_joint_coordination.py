"""Assembly-level regressions; physical acceptance remains the shared CAD gate."""
from manifold.schema import Design,Feature
from manifold.ai_design.joint_routes import improve


def case():
    source=Design(name='QA assembly scheduling',block=dict(length=100,width=100,height=100,material='QA'),
                  nets=[dict(id=n,members=[n+'0',n+'1'],routing='automatic',diameter=8) for n in ('A','B','C')])
    nets={n.id:n for n in source.nets}
    def option(name,level,key):return dict(key=key,route=[Feature(id=name,kind='drilling',face='left',u=level,v=40,
        depth=50,diameter=8,circuit=name,route_net=name,tip_angle=180)],connection_verified=False)
    pools={'A':[option('A',20,'same')],'B':[option('B',30,'same'),option('B',60,'same')],'C':[option('C',50,'same')]}
    return source,nets,pools


def test_insertion_releases_actual_blocker_and_keeps_third_net():
    source,nets,pools=case();seed={n:pools[n][0] for n in ('A','B')}
    def pair(a,ao,b,bo):
        return {('cross_net_wall','B','C')} if {a,b}=={'B','C'} and next(o for n,o in ((a,ao),(b,bo)) if n=='B')['route'][0].u==30 else set()
    best,events,_=improve(source,nets,pools,pair,seed,dict(states=0,limit=100))
    assert len(best)==3 and best['A'] is seed['A']
    assert best['B']['route'][0].u==60
    assert any(e['nets']==['B','C'] for e in events)
    assert not any(o['connection_verified'] for o in best.values())


def test_pair_local_repair_that_hits_third_net_is_not_complete():
    source,nets,pools=case();seed={n:pools[n][0] for n in ('A','B')}
    def pair(a,ao,b,bo):
        if 'B' not in (a,b):return set()
        level=(ao if a=='B' else bo)['route'][0].u
        if ({a,b}=={'B','C'} and level==30) or ({a,b}=={'A','B'} and level==60):return {('cross_net_wall',a,b)}
        return set()
    best,_,_=improve(source,nets,pools,pair,seed,dict(states=0,limit=100))
    assert len(best)==2
    assert all(not pair(a,ao,b,bo) for a,ao in best.items() for b,bo in best.items() if a!=b)


def test_source_change_invalidates_pair_approval_and_changed_terminal():
    from manifold.ai_design.route_catalog import Session,Catalog
    from manifold.engineering_conditions import effective_net
    source,nets,pools=case();session=Session()
    session.context=session.source_context(source,{}, {},{})
    session.pair_evidence={('old',):frozenset()}
    session.seed_combination(source,{'A':pools['A'][0]})
    changed=source.model_copy(deep=True);changed.block.height+=1
    # Only exercise invalidation; no geometry approval can survive this change.
    session.prepare(changed,{}, {},{}, {},[])
    assert session.invalidated and not session.pair_evidence
    assert not session.compatible_core(changed,{},lambda *args:set())
    assert 'A' in session.core_checks['discarded_changed_terminals']


def test_reserved_routes_are_only_pinned_in_a_disposable_context(monkeypatch):
    from manifold.ai_design.joint_routes import corridor_alternatives
    from manifold import routing
    source,nets,pools=case();before=source.model_dump_json();seen=[]
    base={**pools['A'][0],'key':'branch_0_20_30_40:xyz:nearest'}
    reserved=[pools[n][0]['route'][0] for n in ('B','C')]
    def regenerate(context,net,key,*args,**kwargs):
        seen.append(context)
        assert {f.route_net for f in routing._fixed_strategy_source(context).features}=={'B','C'}
        return base['route']
    monkeypatch.setattr(routing,'route_from_variant',regenerate)
    options=corridor_alternatives(source,nets['A'],[base],reserved,{}, {},{},[dict(diameter_mm=8,max_depth_mm=200)],{},allow_bypass=False)
    next(options)
    assert seen and source.model_dump_json()==before
    assert all(n.route_state=='unresolved' for n in source.nets)
