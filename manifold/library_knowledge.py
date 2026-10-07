"""Read-only research access. These queries grant no execution permission."""
import json
from contextlib import closing

from .engineering_db import _connect, validate_database


def browse(*, domain='', search='', status='', limit=50, offset=0, path=None):
    validate_database(path)
    limit, offset = min(200,max(1,int(limit))), max(0,int(offset))
    where, args = ['1=1'], []
    for column, value in [('domain',domain),('status',status)]:
        if value:
            where.append(column+'=?');args.append(value)
    if search:
        where.append('(instr(lower(raw_identity),lower(?))>0 OR instr(lower(id),lower(?))>0)')
        args.extend([search,search])
    clause=' AND '.join(where)
    with closing(_connect(path)) as db:
        count=db.execute('SELECT count(*) FROM library_targets WHERE '+clause,args).fetchone()[0]
        rows=db.execute('SELECT * FROM library_targets WHERE '+clause+' ORDER BY domain,id LIMIT ? OFFSET ?',
                        args+[limit,offset]).fetchall()
        return dict(count=count,limit=limit,offset=offset,items=[dict(r) for r in rows])


def detail(target_id, *, path=None):
    validate_database(path)
    with closing(_connect(path)) as db:
        row=db.execute('SELECT * FROM library_targets WHERE id=?',(target_id,)).fetchone()
        if row is None:
            return None
        result=dict(row)
        result['original']=json.loads(result.pop('original_json'))
        result['gate']=json.loads(result.pop('gate_json'))
        result['evidence']=[json.loads(r[0]) for r in db.execute('''SELECT e.original_json
            FROM library_evidence e JOIN library_target_evidence l ON l.evidence_id=e.id
            WHERE l.target_id=? ORDER BY e.id''',(target_id,))]
        result['unresolved_evidence_ids']=[r[0] for r in db.execute(
            'SELECT evidence_id FROM library_unresolved_links WHERE target_id=? ORDER BY evidence_id',(target_id,))]
        source_ids=sorted({r.get('source_id','') for r in result['evidence']} - {''})
        result['sources']=[json.loads(r[0]) for sid in source_ids for r in db.execute(
            'SELECT original_json FROM library_sources WHERE id=?',(sid,))]
        result['archive_references']=[dict(r) for e in result['evidence'] if e.get('local_file')
            for r in db.execute('SELECT * FROM library_source_aliases WHERE original_path=?',(e['local_file'],))]
        # Raw variants/field findings are accessible by exact native IDs, without
        # guessing runtime equivalence from display names.
        result['findings']=[json.loads(r[0]) for r in db.execute(
            'SELECT original_json FROM library_records WHERE native_id=? ORDER BY dataset_id,row_key',(target_id,))]
        return result
