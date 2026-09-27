"""AI engineering-library binding through the same runtime SQLite master."""
import re
from ..engineering_db import compatible_logical_cavities,get_definition,normalized_port_family,search_cartridges,search_definitions
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
    standard=('SAE_J518' if 'J518' in text or re.search(r'\bSAE\s+FLANGE\b',text) else
              'ISO_6149' if '6149' in text else
              'SAE_ORB' if 'J1926' in text or 'SAE ORB' in text or re.search(r'#\s*\d+\s+SAE\b',text) else
              'NPTF' if 'NPTF' in text else 'NPT' if 'NPT' in text else
              'BSPT' if 'BSPT' in text or re.search(r'(?<![A-Z])(?:RC|RP|R)\s*\d',text) else
              'BSPP' if 'BSPP' in text or re.search(r'(?<![A-Z])G\s*\d',text) else None)
    if standard=='SAE_ORB':
        match=re.search(r'#\s*(\d+)\b',text)
        return standard, '#'+match.group(1) if match else None
    if standard=='ISO_6149':
        match=re.search(r'\bM\s*(\d+(?:\.\d+)?)\s*[X×]\s*(\d+(?:\.\d+)?)',text)
        return standard, 'M'+match.group(1)+'X'+match.group(2) if match else None
    if standard=='SAE_J518':
        code=re.search(r'\b(?:CODE\s*)?(61|62)\b',text)
        size=re.search(r'(?<!\d)(\d+(?:[- ]\d+\/\d+|\/\d+))(?!\d)',text)
        return standard, (code.group(1)+':'+re.sub(r'\s+','-',size.group(1))) if code and size else None
    if standard=='BSPT':
        match=re.search(r'(?<![A-Z])(RC|RP|R)\s*(\d+(?:[- ]\d+\/\d+|\/\d+)?)',text)
        return standard,match.group(1)+re.sub(r'\s+','-',match.group(2)) if match else None
    if standard=='BSPP':
        match=re.search(r'(?<![A-Z])G\s*(\d+(?:[- ]\d+\/\d+|\/\d+)?)',text)
        if not match:
            match=re.search(r'(?<!\d)(\d+(?:[- ]\d+\/\d+|\/\d+)?)\s*BSPP\b',text)
        if match:return standard,re.sub(r'\s+','-',match.group(1))
    match=re.search(r'(?<!\d)(\d+(?:[- ]\d+\/\d+|\/\d+)?)(?:-\d+(?:\.\d+)?)?\s*NPTF?\b',text)
    if not match and standard in ('NPT','NPTF'):
        match=re.search(r'\bNPTF?\s*(\d+(?:[- ]\d+\/\d+|\/\d+)?)',text)
    return standard,re.sub(r'\s+','-',match.group(1)) if match else None


def _explicit_pitch(value):
    match=re.search(r'(?<!\d)\d+(?:[- ]\d+/\d+|/\d+)?-(\d+(?:\.\d+)?)\s*NPTF?\b',str(value or '').upper())
    return match.group(1) if match else None


def exact_port_candidates(inputs,specification):
    standard,size=port_standard(specification)
    if not standard or not size:return []
    rows=search_definitions(kind='port_definition',status='usable',limit=1000)['items']
    result=[]
    for row in rows:
        if normalized_port_family(row)!=standard:continue
        row_standard,row_size=port_standard(' '.join((row['name'],row['family'],row['thread_spec'])))
        if ((row_standard,row_size)==(standard,size) and
                (not _explicit_pitch(specification) or _explicit_pitch(row['thread_spec'])==_explicit_pitch(specification))):
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
        for candidate in compatible_logical_cavities(cartridge['id']):
            cavity_id = candidate['cavity_id']
            definition=get_definition(cavity_id)
            found.append(dict(**summary('db:'+cavity_id,definition),cartridge_id=cartridge['id'],
                              logical_id=candidate['logical_id'],reason='Explicit SQLite cartridge-cavity relationship'))
    return found


def automatic_choice(inputs, choices):
    """Choose within one source-backed logical cavity and the requested unit only."""
    groups={row.get('logical_id',row['key']) for row in choices}
    if not choices:return None,'relationship_missing'
    if len(groups)>1:return None,'ambiguous_cavities'
    usable=[row for row in choices if row['usable']]
    if not usable:return None,'geometry_unusable'
    preferred={row['key']: row for row in usable if row['unit']==inputs.project_context}
    if len(preferred)!=1:return None,'unit_context_unavailable'
    return next(iter(preferred.values())),None


def resolution_status(inputs,result,component,choices):
    chosen,blocked=automatic_choice(inputs,choices)
    usable=[row for row in choices if row['usable']]
    messages={
        'relationship_missing':('No explicit cartridge-cavity relationship exists in SQLite.','Select a cavity explicitly or import confirmed cartridge compatibility.'),
        'geometry_unusable':('Compatible cavities exist but lack executable geometry.','Choose a usable cavity definition.'),
        'ambiguous_cavities':('Multiple distinct logical cavities are compatible.','Choose one cavity and map its interfaces.'),
        'unit_context_unavailable':('No unique usable physical cavity matches the project unit context.','Select a physical cavity explicitly.'),
    }
    if blocked:
        message,action=messages[blocked]
        return dict(code=blocked,message=message,action=action,candidate_count=len(choices),usable_count=len(usable))
    mapping=matching_zones(result,component,chosen['zones'])
    return dict(code='resolved' if mapping else 'window_mapping_required',message='One logical cavity and matching physical unit were found.',action='Confirm the interface mapping.',candidate_count=len(choices),usable_count=len(usable))


def matching_zones(result,component,zones):
    ports={p['id']:value(result,p['id'],'label') for p in result['ports'] if p['component_id']==component['id']}
    mapping={}
    for zone in zones:
        label=re.sub(r'^port','',norm(zone['id']))
        matches=[key for key,name in ports.items() if re.sub(r'^port','',norm(name))==label]
        if len(matches)!=1:return None
        mapping[zone['id']]=matches[0]
    return mapping if set(mapping.values())==set(component['port_ids']) else None
