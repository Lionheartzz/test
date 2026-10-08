import json
import sqlite3
from contextlib import closing

import pytest

from manifold import activate_closure_v8 as deployment
from manifold import engineering_db,library_schema,generic_closures


def source(path):
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    engineering_db.initialize_schema(db);library_schema.initialize(db);generic_closures.reconcile(db)
    db.execute('INSERT INTO tool_definitions VALUES (?,?,?,?,?,1,1)',('existing','drill',8,80,'metric'))
    db.execute('CREATE INDEX preserved_tool_index ON tool_definitions(diameter_mm)')
    db.commit();return db


def bundle(db):
    additions={table:dict(columns=[r[1] for r in db.execute('PRAGMA table_info('+table+')')],rows=[])
               for table in deployment.ADDITIVE_TABLES}
    additions['tool_definitions']['rows']=[['new-source-tap','tap',10,20,'metric',1,1]]
    return dict(format=1,from_schema=7,to_schema=8,additions=additions,external_port_dependencies=[])


def test_explicit_bundle_adds_supported_tool_kinds_without_replacing_existing_rows(tmp_path):
    db=source(tmp_path/'source.db');b=bundle(db)
    before=tuple(db.execute('SELECT * FROM tool_definitions').fetchone())
    db.execute('BEGIN IMMEDIATE');deployment.apply_bundle(db,b);db.commit()
    assert db.execute('PRAGMA user_version').fetchone()[0]==8
    assert tuple(db.execute("SELECT * FROM tool_definitions WHERE id='existing'").fetchone())==before
    assert db.execute("SELECT tool_type FROM tool_definitions WHERE id='new-source-tap'").fetchone()[0]=='tap'
    assert db.execute("SELECT 1 FROM sqlite_master WHERE name='preserved_tool_index'").fetchone()
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    db.close()


def test_bundle_conflict_rolls_back_instead_of_upserting(tmp_path):
    db=source(tmp_path/'source.db');b=bundle(db)
    b['additions']['tool_definitions']['rows'][0][0]='existing'
    before=deployment.table_hashes(db)
    db.execute('BEGIN IMMEDIATE')
    with pytest.raises(sqlite3.IntegrityError):deployment.apply_bundle(db,b)
    db.rollback()
    assert db.execute('PRAGMA user_version').fetchone()[0]==7
    assert deployment.table_hashes(db)==before
    db.close()


def test_bundle_declines_missing_or_changed_source_interface(tmp_path):
    db=source(tmp_path/'source.db');b=bundle(db);b['external_port_dependencies']=[dict(id='missing')]
    with pytest.raises(ValueError,match='Source interface differs'):deployment.apply_bundle(db,b)
    assert db.execute('PRAGMA user_version').fetchone()[0]==7
    db.close()


def test_existing_custom_writers_archive_restore_keep_v8(tmp_path,monkeypatch):
    from manifold.schema import CavityDefinition
    path=tmp_path/'custom-v8.db';db=source(path)
    db.execute('BEGIN IMMEDIATE');deployment.apply_bundle(db,bundle(db));db.commit()
    definition=CavityDefinition(id='user-input',label='Explicit custom test definition',unit_system='custom',
        stages=[dict(start=0,end=20,diameter=12)],zones=[dict(id='port1',start=10,end=20,diameter=8)],
        clearance_diameter=16,clearance_height=20)
    cavity=engineering_db.create_custom_cavity(definition,connection=db)
    port=engineering_db.create_custom_external_port(definition.model_copy(update={'kind':'external-port'}),connection=db)
    db.commit();monkeypatch.setenv('PMC_ENGINEERING_DB',str(path))
    for item in (cavity,port):
        assert not engineering_db.set_custom_active(item.id,False).active
        assert engineering_db.set_custom_active(item.id,True).active
    assert db.execute('PRAGMA user_version').fetchone()[0]==8
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    db.close()


def test_activation_requires_stopped_service_and_exact_accepted_hash(tmp_path):
    for stopped,sha in ((False,'0'*64),(True,'0'*64)):
        active=tmp_path/'active.db';candidate=tmp_path/'candidate.db';active.write_bytes(b'active');candidate.write_bytes(b'candidate')
        with pytest.raises(ValueError):deployment.activate(candidate,active=active,expected_sha=sha,
            backup=tmp_path/'backup.db',report=tmp_path/'report.json',server_stopped=stopped)
        assert active.read_bytes()==b'active' and not (tmp_path/'backup.db').exists()


def test_atomic_activation_preserves_backup_and_candidate(tmp_path,monkeypatch):
    # Exercise replacement/backups independently of engineering-profile validation,
    # which is verified on the accepted full candidate in release preflight.
    active=tmp_path/'active.db';candidate=tmp_path/'candidate.db'
    db=source(active);db.close()
    with closing(sqlite3.connect(active)) as old,closing(sqlite3.connect(candidate)) as new:
        old.backup(new);new.execute('PRAGMA user_version=8');new.commit()
    monkeypatch.setattr(deployment,'verify_pair',lambda *_:dict(intentional_tables=[]))
    before=deployment.digest_file(active);sha=deployment.digest_file(candidate)
    result=deployment.activate(candidate,active=active,expected_sha=sha,backup=tmp_path/'backup.db',
                               report=tmp_path/'activation.json',server_stopped=True)
    assert result['schema']==8 and deployment.digest_file(active)==deployment.digest_file(candidate)==sha
    assert deployment.digest_file(tmp_path/'backup.db')==before
    assert json.loads((tmp_path/'activation.json').read_text())['after_sha256']==sha
