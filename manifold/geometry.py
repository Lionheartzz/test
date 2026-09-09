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


def build_geometry(design: Design):
    b = design.block
    block = cq.Solid.makeBox(b.length, b.width, b.height)
    lib = {d.id: d for d in design.library}
    cuts, nodes, circuits, envelopes, plugs, placements = {}, {}, {}, {}, {}, {}
    boundaries = {}
    for f in design.features:
        if f.suppressed:
            continue
        origin, direction = placement(f, b)
        placements[f.id] = dict(origin=origin, direction=direction)
        if f.kind == 'cavity':
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
                key = f'{f.id}:{z.id}'
                nodes[key] = cylinder(offset_origin(z.offset_u,z.offset_v), direction, z.diameter, z.start, z.end)
                if z.clip_to_cut:
                    nodes[key] = nodes[key].intersect(cuts[f.id]).clean()
                circuits[key] = f.circuits[z.id]
            envelopes[f.id] = cylinder(origin, direction, d.clearance_diameter, -d.clearance_height, 0)
            for i, boundary in enumerate(d.boundaries):
                points = [cq.Vector(*offset_origin(*p)) for p in boundary.points]
                wire = cq.Wire.makePolygon([*points,points[0]])
                face = cq.Face.makeFromWires(wire)
                if not face.isValid() or face.Area() <= 1e-6:
                    raise ValueError(f'{f.id}: invalid mounting boundary')
                shape = cq.Solid.extrudeLinear(wire,[],cq.Vector(*[-x*boundary.height for x in direction])) if boundary.height else face
                boundaries[f'{f.id}/{i}'] = dict(shape=shape,owner=f.id,category=boundary.category,source=boundary.source,height=boundary.height)
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
    production = block.cut(*cuts.values()).clean() if cuts else block
    return Geometry(block, production, cuts, nodes, circuits, envelopes, plugs, placements, boundaries)


def mesh(shape):
    vertices, triangles = shape.tessellate(0.12, 0.15)
    return dict(vertices=[round(v, 6) for p in vertices for v in p.toTuple()], triangles=[i for t in triangles for i in t])


def review_model(design,g):
    """Display only: both build and draft solids use the same machined BRep mesh."""
    from .schema import COLORS
    features={f.id:f for f in design.features}
    parts=[dict(id='block',kind='body',color='#9ba9b9',**mesh(g.production))]
    for key,cut in g.cuts.items():
        if features[key].kind=='cavity':
            parts.append(dict(id=key,owner=key,kind='cavity',color='#bbc7d4',**mesh(cut)))
    for key,shape in g.nodes.items():
        owner=key.split(':')[0];f=features[owner]
        color=next((n.color for n in design.nets if n.id==g.circuits[key] and n.color),COLORS.get(g.circuits[key],'#b08bea'))
        parts.append(dict(id=key,owner=owner,kind='zone' if ':' in key else f.kind,circuit=g.circuits[key],color=color,**mesh(shape)))
    for key,shape in g.plugs.items():
        parts.append(dict(id=key+':plug',owner=key,kind='plug',color='#d5dee9',**mesh(shape)))
    return dict(block=design.block.model_dump(),parts=parts,placements=g.placements,
                volume_mm3=round(g.production.Volume(),3),colors=COLORS,geometry_kind='machined-brep')
