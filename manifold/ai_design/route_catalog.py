"""Resumable analytic Router sampling owned by a new AI generation.

Catalog sampling is analytic. Valuable cores also use the shared local CAD
gate; full Design acceptance remains separate. Model budgets are unchanged.
"""
import itertools
from collections import Counter, defaultdict, deque

from ..kinematics import dimensions


def geometry_key(route):
    return tuple(sorted(f.model_dump_json(exclude={'id','schematic_id'}) for f in route))


def terminal_key(source, net):
    from ..kinematics import pose
    owners={m.split(':')[0] for m in net.members}
    return (net.model_dump_json(),tuple((f.model_dump_json(),pose(f,source.block))
                                      for f in source.features if f.id in owners))


def cut_locations(source,route):
    from ..kinematics import pose,FACE_AXES
    return tuple((pose(f,source.block),dimensions(source.block)[FACE_AXES[f.face][2]] if f.through else f.depth)
                 for f in route)


def arrangement(option):
    # Different complete entry arrangements remain alternatives even when their
    # scalar manufacturing objectives tie. No close-cost deduplication.
    return tuple(sorted({(f.face, f.u, f.v) for f in option['route']}))


class Catalog:
    def __init__(self, source, net, definitions, threads, modifiers, tools, cache, seeds=()):
        from ..routing import propose, obstacle_safe_planes, port_approach_candidates, connection_topology_candidates,simple_routes
        from ..cavity_access import _direct_axial_candidates
        from ..branch_candidates import terminal_branch_candidates
        self.source,self.net,self.definitions=source,net,definitions
        self.threads,self.modifiers,self.tools,self.cache=threads,modifiers,tools,cache
        self.clear=[];self.rejected=[];self.seen=set();self.attempts=0;self.errors=0
        self.families=Counter();self.reused=0;self.seed_queue=deque(seeds)
        orders=[o for o in itertools.permutations(range(3)) if net.preferred_axis=='auto' or o[0]=='xyz'.index(net.preferred_axis)]
        entries=('nearest','negative','positive') if net.entry_preference=='nearest' else (net.entry_preference,)
        self.bases=[];self.refined=set();self.refinements=deque()
        def direct():
            for order,entry in itertools.product(orders,entries):
                key=''.join('xyz'[i] for i in order)+':'+entry+':direct'
                yield key,propose(source,net,order,entry,definitions=definitions)
        def detours():
            planes=obstacle_safe_planes(source,net,definitions,threads,modifiers)
            # Interleave axes, directions and entry arrangements rather than
            # exhausting one XYZ family before reaching another machining layer.
            for side,order,entry,axis in itertools.product('mp',orders,entries,'xyz'):
                name='offset_'+axis+'_'+side
                yield ''.join('xyz'[i] for i in order)+':'+entry+':'+name,propose(source,net,order,entry,name,definitions,planes)
        def trees():
            bases=[dict(key=''.join('xyz'[i] for i in o)+':'+e+':direct',route=propose(source,net,o,e,definitions=definitions))
                   for o in orders[:2] for e in entries]
            yield from connection_topology_candidates(source,net,bases,definitions,threads,modifiers)
        def ports():
            bases=[dict(key=''.join('xyz'[i] for i in o)+':'+e+':direct',route=propose(source,net,o,e,definitions=definitions))
                   for o in orders[:2] for e in entries]
            yield from port_approach_candidates(source,net,bases,definitions,threads,modifiers)
        # Common/deep/face-window branch strategies were absent from the old
        # AI _catalogs path altogether. Reuse the Router's actual cuts.
        def simple():
            for i,route in enumerate(simple_routes(source,net,definitions,include_detours=False)):
                yield 'ai-coaxial-'+str(i),route
        streams=[('simple',simple()),('branch',terminal_branch_candidates(source,net,definitions,threads,modifiers,cache,diverse=True)),
                 ('direct',direct()),('axial',_direct_axial_candidates(source,net,definitions,threads,modifiers)),
                 ('tree',trees()),('port',ports()),('detour',detours())]
        self.queues=deque((name,iter(rows)) for name,rows in streams)

    def step(self):
        from ..routing import route_from_variant
        if self.seed_queue:
            option=self.seed_queue.popleft();name='retained';key,route=option['key'],option['route'];self.reused+=1
        elif self.refinements:
            key=self.refinements.popleft();name='safe-entry'
            route=route_from_variant(self.source,self.net,key,self.definitions,self.threads,self.modifiers,obstruction_cache=self.cache)
        else:
            while self.queues:
                name,queue=self.queues.popleft()
                try:key,route=next(queue)
                except StopIteration:continue
                except ValueError:
                    self.errors+=1;self.attempts+=1;self.queues.append((name,queue));return True
                self.queues.append((name,queue));break
            else:return False
        self.accept(key,route,name)
        return True

    def accept(self,key,route,name):
        from ..routing import route_obstructions,segment_depth
        from ..closure_runtime import bind_route
        from ..schema import Feature
        self.attempts+=1;self.families[name]+=1
        if route is None:return True
        route=bind_route(self.source,route);signature=geometry_key(route)
        if signature in self.seen:return True
        self.seen.add(signature)
        failures=route_obstructions(self.source,self.net,route,self.threads,self.definitions,self.modifiers,self.cache)
        for f in route:
            try:Feature.model_validate(f.model_dump())
            except ValueError:
                # bind_route/model_copy can expose an engagement longer than
                # a shallow generated drilling. Reject that raw candidate;
                # never let diagnostic deserialization abort layout search.
                failures.add(('invalid_machining',f.id));self.errors+=1
        failures.update(('forbidden_face',f.id) for f in route if f.face in self.source.constraints.forbidden_drilling_faces)
        if any(not any(abs(t['diameter_mm']-f.diameter)<=.011 and t['max_depth_mm']+1e-6>=segment_depth(f)
                       for t in self.tools) for f in route):failures.add(('tool_reach',self.net.id))
        option=dict(key=key,route=route,failures=failures,risk=0,connection_verified=False)
        (self.rejected if failures else self.clear).append(option)
        # A source/installation rejection schedules real opposite entry
        # selection immediately, not after the raw catalog's old cutoff.
        legacy=(key.startswith(('tree_','port_','axial_')) or sorted(key.split(':')[0])==list('xyz'))
        if failures and legacy and any(
                f[0] in ('source_protected','source_wall','installation_access','plug_cut') for f in failures):
            token='safe:'+key
            if token not in self.refined:self.refinements.append(token);self.refined.add(token)
        return True

    def active(self, width=8, retained=()):
        from ..routing import route_objective
        ranked=sorted(self.clear,key=lambda o:(route_objective(self.source,o['route'],definitions=self.definitions),o['key']))
        first=[o for o in ranked if o['key'] in retained];seen={arrangement(o) for o in first};rest=[]
        for o in ranked:
            if o in first:continue
            if arrangement(o) in seen:rest.append(o)
            else:first.append(o);seen.add(arrangement(o))
        return (first+rest)[:width]

    def diagnostics(self, active, *, all_rejections=False):
        from ..routing import _conflict_objective, route_objective
        rejected=sorted(self.rejected,key=lambda o:(_conflict_objective(o['failures']),
            route_objective(self.source,o['route'],definitions=self.definitions),o['key']))
        return dict(analytic_candidates=len(active),source_clear=len(self.clear),attempted=self.attempts,
            candidate_errors=self.errors,families=dict(self.families),reused=self.reused,
            deferred_clear=max(0,len(self.clear)-len(active)),unexpanded_families=[n for n,_ in self.queues],
            pending_entry_repairs=len(self.refinements),connectivity='NOT_EXACT_VERIFIED',
            # Entry/layer diversity is evidence even when another entry is
            # source-clear. Keep every distinct explored arrangement; feedback
            # consumes it lazily under its own transform budget.
            rejected_samples=[dict(variant=o['key'],failures=sorted(o['failures']),
                features=[f.model_dump(mode='json') for f in o['route']]) for o in (rejected if all_rejections else rejected[:3])])


class Session:
    """Small operation-owned pool reuse; every copied route is re-screened."""
    def __init__(self):
        self.previous={};self.catalogs={};self.cache={};self.remaining=0
        self.combinations=[];self.pair_evidence={};self.context=None;self.invalidated=False
        self.corridor_frontiers={}
        self.contexts={}
        self._prepared_once=False
        from ..routing_continuation import AISearchContext
        self.search_context=AISearchContext()
        self.local_admission=None;self.local_records={};self.local_source_dependency=None
        self.local_allocation=None
        self.planned_routes={}
        from .joint_solver import JointSolver
        self.solver=JointSolver(self)

    def admit_core(self,source,nets,core):
        from .local_admission import LocalAdmission
        if self.local_admission is None:self.local_admission=LocalAdmission(max(8,2*len(nets)))
        self.local_admission.allocation=self.local_allocation
        before=self.local_admission.used
        kept,records=self.local_admission.core(source,nets,core,self.catalogs)
        if self.local_allocation is not None:self.local_allocation-=self.local_admission.used-before
        if self.local_source_dependency!=self.local_admission.source_dependency:self.local_records={}
        self.local_source_dependency=self.local_admission.source_dependency
        self.local_records.update(records)
        for name,option in core.items():
            self.search_context.record_admission(option,records[name])
        return kept

    def permits_core(self,core):
        return self.solver.permits(core) and (self.local_admission is None or self.local_admission.permits(core))

    def source_context(self,source,definitions,threads,modifiers,tools=None):
        from ..routing_continuation import dependency_key
        from ..engineering_db import tool_definitions
        # Tool, closure, explicit endpoint and engineering dependencies are
        # part of the same state as placement, not an outer geometry-only LRU.
        if source.nets:
            return dependency_key(source,source.nets[0],definitions,threads,modifiers,[],
                                  tool_definitions('drill') if tools is None else tools)
        return source.model_dump_json()

    def seed_combination(self,source,chosen):
        # Restored diagnostics supply real cuts, not a compatibility approval.
        from ..engineering_conditions import effective_net
        geometries={(n,geometry_key(o['route'])) for n,o in chosen.items()}
        clear_pairs=[p for p,failures in self.pair_evidence.items() if not failures and all(k in geometries for k in p)]
        terminals={n:terminal_key(source,effective_net(source,next(k for k in source.nets if k.id==n))) for n in chosen}
        identity=lambda r:(tuple(sorted(r['terminals'].items())),
                           tuple(sorted((n,geometry_key(o['route'])) for n,o in r['chosen'].items())))
        record=dict(source_context=self.context,clear_pairs=clear_pairs,terminals=terminals,chosen=chosen,
            locations={n:cut_locations(source,o['route']) for n,o in chosen.items()})
        self.combinations=[r for r in self.combinations if identity(r)!=identity(record)]+[record]
        # A lower-coverage core with different entrances is not dominated by a
        # longer incumbent. Count budgets bound expansion, not equivalence.
        if self.solver.current:self.solver.current.retain(chosen)

    def compatible_core(self,source,nets,pair):
        best={};discarded=set();checked=0;valid=[]
        for record in self.combinations:
            kept={}
            for name,old in record['chosen'].items():
                if name not in nets or record['terminals'][name]!=terminal_key(source,nets[name]) or record['locations'][name]!=cut_locations(source,old['route']):discarded.add(name);continue
                option=next((o for o in self.catalogs[name].clear if geometry_key(o['route'])==geometry_key(old['route'])),None)
                if option is not None:
                    if not self.permits_core({name:option}):continue
                    checked+=len(kept)
                    if all(not pair(name,option,n,p) for n,p in kept.items()):kept[name]=option
            if len(kept)>len(best):best=kept
            if kept:valid.append(kept)
        self.validated_cores=valid
        self.core_checks=dict(source_context=self.context,source_changed=self.invalidated,
            checked_pairs=checked,discarded_changed_terminals=sorted(discarded),retained_nets=sorted(best),exact_verified=False)
        return best

    def prepare(self, source, nets, definitions, threads, modifiers, tools, progress=None):
        def planned():
            for name,route in self.planned_routes.items():
                if name in self.catalogs and geometry_key(route) not in self.catalogs[name].seen:
                    self.catalogs[name].accept('engineering-plan:'+str(name),route,'engineering-plan')
        context=self.source_context(source,definitions,threads,modifiers,tools)
        self.invalidated=self.context is not None and self.context!=context
        if context in self.contexts and not self._prepared_once:
            self.catalogs,self.cache,self.pair_evidence,self.remaining=self.contexts[context]
            self.context=context
            planned()
            return {n:c.active(width=len(c.clear)) for n,c in self.catalogs.items()}
        if self._prepared_once and context==self.context:
            self._prepared_once=False
            planned()
            return {n:c.active(width=len(c.clear)) for n,c in self.catalogs.items()}
        self._prepared_once=False
        self.invalidated=self.context is not None and self.context!=context
        if context!=self.context:self.pair_evidence={}
        self.context=context
        from .execution import cache
        self.cache=cache();self.catalogs={}
        for name,net in nets.items():
            seeds=[]
            for record in self.combinations:
                if name in record['chosen'] and record['terminals'][name]==terminal_key(source,net) and record['locations'][name]==cut_locations(source,record['chosen'][name]['route']):seeds.append(record['chosen'][name])
            seeds.extend(o for o in self.previous.get(terminal_key(source,net),())
                         if o.get('replay_locations')==cut_locations(source,o['route']))
            self.catalogs[name]=Catalog(source,net,definitions,threads,modifiers,tools,self.cache,seeds)
        planned()
        # SAME total sample allocation as 32 per Net. Cheap Nets stop after
        # first diverse choices; missing/complex Nets receive unused tokens.
        total=24*len(nets);used=len(self.planned_routes);self.remaining=8*len(nets)
        if self.planned_routes and all(any(geometry_key(o['route'])==geometry_key(self.planned_routes.get(n,[]))
                                          for o in c.clear) for n,c in self.catalogs.items()):
            # The compiled process has supplied every real machining network.
            # Leave ordinary alternative generators dormant until a real
            # obstruction/Exact rejection requires a different process branch.
            return {n:c.active(width=len(c.clear)) for n,c in self.catalogs.items()}
        for name,catalog in self.catalogs.items():
            for _ in range(8):
                if catalog.step():used+=1
            if progress:progress('access',net=name,completed=used,total=total)
        while used<total:
            candidates=[(len(c.clear)>=min(4,max(1,len(c.net.members)-1)),
                         len(c.clear),c.attempts/max(1,len(c.net.members)-1),name,c)
                        for name,c in self.catalogs.items() if c.queues or c.refinements or c.seed_queue]
            if not candidates:break
            *_,name,catalog=min(candidates,key=lambda r:r[:-1])
            if catalog.step():used+=1
        return {n:c.active() for n,c in self.catalogs.items()}

    def remember_context(self):
        self.contexts[self.context]=(self.catalogs,self.cache,self.pair_evidence,self.remaining)
        # Operation lifetime and count budgets bound storage. Dropping a live
        # geometry here used to discard deferred entrance/fragment work.

    def coordinate(self,source,witnesses):
        """Allocate reserved samples to conflicting real cut planes, both Nets.

        Candidate production still uses route_from_variant/entry-safe Router.
        Keep old routes too, so releasing both Nets is a joint pool search.
        """
        from ..routing import route_from_variant
        from ..engineering_conditions import required_wall
        from ..kinematics import FACE_AXES
        from ..schema import Feature
        queues=[];seen=set()
        for witness in witnesses:
            cuts=[Feature.model_validate(f) for f in witness.get('features',[])]
            for a,b in itertools.combinations(cuts,2):
                if a.route_net==b.route_net:continue
                axes={FACE_AXES[a.face][2],FACE_AXES[b.face][2]}
                for axis in set(range(3))-axes:
                    gap=(a.diameter+b.diameter)/2+required_wall(source,a,b,definitions=self.catalogs[a.route_net].definitions)+.01
                    for bore in (a,b):
                        catalog=self.catalogs.get(bore.route_net)
                        if catalog is None:continue
                        for option in catalog.active():
                            key=option['key'];head=key.split(':')[0 if not key.startswith('window:') else 1]
                            if not head.startswith('branch_'):continue
                            tokens=head.split('_');old=float(tokens[axis+2])
                            for delta in (-gap,gap):
                                # Shift the actual conflicting line's plane,
                                # relative to this candidate's existing junction.
                                value=old+delta
                                if not 0<value<dimensions(source.block)[axis]:continue
                                parts=tokens.copy();parts[axis+2]=f'{value:.6f}'
                                variant=key.replace(head,'_'.join(parts),1)
                                if (bore.route_net,variant) in seen:continue
                                seen.add((bore.route_net,variant));queues.append((catalog,variant))
        # Round-robin by Net: replan BOTH sides, not all moves for the first one.
        groups=defaultdict(deque)
        for catalog,key in queues:groups[catalog.net.id].append((catalog,key))
        used=0
        while groups and self.remaining:
            for name in list(groups):
                if not self.remaining:break
                catalog,key=groups[name].popleft()
                route=route_from_variant(source,catalog.net,key,catalog.definitions,catalog.threads,catalog.modifiers,obstruction_cache=self.cache)
                catalog.accept(key,route,'conflict-plane');self.remaining-=1;used+=1
                if not groups[name]:del groups[name]
        # Missing source approaches, rather than pair conflicts, receive the
        # unused reserve through their still-resumable strategy queues.
        while self.remaining:
            candidates=[c for c in self.catalogs.values() if c.queues or c.refinements]
            if not candidates:break
            catalog=min(candidates,key=lambda c:(len(c.clear),c.attempts,c.net.id))
            if catalog.step():self.remaining-=1;used+=1
        return dict(samples=used,pending=sum(map(len,groups.values())),unspent=self.remaining)

    def remember(self, source, selected=None):
        if selected:self.seed_combination(source,selected)
        for catalog in self.catalogs.values():
            kept=[]
            if selected and catalog.net.id in selected:kept.append(selected[catalog.net.id])
            seen={geometry_key(o['route']) for o in kept}
            for option in catalog.active():
                key=geometry_key(option['route'])
                if key not in seen:kept.append(option);seen.add(key)
            # The useful partial/complete choice gets the first reuse slot,
            # including when compatibility promoted it beyond the first eight.
            if kept:self.previous[terminal_key(source,catalog.net)]=[
                {**o,'replay_locations':cut_locations(source,o['route'])} for o in kept[:8]]
        while len(self.previous)>128:self.previous.pop(next(iter(self.previous)))
