"""Read-only, engineer-facing Library views. Research records never grant actions."""
from __future__ import annotations

import base64
from contextlib import closing
import json
import re

from .engineering_db import _connect

# One category per domain, independent of research folder names.
CATEGORIES = [
    ('cavities','Cavities','Cavity machining definitions, interfaces and engineering data.','cavities','Non-relation Cavity Knowledge'),
    ('cartridges','Cartridges','Valve identities, technical properties and compatible cavities.','cartridges',None),
    ('external-ports','External Ports','Hydraulic port definitions, threads, sealing and machining data.','external_port_definitions','External Ports'),
    ('threads','Threads','Thread designations, standards and machining reference data.','thread_definitions','Thread Standards'),
    ('materials','Materials & Stock','Engineering materials, properties and available stock sizes.','materials',None),
    ('tooling','Tooling','Drills, flat-bottom drills, spotface cutters and tooling data.','tool_definitions','Tooling'),
    ('closures','Closures & Plugs','Closure and plug products, interfaces and engineering data.','closure_definitions','Closures / Plugs'),
    ('modifiers','Machining Modifiers','O-ring grooves, counterbores, undercuts and machining data.','machining_modifiers','Machining Knowledge'),
    ('seals','Seals & O-rings','Seal sizes, materials, fluids and backup-ring information.',None,'Seals / O-rings / Backup Rings'),
    ('fittings','Fittings & Adapters','Fitting products, connections and engineering dimensions.',None,'Fittings / Adapters / Port Hardware'),
    ('fasteners','Fasteners & Mounting','Bolts, mounting hardware, sizes and assembly information.',None,'Fasteners / Mounting Hardware'),
    ('fluids','Hydraulic Fluids','Fluid types, properties and compatibility information.',None,'Hydraulic Fluids / Compatibility'),
    ('surface-treatments','Surface Treatments','Coatings, material applicability and finish specifications.',None,'Surface Treatments / Coatings'),
    ('standards','Standards','Standard designations, editions and engineering applicability.',None,'Standards Registry'),
    ('cross-references','Cross References','Explicit product and designation relationships.',None,'Cross-reference / Equivalence'),
    ('inspection','Inspection & QA','Inspection methods, test requirements and acceptance criteria.',None,'Inspection / Pressure Test / QA'),
    ('manufacturing','Manufacturing & DFM','Manufacturing guidance and process requirements.',None,'Manufacturing Policy / DFM'),
    ('documentation','Production Documentation','Drawing callouts and manufacturing document requirements.',None,'Production Drawing / Manufacturing Documentation'),
    ('commercial','Commercial & Cost','Dated supplier prices, quantities and lead-time information.',None,'Commercial / Cost'),
    ('suppliers','Manufacturers & Suppliers','Product families, availability and supplier information.',None,'Manufacturer / Supplier / Lifecycle Registry'),
]
DOMAIN_CATEGORY = {r[4]:r[0] for r in CATEGORIES if r[4]}
INTERNAL = re.compile(r'\b(?:cav_[\w-]+|cart_[\w-]+|RAWTHREAD-[\w-]+|(?:EV|SRC|XREF|REL|DATA|SUP|STD)-[\w:.-]+|[a-f0-9]{32,64})\b',re.I)
JARGON = re.compile(r'\b(?:NOT_REPORTED\w*|NOT_STATED\w*|NOT_SPECIFIED\w*|NOT_AVAILABLE\w*|UNKNOWN|UNRESOLVED|REFERENCE_ONLY\w*|NOT_VERIFIED\w*)\b',re.I)


def text(value):
    """Scalar engineering text only; no raw objects, archive locations or keys."""
    if not isinstance(value,(str,int,float)) or isinstance(value,bool):
        return ''
    value=str(value).strip()
    value={'BSPP_G':'G (BSPP)','BSPT_RC':'Rc','BSPT_RP':'Rp','METRIC_M':'Metric M',
           'UN_SERIES_UNRESOLVED_PITCH_CLASS':'UN · class not specified'}.get(value,value)
    if not value or value.startswith(('{','[')) or '://' in value or re.search(r'[A-Z]:[\\/]',value):
        return ''
    value=INTERNAL.sub('',value)
    if JARGON.search(value):
        return ''
    if re.search(r'(?i)\b(?:evidence|provenance|verification|hard gate|gate [ABC]|sha256|research|source ladder)\b',value):
        return ''
    return re.sub(r'\s+',' ',value).strip(' |;')[:600]


def record_key(identifier):
    return base64.urlsafe_b64encode(identifier.encode()).decode().rstrip('=')


def record_id(key):
    try:
        value=base64.b64decode(key+'='*(-len(key)%4),altchars=b'-_',validate=True).decode()
        if record_key(value)!=key or len(value)>300:
            raise ValueError
        return value
    except (ValueError,UnicodeError):
        raise ValueError('Knowledge record not available') from None


def categories(*, path=None):
    with closing(_connect(path)) as db:
        counts=dict(db.execute('SELECT domain,count(*) FROM library_targets WHERE domain<>? GROUP BY domain',('CAD / Assets',)))
        items=[]
        for key,label,description,table,domain in CATEGORIES:
            count=None;error=False
            if table:
                try:
                    where=' WHERE active=1' if table!='cartridges' else ''
                    if key=='materials':where+=' AND id NOT IN (\'material_1\',\'material_2\')'
                    count=db.execute('SELECT count(*) FROM '+table+where).fetchone()[0]
                except Exception:
                    error=True  # A local count cannot take down other categories.
            knowledge=counts.get(domain,0)
            items.append(dict(key=key,label=label,description=description,definition_count=count,
                              knowledge_count=knowledge,browse_mode='knowledge' if table is None or count==0 and knowledge else 'definitions',
                              count_unavailable=error))
        unknown=set(counts)-DOMAIN_CATEGORY.keys()
        if unknown:
            items.append(dict(key='other-knowledge',label='Additional Engineering Data',
                description='Additional engineering information.',definition_count=None,
                knowledge_count=sum(counts[d] for d in unknown),browse_mode='knowledge',count_unavailable=False))
        return dict(items=items)


# Labels/fields are explicit presentation choices, never all-column dumps.
COMMON={'manufacturer':'Manufacturer','part_number':'Part number','model':'Model','type':'Type',
        'product_type':'Type','family':'Family','material':'Material','seal':'Seal',
        'interface':'Interface','thread':'Thread','raw_thread_spec':'Thread','temperature':'Temperature',
        'pressure':'Operating pressure','pressure_rating':'Operating pressure','torque':'Installation torque'}
FIELDS={
    'closures':COMMON | {'function':'Function'},
    'external-ports':{'raw_name':'Port','raw_family':'Family','raw_thread_spec':'Thread','thread_family':'Thread family',
        'nominal_size':'Port size','sealing_method':'Sealing method','port_family_sealing_method':'Sealing method'},
    'threads':{'designation_raw':'Designation','thread_family':'Family','standard_family':'Family','nominal_size':'Nominal size',
        'pitch':'Pitch','pitch_tpi':'Pitch / TPI','taper_parallel':'Form','standard':'Standard','standard_candidate':'Standard','tap_drill':'Tap drill'},
    'seals':{'dash_number':'Size','seal_type':'Seal type','material_name':'Material','material':'Material',
        'normal_temperature_range':'Temperature range','short_period_temperature':'Short-period temperature',
        'fluid':'Fluid','compound':'Compound','size':'Size','series':'Series','backup_ring':'Backup ring',
        'inner_diameter':'Inner diameter','outer_diameter':'Outer diameter','o_ring_width':'Cross-section',
        'groove_width':'Groove width','groove_length':'Groove depth','groove_radius':'Groove radius','groove_outer_diameter':'Groove outer diameter'},
    'fittings':COMMON | {'end_1':'Connection 1','end_2':'Connection 2','finish':'Finish'},
    'fasteners':{'type':'Type','size':'Size','material':'Material','grade':'Grade','class':'Class','code':'Flange code',
        'flange_dash':'Flange size','unc_bolt':'UNC bolt','metric_bolt':'Metric bolt','standard_family':'Standard',
        'parker_assembly_torque_Nm_plus10_minus0':'Parker assembly torque / Nm (+10% / −0%)'},
    'fluids':{'observed_label':'Fluid','normalized_label':'Classification','viscosity':'Viscosity','density':'Density',
        'temperature':'Temperature','compatibility':'Compatibility','fluid':'Fluid','compound':'Compound'},
    'surface-treatments':{'treatment':'Treatment','material':'Applicable material','standard':'Specification',
        'coating_thickness':'Thickness','hardness':'Hardness','dimensional_allowance':'Dimensional allowance'},
    'standards':{'body':'Standards body','number':'Designation','title':'Title','revision':'Edition', 'domains':'Engineering applicability'},
    'cross-references':{'relation_type':'Relationship'},
    'inspection':{'inspection_category':'Inspection','instrument_or_method':'Method','rule_statement':'Requirement',
        'acceptance_criteria':'Acceptance criteria','pressure_basis_or_value':'Test pressure','duration_temperature_cycles':'Duration / temperature',
        'medium':'Test medium','limitations':'Application limits'},
    'manufacturing':{'rule_statement':'Guidance','operation':'Process','feature':'Feature','requirement':'Requirement','limitations':'Application limits'},
    'documentation':{'required_category':'Document item','structured_semantics':'Requirement','metric_inch_example_pattern':'Engineering example'},
    'commercial':{'supplier':'Supplier','entity_name':'Item','currency':'Currency','price':'Price','price_date':'Date',
        'quantity_basis':'Quantity basis','MOQ':'Minimum quantity','lead_time':'Lead time','region':'Region'},
    'suppliers':{'canonical_name':'Name','entity_type':'Type','product_family':'Product family','lifecycle_status':'Availability','region':'Region'},
    'modifiers':{'operation':'Process','tool':'Tool','diameter':'Diameter','diameter_mm':'Diameter / mm','depth':'Depth',
        'angle':'Angle','rule_statement':'Guidance','condition':'Application','material':'Material'},
    'cavities':{'cavity_name':'Cavity','tool':'Tool','bore_diameter':'Bore diameter','tolerance':'Tolerance','minimum_opening':'Minimum opening','thread':'Thread'},
    'tooling':{'manufacturer':'Manufacturer','part_number':'Part number','tool_type':'Tool type','diameter':'Diameter',
        'diameter_mm':'Diameter / mm','depth':'Depth','angle':'Angle','material':'Material','speed':'Cutting speed','feed':'Feed'},
}
FIELDS['cavities'].update(raw_name='Cavity',raw_family='Family',raw_thread_spec='Thread',document_number='Applicable standard')
FIELDS['tooling'].update(product_name='Tool',edp='Part number',exact_tool_identity_and_catalog_dimensions='Dimensions',
    manufacturer_speed_feed_recommendation='Cutting data',exact_tool_identity_and_manufacturer_specifications='Tool specifications')
FIELDS['inspection'].update(manufacturer_deburring_and_cleaning_operations='Manufacturer guidance',
    preinstallation_valve_cavity_condition_check='Before installation',cross_drill_intersection_borescope_inspection='Channel inspection',
    inspection_before_assembly='Before assembly',published_test_scope_boundary='Test applicability')
FIELDS['manufacturing'].update(blind_hole_tap_chamfer_and_effective_thread_depth='Blind-hole tap depth',
    bottom_tap_requirement='Bottom tap',burr_control='Burr control',manufacturer_deburring_and_cleaning_operations='Cleaning process',
    manufacturer_cavity_opening_and_first_thread_quality='Cavity opening',manifold_block_washdown_before_valve_installation='Before installation')
FIELDS['documentation'].update(mounting_surface_flatness_callout_example='Flatness example',
    manufacturer_scoped_drawing_unit_note_example='Drawing units',source_scoped_qualitative_deburr_edge_note='Edge requirement',
    blind_hole_tap_drill_allowance='Blind-hole tap allowance',thread_engagement='Thread engagement')
FIELDS['standards'].update(document_number='Designation',standard_identity_scope_or_lifecycle_metadata='Edition / application')
MASTER_FILES={
    'closures':['CLOSURE_MASTER.csv','CLOSURE_PRODUCTS_V2.csv'],
    'external-ports':['PORT_MASTER.csv'], 'threads':['THREAD_MASTER.csv'],
    'seals':['SEAL_GROOVE_MASTER.jsonl','SEAL_SIZE_MASTER_V2.csv','SEAL_MATERIAL_MASTER_V2.csv'],
    'fittings':['FITTING_MASTER.csv'], 'fasteners':['FASTENER_MASTER.csv','FASTENER_SAE_FLANGE_BOLT_MAP_V2.csv'],
    'fluids':['HYDRAULIC_FLUID_MASTER_V2.csv'], 'surface-treatments':['SURFACE_TREATMENT_MASTER.jsonl'],
    'standards':['STANDARDS_MASTER.csv'], 'cross-references':['CROSS_REFERENCE_MASTER.csv'],
    'inspection':['INSPECTION_MASTER.csv','INSPECTION_RULES.jsonl'],
    'manufacturing':['MANUFACTURING_POLICY_MASTER.csv','MACHINING_REUSABLE_RULES_V2.csv'],
    'documentation':['DRAWING_KNOWLEDGE_TARGETS_V2.csv'], 'commercial':['COMMERCIAL_SNAPSHOT.csv'],
    'suppliers':['SUPPLIER_ENTITY_REGISTRY_V2.csv'], 'modifiers':['MACHINING_REUSABLE_RULES_V2.csv'],
    'cavities':['CAVITY_NONREL_AUDIT.jsonl'], 'tooling':['TOOLING_MASTER.jsonl'],
}
IDENTITY_FIELDS=('entity_id','product_id','target_id','thread_id','fitting_id','fluid_id','standard_id','link_id','supplier_id','material_family_id')


def _master_rows(db,target,category):
    identifiers={target['id']}
    prefixes={'closures':['CLOSURE-FAMILY-','PRODUCT-CLOSURE-'],'external-ports':['PORT-'],
              'seals':['GROOVE-'],'fittings':['FITTING-'],'standards':['STD-EDITION-']}
    identifiers.update(target['id'].removeprefix(p) for p in prefixes.get(category,[]) if target['id'].startswith(p))
    files=MASTER_FILES.get(category,[])
    if not files:return []
    datasets=[r[0] for name in files for r in db.execute('SELECT id FROM library_datasets WHERE archive_path LIKE ?',('%/'+name,))]
    if not datasets:return []
    predicates=[];args=list(datasets)
    for field in IDENTITY_FIELDS:
        predicates.append('json_extract(original_json,\'$.'+field+'\') IN ('+','.join('?' for _ in identifiers)+')')
        args.extend(sorted(identifiers))
    query='SELECT original_json FROM library_records WHERE dataset_id IN ('+','.join('?' for _ in datasets)+') AND ('+' OR '.join(predicates)+') LIMIT 12'
    return [json.loads(r[0]) for r in db.execute(query,args)]


def _reference_name(db,identifier):
    for table,name in [('external_port_definitions','name'),('cavities','name')]:
        row=db.execute('SELECT '+name+' FROM '+table+' WHERE id=?',(identifier,)).fetchone()
        if row and text(row[0]):return text(row[0])
    datasets=[r[0] for r in db.execute("SELECT id FROM library_datasets WHERE archive_path LIKE '%/THREAD_MASTER.csv'")]
    for dataset in datasets:
        row=db.execute("SELECT json_extract(original_json,'$.designation_raw') FROM library_records WHERE dataset_id=? AND json_extract(original_json,'$.thread_id')=? LIMIT 1",(dataset,identifier)).fetchone()
        if row and text(row[0]):return text(row[0])
    for name in ['TOOLING_MASTER.jsonl','CAVITY_NONREL_AUDIT.jsonl']:
        datasets=[r[0] for r in db.execute('SELECT id FROM library_datasets WHERE archive_path LIKE ?',('%/'+name,))]
        for dataset in datasets:
            row=db.execute("SELECT original_json FROM library_records WHERE dataset_id=? AND (native_id=? OR json_extract(original_json,'$.entity_id')=?) LIMIT 1",(dataset,identifier,identifier)).fetchone()
            if row:
                r=json.loads(row[0])
                for key in ['part_number','model','name','raw_name','label']:
                    if text(r.get(key)):return text(r[key])
    return ''


def _name(target,records,category,db):
    if category=='cross-references' and records:
        r=records[0]
        source,target_name=_reference_name(db,r.get('source_entity_id','')),_reference_name(db,r.get('target_entity_id',''))
        if source and target_name:return source+' → '+target_name
        if INTERNAL.search(target['raw_identity']):
            return {'OBSERVED_RAW_THREAD_SPEC_SAME_SOURCE_ROW':'Observed thread designation',
                    'MANUFACTURER_EXPLICIT_TOOL_FOR_CAVITY':'Tool / cavity relationship'}.get(r.get('relation_type'),'Engineering designation relationship')
    for r in records:
        if category=='seals' and r.get('dash_number'):
            return 'O-ring groove '+str(r['dash_number'])+' · '+('Inch' if r.get('unit_system')=='inch' else 'Metric')
        for key in ['raw_name','part_number','designation_raw','number','material_name','normalized_label','canonical_name']:
            if text(r.get(key)):
                manufacturer=text(r.get('manufacturer'))
                return ' '.join(v for v in [manufacturer,text(r[key])] if v)
    raw=target['raw_identity'].replace(target['id'],'').split('{',1)[0]
    # Drop internal fragments from combined raw identities, never use the key.
    values=[text(v) for v in raw.split('|') if text(v) and not v.strip().startswith('STD-')]
    return (' · '.join(values) or 'Engineering information').replace('_',' ')


def _fields(records,category):
    fields=[];seen=set();allowed=FIELDS.get(category,{})
    def visit(row):
        if not isinstance(row,dict):return
        for key,label in allowed.items():
            value=row.get(key)
            if isinstance(value,dict):
                number=value.get('value',value.get('mm'))
                value=f'{number} {value.get("unit","mm")}' if number is not None else ''
            value=text(value)
            if value and (label,value) not in seen:
                fields.append(dict(label=label,value=value));seen.add((label,value))
        for key in ('geometry','record','dimensions'):
            visit(row.get(key))
        for attribute in row.get('exact_manufacturer_attributes',[]):
            if isinstance(attribute,dict) and re.search(r'(?i)diameter|length|flutes|threads|tap drill|projection',str(attribute.get('name',''))):
                label,value=text(attribute.get('name')),text(attribute.get('value'))
                if label and value and (label,value) not in seen:
                    fields.append(dict(label=label,value=value));seen.add((label,value))
    for record in records:visit(record)
    return fields[:40]


def _present(db,target,*,full=False):
    category=DOMAIN_CATEGORY.get(target['domain'],'other-knowledge')
    original=json.loads(target['original_json'])
    masters=_master_rows(db,target,category)
    records=[original.get('increment_disposition',{}),*masters]
    if full:
        # Only explicitly chosen scalar properties from linked records can reach
        # the presentation. No quotes, provenance, raw bodies or diagnostic rows.
        for (raw,) in db.execute('''SELECT e.original_json FROM library_evidence e
            JOIN library_target_evidence l ON l.evidence_id=e.id WHERE l.target_id=? ORDER BY e.id''',(target['id'],)):
            e=json.loads(raw);value=e.get('normalized_value') or e.get('raw_value')
            if isinstance(e.get('raw_value'),str) and e['raw_value'].startswith('{'):
                try:value=json.loads(e['raw_value'])
                except (ValueError,TypeError):pass
            if isinstance(value,str) and value.startswith(('{','[')):
                try:value=json.loads(value)
                except (ValueError,TypeError):continue
            if isinstance(value,dict):records.append(value)
            elif e.get('property') in FIELDS.get(category,{}):
                records.append({e['property']:str(value)+' '+str(e.get('normalized_unit') or e.get('raw_unit') or '')})
    fields=_fields(records,category)
    kind=next((text(r.get('product_type') or r.get('type') or r.get('thread_family') or r.get('standard_family')) for r in records
               if text(r.get('product_type') or r.get('type') or r.get('thread_family') or r.get('standard_family'))),'')
    result=dict(key=record_key(target['id']),name=_name(target,masters,category,db),family=kind,
                status='Verified' if target['status']=='VERIFIED' else 'Partial data',
                key_data=' · '.join(f['label']+': '+f['value'] for f in fields[:2]))
    if full:
        if category=='cross-references' and masters:
            relation=masters[0].get('relation_type','')
            fields=[dict(label=label,value=value) for label,value in [('From',_reference_name(db,masters[0].get('source_entity_id',''))),
                    ('To',_reference_name(db,masters[0].get('target_entity_id',''))),
                    ('Relationship','Observed thread designation' if relation=='OBSERVED_RAW_THREAD_SPEC_SAME_SOURCE_ROW' else text(relation.replace('_',' ').lower()))] if value]
        # Keep dimensions/prices attached to their exact product or dated item.
        related=[r for r in records if r.get('product_name') or r.get('supplier') and r.get('price')]
        if related:
            groups=[]
            for row in related[:12]:
                data=_fields([row],category)
                if data:groups.append(dict(title=text(row.get('product_name')) or 'Supplier price snapshot',fields=data))
            result['groups']=groups or [dict(title='Engineering Data',fields=fields)]
        else:result['groups']=[dict(title='Engineering Data',fields=fields)]
    return result


def browse(category,*,q='',status='',offset=0,limit=40,path=None):
    domain=next((r[4] for r in CATEGORIES if r[0]==category),None)
    with closing(_connect(path)) as db:
        if category=='other-knowledge':
            where='domain NOT IN ('+','.join('?' for _ in DOMAIN_CATEGORY)+') AND domain<>?'
            args=[*DOMAIN_CATEGORY,'CAD / Assets']
        elif domain:
            where='domain=?';args=[domain]
        else:raise ValueError('Knowledge category not available')
        if status:
            where+=' AND status=?';args.append(status)
        if q:
            where+=''' AND (instr(lower(raw_identity),lower(?))>0 OR
                instr(lower(json_extract(original_json,'$.increment_disposition.audited_product_key')),lower(?))>0 OR
                EXISTS(SELECT 1 FROM library_target_evidence l JOIN library_evidence e ON e.id=l.evidence_id
                    WHERE l.target_id=library_targets.id AND instr(lower(json_extract(e.original_json,'$.source_author')),lower(?))>0))'''
            args.extend([q,q,q])
        total=db.execute('SELECT count(*) FROM library_targets WHERE '+where,args).fetchone()[0]
        rows=db.execute('SELECT * FROM library_targets WHERE '+where+' ORDER BY raw_identity,id LIMIT ? OFFSET ?',args+[limit,offset])
        return dict(items=[_present(db,r) for r in rows],total=total,offset=offset,limit=limit)


def detail(key,*,path=None):
    identifier=record_id(key)
    with closing(_connect(path)) as db:
        target=db.execute('SELECT * FROM library_targets WHERE id=? AND domain<>?',(identifier,'CAD / Assets')).fetchone()
        if target is None:raise ValueError('Knowledge record not available')
        return _present(db,target,full=True)


def cartridge_data(identifier):
    """Use resolved properties, without the existing technical/audit payload."""
    from .engineering_facts import resolved_engineering_facts
    data=resolved_engineering_facts('cartridge',identifier)
    with closing(_connect()) as db:
        has_data=db.execute("SELECT 1 FROM technical_identities WHERE domain='cartridge' AND id=?",(identifier,)).fetchone() is not None
        values=list(db.execute('''SELECT e.property,e.raw_value,e.raw_unit,e.normalized_value_json,e.normalized_unit,e.scope,e.condition,v.status
            FROM technical_values v JOIN technical_evidence e ON e.domain=v.domain AND e.id=v.evidence_id
            WHERE v.domain='cartridge' AND v.identity_id=? ORDER BY e.property,e.id''',(identifier,)))
        supplemental=[dict(name=r[0],unit=r[1],message='Cavity identity known · Machining geometry not available') for r in db.execute('''
            SELECT DISTINCT s.display_name,s.unit FROM cartridge_cavity_evidence e
            JOIN cartridge_cavity_supplement_links l ON l.relation_id=e.relation_id
            JOIN kb_cavity_supplements s ON s.canonical_id=l.canonical_id WHERE e.cartridge_id=? ORDER BY s.display_name,s.unit''',(identifier,))]
    fields=[]
    for fact in data.get('facts',{}).values():
        if fact.get('status') in ('SOURCE_BACKED','USER_OVERRIDE'):
            value=text(fact.get('value'))
            if value:fields.append(dict(label=fact['property'].replace('_',' ').title(),value=' '.join(v for v in [value,text(fact.get('unit')),text(fact.get('condition'))] if v)))
    labels={'catalog_flow':'Catalogue flow','catalog_listed_flow':'Catalogue flow','catalog_pressure':'Catalogue pressure',
        'catalog_listed_pressure':'Catalogue pressure','maximum_working_pressure':'Maximum working pressure',
        'maximum_flow':'Maximum flow','nominal_flow':'Nominal flow','installation_torque':'Installation torque',
        'seal_options':'Seal options','seal_kit_part_number':'Seal kit','weight':'Weight','viscosity_range':'Viscosity range',
        'internal_leakage':'Internal leakage','filtration_requirement':'Filtration','product_description':'Description',
        'function_primary':'Function','temperature_range':'Temperature range','detail_check_cracking_pressure':'Check cracking pressure',
        'detail_factory_pressure_settings_established_at':'Factory setting test flow',
        'detail_adjustment_screw_internal_hex_size':'Adjustment hex size'}
    grouped={}
    for prop,raw,raw_unit,normalized,unit,scope,condition,status in values:
        if prop not in labels or status in ('CONFLICT','UNRESOLVED','REJECTED'):continue
        normalized=json.loads(normalized)
        value=text(normalized) or text(raw)
        if not value:continue
        value=' '.join(v for v in [value,text(unit or raw_unit),text(condition)] if v)
        grouped.setdefault((scope,labels[prop]),set()).add(value)
    headings={'EXACT_PART_NUMBER':'Technical data','BASE_MODEL':'Model data','SERIES':'Series data',
              'OPTION_FAMILY':'Option data','PRODUCT_FAMILY':'Product family data'}
    groups=[dict(title='Technical data',fields=fields)] if fields else []
    for scope,title in headings.items():
        extra=[dict(label=label,value=next(iter(vals))) for (s,label),vals in grouped.items() if s==scope and len(vals)==1]
        if extra:groups.append(dict(title=title,fields=extra))
    return dict(available=has_data,groups=groups or [dict(title='Technical data',fields=[])],cavity_identities=supplemental)


def material_data(identifier):
    with closing(_connect()) as db:
        identity=db.execute("SELECT id FROM technical_identities WHERE domain='material' AND (material_id=? OR id=?) ORDER BY material_id IS NULL LIMIT 1",(identifier,identifier)).fetchone()
        if identity is None:return dict(groups=[])
        rows=[json.loads(r[0]) for r in db.execute('''SELECT t.original_json FROM material_research_links l
            JOIN material_surface_treatments t ON t.id=l.record_id WHERE l.material_id=? AND l.kind='treatment' ORDER BY t.id''',(identity[0],))]
        groups=[]
        for row in rows:
            fields=_fields([row],'surface-treatments')
            if fields:
                if row.get('status') not in ('VERIFIED','CONFIRMED'):fields.append(dict(label='Status',value='Partial data'))
                groups.append(dict(title='Surface treatments',fields=fields))
        stocks=[json.loads(r[0]) for r in db.execute('''SELECT s.original_json FROM material_research_links l
            JOIN material_supplier_stock s ON s.id=l.record_id WHERE l.material_id=? AND l.kind='stock' ORDER BY s.id LIMIT 8''',(identity[0],))]
        for row in stocks:
            fields=[]
            for key,label in [('supplier','Supplier'),('product_form','Form'),('material','Material'),('diameter','Diameter'),
                              ('width','Width'),('height','Height'),('length','Length'),('unit','Units'),('retrieved_date','Catalogue date')]:
                if text(row.get(key)):fields.append(dict(label=label,value=text(row[key])))
            if fields:groups.append(dict(title='Supplier catalogue sizes',fields=fields))
        return dict(groups=groups)
