"""Operation-owned engineering facts. No LLM, project writes or CAD approval."""
from dataclasses import dataclass
import hashlib
import json

from ..kinematics import FACE_AXES, pose
from ..engineering_conditions import effective_net, planning_wall
from ..routing import terminal_points, _manufacturing_cuts
from .initialization import source_extents


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class EngineeringPlan:
    source: object
    definitions: dict
    domain: object
    threads: dict
    modifiers: dict
    tools: list
    features: list
    nets: list
    facts: list
    dependency: str

    @classmethod
    def compile(cls, design, definitions, domain, threads, modifiers, tools):
        from ..routing_continuation import dependency_key
        points = terminal_points(design, definitions)
        sources = [f for f in design.features if not f.suppressed and not f.route_net]
        rows = []
        for f in sources:
            origin, normal = pose(f, design.block)
            windows = [dict(member=m, offset=[p[i]-origin[i] for i in range(3)])
                       for m, p in points.items() if m.split(':')[0] == f.id]
            physical = f.model_dump(exclude={'id', 'circuit', 'circuits', 'interface_nets', 'schematic_id',
                'machining_id', 'connects_to', 'cartridge_id'})
            rows.append(dict(feature=f.id, physical=physical, origin=list(origin), normal=list(normal),
                windows=windows, extents=source_extents(design, f, definitions, threads, modifiers),
                cuts=[{k:v for k,v in c.items() if k != 'feature'}
                      for c in _manufacturing_cuts(f, definitions, threads, modifiers)],
                locked=dict(position=domain.fixed_positions.get(f.id), face=domain.fixed_faces.get(f.id),
                            rotation=domain.fixed_rotations.get(f.id), owned=f.id in domain.movable)))
        # Structural colouring has no semantic dependence on names or input order.
        colors = {r['feature']:digest(r['physical']) for r in rows}
        nets = [effective_net(design, n) for n in design.nets
                if n.routing == 'automatic' and len(n.members) >= 2]
        for _ in range(len(rows)+1):
            nc = {n.id:digest([n.diameter, sorted((colors.get(m.split(':')[0], ''),
                    m.partition(':')[2]) for m in n.members)]) for n in nets}
            colors = {r['feature']:digest([r['physical'], sorted(nc[n.id] for n in nets
                    if any(m.split(':')[0] == r['feature'] for m in n.members))]) for r in rows}
        rows.sort(key=lambda r:(colors[r['feature']], r['origin']))
        fi = {r['feature']:i for i,r in enumerate(rows)}
        nets.sort(key=lambda n:(nc[n.id], sorted((fi.get(m.split(':')[0], -1), m.partition(':')[2]) for m in n.members)))
        nr = [dict(net=n.id, members=sorted(n.members,key=lambda m:(fi.get(m.split(':')[0], -1),m.partition(':')[2])),
                   diameter=n.diameter, wall=planning_wall(design,n,definitions),
                   pressure=n.pressure_bar, flow=n.flow_lpm,
                   coupled_nets=[other.id for other in nets if other.id != n.id and
                       {m.split(':')[0] for m in n.members}&{m.split(':')[0] for m in other.members}]) for n in nets]
        from ..closure_runtime import bind_route
        from ..schema import Feature
        for row in nr:
            closure=bind_route(design,[Feature(id='PLAN_CLOSURE',kind='drilling',face='left',u=design.block.width/2,
                v=design.block.height/2,diameter=row['diameter'],depth=max(20,row['diameter']*5),
                circuit=row['net'],route_net=row['net'],plugged=True)])[0]
            row['closure']=dict(definition=closure.closure_definition_id,occupied_depth=closure.plug_length,
                entry_diameter=closure.clearance_diameter) if closure.closure_definition_id else None
        facts = [dict(kind='SOURCE_GEOMETRY', level='HARD_PROVEN', source='Design + executable engineering definitions',
                      features=[r['feature'] for r in rows]),
                 dict(kind='OWNERSHIP_AND_LOCKS', level='HARD_PROVEN', source='explicit new Generate LayoutDomain',
                      value=domain.diagnostics()),
                 dict(kind='MANUFACTURING_RULES', level='HARD_PROVEN', source='Design.rules',value=design.rules.model_dump()),
                 dict(kind='SOFT_LAYOUT', level='SOFT_PREFERENCE',source='generation preferences',
                      faces=domain.soft_faces,dimensions=domain.soft_dimensions)]
        for n in nr:
            for name in ('pressure','flow'):
                facts.append(dict(kind=name,net=n['net'],level='UNKNOWN' if n[name] is None else 'HARD_PROVEN',
                                  value=n[name],source='effective project/Net conditions'))
        from ..engineering_conditions import material_strength
        from ..sizing import route_sizing
        strength=material_strength(design)
        facts.append(dict(kind='MATERIAL_STRENGTH',level='UNKNOWN' if strength['design_strength_mpa'] is None else 'HARD_PROVEN',
            value=strength,source='production engineering_conditions.material_strength'))
        for row in nr:
            net=next(n for n in nets if n.id==row['net'])
            row['sizing']=route_sizing(net,tools=tools,preferred_unit=design.project_context,design=design)
            row['tooling']=dict(required_diameter_mm=row['diameter'],
                tools=[t for t in tools if abs(t['diameter_mm']-row['diameter'])<=.011],
                depth_qualified=False,source='production tool_definitions; complete depth checked after materialization')
        dep = dependency_key(design,nets[0],definitions,threads,modifiers,[],tools) if nets else digest(design.model_dump())
        return cls(design.model_copy(deep=True),definitions,domain,threads,modifiers,tools,rows,nr,facts,dep)

    def diagnostics(self):
        return dict(dependency=self.dependency,scope='NEW_AI_GENERATE_ONLY',facts=self.facts,
                    rigid_features=self.features,net_hypergraph=self.nets,
                    unknowns=[f for f in self.facts if f['level']=='UNKNOWN'],
                    approval='FACTS_AND_CONSTRAINTS_ONLY')
