"""Human-facing names for stable engineering identities.

Machine artifacts keep the original IDs.  This module is only for UI, drawings
and human-readable reports.
"""
import re


_FACE_ORDER={'left':0,'right':1,'front':2,'back':3,'bottom':4,'top':5}
_RULE_NAMES={
    'engineering_review':'Engineering review','schematic_conformance':'Schematic conformance',
    'cartridge_compatibility':'Cartridge compatibility','connected_interface':'Hydraulic interface connection',
    'circuit_connectivity':'Hydraulic net connectivity','minimum_feature_wall':'Minimum feature wall',
    'external_wall':'External wall','solid_validity':'Solid validity','solid_count':'Solid count',
    'step_round_trip':'STEP round trip','cavity_collision':'Cavity collision','pressure_strength':'Pressure strength',
}


def _features(design):
    return list(design.features if hasattr(design,'features') else design.get('features',[]))


def _get(value,key,default=None):
    return getattr(value,key,value.get(key,default) if isinstance(value,dict) else default)


def net_name(design,net_id):
    nets=design.nets if hasattr(design,'nets') else design.get('nets',[])
    row=next((n for n in nets if _get(n,'id')==net_id),None)
    return _get(row,'label') or net_id or 'Unassigned'


def _order(feature):
    return (_FACE_ORDER.get(_get(feature,'face'),99),_get(feature,'u',0) or 0,_get(feature,'v',0) or 0,
            _get(feature,'depth',0) or 0,str(_get(feature,'id','')))


def feature_name(design,feature):
    if feature is None:return 'Unknown feature'
    route=_get(feature,'route_net') or _get(feature,'frozen_net')
    if _get(feature,'kind')=='drilling' and route:
        peers=sorted((f for f in _features(design) if _get(f,'kind')=='drilling' and (_get(f,'route_net') or _get(f,'frozen_net'))==route),key=_order)
        referenced={str(target).split(':',1)[0] for peer in peers for target in (_get(peer,'connects_to',[]) or []) if ':' in str(target)}
        owners=sorted((f for f in _features(design) if _get(f,'kind')=='cavity' and not _get(f,'suppressed',False)
                       and (route in (_get(f,'interface_nets',{}) or {}).values() or _get(f,'id') in referenced)),key=_order)
        prefix=f'{feature_name(design,owners[0])}-{net_name(design,route)}' if len(owners)==1 else net_name(design,route)
        label=f'{prefix}{max(0,next((i for i,f in enumerate(peers) if _get(f,"id")==_get(feature,"id")),0))+1}'
        return label+(' · PLUG' if _get(feature,'plugged',False) else '')
    if _get(feature,'kind')=='port':
        if _get(feature,'schematic_id'):return _get(feature,'schematic_id')
        if _get(feature,'id') and not str(_get(feature,'id')).startswith('PORT_'):return _get(feature,'id')
        peers=sorted((f for f in _features(design) if _get(f,'kind')=='port' and _get(f,'circuit')==_get(feature,'circuit') and not _get(f,'suppressed',False)),key=_order)
        label=net_name(design,_get(feature,'circuit'))
        return label if len(peers)<=1 else f'{label}{max(0,next((i for i,f in enumerate(peers) if _get(f,"id")==_get(feature,"id")),0))+1}'
    components=getattr(design,'components',[])
    component=next((c for c in components if _get(c,'feature_id')==_get(feature,'id')),None)
    return _get(component,'label') or _get(feature,'id')


def interface_name(design,feature_id,interface_id,*,definition_only=False,index=0):
    feature=next((f for f in _features(design) if _get(f,'id')==feature_id),None)
    net=(_get(feature,'interface_nets',{}) or {}).get(interface_id) if feature else None
    if feature and net:return f'{feature_name(design,feature)}-{net_name(design,net)}'
    return f'Interface {index+1} · {interface_id}' if definition_only else f'{feature_id} · Interface {index+1}'


def review_name(value):
    text=str(value or '')
    if text=='PORT_SPEC':return 'External port specification'
    if text.startswith('REVIEW_'):return 'Engineering review item'
    return text


def identity_name(design,value):
    text=str(value or '')
    if text.startswith('F:'):text=text[2:].split(':step:')[0]
    feature=next((f for f in _features(design) if _get(f,'id')==text),None)
    if feature:return feature_name(design,feature)
    if ':' in text:
        owner,suffix=text.split(':',1)
        placed=next((f for f in _features(design) if _get(f,'id')==owner),None)
        if placed and _get(placed,'kind')=='cavity':
            ids=list((_get(placed,'interface_nets',{}) or {}).keys())
            return interface_name(design,owner,suffix,index=ids.index(suffix) if suffix in ids else 0)
    return review_name(text)


def rule_name(rule):
    return _RULE_NAMES.get(rule,re.sub(r'_+',' ',str(rule or '')).capitalize())
