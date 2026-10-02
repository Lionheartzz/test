"""AI engineering-library binding through the same runtime SQLite master."""
import re
from ..engineering_db import compatible_logical_cavities,get_definition,normalized_port_family,search_definitions,thread_definition
from .cartridge_identity import resolve_cartridge_identity
from .service import digest


def norm(value):return re.sub(r'[^a-z0-9]','',str(value).lower())


def summary(key,definition):
    return dict(key=key,sha256=digest(definition.model_dump()),label=definition.label,
                manufacturer=definition.manufacturer,role=definition.kind,zones=[z.model_dump() for z in definition.zones],
                usable=definition.usable,unit=definition.unit_system,unusable_reason=definition.unusable_reason,
                geometry_status='usable' if definition.usable else 'unusable')


def search(inputs,query='',role='cavity'):
    kind='port_definition' if role in ('external-port','port_definition') else 'cavity'
    rows=search_definitions(query=query,kind=kind,limit=20)['items']
    rows.sort(key=lambda row:(row['unit_system']!=inputs.project_context,row['name'],row['id']))
    return [summary('db:'+row['id'],get_definition(row['id'])) for row in rows]


def port_standard(value):
    text=re.sub(r'\s*/\s*','/',str(value or '').upper().replace('"','').replace('″','')).strip()
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
            match=re.search(r'(?<!\d)(\d+(?:[- ]\d+\/\d+|\/\d+)?)(?:-\d+(?:\.\d+)?)?\s*BSPP\b',text)
        if match:return standard,re.sub(r'\s+','-',match.group(1))
    match=re.search(r'(?<!\d)(\d+(?:[- ]\d+\/\d+|\/\d+)?)(?:-\d+(?:\.\d+)?)?\s*NPTF?\b',text)
    if not match and standard in ('NPT','NPTF'):
        match=re.search(r'\bNPTF?\s*(\d+(?:[- ]\d+\/\d+|\/\d+)?)',text)
    return standard,re.sub(r'\s+','-',match.group(1)) if match else None


def _explicit_pitch(value):
    text=str(value or '').upper().replace('"','').replace('″','')
    match=re.search(r'(?:G\s*)?(?<!\d)\d+(?:[- ]\d+/\d+|/\d+)?-(\d+(?:\.\d+)?)(?:\s*(?:NPTF?|BSPP)\b|$)',text)
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


def normalized_port_specification(specification):
    standard,size=port_standard(specification)
    if not standard or not size:return None
    return (standard,size,_explicit_pitch(specification))


def port_equivalence_signature(definition):
    """Compare executable mm geometry, installation and machining, not labels/IDs."""
    data=definition.model_dump();standard,size=port_standard(definition.thread_note or definition.label)
    thread=thread_definition(definition.thread_definition_id) if definition.thread_definition_id else None
    thread_semantics=None if thread is None else {k:thread.get(k) for k in
        ('normalized_family','thread_class','applicability','tapered','tap_diameter_mm','thread_form')}
    if thread_semantics is not None:
        pitch=re.search(r'-(\d+(?:\.\d+)?)(?![A-Z0-9])',thread['pitch_tpi'])
        thread_semantics['pitch_tpi']=pitch.group(1) if pitch else thread['pitch_tpi']
    cuts=[{k:v for k,v in p.items() if k!='source_ref'} for p in data['cutting_primitives']]
    machining=[]
    for operation in data['machining']:
        row=dict(operation)
        for key in ('diameter','depth'):
            if row.get(key+'_mm') is not None:row.pop(key,None)
        if row.get('operation','').upper()=='TAP' and row.get('diameter'):
            raw=str(row['diameter']);family,nominal=port_standard(raw)
            thread_class=re.search(r'-(\d+[A-Z]+)\s*$',raw.upper())
            row['diameter']=dict(family=family,nominal=nominal,pitch=_explicit_pitch(raw) or (thread_semantics or {}).get('pitch_tpi'),
                thread_class=thread_class.group(1) if thread_class else (thread_semantics or {}).get('thread_class'),
                other_spec=norm(raw) if family is None else None)
        machining.append(row)
    signature=dict(standard=standard,size=size,sealing_family=norm(definition.family),thread=thread_semantics,
        stages=data['stages'],cuts=cuts,zones=[{k:v for k,v in z.items() if k!='id'} for z in data['zones']],
        boundaries=data['boundaries'],clearance_diameter=definition.clearance_diameter,
        clearance_height=definition.clearance_height,machining=machining)
    def canonical(value):
        if isinstance(value,float):return round(value,9)
        if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)):return [canonical(v) for v in value]
        return value
    return digest(canonical(signature))


def resolve_port_specification(inputs,specification):
    normalized=normalized_port_specification(specification)
    rows=exact_port_candidates(inputs,specification) if normalized else []
    groups={}
    for row in rows:
        definition=get_definition(row['key'][3:])
        if not definition.active or not definition.usable or len(definition.zones)!=1:continue
        groups.setdefault(port_equivalence_signature(definition),[]).append(row)
    choices=[]
    for signature,physical in sorted(groups.items()):
        canonical=min(physical,key=lambda r:(not r['usable'],r['unit']!=inputs.project_context,r['key']))
        choices.append({**canonical,'equivalence_id':signature,'physical_ids':[r['key'][3:] for r in sorted(physical,key=lambda r:r['key'])]})
    choices.sort(key=lambda row:(row['unit']!=inputs.project_context,row['label'],row['key']))
    standard,size,_=normalized or (None,None,None)
    label=('G'+size+' BSPP' if standard=='BSPP' else ' '.join(x for x in (size,standard) if x)) or specification
    return dict(code='resolved' if len(choices)==1 else 'port_specification_ambiguous' if choices else 'port_definition_missing',
                specification=label,normalized=normalized,physical_count=len(rows),logical_count=len(choices),choices=choices,
                canonical=choices[0] if len(choices)==1 else None)


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


def component_identity(result,component):
    model=identity_value(result,component['id'],'model');maker=identity_value(result,component['id'],'manufacturer')
    return resolve_cartridge_identity(model,maker)


def candidates(inputs,result,component,identity=None):
    identity=identity or component_identity(result,component)
    if identity['code']!='resolved':return []
    matches=identity['candidates']
    found=[]
    from ..engineering_facts import facts_batch
    facts=facts_batch('cartridge',[row['id'] for row in matches])
    for cartridge in matches:
        for candidate in compatible_logical_cavities(cartridge['id']):
            cavity_id = candidate['cavity_id']
            definition=get_definition(cavity_id)
            found.append(dict(**summary('db:'+cavity_id,definition),cartridge_id=cartridge['id'],
                              logical_id=candidate['logical_id'],engineering_facts=facts[cartridge['id']],reason='Explicit SQLite cartridge-cavity relationship'))
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


def resolution_status(inputs,result,component,choices,identity=None):
    identity=identity or component_identity(result,component)
    chosen,blocked=automatic_choice(inputs,choices)
    if identity['code']!='resolved':blocked=identity['code']
    usable=[row for row in choices if row['usable']]
    messages={
        'cartridge_identity_missing':(f'Cartridge “{identity["recognized_model"]}” was recognized, but no runtime cartridge matches the available source-backed identities.' if identity['recognized_model'] else 'No source-backed cartridge model was recognized.','Select a cavity explicitly or provide a sourced identity connection.'),
        'cartridge_identity_ambiguous':('Multiple runtime cartridge identities match the recognized source identity.','Resolve the cartridge identity before automatic cavity selection.'),
        'relationship_missing':('Cartridge resolved; no source-backed cavity relation is available.','Select a cavity explicitly or import confirmed cartridge compatibility.'),
        'geometry_unusable':('Compatible cavities exist but lack executable geometry.','Choose a usable cavity definition.'),
        'ambiguous_cavities':('Multiple distinct logical cavities are compatible.','Choose one cavity and map its interfaces.'),
        'unit_context_unavailable':('No unique usable physical cavity matches the project unit context.','Select a physical cavity explicitly.'),
    }
    if blocked:
        message,action=messages[blocked]
        return dict(code=blocked,message=message,action=action,candidate_count=len(choices),usable_count=len(usable),identity=identity)
    mapping=matching_zones(result,component,chosen['zones'])
    return dict(code='resolved' if mapping else 'window_mapping_required',message='One logical cavity and matching physical unit were found.' if mapping else 'Cavity resolved; hydraulic window mapping needs an explicit engineering decision.',action='Ready for draft generation.' if mapping else 'Confirm the interface mapping.',candidate_count=len(choices),usable_count=len(usable),identity=identity)


def matching_zones(result,component,zones):
    ports={p['id']:value(result,p['id'],'label') for p in result['ports'] if p['component_id']==component['id']}
    mapping={}
    for zone in zones:
        label=re.sub(r'^port','',norm(zone['id']))
        matches=[key for key,name in ports.items() if re.sub(r'^port','',norm(name))==label]
        if len(matches)!=1:return None
        mapping[zone['id']]=matches[0]
    return mapping if set(mapping.values())==set(component['port_ids']) else None
