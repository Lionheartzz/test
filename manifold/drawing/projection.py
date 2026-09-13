"""Exact BRep hidden-line projection. Units are explicit mm, never inferred from size."""
import math
from threading import RLock
from ..cad import cq
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.BRepLib import BRepLib
from OCP.GCPnts import GCPnts_QuasiUniformDeflection

# Outward-looking drawing axes, right-handed: right x up = towards viewer.
FRAMES = {
    'front': ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
    'back': ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    'left': ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
    'right': ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    'top': ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    'bottom': ((1, 0, 0), (0, -1, 0), (0, 0, -1)),
}
_n = 1 / math.sqrt(3)
_x = 1 / math.sqrt(2)
_y = 1 / math.sqrt(6)
FRAMES['iso'] = ((_x, _x, 0), (-_y, _y, 2 * _y), (_n, -_n, _n))
CAD_LOCK = RLock()


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def frame(name):
    return FRAMES[{'section-x': 'right', 'section-y': 'front', 'section-z': 'top'}.get(name, name)]


def projected(point, name):
    x, y, _ = frame(name)
    return [dot(point, x), dot(point, y)]


def edges(shape):
    result = []
    for edge in shape.Edges():
        curve = edge._geomAdaptor()
        sample = GCPnts_QuasiUniformDeflection(curve, 0.002, curve.FirstParameter(), curve.LastParameter())
        if not sample.IsDone():
            raise ValueError('Exact drawing edge could not be projected; no approximate mesh fallback was used')
        points = [[round(sample.Value(i).X(), 6), round(sample.Value(i).Y(), 6)] for i in range(1, sample.NbPoints() + 1)]
        if len(points) > 1:
            result.append(points)
    return result


def project(shape, name, section_at=None):
    with CAD_LOCK:
        x, y, normal = frame(name)
        hatching=[]
        if name.startswith('section-'):
            axis = 'xyz'.index(name[-1])
            if section_at is None:
                box = shape.BoundingBox()
                section_at = (box.xmax, box.ymax, box.zmax)[axis] / 2
            box=shape.BoundingBox()
            if not (getattr(box,name[-1]+'min')+1e-6 < section_at < getattr(box,name[-1]+'max')-1e-6):
                raise ValueError('Section must be strictly inside the manifold')
            origin = [0, 0, 0]
            origin[axis] = section_at
            # Remove material towards the viewer. The exact cut face becomes visible.
            plane = cq.Plane(cq.Vector(*origin), cq.Vector(*x), cq.Vector(*normal))
            half = cq.Workplane(plane).box(10000, 10000, 5000, centered=(True, True, False)).val()
            shape = shape.cut(half).clean()
            if not shape.Solids():
                raise ValueError('Section does not intersect the manifold; choose an interior plane')
            # Clip 45-degree hatching against the exact cut-face wires (including holes).
            # Sampling tolerance equals the vector edge tolerance; never use display meshes.
            for face in shape.Faces():
                if face.geomType()!='PLANE' or abs(face.Center().toTuple()[axis]-section_at)>1e-5 or abs(dot(face.normalAt().toTuple(),normal))<.999:
                    continue
                segments=[]
                for edge in face.Edges():
                    curve=edge._geomAdaptor()
                    sample=GCPnts_QuasiUniformDeflection(curve,.002,curve.FirstParameter(),curve.LastParameter())
                    if not sample.IsDone():raise ValueError('Section boundary could not be evaluated')
                    pts=[projected((sample.Value(i).X(),sample.Value(i).Y(),sample.Value(i).Z()),name) for i in range(1,sample.NbPoints()+1)]
                    segments.extend(zip(pts,pts[1:]))
                offsets=[p[1]-p[0] for seg in segments for p in seg]
                for index in range(math.floor(min(offsets)/3),math.ceil(max(offsets)/3)+1):
                    intercept=index*3;crossings=[]
                    for a,b in segments:
                        da=a[1]-a[0]-intercept;db=b[1]-b[0]-intercept
                        if (da<=0<db) or (db<=0<da):
                            t=da/(da-db);crossings.append(a[0]+t*(b[0]-a[0]))
                    crossings.sort()
                    for a,b in zip(crossings[::2],crossings[1::2]):
                        if b-a>1e-5:hatching.append([[a,a+intercept],[b,b+intercept]])
        algo = HLRBRep_Algo()
        algo.Add(shape.wrapped)
        algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(), gp_Dir(*normal), gp_Dir(*x))))
        algo.Update()
        algo.Hide()
        output = HLRBRep_HLRToShape(algo)
        result = {'visible': [], 'hidden': [], 'hatching': hatching, 'section_at': section_at}
        for kind, getters in [('visible', ['VCompound', 'Rg1LineVCompound', 'OutLineVCompound']), ('hidden', ['HCompound', 'OutLineHCompound'])]:
            for getter in getters:
                raw = getattr(output, getter)()
                if not raw.IsNull():
                    BRepLib.BuildCurves3d_s(raw, 1e-6)
                    result[kind].extend(edges(cq.Shape.cast(raw)))
        points = [p for paths in (result['visible'], result['hidden']) for path in paths for p in path]
        if not points:
            raise ValueError('Exact projection produced no usable edges')
        result['bounds'] = [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]
        result['frame'] = [x, y, normal]
        return result
