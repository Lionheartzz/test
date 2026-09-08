"""Inspection-only machining schedules from the exact resolved build."""
import csv
import json
import math
from itertools import combinations


def manufacturing_outputs(design, g, folder):
    rows = []
    lib = {d.id:d for d in design.library}
    for i,f in enumerate(design.features,1):
        if f.suppressed:
            continue
        rows.append(dict(machining_id=f.machining_id or f'M{i:03}', feature=f.id, kind=f.kind, face=f.face,
                         u=f.u,v=f.v,diameter=f.diameter or '',depth=f.depth or lib[f.definition].stages[-1].end,
                         plug_length=f.plug_length if f.plugged else '',tooling='; '.join(lib[f.definition].tooling) if f.definition else 'Drill selection requires review'))
    with (folder/'drill-chart.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.DictWriter(handle,fieldnames=['machining_id','feature','kind','face','u','v','diameter','depth','plug_length','tooling'])
        writer.writeheader(); writer.writerows(rows)
    meets=[]
    for a,b in combinations(g.nodes,2):
        shape=g.nodes[a].intersect(g.nodes[b]); volume=shape.Volume()
        if volume > 1e-6:
            meets.append(dict(a=a,b=b,volume_mm3=round(volume,5),center_mm=shape.Center().toTuple(),same_net=g.circuits[a]==g.circuits[b]))
    flows=[]
    for n in design.nets:
        if n.flow_lpm:
            diameters=[f.diameter for f in design.features if f.kind=='drilling' and f.circuit==n.id and not f.suppressed]
            diameter=min(diameters,default=n.diameter)
            required=math.sqrt(4*(n.flow_lpm/60000)/(math.pi*n.velocity_limit))*1000
            flows.append(dict(net=n.id,flow_lpm=n.flow_lpm,minimum_drill_mm=diameter,velocity_m_s=round(n.flow_lpm/60000/(math.pi*(diameter/2000)**2),3),
                              suggested_standard_mm=next((d for d in sorted(design.constraints.standard_drills) if d>=required),None),
                              assumption='Full stated net flow through smallest bore; no branch distribution, valve loss or pressure rating calculation.'))
    (folder/'manufacturing.json').write_text(json.dumps(dict(status='ENGINEERING_REVIEW_REQUIRED',drill_chart=rows,meet_list=meets,velocity_screen=flows),indent=2),encoding='utf-8')
