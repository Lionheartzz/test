"""Read-only inventory and relationship audit of original Access databases.

Run with a Python containing pyodbc and the Microsoft Access ODBC driver.
Only SELECT and ODBC metadata calls are used. Hashes are checked again after closing.
The optional exported inventory mode is explicitly not an original-database inspection.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime,timezone

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def audit_source(source):
    import pyodbc
    drivers=[d for d in pyodbc.drivers() if 'Access' in d and '*.mdb' in d]
    if not drivers:raise RuntimeError('Microsoft Access ODBC driver unavailable')
    files=sorted(p for p in source.rglob('*') if p.suffix.lower() in {'.mdb','.accdb'})
    if not files:raise RuntimeError('No original Access databases found')
    databases=[]
    for path in files:
        before=sha(path);tables=[]
        if any(c in str(path.resolve()) for c in ';{}'):raise ValueError('Choose a source path without ODBC delimiters')
        connection=pyodbc.connect(f'DRIVER={{{drivers[-1]}}};DBQ={path.resolve()};ReadOnly=1;',autocommit=True)
        try:
            cursor=connection.cursor()
            names=[t.table_name for t in cursor.tables(tableType='TABLE') if not t.table_name.startswith(('MSys','~'))]
            for name in names:
                columns=[dict(name=c.column_name,type=c.type_name) for c in cursor.columns(table=name)]
                table_name='['+name.replace(']',']]')+']'
                count=cursor.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()[0]
                candidate=[c['name'] for c in columns if re.search(r'cartridge|valve|part.?no|part.?num|model|envel|bound|service',c['name'],re.I)]
                values={}
                for col in candidate:
                    q='['+col.replace(']',']]')+']'
                    rows=cursor.execute(f'SELECT {q} FROM {table_name}').fetchall()
                    filled=[str(row[0]) for row in rows if row[0] is not None and str(row[0]).strip()]
                    values[col]=dict(nonempty=len(filled),distinct=len(set(filled)),examples=list(dict.fromkeys(filled))[:5])
                try:
                    keys=[dict(primary_table=k.pktable_name,primary_column=k.pkcolumn_name,foreign_column=k.fkcolumn_name) for k in cursor.foreignKeys(table=name)]
                    key_status='inspected'
                except pyodbc.Error:
                    keys=[];key_status='driver metadata unavailable'
                tables.append(dict(name=name,row_count=count,columns=columns,candidate_fields=values,foreign_keys=keys,foreign_key_status=key_status))
        finally:connection.close()
        after=sha(path)
        if before!=after:raise RuntimeError(f'Source file hash changed: {path.name}')
        databases.append(dict(file=path.name,sha256=before,sha256_after=after,unchanged=True,tables=tables))
    return dict(mode='original-databases-read-only',databases=databases)

def audit_export(root):
    inventory=json.loads((root/'reports/inventory.json').read_text(encoding='utf-8'))
    databases=[]
    for db in inventory['databases']:
        tables=[]
        for table in db['tables']:
            columns=[c['name'] for c in table['columns']]
            relevant=[c for c in columns if re.search(r'cartridge|valve|part.?no|part.?num|model|envel|bound|service',c,re.I)]
            raw=root/'raw'/Path(db['file']).stem/(table['name']+'.jsonl')
            values={}
            if relevant and raw.exists():
                rows=[json.loads(line) for line in raw.read_text(encoding='utf-8').splitlines() if line.strip()]
                for col in relevant:
                    filled=[str(r[col]) for r in rows if r.get(col) is not None and str(r[col]).strip()]
                    values[col]=dict(nonempty=len(filled),distinct=len(set(filled)),examples=list(dict.fromkeys(filled))[:5])
            tables.append(dict(name=table['name'],row_count=table['row_count'],columns=columns,candidate_fields=values))
        databases.append(dict(file=db['file'],historical_database_sha256=db['sha256'],tables=tables))
    return dict(mode='historical-raw-export-only',original_databases_inspected=False,
                limitation='Original MDB files were not available at this path. Exported columns and rows cannot prove the current contents or database relationships.',databases=databases)

if __name__=='__main__':
    parser=argparse.ArgumentParser();g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--source',type=Path);g.add_argument('--export',type=Path)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    source_root=(args.source or args.export).resolve()
    if args.out.suffix.lower()!='.json' or args.out.resolve().is_relative_to(source_root):
        parser.error('Write the JSON report outside the source directory')
    if args.out.exists():parser.error('Choose a new output file to retain prior audit evidence')
    result=audit_source(args.source) if args.source else audit_export(args.export)
    result['generated_at']=datetime.now(timezone.utc).isoformat()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(mode=result['mode'],databases=len(result['databases']),tables=sum(len(d['tables']) for d in result['databases']),output=str(args.out))))
