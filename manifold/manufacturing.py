"""Inspection-only machining schedules from the exact resolved build."""
import csv
import json
import math
from itertools import combinations


def manufacturing_outputs(design, g, folder):
    rows = []
    profiles = []
    lib = {d.id:d for d in design.library}
    for i,f in enumerate(design.features,1):
        if f.suppressed:
            continue
        definition=lib.get(f.definition)
        steps=([s.model_dump() for s in definition.cutting_primitives] or
               [dict(kind='cylinder',**s.model_dump()) for s in definition.stages]) if definition else []
        profile=dict(feature=f.id,definition=f.definition,source=definition.source if definition else 'Explicit drilling parameters',
                     cutting_steps=steps,hydraulic_interfaces=[z.model_dump() for z in definition.zones] if definition else [],
                     cylinder_diameter_mm=None if definition else f.diameter,cylinder_depth_mm=None if definition else f.depth,
                     tip_angle_degrees=None if definition else f.tip_angle,
                     closure=dict(engagement_mm=f.plug_length,geometry='Declared cylindrical exclusion from hydraulic volume',
                                  entry_machining_status='unresolved',
                                  note='No mapped plug-entry machining profile is bound to this feature. Pinned raw plug/tool records are retained without inventing threads, counterbores or seats.') if f.plugged else None)
        profiles.append(profile)
        common=dict(machining_id=f.machining_id or f'M{i:03}', feature=f.id, kind=f.kind, face=f.face,
                         axis_x=g.placements[f.id]['direction'][0],axis_y=g.placements[f.id]['direction'][1],axis_z=g.placements[f.id]['direction'][2],
                         u=f.u,v=f.v,plug_length=f.plug_length if f.plugged else '',tooling='; '.join(definition.tooling) if definition else 'Drill selection requires review')
        if definition:
            for index,s in enumerate(steps,1):
                rows.append(dict(**common,operation=index,profile=s['kind'],diameter=s['diameter'],depth=s['end'],start=s['start'],
                                 end_diameter=s.get('end_diameter',''),inner_diameter=s.get('inner_diameter',''),
                                 offset_u=s.get('offset_u',0),offset_v=s.get('offset_v',0),tip_angle='',source=definition.source))
        else:
            rows.append(dict(**common,operation=1,profile='explicit-drilling',diameter=f.diameter,depth=f.depth,start=0,
                             end_diameter='',inner_diameter='',offset_u=0,offset_v=0,tip_angle=f.tip_angle,source='Explicit parameters; cylinder depth excludes drill point'))
    with (folder/'drill-chart.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.DictWriter(handle,fieldnames=['machining_id','feature','kind','face','axis_x','axis_y','axis_z','u','v','operation','profile','diameter','start','depth','end_diameter','inner_diameter','offset_u','offset_v','tip_angle','plug_length','tooling','source'])
        writer.writeheader(); writer.writerows(rows)
    meets=[]
    for a,b in combinations(g.nodes,2):
        shape=g.nodes[a].intersect(g.nodes[b]); volume=shape.Volume()
        if volume > 1e-6:
            from .flow import opening_area,equivalent_diameter
            area=opening_area(g.nodes[a],g.nodes[b],[g.placements[x.split(':')[0]]['direction'] for x in (a,b)])
            meets.append(dict(a=a,b=b,volume_mm3=round(volume,5),center_mm=shape.Center().toTuple(),same_net=g.circuits[a]==g.circuits[b],
                              characteristic_opening_mm2=round(area,5),equivalent_diameter_mm=round(equivalent_diameter(area),5),
                              method='Minimum axial common sections at overlap centroid; geometric screen, not minimum-throat certification'))
    flows=[]
    for n in design.nets:
        if n.flow_lpm:
            diameters=[f.diameter for f in design.features if f.kind=='drilling' and f.circuit==n.id and not f.suppressed]
            diameter=min(diameters,default=n.diameter)
            required=math.sqrt(4*(n.flow_lpm/60000)/(math.pi*n.velocity_limit))*1000
            flows.append(dict(net=n.id,flow_lpm=n.flow_lpm,minimum_drill_mm=diameter,velocity_m_s=round(n.flow_lpm/60000/(math.pi*(diameter/2000)**2),3),
                              suggested_standard_mm=next((d for d in sorted(design.constraints.standard_drills) if d>=required),None),
                              assumption='Full stated net flow through smallest bore; no branch distribution, valve loss or pressure rating calculation.'))
    native_recipes=[]
    for definition in design.library:
        if definition.native and any(f.definition==definition.id and not f.suppressed for f in design.features):
            native=definition.native
            native_recipes.append(dict(definition=definition.id,geometry_status=native.geometry_status,
                                      machining_status=native.machining_status,decision=native.machining_decision,
                                      native_units=native.record.unit_system,operations=native.record.machining,
                                      related_records=native.related_records,
                                      note='Legacy operands and tool codes are preserved, not executed or silently certified.'))
    (folder/'manufacturing.json').write_text(json.dumps(dict(status='ENGINEERING_REVIEW_REQUIRED',drill_chart=rows,meet_list=meets,velocity_screen=flows,
                                                           machining_profiles=profiles,native_recipes=native_recipes,pinned_resources=[r.model_dump() for r in design.library_resources]),indent=2),encoding='utf-8')
