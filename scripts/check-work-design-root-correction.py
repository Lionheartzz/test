"""Focused saved snapshots only. Never invokes Generate or an AI provider."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from manifold import store
from manifold.ai_design.execution import supervise


def main():
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=('facts','precheck','repair','source','plug'))
    args=parser.parse_args();old=ROOT/'output/runtime-checks/engineering-planner-20261014'
    folder=ROOT/'output/runtime-checks/single-work-root-correction-20261014'/args.case;folder.mkdir(parents=True,exist_ok=True)
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    if args.case in ('source','plug'):
        path=next((old/('bounded-source-recheck' if args.case=='source' else 'bounded-plug-recheck')).rglob('request.json'))
        original=read(path)['payload']
        payload=dict(operation='single-work-snapshot',mode='repair',design=original['design'],routes={original['net']:original['features']})
    else:
        path=next((old/'complex-frozen-final').rglob('authored-draft.json'))
        payload=dict(operation='single-work-snapshot',mode=args.case,design=read(path))
    protected=read(old/'protected-reference.json')
    actual={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in protected}
    assert actual==protected,'Protected engineering input changed'
    store.OUTPUT=folder/'output';store.PROJECT=folder/'projects/demo.json'
    out=supervise(payload,limits=dict(total=25,layout=20,deep=2))
    out['source']=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    out['protected_before']=actual
    out['protected_after']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in protected}
    assert out['protected_after']==actual
    out['code_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [*sorted((ROOT/'manifold/ai_design').glob('*.py')),ROOT/'manifold/flow.py',ROOT/'manifold/routing.py']}
    store.atomic_json(folder/'result.json',out)
    evidence=(out.get('result') or {}).get('evidence') or (out.get('checkpoint') or {}).get('evidence') or {}
    print(json.dumps(dict(case=args.case,execution=out['execution'],status=(out.get('result') or {}).get('status'),
        source_ready=evidence.get('source_layout_ready'),process_gap=evidence.get('process_gap'),
        dimensions=evidence.get('initial_calculation',{}).get('dimensions'),failures=evidence.get('failures'))))
    assert out['execution']['reason']=='COMPLETED',out['execution']


if __name__=='__main__':main()
