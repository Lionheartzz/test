import json
from pathlib import Path
import pytest
from manifold import cad_acceptance,geometry,routing,store
from manifold.cad import cq
from manifold.schema import Design
from test_routing_priorities import straight_net,drilling


def two_candidates(monkeypatch):
    design=straight_net();design.nets[0].routing_variant='simple_0'
    preferred=[drilling('BAD','left',106)]
    alternate=[drilling('GOOD-L','left',70),drilling('GOOD-R','right',70)]
    monkeypatch.setattr(routing,'simple_routes',lambda *a:[preferred,alternate])
    monkeypatch.setattr(routing,'propose',lambda *a:preferred)
    assert routing.route_objective(design,preferred)<routing.route_objective(design,alternate)
    return design


def invalid_solid():
    # A real open OCCT shell, not a mocked validation status.
    box=cq.Solid.makeBox(10,10,10)
    solid=cq.Solid.makeSolid(cq.Shell.makeShell(box.Faces()[:-1]))
    assert not solid.isValid() and len(solid.Solids())==1
    return solid


def selection(tmp_path,metadata):
    return json.loads((tmp_path/'route-selections'/metadata[0]['selection_evidence']/'summary.json').read_text())


@pytest.mark.parametrize('entry',('resolve','optimize'))
def test_exact_acceptance_rejects_real_invalid_brep_and_uses_worse_clear_route(monkeypatch,tmp_path,entry):
    design=two_candidates(monkeypatch);before=design.model_dump()
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    build=geometry.build_geometry
    def with_bad_boolean(d,*args,**kwargs):
        result=build(d,*args,**kwargs)
        if any(f.id=='BAD' and f.route_net for f in d.features):result.production=invalid_solid()
        return result
    monkeypatch.setattr(geometry,'build_geometry',with_bad_boolean)
    if entry=='resolve':
        target,metadata,g,report=routing.resolve_design(design,prepared=True,persist=True)
        evidence=selection(tmp_path,metadata)
    else:
        from manifold.optimization import search_routes
        result=search_routes(design,max_attempts=3)
        target,metadata=routing.resolve_design(Design.model_validate(result['design']),exact=False)
        g=geometry.build_geometry(target);report={'counts':result['final']}
        evidence=json.loads((tmp_path/'route-selections'/result['selection_evidence']/'summary.json').read_text())
    assert evidence['attempts'][0]['production']==dict(valid=False,solids=1)
    assert evidence['fixed_production']==dict(valid=True,solids=1)
    assert evidence['selected_attempt']==1 and len(evidence['attempts'])==2
    assert metadata[0]['variant']=='simple_1' and report['counts']['FAIL']==0
    assert g.production.isValid() and len(g.production.Solids())==1
    assert evidence['attempts'][1]['objective']>evidence['attempts'][0]['objective']
    assert design.model_dump()==before


def test_build_recovers_failed_step_gate_without_mocking_route_selection(monkeypatch,tmp_path):
    design=two_candidates(monkeypatch);before=design.model_dump()
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'evidence')
    round_trip=cad_acceptance.step_round_trip;seen=[]
    def exporter_result(g,path=None):
        row=round_trip(g,path);seen.append('BAD' in g.cuts)
        if 'BAD' in g.cuts:
            row.update(status='FAIL',valid=False,actual='invalid STEP solid; volume Δ 0.000001 mm³')
        return row
    monkeypatch.setattr(cad_acceptance,'step_round_trip',exporter_result)
    report=store.build_outputs(design,tmp_path/'build')
    resolved=Design.model_validate_json((tmp_path/'build'/'resolved_design.json').read_text())
    assert seen==[True,False] and report['counts']['FAIL']==0
    assert report['route_proposals'][0]['variant']=='simple_1'
    step=[c for c in report['checks'] if c['rule']=='step_round_trip']
    assert len(step)==1 and step[0]['status']=='PASS'
    imported=cq.importers.importStep(str(tmp_path/'build'/'production.step')).val()
    assert imported.isValid() and len(imported.Solids())==1
    assert any(f.id=='GOOD-L' for f in resolved.features) and not any(f.id=='BAD' for f in resolved.features)
    assert design.model_dump()==before


def test_fixed_invalid_geometry_does_not_trigger_unrelated_automatic_search(monkeypatch,tmp_path):
    design=two_candidates(monkeypatch);monkeypatch.setattr(store,'OUTPUT',tmp_path)
    build=geometry.build_geometry
    def fixed_failure(d,*args,**kwargs):
        result=build(d,*args,**kwargs);result.production=invalid_solid();return result
    monkeypatch.setattr(geometry,'build_geometry',fixed_failure)
    monkeypatch.setattr(routing,'alternative_proposals',lambda *a,**k:pytest.fail('Fixed geometry must not trigger rerouting'))
    _,metadata,_,report=routing.resolve_design(design,prepared=True,persist=True)
    evidence=selection(tmp_path,metadata)
    assert len(evidence['attempts'])==1 and not evidence['fixed_production']['valid']
    assert any(c['rule']=='solid_validity' and c['status']=='FAIL' for c in report['checks'])


def test_manual_frozen_geometry_is_preserved_on_step_failure(monkeypatch,tmp_path):
    design=straight_net();design.nets[0].routing='manual'
    fixed=drilling('FROZEN','left',106);fixed.route_net=None;fixed.frozen_net='P'
    fixed.connects_to=['LEFT','RIGHT'];design.features.append(fixed)
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    monkeypatch.setattr(routing,'alternative_proposals',lambda *a,**k:[])
    gate=cad_acceptance.step_round_trip
    def failed_serialization(g,path=None):
        row=gate(g,path);row.update(status='FAIL',valid=False,actual='invalid STEP solid');return row
    monkeypatch.setattr(cad_acceptance,'step_round_trip',failed_serialization)
    target,metadata,_,report=routing.resolve_design(design,prepared=True)
    assert metadata==[] and target.model_dump()==design.model_dump() and report['counts']['FAIL']==1
    assert report['checks'][-1]['rule']=='step_round_trip'


def test_invalid_cad_cannot_win_any_design_priority():
    d=straight_net();cheap=[drilling('A','left',106)]
    dear=[drilling('B','left',70),drilling('C','right',70)]
    invalid=dict(counts=dict(FAIL=1),checks=[dict(rule='solid_validity',status='FAIL',items=['block'])])
    valid=dict(counts=dict(FAIL=0),checks=[])
    for priority in ('fewer_plugs','simple_machining','short_drills','compact'):
        d.constraints.priority=priority
        assert routing.exact_route_score(d,valid,dear)<routing.exact_route_score(d,invalid,cheap)


def test_step_failure_row_names_invalid_topology_even_with_small_volume_delta(monkeypatch):
    from types import SimpleNamespace
    d=straight_net();g=geometry.build_geometry(d)
    imported=SimpleNamespace(isValid=lambda:False,Solids=lambda:g.production.Solids(),
                             Volume=lambda tol=None:g.production.Volume(tol)+0.0001489)
    monkeypatch.setattr(cq.importers,'importStep',lambda _:SimpleNamespace(val=lambda:imported))
    row=cad_acceptance.step_round_trip(g)
    assert row['status']=='FAIL' and row['valid'] is False
    assert 'invalid STEP solid' in row['actual'] and row['solids']==1
    assert row['volume_delta_mm3']<0.01


def test_current_real_project_selects_valid_brep_and_step_deterministically(monkeypatch,tmp_path):
    source=Design.model_validate_json((Path(__file__).parent/'fixtures'/'automatic-cad-topology.json').read_text(encoding='utf-8'))
    before=source.model_dump();monkeypatch.setattr(store,'OUTPUT',tmp_path)
    baseline,metadata=routing.resolve_design(source,exact=False)
    g=geometry.build_geometry(baseline)
    assert not g.production.isValid() and len(g.production.Solids())==1
    target,routes,g,report=routing.resolve_design(source,prepared=True,persist=True)
    assert report['counts']['FAIL']==0 and cad_acceptance.topology_clear(g)
    step=next(c for c in report['checks'] if c['rule']=='step_round_trip')
    assert step['status']=='PASS' and step['valid'] and step['solids']==1 and step['volume_delta_mm3']<0.01
    assert 1<routes[0]['exact_attempts']<=8
    for net in ('P','T','B'):
        assert next(r['variant'] for r in routes if r['net']==net)==next(r['variant'] for r in metadata if r['net']==net)
    pinned=source.model_copy(deep=True)
    for net in pinned.nets:net.routing_variant=next(r['variant'] for r in routes if r['net']==net.id)
    repeated,_=routing.resolve_design(pinned,exact=False)
    assert [(f.id,f.face,f.depth) for f in repeated.features]==[(f.id,f.face,f.depth) for f in target.features]
    assert source.model_dump()==before
