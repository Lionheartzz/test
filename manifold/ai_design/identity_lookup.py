"""Read-only identity-field retrieval across the existing engineering master.

Similarity here supplies AI reference context, never an execution identity.
"""
import json
import re
import time
from collections import defaultdict
from contextlib import closing
from difflib import SequenceMatcher
from functools import lru_cache
from ..engineering_db import _connect, database_path
from .interface_catalog import standard_aliases


IDENTITY_FIELDS={'model','full_part_number','normalized_full_part_number','base_model','series',
    'product_family','manufacturer','manufacturer_original','part_number','name','display_name',
    'cavity_name','cavity','designation','thread_designation','thread_spec','raw_identity',
    'canonical_identity','source_aliases','aliases','function','function_primary','function_original',
    'product_description','model_name','cartridge_model','cavity_designation','part_no','product_code',
    'alias','standard_aliases','canonical_grade','grade','temper_condition','product_form','material_family'}
TABLES=(
    ('cartridges','cartridge',('manufacturer','model','function','active')),
    ('cavities','machining_interface',('name','family','manufacturer','thread_spec','unit_system','usable','active')),
    ('external_port_definitions','external_port',('name','family','manufacturer','thread_spec','unit_system','usable','active')),
    ('thread_definitions','thread',('display_name','family','nominal_size','pitch_tpi','thread_class','unit_system','usable','active')),
    ('materials','material',('display_name','material_type','active')),
    ('closure_definitions','closure_definition',('display_name','model','usable','active')),
    ('closure_products','closure_product',('manufacturer','part_number')),
    ('tool_definitions','tool',('tool_type','diameter_mm','unit_system','usable','active')),
    ('machining_modifiers','machining_modifier',('display_name','kind','unit_system','usable','active')),
)


def norm(value):
    return ''.join(c for c in str(value).casefold() if c.isalnum())


NORMALIZED_IDENTITY_FIELDS={norm(field) for field in IDENTITY_FIELDS}


@lru_cache(maxsize=2048)
def field_name(key):
    return norm(key)


def identity_fields(value, path=''):
    """Extract explicitly named identity fields, never turn prose into aliases."""
    if isinstance(value,dict):
        for key, child in value.items():
            name=field_name(key)
            if name not in NORMALIZED_IDENTITY_FIELDS and not isinstance(child,(dict,list)):continue
            location=path+'.'+str(key) if path else str(key)
            if name in NORMALIZED_IDENTITY_FIELDS:
                if isinstance(child,str) and child.strip():yield location,child
                elif name in ('aliases','sourcealiases','standardaliases') and isinstance(child,list):
                    for i,alias in enumerate(child):
                        if isinstance(alias,str) and alias.strip():yield f'{location}[{i}]',alias
            if isinstance(child,(dict,list)):yield from identity_fields(child,location)
    elif isinstance(value,list):
        for i,child in enumerate(value):
            if isinstance(child,(dict,list)):yield from identity_fields(child,f'{path}[{i}]')


@lru_cache(maxsize=2)
def _index(stamp):
    records=[];coverage={}
    def add(table,role,key,fields,*,reference_only=False):
        readable={k:v for k,v in fields.items() if v is not None and v!=''}
        records.append(dict(source_table=table,role=role,record_id=key,fields=readable,
                            reference_only=reference_only,execution_permission=False))
    with closing(_connect()) as db:
        for table,role,columns in TABLES:
            rows=db.execute('SELECT id,'+','.join(columns)+' FROM '+table+' ORDER BY id')
            count=0
            for row in rows:
                fields={k:row[k] for k in columns}
                if table=='cavities':
                    fields.update({f'standard_alias_{i}':alias for i,alias in
                                   enumerate(standard_aliases(row['name'],row['family']),1)})
                add(table,role,row['id'],fields);count+=1
            coverage[table]=count
        rows=db.execute('''SELECT domain,id,manufacturer_original,full_part_number,base_model,
            series,product_family,disposition,original_json FROM technical_identities ORDER BY domain,id''')
        count=0
        for row in rows:
            fields={k:row[k] for k in ('manufacturer_original','full_part_number','base_model','series','product_family','disposition')}
            original=json.loads(row['original_json'])
            fields.update(dict(identity_fields(original)))
            add('technical_identities',row['domain'],row['id'],fields,reference_only=True);count+=1
        coverage['technical_identities']=count
        rows=db.execute('SELECT id,domain,target_type,raw_identity,canonical_identity,status,disposition FROM library_targets ORDER BY id')
        count=0
        for row in rows:
            add('library_targets',row['domain'],row['id'],
                {k:row[k] for k in ('target_type','raw_identity','canonical_identity','status','disposition')},reference_only=True);count+=1
        coverage['library_targets']=count
        rows=db.execute('''SELECT r.dataset_id,r.row_key,d.domain,r.original_json FROM library_records r
            JOIN library_datasets d ON d.id=r.dataset_id ORDER BY r.dataset_id,r.row_key''')
        count=0
        for row in rows:
            fields=dict(identity_fields(json.loads(row['original_json'])))
            if fields:add('library_records',row['domain'],row['dataset_id']+':'+str(row['row_key']),fields,reference_only=True)
            count+=1
        coverage['library_records']=count
    keys=defaultdict(list)
    for index,record in enumerate(records):
        for field,value in record['fields'].items():
            # States/units/diameters are returned as context, not arbitrary identities.
            if isinstance(value,str) and field not in ('active','usable','unit_system','status','disposition'):
                key=norm(value)
                if len(key)>=2:keys[key].append((index,field))
    neighbors=defaultdict(set)
    for key in keys:
        if 3<=len(key)<=120:
            neighbors['prefix:'+key[:2]].add(key);neighbors['suffix:'+key[-2:]].add(key)
    return records,dict(keys),dict(neighbors),coverage


def _terms(quote):
    words=re.findall(r'[^\s,;，；()]+',quote)
    terms={norm(quote)}
    # Retrieval token windows handle free-form nearby text; they never split or
    # rewrite a product identity for execution.
    for size in range(1,5):
        terms.update(norm(' '.join(words[i:i+size])) for i in range(len(words)-size+1))
    return {term for term in terms if 2<=len(term)<=120}


def lookup(reading, per_role=4, *, deadline=None):
    path=database_path();records,keys,neighbors,coverage=_index((str(path),path.stat().st_mtime_ns))
    captions=[];total_matches=0
    for number,caption in enumerate(reading.captions,1):
        if deadline is not None and time.monotonic()>=deadline:raise TimeoutError()
        terms=_terms(caption.quote);found={}
        def retain(key,score,kind):
            for index,field in keys[key]:
                leaf=norm(field.rsplit('.',1)[-1])
                weight=(2 if leaf in ('manufacturer','manufactureroriginal','function','functionprimary',
                    'functionoriginal','productdescription') else 1 if leaf in
                    ('family','series','productfamily','materialtype','tooltype','nominalsize','pitchtpi','threadclass') else 0)
                rank=score+weight
                previous=found.get(index)
                if previous is None or rank<previous[0]:found[index]=(rank,kind,field)
        for term in sorted(terms):
            if deadline is not None and time.monotonic()>=deadline:raise TimeoutError()
            if term in keys:retain(term,0,'exact_identity_field')
        # Similarity is informational. Always retain distinct catalogue roles.
        for term in sorted(terms):
            if deadline is not None and time.monotonic()>=deadline:raise TimeoutError()
            candidates=neighbors.get('prefix:'+term[:2],set()) | neighbors.get('suffix:'+term[-2:],set())
            for key in sorted(candidates):
                if key in terms or abs(len(term)-len(key))>max(2,len(key)//4):continue
                score=SequenceMatcher(None,key,term).ratio()
                if score>=0.78:retain(key,1-score,'similar_identity_field')
        grouped=defaultdict(list)
        for index,(score,kind,field) in found.items():
            record=records[index]
            grouped[record['role']].append((score,index,kind,field))
        matches=[]
        for role,items in sorted(grouped.items()):
            for score,index,kind,field in sorted(items,key=lambda x:(x[0],records[x[1]]['source_table'],records[x[1]]['record_id']))[:per_role]:
                record=records[index]
                fields={k:(v[:500] if isinstance(v,str) else v) for k,v in record['fields'].items()}
                matches.append({**record,'fields':fields,'match':kind,'matched_field':field,
                    'truncated_fields':[k for k,v in record['fields'].items() if isinstance(v,str) and len(v)>500]})
        total_matches+=len(found)
        captions.append(dict(caption=number,source=caption.model_dump(),matches=matches,
                             matched_records=len(found),returned_records=len(matches)))
    product_ids=sorted({row['record_id'] for entry in captions for row in entry['matches']
                       if row['source_table']=='cartridges'})
    if product_ids:
        from ..engineering_facts import facts_batch
        functions={}
        for start in range(0,len(product_ids),50):
            if deadline is not None and time.monotonic()>=deadline:raise TimeoutError()
            functions.update(facts_batch('cartridge',product_ids[start:start+50]))
        for entry in captions:
            for row in entry['matches']:
                if row['source_table']=='cartridges':
                    row['function_reference']=functions[row['record_id']]['facts']['function_primary']
    return dict(source='current engineering SQLite',searched_tables=coverage,identity_captions=captions,
                matched_records=total_matches,
                instruction='Reference context only. Compare roles/identity fields before assigning product, cavity, '
                'mounting interface or other identity. Similarity, reference-only records and technical function '
                'descriptions grant no identity certainty, compatibility, geometry or execution permission. '
                'Preserve the actual source codes and suffixes; do not replace them with nearest catalogue items. '
                'Do not treat explicitly truncated reference fields as complete identities. The cavities table '
                'contains cartridge cavities and surface/subplate mounting interfaces; compare their actual family. '
                'Catalogue manufacturer/function not stated in the drawing must remain inference, not schematic evidence.')
