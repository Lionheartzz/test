"""Source-bound identities; an ordering suffix is never guessed or stripped."""
import json
from functools import lru_cache
from ..engineering_db import _connect,database_path


def norm(value):return ''.join(character for character in str(value or '').casefold() if character.isalnum())


def _aliases(original):
    # Only explicitly named identity fields, never prose or source URL selectors.
    blocks=[original,*original.get('master_records',[]),*original.get('normalization',[])]
    for block in blocks:
        if not isinstance(block,dict):continue
        status=str(block.get('normalization_status','')).upper()
        if any(x in status for x in ('UNRESOLVED','CONFLICT','REJECTED')):continue
        for key in ('full_part_number','normalized_full_part_number'):
            if isinstance(block.get(key),str):yield block[key]
        for key in ('source_aliases','aliases'):
            for alias in block.get(key,[]) if isinstance(block.get(key),list) else []:
                if isinstance(alias,str):yield alias


@lru_cache(maxsize=4)
def _runtime(stamp):
    with _connect() as db:return [dict(r) for r in db.execute('SELECT * FROM cartridges WHERE active=1 ORDER BY id')]


@lru_cache(maxsize=4)
def _catalog(stamp):
    with _connect() as db:
        runtime=_runtime(stamp)
        supported={r[0] for r in db.execute("""SELECT DISTINCT l.identity_id FROM technical_identity_evidence l
            JOIN technical_evidence_sources s ON s.domain=l.domain AND s.evidence_id=l.evidence_id WHERE l.domain='cartridge'""")}
        conflicted={r[0] for r in db.execute("""SELECT l.identity_id FROM technical_identity_conflicts l JOIN technical_conflicts c
            ON c.domain=l.domain AND c.id=l.conflict_id WHERE l.domain='cartridge'
            AND c.property IN ('identity','model','manufacturer','base_model','full_part_number','alias','aliases','ordering_code','source_alias')
            AND c.resolution NOT IN ('RESOLVED','CONFIRMED')""")}
        identities=[dict(r) for r in db.execute("""SELECT id,cartridge_id,full_part_number,base_model,product_family,manufacturer_original,disposition
            FROM technical_identities WHERE domain='cartridge'""") if r['id'] in supported-conflicted and
            not any(x in r['disposition'].upper() for x in ('UNRESOLVED','CONFLICT','REJECTED','REFERENCE_ONLY'))]
        allowed={r['cartridge_id'] for r in identities};makers={r['id']:{r['manufacturer']} for r in runtime};aliases={};bases={}
        for row in identities:
            makers.setdefault(row['cartridge_id'],set()).add(row['manufacturer_original'])
            aliases.setdefault(norm(row['full_part_number']),set()).add(row['cartridge_id'])
            for key in ('base_model',):
                if row[key]:bases.setdefault(norm(row[key]),set()).add(row['cartridge_id'])
        for row in db.execute("""SELECT id,original_json FROM technical_identities WHERE domain='cartridge'
            AND (original_json LIKE '%"aliases"%' OR original_json LIKE '%"source_aliases"%')"""):
            if row['id'] in allowed:
                for alias in _aliases(json.loads(row['original_json'])):aliases.setdefault(norm(alias),set()).add(row['id'])
        # The property/scope index avoids reading large evidence JSON payloads.
        for row in db.execute("""SELECT l.identity_id,e.applicable_option,e.manufacturer,e.raw_value FROM technical_evidence e
            INDEXED BY technical_evidence_property JOIN technical_identity_evidence l ON l.domain=e.domain AND l.evidence_id=e.id
            WHERE e.domain='cartridge' AND e.scope='FULL_PART_NUMBER' AND e.applicable_option<>''
            AND EXISTS(SELECT 1 FROM technical_evidence_sources s WHERE s.domain=e.domain AND s.evidence_id=e.id)"""):
            if row['identity_id'] in allowed and row['raw_value'] and not row['raw_value'].upper().startswith(('NOT_FOUND','NOT_STATED','NOT_APPLICABLE','UNRESOLVED','REFERENCE_ONLY','REJECTED','CONFLICT')):
                aliases.setdefault(norm(row['applicable_option']),set()).add(row['identity_id']);makers[row['identity_id']].add(row['manufacturer'])
    for row in runtime:row['manufacturer_aliases']=sorted(makers[row['id']])
    return runtime,aliases,bases


def resolve_cartridge_identity(model,manufacturer=None):
    wanted=norm(model);maker=norm(manufacturer)
    if not wanted:return dict(code='cartridge_identity_missing',recognized_model=model,recognized_manufacturer=manufacturer,method=None,cartridge_id=None,candidates=[])
    path=database_path();stamp=(str(path),path.stat().st_mtime_ns);runtime=_runtime(stamp)
    def acceptable(row):return not maker or maker in {norm(m) for m in row.get('manufacturer_aliases',[row['manufacturer']])}
    matches=[r for r in runtime if wanted and norm(r['model'])==wanted and acceptable(r)]
    method='exact_manufacturer_model' if maker else 'exact_model'
    if not matches:
        runtime,aliases,bases=_catalog(stamp)
        matches=[r for r in runtime if norm(r['model'])==wanted and acceptable(r)]
    if not matches:
        matches=[r for r in runtime if r['id'] in aliases.get(wanted,set()) and acceptable(r)];method='source_backed_alias'
    if not matches:
        matches=[r for r in runtime if r['id'] in bases.get(wanted,set()) and acceptable(r)];method='source_backed_base_identity'
    return dict(code='resolved' if len(matches)==1 else 'cartridge_identity_ambiguous' if matches else 'cartridge_identity_missing',
                recognized_model=model,recognized_manufacturer=manufacturer,method=method if matches else None,
                cartridge_id=matches[0]['id'] if len(matches)==1 else None,candidates=matches)
