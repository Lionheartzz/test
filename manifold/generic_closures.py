"""Explicit v6 -> v7 closure/product separation. Never run during startup."""
import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from .engineering_db import _connect,validate_database
from .replace_relation_knowledge import encode,file_hash

TABLES={
    'closure_products':{'id','manufacturer','part_number','properties_json'},
    'closure_definition_products':{'closure_definition_id','product_id'},
    'closure_definition_aliases':{'alias_id','closure_definition_id','source_port_definition_id'},
}


def initialize(db):
    db.execute('''CREATE TABLE closure_products (
        id TEXT PRIMARY KEY,manufacturer TEXT NOT NULL,part_number TEXT NOT NULL,
        properties_json TEXT NOT NULL DEFAULT '{}',UNIQUE(manufacturer,part_number))''')
    db.execute('''CREATE TABLE closure_definition_products (
        closure_definition_id TEXT NOT NULL REFERENCES closure_definitions(id) ON DELETE RESTRICT,
        product_id TEXT NOT NULL REFERENCES closure_products(id) ON DELETE RESTRICT,
        PRIMARY KEY(closure_definition_id,product_id))''')
    db.execute('CREATE INDEX closure_product_reverse ON closure_definition_products(product_id,closure_definition_id)')
    db.execute('''CREATE TABLE closure_definition_aliases (
        alias_id TEXT PRIMARY KEY,closure_definition_id TEXT NOT NULL REFERENCES closure_definitions(id) ON DELETE RESTRICT,
        source_port_definition_id TEXT NOT NULL REFERENCES external_port_definitions(id) ON DELETE RESTRICT)''')


def admission_reason(role,entry,engagement,envelope,*,thread=None):
    """Geometry admission is independent of purchasing identity or ratings."""
    if role not in ('EXPANDER_CLOSURE','THREADED_CONSTRUCTION_PLUG'):
        return 'NON_CONSTRUCTION_ROLE' if role in ('ORIFICE_PLUG','RESTRICTOR','FULL_CAVITY_PLUG','PORT_PLUG') else 'AMBIGUOUS_ROLE'
    if not entry or any(not isinstance(entry.get(k),(int,float)) or not math.isfinite(entry[k]) or entry[k]<=0
                        for k in ('diameter_mm','depth_mm','hydraulic_diameter_max_mm')):
        return 'MISSING_MACHINING'
    if not isinstance(engagement,(int,float)) or not math.isfinite(engagement) or engagement<=0:return 'MISSING_ENGAGEMENT'
    if not envelope or any(not isinstance(envelope.get(k),(int,float)) or not math.isfinite(envelope[k])
                           for k in ('diameter_mm','height_mm')) or envelope['diameter_mm']<=0 or envelope['height_mm']<0:
        return 'MISSING_ENVELOPE'
    if role=='THREADED_CONSTRUCTION_PLUG':
        if not thread or not thread.get('usable') or not thread.get('tap_diameter_mm') or not entry.get('thread_depth_mm'):
            return 'INCOMPLETE_THREAD_MACHINING'
        # No threaded entry adapter is admitted until the exact machining model
        # supports that profile. Do not turn a complete identity into a cylinder.
        return 'UNSUPPORTED_THREAD_ENTRY'
    if entry.get('transition_angle_degrees')!=120:return 'UNSUPPORTED_ENTRY_GEOMETRY'
    return None


def products(db,identifier):
    if db.execute('PRAGMA user_version').fetchone()[0]<7:return []
    return [dict(r) | {'properties':json.loads(r['properties_json'])} for r in db.execute('''
        SELECT p.* FROM closure_definition_products m JOIN closure_products p ON p.id=m.product_id
        WHERE m.closure_definition_id=? ORDER BY p.manufacturer,p.part_number,p.id''',(identifier,))]


def generic_record(source_interface_id,display_name,role,entry,engagement,envelope,*,thread=None):
    """Create a source-interface row without manufacturer/product arguments."""
    reason=admission_reason(role,entry,engagement,envelope,thread=thread)
    if reason:raise ValueError(reason)
    if not source_interface_id or not display_name:raise ValueError('Missing source interface identity')
    recipe=[dict(entry,operation='SOURCE_EXPANDER_ENTRY',role=role,closure_type='expander',automatic_default=False),
            dict(operation="C'BORE",diameter_mm=entry['diameter_mm'],depth_mm=entry['depth_mm']),
            dict(operation='CHAMFER',angle=120,start=entry['depth_mm'],end_diameter='$HYDRAULIC_BORE'),
            dict(operation='INSTALL EXPANDER')]
    identifier='closure_interface_'+hashlib.sha256(encode([source_interface_id,entry,engagement,envelope]).encode()).hexdigest()[:24]
    return dict(id=identifier,display_name=display_name,construction_port_definition_id=source_interface_id,model='',
                machining_json=encode(recipe),engagement_mm=engagement,envelope_json=encode(envelope),usable=1,unusable_reason='',active=1)


def reconcile(db):
    """Preserve all existing IDs and physical fields; separate product data only."""
    rows=db.execute('SELECT * FROM closure_definitions ORDER BY model,id').fetchall()
    initialize(db)
    groups={}
    for order,raw in enumerate(rows):
        r=dict(raw);recipe=json.loads(r['machining_json']);entry=next(x for x in recipe if x.get('operation')=='SOURCE_EXPANDER_ENTRY')
        reason=admission_reason('EXPANDER_CLOSURE',entry,r['engagement_mm'],json.loads(r['envelope_json']))
        if reason:raise ValueError(f"{r['id']}: {reason}")
        maker=entry['manufacturer'];part=entry['model']
        pid='closure_product_'+hashlib.sha256((maker+'\n'+part).encode()).hexdigest()[:24]
        info={k:entry[k] for k in ('setting_stroke_mm','pressure_rating','note') if k in entry}
        info['source_evidence_ids']=entry.get('source_evidence_ids',[])
        info['installation']=[x for x in recipe if x.get('operation')=='INSTALL EXPANDER']
        db.execute('INSERT INTO closure_products VALUES (?,?,?,?)',(pid,maker,part,encode(info)))
        db.execute('INSERT INTO closure_definition_products VALUES (?,?)',(r['id'],pid))
        for key in ('manufacturer','model','setting_stroke_mm','pressure_rating','note'):entry.pop(key,None)
        entry.update(closure_type='expander',role='EXPANDER_CLOSURE',automatic_default=True,default_order=order)
        for op in recipe:
            if op.get('operation')=='INSTALL EXPANDER':
                op.pop('model',None);op.pop('setting_stroke_mm',None)
        name=f"Expander Plug Ø{entry['diameter_mm']:g} · entry {entry['depth_mm']:g} / engagement {r['engagement_mm']:g} mm"
        db.execute("UPDATE closure_definitions SET display_name=?,model='',machining_json=? WHERE id=?",(name,encode(recipe),r['id']))
        # Product ratings/strokes are not interface geometry. Compare every
        # physical profile/tolerance field, unit, engagement and envelope before
        # combining truly equivalent construction interfaces.
        unit=db.execute('SELECT unit_system FROM external_port_definitions WHERE id=?',(r['construction_port_definition_id'],)).fetchone()[0]
        physical={k:v for k,v in entry.items() if k not in ('source_evidence_ids','dimensional_drawing','default_order')}
        key=encode([unit,physical,r['engagement_mm'],json.loads(r['envelope_json'])])
        if key in groups:
            canonical=groups[key]
            db.execute('UPDATE closure_definition_products SET closure_definition_id=? WHERE closure_definition_id=?',(canonical,r['id']))
            db.execute('INSERT INTO closure_definition_aliases VALUES (?,?,?)',(r['id'],canonical,r['construction_port_definition_id']))
            db.execute('DELETE FROM closure_definitions WHERE id=?',(r['id'],))
        else:groups[key]=r['id']
    db.execute('PRAGMA user_version=7')
    return len(groups)


def protected_digest(db):
    result={}
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if table in ('closure_definitions',*TABLES):continue
        h=hashlib.sha256();count=0
        # Table names originate from SQLite metadata, never user input.
        rows=sorted(encode(list(r)) for r in db.execute('SELECT * FROM "'+table.replace('"','""')+'"'))
        for row in rows:h.update(row.encode());h.update(b'\n');count+=1
        result[table]=dict(count=count,sha256=h.hexdigest())
    return result


def migrate(source,output,report):
    source,output=Path(source).resolve(),Path(output).resolve()
    validate_database(source,schema_version=6)
    if output.exists():raise FileExistsError(output)
    with closing(_connect(source)) as db:
        before=protected_digest(db);source_hash=file_hash(source)
        with output.open('xb'):pass
        with closing(sqlite3.connect(output)) as target:
            target.row_factory=sqlite3.Row;db.backup(target);target.execute('PRAGMA foreign_keys=ON')
            with target:count=reconcile(target)
            assert target.execute('PRAGMA integrity_check').fetchall()[0][0]=='ok'
            assert not target.execute('PRAGMA foreign_key_check').fetchall()
            after=protected_digest(target)
            if before!=after:raise ValueError('Protected tables changed')
            counts={table:target.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in TABLES}
    validate_database(output,schema_version=7)
    result=dict(source_sha256=source_hash,output_sha256=file_hash(output),schema=7,definitions=count,
                products=counts['closure_products'],mappings=counts['closure_definition_products'],
                aliases=counts['closure_definition_aliases'],protected_tables=before,protected_tables_unchanged=before==after,
                size_delta=output.stat().st_size-source.stat().st_size)
    Path(report).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(encode({k:v for k,v in result.items() if k!='protected_tables'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--report',required=True)
    a=p.parse_args();migrate(a.source,a.output,a.report)
