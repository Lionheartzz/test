"""V1 velocity-based bore sizing; no source geometry or manufacturing selection."""
import math


def route_sizing(net, standard_drills):
    area=net.flow_lpm*1000/60/net.velocity_limit if net.flow_lpm else None
    required=math.sqrt(4*area/math.pi) if area is not None else None
    result=dict(mode=net.diameter_mode,required_area_mm2=area,required_diameter_mm=required,
                diameter_mm=net.diameter,status='MANUAL' if net.diameter_mode=='manual' or net.routing=='manual' else 'UNRESOLVED_FLOW')
    if net.routing=='manual' or net.diameter_mode=='manual':return result
    if required is None:return result
    sizes=sorted(set(d for d in standard_drills if math.pi*d*d/4+1e-9>=area))
    if not sizes:
        raise ValueError(f'{net.id}: hydraulic sizing unresolved: requires diameter >= {required:.3f} mm '
                         f'({area:.3f} mm²); no available standard drill is large enough. '
                         'Add an appropriate available drill or explicitly specify an engineer override.')
    return {**result,'diameter_mm':sizes[0],'status':'FLOW_SIZED'}
