import hashlib
import json
import os
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
import uuid
from .cad import cq
from .schema import Design, COLORS
from .geometry import build_geometry, mesh
from .validation import validate
from .routing import resolve_design, authorize_generated_contacts

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'projects' / 'demo.json'
OUTPUT = ROOT / 'output'


def canonical(design):
    return json.dumps(design.model_dump(), sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def revision(design):
    return hashlib.sha256(canonical(design).encode()).hexdigest()


def engine_revision():
    files = ['cad.py','schema.py','kinematics.py','routing.py','geometry.py','validation.py','manufacturing.py','store.py']
    return hashlib.sha256(b''.join((Path(__file__).parent/name).read_bytes() for name in files)).hexdigest()


def read_design(path=PROJECT):
    return Design.model_validate_json(path.read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def project_lock():
    OUTPUT.mkdir(exist_ok=True)
    with (OUTPUT / '.build.lock').open('a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('Another build is running. Retry when it finishes.') from exc
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def build_outputs(design, folder):
    folder.mkdir(parents=True, exist_ok=False)
    authored = design
    design, routes = resolve_design(authored)
    g = build_geometry(design)
    authorize_generated_contacts(design, g)
    report = validate(design, g)
    rev = revision(authored)
    report['route_proposals'] = routes
    report.update(design_revision=rev, generated_at=datetime.now(timezone.utc).isoformat(),
                  cadquery_version=cq.__version__, rules_version='pmc-intent-2', engine_revision=engine_revision())
    cq.exporters.export(g.production, str(folder / 'production.step'))
    # Round trip tests actual serialized CAD, not merely in-memory validity.
    imported = cq.importers.importStep(str(folder / 'production.step')).val()
    error = abs(imported.Volume() - g.production.Volume())
    passed = imported.isValid() and len(imported.Solids()) == 1 and error < 0.01
    report['checks'].append(dict(rule='step_round_trip', items=['block'], actual=round(error, 8), required=0.01,
                                 status='PASS' if passed else 'FAIL', unit='mm³',
                                 message='STEP reimport: valid single solid and matching volume.'))
    report['counts']['PASS' if passed else 'FAIL'] += 1
    if not passed:
        report['status'] = 'FAIL'
    features = {f.id: f for f in design.features}
    parts = [dict(id='block', kind='body', color='#9ba9b9', **mesh(g.production))]
    for key, cut in g.cuts.items():
        f = features[key]
        if f.kind == 'cavity':
            parts.append(dict(id=key, owner=key, kind='cavity', color='#bbc7d4', **mesh(cut)))
    for key, shape in g.nodes.items():
        owner = key.split(':')[0]
        f = features[owner]
        parts.append(dict(id=key, owner=owner, kind='zone' if ':' in key else f.kind,
                          circuit=g.circuits[key], color=next((n.color for n in design.nets if n.id == g.circuits[key] and n.color), COLORS.get(g.circuits[key], '#b08bea')), **mesh(shape)))
    for key, shape in g.plugs.items():
        parts.append(dict(id=key + ':plug', owner=key, kind='plug', color='#d5dee9', **mesh(shape)))
    review = dict(design_revision=rev, block=design.block.model_dump(), parts=parts, placements=g.placements,
                  volume_mm3=round(g.production.Volume(), 3), colors=COLORS)
    atomic_json(folder / 'review.json', review)
    atomic_json(folder / 'design.json', authored.model_dump())
    atomic_json(folder / 'resolved_design.json', design.model_dump())
    from .manufacturing import manufacturing_outputs
    manufacturing_outputs(design, g, folder)
    atomic_json(folder / 'validation.json', report)
    lines = [f"# {design.name}", '', f"Status: {report['status']}", f"Design SHA-256: {rev}", '', report['scope'], '',
             '| Status | Rule | Items | Actual | Required | Unit |', '|---|---|---|---|---|---|']
    for c in report['checks']:
        lines.append('| ' + ' | '.join(str(c.get(k, '')).replace('|', '/') for k in ['status', 'rule', 'items', 'actual', 'required', 'unit']) + ' |')
    lines.extend(['', '## Scope limits', *['- ' + s for s in report['limitations']]])
    (folder / 'validation.md').write_text('\n'.join(lines), encoding='utf-8')
    return report


def current():
    path = OUTPUT / 'current.json'
    return json.loads(path.read_text()) if path.exists() else None


def rebuild(design=None, expected_revision=None):
    with project_lock():
        previous = read_design()
        previous_revision = revision(previous)
        if expected_revision is not None and previous_revision != expected_revision:
            raise ValueError('Design changed on disk. Reload before saving to avoid overwriting Codex edits.')
        target = design or previous
        build_id = uuid.uuid4().hex
        report = build_outputs(target, OUTPUT / 'builds' / build_id)
        # Detect direct edits during an expensive CAD build before committing anything.
        if revision(read_design()) != previous_revision:
            raise ValueError('Design changed during build. Reload and rebuild the latest file.')
        if design is not None:
            atomic_json(PROJECT.parent / '.history' / f'{uuid.uuid4().hex}.json', previous.model_dump())
            atomic_json(PROJECT, target.model_dump())
        pointer = dict(build_id=build_id, design_revision=revision(target), engine_revision=engine_revision(), status=report['status'], counts=report['counts'])
        atomic_json(OUTPUT / 'current.json', pointer)
        return pointer
