"""Conservative broad phase and immutable pair reuse within one CAD operation."""
import math


def geometry_pairs(geometry):
    """Reuse immutable geometry measurements across contact and rule checks."""
    if not hasattr(geometry,'_exact_pairs'):geometry._exact_pairs=ExactPairs()
    return geometry._exact_pairs


class ExactPairs:
    def __init__(self):
        self.shapes={};self.volumes={};self.intersections={};self.distances={}
        self.stats=dict(bounds_clearance_proofs=0,bounds_disjoint_proofs=0,exact_distances=0,exact_intersections=0)

    def bounds(self,shape):
        key=id(shape)
        if key not in self.shapes:
            box=shape.BoundingBox()
            # Hold the wrapper as well: Python object IDs must not be recycled
            # while a derived protected/window shape is in this operation cache.
            self.shapes[key]=(shape,((box.xmin,box.xmax),(box.ymin,box.ymax),(box.zmin,box.zmax)))
        return self.shapes[key][1]

    def lower_bound(self,a,b):
        return math.sqrt(sum(max(0,x[0]-y[1]-1e-6,y[0]-x[1]-1e-6)**2
                             for x,y in zip(self.bounds(a),self.bounds(b))))

    def volume(self,a,b):
        # Subtracting the complete assigned window may leave an empty compound;
        # its volume is zero and it need not have a finite bounding box.
        for shape in (a,b):
            if id(shape) not in self.volumes:self.volumes[id(shape)]=(shape,shape.Volume())
        if any(self.volumes[id(shape)][1]==0 for shape in (a,b)):return 0.0
        self.bounds(a);self.bounds(b)
        key=tuple(sorted((id(a),id(b))))
        if key not in self.intersections:
            separated=self.lower_bound(a,b)>0
            self.stats['bounds_disjoint_proofs' if separated else 'exact_intersections']+=1
            self.intersections[key]=0.0 if separated else a.intersect(b).Volume()
        return self.intersections[key]

    def separation(self,a,b,required):
        lower=self.lower_bound(a,b)
        if lower>=required:
            self.stats['bounds_clearance_proofs']+=1
            # A lower bound proves this check, not an exact measured clearance.
            return f'>= {lower:.5f} (conservative bounds)',True
        key=tuple(sorted((id(a),id(b))))
        if key not in self.distances:
            self.stats['exact_distances']+=1;self.distances[key]=a.distance(b)
        distance=self.distances[key]
        return distance,distance+1e-6>=required
