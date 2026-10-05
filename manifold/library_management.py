"""Explicit custom-definition lifecycle; machining identities stay immutable."""
import hashlib
import json
import sqlite3
from . import store
from .engineering_db import _connect, _get_definition, create_custom_cavity, create_custom_external_port


def definition_revision(definition):
    return hashlib.sha256(json.dumps(definition.model_dump(),sort_keys=True,separators=(',',':'),
                                     ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _custom(connection, identifier, expected):
    if not identifier.startswith(('custom_', 'legacy_')):
        raise ValueError('Master records are read-only. Duplicate as Custom to make changes.')
    try:current=_get_definition(connection,identifier,include_inactive=True)
    except ValueError:raise ValueError('This custom record is no longer available. Refresh the library.') from None
    if definition_revision(current)!=expected:
        raise ValueError('This record changed. Refresh it before editing or deleting.')
    return current


def edit_custom(identifier, definition, expected):
    with store.project_lock(), _connect(writable=True) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        current=_custom(connection,identifier,expected)
        if definition.kind!=current.kind:
            raise ValueError('A custom edit cannot change the definition type.')
        create=create_custom_cavity if current.kind=='cavity' else create_custom_external_port
        try:saved=create(definition,connection=connection)
        except sqlite3.IntegrityError:
            raise ValueError('The machining definition refers to unavailable library data. Select a valid definition and retry.') from None
        table='cavities' if current.kind=='cavity' else 'external_port_definitions'
        connection.execute(f'UPDATE {table} SET active=0 WHERE id=?',(identifier,))
        return saved


def _contains_reference(value, identifier):
    if isinstance(value,dict):
        keys={'cavity_id','port_definition_id','cavity_definition','definition','definition_id','construction_port_definition_id'}
        return any(key in keys and item==identifier or key=='definition_key' and item=='db:'+identifier or _contains_reference(item,identifier)
                   for key,item in value.items())
    if isinstance(value,list):return any(_contains_reference(item,identifier) for item in value)
    return False


def _project_references(identifier):
    saved=store.PROJECT.parent/'saved'
    try:
        paths=list(saved.rglob('*.json')) if saved.exists() else []
        if store.PROJECT.is_file():paths.append(store.PROJECT)
        for root in (store.OUTPUT/'builds',store.OUTPUT/'ai-design'):
            if root.exists():
                paths.extend(path for path in root.rglob('*.json')
                             if path.name in {'design.json','resolved_design.json','input_design.json','project.json','generation.json'})
    except OSError:
        raise ValueError('Project references could not be checked. Archive this record instead.') from None
    for path in paths:
        try:
            if path.is_symlink():raise ValueError('Linked project data cannot be checked safely.')
            data=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            raise ValueError('Project references could not be checked. Refresh and retry, or archive this record.') from None
        if _contains_reference(data,identifier):return True
    return False


def _engineering_references(connection,identifier,kind):
    if kind=='cavity':
        queries=('SELECT 1 FROM cartridge_cavities WHERE cavity_id=? LIMIT 1',
                 'SELECT 1 FROM cartridge_cavity_evidence_links WHERE cavity_id=? LIMIT 1')
    else:
        queries=('SELECT 1 FROM closure_definitions WHERE construction_port_definition_id=? LIMIT 1',)
    return any(connection.execute(query,(identifier,)).fetchone() for query in queries)


def delete_custom(identifier, expected, confirm_name):
    with store.project_lock(), _connect(writable=True) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        current=_custom(connection,identifier,expected)
        if confirm_name!=current.label:raise ValueError('Type the exact record name to confirm deletion.')
        if _engineering_references(connection,identifier,current.kind) or _project_references(identifier):
            raise ValueError('This record is used by a project, retained build or another engineering record. Archive it instead.')
        try:
            if current.kind=='cavity':
                connection.execute('DELETE FROM cavity_interfaces WHERE cavity_id=?',(identifier,))
            table='cavities' if current.kind=='cavity' else 'external_port_definitions'
            connection.execute(f'DELETE FROM {table} WHERE id=?',(identifier,))
        except sqlite3.IntegrityError:
            raise ValueError('This record is referenced by another engineering record. Archive it instead.') from None
        return dict(deleted=True)
