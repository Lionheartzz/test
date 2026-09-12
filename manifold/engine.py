"""Process-start engineering identity. Disk edits never relabel already-imported code."""
from copy import deepcopy
import hashlib
from importlib.metadata import version, PackageNotFoundError
from importlib.machinery import SourceFileLoader
import json
import marshal
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).parent
DEPENDENCIES = ('cadquery', 'cadquery-ocp', 'casadi', 'nlopt', 'numpy', 'pydantic')


def source_manifest():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.glob('*.py'))}


def dependency_manifest():
    result = {}
    for name in DEPENDENCIES:
        try: result[name] = version(name)
        except PackageNotFoundError: result[name] = 'unavailable'
    return result


def code_manifest():
    # Capture what the Python loader will execute, including valid bytecode caches.
    # Together with immutable startup sources this detects a different executable
    # even when someone retained an old cache with matching source size/mtime.
    return {p.name: hashlib.sha256(marshal.dumps(SourceFileLoader(
        'manifold' if p.stem=='__init__' else 'manifold.'+p.stem,str(p)).get_code(
        'manifold' if p.stem=='__init__' else 'manifold.'+p.stem))).hexdigest()
        for p in sorted(ROOT.glob('*.py'))}


_LOADED = dict(format=1, sources=source_manifest(), executable_code=code_manifest(), dependencies=dependency_manifest(),
               python=sys.version, implementation=platform.python_implementation(),
               system=platform.system(), machine=platform.machine())
_REVISION = hashlib.sha256(json.dumps(_LOADED, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def engine_revision():
    return _REVISION


def engine_current():
    try:
        return source_manifest() == _LOADED['sources'] and dependency_manifest() == _LOADED['dependencies']
    except OSError:
        return False


def assert_engine_current():
    if not engine_current():
        raise RuntimeError('Engineering source or CAD dependencies changed after this process started. Restart the local server before producing new engineering evidence.')


def engine_evidence():
    return dict(revision=_REVISION, **deepcopy(_LOADED))
