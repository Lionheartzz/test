from .engineering_conditions import effective_net
"""Transient, source-checked incremental proposals. Never used by Validate/Build."""
from typing import Literal, Annotated
from pydantic import Field
from .schema import Design, Strict, Identifier, Circuit
from .kinematics import resolve_parents
from .timing import timed


class PreviewEdit(Strict):
    kind:Literal['global','local','none']='global'
    feature_ids:list[Identifier]=Field(default_factory=list,max_length=120)
    affected_nets:list[Circuit]=Field(default_factory=list,max_length=24)


class PreviewContext(Strict):
    scope:str=Field(max_length=80)
    source:Design
    source_revision:str=Field(pattern=r'^[0-9a-f]{64}$')
    proposal:Design
    edit:PreviewEdit
    variants:dict[Circuit,Annotated[str,Field(max_length=80,pattern=r'^(simple_\d+|[xyz]{3}:(nearest|negative|positive):(direct|offset_[xyz]_[pm]2?)|axial_\d+_[01]:[xyz]{3}:(nearest|negative|positive)(?::(?:c\d+_[xyz]_|j\d+_)\d+(?:\.\d{1,6})?(?:\+(?:c\d+_[xyz]_|j\d+_)\d+(?:\.\d{1,6})?){0,2})?)$')]]=Field(default_factory=dict,max_length=24)


class PreviewRequest(Strict):
    design:Design
    scope:str=Field(default='',max_length=80)
    context:PreviewContext|None=None
    exact_idle_ms:int=Field(default=0,ge=0,le=2000)


def affected_nets(design, feature_ids):
    owners=set(feature_ids)
    while True:
        descendants={f.id for f in design.features if f.parent_id in owners}
        if descendants<=owners:break
        owners.update(descendants)
    assigned={f.circuit for f in design.features if f.id in owners and f.circuit}
    assigned.update(net for f in design.features if f.id in owners for net in f.interface_nets.values())
    assigned.update(n.id for n in design.nets if any(m.split(':')[0] in owners for m in n.members))
    return assigned


def _routing_state(design, moved=()):
    # This is a safety check on explicit action metadata, not an edit classifier.
    pose={'u','v','face','rotation','direction'}
    features={f.id:f.model_dump(exclude=pose if f.id in moved else set()) for f in design.features}
    return dict(dimensions=(design.block.length,design.block.width,design.block.height),
                project_defaults=design.project_defaults.model_dump(),material_id=design.block.material_id,
                unit=design.project_context,rules=design.rules.model_dump(),constraints=design.constraints.model_dump(),
                nets=[n.model_dump() for n in design.nets],features=features,
                engravings=[r.model_dump() for r in design.engravings],
                block_modifiers=[r.model_dump() for r in design.block_modifiers])


def _seed_routes(request):
    context=request.context;design=request.design
    if context is None or context.edit.kind=='global' or request.scope!=context.scope:return None
    from .store import revision
    if revision(context.source)!=context.source_revision:return None
    changed=set(context.edit.feature_ids)
    ids={f.id for f in design.features}
    if context.edit.kind=='local' and (not changed or not changed<=ids):return None
    if context.edit.kind=='none' and changed:return None
    if _routing_state(design,changed)!=_routing_state(context.source,changed):return None
    original=resolve_parents(context.source)
    proposal=context.proposal
    if proposal.block!=original.block or proposal.rules!=original.rules or proposal.constraints!=original.constraints or proposal.project_defaults!=original.project_defaults:return None
    if [(n.id,n.members,n.routing,n.flow_lpm,n.velocity_limit) for n in proposal.nets]!=[
            (n.id,n.members,n.routing,n.flow_lpm,n.velocity_limit) for n in original.nets]:return None
    by_id={f.id:f for f in proposal.features}
    for feature in original.features:
        found=by_id.get(feature.id)
        # Exact presentation may add inferred generated contacts. Do not adopt
        # them as authored contacts; use the current authored features below.
        if found is None or found.model_dump(exclude={'connects_to'})!=feature.model_dump(exclude={'connects_to'}):return None
        if not set(feature.connects_to)<=set(found.connects_to):return None
    automatic={n.id for n in design.nets if n.routing=='automatic' and not any(f.frozen_net==n.id for f in design.features)}
    generated=[f for f in proposal.features if f.id not in ids]
    if any(f.kind!='drilling' or f.route_net not in automatic or f.circuit!=f.route_net or f.frozen_net for f in generated):return None
    if any(len(n.members)>1 and not any(f.route_net==n.id for f in generated) for n in design.nets if n.id in automatic):return None
    return generated,automatic


@timed('route.interactive')
def resolve_preview(request):
    import time
    local_deadline=time.monotonic()+8
    snapshot=None
    from .routing import (resolve_design,route_options,route_obstructions,route_objective,
                          proximity_risk,route_from_variant,resize_route,_ProposalSnapshot,_complete_route_combination,_proposal_source_key)
    def full(reason):
        cache={_proposal_source_key(request.design):snapshot} if snapshot is not None else None
        target,routes=resolve_design(request.design,exact=False,snapshot_cache=cache)
        return target,routes,dict(mode='GLOBAL',reason=reason,recomputed=sorted(n.id for n in target.nets if n.routing=='automatic'),retained=[],expansions=[])
    seed=_seed_routes(request)
    if seed is None:return full('No matching current proposal or global edit')
    generated,automatic=seed
    context=request.context
    initial=(affected_nets(request.design,context.edit.feature_ids)|affected_nets(context.source,context.edit.feature_ids)) if context.edit.kind=='local' else set()
    if context.edit.affected_nets and set(context.edit.affected_nets)!=initial:return full('Edit dependency mismatch')
    fixed=initial-automatic
    active=initial&automatic
    from .engineering_db import definitions_for_design,thread_definitions_for_design,modifier_definitions_for_design,tool_definitions
    from .sizing import route_sizing
    authored=resolve_parents(request.design)
    definitions=definitions_for_design(authored);threads=thread_definitions_for_design(authored)
    modifiers=modifier_definitions_for_design(authored) if any(f.machining_modifiers for f in authored.features) else {}
    snapshot=_ProposalSnapshot(authored,definitions,threads,modifiers)
    tools=None
    by_id={f.id:f for f in generated}
    expansions=[]
    baseline=context.proposal
    def screen(target,net):
        return route_obstructions(target,net,[f for f in target.features if f.route_net==net.id],threads,definitions,modifiers)
    baseline_failures={n.id:screen(baseline,n) for n in baseline.nets if n.id in automatic}
    current=authored.model_copy(deep=True)
    current.features.extend(f.model_copy(deep=True) for f in generated)
    newly_obstructed={n.id for n in current.nets if n.id in automatic-active and screen(current,n)-baseline_failures[n.id]}
    if newly_obstructed:
        expansions.append(dict(added=sorted(newly_obstructed),reason='Changed feature obstructs retained route'))
        active.update(newly_obstructed)

    def blockers(options,target,net):
        candidates=[]
        for option in options[:8]:
            failures=route_obstructions(target,net,option['route'],threads,definitions,modifiers)
            owners={by_id[key].route_net for failure in failures for key in failure[1:] if key in by_id}-active
            if owners:candidates.append((len(owners),len(failures),tuple(sorted(owners))))
        return set(min(candidates)[2]) if candidates else set()

    def attempt():
        nonlocal tools
        target=authored.model_copy(deep=True)
        target.features.extend(f.model_copy(deep=True) for f in generated if f.route_net not in active)
        selected={}
        for net in sorted(target.nets,key=lambda n:n.id):
            if net.id not in active:continue
            effective=effective_net(target,net)
            if time.monotonic()>=local_deadline:return None,selected,set()
            net.routing_variant=None
            if tools is None:tools=tool_definitions('drill')
            net.diameter=route_sizing(effective,tools=tools,required_depth=0,preferred_unit=target.project_context)['diameter_mm']
            options=[]
            variant=context.variants.get(net.id)
            # Regenerate an unchanged-priority current template before opening
            # a neighbourhood. This preview remains explicitly NOT OPTIMIZED;
            # hard screening and exact pruning still decide its admissibility.
            if variant and not effective.flow_lpm:
                route=route_from_variant(target,net,variant,definitions,threads,modifiers)
                if (route is not None and all(f.face not in target.constraints.forbidden_drilling_faces for f in route)
                        and not route_obstructions(target,net,route,threads,definitions,modifiers)):
                    original=route
                    route,connected=snapshot.simplify(target,net,route,known_failures=set())
                    if connected:options=[dict(key=variant,route=route,hard_failures=0,
                        risk=proximity_risk(target,net,route,definitions,threads),pruned_ids=sorted({f.id for f in original}-{f.id for f in route}))]
            # A feasible old template is a seed, never a proof of optimality.
            # The same source-safe family/Pareto shortlist now competes after
            # pruning, while retained nets stay fixed in the compatibility screen.
            options=route_options(target,net,definitions=definitions,thread_definitions=threads,
                                  modifier_definitions=modifiers,snapshot=snapshot,
                                  seed=options[0] if options else None)
            if effective.flow_lpm:
                sized=[]
                for option in options:
                    for _ in range(12):
                        from .geometry import tip_depth
                        try:sizing=route_sizing(effective,tools=tools,required_depth=max((f.depth+tip_depth(f) for f in option['route']),default=0),preferred_unit=target.project_context)
                        except ValueError:break
                        if all(abs(f.diameter-sizing['diameter_mm'])<1e-9 for f in option['route']):
                            option['hard_failures']=len(route_obstructions(target,net,option['route'],threads,definitions,modifiers))
                            option['tool_sizing']=sizing
                            sized.append(option);break
                        try:resize_route(target,net,option,sizing['diameter_mm'],definitions,threads,modifiers)
                        except ValueError:break
                for option in sized:
                    if option['hard_failures']:continue
                    option['route'],connected=snapshot.simplify(target,net,option['route'],known_failures=set())
                    option['hard_failures']=0 if connected else 1
                    option['risk']=proximity_risk(target,net,option['route'],definitions,threads)
                options=sorted(sized,key=lambda o:(o['hard_failures'],route_objective(target,o['route'],o['risk'],definitions),o['key']))
            if not options or options[0]['hard_failures']:
                return None,selected,blockers(options,target,net)
            option=options[0];selected[net.id]=option
            if option.get('tool_sizing'):net.diameter=option['tool_sizing']['diameter_mm']
            target.features.extend(option['route'])
        invalid={n.id for n in target.nets if n.id in automatic and
                 (screen(target,n) if n.id in active else screen(target,n)-baseline_failures[n.id])}
        return (target if not invalid else None),selected,invalid-active

    target=None;selected={}
    for _ in range(3):
        target,selected,conflicting=attempt()
        if target is not None:break
        # Try a bounded combination of ONLY the current local dependency set.
        if len(active)>1:
            local=authored.model_copy(deep=True)
            local.features.extend(f.model_copy(deep=True) for f in generated if f.route_net not in active)
            for net in local.nets:
                if net.id in active:
                    net.routing_variant=None
                    net.diameter=route_sizing(effective_net(local,net),tools=tools,required_depth=0,preferred_unit=local.project_context)['diameter_mm']
            pair=_complete_route_combination(local,definitions,threads,modifiers,snapshot,net_ids=active,deadline=local_deadline)
            if pair:
                local.features.extend(f for option in pair.values() for f in option['route'])
                if all(not screen(local,n) if n.id in active else not(screen(local,n)-baseline_failures[n.id])
                       for n in local.nets if n.id in automatic):
                    target,selected=local,pair;break
        new=conflicting&automatic-active
        if not new:break
        expansions.append(dict(added=sorted(new),reason='Hard conflict with retained route'))
        active.update(new)
        if active==automatic:break
    if target is None:
        result=full('Bounded local dependency search could not resolve conflicts')
        result[2]['initial_affected']=sorted(initial);result[2]['expansions']=expansions
        result[2]['fixed_nets_affected']=sorted(fixed)
        return result
    if len(target.features)>120:return full('Local proposal exceeds physical feature budget')
    routes=[]
    for net in target.nets:
        if net.id not in automatic:continue
        route=[f for f in target.features if f.route_net==net.id]
        option=selected.get(net.id)
        routes.append(dict(net=net.id,variant=option['key'] if option else 'retained',
            drillings=len(route),plugs=sum(f.plugged for f in route),
            objective=route_objective(target,route,definitions=definitions),
            pruned_drillings=option.get('pruned_ids',[]) if option else [],
            status='PROPOSAL_REQUIRES_EXACT_VALIDATION' if option else 'RETAINED_UNVALIDATED_PROPOSAL'))
    return target,routes,dict(mode='LOCAL' if active else 'REUSED',initial_affected=sorted(initial),
        recomputed=sorted(active),retained=sorted(automatic-active),fixed_nets_affected=sorted(fixed),expansions=expansions)
