"""Explicit closure-v8 deployment. Never imported or called at server startup."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid

from .engineering_db import DEFAULT_DB, _connect, validate_database

ADDITIVE_TABLES = ('thread_definitions', 'tool_definitions', 'closure_definitions',
                   'closure_products', 'closure_definition_products')


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def table_hashes(db):
    """Bounded-memory logical hashes, ordered by actual SQLite primary keys."""
    result = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        columns = list(db.execute('PRAGMA table_info(' + quote(name) + ')'))
        keys = [r[1] for r in sorted(columns, key=lambda r: r[5]) if r[5]]
        order = ','.join(quote(k) for k in (keys or [r[1] for r in columns]))
        h = hashlib.sha256(); count = 0
        for row in db.execute('SELECT * FROM ' + quote(name) + ' ORDER BY ' + order):
            h.update(json.dumps(list(row), ensure_ascii=False, separators=(',', ':')).encode())
            h.update(b'\n'); count += 1
        result[name] = dict(count=count, sha256=h.hexdigest())
    return result


def verify_pair(source, candidate):
    validate_database(source, schema_version=7)
    validate_database(candidate, schema_version=8)
    with closing(_connect(source)) as old, closing(_connect(candidate)) as new:
        before = table_hashes(old); after = table_hashes(new)
        if set(before) != set(after):
            raise ValueError('Unexpected added/removed database tables')
        changed = {t for t in before if before[t] != after[t]}
        if not changed <= set(ADDITIVE_TABLES):
            raise ValueError('Unrelated data changed: ' + ', '.join(sorted(changed - set(ADDITIVE_TABLES))))
        preserved = {}
        for table in changed:
            columns = [r[1] for r in old.execute('PRAGMA table_info(' + quote(table) + ')')]
            if columns != [r[1] for r in new.execute('PRAGMA table_info(' + quote(table) + ')')]:
                raise ValueError('Unexpected column changes: ' + table)
            primary = [r[1] for r in sorted(old.execute('PRAGMA table_info(' + quote(table) + ')'), key=lambda r:r[5]) if r[5]]
            where = ' AND '.join(quote(k) + '=?' for k in primary)
            for row in old.execute('SELECT * FROM ' + quote(table)):
                found = new.execute('SELECT * FROM ' + quote(table) + ' WHERE ' + where,
                                    [row[k] for k in primary]).fetchone()
                if found is None or tuple(found) != tuple(row):
                    raise ValueError('Existing row modified/removed in ' + table)
            preserved[table] = before[table]['count']
        # A closure release changes only the tool-type CHECK, preserving named indexes.
        for kind in ('table', 'index'):
            original = {r[0]:r[1] for r in old.execute('SELECT name,sql FROM sqlite_master WHERE type=? AND sql IS NOT NULL', (kind,))}
            updated = {r[0]:r[1] for r in new.execute('SELECT name,sql FROM sqlite_master WHERE type=? AND sql IS NOT NULL', (kind,))}
            if kind == 'table':original.pop('tool_definitions');updated.pop('tool_definitions')
            if original != updated:raise ValueError('Unexpected schema/index changes: ' + kind)
        integrity = new.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys = [tuple(r) for r in new.execute('PRAGMA foreign_key_check')]
        if integrity != 'ok' or foreign_keys:raise ValueError('Candidate integrity/foreign-key failure')
        from .closure_runtime import _catalog, compatible
        from .schema import Feature
        stat = Path(candidate).stat(); rows = _catalog(Path(candidate), stat.st_mtime_ns, stat.st_size)
        if sum(bool(r['usable'] and r['active']) for r in rows) < 103:
            raise ValueError('This accepted closure release requires at least 103 usable definitions')
        for row in rows:
            if not row['usable'] or not row['active']:continue
            probe = Feature(id='closure-check',kind='drilling',face='top',u=500,v=500,
                            circuit='P',diameter=1,depth=1000,plugged=True)
            if not compatible(probe,row):raise ValueError('Incomplete usable closure: ' + row['id'])
        return dict(protected_before=before, protected_after=after, intentional_tables=sorted(changed),
                    existing_rows_preserved=preserved, integrity_check=integrity, foreign_key_check=foreign_keys,
                    runtime_counts={t:new.execute('SELECT count(*) FROM '+quote(t)).fetchone()[0]
                                    for t in (*ADDITIVE_TABLES,'closure_definition_aliases')})


def export_bundle(source, candidate, output):
    """Capture already accepted additions; no raw-source scan or definition regeneration."""
    with closing(_connect(source)) as old, closing(_connect(candidate)) as new:
        tables = {}
        for table in ADDITIVE_TABLES:
            columns = [r[1] for r in old.execute('PRAGMA table_info(' + quote(table) + ')')]
            previous = {tuple(r) for r in old.execute('SELECT * FROM ' + quote(table))}
            tables[table] = dict(columns=columns, rows=[list(r) for r in new.execute('SELECT * FROM ' + quote(table) + ' ORDER BY 1,2') if tuple(r) not in previous])
        ports = {r[2] for r in tables['closure_definitions']['rows']}
        dependencies = [dict(new.execute('SELECT * FROM external_port_definitions WHERE id=?',(key,)).fetchone()) for key in sorted(ports)]
        value = dict(format=1,from_schema=7,to_schema=8,accepted_candidate_sha256=digest_file(candidate),
                     source_archive_sha256='123cff0facd981201e7619815e15eb77da8d27b371d2329c8fac29da5a24e26c',
                     external_port_dependencies=dependencies,additions=tables)
    output = Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    return value


def apply_bundle(db, bundle):
    if bundle.get('format') != 1 or (bundle.get('from_schema'),bundle.get('to_schema')) != (7,8):
        raise ValueError('Unsupported deployment bundle')
    if db.execute('PRAGMA user_version').fetchone()[0] != 7:raise ValueError('Explicit migration requires v7')
    if set(bundle['additions']) != set(ADDITIVE_TABLES):raise ValueError('Unexpected bundle tables')
    for expected in bundle['external_port_dependencies']:
        actual = db.execute('SELECT * FROM external_port_definitions WHERE id=?',(expected['id'],)).fetchone()
        if actual is None or dict(actual) != expected:raise ValueError('Source interface differs: ' + expected['id'])
    from .extend_construction_closures import extend_tool_kinds
    extend_tool_kinds(db)
    for table in ADDITIVE_TABLES:
        entry = bundle['additions'][table]
        actual = [r[1] for r in db.execute('PRAGMA table_info(' + quote(table) + ')')]
        if entry['columns'] != actual:raise ValueError('Bundle column mismatch: ' + table)
        for row in entry['rows']:
            db.execute('INSERT INTO ' + quote(table) + ' VALUES (' + ','.join('?' for _ in actual) + ')',row)
    db.execute('PRAGMA user_version=8')


def migrate(source, bundle_path, output, report):
    source,output = Path(source).resolve(),Path(output).resolve()
    validate_database(source,schema_version=7)
    bundle = json.loads(Path(bundle_path).read_text(encoding='utf-8'))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb'):pass
    with closing(_connect(source)) as old,closing(sqlite3.connect(output)) as new:
        new.row_factory=sqlite3.Row;old.backup(new);new.execute('PRAGMA foreign_keys=ON')
        try:
            new.execute('BEGIN IMMEDIATE');apply_bundle(new,bundle)
            if new.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or new.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Migration integrity/foreign-key failure')
            new.commit()
        except Exception:new.rollback();raise
    result=verify_pair(source,output)
    result.update(source=str(source),candidate=str(output),bundle_sha256=digest_file(bundle_path),
                  candidate_sha256=digest_file(output),schema=8)
    Path(report).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def activate(candidate, *, expected_sha, backup, report, active=DEFAULT_DB, server_stopped=False):
    if not server_stopped:raise ValueError('Stop every backend/worker before activation; --server-stopped is required')
    candidate,active,backup=Path(candidate).resolve(),Path(active).resolve(),Path(backup).resolve()
    if len({candidate,active,backup}) != 3:raise ValueError('Candidate, active and backup must be distinct')
    if digest_file(candidate)!=expected_sha:raise ValueError('Candidate SHA-256 differs from accepted candidate')
    for path in (active,candidate):
        if any(Path(str(path)+suffix).exists() for suffix in ('-wal','-journal')):
            raise ValueError('Database has a journal/WAL; stop writers and checkpoint explicitly first')
    result=verify_pair(active,candidate);before=digest_file(active)
    # Confirm exclusive SQLite access after readers/writers have been stopped.
    with closing(sqlite3.connect(active,timeout=0)) as lock:
        lock.execute('BEGIN EXCLUSIVE');lock.rollback()
    backup.parent.mkdir(parents=True,exist_ok=True)
    with backup.open('xb') as dest,active.open('rb') as src:shutil.copyfileobj(src,dest)
    if digest_file(backup)!=before:raise ValueError('Backup verification failed')
    temp=active.with_name(active.name+'.activation-'+uuid.uuid4().hex)
    try:
        with temp.open('xb') as dest,candidate.open('rb') as src:
            shutil.copyfileobj(src,dest);dest.flush();os.fsync(dest.fileno())
        if digest_file(temp)!=expected_sha or digest_file(active)!=before:
            raise ValueError('Database changed during activation preparation')
        validate_database(temp,schema_version=8)
        os.replace(temp,active)
    finally:
        if temp.exists():temp.unlink()
    result.update(active_path=str(active),before_sha256=before,after_sha256=digest_file(active),
                  backup=str(backup),candidate=str(candidate),schema=validate_database(active)['schema_version'])
    if result['after_sha256']!=expected_sha:raise RuntimeError('Activated bytes do not match candidate; backup retained')
    Path(report).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    migration=sub.add_parser('stage');migration.add_argument('--source',type=Path,default=DEFAULT_DB)
    migration.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parents[1]/'data/migrations/construction-closures-v8.json')
    migration.add_argument('--output',type=Path,required=True);migration.add_argument('--report',type=Path,required=True)
    activation=sub.add_parser('activate');activation.add_argument('--candidate',type=Path,required=True)
    activation.add_argument('--sha256',required=True);activation.add_argument('--backup',type=Path,required=True)
    activation.add_argument('--report',type=Path,required=True);activation.add_argument('--server-stopped',action='store_true')
    args=parser.parse_args()
    result=(migrate(args.source,args.bundle,args.output,args.report) if args.command=='stage' else
            activate(args.candidate,expected_sha=args.sha256,backup=args.backup,report=args.report,server_stopped=args.server_stopped))
    print(json.dumps({k:v for k,v in result.items() if k not in ('protected_before','protected_after')},indent=2))


if __name__=='__main__':main()
