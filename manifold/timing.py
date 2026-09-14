"""Bounded phase diagnostics: identifiers, counts and durations, never draft contents."""
from contextlib import contextmanager
from functools import wraps
import json
from pathlib import Path
import time

_path=None
_started=time.monotonic()
_counts={}
_stack=[]
_last_write=0
_write_errors=0


def configure(path):
    global _path,_started,_counts,_stack,_last_write,_write_errors
    _path=Path(path);_started=time.monotonic();_counts={};_stack=[];_last_write=0;_write_errors=0
    publish(force=True)


def summary():
    return dict(elapsed_s=round(time.monotonic()-_started,4),phase=' / '.join(_stack) or 'completed',
                diagnostic_write_errors=_write_errors,operations={k:dict(count=v[0],seconds=round(v[1],6)) for k,v in sorted(_counts.items())})


def publish(force=False):
    global _last_write,_write_errors
    now=time.monotonic()
    if _path and (force or now-_last_write>.15):
        _last_write=now
        try:
            temp=_path.with_suffix('.tmp');temp.write_text(json.dumps(summary()),encoding='utf-8');temp.replace(_path)
        except OSError:
            # Windows can briefly deny replacement while a status reader holds
            # the old file. Diagnostics must never abort an engineering check.
            _write_errors+=1


@contextmanager
def phase(name):
    start=time.monotonic();_stack.append(name);publish()
    try:yield
    finally:
        value=_counts.setdefault(name,[0,0.0]);value[0]+=1;value[1]+=time.monotonic()-start
        _stack.pop();publish()


def timed(name):
    def decorate(fn):
        @wraps(fn)
        def call(*args,**kwargs):
            with phase(name):return fn(*args,**kwargs)
        return call
    return decorate


def trace_occt():
    from .cad import cq
    # Instrument the methods actually defined on each class, without double-wrapping
    # inherited methods. No geometric tolerance or operation changes.
    for cls in (cq.Shape,cq.Compound):
        for method in ('cut','fuse','intersect','distance','clean'):
            fn=cls.__dict__.get(method)
            if fn and not getattr(fn,'_pmc_timed',False):
                wrapped=timed('boolean.'+method)(fn);wrapped._pmc_timed=True;setattr(cls,method,wrapped)
