"""One constructive, hypergraph-guided source arrangement for new Generate.

Boundary events are measured supports of rigid machining/installation bodies.
They are a sufficient packing seed, not a collision verdict or a layout search
portfolio. The production source and drilling gates must still accept it.
"""
import itertools
import math

from .. import timing
from ..kinematics import FACE_AXES,dimensions,pose
from ..engineering_conditions import required_wall
from ..routing import terminal_points
from .initialization import source_extents


def arrange(work):
    e=work.e;d=work.design;domain=e.domain;index=work.solver.fi
    sources=[f for f in d.features if not f.suppressed and not f.route_net]
    associations=e.associations()
    links={f.id:{} for f in sources}
    for row in associations:
        a,b=row['features'];links[a][b]=row['weight'];links[b][a]=row['weight']
    facts={};pose_facts={}
    def profile(f,face,rotation):
        key=(f.id,face,rotation)
        if key not in pose_facts:
            g=f.model_copy(update=dict(face=face,rotation=rotation));o,_=pose(g,d.block)
            r=source_extents(d,g,e.definitions,e.threads,e.modifiers)
            bounds=[(min(b[a][0]-o[a] for b in r['bounds']),max(b[a][1]-o[a] for b in r['bounds'])) for a in range(3)]
            u,v,n,sign=FACE_AXES[face]
            definition=e.definitions.get(g.definition)
            height=max([definition.clearance_height,*[b.height for b in definition.boundaries]]) if definition else g.clearance_height
            # A support box includes the declared installation body OUTSIDE
            # the block, not a fictitious cylinder through the source depth.
            installed={a:r['projected_supports'][a] for a in (u,v)}
            installed[n]=(-height,0.) if sign>0 else (0.,height)
            box=[(min(bounds[a][0],installed[a][0]),max(bounds[a][1],installed[a][1])) for a in range(3)]
            points=terminal_points(d.model_copy(update=dict(features=[g])),e.definitions)
            offsets={m:tuple(p[a]-o[a] for a in range(3)) for m,p in points.items()}
            pose_facts[key]=(g,r,box,offsets)
        return pose_facts[key]
    for f in sources:facts[f.id]=profile(f,f.face,f.rotation)
    def priority(f):
        _,r,_,_=facts[f.id]
        return (f.id in domain.movable,-len(domain.fixed_positions.get(f.id,{}))-int(f.id in domain.fixed_faces),
            -sum(links[f.id].values()),-len(next(x for x in e.features if x['feature']==f.id)['windows']),
            -math.prod(r['planar_spans'].values()),index[f.id])
    remaining=sorted(sources,key=priority);placed=[];chosen={};decisions=[]
    lower=d.constraints.envelope_min or (1,1,1);upper=d.constraints.envelope_max or (2000,2000,2000)
    sizes=[lower[a] if a in domain.dimension_axes else dimensions(d.block)[a] for a in range(3)]
    def origin(g,stock):
        u,v,n,sign=FACE_AXES[g.face];o=[0.,0.,0.];o[u]=g.u;o[v]=g.v;o[n]=0 if sign>0 else stock[n];return o
    def world(g,box,stock):
        o=origin(g,stock);return [(o[a]+box[a][0],o[a]+box[a][1]) for a in range(3)]
    def rotations(f):
        if f.id in domain.fixed_rotations:return (domain.fixed_rotations[f.id],)
        if f.id not in domain.movable:return (f.rotation,)
        definition=e.definitions.get(f.definition)
        if not definition:return (f.rotation,)
        # Only distinct engineering projections: a rectangle/window footprint
        # can align its principal span with the other face coordinate.
        asymmetric=any(z.offset_u or z.offset_v for z in definition.zones) or any(not b.circle for b in definition.boundaries)
        return tuple(dict.fromkeys((f.rotation,(f.rotation+90)%360))) if asymmetric else (f.rotation,)
    with timing.phase('single.face_placement'):
        while remaining:
            # Closely coupled rigid sources are placed next, not every source
            # in the transitive connected component along the same line.
            f=min(remaining,key=lambda f:(f.id in domain.movable,
                -len(domain.fixed_positions.get(f.id,{}))-int(f.id in domain.fixed_faces),
                -sum(links[f.id].get(g.id,0) for g in placed),priority(f)))
            remaining.remove(f);candidates=[]
            for face,rotation in itertools.product(domain.faces(f),rotations(f)):
                g,r,box,offsets=profile(f,face,rotation);u,v,n,sign=FACE_AXES[face]
                # Plan the directly coupled installation area BEFORE inserting
                # the next centre. Otherwise incremental minimum-volume packing
                # irrevocably builds a strip: its first three placements leave
                # no compact two-dimensional fourth position. This is a soft
                # completion estimate, not a row count, grid or hard face quota.
                neighbours=[h for h in [f,*remaining] if h.kind=='cavity' and
                    (h.id==f.id or h.id in links[f.id]) and face in domain.faces(h)]
                spans=[profile(h,face,rotation if h.id==f.id else rotations(h)[0])[1]['planar_spans'] for h in neighbours]
                area=sum((s[u]+d.rules.minimum_access_gap)*(s[v]+d.rules.minimum_access_gap) for s in spans)
                aspect=sum(s[u]/max(1e-7,s[v]) for s in spans)/len(spans) if spans else 1.
                completion={u:math.sqrt(area*aspect),v:math.sqrt(area/aspect)}
                stock=list(sizes);stock[n]=max(stock[n],r['depth']+r['wall']) if n in domain.dimension_axes else stock[n]
                if r['depth']+r['wall']>stock[n]+1e-7:continue
                for a in (u,v):
                    need=r['projected_supports'][a][1]-r['projected_supports'][a][0]+2*r['wall']
                    if a in domain.dimension_axes:stock[a]=max(stock[a],need)
                coordinates={a:{-r['projected_supports'][a][0]+r['wall']} for a in (u,v)}
                for other in placed:
                    ob=world(other,chosen[other.id][2],stock)
                    gap=max(d.rules.minimum_access_gap,required_wall(d,f,other,definitions=e.definitions))
                    oo=origin(other,stock)
                    for a in (u,v):
                        coordinates[a].update((oo[a],ob[a][1]+gap-box[a][0],ob[a][0]-gap-box[a][1]))
                    # Align actual windows when they share a Net, not just
                    # their feature origins or names.
                    for row in e.nets:
                        own=[m for m in row['members'] if m in offsets]
                        others=[m for m in row['members'] if m in chosen[other.id][3]]
                        for m,k in itertools.product(own,others):
                            for a in (u,v):coordinates[a].add(oo[a]+chosen[other.id][3][k][a]-offsets[m][a])
                locks=domain.fixed_positions.get(f.id,{})
                for a,field in ((u,'u'),(v,'v')):
                    value=locks.get(field,locks.get('xyz'[a]))
                    if f.id not in domain.movable:value=getattr(f,field)
                    if value is not None:coordinates[a]={value}
                for x,y in itertools.product(sorted(coordinates[u]),sorted(coordinates[v])):
                    if x+r['projected_supports'][u][0]<r['wall']-1e-7 or y+r['projected_supports'][v][0]<r['wall']-1e-7:continue
                    target=g.model_copy(update=dict(u=x,v=y));need=list(stock)
                    for a,value in ((u,x),(v,y)):
                        bound=value+r['projected_supports'][a][1]+r['wall']
                        if a in domain.dimension_axes:need[a]=max(need[a],bound)
                        elif bound>need[a]+1e-7:break
                    else:
                        if any(need[a]>upper[a]+1e-7 for a in range(3)):continue
                        if not domain.position_matches(target,d.block.model_copy(update=dict(zip(('length','width','height'),need)))):continue
                        wb=world(target,box,need)
                        blocked=False
                        for other in placed:
                            ob=world(other,chosen[other.id][2],need)
                            gap=max(d.rules.minimum_access_gap,required_wall(d,target,other,definitions=e.definitions))
                            if all(wb[a][1]+gap>ob[a][0]+1e-7 and ob[a][1]+gap>wb[a][0]+1e-7 for a in range(3)):
                                # Same-face round/rectangular supports may be
                                # narrower than this conservative combined box.
                                blocked=True;break
                        if blocked:continue
                        # Growth can move negative-face sources toward a fixed
                        # source: recheck ALL placed pairs at the new stock.
                        for a,b in itertools.combinations(placed,2):
                            aa,bb=world(a,chosen[a.id][2],need),world(b,chosen[b.id][2],need)
                            gap=max(d.rules.minimum_access_gap,required_wall(d,a,b,definitions=e.definitions))
                            if all(aa[k][1]+gap>bb[k][0]+1e-7 and bb[k][1]+gap>aa[k][0]+1e-7 for k in range(3)):blocked=True;break
                        if blocked:continue
                        o=origin(target,need);length=0.;turns=0.
                        for other in placed:
                            weight=links[f.id].get(other.id,0)
                            if not weight:continue
                            oo=origin(other,need)
                            for row in e.nets:
                                own=[m for m in row['members'] if m in offsets];ends=[m for m in row['members'] if m in chosen[other.id][3]]
                                for m,k in itertools.product(own,ends):
                                    delta=[abs(o[a]+offsets[m][a]-oo[a]-chosen[other.id][3][k][a]) for a in range(3)]
                                    length+=weight*sum(delta)*row['diameter']**2
                                    turns+=weight*max(0,sum(v>1e-6 for v in delta)-1)*row['diameter']**3
                        pref=domain.soft_faces.get(f.id) or f.face
                        estimate=list(need)
                        for a in (u,v):estimate[a]=max(estimate[a],completion[a])
                        # Utility ties must not depend on multiplication order
                        # after permuting equivalent X/Y/Z frames. This rounds
                        # scheduling costs ONLY; coordinates/cuts stay precise.
                        score=(round(math.prod(estimate)+length+turns,8),round(math.prod(need),8),
                            face!=pref,rotation!=f.rotation,tuple(need),tuple(FACE_AXES[face]),x,y)
                        candidates.append((score,target,r,box,offsets,need,dict(
                            directly_coupled_sources=[h.id for h in neighbours],projected_area=area,
                            projected_aspect=aspect,estimated_completion_spans=completion,
                            role='Soft geometric completion estimate; never a hard row count or minimum stock')))
            if not candidates:
                # A conservative seed builder cannot prove physical infeasibility.
                decisions.append(dict(feature=f.id,status='PACKING_DOMAIN_UNCOVERED',allowed_faces=domain.faces(f)))
                return False,decisions
            score,g,r,box,offsets,sizes,allocation=min(candidates,key=lambda row:row[0])
            chosen[f.id]=(g,r,box,offsets);placed.append(g)
            decisions.append(dict(feature=f.id,face=g.face,rotation=g.rotation,u=g.u,v=g.v,dimensions=list(sizes),
                associated_sources=links[f.id],score=list(score[:2]),allowed_faces=domain.faces(f),
                area_allocation=allocation,
                reason='Measured machining/installation supports + shared-window adjacency + required stock and predicted drilling length',
                status='CONSTRUCTIVE_SEED_REQUIRES_PRODUCTION_CHECK'))
    for field,value in zip(('length','width','height'),sizes):setattr(d.block,field,value)
    d.features=[chosen[f.id][0] if f.id in chosen else f for f in d.features]
    return True,decisions
