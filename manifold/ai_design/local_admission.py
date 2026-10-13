"""Selective, dependency-bound local CAD admission of AI partial cores.

Raw candidates and error evidence survive rejection. This is neither a full
Design validation nor evidence of physical impossibility after a CAD error.
"""
from copy import deepcopy
import hashlib

from ..routing_continuation import dependency_key

ANALYTIC_CLEAR='ANALYTIC_CLEAR'
ADMISSIBLE='LOCAL_EXACT_ADMISSIBLE'
REJECTED='LOCAL_EXACT_REJECTED'
CAD_ERROR='CAD_EVALUATION_ERROR'


class LocalAdmission:
    def __init__(self,limit):
        self.limit=limit;self.used=0;self.records={};self.snapshots={};self.cache_hits=0;self.events=[]
        self.intrinsic_rejections={};self.source_dependency=None

    def bind(self,source,nets,catalogs):
        if not nets:self.source_dependency=None;return
        name=next(iter(nets));c=catalogs[name]
        self.source_dependency=dependency_key(source,nets[name],c.definitions,c.threads,c.modifiers,[],c.tools)

    def permits(self,core):
        from ..routing_space import network_key
        # Only a source/own-fluid proof is transferable to a smaller partial
        # core. Cross-Net obstruction failures remain conditional on retained
        # cuts and cannot become unconditional candidate exclusions.
        return all((self.source_dependency,n,network_key(o['route'])) not in self.intrinsic_rejections
                   for n,o in core.items())

    def check(self,source,net,option,core,definitions,threads,modifiers,tools,*,retry=False):
        from ..routing import _ProposalSnapshot,_verify_route_candidate
        from ..cad_geometry import GeometryEvaluationError
        from ..timing import diagnostic
        retained=[f for n,o in sorted(core.items()) if n!=net.id for f in o['route']]
        key=dependency_key(source,net,definitions,threads,modifiers,[*retained,*option['route']],tools)
        if key in self.records and not retry:
            self.cache_hits+=1
            return deepcopy(self.records[key])
        record=dict(status=ANALYTIC_CLEAR,dependency=key,candidate=option['key'],net=net.id,
            checked=False,full_engineering_validation_passed=None,physical_connectivity=None,
            retained_nets=sorted(set(core)-{net.id}),geometry=[f.model_dump(mode='json') for f in option['route']])
        from ..routing_space import network_key
        intrinsic=(self.source_dependency,net.id,network_key(option['route']))
        certificate=self.intrinsic_rejections.get(intrinsic) if self.source_dependency and not retry else None
        if certificate:
            previous=self.records[certificate['dependency']]
            inherited=deepcopy(previous)
            inherited.update(record,status=previous['status'],checked=True,
                physical_connectivity=previous['physical_connectivity'],
                reuse_basis=certificate['basis'],basis_dependency=certificate['dependency'])
            self.records[key]=deepcopy(inherited);self.cache_hits+=1
            return inherited
        if self.used>=self.limit:
            return dict(record,pending_reason='LOCAL_ADMISSION_BUDGET',retry_conditions=['Local evaluation allocation available'])
        context=source.model_copy(update=dict(features=[*source.features,*retained,*option['route']]))
        core_key=hashlib.sha256((key+str(retry)).encode()).hexdigest()
        # Each complete dependency set owns its source/contact/error cache.
        snapshot=self.snapshots.setdefault(core_key,_ProposalSnapshot(context,definitions,threads,modifiers))
        if retry:snapshot=_ProposalSnapshot(context,definitions,threads,modifiers);self.snapshots[core_key]=snapshot
        trial=deepcopy(option);trial.pop('cad_geometry_error',None)
        self.used+=1;error=None
        try:
            admitted=_verify_route_candidate(context,net,trial,snapshot,prune=False)
            error=trial.get('cad_geometry_error')
        except GeometryEvaluationError as exc:
            admitted=False;error=deepcopy(exc.record)
        record.update(checked=True,admission=trial.get('admission'),connectivity=trial.get('connectivity_detail'),
            failures=trial.get('conflicts',[]),verified_geometry=[f.model_dump(mode='json') for f in trial['route']])
        if error:
            record.update(status=CAD_ERROR,cad_error=error,physical_connectivity=None,
                retry_conditions=['Changed source/route/retained machining/engineering dependency',
                                  'Explicit local CAD retry uses a fresh error cache'])
        else:
            record.update(status=ADMISSIBLE if admitted else REJECTED,
                physical_connectivity=(trial.get('admission') or {}).get('fluid_connectivity_verified'),
                retry_conditions=[] if admitted else ['Changed geometry or engineering conditions'])
        own={f.id for f in [*source.features,*option['route']]}
        error_nodes=(error or {}).get('node_pair',[])
        independent_error=bool(error_nodes) and all(n.split(':')[0] in own for n in error_nodes) and (
            (error or {}).get('cad_operation','').startswith(('routing.fluid_','routing.common_','routing.node_','routing.opening_')))
        facts=trial.get('admission') or {}
        independent_failure=not error and (facts.get('fluid_connectivity_verified') is False or
            facts.get('all_fluid_nodes_connected') is False or facts.get('direct_contact_adequate') is False or
            facts.get('flow_opening_adequate') is False)
        if self.source_dependency and (independent_error or independent_failure):
            self.intrinsic_rejections[intrinsic]=dict(dependency=key,status=record['status'],
                basis='UNCHANGED_SOURCE_AND_OWN_FLUID_GEOMETRY',physical_infeasibility_proven=False)
        elif retry:self.intrinsic_rejections.pop(intrinsic,None)
        self.records[key]=deepcopy(record)
        self.events.append({k:v for k,v in record.items() if k not in ('geometry','verified_geometry','connectivity')})
        diagnostic('ai_local_admission',self.events[-1])
        return record

    def core(self,source,nets,core,catalogs):
        self.bind(source,nets,catalogs)
        records={}
        for name in sorted(core):
            c=catalogs[name]
            records[name]=self.check(source,nets[name],core[name],core,c.definitions,c.threads,c.modifiers,c.tools)
            core[name]['local_exact']=records[name]
        kept={n:o for n,o in core.items() if records[n]['status'] not in (REJECTED,CAD_ERROR)}
        return kept,records

    def diagnostics(self):
        return dict(used=self.used,limit=self.limit,cache_hits=self.cache_hits,events=self.events,
                    final_design_validated=False)
