"""Bounded saved-source facts, physical precheck and ONE local repair. No Generate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manifold import store
from manifold.ai_design.execution import supervise


def main():
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=('facts','precheck','source','plug'))
    args=parser.parse_args();old=ROOT/'output/runtime-checks/engineering-planner-20261014'
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    folder=ROOT/'output/runtime-checks/single-work-20261014'/args.case
    folder.mkdir(parents=True,exist_ok=True)
    code_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [*sorted((ROOT/'manifold/ai_design').glob('*.py')),ROOT/'manifold/routing.py',ROOT/'manifold/cavity_access.py',
         ROOT/'manifold/geometry.py',ROOT/'manifold/validation.py',ROOT/'manifold/engineering_conditions.py']}
    if args.case in ('source','plug'):
        p=next((old/('bounded-source-recheck' if args.case=='source' else 'bounded-plug-recheck')).rglob('request.json'))
        original=read(p)['payload']
        payload=dict(operation='single-work-snapshot',mode='repair',design=original['design'],routes={original['net']:original['features']})
    else:
        p=next((old/'complex-frozen-final').rglob('authored-draft.json'))
        payload=dict(operation='single-work-snapshot',mode=args.case,design=read(p))
    # Private output/store; never touch any source project or Library.
    store.OUTPUT=folder/'output';store.PROJECT=folder/'projects/demo.json'
    out=supervise(payload,limits=dict(total=25,layout=20,deep=2))
    out['source']=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    out['code_hashes']=code_hashes
    store.atomic_json(folder/'result.json',out)
    e=(out.get('result') or {}).get('evidence') or (out.get('checkpoint') or {}).get('evidence') or {}
    print(json.dumps(dict(case=args.case,reason=out['execution']['reason'],status=(out.get('result') or {}).get('status'),
        seconds=out['execution'].get('elapsed_s'),source_ready=e.get('source_layout_ready'),
        failures=e.get('failures'),catalog_searches=e.get('catalog_searches'),labels=e.get('deep_labels'))))
    if out['execution']['reason']=='WORKER_ERROR':raise RuntimeError(out['execution'].get('worker_failure'))


if __name__=='__main__':main()
