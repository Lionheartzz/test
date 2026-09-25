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
    manufacturing_features: dict


def placement(f: Feature, block):
    from .kinematics import pose
    return pose(f,block)


def at(origin, direction, depth):
    return tuple(a + b * depth for a, b in zip(origin, direction))


def cylinder(origin, direction, diameter, start, end):
    return cq.Solid.makeCylinder(diameter / 2, end - start, cq.Vector(*at(origin, direction, start)), cq.Vector(*direction))


def face_origin(face, u, v, block):
    from .kinematics import FACE_AXES,dimensions
    ua,va,axis,sign=FACE_AXES[face];point=[0.0,0.0,0.0]
    point[ua]=u;point[va]=v;point[axis]=dimensions(block)[axis] if sign<0 else 0
    direction=[0.0,0.0,0.0];direction[axis]=sign
    return tuple(point),tuple(direction),ua,va


def rectangular_cut(row, block):
    origin,direction,ua,va=face_origin(row.face,row.u,row.v,block)
    angle=math.radians(row.rotation);corners=[]
    for x,y in ((-row.width/2,-row.height/2),(row.width/2,-row.height/2),(row.width/2,row.height/2),(-row.width/2,row.height/2)):
        point=list(origin);point[ua]+=x*math.cos(angle)-y*math.sin(angle);point[va]+=x*math.sin(angle)+y*math.cos(angle);corners.append(cq.Vector(*point))
    wire=cq.Wire.makePolygon([*corners,corners[0]])
    return cq.Solid.extrudeLinear(wire,[],cq.Vector(*(component*row.depth for component in direction)))


def engraving_cut(row, block):
    origin,direction,ua,_=face_origin(row.face,row.u,row.v,block)
    xdir=[0.0,0.0,0.0];xdir[ua]=1
    plane=cq.Plane(origin=cq.Vector(*origin),xDir=cq.Vector(*xdir),normal=cq.Vector(*direction))
    return cq.Workplane(plane).transformed(rotate=(0,0,row.rotation)).text(
        row.text,row.text_height,row.depth,combine=False,clean=True).val()


def tip_depth(f):
    return 0 if f.tip_angle == 180 else f.diameter / 2 / math.tan(math.radians(f.tip_angle / 2))


@timed('geometry.construction')
def build_geometry(design: Design, definitions=None, thread_definitions=None, modifier_definitions=None):
    b = design.block
    block = cq.Solid.makeBox(b.length, b.width, b.height)
    stock=block
    manufacturing_features={}
    face_selectors={'top':'>Z','bottom':'<Z','front':'<Y','back':'>Y','left':'<X','right':'>X'}
    for row in design.block_modifiers:
        if row.kind=='chamfer':
            stock=cq.Workplane(obj=stock).faces(face_selectors[row.face]).edges().chamfer(row.size).val()
            manufacturing_features[row.id]=block.cut(stock)
        else:
            manufacturing_features[row.id]=rectangular_cut(row,b)
    for row in design.engravings:
        manufacturing_features[row.id]=engraving_cut(row,b)
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    if thread_definitions is None:
        from .engineering_db import thread_definitions_for_design
        thread_definitions=thread_definitions_for_design(design)
    if modifier_definitions is None:
        from .engineering_db import modifier_definitions_for_design
        modifier_definitions=modifier_definitions_for_design(design)
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
                if f.kind=='cavity' and z.id not in f.circuits:
                    continue
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
            diameter=thread_definitions[f.thread_definition_id]['tap_diameter_mm'] if f.kind=='mounting' and f.mounting_mode=='threaded' else f.diameter
            extension=diameter/2*math.sqrt(max(0,1-cosine*cosine))/cosine if f.direction else 0
            cut = cylinder(origin, direction, diameter, -extension, f.depth)
            tip = 0 if f.kind=='mounting' and f.through else diameter/2/math.tan(math.radians(f.tip_angle/2)) if f.tip_angle!=180 else 0
            if tip:
                cone = cq.Solid.makeCone(diameter / 2, 0, tip, cq.Vector(*at(origin, direction, f.depth)), cq.Vector(*direction))
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
        if f.machining_modifiers:
            pieces=[]
            for placement_value in f.machining_modifiers:
                modifier=modifier_definitions[placement_value.modifier_id]
                for primitive in modifier['primitives']:
                    start=placement_value.start+primitive['start'];end=placement_value.start+primitive['end']
                    if primitive['kind']=='annulus':
                        shape=cylinder(origin,direction,primitive['diameter'],start,end).cut(
                            cylinder(origin,direction,primitive['inner_diameter'],start,end))
                    else:shape=cylinder(origin,direction,primitive['diameter'],start,end)
                    pieces.append(shape)
            if pieces:
                modifier_cut=pieces[0].fuse(*pieces[1:]) if len(pieces)>1 else pieces[0]
                cuts[f.id]=cuts[f.id].fuse(modifier_cut)
    with phase('geometry.production_boolean'):
        all_cuts=[*cuts.values(),*(shape for key,shape in manufacturing_features.items()
                                   if not any(item.id==key and item.kind=='chamfer' for item in design.block_modifiers))]
        production = stock.cut(*all_cuts).clean() if all_cuts else stock
    return Geometry(block, production, cuts, nodes, circuits, envelopes, plugs, placements, boundaries,manufacturing_features)


@timed('tessellation',immediate=True)
def mesh(shape):
    # OCCT attaches triangulations to a shape and can enlarge subsequent bounds.
    # Rendering must not mutate solids that will be used again by exact validation.
    with phase('mesh.copy'):
        prepared=shape.copy(mesh=False)
    with phase('mesh.occt_tessellate',immediate=True):
        vertices, triangles = prepared.tessellate(0.12, 0.15)
    with phase('mesh.flatten'):
        return dict(vertices=[round(v, 6) for p in vertices for v in p.toTuple()], triangles=[i for t in triangles for i in t])


def review_layer(design,g,layer):
    """Exact display-only parts deferred by interactive preview."""
    from .schema import COLORS
    features={f.id:f for f in design.features}
    parts=[]
    if layer=='void':
        with phase('review.removed_volume'):
            # Do not run ShapeUpgrade_UnifySameDomain on this complementary solid.
            # Coincident cut faces can make that display-only cleanup unbounded.
            void = g.block.cut(g.production)
        if void.Volume() > 1e-6:
            parts.append(dict(id='machined-void',kind='machined-void',color='#b6c9da',volume_mm3=void.Volume(),**mesh(void)))
    elif layer=='features':
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
    else:
        raise ValueError('Unknown exact preview layer')
    return parts


@timed('review.generation')
def review_model(design,g,*,core_only=False):
    """Display only: both build and draft solids use the same machined BRep mesh."""
    from .schema import COLORS
    parts=[dict(id='block',kind='body',color='#9ba9b9',**mesh(g.production))]
    # Boolean the authoritative solids before tessellation. Meshes never define connectivity.
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
    if not core_only:
        parts.extend(review_layer(design,g,'void'))
        parts.extend(review_layer(design,g,'features'))
    return dict(block=design.block.model_dump(),parts=parts,placements=g.placements,
                volume_mm3=round(g.production.Volume(),3),colors=COLORS,geometry_kind='machined-brep',
                brep_valid=g.production.isValid(),
                collisions=collisions,deferred_layers=['void','features'] if core_only else [],
                loaded_layers=[] if core_only else ['void','features'],
                semantics='Machined void is stock minus production; hydraulic nets are separate exact unions of flow nodes after closures. Interface parts remain separate inspection layers.')
