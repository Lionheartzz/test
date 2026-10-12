"""Real JSON/API/fresh-worker persistence, with all search entries forbidden."""
import json
import subprocess
import sys
from pathlib import Path

from test_ai_design import client,HEADERS
from test_corridor_planner import crossing,verify_case
from manifold.drilling_planner import coordinate_routes,materialized_proposal
from manifold import route_state,routing,store,engineering_db


def test_save_reload_fresh_exact_worker_edit_and_explicit_reroute(client,monkeypatch,tmp_path):
    d=crossing();before=d.model_dump_json()
    chosen,detail=coordinate_routes(d,d.nets,{}, {}, {},label_limit=256)
    assert chosen,detail
    proposed,rows=materialized_proposal(d,chosen,detail)
    assert all(n.routing_variant is None for n in proposed.nets)
    definitions_for_design=engineering_db.definitions_for_design
    proposed,_=verify_case(d,chosen,{},tmp_path/'planned',monkeypatch,detail)
    monkeypatch.setattr(engineering_db,'definitions_for_design',definitions_for_design)
    saved=client.post('/api/projects',json=dict(design=proposed.model_dump()),headers=HEADERS)
    assert saved.status_code==200,saved.text
    loaded=client.get('/api/projects/'+saved.json()['project_id']).json()['design']
    assert all(n['route_state']=='committed' and n['routing_variant'] is None for n in loaded['nets'])
    assert loaded['features']==proposed.model_dump(mode='json')['features']
    path=tmp_path/'worker-project.json';path.write_text(json.dumps(loaded),encoding='utf-8')
    code='''
import sys,json
from pathlib import Path
from manifold.schema import Design
from manifold import routing,drilling_planner,store
from manifold.cad_worker import dispatch
def forbidden(*a,**k):raise AssertionError('Save/Reload/Validate/Build must not search')
for name in ('resolve_design','_resolve_proposals','route_options','_complete_route_combination'):setattr(routing,name,forbidden)
drilling_planner.plan_net=forbidden;drilling_planner.coordinate_routes=forbidden
d=Design.model_validate_json(Path(sys.argv[1]).read_text());before=d.model_dump_json()
checked=dispatch('validate',d.model_dump())
assert checked['report']['counts']['FAIL']==0,checked['report']
assert checked['design']['features']==d.model_dump()['features']
report=store.build_outputs(d,Path(sys.argv[2]))
assert report['counts']['FAIL']==0,report
assert d.model_dump_json()==before
print(json.dumps(dict(counts=report['counts'],search_called=False,feature_count=len(d.features))))
'''
    completed=subprocess.run([sys.executable,'-c',code,str(path),str(tmp_path/'worker-build')],capture_output=True,text=True)
    assert completed.returncode==0,completed.stdout+completed.stderr
    (tmp_path/'worker-result.json').write_text(completed.stdout,encoding='utf-8')
    from manifold.schema import Design
    current=Design.model_validate(loaded)
    geometry_before=[f.model_dump_json() for f in current.features]
    current.nets[0].flow_lpm=40
    stale=route_state.refresh_conditions(current,{current.nets[0].id},{current.nets[0].id})
    assert [f.model_dump_json() for f in stale.features]==geometry_before
    assert stale.nets[0].route_state=='stale'
    from manifold.route_edit import freeze
    frozen=freeze(Design.model_validate(loaded),'P',Design.model_validate(loaded))
    item=next(f for f in frozen.features if f.frozen_net=='P');item.depth+=.25
    changed=client.post('/api/projects',json=dict(design=frozen.model_dump()),headers=HEADERS)
    assert changed.status_code==200,changed.text
    reloaded=client.get('/api/projects/'+changed.json()['project_id']).json()['design']
    assert reloaded['features']==frozen.model_dump(mode='json')['features']
    released=frozen.model_copy(deep=True)
    released.features=[f for f in released.features if f.route_net!='T']
    next(n for n in released.nets if n.id=='T').route_state='unresolved'
    preserved=[f.model_dump_json() for f in released.features if f.frozen_net]
    new,_=routing.resolve_design(released,exact=False)
    assert [f.model_dump_json() for f in new.features if f.frozen_net]==preserved
    assert new.block==released.block and d.model_dump_json()==before
    assert [(f.id,f.face,f.u,f.v) for f in new.features if f.kind=='port']==[(f.id,f.face,f.u,f.v) for f in released.features if f.kind=='port']


def test_insufficient_same_net_contact_is_not_excused_by_other_connections():
    from manifold.schema import Design,Feature
    d=Design(name='Incidental direct contact',block=dict(length=100,width=100,height=100,material='QA'),rules=dict(minimum_wall=2,minimum_overlap_volume=.1),
        features=[dict(id='E1',kind='port',face='front',u=40,v=40,diameter=8,depth=20,circuit='N'),
                  dict(id='E2',kind='port',face='front',u=47.95,v=80,diameter=8,depth=20,circuit='N')],
        nets=[dict(id='N',routing='automatic',diameter=8)])
    route=[Feature(id=key,kind='drilling',face=face,u=u,v=v,depth=depth,diameter=8,circuit='N',route_net='N',plugged=True,plug_length=16)
        for key,face,u,v,depth in [('Y1','front',40,40,60),('Y2','front',47.95,80,60),('Z1','bottom',40,56,84),('Z2','bottom',47.95,56,84),('BRIDGE','left',56,60,51.95)]]
    option=dict(key='incidental',route=route,risk=0)
    assert not routing._verify_route_candidate(d,d.nets[0],option,routing._ProposalSnapshot(d,{}, {}, {}),prune=False)
    assert option['connection_verified'] and not option['admission']['direct_contact_adequate']
    assert not routing._candidate_admitted(option)


def test_pending_neighbour_does_not_release_committed_route(monkeypatch):
    from manifold.preview_routing import PreviewRequest,PreviewContext,PreviewEdit,resolve_preview
    d=crossing();chosen,detail=coordinate_routes(d,d.nets,{}, {}, {},label_limit=256)
    proposed,_=materialized_proposal(d,chosen,detail)
    source=proposed.model_copy(deep=True)
    source.features=[f for f in source.features if f.route_net!='T']
    for n in source.nets:n.route_state='committed' if n.id=='P' else 'unresolved'
    original=source.model_copy(deep=True)
    next(f for f in source.features if f.id=='P1').u+=1
    next(n for n in source.nets if n.id=='P').route_state='stale'
    saved_cuts=[f.model_dump_json() for f in source.features if f.route_net=='P']
    real_options=routing.route_options
    def pending_only(design,net,**kwargs):
        assert net.id!='P','A pending neighbour must not authorize re-searching a saved route'
        return real_options(design,net,**kwargs)
    monkeypatch.setattr(routing,'route_options',pending_only)
    target,_,update=resolve_preview(PreviewRequest(design=source,scope='owned',context=PreviewContext(
        scope='owned',source=original,source_revision=store.revision(original),proposal=proposed,
        edit=PreviewEdit(kind='local',feature_ids=['P1']))))
    assert [f.model_dump_json() for f in target.features if f.route_net=='P']==saved_cuts
    assert next(n for n in target.nets if n.id=='P').route_state=='stale'
    assert update['recomputed']==['T'] and update['retained']==['P']
