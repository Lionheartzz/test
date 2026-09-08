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


def placement(f: Feature, block):
    # Face coordinates are always global increasing axes, not mirrored screen axes.
    l, w, h = block.length, block.width, block.height
    return {
        'left': ((0, f.u, f.v), (1, 0, 0)),
        'right': ((l, f.u, f.v), (-1, 0, 0)),
        'front': ((f.u, 0, f.v), (0, 1, 0)),
        'back': ((f.u, w, f.v), (0, -1, 0)),
        'bottom': ((f.u, f.v, 0), (0, 0, 1)),
        'top': ((f.u, f.v, h), (0, 0, -1)),
    }[f.face]


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
    for f in design.features:
        origin, direction = placement(f, b)
        placements[f.id] = dict(origin=origin, direction=direction)
        if f.kind == 'cavity':
            d = lib[f.definition]
            pieces = [cylinder(origin, direction, s.diameter, s.start, s.end) for s in d.stages]
            cuts[f.id] = pieces[0].fuse(*pieces[1:]).clean() if len(pieces) > 1 else pieces[0]
            for z in d.zones:
                key = f'{f.id}:{z.id}'
                nodes[key] = cylinder(origin, direction, z.diameter, z.start, z.end)
                circuits[key] = f.circuits[z.id]
            envelopes[f.id] = cylinder(origin, direction, d.clearance_diameter, -d.clearance_height, 0)
        else:
            cut = cylinder(origin, direction, f.diameter, 0, f.depth)
            tip = tip_depth(f)
            if tip:
                cone = cq.Solid.makeCone(f.diameter / 2, 0, tip, cq.Vector(*at(origin, direction, f.depth)), cq.Vector(*direction))
                cut = cut.fuse(cone).clean()
            cuts[f.id] = cut
            if f.plugged:
                plugs[f.id] = cylinder(origin, direction, f.diameter, 0, f.plug_length)
                nodes[f.id] = cut.cut(plugs[f.id]).clean()
            else:
                nodes[f.id] = cut
            circuits[f.id] = f.circuit
            if f.plugged or f.kind == 'port':
                envelopes[f.id] = cylinder(origin, direction, f.clearance_diameter, -f.clearance_height, 0)
    production = block.cut(*cuts.values()).clean()
    return Geometry(block, production, cuts, nodes, circuits, envelopes, plugs, placements)


def mesh(shape):
    vertices, triangles = shape.tessellate(0.12, 0.15)
    return dict(vertices=[round(v, 6) for p in vertices for v in p.toTuple()], triangles=[i for t in triangles for i in t])
