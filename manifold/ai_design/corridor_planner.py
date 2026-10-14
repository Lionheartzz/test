"""Manufacturing topology BEFORE placement: symbolic external drill corridors.

These are sufficient constraint domains, not an exhaustive machining language.
Only the production Router materializes them; every cut still needs its gates.
"""
from dataclasses import dataclass, replace
import itertools

from ..kinematics import FACE_AXES, dimensions
from ..engineering_conditions import effective_net
from ..routing import propose, port_turn_depth
from ..branch_candidates import face_window_points


@dataclass(frozen=True)
class MachiningPlan:
    net: str
    spine_axis: int
    orders: tuple
    entry: str = 'negative'
    planar: bool = False
    side: int = 1
    access: str = 'window'
    axial_members: tuple = ()
    layer_axis: int | None = None
    entry_axes: tuple = ()
    reserve_columns: bool = True

    def diagnostics(self):
        return dict(net=self.net,spine_axis=self.spine_axis,terminal_orders=dict(self.orders),
                    entry=self.entry,planar=self.planar,side=self.side,access=self.access,
                    axial_members=self.axial_members,layer_axis=self.layer_axis,entry_axes=dict(self.entry_axes),reserve_columns=self.reserve_columns,
                    primitive='production.propose(junction_override, terminal_orders, port_approaches)',
                    status='SYMBOLIC_MANUFACTURING_INTENT_NOT_ADMITTED')


class CorridorPlanner:
    def __init__(self, engineering):
        self.engineering=engineering
        self.profile_access={}
        from ..cavity_access import cavity_terminal_candidates
        from ..closure_runtime import bind_route
        from .initialization import source_extents
        # Profile eligibility is an isolated geometric subproblem, not an
        # approval of today's source placement. An invalid soft scaffold must
        # not erase a genuine source-defined deep-end machining interface.
        for row in engineering.nets:
            net=effective_net(engineering.source,next(n for n in engineering.source.nets if n.id==row['net']))
            for f in engineering.source.features:
                own=[m for m in row['members'] if m.split(':')[0]==f.id]
                if f.kind!='cavity' or not own:continue
                probe=engineering.source.model_copy(deep=True)
                ext=source_extents(probe,f,engineering.definitions,engineering.threads,engineering.modifiers)
                size=max(*dimensions(probe.block),2*(ext['depth']+ext['radius']+ext['wall']+net.diameter))
                for field in ('length','width','height'):setattr(probe.block,field,size)
                source=f.model_copy(update=dict(u=size/2,v=size/2));probe.features=[source]
                selected=cavity_terminal_candidates(probe,net,engineering.definitions,engineering.threads,engineering.modifiers)
                for member,bore in selected.items():
                    bore=bind_route(probe,[bore])[0]
                    self.profile_access[member]=dict(depth_minus_stock=bore.depth-size,
                        plug_length=bore.plug_length,source_profile_only=True,
                        evidence='production.cavity_terminal_candidates isolated source profile')
        self.options={r['net']:self.for_net(r) for r in engineering.nets}
        # Most constrained access domain and rigid coupling FIRST, never Net ID.
        order={r['net']:i for i,r in enumerate(engineering.nets)}
        self.order=sorted(self.options,key=lambda n:(len(self.options[n]),
             -len(next(r for r in engineering.nets if r['net']==n)['coupled_nets']),order[n]))

    def for_net(self, row, design=None):
        e=self.engineering;d=design or e.source;by_id={f.id:f for f in d.features}
        result=[]
        members=[by_id.get(m.split(':')[0]) for m in row['members']]
        if members and all(f is not None and f.kind=='port' and not f.direction for f in members) and len({FACE_AXES[f.face][2] for f in members})==1:
            axis=FACE_AXES[members[0].face][2]
            result.append(MachiningPlan(row['net'],axis,tuple((m,(axis,*[a for a in range(3) if a!=axis])) for m in row['members']),access='coaxial'))
        if members and all(f is not None and f.kind=='cavity' and not f.direction for f in members):
            wide=all(any(z.id==m.partition(':')[2] and z.end-z.start>=row['diameter']+.2 and z.diameter>=row['diameter']
                         for z in e.definitions[f.definition].zones) for m,f in zip(row['members'],members))
            if wide:
                for axis in range(3):
                    if all(FACE_AXES[f.face][2]!=axis for f in members):
                        result.append(MachiningPlan(row['net'],axis,tuple((m,(axis,*[a for a in range(3) if a!=axis]))
                            for m in row['members']),access='aligned-window'))
        for spine in range(3):
            if all(FACE_AXES[f][2]!=spine for f in FACE_AXES if f not in d.constraints.forbidden_drilling_faces):continue
            orders=[]
            axial=[]
            for m in row['members']:
                f=by_id.get(m.split(':')[0])
                if f is None or f.direction:return []
                normal=FACE_AXES[f.face][2]
                opposite=next(face for face,v in FACE_AXES.items() if v[2]==normal and v[3]==-FACE_AXES[f.face][3])
                if m in self.profile_access and opposite not in d.constraints.forbidden_drilling_faces:axial.append(m)
                radial=[a for a in range(3) if a!=normal]
                first=next((a for a in radial if a!=spine),radial[0])
                order=(first,*[a for a in range(3) if a not in (first,spine)],spine) if first!=spine else (first,*[a for a in range(3) if a!=first])
                orders.append((m,order))
            for planar in (True,False):
                normals=[FACE_AXES[by_id[m.split(':')[0]].face][2] for m in row['members'] if by_id[m.split(':')[0]].kind=='cavity']
                layer=min((a for a in range(3) if a!=spine),key=lambda a:(-normals.count(a),a))
                result.append(MachiningPlan(row['net'],spine,tuple(orders),planar=planar,
                    axial_members=tuple(axial),layer_axis=layer))
                if axial:result.append(MachiningPlan(row['net'],spine,tuple(orders),planar=planar,layer_axis=layer))
        return result

    def initial(self):
        return {n:self.options[n][0] for n in self.order if self.options[n]}

    def alternatives(self, plans, implicated=(),poses=None):
        selected=set(implicated) or set(plans)
        source=self.engineering.source.model_copy(deep=True)
        for feature in source.features:
            if poses and feature.id in poses:feature.face,feature.rotation=poses[feature.id]
        rows={r['net']:r for r in self.engineering.nets}
        for n in self.order:
            if n not in selected or n not in plans:continue
            p=plans[n]
            # Change external approach while preserving source geometry first.
            for entry in ('negative','positive'):
                if p.entry!=entry:yield {**plans,n:replace(p,entry=entry)},dict(kind='ENTRY',nets=[n])
            for q in self.for_net(rows[n],source):
                q=replace(q,entry=p.entry)
                if q!=p:yield {**plans,n:q},dict(kind='MACHINING_TOPOLOGY',nets=[n])
            yield {**plans,n:replace(p,side=-p.side)},dict(kind='CORRIDOR_SIDE',nets=[n])
            if p.reserve_columns:
                yield {**plans,n:replace(p,reserve_columns=False)},dict(kind='EXACT_SOURCE_CORRIDOR_DOMAIN',nets=[n])
            for axis in range(3):
                current=dict(p.entry_axes).get(axis,p.entry)
                other='positive' if current!='positive' else 'negative'
                yield {**plans,n:replace(p,entry_axes=tuple(sorted({**dict(p.entry_axes),axis:other}.items())))},dict(kind='AXIS_ENTRY',nets=[n],axis=axis)
            for member,order in p.orders:
                feature=next(f for f in source.features if f.id==member.split(':')[0])
                normal=FACE_AXES[feature.face][2]
                for alternative in itertools.permutations(range(3)):
                    if alternative==order or alternative[0]==normal:continue
                    orders=tuple((m,alternative if m==member else o) for m,o in p.orders)
                    yield {**plans,n:replace(p,orders=orders)},dict(kind='TERMINAL_PROCESS_ORDER',nets=[n],member=member)

    def materialize(self, design, plans, junctions, cache=None, *, net_ids=None, operation_records=None):
        e=self.engineering;out={};nets={n.id:effective_net(design,n) for n in design.nets}
        for name in self.order:
            if name not in plans or net_ids is not None and name not in net_ids:continue
            plan=plans[name];net=nets[name];approaches={};operations=[];rejections=[]
            if plan.access=='coaxial':
                from ..routing import simple_routes
                choices=simple_routes(design,net,e.definitions,include_detours=False)
                if choices:out[name]=choices[0]
                if operation_records is not None:operation_records[name]=[]
                continue
            for f in design.features:
                if f.kind=='port' and f.id in net.members:
                    depth=port_turn_depth(design,net,f,e.definitions,'window' if plan.access=='window' else 'clear',e.threads,e.modifiers)
                    if depth is None:depth=port_turn_depth(design,net,f,e.definitions,'clear',e.threads,e.modifiers)
                    if depth is not None:approaches[f.id]=depth
            windows=face_window_points(design,net,e.definitions,e.threads,e.modifiers)
            if plan.axial_members:
                from ..cavity_access import axial_route,cavity_terminal_candidates
                from ..closure_runtime import bind_route
                # AI's explicit process uses the actual source-bound engagement
                # also used by geometry; never a Feature's default plug length.
                candidates={m:bind_route(design,[bore])[0] for m,bore in cavity_terminal_candidates(
                    design,net,e.definitions,e.threads,e.modifiers).items()}
                members=sorted(net.members);mask=sum(1<<members.index(m) for m in plan.axial_members)
                route=axial_route(design,net,e.definitions,f'axial_{mask}_0:xyz:'+plan.entry,
                    candidates=candidates,threads=e.threads,modifiers=e.modifiers,port_approaches=approaches,entry_safe=False,
                    obstruction_cache=cache,junction_override=junctions[name],terminal_orders=dict(plan.orders),
                    terminal_overrides={m:p for m,p in windows.items() if m not in plan.axial_members},operation_records=operations,failure_records=rejections)
            else:
                route=propose(design,net,(0,1,2),plan.entry,definitions=e.definitions,
                    junction_override=junctions[name],terminal_orders=dict(plan.orders),terminal_overrides=windows,
                    port_approaches=approaches,entry_safe=False,thread_definitions=e.threads,modifier_definitions=e.modifiers,
                    obstruction_cache=cache,operation_records=operations)
            if route is not None:
                from ..closure_runtime import bind_route
                route=bind_route(design,route)
                if plan.entry_axes:
                    from ..routing_space import MachiningSpace
                    space=MachiningSpace(design,net,e.definitions,e.threads,e.modifiers,tools=e.tools,cache=cache)
                    records={r['feature']:r for r in operations};selected=[]
                    for feature in route:
                        record=records.get(feature.id);mode=dict(plan.entry_axes).get(FACE_AXES[feature.face][2])
                        if not mode or not record or record['source_bound']:
                            selected.append(feature);continue
                        axis=record['axis'];u,v,_,sign=FACE_AXES[feature.face];lo,hi=record['required_interval']
                        expected=(hi if sign>0 else dimensions(design.block)[axis]-lo)+net.diameter/2
                        if abs(expected-feature.depth)>1e-5:
                            selected.append(feature);continue  # source-bound tip stop
                        a=list(record['fixed']);a.insert(axis,lo);b=list(record['fixed']);b.insert(axis,hi)
                        choices=space.operations(tuple(a),tuple(b),[])
                        preferred=next((r[0] for r in choices if len(r)==1 and
                            (FACE_AXES[r[0].face][3]>0)==(mode=='negative')),None)
                        selected.append(preferred or feature)
                    route=selected
                out[name]=bind_route(design,route)
            if operation_records is not None:operation_records[name]=operations+([
                dict(status='MATERIALIZATION_REJECTED',failures=rejections or [dict(rule='PROCESS_NOT_MATERIALIZED')])] if route is None else [])
        return out

    def diagnostics(self):
        return dict(order=self.order,profile_access=self.profile_access,topologies={n:[p.diagnostics() for p in ps] for n,ps in self.options.items()},
                    coverage='External orthogonal junction trees; other topologies use shared resumable Router',
                    physical_infeasibility_proven=False)
