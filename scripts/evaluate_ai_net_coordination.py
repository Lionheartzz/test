"""Replay one saved AI-only source layout and its real compatible route core.

No recognition, layout generation or saved-project mutation. Exact/STEP runs
only if the complete analytic assignment is compatible under shared screens.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manifold import engineering_db as db,store
from manifold.schema import Design,Feature
from manifold.ai_design.route_catalog import Session
from manifold.ai_design.layout_search import screen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--labels',type=int,default=2048)
    parser.add_argument('--assessment',type=Path)
    parser.add_argument('--pools',type=Path)
    parser.add_argument('--core',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to(store.OUTPUT.resolve()):raise ValueError('Output must remain in output/')
    out.mkdir(parents=True,exist_ok=False)
    protected=[args.layout.resolve(),db.database_path(),*sorted((store.PROJECT.parent/'saved').glob('*.json'))]
    protected.extend(p.resolve() for p in (args.assessment,args.pools,args.core) if p)
    hashes=lambda:{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    before=hashes();row=json.loads(args.layout.read_text(encoding='utf-8'));design=Design.model_validate(row['design'])
    if any(f.route_net or f.kind=='drilling' or f.frozen_net for f in design.features):raise ValueError('Reviewed source-only AI candidate required')
    defs=db.definitions_for_design(design);threads=db.thread_definitions_for_design(design);modifiers={}
    assessment=row['assessment']
    if args.assessment:
        final=json.loads(args.assessment.read_text(encoding='utf-8'))
        evaluation=next(x for x in final['evaluations'] if x['index']==row['index'])
        if evaluation['geometry_changes']!=row['geometry_changes']:raise ValueError('Final assessment does not match this source layout')
        assessment=evaluation['assessment']
    if args.core:
        core_source=Design.model_validate_json((args.core.parent/'source.json').read_text(encoding='utf-8'))
        if core_source.model_dump()!=design.model_dump():raise ValueError('Compatible core belongs to different source geometry')
        assessment=json.loads(args.core.read_text(encoding='utf-8'))
    session=Session();seed={}
    for raw in assessment['partial_routing']['features']:
        f=Feature.model_validate(raw);seed.setdefault(f.route_net,dict(key='saved-core:'+f.route_net,route=[],risk=0,connection_verified=False))['route'].append(f)
    session.seed_combination(design,seed);started=time.monotonic()
    def progress(stage,**details):store.atomic_json(out/'progress.json',dict(stage=stage,elapsed_s=time.monotonic()-started,**details))
    print('START fixed source layout; restoring analytic compatible core',len(seed),flush=True)
    from manifold.engineering_conditions import effective_net
    nets={n.id:effective_net(design,n) for n in design.nets if n.routing=='automatic' and
          n.route_state in ('unresolved','proposal') and len(n.members)>=2}
    tools=db.tool_definitions('drill')
    if args.pools:
        from manifold.ai_design.route_catalog import Catalog
        pool_source=Design.model_validate_json((args.pools.parent/'source.json').read_text(encoding='utf-8'))
        if pool_source.model_dump()!=design.model_dump():raise ValueError('Candidate pool belongs to different source geometry')
        session.context=session.source_context(design,defs,threads,modifiers);session.remaining=8*len(nets)
        loaded=json.loads(args.pools.read_text(encoding='utf-8'))
        for name,net in nets.items():
            catalog=Catalog(design,net,defs,threads,modifiers,tools,session.cache)
            for option in loaded[name]:catalog.accept(option['key'],[Feature.model_validate(f) for f in option['features']],'replayed')
            session.catalogs[name]=catalog
        # Explicit saved core cuts also need admission against the current source.
        for name,option in seed.items():session.catalogs[name].accept(option['key'],option['route'],'saved-core')
    else:session.prepare(design,nets,defs,threads,modifiers,tools,progress)
    store.atomic_json(out/'prepared-pools.json',{n:[dict(key=o['key'],features=[f.model_dump() for f in o['route']]) for o in c.clear] for n,c in session.catalogs.items()})
    session._prepared_once=True
    store.atomic_json(out/'source.json',design.model_dump())
    try:
        result=screen(design,defs,threads,modifiers,db.tool_definitions('drill'),{},0,progress,
            include_routes=True,general_families=True,corridor_labels=args.labels,route_session=session)
    finally:
        store.atomic_json(out/'candidate-pools.json',{n:[dict(key=o['key'],features=[f.model_dump() for f in o['route']])
            for o in c.clear] for n,c in session.catalogs.items()})
    store.atomic_json(out/'assessment.json',result)
    exact=None
    if result['compatible']:
        target=design.model_copy(deep=True);target.features.extend(Feature.model_validate(f) for f in result['route_features'])
        for net in target.nets:
            if net.routing=='automatic':net.route_state='proposal';net.routing_variant=None
        from manifold.ai_design.joint_layout import run_exact
        folder=out/'exact';folder.mkdir()
        exact=run_exact(target,defs,threads,modifiers,folder=folder,progress=lambda d:progress('exact',detail=d))
    after=hashes();assert before==after
    receipt=dict(before_compatible=len(seed),after_compatible=result['joint_coordination']['best_compatible'],
        complete=result['compatible'],exact_status=(exact or {}).get('status'),validation=(exact or {}).get('validation'),
        elapsed_s=time.monotonic()-started,source_unchanged=True,protected_before=before,protected_after=after,
        coordination=result['joint_coordination'],combination=result['combination'])
    store.atomic_json(out/'result.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k in ('before_compatible','after_compatible','complete','exact_status','elapsed_s','source_unchanged')}),flush=True)


if __name__=='__main__':main()
