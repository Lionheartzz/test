"""Offline NEW AI candidate from reviewed source-only requirements; no AI call.

Never feed committed/manual routes, overwrite a project, or infer permission
from origin.method. --output must name a new directory under output/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manifold.schema import Design
from manifold import store,engineering_db
from manifold.ai_design.layout_search import plan_new
from manifold.engineering import executor


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--layouts',type=int,default=48)
    parser.add_argument('--exact',type=int,default=2)
    args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to(store.OUTPUT.resolve()):raise ValueError('Evidence must stay under output/')
    out.mkdir(parents=True,exist_ok=False)
    protected=[args.source.resolve(),engineering_db.database_path(),*sorted((store.PROJECT.parent/'saved').glob('*.json'))]
    hashes=lambda:{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    before=hashes();source=Design.model_validate_json(args.source.read_text(encoding='utf-8'))
    if any(f.route_net or f.frozen_net or f.kind=='drilling' for f in source.features) or any(
        n.routing_variant or n.route_state!='unresolved' for n in source.nets):
        raise ValueError('Supply reviewed source-only NEW-generation requirements, not a committed/manual project')
    # Explicit fresh ownership and independent identity; the input file and its
    # source machining/Net semantics remain intact. Positions/sizes are seeds.
    ids={f.id:'AI_'+hashlib.sha256(f.id.encode()).hexdigest()[:20] for f in source.features}
    raw=source.model_dump()
    for f in raw['features']:
        f['id']=ids[f['id']]
        f['connects_to']=[ids.get(k.split(':')[0],k.split(':')[0])+(':'+k.split(':',1)[1] if ':' in k else '') for k in f['connects_to']]
        if f.get('parent_id'):f['parent_id']=ids[f['parent_id']]
    for row in raw['schematic_intent']['components']:
        if row.get('placement_id') in ids:row['placement_id']=ids[row['placement_id']]
    for row in raw['review_items']:
        owner,separator,zone=row['subject'].partition(':')
        if owner in ids:row['subject']=ids[owner]+separator+zone
    raw['constraints']['required_feature_faces']={ids.get(k,k):v for k,v in raw['constraints']['required_feature_faces'].items()}
    design=Design.model_validate(raw);store.atomic_json(out/'source-copy.json',design.model_dump())
    started=time.monotonic();last=[0]
    def progress(stage,**detail):
        if time.monotonic()-last[0]<.25 and stage not in ('exact_layout','layout_alternate'):return
        last[0]=time.monotonic();store.atomic_json(out/'progress.json',dict(stage=stage,elapsed_s=time.monotonic()-started,**detail))
    print('START new AI-owned layout/routing candidate from reviewed requirements; original file preserved',flush=True)
    result=plan_new(design,engineering_db.definitions_for_design(design),movable_features=set(ids.values()),
        layout_limit=args.layouts,exact_limit=args.exact,progress=progress,evidence_dir=out,
        initial=lambda d:store.atomic_json(out/'initial-draft.json',d.model_dump()))
    target=Design.model_validate(result['proposals'][0]['design'])
    after=hashes()
    result.update(elapsed_s=time.monotonic()-started,protected_before=before,protected_after=after,
        protected_unchanged=before==after,identity_mapping=ids,original_dimensions=source.block.model_dump(),
        worker_records=executor.history,source_requirements='Reviewed source machining and Net assignments; no new recognition')
    store.atomic_json(out/'result.json',result);store.atomic_json(out/'selected-design.json',target.model_dump())
    print(json.dumps(dict(status=result['status'],elapsed_s=result['elapsed_s'],counters=result['counters'],
        dimensions=target.block.model_dump(),validation=(result.get('validation') or {}).get('counts'),
        protected_unchanged=result['protected_unchanged'])),flush=True)


if __name__=='__main__':main()
