from .timing import timed,phase
"""Geometric connection screen, not a pressure-drop or CFD calculation."""
import math
from .cad import cq
from .cad_geometry import checked_intersection,checked_shape,solid_volume,cad_operation,GeometryEvaluationError,error_record


@timed('hydraulic.opening')
def opening_area(a, b, directions, *, common=None, context=None):
    """Minimum exact common-section area on the two flow axes at overlap centroid.

    A reproducible characteristic opening, not a certified minimum throat area.
    Both sections are OCCT face/solid intersections; no tessellation is used.
    """
    if common is None:common=checked_intersection(a,b,'opening_area.common_intersection',context)
    if solid_volume(common,'opening_area.common',context)<=1e-6:
        return 0.0
    # Ignore any zero-volume face/edge remnants in a mixed-dimensional Common.
    # CadQuery's compound mass/center policy follows its first child's dimension.
    with cad_operation('opening_area.solid_components',context):
        common=cq.Compound.makeCompound(common.Solids())
    checked_shape(common,'opening_area.solid_common',context,allow_empty=False)
    with cad_operation('opening_area.common_center',context):center=common.Center()
    with cad_operation('opening_area.common_bounds',context):size=common.BoundingBox().DiagonalLength*4+10
    areas = []
    for direction in directions:
        with cad_operation('opening_area.make_plane',context):plane=cq.Face.makePlane(size,size,center,cq.Vector(*direction))
        section=checked_intersection(common,plane,'opening_area.section_intersection',context)
        state=checked_shape(section,'opening_area.section',context)
        if state['empty']:areas.append(0.0);continue
        with cad_operation('opening_area.section_faces',context):faces=section.Faces()
        area=0.0
        for face in faces:
            checked_shape(face,'opening_area.section_face',context)
            with cad_operation('opening_area.face_area',context):value=face.Area()
            if not math.isfinite(value) or value<0:
                raise GeometryEvaluationError(error_record('opening_area.face_area',context,reason='INVALID_AREA'))
            area+=value
        areas.append(area)  # A valid wire/edge/vertex section has zero face area.
    if not areas:raise ValueError('Opening calculation requires at least one flow direction')
    return min(areas)


def required_area(flow_lpm, velocity):
    return flow_lpm * 1_000_000 / 60 / (velocity * 1000)


def equivalent_diameter(area):
    return math.sqrt(4 * max(0, area) / math.pi)
