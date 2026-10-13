"""Search-only joint state. Diagnostic routes confer no engineering authority."""
import math
from ..kinematics import dimensions
from ..schema import Feature


def capture(design, assessment, definitions):
    from ..routing import route_objective
    from .route_catalog import terminal_key, geometry_key
    from .coupled_layout import interfaces
    required={n.id:n for n in design.nets if n.routing=='automatic' and
              n.route_state in ('unresolved','proposal') and len(n.members)>=2}
    partial=assessment.get('partial_routing',{})
    local=partial.get('local_admission',{})
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
    alternatives={}
    for w in constraints:
        key=(w.get('missing_net'),w.get('candidate'))
        entry=alternatives.setdefault(key,dict(nets=set(),pairs=set()))
        entry['nets'].update(set(w['nets'])-{w.get('missing_net')})
        entry['pairs'].update(tuple(f) for f in w.get('failures',[]) if isinstance(f,(list,tuple)))
    # Compare the best actual insertion for each missing Net, not the number
    # of diagnostics or options. More discovered alternatives must not make a
    # layout appear worse by themselves.
    burden=[]
    for name in missing:
        choices=[(len(v['nets']),len(v['pairs'])) for (n,_),v in alternatives.items() if n==name]
        burden.append(min(choices) if choices else (len(required)+1,0))
    return dict(status='SEARCH_STATE_NOT_ENGINEERING_APPROVAL',dimensions=list(dimensions(design.block)),
        placements=[dict(id=f.id,face=f.face,u=f.u,v=f.v,rotation=f.rotation) for f in design.features],
        compatible_nets=sorted(covered),unresolved_nets=missing,route_dependencies=dependencies,
        locally_admitted_nets=sorted(n for n in covered if local.get(n,{}).get('status')=='LOCAL_EXACT_ADMISSIBLE'),
        local_pending_nets=sorted(n for n in covered if local.get(n,{}).get('status')!='LOCAL_EXACT_ADMISSIBLE'),
        local_cad_error_candidates={n:r.get('candidate') for n,r in local.items() if r.get('status')=='CAD_EVALUATION_ERROR'},
        local_rejected_candidates={n:r.get('candidate') for n,r in local.items() if r.get('status')=='LOCAL_EXACT_REJECTED'},
        local_admission=local,
        interface_frames=interfaces(design,definitions),
        repair_burden=[sum(b[0] for b in burden),sum(b[1] for b in burden)],
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
        len(state['unresolved_nets']),-len(state.get('locally_admitted_nets',[])),tuple(state.get('repair_burden',(0,0))),tuple(objective[:-1]),
        math.prod(state['dimensions']),tuple(objective[-1:]),row['index'])
