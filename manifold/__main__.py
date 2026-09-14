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
    parser.add_argument('--project-id',help='Saved local project ID from Projects')
    parser.add_argument('--lan',action='store_true',help='Serve on LAN interfaces (default: this computer only)')
    args = parser.parse_args()
    if args.project_id and (args.project or args.out or args.command not in {'build','validate'}):
        parser.error('--project-id is for build/validate and cannot be combined with --project or --out')
    if args.command == 'init':
        if not PROJECT.exists():
            atomic_json(PROJECT, demo().model_dump())
        print(PROJECT)
    elif args.command == 'build':
        if args.project_id:
            from .projects import read,snapshot,build
            saved=snapshot(read(args.project_id))
            report=build(args.project_id,saved['revision'])['build']
            print(json.dumps(report))
        elif args.project:
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
        from .routing import resolve_design,authorize_generated_contacts
        if args.project_id:
            from .projects import read
            from .schema import Design
            design=Design.model_validate(read(args.project_id)['design'])
        else:design = read_design(args.project or PROJECT)
        design,_=resolve_design(design)
        geometry=build_geometry(design)
        authorize_generated_contacts(design,geometry)
        report = validate(design, geometry)
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
        uvicorn.run('manifold.server:app', host='0.0.0.0' if args.lan else '127.0.0.1', port=8765, workers=1,proxy_headers=False,timeout_graceful_shutdown=3)


if __name__ == '__main__':
    main()
