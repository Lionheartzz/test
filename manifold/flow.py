from .timing import timed,phase
"""Geometric connection screen, not a pressure-drop or CFD calculation."""
import math
from .cad import cq


@timed('hydraulic.opening')
def opening_area(a, b, directions):
    """Minimum exact common-section area on the two flow axes at overlap centroid.

    A reproducible characteristic opening, not a certified minimum throat area.
    Both sections are OCCT face/solid intersections; no tessellation is used.
    """
    common = a.intersect(b)
    if common.Volume() <= 1e-6:
        return 0.0
    center = common.Center()
    size = common.BoundingBox().DiagonalLength * 4 + 10
    areas = []
    for direction in directions:
        plane = cq.Face.makePlane(size, size, center, cq.Vector(*direction))
        section = common.intersect(plane)
        areas.append(sum(face.Area() for face in section.Faces()))
    return min(areas)


def required_area(flow_lpm, velocity):
    return flow_lpm * 1_000_000 / 60 / (velocity * 1000)


def equivalent_diameter(area):
    return math.sqrt(4 * max(0, area) / math.pi)
