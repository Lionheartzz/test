"""REV2 browsing and evidence. Engineering consumption uses engineering_facts."""
import json

from .engineering_db import _connect


def _identity(db, domain, identifier):
    row = db.execute('SELECT * FROM technical_identities WHERE domain=? AND id=?', (domain, identifier)).fetchone()
    if row is None:
        # Existing manual identities may have no research pass; browse remains valid.
        if domain == 'cartridge' and db.execute('SELECT 1 FROM cartridges WHERE id=?', (identifier,)).fetchone():
            return dict(id=identifier, disposition='NOT_RESEARCHED', original={}, domain=domain)
        raise ValueError('Technical identity not found')
    result = dict(row)
    result['original'] = json.loads(result.pop('original_json'))
    return result


def _evidence(rows):
    result = []
    for row in rows:
        value = dict(row)
        value['original'] = json.loads(value.pop('original_json'))
        value['normalized_value'] = json.loads(value.pop('normalized_value_json'))
        result.append(value)
    return result


def evidence(domain, identifier, *, property='', offset=0, limit=40):
    with _connect() as db:
        _identity(db, domain, identifier)
        where = 'l.domain=? AND l.identity_id=?'
        args = [domain, identifier]
        if property:
            where += ' AND e.property=?'
            args.append(property)
        total = db.execute(f'''SELECT count(*) FROM technical_identity_evidence l
            JOIN technical_evidence e ON e.domain=l.domain AND e.id=l.evidence_id WHERE {where}''', args).fetchone()[0]
        rows = _evidence(db.execute(f'''SELECT e.*,l.attribution FROM technical_identity_evidence l
            JOIN technical_evidence e ON e.domain=l.domain AND e.id=l.evidence_id
            WHERE {where} ORDER BY e.property,e.id LIMIT ? OFFSET ?''', [*args, limit, offset]))
        ids = [row['id'] for row in rows]
        sources = {}
        if ids:
            for row in db.execute(f'''SELECT l.evidence_id,s.* FROM technical_evidence_sources l
                JOIN technical_sources s ON s.domain=l.domain AND s.id=l.source_id
                WHERE l.domain=? AND l.evidence_id IN ({','.join('?' for _ in ids)}) ORDER BY s.id''', [domain, *ids]):
                value = dict(row)
                value['original'] = json.loads(value.pop('original_json'))
                sources.setdefault(value.pop('evidence_id'), []).append(value)
        for row in rows:
            row['sources'] = sources.get(row['id'], [])
    return dict(items=rows, total=total, offset=offset, limit=limit)


def summary(domain, identifier):
    with _connect() as db:
        identity = _identity(db, domain, identifier)
        values_total = db.execute('SELECT count(*) FROM technical_values WHERE domain=? AND identity_id=?', (domain, identifier)).fetchone()[0]
        values = _evidence(db.execute('''SELECT e.*,v.status,v.preferred_evidence_id FROM technical_values v
            JOIN technical_evidence e ON e.domain=v.domain AND e.id=v.evidence_id
            WHERE v.domain=? AND v.identity_id=? ORDER BY e.property,e.id LIMIT 200''', (domain, identifier)))
        counts = dict(evidence=db.execute('SELECT count(*) FROM technical_identity_evidence WHERE domain=? AND identity_id=?', (domain, identifier)).fetchone()[0],
                      sources=db.execute('''SELECT count(DISTINCT s.source_id) FROM technical_identity_evidence l
                        JOIN technical_evidence_sources s ON s.domain=l.domain AND s.evidence_id=l.evidence_id
                        WHERE l.domain=? AND l.identity_id=?''', (domain, identifier)).fetchone()[0],
                      conflicts=db.execute('SELECT count(*) FROM technical_identity_conflicts WHERE domain=? AND identity_id=?', (domain, identifier)).fetchone()[0])
        fields = [dict(row) | {'original': json.loads(row['original_json'])} for row in db.execute(
            'SELECT field_group,status,original_json FROM technical_field_status WHERE domain=? AND identity_id=? ORDER BY field_group', (domain, identifier))]
        for row in fields:
            row.pop('original_json')
        result = dict(identity=identity, values=values, values_total=values_total, counts=counts,
                      field_status=fields, execution_permission=False)
        from .engineering_facts import resolved_engineering_facts
        result['engineering_facts'] = resolved_engineering_facts(domain, identifier, connection=db)
        if domain == 'material':
            core=identity['original'].get('core_material') or {}
            primary_ids=core.get('source_ids',[])[:8]
            result['primary_sources']=[]
            if primary_ids:
                for row in db.execute(f"SELECT * FROM technical_sources WHERE domain='material' AND id IN ({','.join('?' for _ in primary_ids)}) ORDER BY id",primary_ids):
                    source=dict(row);source['original']=json.loads(source.pop('original_json'));result['primary_sources'].append(source)
            result['surface_treatments'] = [json.loads(row[0]) for row in db.execute('''
                SELECT t.original_json FROM material_research_links l JOIN material_surface_treatments t ON t.id=l.record_id
                WHERE l.material_id=? AND l.kind='treatment' ORDER BY t.id''', (identifier,))]
            runtime = identity.get('material_id')
            result['engineering_stock'] = [dict(row) for row in db.execute('SELECT * FROM material_stock WHERE material_id=? ORDER BY id', (runtime,))] if runtime else []
            result['supplier_stock_count'] = db.execute("SELECT count(*) FROM material_research_links WHERE material_id=? AND kind='stock'", (identifier,)).fetchone()[0]
    return result


def conflicts(domain, identifier, *, offset=0, limit=10):
    with _connect() as db:
        _identity(db, domain, identifier)
        total = db.execute('SELECT count(*) FROM technical_identity_conflicts WHERE domain=? AND identity_id=?', (domain, identifier)).fetchone()[0]
        rows = [dict(row) for row in db.execute('''SELECT c.* FROM technical_identity_conflicts l
            JOIN technical_conflicts c ON c.domain=l.domain AND c.id=l.conflict_id
            WHERE l.domain=? AND l.identity_id=? ORDER BY c.id LIMIT ? OFFSET ?''', (domain, identifier, limit, offset))]
        ids = [row['id'] for row in rows]
        links = {}
        if ids:
            # A conflict side can reference a whole document. Return bounded samples,
            # preserving the total rather than serializing thousands of rows per side.
            for row in db.execute(f'''SELECT l.conflict_id,l.side,e.*,
                row_number() OVER(PARTITION BY l.conflict_id,l.side ORDER BY e.id) AS position,
                count(*) OVER(PARTITION BY l.conflict_id,l.side) AS side_total
                FROM technical_conflict_evidence l JOIN technical_evidence e ON e.domain=l.domain AND e.id=l.evidence_id
                WHERE l.domain=? AND l.conflict_id IN ({','.join('?' for _ in ids)})''', [domain, *ids]):
                key = (row['conflict_id'], row['side'])
                group = links.setdefault(key, dict(total=row['side_total'], items=[]))
                if row['position'] <= 5:
                    value = _evidence([row])[0]
                    for field in ('conflict_id', 'side', 'position', 'side_total'):
                        value.pop(field)
                    group['items'].append(value)
        for row in rows:
            raw = json.loads(row.pop('original_json'))
            raw.pop('evidence_a_ids_json', None)
            raw.pop('evidence_b_ids_json', None)
            row['original'] = raw
            row['sides'] = {side: links.get((row['id'], side), dict(total=0, items=[])) for side in ('a', 'b')}
    return dict(items=rows, total=total, offset=offset, limit=limit)


def materials():
    with _connect() as db:
        from .engineering_facts import material_actionability
        rows=[]
        for row in db.execute("""SELECT i.*,EXISTS(SELECT 1 FROM technical_identity_evidence l
            JOIN technical_evidence_sources s ON s.domain=l.domain AND s.evidence_id=l.evidence_id
            WHERE l.domain=i.domain AND l.identity_id=i.id) AS source_supported
            FROM technical_identities i WHERE domain='material' ORDER BY full_part_number,id"""):
            item=dict(row);item['original']=json.loads(item.pop('original_json'))
            decision=material_actionability(item)
            rows.append(dict(id=item['id'],runtime_id=item['material_id'],display_name=decision['display_name'],
                material_type=item['product_family'],disposition=item['disposition'],active=True,
                research_only=not bool(item['material_id']) or not decision['selectable'],research_reason=decision['reason']))
    return dict(items=rows, total=len(rows))


def supplier_stock(identifier, offset=0, limit=30):
    with _connect() as db:
        _identity(db, 'material', identifier)
        total = db.execute("SELECT count(*) FROM material_research_links WHERE material_id=? AND kind='stock'", (identifier,)).fetchone()[0]
        rows = [dict(row) for row in db.execute('''SELECT s.* FROM material_research_links l
            JOIN material_supplier_stock s ON s.id=l.record_id WHERE l.material_id=? AND l.kind='stock'
            ORDER BY s.id LIMIT ? OFFSET ?''', (identifier, limit, offset))]
        for row in rows:
            row['original'] = json.loads(row.pop('original_json'))
    return dict(items=rows, total=total, offset=offset, limit=limit, execution_permission=False)
