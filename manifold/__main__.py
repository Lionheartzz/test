import argparse
import json
from pathlib import Path
from .store import PROJECT, OUTPUT, atomic_json, read_design, build_outputs, rebuild
from .demo import demo, invalid_demo


def main():
    parser = argparse.ArgumentParser(description='PMC local manifold CAD')
    parser.add_argument('command', choices=['init', 'build', 'validate', 'prove', 'serve'])
    parser.add_argument('--project', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--lan',action='store_true',help='Serve on LAN interfaces (default: this computer only)')
    args = parser.parse_args()
    if args.command == 'init':
        if not PROJECT.exists():
            atomic_json(PROJECT, demo().model_dump())
        print(PROJECT)
    elif args.command == 'build':
        if args.project:
            if not args.out:
                parser.error('--project requires a new --out directory')
            report = build_outputs(read_design(args.project), args.out)
            print(json.dumps(dict(status=report['status'], counts=report['counts'], output=str(args.out))))
        else:
            report = rebuild()
            print(json.dumps(report))
        raise SystemExit(1 if report['status'] == 'FAIL' else 0)
    elif args.command == 'validate':
        from .geometry import build_geometry
        from .validation import validate
        design = read_design(args.project or PROJECT)
        report = validate(design, build_geometry(design))
        print(json.dumps(report, indent=2))
        raise SystemExit(1 if report['status'] == 'FAIL' else 0)
    elif args.command == 'prove':
        from datetime import datetime
        folder = args.out or OUTPUT / 'proof' / datetime.now().strftime('%Y%m%d-%H%M%S')
        bad = build_outputs(invalid_demo(), folder / 'invalid')
        good = build_outputs(demo(), folder / 'corrected')
        assert bad['status'] == 'FAIL' and any(c['rule'] == 'circuit_intersection' and c['status'] == 'FAIL' for c in bad['checks'])
        assert good['status'] == 'PASS', good['counts']
        print(json.dumps(dict(invalid=bad['counts'], corrected=good['counts'], output=str(folder))))
    else:
        import uvicorn
        import os
        os.environ['PMC_LAN']='1' if args.lan else '0'
        from .network import endpoints
        print(json.dumps(endpoints()),flush=True)
        uvicorn.run('manifold.server:app', host='0.0.0.0' if args.lan else '127.0.0.1', port=8765, workers=1,proxy_headers=False)


if __name__ == '__main__':
    main()
