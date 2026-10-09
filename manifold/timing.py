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
_progress={}
_diagnostics={}


def configure(path):
    global _path,_started,_counts,_stack,_last_write,_write_errors,_progress,_diagnostics
    _path=Path(path);_started=time.monotonic();_counts={};_stack=[];_last_write=0;_write_errors=0
    _progress={}
    _diagnostics={}
    publish(force=True)


def summary():
    return dict(elapsed_s=round(time.monotonic()-_started,4),phase=' / '.join(_stack) or 'completed',
                diagnostic_write_errors=_write_errors,operations={k:dict(count=v[0],seconds=round(v[1],6)) for k,v in sorted(_counts.items())},
                progress={**_progress,'events':list(_progress.get('events',[]))},diagnostics=dict(_diagnostics))


def diagnostic(name,value):
    """Small bounded engineering outcomes in the SAME request-owned trace.

    Callers supply IDs/counts, never complete designs, source input or secrets.
    This does not force writes or instrument additional Boolean operations.
    """
    _diagnostics[name]=(_diagnostics.get(name,[])+[value])[-8:]
    publish()


def progress(stage, percent, *, candidate=None, candidate_limit=None):
    """Coarse actual milestones in the existing trace; never a wall-time percent.

    Reserve completion for the API's authoritative commit. Retries retain the
    high-water mark; these few events do not instrument individual Booleans.
    """
    global _progress
    previous=_progress.get('percent',0)
    value=min(99,max(previous,float(percent)))
    if _progress and stage!=_progress.get('stage') and value==previous:
        value=min(99,value+.25)
    events=_progress.get('events',[])
    if candidate is not None:_progress['candidate']=candidate
    if candidate_limit is not None:_progress['candidate_limit']=candidate_limit
    event=dict(stage=stage,percent=value,elapsed_s=round(time.monotonic()-_started,3),
               candidate=_progress.get('candidate'))
    _progress.update(stage=stage,percent=value,events=(events+[event])[-32:])
    publish()  # Same 150 ms publisher; no extra per-Boolean writes.


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


def record(name,seconds):
    """Record bounded timing measured before this request trace was configured."""
    value=_counts.setdefault(name,[0,0.0]);value[0]+=1;value[1]+=max(0.0,float(seconds))
    publish()


@contextmanager
def phase(name, *, immediate=False):
    start=time.monotonic();_stack.append(name);publish(force=immediate)
    try:yield
    finally:
        value=_counts.setdefault(name,[0,0.0]);value[0]+=1;value[1]+=time.monotonic()-start
        _stack.pop();publish()


def timed(name, *, immediate=False):
    def decorate(fn):
        @wraps(fn)
        def call(*args,**kwargs):
            with phase(name,immediate=immediate):return fn(*args,**kwargs)
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
                # Keep bounded OCCT diagnostics without forcing a Windows file
                # replacement before every primitive call. publish() still
                # emits progress at most every 150 ms. Cancellation remains
                # owned by the executor, independently of trace-file writes.
                wrapped=timed('boolean.'+method)(fn);wrapped._pmc_timed=True;setattr(cls,method,wrapped)
