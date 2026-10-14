"""Operation-owned joint geometry state and conditional machining constraints.

Only a new AI Generate creates this owner. A state is a complete source
geometry revision, not an origin flag or a persisted candidate identifier.
Analytic facts guide search; they never grant production approval.
"""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json

from ..routing_continuation import dependency_key
from .route_catalog import geometry_key


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def assignment_key(core):
    return tuple(sorted((n, (geometry_key(o['route']),tuple(sorted(f.id for f in o['route'])))) for n, o in core.items()))


@dataclass
class GeometryState:
    dependency: str
    source: object
    nets: dict
    catalogs: dict
    domain: dict
    constraints: dict = field(default_factory=dict)
    cores: dict = field(default_factory=dict)
    transactions: dict = field(default_factory=dict)
    source_obstacles: list = field(default_factory=list)
    admission: dict = field(default_factory=dict)
    assessment: dict = field(default_factory=dict)
    violations: set = field(default_factory=set)

    def permits(self, core):
        chosen = dict(assignment_key(core))
        import itertools
        return all(tuple(sorted(pair)) not in self.violations for pair in itertools.combinations(chosen.items(),2))

    def retain(self, core):
        # Coverage and drilling cost do NOT establish geometric dominance.
        # Only identical complete arrangements are coalesced.
        if self.permits(core):
            self.cores.setdefault(assignment_key(core), dict(core))

    def pair_fact(self, a, ao, b, bo, failures=None):
        arrangements = assignment_key({a: ao, b: bo})
        key = _digest(arrangements)
        if failures is None:
            return self.constraints.get(key)
        if any(f[0] == 'search_budget' for f in failures):
            return None  # Unexplored is not a geometric prohibition.
        fact = dict(dependency=self.dependency, arrangements=arrangements,
                    nets=sorted((a, b)), state='PROVEN_VIOLATION' if failures else 'PROVEN_SAFE',
                    basis='SHARED_MACHINING_PREDICATES', failures=sorted(failures),
                    features=[f.model_dump(mode='json') for o in (ao, bo) for f in o['route']],
                    source_dependencies=sorted({m.split(':')[0] for n in (a, b) for m in self.nets[n].members}),
                    full_exact_accepted=False)
        self.constraints[key] = fact
        if failures:self.violations.add(arrangements)
        else:self.violations.discard(arrangements)
        return fact

    def diagnostics(self, search_context):
        searches = [dict(dependency=k, labels=s.budget['used'],
                         pending=s.event is not None, candidate_count=len(s.candidates),
                         admission=s.evidence)
                    for k, s in search_context.searches.items()
                    if s.space.design.model_dump_json() == self.source.model_dump_json()]
        constraints=[{**{k:v for k,v in c.items() if k not in ('arrangements','features')},
                      'arrangements':[(n,_digest(g)) for n,g in c['arrangements']],
                      'feature_ids':[f['id'] for f in c['features']],
                      'features':[f for f in c['features'] if f['id'] in {v for r in c['failures'] for v in r[1:]}]}
                     for c in self.constraints.values()]
        return dict(dependency=self.dependency, ownership='NEW_AI_GENERATE_ONLY',
                    source=self.source.model_dump(mode='json'), domain=self.domain,
                    net_demands={n:dict(members=list(net.members), requirements=net.model_dump(mode='json'))
                                 for n, net in self.nets.items()},
                    conditional_constraints=constraints,
                    source_obstacle_count=len(self.source_obstacles), local_admission=self.admission,
                    full_exact_status=self.assessment.get('full_exact_status','NOT_EVALUATED'),
                    full_exact_failures=self.assessment.get('exact_failures',[]),
                    full_exact_outcome=self.assessment.get('full_exact_outcome'),
                    cores=[dict(nets=sorted(c), arrangements={n:_digest(geometry_key(o['route'])) for n,o in c.items()})
                           for c in self.cores.values()],
                    repair_transactions=[t.diagnostics() for t in self.transactions.values()],
                    continuation=searches, physical_infeasibility_proven=False)


class JointSolver:
    def __init__(self, session):
        self.session = session
        self.states = {}
        self.current = None
        self.domain = {}

    def bind(self, source, nets, catalogs):
        if not nets:
            self.current = None
            return
        name = next(iter(nets)); c = catalogs[name]
        key = _digest((dependency_key(source, nets[name], c.definitions, c.threads, c.modifiers, [], c.tools), self.domain))
        if key not in self.states:
            self.states[key] = GeometryState(key, source.model_copy(deep=True), nets, catalogs, deepcopy(self.domain))
        self.current = self.states[key]
        self.current.catalogs = catalogs

    def permits(self, core):
        return self.current is None or self.current.permits(core)

    def update(self, assessment, *, state=None):
        state = state if state is not None else self.current
        if state is None:
            return
        state.assessment = assessment
        state.source_obstacles = assessment.get('spatial_feedback', [])
        state.admission = deepcopy(assessment.get('partial_routing',{}).get('local_admission',
            self.session.local_records if state is self.current else state.admission))
        assessment['joint_solver'] = state.diagnostics(self.session.search_context)


class RepairTransaction:
    """Persistent conditional connection-tree search over several released Nets.

    A child plans against the actual NEW complete cuts selected by its parent
    and every outside Net. All attachment orders remain queued. Neither partial
    branches nor unfinished shared 3D searches disappear at a batch boundary.
    """
    def __init__(self, state, group, outside):
        self.state = state; self.group = frozenset(group); self.outside = dict(outside)
        self.queue = deque(); self.visited = set(); self.completed = {}; self.events = []
        self.uncertain = []
        self.labels = 0; self.calls = 0; self.new_candidates = 0; self.delivered = set()
        self.probes = 0
        self.enqueue({}, ())

    def enqueue(self, chosen, generated):
        token = assignment_key(chosen)
        if token in self.visited:
            return
        self.visited.add(token)
        remaining = self.group - chosen.keys()
        if not remaining:
            self.completed[token] = {**self.outside, **chosen}
            self.events.append(dict(action='JOINT_REPLACEMENT_READY', released=sorted(self.group),
                regenerated=list(generated), selected={n:o['key'] for n,o in chosen.items()},
                status='ANALYTIC_CLEAR_REQUIRES_EXACT'))
            return
        for name in sorted(remaining, key=lambda n:(-len(self.state.nets[n].members), n)):
            self.queue.append(dict(chosen=dict(chosen), generated=generated, net=name, pending=deque(),
                                   search_key=None, search_done=False, fragments=None, fragments_done=False))

    def take_completed(self):
        fresh=[core for key,core in self.completed.items() if key not in self.delivered]
        self.delivered.update(self.completed)
        return fresh

    @staticmethod
    def buffered(job, session):
        search=session.search_context.searches.get(job['search_key'])
        return search is not None and bool(search.candidates.keys()-search.delivered-search.forbidden)

    def priority(self):
        # Finish an already conditioned branch before opening another cold
        # release group. Queue rotation still visits all equal-depth jobs.
        depth=max((len(j['chosen']) for j in self.queue),default=-1)
        return (-depth, -sum(bool(j['pending']) for j in self.queue), self.calls)

    def advance(self, session, pair, *, labels, samples, states, probes=0, progress=None):
        from ..drilling_planner import plan_net
        from .joint_routes import corridor_alternatives
        self.queue=deque(j for j in self.queue if not (j['search_done'] and j['fragments_done'])
                         or j['pending'] or self.buffered(j,session))
        spent = dict(labels=0, samples=0, states=0, probes=0); searches = []
        # Deeper conditional arrangements get a turn before another root batch.
        # Within the same depth, deque rotation preserves every unfinished job.
        while self.queue and spent['states'] < states:
            runnable=[(i,j) for i,j in enumerate(self.queue) if j['pending'] or
                spent['samples']<samples and (self.buffered(j,session) or
                    labels>spent['labels'] and not j['search_done'] or
                    probes>spent['probes'] and not j['fragments_done'])]
            if not runnable:break
            index,job=min(runnable,key=lambda r:(-len(r[1]['chosen']),not bool(r[1]['pending']),r[0]))
            self.queue.rotate(-index); job = self.queue.popleft(); self.queue.rotate(index)
            name = job['net']; chosen = job['chosen']; catalog = self.state.catalogs[name]
            retained = {**self.outside, **chosen}
            reserved = [f for o in retained.values() for f in o['route']]
            allowance = min(32, max(0,labels-spent['labels']))
            deferred=bool(job['pending'])
            if job['pending']:
                options=[job['pending'].popleft()]
                detail=dict(labels=0,classification='DEFERRED_PAIR_SCREEN')
            elif self.buffered(job,session) or allowance and not job['search_done']:
                options, detail = plan_net(self.state.source, self.state.nets[name], catalog.definitions,
                    catalog.threads, catalog.modifiers, reserved=reserved, label_limit=allowance,
                    alternatives=min(2, samples-spent['samples']), cache=session.cache, tools=catalog.tools,
                    ai_context=session.search_context)
                job['search_key']=detail['search_context'];job['search_done']=not detail.get('resumable')
            else:
                # Reuse the existing manufacturing-alternative generator with
                # the SAME newly chosen reservations. Unused probe resources
                # can advance a conditional branch after labels are exhausted.
                if job['fragments'] is None:
                    job['fragments']=iter(corridor_alternatives(self.state.source,self.state.nets[name],
                        tuple(catalog.clear),reserved,catalog.definitions,catalog.threads,catalog.modifiers,catalog.tools,
                        session.cache,excluded=catalog.seen,allow_bypass=True))
                try:
                    option=next(job['fragments']);spent['probes']+=1;self.probes+=1
                    options=[] if 'checkpoint' in option else [option]
                    detail=dict(labels=0,classification=option.get('checkpoint','CONDITIONAL_FRAGMENT'))
                except StopIteration:
                    job['fragments_done']=True;options=[]
                    detail=dict(labels=0,classification='CONDITIONAL_FRAGMENTS_EXHAUSTED')
            self.calls += 1; self.labels += detail.get('labels', 0)
            spent['labels'] += detail.get('labels', 0); spent['states'] += 1
            searches.append({**detail, 'released':sorted(self.group), 'reserved_nets':sorted(retained),
                             'conditional_parent':{n:o['key'] for n,o in chosen.items()}})
            self.queue.append(job)
            if not deferred:
                spent['samples']+=len(options);self.new_candidates+=len(options)
            if progress:progress('joint_repair',released=sorted(self.group),conditional_depth=len(chosen),
                                 labels=spent['labels'],probes=spent['probes'],states=spent['states'])
            for oi,option in enumerate(options):
                catalog.accept(option['key'], option['route'], 'joint-transaction-3d')
                candidate = next((o for o in catalog.clear if geometry_key(o['route']) == geometry_key(option['route'])), None)
                if candidate is None:
                    continue
                trial = {**retained, name:candidate}
                if len(self.state.source.features)+sum(len(o['route']) for o in trial.values()) > 120:
                    continue
                failures = {n:sorted(pair(name,candidate,n,o)) for n,o in retained.items() if pair(name,candidate,n,o)}
                if any(f[0]=='search_budget' for rows in failures.values() for f in rows):
                    job['pending'].extend(options[oi:])
                    if not any(j is job for j in self.queue):self.queue.append(job)
                    self.events.append(dict(action='PAIR_SCREEN_PENDING',net=name,retained=sorted(retained)))
                    searches[-1]['pair_budget_pending']=True
                    # Fresh pair resources on the next screen; do not consume
                    # and lose a candidate on an unperformed geometry check.
                    return self.take_completed(), spent, searches
                if failures or not session.permits_core(trial):
                    self.events.append(dict(action='CONDITIONAL_REJECTION', net=name, failures=failures,
                                            retained=sorted(retained)))
                    continue
                # Local errors keep their evidence and the original path heaps.
                # They do not produce a geometric nogood.
                admitted = session.admit_core(self.state.source, self.state.nets, trial)
                if set(admitted) != set(trial):
                    record=dict(action='LOCAL_ADMISSION_DEFERRED_OR_REJECTED', net=name,
                                evidence=deepcopy(session.local_records),selected={n:o['key'] for n,o in trial.items()})
                    self.events.append(record)
                    if any(r['status']=='CAD_EVALUATION_ERROR' for r in session.local_records.values()):
                        self.uncertain.append(dict(core=trial,evidence=record))
                    continue
                self.enqueue({**chosen, name:candidate}, (*job['generated'],name))
            if self.completed.keys()-self.delivered:
                break
        return self.take_completed(), spent, searches

    def diagnostics(self):
        return dict(released=sorted(self.group), outside=sorted(self.outside), pending_jobs=len(self.queue),
                    independent_states=len(self.visited), labels=self.labels, calls=self.calls,
                    generated_candidates=self.new_candidates, events=self.events,
                    fragment_probes=self.probes,delivered_completions=len(self.delivered),
                    cad_unknown_arrangements=len(self.uncertain),
                    pending=[dict(net=j['net'], new_routes={n:o['key'] for n,o in j['chosen'].items()})
                             for j in self.queue], completed=len(self.completed),
                    deferred_pair_candidates=sum(len(j['pending']) for j in self.queue))
