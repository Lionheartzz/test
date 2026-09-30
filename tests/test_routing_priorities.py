from manifold.schema import Design,Feature
from manifold.routing import (route_objective,route_options,simplify_generated_route,
                              authorize_generated_contacts,route_obstructions,exact_route_score)
from manifold.geometry import build_geometry
from manifold.validation import validate
import manifold.routing as routing


def straight_net():
    return Design.model_validate(dict(name='Focused priority and pruning case',
        block=dict(length=120,width=120,height=100,material='Aluminum'),
        features=[dict(id='LEFT',kind='port',face='left',u=60,v=50,circuit='P',diameter=12,depth=16),
                  dict(id='RIGHT',kind='port',face='right',u=60,v=50,circuit='P',diameter=12,depth=16)],
        nets=[dict(id='P',routing='automatic',members=['LEFT','RIGHT'],diameter=8)]))


def drilling(identifier,face,depth,u=60,v=50,plugged=False):
    return Feature(id=identifier,kind='drilling',face=face,u=u,v=v,depth=depth,diameter=8,
                   circuit='P',route_net='P',plugged=plugged)


def exact_report(design,route):
    target=design.model_copy(deep=True)
    target.features.extend(route)
    geometry=build_geometry(target)
    authorize_generated_contacts(target,geometry)
    return validate(target,geometry)


def test_exact_graph_removes_subsumed_and_dead_end_generated_cuts_but_keeps_declared_contacts(tmp_path):
    design=straight_net();net=design.nets[0]
    route=[drilling('LONG','left',106),drilling('SHORT','left',60),
           drilling('DEAD','front',65,plugged=True)]
    assert exact_report(design,route)['counts']['FAIL']==0
    simplified,connected=simplify_generated_route(design,net,route)
    assert connected and [f.id for f in simplified]==['LONG']
    assert exact_report(design,simplified)['counts']['FAIL']==0
    assert not route_obstructions(design,net,simplified)
    from manifold.manufacturing import manufacturing_outputs
    manufacturing=design.model_copy(deep=True);manufacturing.features.extend(simplified)
    manufacturing.features[0].machining_id='LEGACY_REF'
    manufacturing_outputs(manufacturing,build_geometry(manufacturing),tmp_path)
    chart=__import__('json').loads((tmp_path/'manufacturing.json').read_text(encoding='utf-8'))['drill_chart']
    assert [row['machining_id'] for row in chart]==['LEGACY_REF','M002','M003']
    assert [row['feature'] for row in chart]==['LEFT','RIGHT','LONG']
    design.features[0].connects_to=['SHORT']
    route[-1].frozen_net='P'
    preserved,connected=simplify_generated_route(design,net,route)
    assert connected and {f.id for f in preserved}=={'LONG','SHORT','DEAD'}


def test_fewer_plugs_and_short_drills_select_distinct_exact_feasible_candidates(monkeypatch):
    design=straight_net();net=design.nets[0]
    long=[drilling('LONG','left',106)]
    short=[drilling('L','left',70),drilling('R','right',70)]
    for route in (long,short):assert exact_report(design,route)['counts']['FAIL']==0
    monkeypatch.setattr(routing,'simple_routes',lambda *_:[long,short])
    monkeypatch.setattr(routing,'propose',lambda *_:long)
    design.constraints.priority='fewer_plugs'
    assert route_options(design,net)[0]['key']=='simple_0'
    design.constraints.priority='short_drills'
    assert route_options(design,net)[0]['key']=='simple_1'
    one_plug=[drilling('ONE','left',100,plugged=True)]
    two_plugs=[drilling('TWO1','left',30,plugged=True),drilling('TWO2','right',30,plugged=True)]
    design.constraints.priority='fewer_plugs'
    assert route_objective(design,one_plug)<route_objective(design,two_plugs)
    design.constraints.priority='short_drills'
    assert route_objective(design,two_plugs)<route_objective(design,one_plug)
    def closure_report(route):
        return dict(counts=dict(FAIL=0,WARNING=len(route)),checks=[dict(rule='construction_closure',
            status='WARNING',items=[f.id],actual='unresolved',required='resolved closure definition') for f in route])
    assert exact_route_score(design,closure_report(two_plugs),two_plugs)[1]==1
    assert exact_route_score(design,closure_report(two_plugs),two_plugs)<exact_route_score(design,closure_report(one_plug),one_plug)


def test_setup_faces_and_geometric_envelope_have_distinct_objectives():
    design=straight_net()
    one_face=[drilling('A','left',50),drilling('B','left',50,u=85)]
    two_faces=[drilling('A','left',50),drilling('B','right',50,u=85)]
    design.constraints.priority='simple_machining'
    assert route_objective(design,one_face)[1]==1
    assert route_objective(design,two_faces)[1]==2
    assert route_objective(design,one_face)<route_objective(design,two_faces)
    near=[drilling('NEAR','left',106,u=60)]
    excursion=[drilling('FAR','left',106,u=100)]
    design.constraints.priority='short_drills'
    assert route_objective(design,near)[:4]==route_objective(design,excursion)[:4]
    design.constraints.priority='compact'
    assert route_objective(design,near)<route_objective(design,excursion)
