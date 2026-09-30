"""Focused reproduction from the observed manifold and corrected source geometry."""
import json
from pathlib import Path

from manifold import engineering_db, store
from manifold.routing import resolve_design, route_obstructions
from manifold.schema import CavityDefinition, Design, Feature


def observed():
    fixture=json.loads(Path('tests/fixtures/automatic-t10a.json').read_text())
    return (Design.model_validate(fixture['design']),
            {key:CavityDefinition.model_validate(value) for key,value in fixture['definitions'].items()})


def signature(design):
    return sorted((f.id,f.face,f.u,f.v,f.depth,f.diameter,f.plugged)
                  for f in design.features if f.route_net)


def test_observed_four_net_manifold_selects_exact_clear_routes_and_rebuilds_identically(monkeypatch,tmp_path):
    design,definitions=observed()
    before=design.model_dump()
    monkeypatch.setattr(engineering_db,'definitions_for_design',lambda _:definitions)
    monkeypatch.setattr(store,'OUTPUT',tmp_path)
    resolved,routes,geometry,report=resolve_design(design,prepared=True,persist=True)
    assert report['counts']['FAIL']==0,report
    assert geometry.production.isValid()
    assert len(geometry.production.Solids())==1
    for net in resolved.nets:
        assert not route_obstructions(resolved,net,[f for f in resolved.features if f.route_net==net.id],
                                      definitions=definitions)
    pinned=design.model_copy(deep=True)
    for net in pinned.nets:
        net.routing_variant=next(r['variant'] for r in routes if r['net']==net.id)
    rebuilt,_=resolve_design(pinned,exact=False)
    assert signature(rebuilt)==signature(resolved)
    assert design.model_dump()==before
    store.atomic_json(tmp_path/'selected-validation.json',report)


def test_full_bore_allows_only_assigned_window_and_enforces_source_wall():
    design,definitions=observed()
    net=next(n for n in design.nets if n.id=='A')
    def route(identifier,x,z):
        return [Feature(id=identifier,kind='drilling',face='front',u=x,v=z,
                        circuit='A',route_net='A',diameter=8,depth=104,plugged=True)]
    allowed=route('WINDOW',53,167.44)
    assert not route_obstructions(design,net,allowed,definitions=definitions)
    protected=route('PROTECTED',53,180)
    assert ('source_protected','CV1','PROTECTED') in route_obstructions(design,net,protected,definitions=definitions)
    separated=route('THIN_WALL',36,180)
    assert ('source_wall','CV1','THIN_WALL') in route_obstructions(design,net,separated,definitions=definitions)
    unassigned=net.model_copy(update=dict(members=[m for m in net.members if not m.startswith('CV1:')]))
    assert ('source_wall','CV1','WINDOW') in route_obstructions(design,unassigned,allowed,definitions=definitions)


def test_source_port_and_mounting_modifier_block_full_bore_after_plug_engagement():
    design,definitions=observed()
    net=next(n for n in design.nets if n.id=='A')
    port=CavityDefinition(id='source_port',label='Source external port',kind='external-port',
                          stages=[dict(start=0,end=30,diameter=18)],
                          zones=[dict(id='inlet',start=20,end=30,diameter=18)],
                          clearance_diameter=20,clearance_height=10)
    design.features=[Feature(id='SOURCE',kind='port',face='top',u=53,v=100,
                             port_definition_id=port.id,circuit='T')]
    definitions={port.id:port}
    route=[Feature(id='BORE',kind='drilling',face='front',u=53,v=180,
                   circuit='A',route_net='A',diameter=8,depth=104,plugged=True)]
    failures=route_obstructions(design,net,route,definitions=definitions)
    assert ('source_wall','BORE','SOURCE') in failures
    assert not any(f[0]=='plug_cut' for f in failures)
    design.features=[Feature(id='MOUNT',kind='mounting',face='top',u=66,v=100,
                             diameter=6,depth=30,machining_modifiers=[dict(modifier_id='counterbore',start=10)])]
    modifiers={'counterbore':dict(primitives=[dict(kind='cylinder',start=0,end=15,diameter=24)])}
    assert ('cross_net_wall','BORE','MOUNT') in route_obstructions(
        design,net,route,definitions={},thread_definitions={},modifier_definitions=modifiers)
