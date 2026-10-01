"""Read-only focused acceptance for the independently rebuilt core-material DBs."""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from manifold import engineering_db,technical_schema
from manifold.import_technical_knowledge import preserved_tables
from manifold.engineering_facts import resolved_engineering_facts
from manifold.material_supplement import read_supplement


def digest(db,table,where=''):
    columns=db.execute(f'PRAGMA table_info({table})').fetchall()
    h=hashlib.sha256();count=0
    for row in db.execute(f"SELECT * FROM {table} {where} ORDER BY {','.join(str(i+1) for i in range(len(columns)))}"):
        h.update((json.dumps(tuple(row),ensure_ascii=False,separators=(',',':'))+'\n').encode());count+=1
    return dict(count=count,sha256=h.hexdigest())


def main():
    parser=argparse.ArgumentParser()
    for key in ('source','first','second','supplement','report'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();data,sha=read_supplement(args.supplement);result=dict(supplement_sha256=sha,schema_version=4)
    with sqlite3.connect(args.source.resolve().as_uri()+'?mode=ro',uri=True) as source, \
         sqlite3.connect(args.first.resolve().as_uri()+'?mode=ro',uri=True) as a, \
         sqlite3.connect(args.second.resolve().as_uri()+'?mode=ro',uri=True) as b:
        before,after=preserved_tables(source),preserved_tables(a)
        assert {k:v for k,v in before.items() if k!='materials'}=={k:v for k,v in after.items() if k!='materials'}
        result['compatibility_before']=digest(source,'cartridge_cavities','WHERE valid=1')
        result['compatibility_after']=digest(a,'cartridge_cavities','WHERE valid=1')
        assert result['compatibility_before']==result['compatibility_after']
        result['deterministic_tables']={};result['cartridge_preserved']={}
        for table in [*technical_schema.TABLES,'materials','material_stock']:
            if table=='technical_import_batches':continue
            da,db=digest(a,table),digest(b,table);assert da==db,table
            result['deterministic_tables'][table]=da
            names={c[1] for c in a.execute(f'PRAGMA table_info({table})')}
            if 'domain' in names:
                old,current=digest(source,table,"WHERE domain='cartridge'"),digest(a,table,"WHERE domain='cartridge'")
                assert old==current,table;result['cartridge_preserved'][table]=current
        for db in (a,b):
            assert db.execute('PRAGMA user_version').fetchone()[0]==4
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        previous=dict(source.execute("SELECT id,material_id FROM technical_identities WHERE domain='material' AND material_id IS NOT NULL"))
        current=dict(a.execute("SELECT id,material_id FROM technical_identities WHERE domain='material' AND material_id IS NOT NULL"))
        assert all(current[mid]==rid for mid,rid in previous.items())
        result['preserved_previous_material_ids']=previous
        result['runtime_rows_before']=source.execute('SELECT count(*) FROM materials').fetchone()[0]
        result['runtime_rows_after']=a.execute('SELECT count(*) FROM materials').fetchone()[0]
        result['engineering_stock_before_after']=[source.execute('SELECT count(*) FROM material_stock').fetchone()[0],a.execute('SELECT count(*) FROM material_stock').fetchone()[0]]
        result['supplier_stock']=a.execute('SELECT count(*) FROM material_supplier_stock').fetchone()[0]
        result['surface_treatments']=a.execute('SELECT count(*) FROM material_surface_treatments').fetchone()[0]
    snapshots=[]
    for path in (args.first,args.second):
        os.environ['PMC_ENGINEERING_DB']=str(path.resolve());start=time.perf_counter();rows=engineering_db.materials()
        snapshots.append(rows)
        result['materials_api_ms']=round((time.perf_counter()-start)*1000,1)
    assert snapshots[0]==snapshots[1]
    rows=snapshots[0];assert len(rows)==sum(r['core_material']['status']=='ENGINEERING' for r in data['identities'])
    assert not {'material_1','material_2'}&{r['id'] for r in rows}
    result['selectable_count']=len(rows);result['materials_response_bytes']=len(json.dumps(rows).encode())
    result['selectable']=[dict(runtime_id=r['id'],research_id=r['technical_identity_id'],display_name=r['display_name'],family=r['material_type']) for r in rows]
    result['research_only']=[dict(id=r['id'],reason=r['core_material']['reason']) for r in data['identities'] if r['core_material']['status']=='RESEARCH_ONLY']
    assert all(r['engineering_defaults']['allowable_stress_mpa'] is None for r in rows)
    result['conditional_checks']={}
    for mid,prop,context in [('MAT-6082','yield_strength_Rp0.2',{}),('MAT-C45','yield_strength_Rp0.2',{}),
        ('MAT-CORE-7075-T651-PLATE','yield_strength',{'product_form':'Extruded bar'})]:
        fact=resolved_engineering_facts('material',mid,context=context)['facts'][prop]
        assert fact['value'] is None;result['conditional_checks'][mid]=fact['status']
    result['validation']='PASS'
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('deterministic_tables','cartridge_preserved','selectable')},ensure_ascii=True))


if __name__=='__main__':main()
