"""Map only explicitly closed source line loops; preserve unsupported syntax for review."""
import math


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
        points=source_boundary(raw,25.4 if r.get('unit_system')=='inch' else 1)
        if not points or tuple(sorted(points)) in seen:
            continue
        seen.add(tuple(sorted(points)))
        result.append(dict(category='mounting-footprint',points=points,height=0,source=r['id']+' / envelope.dimensions_raw',status='source-mapped'))
    return result
