"""Identity/search adapter for the existing runtime machining-definition catalogue.

Standard aliases identify interface families, never product compatibility or
equivalent machining. Physical variants and canonical definitions stay distinct.
"""
import re
from functools import lru_cache
from ..engineering_db import _connect, database_path


def norm(value):
    return ''.join(character for character in str(value or '').casefold() if character.isalnum())


# Standard terminology from Parker's industrial/electrohydraulic catalogues.
# No valve SKU, geometry or cartridge relationship is established by this table.
ISO_4401_SIZES = {'03': ('3', '6'), '05': ('5', '10'), '07': ('7', '16'),
                  '08': ('8', '25'), '10': ('10', '32')}


def _iso_4401_size(name, family):
    match = re.match(r'^(?:ISO\s*)?4401-(\d{2})-\d{2}-[^\s\[]+', name, re.I)
    if 'iso4401' not in norm(family) or not match:
        return None
    return match[1]


def standard_aliases(name, family):
    size = _iso_4401_size(name, family)
    if size is None:
        return ()
    aliases = [name if name.upper().startswith('ISO') else 'ISO ' + name, 'ISO 4401-' + size]
    if size in ISO_4401_SIZES:
        cetop, ng = ISO_4401_SIZES[size]
        aliases.extend(('CETOP-' + cetop, 'CETOP ' + size, 'NG' + ng))
    return tuple(aliases)


def display_label(name, family):
    size = _iso_4401_size(name, family)
    if size in ISO_4401_SIZES:
        cetop, ng = ISO_4401_SIZES[size]
        code = name if name.upper().startswith('ISO') else 'ISO ' + name
        return 'CETOP-' + cetop + ' / NG' + ng + ' · ' + code
    return name


def hydraulic_label(identifier):
    # import_mdtools prefixes associated footprint windows with their source
    # application name. Retain the actual window label, including TA/TB/X/Y.
    match = re.fullmatch(r'[a-z][a-z0-9]*_([A-Za-z][A-Za-z0-9]*)', identifier)
    return match[1] if match else identifier


@lru_cache(maxsize=4)
def _rows(stamp):
    with _connect() as db:
        rows = [dict(row) for row in db.execute('''SELECT id,name,family,unit_system,
            manufacturer,thread_spec,usable,unusable_reason FROM cavities
            WHERE active=1 ORDER BY name,id''')]
    for row in rows:
        row['aliases'] = standard_aliases(row['name'], row['family'])
        row['search_text'] = norm(' '.join([row['name'], row['family'],
            row['manufacturer'], row['thread_spec'], *row['aliases']]))
    return rows


def rows():
    path = database_path()
    return _rows((str(path), path.stat().st_mtime_ns))


def _standard_words(value):
    return re.sub(r'\b(CETOP|NG)[\s\-\u2010-\u2014\u2212]*0*(\d+)\b', r'\1\2', value, flags=re.I)


def search(query, unit, limit=20):
    # Group standard-size words before punctuation-insensitive matching. This
    # prevents a stray "5" in another definition's edition from matching CETOP 5.
    raw_key = norm(query)
    query = _standard_words(query)
    tokens = [norm(token) for token in query.split() if norm(token)]
    found = [row for row in rows() if all(token in row['search_text'] for token in tokens)
             or raw_key and raw_key in norm(row['name'])]
    found.sort(key=lambda row: (row['unit_system'] != unit, not row['usable'], row['name'], row['id']))
    return found[:limit]


def exact_ids(designation, *, mounting=False):
    """Bind only a full source identity or a documented standard-family identity.

    A family can match several port/orientation variants; the caller must retain
    that ambiguity. Free-text search matches are never an automatic binding.
    """
    literal = norm(designation)
    wanted = norm(_standard_words(str(designation or '')))
    if not wanted:
        return set()
    if mounting:
        aliases={row['id'] for row in rows() if wanted in
                 {norm(_standard_words(alias)) for alias in row['aliases']}}
        families={norm(_standard_words(term)) for size,(cetop,ng) in ISO_4401_SIZES.items()
                  for term in ('ISO 4401-'+size,'CETOP-'+cetop,'NG'+ng)}
        # A mounting standard such as NG6 must not become a same-named
        # cartridge cavity from another library family.
        if aliases or wanted in families:return aliases
    return {row['id'] for row in rows() if literal==norm(row['name']) or wanted in
            {norm(_standard_words(alias)) for alias in row['aliases']}}
