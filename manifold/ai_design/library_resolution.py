"""AI engineering-library binding through the same runtime SQLite master."""
import re
from ..engineering_db import compatible_logical_cavities,get_definition,normalized_port_family,search_definitions,search_threads,thread_definition
from .cartridge_identity import resolve_cartridge_identity
from . import interface_catalog
from .service import digest


def norm(value):return re.sub(r'[^a-z0-9]','',str(value).lower())


def summary(key,definition):
    return dict(key=key,sha256=digest(definition.model_dump()),label=definition.label,
                display_label=interface_catalog.display_label(definition.label,definition.family),family=definition.family,
                manufacturer=definition.manufacturer,role=definition.kind,
                definition_origin='Custom definition' if definition.id.startswith('custom_') else
                                  'Legacy definition' if definition.id.startswith('legacy_') else 'Imported definition',
                machining_depth_mm=max([stage.end for stage in definition.stages]+
                                       [cut.end for cut in definition.cutting_primitives]+[0]),
                zones=[dict(**z.model_dump(),display_label=interface_catalog.hydraulic_label(z.id)) for z in definition.zones],
                usable=definition.usable,unit=definition.unit_system,unusable_reason=definition.unusable_reason,
                geometry_status='usable' if definition.usable else 'unusable')


def search(inputs,query='',role='cavity'):
    kind='port_definition' if role in ('external-port','port_definition') else 'cavity'
    rows=(interface_catalog.search(query,inputs.project_context) if kind=='cavity' else
          search_definitions(query=query,kind=kind,limit=20)['items'])
    rows.sort(key=lambda row:(row['unit_system']!=inputs.project_context,not row['usable'],row['name'],row['id']))
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


def resolve_thread_specification(specification):
    """Resolve a pipe-thread identity independently of sealing/port machining."""
    normalized=normalized_port_specification(specification)
    standard,size,pitch=normalized or (None,None,None)
    recognized=standard in ('BSPP','BSPT','NPT','NPTF') and bool(size)
    label=('G'+size+' BSPP' if standard=='BSPP' else ' '.join(x for x in (size,standard) if x)) or specification
    if not recognized:
        return dict(code='thread_not_specified',recognized=False,label=label,definition=None,physical_ids=[])
    matches=[]
    for row in search_threads(family=standard,limit=None):
        if row['applicability']!='internal':continue
        text=' '.join((row['display_name'],row['pitch_tpi'],standard))
        if port_standard(text)!=(standard,size):continue
        if pitch and _explicit_pitch(row['display_name'])!=pitch:continue
        matches.append(row)
    # Missing pitch/class is not a contradictory identity. Different explicit
    # identities remain ambiguous; tap-drill recipes do not imply a sealing form.
    forms={row['thread_form'] for row in matches if row['usable']}
    classes={row['thread_class'] for row in matches if row['usable'] and row['thread_class']}
    pitches={_explicit_pitch(row['display_name']) for row in matches if row['usable']} - {None}
    usable=[row for row in matches if row['usable'] and row['tap_diameter_mm'] is not None]
    if len(forms)>1 or len(classes)>1 or len(pitches)>1:
        code,chosen='thread_identity_ambiguous',None
    elif usable:
        designation='G'+size if standard=='BSPP' else size+' '+standard
        # Stable source-backed tap-drill proposal, not an assertion that all
        # source tap diameters or complete port forms are interchangeable.
        chosen=min(usable,key=lambda row:(norm(row['display_name'])!=norm(designation),bool(row['thread_class']),row['id']))
        code='resolved'
    else:
        code,chosen='thread_machining_unavailable' if matches else 'thread_definition_missing',None
    return dict(code=code,recognized=True,label=label,definition=chosen,
                physical_ids=sorted(row['id'] for row in matches))


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
    thread=resolve_thread_specification(specification)
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
    code=(('thread_defined' if thread['code']=='resolved' else thread['code']) if thread['recognized'] else
          'resolved' if len(choices)==1 else 'port_specification_ambiguous' if choices else 'port_definition_missing')
    return dict(code=code,thread_resolution=thread,
                specification=label,normalized=normalized,physical_count=len(rows),logical_count=len(choices),choices=choices,
                canonical=choices[0] if len(choices)==1 and not thread['recognized'] else None)


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


def display_label(result,row):
    label=value(result,row['id'],'label')
    if label and label!=row['id']:return str(label)
    if row in result['components']:
        return str(identity_value(result,row['id'],'model') or 'Component '+str(result['components'].index(row)+1))
    if row in result['ports']:
        peers=[p for p in result['ports'] if p['component_id']==row['component_id']]
        return str(label if label and label!=row['id'] else ('External port ' if row['component_id'] is None else 'Port ')+str(peers.index(row)+1))
    return str(label or 'Hydraulic line '+str(result['nets'].index(row)+1))


def component_identity(result,component):
    model=identity_value(result,component['id'],'model');maker=identity_value(result,component['id'],'manufacturer')
    identity=resolve_cartridge_identity(model,maker)
    declared=[(field,identity_value(result,component['id'],field)) for field in ('cavity','mounting_interface')]
    declared=[(field,value) for field,value in declared if value]
    identity['model_role']='product' if model else None
    # A source-backed designation can be placed in the wrong observation field.
    # Resolve the full literal against the typed runtime catalogue, without
    # splitting captions, mining display labels or guessing product compatibility.
    # Known/ambiguous product identities keep their product semantics.
    if identity['code']=='cartridge_identity_missing' and isinstance(model,str) and model.strip():
        interface_ids=interface_catalog.exact_ids(model)
        if interface_ids:
            declared.append(('model',model))
            identity.update(recognized_model=None,observed_model=model,model_role='engineering_interface')
    requirements=[value for _,value in declared]
    identity['interface_requirements']=requirements
    if requirements:
        matches=[interface_catalog.exact_ids(value,mounting=field=='mounting_interface') for field,value in declared]
        if any(not ids for ids in matches):identity['code']='interface_definition_missing'
        elif not set.intersection(*matches):identity['code']='interface_requirements_conflict'
        else:
            identity['interface_ids']=sorted(set.intersection(*matches))
            if identity['code']=='cartridge_identity_missing':
                identity.update(code='resolved',method='typed_engineering_interface' if identity['model_role']=='engineering_interface'
                                else 'explicit_engineering_interface',interface_only=True)
    return identity


def identity_interpretations(result):
    """Current catalogue interpretation for display, separate from saved facts."""
    interpretations={}
    for component in result['components']:
        identity=component_identity(result,component)
        if identity['model_role']=='engineering_interface':
            interpretations[component['id']]=dict(model_role=identity['model_role'],
                designation=identity['observed_model'])
    return interpretations


def candidates(inputs,result,component,identity=None,*,include_engineering_facts=True):
    identity=identity or component_identity(result,component)
    if identity['code']!='resolved':return []
    if identity.get('interface_only'):
        return [dict(**summary('db:'+key,get_definition(key)),logical_id='definition:'+key,
                     reason='Source-backed designation matched an existing engineering interface' if identity.get('model_role')=='engineering_interface'
                     else 'Explicit source-backed engineering interface') for key in identity['interface_ids']]
    matches=identity['candidates']
    found=[]
    from ..engineering_facts import facts_batch
    facts=facts_batch('cartridge',[row['id'] for row in matches]) if include_engineering_facts else {}
    for cartridge in matches:
        for candidate in compatible_logical_cavities(cartridge['id']):
            cavity_id = candidate['cavity_id']
            if identity.get('interface_ids') is not None and cavity_id not in identity['interface_ids']:continue
            definition=get_definition(cavity_id)
            found.append(dict(**summary('db:'+cavity_id,definition),cartridge_id=cartridge['id'],
                              logical_id=candidate['logical_id'],engineering_facts=facts.get(cartridge['id']),reason='Explicit SQLite cartridge-cavity relationship'))
    return found


def automatic_choice(inputs, choices, identity=None,*,require_usable=True):
    """Choose within one source-backed logical cavity and the requested unit only."""
    if identity and identity.get('interface_only'):
        if not choices:return None,'interface_definition_missing'
        usable=[row for row in choices if row['usable'] or not require_usable]
        if not usable:return None,'geometry_unusable'
        preferred={row['key']:row for row in usable if row['unit']==inputs.project_context}
        if not preferred:return None,'unit_context_unavailable'
        if len(preferred)>1:return None,'ambiguous_interfaces'
        return next(iter(preferred.values())),None
    groups={row.get('logical_id',row['key']) for row in choices}
    if not choices:return None,'relationship_missing'
    if len(groups)>1:return None,'ambiguous_cavities'
    usable=[row for row in choices if row['usable'] or not require_usable]
    if not usable:return None,'geometry_unusable'
    preferred={row['key']: row for row in usable if row['unit']==inputs.project_context}
    if len(preferred)!=1:return None,'unit_context_unavailable'
    return next(iter(preferred.values())),None


def resolution_status(inputs,result,component,choices,identity=None):
    identity=identity or component_identity(result,component)
    chosen,blocked=automatic_choice(inputs,choices,identity)
    if identity['code']!='resolved':blocked=identity['code']
    elif blocked=='relationship_missing' and identity.get('interface_requirements'):blocked='interface_compatibility_conflict'
    usable=[row for row in choices if row['usable']]
    messages={
        'cartridge_identity_missing':(f'Observed model “{identity["recognized_model"]}” has no runtime product identity match.' if identity['recognized_model'] else 'No source-backed product or machining interface was recognized.','Choose the existing machining interface for this component. Product identity and mounting interface are resolved separately.'),
        'cartridge_identity_ambiguous':('Multiple runtime cartridge identities match the recognized source identity.','Resolve the cartridge identity before automatic cavity selection.'),
        'interface_definition_missing':('The declared engineering interface has no exact runtime definition or standard-family match.','Search the interface catalogue or clarify the source designation; no geometry is inferred.'),
        'interface_requirements_conflict':('The declared cavity and mounting interface select different engineering definitions.','Resolve the source identity conflict before generation.'),
        'interface_compatibility_conflict':('The declared interface does not match the resolved cartridge compatibility whitelist.','Review the source model and interface; compatibility is not inferred from names.'),
        'ambiguous_interfaces':('The declared interface matches multiple physical definitions or port/orientation variants.','Select the required variant and confirm every hydraulic interface.'),
        'relationship_missing':('Cartridge resolved; no source-backed cavity relation is available.','Select a cavity explicitly or import confirmed cartridge compatibility.'),
        'geometry_unusable':('Matched engineering definitions lack executable geometry.','Choose a usable source definition.'),
        'ambiguous_cavities':('Multiple distinct logical cavities are compatible.','Choose one cavity and map its interfaces.'),
        'unit_context_unavailable':('No unique usable physical interface matches the project unit context.','Select a physical definition explicitly.'),
    }
    if blocked:
        message,action=messages[blocked]
        return dict(code=blocked,message=message,action=action,candidate_count=len(choices),usable_count=len(usable),identity=identity)
    contract=interface_port_contract(result,component,chosen['zones'])
    matched=contract['status']=='matched'
    message=('An engineering interface and matching physical unit were found.' if matched else
        f"The library fixes {contract['physical_port_count']} hydraulic interfaces; the analysis contains {contract['observed_port_count']} schematic terminal observations.")
    return dict(code='resolved' if matched else 'window_mapping_required',message=message,
        action='Ready for draft generation.' if matched else 'Resolve missing or unassigned schematic observations against the fixed library ports.',
        candidate_count=len(choices),usable_count=len(usable),identity=identity,port_contract=contract)


def interface_port_contract(result,component,zones):
    """Library windows define hardware; model ports are schematic observations."""
    canonical=lambda label:re.sub(r'^port','',norm(interface_catalog.hydraulic_label(label)))
    expected=[dict(id=z['id'],label=interface_catalog.hydraulic_label(z['id'])) for z in zones]
    observed=[dict(id=p['id'],label=str(value(result,p['id'],'label') or p['id']))
              for p in result['ports'] if p['component_id']==component['id']]
    mapping={};missing=[];ambiguous=[]
    for port in expected:
        matches=[p for p in observed if canonical(p['label'])==canonical(port['label'])]
        physical_matches=[p for p in expected if canonical(p['label'])==canonical(port['label'])]
        if len(matches)==1 and len(physical_matches)==1:mapping[port['id']]=matches[0]['id']
        elif not matches:missing.append(port['id'])
        else:ambiguous.append(port['id'])
    unassigned=[p for p in observed if p['id'] not in mapping.values()]
    complete=(len(mapping)==len(expected) and set(mapping.values())==set(component['port_ids']))
    return dict(source='engineering_library',physical_ports=expected,physical_port_count=len(expected),
        observed_ports=observed,observed_port_count=len(observed),mapping=mapping,missing_interfaces=missing,
        ambiguous_interfaces=ambiguous,unassigned_observations=unassigned,
        status='matched' if complete else 'port_count_conflict' if len(expected)!=len(observed) else 'port_labels_need_mapping')


def matching_zones(result,component,zones):
    contract=interface_port_contract(result,component,zones)
    return contract['mapping'] if contract['status']=='matched' else None


def interface_checks(inputs,result):
    """Read-only reconciliation for every admitted component identity/family.

    Port count never selects a product, logical cavity, unit or physical variant.
    Unusable geometry may expose its fixed ports but grants no execution access.
    """
    checks=[]
    for component in result['components']:
        identity=component_identity(result,component)
        choices=candidates(inputs,result,component,identity,include_engineering_facts=False)
        chosen,reason=automatic_choice(inputs,choices,identity)
        if not chosen:chosen,reason=automatic_choice(inputs,choices,identity,require_usable=False)
        reason=identity['code'] if identity['code']!='resolved' else reason
        check=dict(component_id=component['id'],component_label=display_label(result,component),
                   status='interface_unresolved',resolution_code=reason,execution_permission=False)
        if chosen and not reason and chosen['zones']:
            check.update(interface_port_contract(result,component,chosen['zones']),
                definition_key=chosen['key'],definition_label=chosen['display_label'],unit=chosen['unit'],
                geometry_usable=chosen['usable'])
        elif chosen and not chosen['zones']:check['resolution_code']='interface_data_incomplete'
        checks.append(check)
    return checks
