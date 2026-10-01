from .timing import timed,phase,progress
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
from .engine import engine_revision, engine_current, engine_evidence, assert_engine_current

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'projects' / 'demo.json'
OUTPUT = ROOT / 'output'


def canonical(design):
    return json.dumps(design.model_dump(), sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def revision(design):
    return hashlib.sha256(canonical(design).encode()).hexdigest()


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


@timed('build')
def build_outputs(design, folder, *, engineering_complete=None):
    assert_engine_current()
    folder.mkdir(parents=True, exist_ok=False)
    authored = design
    progress('preparing',5)
    design, routes, g, report = resolve_design(authored,persist=True,prepared=True,step_path=folder/'production.step')
    rev = revision(authored)
    report['route_proposals'] = routes
    report.update(design_revision=rev, generated_at=datetime.now(timezone.utc).isoformat(),
                  cadquery_version=cq.__version__, rules_version='pmc-intent-2', engine_revision=engine_revision(), engine=engine_evidence())
    progress('finalizing',95)
    with phase('step.export'):
        from .presentation import feature_name
        import re
        assembly=cq.Assembly(name='PMC_ENGINEERING')
        assembly.add(g.production,name='MANIFOLD_FINISHED')
        used={'MANIFOLD_FINISHED'}
        for feature in design.features:
            if feature.suppressed or feature.id not in g.cuts:continue
            base=re.sub(r'[^A-Za-z0-9_.-]+','_',feature_name(design,feature)).strip('_') or 'MACHINING'
            name=base;index=2
            while name in used:name=f'{base}_{index}';index+=1
            used.add(name);assembly.add(g.cuts[feature.id],name=name)
            if feature.id in g.plugs:assembly.add(g.plugs[feature.id],name=name+'_PLUG')
        for identifier,shape in g.manufacturing_features.items():
            assembly.add(shape,name='MANUFACTURING_'+identifier)
        assembly.save(str(folder/'engineering.step'),exportType='STEP',mode='default')
    # The selected production.step was checked by the authoritative resolver's
    # serialization gate. Build uses that exact route and serialized artifact.
    atomic_json(folder / 'design.json', authored.model_dump())
    atomic_json(folder / 'resolved_design.json', design.model_dump())
    from .manufacturing import manufacturing_outputs
    manufacturing_outputs(design, g, folder)
    assert_engine_current()
    atomic_json(folder / 'validation.json', report)
    lines = [f"# {design.name}", '', f"Status: {report['status']}", f"Design SHA-256: {rev}", '', report['scope'], '',
             '| Status | Rule | Items | Actual | Required | Unit |', '|---|---|---|---|---|---|']
    from .presentation import identity_name,rule_name
    for c in report['checks']:
        human={**c,'rule':rule_name(c.get('rule')),'items':' ↔ '.join(identity_name(design,item) for item in c.get('items',[]))}
        lines.append('| ' + ' | '.join(str(human.get(k, '')).replace('|', '/') for k in ['status', 'rule', 'items', 'actual', 'required', 'unit']) + ' |')
    lines.extend(['', '## Scope limits', *['- ' + s for s in report['limitations']]])
    (folder / 'validation.md').write_text('\n'.join(lines), encoding='utf-8')
    # All engineering evidence is complete before optional display work. A mesh
    # failure must not erase actual validation/STEP results or imply a CAD FAIL.
    unavailable=dict(geometry_kind='unavailable',review_error='Review generation did not complete. Exact validation and STEP evidence are available.',
                     design_revision=rev,engine_revision=engine_revision())
    atomic_json(folder / 'review.json', unavailable)
    if engineering_complete:engineering_complete(report)
    progress('finalizing',97)
    from .geometry import review_model
    try:
        review=review_model(design,g)
        review.update(design_revision=rev,engine_revision=engine_revision())
        atomic_json(folder / 'review.json',review)
    except Exception as exc:
        unavailable['review_error']='Review unavailable: '+(str(exc) or type(exc).__name__)[:2000]
        atomic_json(folder / 'review.json',unavailable)
    assert_engine_current()
    progress('finalizing',98)
    return report


def current():
    path = OUTPUT / 'current.json'
    return json.loads(path.read_text()) if path.exists() else None


def prepare_rebuild(design=None,expected_revision=None):
    with project_lock():
        previous=read_design();previous_revision=revision(previous)
        if expected_revision is not None and previous_revision!=expected_revision:
            raise ValueError('Design changed on disk. Reload before saving to avoid overwriting Codex edits.')
        return dict(previous=previous,revision=previous_revision,target=design or previous,save=design is not None,build_id=uuid.uuid4().hex)


def finish_rebuild(plan,report):
    with project_lock():
        assert_engine_current()
        if revision(read_design())!=plan['revision']:
            raise ValueError('Design changed during build. Reload and rebuild the latest file.')
        if plan['save']:
            atomic_json(PROJECT.parent/'.history'/(uuid.uuid4().hex+'.json'),plan['previous'].model_dump())
            atomic_json(PROJECT,plan['target'].model_dump())
        pointer=dict(build_id=plan['build_id'],design_revision=revision(plan['target']),engine_revision=engine_revision(),status=report['status'],counts=report['counts'])
        atomic_json(OUTPUT/'current.json',pointer)
        return pointer


def rebuild(design=None,expected_revision=None):
    plan=prepare_rebuild(design,expected_revision)
    report=build_outputs(plan['target'],OUTPUT/'builds'/plan['build_id'])
    return finish_rebuild(plan,report)
