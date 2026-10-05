"""Actual project route geometry, independent of search strategy and engine revision."""
from .schema import Design
from .kinematics import resolve_parents
from .timing import progress


def pending_nets(design):
    return {n.id for n in design.nets if n.routing=='automatic' and n.route_state=='unresolved'}


def route_metadata(design):
    return [dict(net=n.id,variant=n.routing_variant or 'retained',route_state=n.route_state,
                 drillings=len(route),plugs=sum(f.plugged for f in route),
                 length_mm=round(sum(f.depth for f in route),2),status='CURRENT_GEOMETRY')
            for n in design.nets if n.routing=='automatic'
            for route in [[f for f in design.features if f.route_net==n.id and not f.suppressed]]]


def merge_routes(authored,proposal,*,commit=False,net_ids=None):
    """Copy only owned generated cuts; never flatten authored parent placements."""
    result=authored.model_copy(deep=True)
    owners={n.id for n in result.nets if n.routing=='automatic' and (net_ids is None or n.id in net_ids)}
    result.features=[f for f in result.features if f.route_net not in owners]
    result.features.extend(f.model_copy(deep=True) for f in proposal.features if f.route_net in owners)
    by_net={n.id:n for n in proposal.nets}
    for net in result.nets:
        if net.id not in owners:continue
        source=by_net[net.id]
        net.routing_variant=source.routing_variant
        net.route_state='committed' if commit and source.route_state=='proposal' else source.route_state
        net.route_issue=source.route_issue
        # Keep the authored automatic/manual sizing choice and nullable overrides.
        net.diameter=source.diameter
    return Design.model_validate(result.model_dump())


def require_current_routes(design):
    missing=[n.id for n in design.nets if n.id in pending_nets(design) and len(n.members)>1]
    if missing:raise ValueError('Routing must finish for '+', '.join(missing)+'. Inspect the current proposal, then Save or Validate; use Reroute to request a new route.')


def validate_current_design(design,*,step_path=None):
    """One exact check of these cuts. No candidate enumeration or CAD fallback."""
    require_current_routes(design)
    from .geometry import build_geometry
    from .routing import authorize_generated_contacts
    from .validation import validate
    from .cad_acceptance import step_round_trip,add_step_check
    target=resolve_parents(design.model_copy(deep=True))
    progress('geometry',20)
    geometry=build_geometry(target)
    progress('rules',75)
    authorize_generated_contacts(target,geometry)
    report=validate(target,geometry)
    for net in target.nets:
        if net.routing=='automatic' and net.route_state=='stale':
            report['checks'].append(dict(rule='route_state_review',status='WARNING',items=[net.id],
                message=net.route_issue or 'Stored route retained. Review conditions or explicitly Reroute / Optimize.',repair_domain=None))
            report['counts']['WARNING']+=1
            if report['status']=='PASS':report['status']='WARNING'
    progress('topology',85)
    progress('step',88)
    check=step_round_trip(geometry,step_path)
    add_step_check(report,check)
    if check['status']=='PASS':progress('step_verified',93)
    return target,route_metadata(target),geometry,report


def refresh_conditions(design,net_ids,resize_ids=()):
    """Resize only stored centerlines, screen them, and retain old cuts on failure."""
    from .engineering_db import definitions_for_design,thread_definitions_for_design,modifier_definitions_for_design,tool_definitions
    from .engineering_conditions import effective_net,wall_unresolved
    from .routing import route_obstructions
    from .geometry import tip_depth
    from .sizing import route_sizing
    result=design.model_copy(deep=True);posed=resolve_parents(result)
    definitions=definitions_for_design(posed);threads=thread_definitions_for_design(posed)
    modifiers=modifier_definitions_for_design(posed) if any(f.machining_modifiers for f in posed.features) else {}
    tools=None
    for net in result.nets:
        if net.id not in net_ids or net.routing!='automatic' or net.route_state=='unresolved':continue
        previous=[f for f in result.features if f.route_net==net.id]
        if not previous:continue
        context=resolve_parents(result);current=effective_net(context,net)
        route=[f.model_copy(deep=True) for f in previous]
        try:
            if net.id in resize_ids and tools is None:tools=tool_definitions('drill')
            diameter=net.diameter
            for _ in range(12 if net.id in resize_ids else 0):
                size=route_sizing(current,tools=tools,required_depth=max(f.depth+tip_depth(f) for f in route),preferred_unit=context.project_context)
                diameter=size['diameter_mm']
                changed=any(abs(f.diameter-diameter)>1e-9 for f in route)
                for f in route:f.diameter=diameter
                if changed and net.routing_variant and net.routing_variant.startswith('axial_'):
                    from .cavity_access import cavity_terminal_candidates
                    probes=cavity_terminal_candidates(context,current.model_copy(update=dict(diameter=diameter)),definitions,threads,modifiers)
                    from .kinematics import FACE_AXES
                    sources={item.id:item for item in context.features if item.kind=='cavity'}
                    for f in route:
                        windows=[m for m in f.connects_to if ':' in m and m in net.members]
                        if not windows:continue
                        axial=[m for m in windows if m.split(':')[0] in sources
                               and FACE_AXES[sources[m.split(':')[0]].face][2]==FACE_AXES[f.face][2]
                               and FACE_AXES[sources[m.split(':')[0]].face][3]==-FACE_AXES[f.face][3]
                               and abs(sources[m.split(':')[0]].u-f.u)<1e-6 and abs(sources[m.split(':')[0]].v-f.v)<1e-6]
                        if not axial:continue
                        matches=[probes[m] for m in axial if m in probes and probes[m].face==f.face and abs(probes[m].u-f.u)<1e-6 and abs(probes[m].v-f.v)<1e-6 and probes[m].tip_angle==f.tip_angle and not f.direction]
                        if len(matches)!=len(axial):raise ValueError('The stored axial window has no safe resized stop depth for its tip/axis')
                        f.depth=max(p.depth for p in matches)
                if not changed:break
            else:
                if net.id in resize_ids:raise ValueError('Stored route sizing did not settle')
            context.features=[f for f in context.features if f.route_net!=net.id]+route
            if wall_unresolved(context,*route,definitions=definitions):raise ValueError('Pressure/material wall basis is unresolved')
            failures=route_obstructions(context,current,route,threads,definitions,modifiers)
            if failures:raise ValueError(' / '.join(sorted({f[0] for f in failures})))
            result.features=[f for f in result.features if f.route_net!=net.id]+route
            net.diameter=diameter;net.route_state='proposal';net.route_issue=''
        except ValueError as exc:
            net.route_state='stale';net.route_issue=f'Route {net.id} no longer satisfies current conditions: {exc}. Reroute this net.'[:500]
    return Design.model_validate(result.model_dump())
