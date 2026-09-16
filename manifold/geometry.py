from .timing import timed,phase
from dataclasses import dataclass
import math
from .cad import cq
from .schema import Design, Feature


@dataclass
class Geometry:
    block: cq.Shape
    production: cq.Shape
    cuts: dict
    nodes: dict
    circuits: dict
    envelopes: dict
    plugs: dict
    placements: dict
    boundaries: dict


def placement(f: Feature, block):
    from .kinematics import pose
    return pose(f,block)


def at(origin, direction, depth):
    return tuple(a + b * depth for a, b in zip(origin, direction))


def cylinder(origin, direction, diameter, start, end):
    return cq.Solid.makeCylinder(diameter / 2, end - start, cq.Vector(*at(origin, direction, start)), cq.Vector(*direction))


def tip_depth(f):
    return 0 if f.tip_angle == 180 else f.diameter / 2 / math.tan(math.radians(f.tip_angle / 2))


@timed('geometry.construction')
def build_geometry(design: Design, definitions=None):
    b = design.block
    block = cq.Solid.makeBox(b.length, b.width, b.height)
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    lib = definitions
    cuts, nodes, circuits, envelopes, plugs, placements = {}, {}, {}, {}, {}, {}
    boundaries = {}
    for f in design.features:
        if f.suppressed:
            continue
        origin, direction = placement(f, b)
        placements[f.id] = dict(origin=origin, direction=direction)
        if f.definition:
            d = lib[f.definition]
            from .kinematics import FACE_AXES
            def offset_origin(u, v):
                angle = math.radians(f.rotation)
                du, dv = u*math.cos(angle)-v*math.sin(angle), u*math.sin(angle)+v*math.cos(angle)
                p = list(origin); axes = FACE_AXES[f.face]
                p[axes[0]] += du; p[axes[1]] += dv
                return tuple(p)
            pieces = []
            for s in d.cutting_primitives:
                p = offset_origin(s.offset_u,s.offset_v)
                if s.kind == 'cone':
                    shape = cq.Solid.makeCone(s.diameter/2,s.end_diameter/2,s.end-s.start,cq.Vector(*at(p,direction,s.start)),cq.Vector(*direction))
                else:
                    shape = cylinder(p,direction,s.diameter,s.start,s.end)
                    if s.kind == 'annulus' and s.inner_diameter:
                        shape = shape.cut(cylinder(p,direction,s.inner_diameter,s.start,s.end))
                pieces.append(shape)
            if not pieces:
                pieces = [cylinder(origin, direction, s.diameter, s.start, s.end) for s in d.stages]
            cuts[f.id] = pieces[0].fuse(*pieces[1:]).clean() if len(pieces) > 1 else pieces[0]
            for z in d.zones:
                key = f.id if f.kind=='port' else f'{f.id}:{z.id}'
                nodes[key] = cylinder(offset_origin(z.offset_u,z.offset_v), direction, z.diameter, z.start, z.end)
                if z.clip_to_cut:
                    nodes[key] = nodes[key].intersect(cuts[f.id]).clean()
                circuits[key] = f.circuit if f.kind=='port' else f.circuits[z.id]
            envelopes[f.id] = cylinder(origin, direction, d.clearance_diameter, -d.clearance_height, 0)
            for i, boundary in enumerate(d.boundaries):
                if boundary.circle:
                    x,y,radius=boundary.circle
                    wire=cq.Wire.makeCircle(radius,cq.Vector(*offset_origin(x,y)),cq.Vector(*direction))
                else:
                    points = [cq.Vector(*offset_origin(*p)) for p in boundary.points]
                    wire = cq.Wire.makePolygon([*points,points[0]])
                face = cq.Face.makeFromWires(wire)
                if not face.isValid() or face.Area() <= 1e-6:
                    raise ValueError(f'{f.id}: invalid mounting boundary')
                shape = cq.Solid.extrudeLinear(wire,[],cq.Vector(*[-x*boundary.height for x in direction])) if boundary.height else face
                boundaries[f'{f.id}/{i}'] = dict(shape=shape,owner=f.id,category=boundary.category,height=boundary.height)
        else:
            from .kinematics import FACE_AXES
            cosine=abs(direction[FACE_AXES[f.face][2]])
            extension=f.diameter/2*math.sqrt(max(0,1-cosine*cosine))/cosine if f.direction else 0
            cut = cylinder(origin, direction, f.diameter, -extension, f.depth)
            tip = tip_depth(f)
            if tip:
                cone = cq.Solid.makeCone(f.diameter / 2, 0, tip, cq.Vector(*at(origin, direction, f.depth)), cq.Vector(*direction))
                cut = cut.fuse(cone).clean()
            if f.direction:
                # Trim only at the entry half-space. Other stock breakout remains visible to validation.
                normal=[0,0,0];normal[FACE_AXES[f.face][2]]=FACE_AXES[f.face][3]
                plane=cq.Plane(origin=cq.Vector(*origin),normal=cq.Vector(*normal))
                half=cq.Workplane(plane).box(12000,12000,6000,centered=(True,True,False)).val()
                cut=cut.intersect(half).clean()
            cuts[f.id] = cut
            if f.kind=='mounting':
                continue # Real stock removal, deliberately absent from hydraulic nodes/circuits.
            if f.plugged:
                plugs[f.id] = cylinder(origin, direction, f.diameter, -extension, f.plug_length)
                if f.direction:
                    plugs[f.id]=plugs[f.id].intersect(half).clean()
                nodes[f.id] = cut.cut(plugs[f.id]).clean()
            else:
                nodes[f.id] = cut
            circuits[f.id] = f.circuit
            if f.plugged or f.kind == 'port':
                envelopes[f.id] = cylinder(origin, direction, f.clearance_diameter, -f.clearance_height, 0)
    with phase('geometry.production_boolean'):
        production = block.cut(*cuts.values()).clean() if cuts else block
    return Geometry(block, production, cuts, nodes, circuits, envelopes, plugs, placements, boundaries)


@timed('tessellation',immediate=True)
def mesh(shape):
    # OCCT attaches triangulations to a shape and can enlarge subsequent bounds.
    # Rendering must not mutate solids that will be used again by exact validation.
    vertices, triangles = shape.copy(mesh=False).tessellate(0.12, 0.15)
    return dict(vertices=[round(v, 6) for p in vertices for v in p.toTuple()], triangles=[i for t in triangles for i in t])


@timed('review.generation')
def review_model(design,g):
    """Display only: both build and draft solids use the same machined BRep mesh."""
    from .schema import COLORS
    features={f.id:f for f in design.features}
    parts=[dict(id='block',kind='body',color='#9ba9b9',**mesh(g.production))]
    # Boolean the authoritative solids before tessellation. Meshes never define connectivity.
    with phase('review.removed_volume'):
        # Do not run ShapeUpgrade_UnifySameDomain on this complementary solid.
        # Coincident cut faces can make that display-only cleanup unbounded.
        void = g.block.cut(g.production)
    if void.Volume() > 1e-6:
        parts.append(dict(id='machined-void',kind='machined-void',color='#b6c9da',volume_mm3=void.Volume(),**mesh(void)))
    unions = {}
    with phase('hydraulic.net_geometry'):
        for circuit in sorted(set(g.circuits.values())):
            members=[key for key in g.nodes if g.circuits[key]==circuit]
            shapes=[g.nodes[key].intersect(g.block) for key in members]
            shape=shapes[0].fuse(*shapes[1:]) if len(shapes)>1 else shapes[0]
            unions[circuit]=shape
            color=next((n.color for n in design.nets if n.id==circuit and n.color),COLORS.get(circuit,'#b08bea'))
            parts.append(dict(id='net:'+circuit,kind='hydraulic-net',circuit=circuit,color=color,members=members,
                              volume_mm3=shape.Volume(),solid_count=len(shape.Solids()),**mesh(shape)))
    from itertools import combinations
    collisions=[]
    with phase('hydraulic.cross_net_geometry'):
        for a,b in combinations(unions,2):
            common=unions[a].intersect(unions[b])
            if common.Volume()>1e-6:
                collisions.append(dict(nets=[a,b],volume_mm3=common.Volume()))
                parts.append(dict(id=f'collision:{a}:{b}',kind='collision',color='#ff163e',nets=[a,b],**mesh(common)))
    for key,cut in g.cuts.items():
        f=features[key]
        parts.append(dict(id=key+':machining',owner=key,kind='cavity' if f.kind=='cavity' else 'port-machining' if f.kind=='port' else 'mounting-machining' if f.kind=='mounting' else 'drilling-machining',
                          color='#bbc7d4',definition=f.definition,volume_mm3=cut.Volume(),**mesh(cut)))
    for key,shape in g.nodes.items():
        owner=key.split(':')[0];f=features[owner]
        color=next((n.color for n in design.nets if n.id==g.circuits[key] and n.color),COLORS.get(g.circuits[key],'#b08bea'))
        parts.append(dict(id=key,owner=owner,kind='zone' if ':' in key else f.kind,circuit=g.circuits[key],color=color,**mesh(shape)))
    for key,shape in g.plugs.items():
        parts.append(dict(id=key+':plug',owner=key,kind='plug',color='#d5dee9',entry_machining_status='unresolved',**mesh(shape)))
    return dict(block=design.block.model_dump(),parts=parts,placements=g.placements,
                volume_mm3=round(g.production.Volume(),3),colors=COLORS,geometry_kind='machined-brep',
                brep_valid=g.production.isValid(),
                collisions=collisions,semantics='Machined void is stock minus production; hydraulic nets are separate exact unions of flow nodes after closures. Interface parts remain separate inspection layers.')
