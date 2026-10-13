"""Explicit new-AI-operation lifetime for shared 3D machining search.

No Model entry creates this context. Live heaps, cursors and connection trees
remain in the owned search; candidate IDs never store project geometry.
"""
from collections import OrderedDict
import hashlib
import heapq
import itertools
import json
from copy import deepcopy

from .routing_space import network_key


def dependency_key(design,net,definitions,threads,modifiers,reserved,tools):
    from .closure_runtime import bound
    closures={f.closure_definition_id:bound(f) for f in [*design.features,*reserved] if f.closure_definition_id}
    # Include defaults for newly bound closures too. A changed closure library
    # must not retain an old action/engagement cache in a live search.
    from .closure_runtime import catalog
    # members is a derived/excluded schema field, but callers can supply a
    # scoped terminal set. It is an explicit search dependency nonetheless.
    payload=[design.model_dump(mode='json'),net.model_dump(mode='json'),list(net.members),
        [(n.id,list(n.members)) for n in design.nets],
        sorted((k,d.model_dump(mode='json')) for k,d in definitions.items()),threads,modifiers,
        [f.model_dump(mode='json') for f in sorted(reserved,key=lambda f:f.id)],tools,closures,catalog()]
    return hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()


class _NetSearch:
    def __init__(self,design,net,definitions,threads,modifiers,reserved,tools,trace,geometry_cache):
        from .drilling_planner import _prepare_net
        design=design.model_copy(deep=True);net=net.model_copy(deep=True)
        definitions=deepcopy(definitions);threads=deepcopy(threads);modifiers=deepcopy(modifiers)
        reserved=deepcopy(reserved);tools=deepcopy(tools)
        self.space,self.members,self.detail,self.aliases,self.seeds=_prepare_net(design,net,definitions,threads,modifiers,
            reserved=reserved,tools=tools,cache=geometry_cache)
        # Phase A separated endpoint checks from complete-cut facts. These
        # facts can therefore be shared across independent searches with the
        # exact same dependency fingerprint, without sharing visited/frontiers.
        self.space.actions=geometry_cache.setdefault('complete_actions',{})
        # Candidate delivery is batched; path exploration is not truncated
        # after a batch of solutions. Its actual heap survives until exhausted.
        self.budget=dict(used=0,limit=0,alternatives=None)
        self.trace=[] if trace else None;self.trace_digest=hashlib.sha256()
        self.candidates={};self.delivered=set();self.evidence={};self.forbidden=set()
        self.path=None;self.frontier=[];self.visited=set();self.order=[];self.order_index=0
        self.largest_path_solution_batch=0
        self.iterator=self.steps();self.event=next(self.iterator,None)

    def observe(self,row):
        row=dict(order=self.order,next_terminal=self.order[self.index],**row)
        encoded=json.dumps(row,sort_keys=True);self.trace_digest.update(encoded.encode())
        if self.trace is not None:self.trace.append(row)

    def steps(self):
        from .drilling_planner import _PathSearch,_distance,candidate
        from .routing import route_objective
        if self.aliases is None:return
        design=self.space.design;members=self.members
        orders=[members,list(reversed(members))] if len(members)>2 else [members]
        for self.order_index,order in enumerate(orders):
            self.order=order;self.frontier=[];self.visited=set();serial=itertools.count()
            def push(job):
                heapq.heappush(self.frontier,(len(order)-job['index'],
                    route_objective(design,job['cuts'],definitions=self.space.definitions),next(serial),job))
            def enqueue(index,cuts,root,paths,blocked=()):
                token=(index,network_key(cuts),root,blocked)
                if token in self.visited:return
                self.visited.add(token)
                push(dict(index=index,cuts=cuts,root=root,paths=paths,blocked=blocked,
                          attempted=set(blocked),goal_index=0,path=None,harvested=0))
            enqueue(1,[],None,[])
            while self.frontier:
                *_,job=heapq.heappop(self.frontier);self.active_job=job
                index=job['index'];self.index=index;cuts=job['cuts'];root=job['root'];paths=job['paths']
                if index==len(order):
                    self.candidates.setdefault(network_key(cuts),candidate(cuts))
                    yield 'candidate'
                    continue
                member=order[index]
                if job['goal_index']>=len(self.aliases[member]):
                    # All goal heaps were fully explored. Recreating a parent
                    # with a forbidden list would repeat the same prefix.
                    continue
                goal=self.aliases[member][job['goal_index']]
                if job['path'] is None:
                    if root is None:
                        starters=[(p,self.seeds.get((order[0],p),[])) for p in self.aliases[order[0]]]
                    else:
                        points={root,*self.space.junctions(cuts,goal),*[p for path in paths for segment in path for p in segment]}
                        starters=[(p,cuts) for p in sorted(points,key=lambda p:(_distance(p,goal),p))]
                    initial=[]
                    for point,route in starters:
                        for bore in self.seeds.get((member,goal),[]):route=self.space.attach(route,bore)
                        initial.append((point,route))
                    job['path']=_PathSearch(self.space,None,goal,[],set(job['blocked']),self.detail,
                        starts=initial,trim=False,observe=self.observe)
                    job['harvested']=0
                self.path=job['path']
                if self.path.queue and not self.path.done:
                    yield 'label'
                    self.path.step(self.budget)
                # A valid partial connection advances the actual terminal tree
                # immediately; its unfinished parent path remains a live job.
                for route,path in self.path.solutions[job['harvested']:]:
                    job['attempted'].add(network_key(route))
                    enqueue(index+1,route,root if root is not None else path[0][0] if path else goal,[*paths,path])
                job['harvested']=len(self.path.solutions)
                self.largest_path_solution_batch=max(self.largest_path_solution_batch,len(self.path.solutions))
                if not self.path.queue or self.path.done:
                    job['path']=None;job['goal_index']+=1
                push(job)

    def advance(self,labels,alternatives,forbidden):
        before=self.budget['used'];target=before+labels;self.budget['limit']=target
        self.forbidden.update(forbidden)
        # Drain completed candidate/tree bookkeeping at a batch boundary; stop
        # only BEFORE the next label. No partially popped state is discarded.
        while self.event is not None:
            if self.event=='label' and self.budget['used']>=target:break
            self.event=next(self.iterator,None)
        options=[]
        for key,option in self.candidates.items():
            if key in self.delivered or key in self.forbidden:continue
            options.append(deepcopy(option))
            self.delivered.add(key)
            if len(options)>=alternatives:break
        jobs=[row[-1] for row in self.frontier]
        if self.event=='label':jobs.append(self.active_job)
        live_paths=[j['path'] for j in jobs if j.get('path') is not None]
        termination=self.detail.get('termination') if self.aliases is None else 'LABEL_BUDGET' if self.event else 'EXPLORED_FRONTIER_EMPTY'
        classification=self.detail.get('classification') or ('CANDIDATE_ADMISSION_PENDING' if options else
            'CORRIDOR_GENERATION_LIMIT' if self.event else 'EXPLORED_CANDIDATES_DELIVERED' if self.candidates else
            'NO_ADMISSIBLE_CORRIDOR_IN_EXPLORED_SPACE')
        detail={**self.detail,**self.space.diagnostics(termination),
            'labels':self.budget['used']-before,'cumulative_labels':self.budget['used'],
            'frontier_labels':len(self.path.queue) if self.path else 0,'path_visited':len(self.path.seen) if self.path else 0,
            'deferred_tree_states':len(self.frontier),'tree_visited':len(self.visited),'terminal_order_index':self.order_index,
            'live_path_frontiers':len(live_paths),'all_frontier_labels':sum(len(p.queue) for p in live_paths),
            'largest_retained_path_solution_batch':self.largest_path_solution_batch,
            'active_tree':dict(next_terminal_index=self.index,goal_index=self.active_job['goal_index'],
                cut_ids=[f.id for f in self.active_job['cuts']],root=self.active_job['root'],
                connected_paths=self.active_job['paths']) if self.event=='label' else None,
            'trace_sha256':self.trace_digest.hexdigest(),'generated_candidates':len(options),
            'total_candidates':len(self.candidates),'admission_states':self.evidence,
            'classification':classification,'resumable':self.event is not None}
        return options,detail


class AISearchContext:
    """Must be explicitly supplied by new AI Generate; never inferred from origin."""
    def __init__(self,*,trace=False):
        self.searches=OrderedDict();self.trace=trace;self.last_key=None

    def advance(self,design,net,definitions,threads,modifiers,*,reserved=(),label_limit=8192,
                alternatives=4,forbidden=(),cache=None,tools=None):
        from .engineering_db import tool_definitions
        tools=tools if tools is not None else tool_definitions('drill');reserved=list(reserved)
        key=dependency_key(design,net,definitions,threads,modifiers,reserved,tools)
        resumed=key in self.searches
        if not resumed:
            geometry_cache=(cache if cache is not None else {}).setdefault('ai_search_geometry',{}).setdefault(key,{})
            self.searches[key]=_NetSearch(design,net,definitions,threads,modifiers,reserved,tools,self.trace,geometry_cache)
        self.searches.move_to_end(key);self.last_key=key
        options,detail=self.searches[key].advance(label_limit,alternatives,forbidden)
        detail.update(search_context=key,resumed=resumed,dependency_changed=not resumed)
        return options,detail

    def record_admission(self,option,evidence):
        token=network_key(option['route'])
        for search in self.searches.values():
            if token in search.candidates:
                records=search.evidence.setdefault(search.candidates[token]['key'],{})
                records[evidence['dependency']]=dict(evidence)
