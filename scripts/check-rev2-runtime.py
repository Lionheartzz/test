"""Read-only acceptance of two explicit REV2 runtime rebuilds."""
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
from manifold import engineering_db, technical_schema
from manifold.engineering_facts import resolved_engineering_facts, ai_context
from manifold.import_technical_knowledge import preserved_tables


def table_digest(db,table,where=''):
    columns=db.execute(f'PRAGMA table_info({table})').fetchall()
    h=hashlib.sha256();count=0
    for row in db.execute(f"SELECT * FROM {table} {where} ORDER BY {','.join(str(i+1) for i in range(len(columns)))}"):
        h.update((json.dumps(tuple(row),ensure_ascii=False,separators=(',',':'))+'\n').encode());count+=1
    return dict(count=count,sha256=h.hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('source','first','second','report'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();result={}
    with sqlite3.connect(args.source.resolve().as_uri()+'?mode=ro',uri=True) as source, \
         sqlite3.connect(args.first.resolve().as_uri()+'?mode=ro',uri=True) as a, \
         sqlite3.connect(args.second.resolve().as_uri()+'?mode=ro',uri=True) as b:
        old=preserved_tables(source);new=preserved_tables(a)
        assert {k:v for k,v in old.items() if k!='materials'}=={k:v for k,v in new.items() if k!='materials'}
        result['compatibility_before']=table_digest(source,'cartridge_cavities','WHERE valid=1')
        result['compatibility_after']=table_digest(a,'cartridge_cavities','WHERE valid=1')
        assert result['compatibility_before']==result['compatibility_after']
        result['rebuild_tables']={}
        for table in [*technical_schema.TABLES,'materials','material_stock']:
            if table=='technical_import_batches':continue
            da,db=table_digest(a,table),table_digest(b,table);assert da==db,table
            result['rebuild_tables'][table]=da
        for db in (a,b):
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        result['schema']=a.execute('PRAGMA user_version').fetchone()[0]
        result['materials_before']=source.execute('SELECT * FROM materials ORDER BY id').fetchall()
        result['materials_after']=a.execute('SELECT * FROM materials ORDER BY id').fetchall()
        for row in result['materials_before']:assert row in result['materials_after']
        result['mdtools_rev1_domain_preservation']='All existing executable tables and original material rows identical'
        result['stock_before_after']=[source.execute('SELECT count(*) FROM material_stock').fetchone()[0],a.execute('SELECT count(*) FROM material_stock').fetchone()[0]]
        result['supplier_stock']=a.execute('SELECT count(*) FROM material_supplier_stock').fetchone()[0]
        result['treatments']=a.execute('SELECT count(*) FROM material_surface_treatments').fetchone()[0]
        representatives=[('Sun','Sun Hydraulics','RDFA3'),('non_Sun','TRIES','519.022')]
        chosen={label:a.execute('SELECT id FROM cartridges WHERE manufacturer=? AND model=?',(maker,model)).fetchone()[0] for label,maker,model in representatives}
        for label,disposition in [('ambiguous','IDENTITY_AMBIGUOUS'),('relation_only','RELATION_SOURCE_ONLY')]:
            chosen[label]=a.execute("SELECT id FROM technical_identities WHERE domain='cartridge' AND disposition=? ORDER BY id LIMIT 1",(disposition,)).fetchone()[0]
        chosen['conflicted']=a.execute("""SELECT l.identity_id FROM technical_identity_conflicts l
            JOIN technical_conflicts c ON c.domain=l.domain AND c.id=l.conflict_id
            WHERE l.domain='cartridge' AND c.property='maximum_working_pressure' AND c.preferred_evidence_id IS NULL ORDER BY l.identity_id LIMIT 1""").fetchone()[0]
    os.environ['PMC_ENGINEERING_DB']=str(args.first.resolve())
    start=time.perf_counter();material_a=engineering_db.materials();elapsed=time.perf_counter()-start
    os.environ['PMC_ENGINEERING_DB']=str(args.second.resolve());assert engineering_db.materials()==material_a
    os.environ['PMC_ENGINEERING_DB']=str(args.first.resolve())
    result['materials_request_ms']=round(elapsed*1000,1);result['materials_response_bytes']=len(json.dumps(material_a).encode())
    assert len(material_a)==9
    result['representatives']={label:resolved_engineering_facts('cartridge',identifier) for label,identifier in chosen.items()}
    for label in ('Sun','non_Sun'):
        assert result['representatives'][label]['facts']['maximum_working_pressure']['status']=='SOURCE_BACKED'
    for label in ('ambiguous','relation_only'):
        assert all(f['value'] is None for f in result['representatives'][label]['facts'].values())
    assert result['representatives']['conflicted']['facts']['maximum_working_pressure']['value'] is None
    context=ai_context(cartridge_ids=chosen.values());assert len(context['materials'])==7
    result['ai_materials']=len(context['materials']);result['ai_cartridges']=len(context['cartridges'])
    result['allowable_defaults']=[row['engineering_defaults']['allowable_stress_mpa'] for row in material_a]
    assert all(v is None for v in result['allowable_defaults'])
    result['validation']='PASS';args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rebuild_tables','representatives','materials_after')},ensure_ascii=True))


if __name__=='__main__':main()
