"""Replay the saved Astra counterexamples; no Generate or AI/provider calls.

Requires the original local review/run evidence. Outputs new artifacts only.
Run with .venv/Scripts/python.exe -B scripts/check-phase-a.py.
"""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from manifold.schema import Design,Feature,CavityDefinition
from manifold import engineering_db as db
from manifold.routing import route_obstructions,terminal_points
from manifold.routing_space import MachiningSpace
from manifold.closure_runtime import bind_route
from manifold.ai_design import coupled_layout as cl
from manifold.ai_design.design_space import LayoutDomain,source_conflicts
from manifold.ai_design.joint_layout import exact_candidate
from test_phase_a_correctness import short_case,cache_case,proxy_case

OLD=ROOT/'output/runtime-checks/root-cause-review-20261013'
RUN=ROOT/'output/runtime-checks/global-ai-20261013/fair-scheduling-generate'
OUT=ROOT/'output/runtime-checks/phase-a-20261013'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(name,value):
    (OUT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def first_beam(d,defs,domain,assessment,groups,threads):
    """Observe real beam output without replacing production decisions."""
    data={};lines,start=inspect.getsourcelines(cl._actions)
    stop=start+next(i for i,line in enumerate(lines) if line.strip()=='beam=kept')
    class Observed(Exception):pass
    def trace(frame,event,arg):
        if frame.f_code is not cl._actions.__code__:return None
        if event=='line' and frame.f_lineno==stop:
            expanded=frame.f_locals['expanded'];kept=frame.f_locals['kept']
            def positions(target):return [dict(id=f.id,face=f.face,u=f.u,v=f.v,rotation=f.rotation) for f in target.features]
            data.update(expanded=len(expanded),
                full_state_keys=len({cl._beam_key(t,p,domain) for _,t,p in expanded}),
                retained=[dict(positions=positions(t),source_conflicts=source_conflicts(t,defs,threads,{})) for t,p in kept],
                distinct_positions=len({tuple((f.face,f.u,f.v,f.rotation) for f in t.features) for t,p in kept}))
            raise Observed
        return trace
    sys.settrace(trace)
    try:next(cl._actions(d,assessment,defs,domain,threads,{},groups))
    except (Observed,StopIteration):pass
    finally:sys.settrace(None)
    assert data and data['expanded']==data['full_state_keys']
    return data


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=read(RUN/'protected-before.json')
    before={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in manifest}
    write('protected-before',before)
    original={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in read(OLD/'input-hashes.json')}
    qa=read(OLD/'beam.json')['qa'];d=Design.model_validate(qa['design'])
    definition=CavityDefinition.model_validate(qa['definition']);defs={definition.id:definition}
    domain=LayoutDomain.new_generation(d,{'A','B'},dimension_axes=(),fixed_faces={'A':'top','B':'top'},
        fixed_rotations={'A':0,'B':0},fixed_positions={'B':dict(u=40,v=60)})
    e1=first_beam(d,defs,domain,dict(unresolved_nets=['N1','N2']),[(['A','B'],{'N1','N2'})],{})
    assert e1['distinct_positions']>1 and all(not r['source_conflicts'] for r in e1['retained'])
    points=terminal_points(d,defs);route=[]
    for net in d.nets:
        pts=[points[m] for m in net.members];net.route_state='proposal'
        route.append(Feature(id='DRILL_'+net.id,kind='drilling',face='left',u=pts[0][1],v=pts[0][2],
            diameter=net.diameter,depth=max(p[0] for p in pts)+net.diameter/2,circuit=net.id,route_net=net.id,plugged=True))
    target=d.model_copy(update=dict(features=[*d.features,*bind_route(d,route)]))
    folder=OUT/'beam-valid-exact';folder.mkdir(exist_ok=True)
    result=exact_candidate(target,defs,{}, {},folder=folder)
    assert result['status']=='EXACT_FEASIBLE',result['failures']
    e1['exact']=dict(status=result['status'],counts=result['validation']['counts'],topology=result['topology'],step=result['step'])
    row=read(RUN/'layout-optimization/layouts/038.json');real=Design.model_validate(row['design'])
    rdefs=db.definitions_for_design(real);threads=db.thread_definitions_for_design(real)
    groups=[g for g in cl.coupling_groups(real,row['assessment']) if all(not any(z.offset_u or z.offset_v for z in rdefs[f.definition].zones)
        for f in real.features if f.id in g[0] and f.definition)]
    e1['real_layout_38']=first_beam(real,rdefs,LayoutDomain.new_generation(real,{f.id for f in real.features}),row['assessment'],groups[:1],threads)
    write('beam-replay',e1);print('E1 complete',flush=True)
    e2=[];d=cache_case()
    for order in ((1,20),(20,1)):
        space=MachiningSpace(d,d.nets[0],{}, {},{});counts=[]
        for x in order:
            count=len(space.operations((x,50,30),(60,50,30),[]));counts.append(count)
            assert count==(1 if x==20 else 0)
        e2.append(dict(order=order,counts=counts,generated=space.generated))
    write('endpoint-replay',e2)
    e4=[]
    for x in (6,10):
        d,defs=short_case(x);options=MachiningSpace(d,d.nets[0],defs,{},{}).operations((1,20,20),(x,20,20),[])
        assert len(options)==1
        folder=OUT/f'short-{x}';folder.mkdir(exist_ok=True)
        result=exact_candidate(d.model_copy(update=dict(features=[*d.features,*options[0]])),defs,{}, {},folder=folder)
        assert result['status']=='EXACT_FEASIBLE',result['failures']
        e4.append(dict(depth=options[0][0].depth,operations=len(options),status=result['status'],
            counts=result['validation']['counts'],topology=result['topology'],step=result['step']))
    write('short-replay',e4);print('E2/E4 complete',flush=True)
    from manifold.routing import _manufacturing_cuts,_cuts_too_close,_plug_cut_overlap
    from manifold.geometry import feature_geometry
    from manifold.closure_runtime import plug_diameter
    d,a,b=proxy_case();cache={}
    rejected=_cuts_too_close(list(_manufacturing_cuts(a,{},{},{})),next(_manufacturing_cuts(b,{},{},{})),d.block,3,cache)
    cuts,*_=feature_geometry(d.model_copy(update=dict(features=[a,b])),{},{},{})
    assert not rejected and cuts[a.id].distance(cuts[b.id])>3
    plug=bind_route(d,[a.model_copy(update=dict(id='PLUG',depth=40,tip_angle=118,plugged=True,route_net='N'))])[0]
    graze=Feature(id='GRAZE',kind='drilling',face='front',u=plug.plug_length/2,v=50+plug_diameter(plug)/2+4-.02,
        diameter=8,depth=60,tip_angle=180,circuit='N')
    geometry=feature_geometry(d.model_copy(update=dict(features=[plug,graze])),{},{},{})
    volume=geometry[4][plug.id].intersect(geometry[0][graze.id]).Volume()
    detected=any(_plug_cut_overlap(plug,c,d.block) for c in _manufacturing_cuts(graze,{},{},{}))
    assert detected and volume>1e-6
    e5=dict(finite_endcap_rejected=rejected,distance_mm=cuts[a.id].distance(cuts[b.id]),
        plug_intersection_detected=detected,plug_overlap_mm3=volume)
    write('proxy-replay',e5)
    # Same saved real offending cuts; no new route/layout search.
    row=read(RUN/'layout-optimization/layouts/045.json');d=Design.model_validate(row['design'])
    defs=db.definitions_for_design(d);threads=db.thread_definitions_for_design(d);records=[]
    for old in read(OLD/'real-geometry.json')['checks']:
        net=next(n for n in d.nets if n.id==old['net']);features=[Feature.model_validate(f) for f in old['features']]
        route=[f for f in features if f.route_net];cache={};started=time.monotonic()
        context=d.model_copy(update=dict(features=list({f.id:f for f in [*d.features,*features]}.values())))
        failures=route_obstructions(context,net,route,threads,defs,{},cache)
        failure=(old['rule'],*sorted(old['ids']));assert failure in failures,(failure,failures)
        records.append(dict(net=net.id,expected=failure,rejected=True,failures=sorted(failures),
            exact_evaluations=cache.get('local_exact_evaluations'),seconds=time.monotonic()-started,
            prior_exact={k:v for k,v in old.items() if k in ('cut_overlap','exact_envelope_distance','protected_overlap','plug_overlaps')}))
    write('real-violation-replay',records);print('Real violations retained',flush=True)
    after={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
    assert before==after==manifest
    assert original=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in original}
    write('protected-after',after)
    write('acceptance',dict(E1=e1,E2=e2,E4=e4,E5=e5,real_violations=records,
        protected_files=len(before),protected_unchanged=True,original_evidence_files=len(original),original_evidence_unchanged=True,
        complex_generate_run=False,phase_b_or_c_implemented=False))


if __name__=='__main__':main()
