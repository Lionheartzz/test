"""Material-only research supplements through the schema-v4 REV2 evidence tables.

Called by explicit rebuilds, never by startup or a runtime request. The original
REV2 package remains immutable; no cartridge data is written here.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from .import_technical_knowledge import encode, stable

SOLID_FORMS = {'Extrusion', 'Extruded bar', 'Plate', 'Bar', 'Continuous cast bar'}
PRIMARY_TYPES = {'PRIMARY_PRODUCER_DATASHEET', 'MANUFACTURER_OFFICIAL_PRODUCT_PAGE',
                 'OEM_MANUFACTURER_BULLETIN', 'OFFICIAL_STANDARD_OWNER'}


def read_supplement(path):
    path=Path(path).resolve()
    payload=path.read_bytes()
    if len(payload)>2_000_000:raise ValueError('Material supplement exceeds 2 MB')
    data=json.loads(payload)
    if data.get('format_version')!=1 or data.get('domain')!='material':
        raise ValueError('Expected a version 1 material-only supplement')
    for key in ('sources','identities','evidence','conflicts','field_status','treatment_links'):
        if not isinstance(data.get(key),list):raise ValueError('Missing material supplement '+key)
    for key,id_key in [('sources','id'),('identities','id'),('evidence','id'),('conflicts','id')]:
        ids=[row.get(id_key) for row in data[key]]
        if any(not isinstance(i,str) or not i.startswith('CORE-') for i in ids if key!='identities') or len(set(ids))!=len(ids):
            raise ValueError('Invalid or duplicate supplement '+key+' identity')
    return data,hashlib.sha256(payload).hexdigest()


def apply_supplement(db,path,base_sha256):
    data,digest=read_supplement(path)
    if data.get('base_rev2_sha256')!=base_sha256:
        raise ValueError('Material supplement was reviewed against a different REV2 package')
    sources={row['id']:row for row in data['sources']}
    for sid,row in sources.items():
        url=urlsplit(row['url'])
        if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:
            raise ValueError('Material source must have a complete public HTTP(S) URL')
        if row.get('source_type') not in PRIMARY_TYPES or not all(row.get(k) for k in ('title','organization','retrieved_date','applicability')):
            raise ValueError('Material source authority/provenance incomplete')
        db.execute('INSERT INTO technical_sources VALUES (?,?,?,?,?,?)',
            ('material',sid,row['title'],row['url'],row.get('sha256',''),encode(row)))
    evidence={row['id']:row for row in data['evidence']}
    identities={row['id']:row for row in data['identities']}
    for mid,row in identities.items():
        existing=db.execute("SELECT original_json,material_id FROM technical_identities WHERE domain='material' AND id=?",(mid,)).fetchone()
        if row.get('update'):
            if not existing:raise ValueError('Material review update identity does not exist')
            raw=json.loads(existing[0])
            # Review metadata may clarify a delivery standard/form, never rewrite
            # the original grade/state/standard identity or its evidence history.
            if any(row.get(k)!=raw.get(k) for k in ('canonical_grade','temper_condition','standard','product_form')):
                raise ValueError('Material identity update changes original engineering meaning')
            raw['core_material']=row['core_material']
            db.execute("UPDATE technical_identities SET original_json=? WHERE domain='material' AND id=?",(encode(raw),mid))
        else:
            if existing:raise ValueError('New core material identity already exists')
            raw={k:v for k,v in row.items() if k not in ('update','id')}
            raw['material_id']=mid
            db.execute('INSERT INTO technical_identities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                ('material',mid,None,None,row.get('manufacturer',''),row['canonical_grade'],row['canonical_grade'],
                 row['temper_condition'],row['material_family'],'PARTIAL','CORE_MATERIAL_REVIEW',encode(raw)))
        core=row['core_material']
        if core['status']=='ENGINEERING':
            if core.get('stock_product_form') not in SOLID_FORMS or not core.get('primary_standard'):
                raise ValueError('Core identity lacks a solid block stock form/standard')
            for eid in core.get('identity_evidence_ids',[]):
                ev=evidence.get(eid)
                if not ev or ev['identity_id']!=mid or ev['evidence_class']!='identity' or not ev['source_ids']:
                    raise ValueError('Core identity must have exact primary identity evidence')
                expected=dict(grade=row['canonical_grade'],state=row['temper_condition'],
                    standard=core['primary_standard'],product_form=core['stock_product_form'])
                if ev.get('normalized_value')!=expected:
                    raise ValueError('Primary identity evidence does not match the reviewed grade/state/standard/form')
            if not core.get('identity_evidence_ids'):raise ValueError('Core identity has no primary identity support')
            for eid in core.get('parameter_evidence_ids',[]):
                if eid not in evidence or evidence[eid]['identity_id']!=mid or evidence[eid]['evidence_class']!='parameter':
                    raise ValueError('Reviewed parameter evidence is not an exact material parameter')
        elif core['status']!='RESEARCH_ONLY' or not core.get('reason'):
            raise ValueError('Core research-only disposition requires an exact reason')
    for eid,row in evidence.items():
        if row['identity_id'] not in identities or row['evidence_class'] not in ('parameter','identity','source_review'):
            raise ValueError('Unsupported supplement evidence attribution/class')
        if not row['source_ids'] or not set(row['source_ids'])<=sources.keys():
            raise ValueError('Material evidence source not registered')
        raw={k:v for k,v in row.items() if k not in ('id','identity_id')}
        raw.update(evidence_id=eid,entity_id=row['identity_id'],source_type=sources[row['source_ids'][0]]['source_type'])
        db.execute('INSERT INTO technical_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('material',eid,row['identity_id'],sources[row['source_ids'][0]]['organization'],row['property'],
             str(row['raw_value']),row.get('raw_unit',''),encode(row.get('normalized_value')),row.get('normalized_unit',''),
             row.get('condition',''),row['scope'],row['scope'],row.get('scope_detail',''),'',row['evidence_class'],encode(raw)))
        db.executemany('INSERT INTO technical_evidence_sources VALUES (?,?,?)',
            [('material',eid,sid) for sid in row['source_ids']])
        db.execute('INSERT INTO technical_evidence_observations VALUES (?,?,?,?)',
            ('material',eid,data['id'],encode(raw)))
        db.execute('INSERT INTO technical_identity_evidence VALUES (?,?,?,?)',
            ('material',row['identity_id'],eid,'EXACT_CORE_RESEARCH_IDENTITY'))
        if row['evidence_class']=='parameter':
            db.execute('INSERT INTO technical_values VALUES (?,?,?,?,?,?,?)',
                ('material','core_'+stable([row['identity_id'],eid]),row['identity_id'],eid,row['property'],'EVIDENCE_PRESENT',None))
    for row in data['conflicts']:
        if row['identity_id'] not in identities:raise ValueError('Unknown conflict identity')
        preferred=row.get('preferred_evidence_id')
        links=row.get('evidence_a_ids',[])+row.get('evidence_b_ids',[])
        if not links or not set(links)<=evidence.keys() or preferred and preferred not in links:
            raise ValueError('Conflict has unsupported preferred/evidence references')
        db.execute('INSERT INTO technical_conflicts VALUES (?,?,?,?,?,?,?,?,?)',
            ('material',row['id'],row['identity_id'],row['property'],row['conflict_type'],row['resolution'],'LINKED',preferred,encode(row)))
        db.execute('INSERT INTO technical_identity_conflicts VALUES (?,?,?)',('material',row['identity_id'],row['id']))
        for side in ('a','b'):
            db.executemany('INSERT INTO technical_conflict_evidence VALUES (?,?,?,?)',
                [('material',row['id'],side,eid) for eid in row['evidence_'+side+'_ids']])
    for row in data['field_status']:
        if row['identity_id'] not in identities:raise ValueError('Unknown field-status identity')
        if row['status'] not in ('NOT_REPORTED','EVIDENCE_PRESENT','NOT_APPLICABLE','UNRESOLVED'):
            raise ValueError('Unsupported field-status disposition')
        db.execute('INSERT INTO technical_field_status VALUES (?,?,?,?,?)',
            ('material',row['identity_id'],row['field_group'],row['status'],encode(row)))
    for row in data['treatment_links']:
        if row['identity_id'] not in identities or not row.get('applicability'):
            raise ValueError('Treatment reference requires reviewed applicability')
        record=db.execute('SELECT id FROM material_surface_treatments WHERE id=?',(row['treatment_id'],)).fetchone()
        if not record:raise ValueError('Treatment reference does not exist')
        db.execute('INSERT INTO material_research_links VALUES (?,?,?,?,?,?)',
            (row['identity_id'],'material',row['treatment_id'],'treatment',row['treatment_id'],None))
    return dict(id=data['id'],sha256=digest,path=str(Path(path).resolve()),retrieved_date=data['retrieved_date'],
        sources=len(sources),identities=len(identities),evidence=len(evidence),conflicts=len(data['conflicts']),
        engineering_stock_promoted=0,legacy_materials=data['legacy_materials'])
