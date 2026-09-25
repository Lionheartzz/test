"""Velocity sizing with a separate source-backed manufacturing-tool choice."""
import math


def route_sizing(net, standard_drills=(), *, tools=None, required_depth=0, preferred_unit=''):
    area=net.flow_lpm*1000/60/net.velocity_limit if net.flow_lpm else None
    required=math.sqrt(4*area/math.pi) if area is not None else None
    result=dict(mode=net.diameter_mode,required_area_mm2=area,required_diameter_mm=required,
                diameter_mm=net.diameter,status='MANUAL' if net.diameter_mode=='manual' or net.routing=='manual' else 'UNRESOLVED_FLOW')
    if net.routing=='manual' or net.diameter_mode=='manual':return result
    if required is None:return result
    candidates=([row for row in tools if row['max_depth_mm']+1e-6>=required_depth] if tools is not None else
                [dict(id=None,diameter_mm=d,max_depth_mm=None) for d in standard_drills])
    candidates=sorted((row for row in candidates if math.pi*row['diameter_mm']**2/4+1e-9>=area),
                      key=lambda row:(row['diameter_mm'],0 if preferred_unit and row.get('unit_system')==preferred_unit else 1,
                                      row.get('max_depth_mm') or 0,row.get('id') or ''))
    if not candidates:
        raise ValueError(f'{net.id}: hydraulic sizing unresolved: requires diameter >= {required:.3f} mm '
                         f'({area:.3f} mm²); no source-backed drill reaches the required depth. '
                         'Add an appropriate available drill or explicitly specify an engineer override.')
    selected=candidates[0]
    return {**result,'diameter_mm':selected['diameter_mm'],'selected_tool_id':selected.get('id'),'status':'FLOW_SIZED'}
