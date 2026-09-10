"""Map only explicitly closed source line loops; preserve unsupported syntax for review."""
import math
import hashlib
import json


def boundary_shape(raw,source_type='',scale=1):
    points=source_boundary(raw,scale)
    if points:return dict(points=points)
    # Only the explicit Circle form with four matching quarter-arc endpoint pairs.
    # General arc direction, bulges and mixed L/A contours remain unmapped.
    tokens=[x.strip() for x in raw.split(';') if x.strip()]
    if source_type!='Circle' or len(tokens)!=28 or any(tokens[i]!='A' for i in range(0,28,7)):return None
    try:
        arcs=[tuple(float(v)*scale for v in tokens[i+1:i+7]) for i in range(0,28,7)]
        if any(not math.isfinite(v) or abs(v)>2000 for a in arcs for v in a):return None
        cx,cy=arcs[0][4:];r=math.hypot(arcs[0][0]-cx,arcs[0][1]-cy)
        if r<=0:return None
        edges=set();vertices={}
        for x,y,xx,yy,cxx,cyy in arcs:
            if math.dist((cx,cy),(cxx,cyy))>1e-6:return None
            if abs(math.hypot(x-cx,y-cy)-r)>1e-6 or abs(math.hypot(xx-cx,yy-cy)-r)>1e-6:return None
            if abs((x-cx)*(xx-cx)+(y-cy)*(yy-cy))>1e-6:return None
            a,b=(round(x,6),round(y,6)),(round(xx,6),round(yy,6));edges.add(tuple(sorted((a,b))))
            for p in (a,b):vertices[p]=vertices.get(p,0)+1
        if len(edges)!=4 or len(vertices)!=4 or set(vertices.values())!={2}:return None
        return dict(circle=(cx,cy,r))
    except ValueError:return None


def boundary_source(record):
    assembly=record.get('kind')=='assembly_envelope'
    raw=record.get('dimension_raw','') if assembly else record.get('envelope',{}).get('dimensions_raw','')
    typ=record.get('envelope_type','') if assembly else record.get('envelope',{}).get('type','')
    return dict(source=record['id'],source_role='assembly-envelope' if assembly else 'footprint-envelope',
                source_type=typ or '',source_raw=raw or '',source_sha256=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest())


def source_boundary(raw, scale=1):
    tokens=[x.strip() for x in raw.split(';') if x.strip()]
    if not tokens or len(tokens)%5 or any(tokens[i]!='L' for i in range(0,len(tokens),5)):
        return None
    try:
        edges=[((float(tokens[i+1])*scale,float(tokens[i+2])*scale),(float(tokens[i+3])*scale,float(tokens[i+4])*scale)) for i in range(0,len(tokens),5)]
    except ValueError:
        return None
    if any(not math.isfinite(v) or abs(v)>2000 for edge in edges for p in edge for v in p):
        return None
    points=list(edges.pop(0))
    while edges:
        matches=[(i,a,b) if math.dist(a,points[-1])<1e-7 else (i,b,a) for i,(a,b) in enumerate(edges) if min(math.dist(a,points[-1]),math.dist(b,points[-1]))<1e-7]
        if len(matches)!=1:
            return None
        i,_,end=matches[0];points.append(end);edges.pop(i)
    if len(points)<4 or math.dist(points[0],points[-1])>1e-7:
        return None
    return points[:-1]


def mapped_boundaries(record,relations):
    result=[];seen=set()
    for r in [record,*relations]:
        raw=r.get('envelope',{}).get('dimensions_raw','')
        if not raw:
            continue
        shape=boundary_shape(raw,r.get('envelope',{}).get('type',''),25.4 if r.get('unit_system')=='inch' else 1)
        signature=json.dumps(shape,sort_keys=True)
        if not shape or signature in seen:
            continue
        seen.add(signature)
        result.append(dict(category='mounting-footprint',**shape,height=0,**boundary_source(r),status='source-mapped'))
    return result
