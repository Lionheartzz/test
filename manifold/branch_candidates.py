"""Bounded common-junction strategies within supplied, fixed geometry.

These are unverified route candidates, never layout changes or saved pins.
The normal source/contact/global acceptance paths decide whether they work.
"""
import itertools
import math
from collections import Counter

from .kinematics import FACE_AXES, dimensions
from .engineering_conditions import effective_net, planning_wall


def _entry_face(design,net):
    ports=[f for f in design.features if f.kind=='port' and not f.suppressed]
    own=[f for f in ports if f.id in net.members]
    return own[0].face if own else min(Counter(f.face for f in ports),key=lambda face:(-sum(p.face==face for p in ports),face))


def _axis_mask(design,net,definitions,threads,modifiers):
    from .cavity_access import cavity_terminal_candidates
    candidates=cavity_terminal_candidates(design,net,definitions,threads,modifiers)
    groups={}
    for member,bore in candidates.items():groups.setdefault(FACE_AXES[bore.face][2],[]).append(member)
    if not groups:return 0
    by_id={f.id:f for f in design.features}
    def weight(members):
        depths=[max(p.end for p in definitions[by_id[m.split(':')[0]].definition].cutting_primitives or
                    definitions[by_id[m.split(':')[0]].definition].stages) for m in members]
        return len(members),sum(depths)
    chosen=max(groups,key=lambda axis:(weight(groups[axis]),-axis))
    return sum(1<<i for i,m in enumerate(sorted(net.members)) if m in groups[chosen])


def face_window_points(design,net,definitions,threads,modifiers):
    """Full source cylinders in face-open windows, preserving their offsets.

    This is an internal turn in the assigned opening, not deep-end eligibility
    or an exception for protected machining. Every interval from the actual
    face to the turn must contain the full inscribed fluid cylinder.
    """
    from .routing import _manufacturing_cuts
    from .cavity_access import _axis_core
    from .kinematics import pose
    by_id={f.id:f for f in design.features};radius=net.diameter/2;result={}
    for member in net.members:
        owner,_,zone_id=member.partition(':');source=by_id.get(owner)
        if not zone_id or source is None or not source.definition or source.direction:continue
        definition=definitions[source.definition]
        zone=next((z for z in definition.zones if z.id==zone_id),None)
        if zone is None or abs(zone.start)>1e-7 or zone.end-zone.start<2*radius+.2 or zone.diameter/2<radius:continue
        angle=math.radians(source.rotation)
        axis=source.model_copy(update=dict(u=source.u+zone.offset_u*math.cos(angle)-zone.offset_v*math.sin(angle),
            v=source.v+zone.offset_u*math.sin(angle)+zone.offset_v*math.cos(angle)))
        depth=zone.end-radius-.1;high=depth+radius
        cuts=list(_manufacturing_cuts(source,definitions,threads,modifiers))
        breaks=sorted({0.,high,*(x for c in cuts for x in (c['start'],c['end']) if 0<x<high)})
        if not all(any(c['start']<=a and c['end']>=b and min(_axis_core(c,a,axis),_axis_core(c,b,axis))>=radius
                       for c in cuts) for a,b in zip(breaks,breaks[1:])):continue
        origin,direction=pose(axis,design.block)
        result[member]=tuple(origin[i]+direction[i]*depth for i in range(3))
    return result


def junction_sites(design,net,definitions,threads,modifiers):
    from .routing import terminal_points,_manufacturing_cuts,cylinder_bounds
    from .closure_runtime import bind_route
    from .schema import Feature
    ports=[f for f in design.features if f.kind=='port' and not f.suppressed]
    if not ports:return []
    points=terminal_points(design,definitions)
    if any(m not in points for m in net.members):return []
    own=[f for f in ports if f.id in net.members]
    face=_entry_face(design,net)
    u,v,axis,_=FACE_AXES[face];sizes=dimensions(design.block)
    axis_values=[points[m][axis] for m in net.members]
    anchors=tuple(dict.fromkeys((sum(axis_values)/len(axis_values),min(axis_values)+net.diameter,max(axis_values)-net.diameter)))
    if own:
        lanes=[sum(f.u for f in own)/len(own)];height=sum(f.v for f in own)/len(own)
    else:
        entries=[p for p in ports if FACE_AXES[p.face][2]==axis]
        if not entries:return []
        height=sum(p.v for p in entries)/len(entries)
        probe=bind_route(design,[Feature(id='BRANCH_SPACE',kind='drilling',face=face,u=sizes[u]/2,v=height,
            depth=max(20,net.diameter*3),diameter=net.diameter,circuit=net.id,route_net=net.id,plugged=True)])[0]
        radius=max(probe.clearance_diameter,net.diameter)/2
        gap=design.rules.minimum_access_gap
        wall=planning_wall(design,net,definitions)
        # Actual functional entries reserve their fitting/entry footprints.
        intervals=[(p.u-(max(p.diameter or 0,p.clearance_diameter)/2+radius+gap),
                    p.u+(max(p.diameter or 0,p.clearance_diameter)/2+radius+gap)) for p in entries]
        source_edge=max((cylinder_bounds(c['feature'],design.block,c['start'],c['end'],
                         2*max(c['radius_start'],c['radius_end']))[u][1]
                        for f in design.features if f.kind=='cavity' for c in _manufacturing_cuts(f,definitions,threads,modifiers)),default=0)
        starts=[hi for _,hi in intervals]+[source_edge+net.diameter+wall]
        sites={}
        for start in starts:
            for i in range(8):
                coordinate=start+i*(2*radius+gap)
                if not radius+wall<=coordinate<=sizes[u]-radius-wall:continue
                if coordinate<source_edge+net.diameter+wall:continue
                if any(lo+1e-6<coordinate<hi-1e-6 for lo,hi in intervals):continue
                sites[round(coordinate,6)]=coordinate
        lanes=[]
        for site in sorted(sites.values()):
            if not lanes or site-lanes[-1]>=2*radius+gap-1e-6:lanes.append(site)
        if not lanes:return []
        # Allocate candidate ordering, not geometry. Deep-only branches get an
        # early free corridor; multi-terminal branches retain independent lanes.
        peers=[effective_net(design,n) for n in design.nets if n.routing=='automatic' and
               len(n.members)>=2 and not any(p.id in n.members for p in ports)]
        peers.sort(key=lambda n:(not bool(_axis_mask(design,n,definitions,threads,modifiers)),-len(n.members),n.id))
        index=next((i for i,n in enumerate(peers) if n.id==net.id),0)
        preferred=lanes[min(index,len(lanes)-1)]
        lanes=[preferred,*sorted((s for s in lanes if s!=preferred),key=lambda s:(abs(s-preferred),s))][:3]
    result=[]
    for lane in lanes:
        for anchor in anchors:
            point=[0.,0.,0.];point[u]=lane;point[v]=height;point[axis]=anchor
            if all(0<x<size for x,size in zip(point,sizes)):result.append(tuple(point))
    return result


def terminal_branch_candidates(design,net,definitions,threads,modifiers,cache=None):
    from .routing import _fixed_strategy_source,route_from_variant
    source=_fixed_strategy_source(design)
    # Preserve the established small external-port/cavity routing shortlist.
    if len(net.members)<3 and (sum(f.kind=='cavity' for f in source.features)<3 or
            any(f.kind=='port' and f.id in net.members for f in source.features)):return
    sites=junction_sites(source,net,definitions,threads,modifiers)
    if not sites:return
    mask=_axis_mask(source,net,definitions,threads,modifiers)
    # First expose different trunk lanes, then different anchors. The family
    # has twelve raw attempts and uses the unchanged final exact shortlist.
    face=_entry_face(source,net)
    axis=FACE_AXES[face][2];u,v,_,_=FACE_AXES[face]
    orders=[o for o in ((u,axis,v),(u,v,axis)) if net.preferred_axis=='auto' or o[0]=='xyz'.index(net.preferred_axis)]
    primary=sites[:3]
    primary.extend(next(p for p in sites if p[u]==lane) for lane in dict.fromkeys(p[u] for p in sites) if lane!=sites[0][u])
    # A source-station-derived second plane can avoid a shared-height trunk.
    from .routing import terminal_points
    points=terminal_points(source,definitions);station=[points[m][v] for m in net.members]
    margin=net.diameter+planning_wall(source,net,definitions)
    for coordinate in (max(station)+margin,min(station)-margin):
        if margin<coordinate<dimensions(source.block)[v]-margin:
            point=list(sites[0]);point[v]=coordinate;primary.append(tuple(point));break
    windows=face_window_points(source,net,definitions,threads,modifiers)
    modes=([False,True] if windows else [False])
    samples=[(window,point,order) for window in modes for point,order in itertools.product(primary[:3] if windows else primary[:6],orders)]
    seen=set()
    for window,point,order in samples[:12]:
        entry=net.entry_preference
        if entry=='nearest' and order==orders[-1]:entry='negative'
        key=('window:' if window else '')+f'branch_{mask}_'+ '_'.join(f'{x:.6f}' for x in point)+':'+''.join('xyz'[i] for i in order)+':'+entry
        if key in seen:continue
        seen.add(key)
        route=route_from_variant(source,net,key,definitions,threads,modifiers,obstruction_cache=cache)
        if route is not None:yield key,route
