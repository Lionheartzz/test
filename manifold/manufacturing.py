"""Inspection-only machining schedules from the exact resolved build."""
import csv
import json
import math
from itertools import combinations


def manufacturing_outputs(design, g, folder, definitions=None):
    rows = []
    profiles = []
    if definitions is None:
        from .engineering_db import definitions_for_design
        definitions=definitions_for_design(design)
    lib = definitions
    from .engineering_db import thread_definitions_for_design,closure_definitions_for_design,select_tool,resolve_machining_tools
    threads=thread_definitions_for_design(design)
    closures=closure_definitions_for_design(design)
    for i,f in enumerate(design.features,1):
        if f.suppressed:
            continue
        definition=lib.get(f.definition);thread=threads.get(f.thread_definition_id)
        steps=([s.model_dump() for s in definition.cutting_primitives] or
               [dict(kind='cylinder',**s.model_dump()) for s in definition.stages]) if definition else []
        effective_diameter=thread['tap_diameter_mm'] if thread else f.diameter
        point_depth=(0 if definition or (f.kind=='mounting' and f.through) or f.tip_angle==180 else
                     effective_diameter/2/math.tan(math.radians(f.tip_angle/2)))
        drill_depth=(f.depth+point_depth) if effective_diameter else None
        selected_tool=select_tool(effective_diameter,drill_depth,tool_type='drill',unit=design.project_context,exact_diameter=bool(thread)) if effective_diameter else None
        operation_tools=resolve_machining_tools(definition,design.project_context) if definition else []
        closure=closures.get(f.closure_definition_id)
        profile=dict(feature=f.id,definition=f.definition,source='PMC engineering database' if definition or thread else 'Explicit drilling parameters',
                      cutting_steps=steps,hydraulic_interfaces=[z.model_dump() for z in definition.zones] if definition else [],
                      definition_facts=(dict(id=definition.id,label=definition.label,thread_specification=definition.thread_note,
                                             machining_operations=definition.machining) if definition else None),
                      thread_facts=thread,cylinder_diameter_mm=None if definition else effective_diameter,cylinder_depth_mm=None if definition else f.depth,
                      drill_depth_mm=None if definition else drill_depth,
                      selected_tool=selected_tool,operation_tools=operation_tools,machining_modifiers=[p.model_dump() for p in f.machining_modifiers],
                     tip_angle_degrees=None if definition else f.tip_angle,
                     closure=(dict(id=closure['id'],display_name=closure['display_name'],model=closure['model'],engagement_mm=closure['engagement_mm'],
                                   machining=closure['machining'],envelope=closure['envelope'],entry_machining_status='resolved') if closure else
                              dict(engagement_mm=f.plug_length,geometry='Declared cylindrical exclusion from hydraulic volume',
                                   entry_machining_status='unresolved',
                                   note='No executable plug-entry machining profile is bound to this feature; threads, counterbores and seats remain unresolved.')) if f.plugged else None)
        profiles.append(profile)
        common=dict(machining_id=f.machining_id or f'M{i:03}', feature=f.id, kind=f.kind, face=f.face,
                         axis_x=g.placements[f.id]['direction'][0],axis_y=g.placements[f.id]['direction'][1],axis_z=g.placements[f.id]['direction'][2],
                         u=f.u,v=f.v,plug_length=f.plug_length if f.plugged else '',
                         thread=thread['display_name'] if thread else '',thread_depth=f.thread_depth if thread else '',
                         port_spec=(definition.thread_note or definition.label) if definition and f.kind=='port' else '',
                         closure=closure['display_name'] if closure else ('UNRESOLVED' if f.plugged else ''),
                         tooling=(selected_tool['id'] if selected_tool else
                                  '; '.join(f"{row['operation_name']}: {row['tool']['id'] if row['tool'] else 'UNRESOLVED'}" for row in operation_tools)
                                  if operation_tools else 'No source-backed tool reaches the required diameter/depth'))
        if definition:
            for index,s in enumerate(steps,1):
                rows.append(dict(**common,operation=index,profile=s['kind'],diameter=s['diameter'],depth=s['end'],start=s['start'],
                                 end_diameter=s.get('end_diameter',''),inner_diameter=s.get('inner_diameter',''),
                                 offset_u=s.get('offset_u',0),offset_v=s.get('offset_v',0),tip_angle='',source='PMC engineering database'))
        else:
            rows.append(dict(**common,operation=1,profile='thread-tap-drill' if thread else 'explicit-drilling',diameter=effective_diameter,depth=f.depth,start=0,
                             end_diameter='',inner_diameter='',offset_u=0,offset_v=0,tip_angle=f.tip_angle,source='Explicit parameters; cylinder depth excludes drill point'))
    with (folder/'drill-chart.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.DictWriter(handle,fieldnames=['machining_id','feature','kind','face','axis_x','axis_y','axis_z','u','v','operation','profile','diameter','start','depth','end_diameter','inner_diameter','offset_u','offset_v','tip_angle','plug_length','thread','thread_depth','port_spec','closure','tooling','source'])
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
            tool=select_tool(required,max((f.depth for f in design.features if f.kind=='drilling' and f.circuit==n.id and not f.suppressed),default=0),tool_type='drill',unit=design.project_context)
            flows.append(dict(net=n.id,flow_lpm=n.flow_lpm,hydraulic_minimum_mm=required,selected_tool=tool,
                              minimum_drill_mm=diameter,velocity_m_s=round(n.flow_lpm/60000/(math.pi*(diameter/2000)**2),3),
                              suggested_standard_mm=tool['diameter_mm'] if tool else None,
                              assumption='Full stated net flow through smallest bore; no branch distribution, valve loss or pressure rating calculation.'))
    native_recipes=[dict(definition=d.id,unit_system=d.unit_system,operations=d.machining)
                    for d in definitions.values() if any(f.definition==d.id and not f.suppressed for f in design.features)]
    stock=dict(material_id=design.block.material_id,material=design.block.material,stock_id=design.block.stock_id,
               finished_dimensions_mm=[design.block.length,design.block.width,design.block.height],
               stock_dimensions_mm=design.block.stock_dimensions,required_machining_allowance_mm=design.block.machining_allowance,
               actual_stock_excess_mm=design.block.stock_excess)
    (folder/'manufacturing.json').write_text(json.dumps(dict(status='ENGINEERING_REVIEW_REQUIRED',drill_chart=rows,meet_list=meets,velocity_screen=flows,
                                                           machining_profiles=profiles,native_recipes=native_recipes,stock=stock,
                                                           engravings=[row.model_dump() for row in design.engravings],
                                                           block_modifiers=[row.model_dump() for row in design.block_modifiers]),indent=2),encoding='utf-8')
