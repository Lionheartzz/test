"""AI engineering-library binding through the same runtime SQLite master."""
import re
from ..engineering_db import compatible_cavity_ids,get_definition,search_cartridges,search_definitions
from .service import digest


def norm(value):return re.sub(r'[^a-z0-9]','',str(value).lower())


def summary(key,definition):
    return dict(key=key,sha256=digest(definition.model_dump()),label=definition.label,
                manufacturer=definition.manufacturer,role=definition.kind,zones=[z.model_dump() for z in definition.zones],
                usable=definition.usable,unit=definition.unit_system,unusable_reason=definition.unusable_reason)


def search(inputs,query='',role='cavity'):
    kind='port_definition' if role in ('external-port','port_definition') else 'cavity'
    rows=search_definitions(query=query,kind=kind,limit=20)['items']
    rows.sort(key=lambda row:(row['unit_system']!=inputs.project_context,row['name'],row['id']))
    return [summary('db:'+row['id'],get_definition(row['id'])) for row in rows]


def port_standard(value):
    text=str(value or '').upper().replace('"','').strip()
    standard=('NPTF' if 'NPTF' in text else 'NPT' if 'NPT' in text else
              'BSPT' if any(token in text for token in ('BSPT',' RC',' R ',' RP')) else
              'BSPP' if 'BSPP' in text or re.search(r'(^|\s)G\s*\d',text) else None)
    match=re.search(r'(?<!\d)(\d+(?:[ -]\d+/\d+|/\d+))(?!\d)',text)
    return (standard,re.sub(r'\s+','-',match.group(1)) if match else None)


def exact_port_candidates(inputs,specification):
    standard,size=port_standard(specification)
    if not standard or not size:return []
    rows=search_definitions(query=size.replace('-',' '),kind='port_definition',status='usable',limit=500)['items']
    result=[]
    for row in rows:
        row_standard,row_size=port_standard(' '.join((row['name'],row['family'],row['thread_spec'])))
        if (row_standard,row_size)==(standard,size):
            result.append(summary('db:'+row['id'],get_definition(row['id'])))
    return sorted(result,key=lambda row:(row['unit']!=inputs.project_context,row['label'],row['key']))


def load(inputs,key,sha=None):
    if not key.startswith('db:'):raise ValueError('AI generation accepts SQLite engineering IDs only')
    definition=get_definition(key[3:])
    if sha and digest(definition.model_dump())!=sha:raise ValueError('Selected definition changed. Search and confirm it again.')
    return definition


def value(result,subject,predicate):
    for row in [*result['components'],*result['ports'],*result['nets']]:
        if row['id']==subject:
            return row.get('label') if predicate=='label' else row.get('facts',{}).get(predicate)
    return None


def identity_value(result,subject,predicate):
    row=next((row for row in result['components'] if row['id']==subject),None)
    return row.get('facts',{}).get(predicate) if row and row.get('identity_valid',{}).get(predicate) else None


def candidates(inputs,result,component):
    model=identity_value(result,component['id'],'model');maker=identity_value(result,component['id'],'manufacturer')
    if not model:return []
    cartridges=search_cartridges(' '.join(x for x in (maker,model) if x),0,20)['items']
    matches=[row for row in cartridges if norm(row['model'])==norm(model) and (not maker or norm(maker) in norm(row['manufacturer']))]
    found=[]
    for cartridge in matches:
        for cavity_id in compatible_cavity_ids(cartridge['id']):
            definition=get_definition(cavity_id)
            found.append(dict(**summary('db:'+cavity_id,definition),cartridge_id=cartridge['id'],reason='Explicit SQLite cartridge-cavity relationship'))
    return found


def resolution_status(inputs,result,component,choices):
    usable=[row for row in choices if row['usable']]
    if not choices:return dict(code='relationship_missing',message='No explicit cartridge-cavity relationship exists in SQLite.',action='Select a cavity explicitly or import confirmed cartridge compatibility.',candidate_count=0,usable_count=0)
    if not usable:return dict(code='geometry_unusable',message='Compatible cavities exist but lack executable geometry.',action='Choose a usable cavity definition.',candidate_count=len(choices),usable_count=0)
    if len(usable)>1:return dict(code='ambiguous_cavities',message='Multiple compatible cavities exist.',action='Choose one cavity and map its interfaces.',candidate_count=len(choices),usable_count=len(usable))
    mapping=matching_zones(result,component,usable[0]['zones'])
    return dict(code='resolved' if mapping else 'window_mapping_required',message='One explicit compatible cavity was found.',action='Confirm the interface mapping.',candidate_count=len(choices),usable_count=1)


def matching_zones(result,component,zones):
    ports={p['id']:value(result,p['id'],'label') for p in result['ports'] if p['component_id']==component['id']}
    mapping={}
    for zone in zones:
        label=re.sub(r'^port','',norm(zone['id']))
        matches=[key for key,name in ports.items() if re.sub(r'^port','',norm(name))==label]
        if len(matches)!=1:return None
        mapping[zone['id']]=matches[0]
    return mapping if set(mapping.values())==set(component['port_ids']) else None
