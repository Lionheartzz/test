"""Deterministic disjunctive difference-constraint placement, without a grid.

Every shared rigid source has ONE origin variable per axis. Corridor equalities,
source/stock bounds and measured separations propagate through the same graph.
A contradictory graph rejects that selected sufficient domain, not the Design.
"""
from dataclasses import dataclass
import itertools
from ..kinematics import FACE_AXES, dimensions, pose
from ..routing import terminal_points
from .initialization import source_extents


class DifferenceSystem:
    def __init__(self):self.edges=[];self.variables={'ZERO'}
    def lower(self,x,y,c,reason):
        self.variables.update((x,y));self.edges.append((y,x,float(c),reason))
    def equal(self,x,y,c,reason):
        self.lower(x,y,c,reason);self.lower(y,x,-c,reason)
    def bounds(self,x,lo,hi,reason):
        self.lower(x,'ZERO',lo,reason);self.lower('ZERO',x,-hi,reason)
    def solve(self):
        values={v:0. for v in self.variables};parent={};updated=None
        for _ in range(len(values)):
            updated=None
            for a,b,c,reason in self.edges:
                if values[b]+1e-8<values[a]+c:
                    values[b]=values[a]+c;parent[b]=(a,reason);updated=b
            if updated is None:
                zero=values['ZERO'];return {k:v-zero for k,v in values.items()},[]
        for _ in values:updated=parent[updated][0]
        at=updated;reasons=[]
        while not reasons or at!=updated:
            at,reason=parent[at];reasons.append(reason)
        return None,reasons

    def intervals(self):
        """Exact variable projections of this selected difference domain."""
        def distances(reverse):
            edges=[(b,a,c) if reverse else (a,b,c) for a,b,c,_ in self.edges]
            values={v:float('-inf') for v in self.variables};values['ZERO']=0.
            for _ in self.variables:
                changed=False
                for a,b,c in edges:
                    if values[a]!=float('-inf') and values[b]+1e-8<values[a]+c:
                        values[b]=values[a]+c;changed=True
                if not changed:break
            return values
        lo,hi=distances(False),distances(True)
        return {v:[None if lo[v]==float('-inf') else lo[v],None if hi[v]==float('-inf') else -hi[v]] for v in sorted(self.variables)}


@dataclass(frozen=True)
class Separation:
    high: str
    low: str
    distance: float
    reason: dict


class PlacementSolver:
    def __init__(self,engineering):
        self.e=engineering
        self.fi={r['feature']:i for i,r in enumerate(engineering.features)}
        self.ni={r['net']:i for i,r in enumerate(engineering.nets)}
        self.profile_access={}
    def origin(self,f,a):return f'F{self.fi[f]}.{a}'
    def lane(self,n,a):return f'N{self.ni[n]}.{a}'

    def solve(self, plans, *, poses=None, separations=(), preserve=False,dimension_floor=(),release=(),release_axes=None,
              working=None,fixed_junctions=None,use_projected=False):
        e=self.e;d=(working or e.source).model_copy(deep=True);domain=e.domain
        for f in d.features:
            if poses and f.id in poses:f.face,f.rotation=poses[f.id]
        s=DifferenceSystem();sizes=dimensions(d.block)
        for a,size in enumerate(sizes):
            lo=(d.constraints.envelope_min or (1,)*3)[a];hi=(d.constraints.envelope_max or (2000,)*3)[a]
            if dimension_floor:lo=max(lo,dimension_floor[a])
            s.bounds(f'D{a}',lo if a in domain.dimension_axes and not preserve else size,
                     hi if a in domain.dimension_axes and not preserve else size,dict(rule='BLOCK_BOUND',axis=a))
        for f in d.features:
            if f.suppressed or f.route_net:continue
            r=source_extents(d,f,e.definitions,e.threads,e.modifiers);u,v,normal,sign=FACE_AXES[f.face]
            for a in range(3):
                var=self.origin(f.id,a)
                if a==normal:s.equal(var,'ZERO' if sign>0 else f'D{a}',0,dict(rule='MOUNTING_FACE',feature=f.id,axis=a))
                else:
                    origin=pose(f,d.block)[0][a]
                    low=min([-r['radius']]+[b[a][0]-origin for b in r['bounds']])-r['wall']
                    high=max([r['radius']]+[b[a][1]-origin for b in r['bounds']])+r['wall']
                    if use_projected:low,high=r['projected_supports'][a][0]-r['wall'],r['projected_supports'][a][1]+r['wall']
                    s.lower(var,'ZERO',-low,dict(rule='SOURCE_EDGE_LOW',feature=f.id,axis=a))
                    s.lower(f'D{a}',var,high,dict(rule='SOURCE_EDGE_HIGH',feature=f.id,axis=a))
                    field='u' if a==u else 'v';locks=domain.fixed_positions.get(f.id,{})
                    fixed=locks.get(field,locks.get('xyz'[a]))
                    if preserve or f.id not in domain.movable or release and f.id not in release:fixed=getattr(f,field)
                    if release_axes and a not in release_axes.get(f.id,()):fixed=getattr(f,field)
                    if fixed is not None:s.equal(var,'ZERO',fixed,dict(
                        rule='SOFT_SEED_POSITION' if preserve and f.id in domain.movable and
                            field not in locks and 'xyz'[a] not in locks else 'AUTHORED_POSITION',feature=f.id,axis=a))
            s.lower(f'D{normal}','ZERO',r['depth']+r['wall'],dict(rule='SOURCE_DEPTH',feature=f.id,axis=normal))
        points=terminal_points(d,e.definitions);by_id={f.id:f for f in d.features};nr={r['net']:r for r in e.nets}
        # Opposite machining depths share thickness ONLY where their actual
        # transverse projections overlap. Disjoint columns need max(depth),
        # not an unconditional top + bottom sum. Recheck after coordinates move.
        for a,b in itertools.combinations([f for f in d.features if not f.route_net and not f.suppressed],2):
            normal,sign=FACE_AXES[a.face][2:]
            if FACE_AXES[b.face][2:]!=(normal,-sign):continue
            ra=source_extents(d,a,e.definitions,e.threads,e.modifiers)
            rb=source_extents(d,b,e.definitions,e.threads,e.modifiers)
            axes=[v for v in range(3) if v!=normal]
            if any(all(x[v][1]>=y[v][0] and y[v][1]>=x[v][0] for v in axes) for x in ra['bounds'] for y in rb['bounds']):
                from ..engineering_conditions import required_wall
                wall=required_wall(d,a,b,definitions=e.definitions)
                s.lower(f'D{normal}','ZERO',ra['depth']+rb['depth']+wall,
                    dict(rule='OVERLAPPING_OPPOSITE_DEPTHS',features=[a.id,b.id],axis=normal,
                        depths=[ra['depth'],rb['depth']],wall=wall,source='actual machining projections'))
        # Reserve branches before choosing source coordinates. Sources sharing
        # a radial approach axis occupy different transverse source columns;
        # otherwise a full external drilling can cross an intervening cavity.
        # This is one sufficient process domain, not a universal prohibition.
        for a,b in itertools.combinations([f for f in d.features if f.kind=='cavity' and not f.suppressed],2):
            aa={order[0] for p in plans.values() if p.reserve_columns and p.access not in ('coaxial','aligned-window') for m,order in p.orders if m.split(':')[0]==a.id}
            bb={order[0] for p in plans.values() if p.reserve_columns and p.access not in ('coaxial','aligned-window') for m,order in p.orders if m.split(':')[0]==b.id}
            common=aa&bb
            if not common:continue
            approach=min(common);normal=FACE_AXES[a.face][2]
            candidates=[i for i in range(3) if i!=approach and i not in (FACE_AXES[a.face][2],FACE_AXES[b.face][2])]
            if not candidates:continue
            axis=candidates[0]
            low,high=sorted((a,b),key=lambda f:(pose(f,d.block)[0][axis],self.fi[f.id]))
            ra=source_extents(d,low,e.definitions,e.threads,e.modifiers)
            rb=source_extents(d,high,e.definitions,e.threads,e.modifiers)
            spacing=ra['radius']+rb['radius']+max(ra['wall'],rb['wall'],d.rules.minimum_access_gap)
            if use_projected:spacing=ra['projected_supports'][axis][1]-rb['projected_supports'][axis][0]+max(ra['wall'],rb['wall'],d.rules.minimum_access_gap)
            s.lower(self.origin(high.id,axis),self.origin(low.id,axis),spacing,
                dict(rule='RADIAL_BRANCH_SOURCE_COLUMNS',features=[low.id,high.id],axis=axis,approach_axis=approach,required=spacing,
                    nets=[n for n,p in plans.items() if p.reserve_columns and p.access not in ('coaxial','aligned-window') and
                          any(m.split(':')[0] in (a.id,b.id) for m,o in p.orders)]))
        groups={}
        for name,p in plans.items():
            if p.layer_axis is not None:groups.setdefault((p.spine_axis,p.layer_axis),[]).append(name)
        for (spine,axis),names in groups.items():
            names.sort(key=lambda n:(sum(points[m][axis] for m in nr[n]['members'])/len(nr[n]['members']),self.ni[n]))
            for low,high in zip(names,names[1:]):
                entry=lambda n:max(nr[n]['diameter'],(nr[n].get('closure') or {}).get('entry_diameter',0))
                gap=(entry(low)+entry(high))/2+max(nr[low]['wall'],nr[high]['wall'],d.rules.minimum_access_gap)
                s.lower(self.lane(high,axis),self.lane(low,axis),gap,
                    dict(rule='TRUNK_LAYER_RESERVATION',nets=[low,high],axis=axis,required=gap))
                escape=3-spine-axis
                s.lower(self.lane(high,escape),self.lane(low,escape),gap,
                    dict(rule='BRANCH_CORRIDOR_RESERVATION',nets=[low,high],axis=escape,required=gap))
            for source in (f for f in d.features if f.kind=='cavity' and FACE_AXES[f.face][2]==axis):
                owned=[(name,m) for name in names for m in nr[name]['members'] if m.split(':')[0]==source.id]
                owned.sort(key=lambda item:(points[item[1]][axis],self.ni[item[0]]))
                for (low,lm),(high,hm) in zip(owned,owned[1:]):
                    if low==high:continue
                    escape=3-spine-axis
                    entry=lambda n:max(nr[n]['diameter'],(nr[n].get('closure') or {}).get('entry_diameter',0))
                    gap=(entry(low)+entry(high))/2+max(nr[low]['wall'],nr[high]['wall'],d.rules.minimum_access_gap)
                    s.lower(self.lane(high,escape),self.lane(low,escape),gap,
                        dict(rule='SHARED_WINDOW_ESCAPE_ORDER',nets=[low,high],feature=source.id,
                             terminals=[lm,hm],axis=escape,required=gap))
        for name,p in plans.items():
            row=nr[name];r=row['diameter']/2;wall=row['wall'];margin=r+wall
            if row.get('closure') and p.access!='coaxial':
                margin=max(margin,row['closure']['occupied_depth']+r+wall,row['closure']['entry_diameter']/2+wall)
            from ..routing import port_turn_depth
            from ..engineering_conditions import effective_net
            net=effective_net(d,next(n for n in d.nets if n.id==name))
            from ..branch_candidates import face_window_points
            approach_points={**points,**face_window_points(d,net,e.definitions,e.threads,e.modifiers)}
            for member in row['members']:
                source=by_id[member.split(':')[0]]
                if source.kind=='port':
                    depth=port_turn_depth(d,net,source,e.definitions,'window',e.threads,e.modifiers)
                    if depth is None:depth=port_turn_depth(d,net,source,e.definitions,'clear',e.threads,e.modifiers)
                    origin,direction=pose(source,d.block)
                    approach_points[member]=tuple(origin[a]+direction[a]*depth for a in range(3))
            for a in range(3):
                var=self.lane(name,a)
                s.lower(var,'ZERO',margin,dict(rule='CORRIDOR_EDGE_LOW',net=name,axis=a))
                s.lower(f'D{a}',var,margin,dict(rule='CORRIDOR_EDGE_HIGH',net=name,axis=a))
            anchors=[m for m in row['members'] if not (m in p.axial_members and FACE_AXES[by_id[m.split(':')[0]].face][2]==p.spine_axis)]
            anchor_member=min(anchors or row['members'],key=lambda m:(by_id[m.split(':')[0]].kind!='cavity',
                FACE_AXES[by_id[m.split(':')[0]].face][2]==p.spine_axis,row['members'].index(m)))
            anchor=by_id[anchor_member.split(':')[0]];a=p.spine_axis
            offset=approach_points[anchor_member][a]-pose(anchor,d.block)[0][a]
            if anchors:s.equal(self.lane(name,a),self.origin(anchor.id,a),offset,
                               dict(rule='SPINE_TERMINAL_ANCHOR',net=name,member=anchor_member,axis=a))
            for member,order in p.orders:
                f=by_id[member.split(':')[0]];origin=pose(f,d.block)[0];offset=[approach_points[member][a]-origin[a] for a in range(3)]
                if p.access in ('coaxial','aligned-window'):
                    for a in range(3):
                        if a!=p.spine_axis:s.equal(self.lane(name,a),self.origin(f.id,a),offset[a],
                            dict(rule='COAXIAL_WINDOW_ALIGNMENT',net=name,member=member,axis=a))
                    if p.access=='aligned-window' and row.get('closure'):
                        ext=source_extents(d,f,e.definitions,e.threads,e.modifiers)
                        support=max(abs(x) for x in ext['projected_supports'][p.spine_axis]) if use_projected else ext['radius']
                        clearance=support+row['closure']['occupied_depth']+wall
                        if p.entry!='positive':s.lower(self.origin(f.id,p.spine_axis),'ZERO',clearance,
                            dict(rule='DIRECT_WINDOW_ENTRY',net=name,member=member,axis=p.spine_axis))
                        if p.entry!='negative':s.lower(f'D{p.spine_axis}',self.origin(f.id,p.spine_axis),clearance,
                            dict(rule='DIRECT_WINDOW_ENTRY',net=name,member=member,axis=p.spine_axis))
                    continue
                if member in p.axial_members:
                    profile=self.profile_access[member];normal=FACE_AXES[f.face][2];sign=FACE_AXES[f.face][3]
                    head=profile['plug_length']+r+wall;stop=-profile['depth_minus_stock']+r+wall
                    s.lower(self.lane(name,normal),'ZERO',head if sign<0 else stop,
                        dict(rule='SOURCE_BACKED_AXIAL_INTERVAL',net=name,member=member,axis=normal,side='lower'))
                    s.lower(f'D{normal}',self.lane(name,normal),stop if sign<0 else head,
                        dict(rule='SOURCE_BACKED_AXIAL_INTERVAL',net=name,member=member,axis=normal,side='upper'))
                first=order[0];ext=source_extents(d,f,e.definitions,e.threads,e.modifiers)
                if row.get('closure') and member not in p.axial_members:
                    support=max(abs(x) for x in ext['projected_supports'][first]) if use_projected else ext['radius']
                    entry=support+row['closure']['occupied_depth']+wall
                    if p.entry!='positive':s.lower(self.origin(f.id,first),'ZERO',entry,
                        dict(rule='RADIAL_ENTRY_PLUG_RESERVATION',net=name,member=member,axis=first,side='negative',required=entry))
                    if p.entry!='negative':s.lower(f'D{first}',self.origin(f.id,first),entry,
                        dict(rule='RADIAL_ENTRY_PLUG_RESERVATION',net=name,member=member,axis=first,side='positive',required=entry))
                # Real source radial bounds determine where a branch can turn;
                # this reservation never authorizes crossing protected machining.
                reach=max(ext['radius'],max((max(abs(b[first][0]-origin[first]),abs(b[first][1]-origin[first])) for b in ext['bounds']),default=0))+max(r,(row.get('closure') or {}).get('entry_diameter',0)/2)+max(wall,d.rules.minimum_access_gap)
                if use_projected:reach=max(abs(x) for x in ext['projected_supports'][first])+max(r,(row.get('closure') or {}).get('entry_diameter',0)/2)+max(wall,d.rules.minimum_access_gap)
                if p.side>0:s.lower(self.lane(name,first),self.origin(f.id,first),reach,dict(rule='BRANCH_CLEAR_SOURCE',net=name,member=member,axis=first))
                else:s.lower(self.origin(f.id,first),self.lane(name,first),reach,dict(rule='BRANCH_CLEAR_SOURCE',net=name,member=member,axis=first))
                if p.planar and member not in p.axial_members:
                    # All branches of a planar trunk must share its third
                    # coordinate. Inconsistent rigid windows cause backtracking.
                    a=next(a for a in range(3) if a not in (first,p.spine_axis)) if first!=p.spine_axis else order[-1]
                    s.equal(self.lane(name,a),self.origin(f.id,a),offset[a],dict(rule='WINDOW_LAYER',net=name,member=member,axis=a))
        for cut in separations:s.lower(cut.high,cut.low,cut.distance,cut.reason)
        for name,point in (fixed_junctions or {}).items():
            if name in plans:
                for a in range(3):s.equal(self.lane(name,a),'ZERO',point[a],dict(rule='UNCHANGED_PROCESS_JUNCTION',net=name,axis=a))
        values,cycle=s.solve()
        if values is None:return None,dict(status='SELECTED_DOMAIN_CONTRADICTION',cycle=cycle,physical_infeasibility_proven=False)
        for a,name in enumerate(('length','width','height')):setattr(d.block,name,values[f'D{a}'])
        for f in d.features:
            if f.id not in self.fi:continue
            u,v,_,_=FACE_AXES[f.face];f.u=values[self.origin(f.id,u)];f.v=values[self.origin(f.id,v)]
        if not domain.accepts(e.source,d):return None,dict(status='HARD_OWNERSHIP_REJECTED',physical_infeasibility_proven=False)
        junctions={n:tuple(values[self.lane(n,a)] for a in range(3)) for n in plans}
        return (d,junctions),dict(status='CONSTRAINT_DOMAIN_SOLVED_NOT_ADMITTED',values=values,
            coordinate_domains=s.intervals(),
            constraints=[dict(high=b,low=a,distance=c,cause=r) for a,b,c,r in s.edges],
            preserve_sources=preserve,physical_infeasibility_proven=False)
