"""Face-local design coordinates shared conceptually with web/kinematics.js."""
import math

FACE_AXES = {'top': (0, 1, 2, -1), 'bottom': (0, 1, 2, 1),
             'front': (0, 2, 1, 1), 'back': (0, 2, 1, -1),
             'left': (1, 2, 0, 1), 'right': (1, 2, 0, -1)}


def dimensions(block):
    return (block.length, block.width, block.height)


def pose(feature, block):
    u, v, axis, sign = FACE_AXES[feature.face]
    p = [0.0, 0.0, 0.0]
    p[u], p[v], p[axis] = feature.u, feature.v, 0 if sign > 0 else dimensions(block)[axis]
    d = [0, 0, 0]; d[axis] = sign
    return tuple(p), tuple(d)


def footprint_radius(feature, library):
    if feature.kind == 'cavity':
        definition = next(d for d in library if d.id == feature.definition)
        return max(definition.clearance_diameter, *(s.diameter for s in definition.stages)) / 2
    return max(feature.diameter, feature.clearance_diameter if feature.kind == 'port' or feature.plugged else 0) / 2


def placement_bounds(feature, design):
    u, v, _, _ = FACE_AXES[feature.face]
    radius = footprint_radius(feature, design.library)
    sizes = dimensions(design.block)
    return dict(min_u=radius, max_u=sizes[u] - radius, min_v=radius, max_v=sizes[v] - radius,
                fits=2 * radius <= sizes[u] and 2 * radius <= sizes[v], radius=radius)


def clamp_placement(feature, design, u, v, snap=1):
    bounds = placement_bounds(feature, design)
    if not bounds['fits']:
        raise ValueError('This component envelope does not fit on the selected face')
    if snap:
        u, v = math.floor(u / snap + .5) * snap, math.floor(v / snap + .5) * snap
    return max(bounds['min_u'], min(bounds['max_u'], u)), max(bounds['min_v'], min(bounds['max_v'], v))


def resolve_parents(design):
    result = design.model_copy(deep=True)
    by_id = {f.id: f for f in result.features}
    resolved = set()
    def resolve(f):
        if f.id in resolved:
            return
        if f.parent_id:
            parent = by_id[f.parent_id]; resolve(parent)
            angle = math.radians(parent.rotation)
            u, v = f.local_offset
            f.face = parent.face
            f.u = parent.u + u * math.cos(angle) - v * math.sin(angle)
            f.v = parent.v + u * math.sin(angle) + v * math.cos(angle)
            f.suppressed = f.suppressed or parent.suppressed
        resolved.add(f.id)
    for f in result.features:
        resolve(f)
    return result
