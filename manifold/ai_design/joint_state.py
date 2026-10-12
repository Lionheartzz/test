"""Search-only joint state. Diagnostic routes confer no engineering authority."""
import math
from ..kinematics import dimensions
from ..schema import Feature


def capture(design, assessment, definitions):
    from ..routing import route_objective
    from .route_catalog import terminal_key, geometry_key
    required={n.id:n for n in design.nets if n.routing=='automatic' and
              n.route_state in ('unresolved','proposal') and len(n.members)>=2}
    partial=assessment.get('partial_routing',{})
    route=[Feature.model_validate(f) for f in partial.get('features',[])]
    covered=set(partial.get('nets',[])) & set(required)
    # A complete legacy screen may not have populated its partial record.
    if assessment.get('compatible') and not covered:
        route=[Feature.model_validate(f) for f in assessment.get('route_features',[])]
        covered={f.route_net for f in route}&set(required)
    dependencies={n:dict(terminals=terminal_key(design,required[n]),
        source_features=sorted({m.split(':')[0] for m in required[n].members}),
        drilling_ids=[f.id for f in route if f.route_net==n],
        geometry=geometry_key([f for f in route if f.route_net==n])) for n in sorted(covered)}
    missing=sorted(set(required)-covered)
    hard=assessment.get('fixed_conflicts',[])
    exact=assessment.get('exact_failures',[])
    constraints=assessment.get('coordination_constraints',[])
    return dict(status='SEARCH_STATE_NOT_ENGINEERING_APPROVAL',dimensions=list(dimensions(design.block)),
        placements=[dict(id=f.id,face=f.face,u=f.u,v=f.v,rotation=f.rotation) for f in design.features],
        compatible_nets=sorted(covered),unresolved_nets=missing,route_dependencies=dependencies,
        machining_objective=list(route_objective(design,route,definitions=definitions)),
        hard_conflicts=hard,exact_failures=exact,machining_constraints=constraints,
        exact_connections=assessment.get('exact_connections',{}),
        deferred_constraints=assessment.get('deferred_constraints',[]),
        compatible_cores=(assessment.get('joint_coordination') or {}).get('compatible_cores',[]),
        next_action='EXACT' if not missing and not hard and not exact else
            'REPAIR_LAYOUT' if constraints or assessment.get('spatial_feedback') or exact else 'EXPLORE_LAYOUT_AND_ROUTES')


def rank(row):
    """Hard constraints, compatible coverage, machining, then stock volume."""
    a=row['assessment'];state=row['joint_state'];objective=state['machining_objective']
    return (a['status']=='SOURCE_LAYOUT_REJECTED',len(state['hard_conflicts'])+len(state['exact_failures']),
        len(state['unresolved_nets']),tuple(objective[:-1]),
        math.prod(state['dimensions']),tuple(objective[-1:]),row['index'])
