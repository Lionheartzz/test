"""Editable route adoption and conservative branch extension; never changes net intent."""
from .routing import resolve_design,authorize_generated_contacts
from .geometry import build_geometry
from .kinematics import FACE_AXES,pose
from .schema import Design

def freeze(design,net_id):
    if not any(n.id==net_id and n.routing=='automatic' for n in design.nets):
        raise ValueError('Choose an automatic hydraulic net')
    resolved,_=resolve_design(design)
    geometry=build_geometry(resolved)
    authorize_generated_contacts(resolved,geometry)
    result=design.model_copy(deep=True)
    result.features=[f for f in result.features if f.route_net!=net_id]
    for f in resolved.features:
        if f.route_net==net_id:
            f.route_net=None;f.frozen_net=net_id
            result.features.append(f)
    net=next(n for n in result.nets if n.id==net_id)
    net.routing='manual';net.construction_access=[]
    return Design.model_validate(result.model_dump())

def refine(design,feature_id,u,v):
    result=design.model_copy(deep=True)
    target=next((f for f in result.features if f.id==feature_id and f.frozen_net),None)
    if target is None:raise ValueError('Adopt the route for refinement first')
    old=target.model_copy(deep=True)
    target.u=u;target.v=v
    adjusted=[];notes=[]
    _,_,axis,_=FACE_AXES[target.face]
    origin,_=pose(target,result.block)
    if target.direction:
        notes.append('Angled drill moved without inferring branch changes; inspect exact connections.')
    else:
        for branch in result.features:
            if branch.id==target.id or branch.frozen_net!=target.frozen_net or branch.direction:continue
            if branch.id not in old.connects_to and old.id not in branch.connects_to:continue
            _,_,other_axis,_=FACE_AXES[branch.face]
            if other_axis==axis:continue
            shared=3-axis-other_axis
            branch_origin,branch_direction=pose(branch,result.block)
            if abs(origin[shared]-branch_origin[shared])>1e-5:
                notes.append(f'{branch.id}: lateral alignment changed; exact opening check decides connectivity.')
                continue
            distance=(origin[other_axis]-branch_origin[other_axis])*branch_direction[other_axis]
            if distance <= (branch.plug_length if branch.plugged else 0):
                notes.append(f'{branch.id}: new intersection is in the entry/plug region.');continue
            required=distance+target.diameter/2
            if required>branch.depth:
                branch.depth=required;adjusted.append(branch.id)
            target_distance=(branch_origin[axis]-origin[axis])*pose(target,result.block)[1][axis]
            if target_distance>0:target.depth=max(target.depth,target_distance+branch.diameter/2)
    result=Design.model_validate(result.model_dump())
    return result,adjusted,notes
