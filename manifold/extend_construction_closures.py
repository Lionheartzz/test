"""Explicit R1-based construction closure admission into a new v8 staging DB."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .engineering_db import _connect,validate_database
from .generic_closures import protected_digest
from .replace_relation_knowledge import encode,file_hash
from .import_mdtools import number


def identifier(prefix,value):
    return prefix+hashlib.sha256(encode(value).encode()).hexdigest()[:24]


def extend_tool_kinds(db):
    # Only the CHECK changes; all pre-existing tool columns and rows are copied
    # verbatim. No rated reach is invented from an overall product length.
    original=db.execute("SELECT sql FROM sqlite_master WHERE name='tool_definitions'").fetchone()[0]
    indexes=[r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='tool_definitions' AND sql IS NOT NULL")]
    sql=original.replace('CREATE TABLE tool_definitions','CREATE TABLE closure_tools_stage').replace("'spotface'","'spotface','form-port','tap'")
    if sql==original:raise ValueError('Unexpected tool schema')
    db.execute(sql);db.execute('INSERT INTO closure_tools_stage SELECT * FROM tool_definitions')
    db.execute('DROP TABLE tool_definitions');db.execute('ALTER TABLE closure_tools_stage RENAME TO tool_definitions')
    for statement in indexes:db.execute(statement)


def add_tool(db,kind,diameter,depth,unit,source):
    existing=db.execute('''SELECT id FROM tool_definitions WHERE tool_type=? AND diameter_mm=? AND max_depth_mm=? AND unit_system=?''',
                        (kind,diameter,depth,unit)).fetchone()
    if existing:return existing[0]
    key=identifier('tool_closure_',dict(kind=kind,diameter=diameter,depth=depth,unit=unit,source=source))
    db.execute('INSERT INTO tool_definitions VALUES (?,?,?,?,?,1,1)',(key,kind,diameter,depth,unit))
    return key


def admit(db,raw_rows,facts):
    extend_tool_kinds(db);mapping=[];new_ids=[];groups={}
    for raw in raw_rows:
        if raw['library_name'] not in ('Expander Plug Ports','SAE Plugs','SAE Ports-J1926-1','Metric Ports-ISO 6149-1'):continue
        r=raw['raw_source_row'];unit='metric' if raw['source_db'].startswith('MM') else 'inch';scale=1 if unit=='metric' else 25.4
        found=db.execute('SELECT * FROM external_port_definitions WHERE family=? AND name=? AND unit_system=? AND active=1',
                         (raw['library_name'],r['CavityName'],unit)).fetchall()
        if len(found)!=1:raise ValueError(f"Ambiguous/missing source interface: {r['CavityName']} / {unit}")
        port=dict(found[0]);mapped=db.execute('SELECT id FROM closure_definitions WHERE construction_port_definition_id=?',(port['id'],)).fetchone()
        if not port['usable'] and port['unusable_reason']!='External port requires one executable hydraulic interface':
            raise ValueError('Source machining is blocked: '+port['unusable_reason'])
        alias=db.execute('SELECT closure_definition_id FROM closure_definition_aliases WHERE source_port_definition_id=?',(port['id'],)).fetchone()
        if mapped or alias:
            mapping.append(dict(source_db=raw['source_db'],source_table=raw['source_table'],source_row_key=raw['source_row_key'],definition_id=(mapped or alias)[0],state='EXISTING'));continue
        source=dict(source_db=raw['source_db'],table=raw['source_table'],key=raw['source_row_key'],
                    library=raw['library_name'],archive_sha256='123cff0facd981201e7619815e15eb77da8d27b371d2329c8fac29da5a24e26c')
        if raw['library_name']=='Expander Plug Ports':
            key=re.sub('[^A-Z0-9]','',r['CavityName'].upper())
            if key not in facts['expander_products']:raise ValueError('Missing exact expander facts: '+key)
            f=facts['expander_products'][key];entry=dict(f['entry']);engagement=f['engagement_mm'];envelope=f['envelope']
            for field in ('manufacturer','model','setting_stroke_mm','pressure_rating','note'):entry.pop(field,None)
            entry.update(closure_type='expander',role='EXPANDER_CLOSURE',automatic_default=True,default_order=1000,
                         independent_machining_interface=True,
                         source_r1=source,source_nominal_policy='Exact named manufacturer drawing. R1 inch catalogue layouts of metric MB products are not new inch SKUs.')
            recipe=[entry,dict(operation="C'BORE",diameter_mm=entry['diameter_mm'],depth_mm=entry['depth_mm']),
                    dict(operation='CHAMFER',angle=120),dict(operation='INSTALL EXPANDER')]
            display=f"Expander Plug Ø{entry['diameter_mm']:g} · {unit} · engagement {engagement:g} mm"
        else:
            short=raw['library_name']=='SAE Plugs'
            metric_thread=raw['library_name']=='Metric Ports-ISO 6149-1'
            thread_circle=2 if short else 3
            pilot_circle=thread_circle+1
            expected_class='6H' if metric_thread else '2B'
            if (short and str(r.get('PlugPort'))!='1') or r.get('ThreadCircle')!=thread_circle or r.get('ThreadClass')!=expected_class:raise ValueError('Unproven source role/thread')
            if [r.get('MachineOperation'+str(i)) for i in (1,2,3)]!=['DRILL','FORM PORT','TAP']:raise ValueError('Incomplete SAE source sequence')
            # This is the literal pilot of the documented FORM PORT contour,
            # not nominal thread diameter minus pitch. Preserve raw dimensions.
            tap=number(r[f'Circle{pilot_circle}Dia'])*scale;engagement=number(r['InsertionDepth'])*scale
            # ThreadSize for ISO 6149 remains metric even in an inch layout.
            major=number(r['ThreadSize'])*(1 if metric_thread else 25.4);thread_depth=number(r[f'Circle{thread_circle}Depth'])*scale
            if not 0<tap<major or engagement<=0:raise ValueError('Missing source pilot/occupied depth')
            if not 0<number(r['MaxCircle12Dia'])*scale<=tap:raise ValueError('Hydraulic bore may not enlarge the source tap pilot')
            spec=r['ThreadPitch'];thread_id=identifier('thread_closure_',dict(source=source,spec=spec,klass=expected_class,tap=tap))
            db.execute('INSERT INTO thread_definitions VALUES (?,?,?,?,?,?,?,?,?,?,1,\'\',1)',
                       (thread_id,spec+'-'+expected_class,'Metric' if metric_thread else 'Unified',r['ThreadSize'],spec,expected_class,'internal',0,'metric' if metric_thread else 'inch',tap))
            form_depth=number(r['Circle0Depth'])*scale
            form=add_tool(db,'form-port',number(r['Circle0Dia'])*scale,form_depth,unit,source)
            tapping=add_tool(db,'tap',major,thread_depth,unit,source)
            envelope=dict(diameter_mm=number(r['Circle0Dia'])*scale,height_mm=number(r['PlugHeadHeight'])*scale,
                          installed_length_mm=engagement,scope='Source construction-plug occupied depth/head height; source port footprint radial bound.')
            entry=dict(operation='SOURCE_FORM_PORT_ENTRY',closure_type='metric-iso6149' if metric_thread else 'sae-short-port' if short else 'sae-standard-port',role='THREADED_CONSTRUCTION_PLUG',
                       diameter_mm=envelope['diameter_mm'],depth_mm=number(r[f'Circle{pilot_circle}Depth'])*scale,
                       hydraulic_diameter_max_mm=number(r['MaxCircle12Dia'])*scale,
                       transition_angle_degrees=number(r[f'Circle{pilot_circle}Angle'])*2,source_profile_row=r,source_scale=scale,
                       pilot_circle=pilot_circle,
                       thread_definition_id=thread_id,source_r1=source,sealing_form='ISO 6149 straight-thread O-ring boss' if metric_thread else 'straight-thread O-ring boss short construction port' if short else 'straight-thread O-ring boss standard construction port',
                       independent_machining_interface=True,
                       automatic_default=True,default_order=2000,
                       form_tool_id=form,tap_tool_id=tapping,
                       tool_scope='Conservative capability of the exact declared source FORM PORT/TAP operation, not vendor maximum reach or shop-stock assertion.',
                       role_reference=dict(document='BC431760070941en-000101',page='M-11' if short else 'M-5',pdf_page=647 if short else 644,
                                           statement='Short port: SAE plugged construction holes only, not external porting with standard fittings.' if short else 'Construction drilling closures may use standard SAE or short SAE straight-thread O-ring boss machining.'))
            if metric_thread:
                entry['role_reference']=dict(url='https://www.zeroleak.com/port-dimensions/',
                    application_url='https://www.zeroleak.com/product/plugs/',
                    statement='ISO 6149 metric ORB plugs use the standard port configuration; manufacturer explicitly lists manifold applications.',
                    scope='Generic ISO 6149 ORB interface only. No ZLG-specific taper seal or optional SKU compatibility is inferred.')
            recipe=[entry,dict(operation='FORM PORT',tool_type='form-port',diameter_mm=envelope['diameter_mm'],depth_mm=form_depth,tool_id=form),
                    dict(operation='TAP',thread=spec+'-'+expected_class,tool_type='tap',diameter_mm=major,depth_mm=thread_depth,tool_id=tapping)]
            display=f"{'ISO 6149' if metric_thread else 'SAE'} construction plug {r['CavityName']} · {spec} · {unit}"
        physical={k:v for k,v in entry.items() if k not in ('source_r1','source_evidence_ids','dimensional_drawing','source_profile_row','thread_definition_id','form_tool_id','tap_tool_id')}
        if raw['library_name']!='Expander Plug Ports':physical['source_profile_row']=r
        signature=encode([unit,physical,engagement,envelope])
        if signature in groups:closure_id=groups[signature]
        else:
            closure_id=identifier('closure_r1_',signature);groups[signature]=closure_id
            db.execute('INSERT INTO closure_definitions VALUES (?,?,?,?,?,?,?,?,?,1)',
                       (closure_id,display,port['id'],'',encode(recipe),engagement,encode(envelope),1,''));new_ids.append(closure_id)
        mapping.append(dict(source_db=raw['source_db'],source_table=raw['source_table'],source_row_key=raw['source_row_key'],definition_id=closure_id,state='ADMITTED'))
        if raw['library_name']=='Expander Plug Ports':
            part=f['part_number'];key=re.sub('[^A-Z0-9]','',part.upper())
            existing=[p for p in db.execute('SELECT * FROM closure_products WHERE manufacturer=\'SFC KOENIG\'')
                      if re.sub('[^A-Z0-9]','',p['part_number'].upper())==key]
            if len(existing)>1:raise ValueError('Ambiguous exact product mapping')
            pid=existing[0]['id'] if existing else identifier('closure_product_',dict(manufacturer='SFC KOENIG',part=part))
            if not existing:db.execute('INSERT INTO closure_products VALUES (?,?,?,?)',(pid,'SFC KOENIG',part,encode(dict(pressure_rating=None,source_entry=f['entry']))))
            db.execute('INSERT OR IGNORE INTO closure_definition_products VALUES (?,?)',(closure_id,pid))
    db.execute('PRAGMA user_version=8')
    return dict(new_definitions=new_ids,source_mapping=mapping)


def migrate(source,output,raw_path,facts_path,report):
    source,output=Path(source).resolve(),Path(output).resolve();validate_database(source,schema_version=7)
    if output.exists():raise FileExistsError(output)
    raw=[json.loads(s) for s in Path(raw_path).read_text(encoding='utf-8-sig').splitlines()]
    facts=json.loads(Path(facts_path).read_text())
    with closing(_connect(source)) as original,closing(sqlite3.connect(output)) as target:
        target.row_factory=sqlite3.Row;original.backup(target)
        before=protected_digest(original);target.execute('BEGIN IMMEDIATE')
        try:
            result=admit(target,raw,facts)
            after=protected_digest(target)
            changed={k for k in before if before[k]!=after[k]}
            if not changed<= {'thread_definitions','tool_definitions'}:raise ValueError('Unrelated protected changes: '+str(changed))
            for table in changed:
                old=[tuple(r) for r in original.execute('SELECT * FROM '+table)]
                assert all(tuple(target.execute('SELECT * FROM '+table+' WHERE id=?',(r[0],)).fetchone())==r for r in old)
            # The optional commercial layer and legacy IDs are protected too;
            # protected_digest excludes these intentionally additive tables.
            preserved={}
            for table in ('closure_definitions','closure_products','closure_definition_products','closure_definition_aliases'):
                old={tuple(r) for r in original.execute('SELECT * FROM '+table)}
                current={tuple(r) for r in target.execute('SELECT * FROM '+table)}
                if not old<=current:raise ValueError('Existing closure data changed: '+table)
                preserved[table]=len(old)
            result['preserved_closure_rows']=preserved
            assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not target.execute('PRAGMA foreign_key_check').fetchall();target.commit()
        except Exception:target.rollback();raise
        result.update(before_hash=file_hash(source),after_hash=file_hash(output),protected_before=before,protected_after=after,
                      intentional_additive_tables=sorted(changed),schema=8,
                      definitions=target.execute('SELECT count(*) FROM closure_definitions').fetchone()[0])
    Path(report).write_text(json.dumps(result,indent=2),encoding='utf-8');print(result['definitions'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output','raw-r1','facts','report'):p.add_argument('--'+name,required=True)
    a=p.parse_args();migrate(a.source,a.output,a.raw_r1,a.facts,a.report)
