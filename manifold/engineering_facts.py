"""Controlled, bounded REV2 facts for runtime consumers (never compatibility).

Only explicitly mapped meanings participate. A quoted conditional observation is
useful reference information, but is not an unconditional engineering limit.
"""
import hashlib
import json
import math
import re
import sqlite3
from collections import defaultdict

from .engineering_db import _connect

# Maximum, rated, nominal and capacity deliberately remain different meanings.
PROPERTIES = {
    'material': {
        'allowable_stress': ('allowable_stress_mpa', 'MPa'),
        'design_allowable_stress': ('allowable_stress_mpa', 'MPa'),
        'yield_strength': ('yield_strength', 'MPa'),
        'yield_strength_Rp0.2': ('yield_strength_Rp0.2', 'MPa'),
        'tensile_strength': ('tensile_strength', 'MPa'),
        'density': ('density', 'kg/m³'),
        'hardness': ('hardness', None),
        'service_temperature': ('service_temperature', '°C'),
    },
    'cartridge': {
        'maximum_working_pressure': ('maximum_working_pressure', 'bar'),
        'rated_pressure': ('rated_pressure', 'bar'),
        'maximum_flow': ('maximum_flow', 'L/min'),
        'rated_flow': ('rated_flow', 'L/min'),
        'nominal_flow': ('nominal_flow', 'L/min'),
        'capacity': ('capacity', 'L/min'),
        'function_primary': ('function_primary', ''),
        'fluid_temperature_min': ('fluid_temperature_min', '°C'),
        'fluid_temperature_max': ('fluid_temperature_max', '°C'),
        'viscosity': ('viscosity', 'cSt'),
        'internal_leakage': ('internal_leakage', 'mL/min'),
    },
}
SOURCE_TYPES = {
    'MANUFACTURER_OFFICIAL_DATASHEET', 'MANUFACTURER_OFFICIAL_CATALOG',
    'MANUFACTURER_OFFICIAL_PRODUCT_PAGE', 'MANUFACTURER_OFFICIAL_WEBSITE',
    'OFFICIAL_MANUFACTURER_DATASHEET', 'OFFICIAL_MANUFACTURER_CATALOG',
    'OFFICIAL_MANUFACTURER_PRODUCT_DATASHEET', 'OFFICIAL_MANUFACTURER_TECHNICAL_INFORMATION',
    'PRIMARY_PRODUCER_DATASHEET', 'PRIMARY_PRODUCER_GENERATED_MODEL_DATASHEET',
    'OEM_MANUFACTURER_BULLETIN',
    'SUN_GENERATED_CURRENT_MODEL_PDF', 'CURRENT_OFFICIAL_MODEL_PDF',
    'MANUFACTURER_AUTHORED_CATALOGUE_THIRD_PARTY_HOST', 'HISTORICAL_OFFICIAL_CATALOG',
    'PRODUCER_OR_SUPPLIER_DATASHEET',
}
UNITS = {
    'MPa': {'mpa': 1, 'n/mm2': 1, 'n/mm^2': 1, 'ksi': 6.894757293, 'psi': .006894757293},
    'bar': {'bar': 1, 'mpa': 10, 'psi': .06894757293},
    'L/min': {'l/min': 1, 'lpm': 1, 'usgpm': 3.785411784},
    'kg/m³': {'kg/m3': 1, 'kg/m^3': 1, 'kg/m³': 1, 'kg/dm3': 1000},
    '°C': {'°c': 1, 'c': 1, 'degc': 1},
    'cSt': {'cst': 1, 'mm2/s': 1, 'mm^2/s': 1},
    'mL/min': {'ml/min': 1, 'cc/min': 1, 'cm3/min': 1},
}


def norm(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).casefold()


def material_actionability(identity, conflicts=()):
    """Identity admission is separate from any individual property conflict."""
    raw = identity['original']
    grade, state, standard = (str(raw.get(k) or '').strip() for k in
                              ('canonical_grade', 'temper_condition', 'standard'))
    core=raw.get('core_material') or {}
    reason = ''
    if core.get('status')=='RESEARCH_ONLY':
        reason=core['reason']
    elif identity['disposition'] in ('IDENTITY_AMBIGUOUS', 'RELATION_SOURCE_ONLY'):
        reason = 'Ambiguous or relation-only identity'
    elif not all((grade, state, standard)):
        reason = 'Grade, standard and material state must all be explicit'
    elif not identity.get('source_supported'):
        reason = 'No attributed registered source evidence supports this material identity'
    elif core and (not core.get('identity_evidence_ids') or not core.get('primary_standard') or
                   not core.get('stock_product_form')):
        reason = 'Primary identity support or exact solid stock form unresolved'
    elif any(term in norm(state + ' ' + standard) for term in
             ('requires confirmation', 'suffix-specific', 'unspecified', 'unknown')):
        reason = 'Standard applicability or grade/state suffix is unresolved'
    elif 'condition and standard-specific applicability to be confirmed' in norm(raw.get('notes')):
        reason = 'Source condition and standard applicability require confirmation'
    elif any(c['property'] in ('identity', 'canonical_grade', 'standard', 'temper_condition') and
             not c.get('preferred_evidence_id') for c in conflicts):
        reason = 'Unresolved conflict in material identity, standard or state'
    key = json.dumps([identity['id'], grade, standard, state], ensure_ascii=False, separators=(',', ':'))
    display_standard=core.get('primary_standard') or standard
    form=core.get('stock_product_form') or raw.get('product_form','')
    display_grade=core.get('display_grade') or grade
    label_state=state+(' ('+form.lower()+')' if core and not reason else '')
    return dict(selectable=not reason, reason=reason, grade=grade, standard=display_standard,
                canonical_standard=standard, additional_standards=core.get('additional_standards',[]),
                state=state, product_form=form, material_family=core.get('material_family') or identity.get('product_family',''),
                runtime_id='material_rev2_' + hashlib.sha256(key.encode()).hexdigest()[:24],
                display_name=f'{display_grade} · {label_state} · {display_standard}')


def _number(value, unit, target):
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value.strip()):
        return None  # ranges, limits, test text and sentinel strings are not scalars
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if target is None:
        return (number, unit) if unit in ('HB', 'HBW', 'HRB', 'HRBW', 'HBN') else None
    # SI prefixes are case-sensitive: megagram Mg is not milligram mg.
    factor = 1000 if target=='kg/m³' and unit=='Mg/m3' else UNITS.get(target, {}).get(norm(unit))
    return (number * factor, target) if factor is not None else None


def _applicability(domain, identity, row, original, context):
    if domain == 'cartridge':
        scope = row['scope']
        # Explicit attribution at import time alone is insufficient for a family.
        if scope == 'FULL_PART_NUMBER' and norm(row['entity_id']) == norm(identity['full_part_number']):
            applies = True
        elif scope == 'BASE_MODEL' and identity['base_model'] and norm(row['entity_id']) == norm(identity['base_model']):
            applies = True
        elif scope == 'OPTION_FAMILY' and context.get('option') and norm(context['option']) == norm(row['applicable_option']):
            applies = norm(row['entity_id']) in (norm(identity['full_part_number']), norm(identity['base_model']))
        else:
            return False, 'Scope/option does not establish exact model applicability'
    else:
        core=identity['original'].get('core_material') or {}
        if core and core.get('status')=='ENGINEERING':
            if row['entity_id']!=identity['id'] or row['id'] not in core.get('parameter_evidence_ids',[]):
                return False,'Evidence is not reviewed for this exact material identity'
            applicability=original.get('applies_to') or {}
            expected=dict(grade=identity['original']['canonical_grade'],state=identity['original']['temper_condition'],
                          product_form=core['stock_product_form'])
            if any(applicability.get(k)!=v for k,v in expected.items()):
                return False,'Exact grade/state/product form not established for this reviewed identity'
            if context.get('product_form') and context['product_form']!=expected['product_form']:
                return False,'Actual stock product form does not match the source'
            if applicability.get('source_profile') and context.get('source_profile')!=applicability['source_profile']:
                return False,'Exact extrusion profile type not established'
            for key in ('producer_variant','standard_basis'):
                if applicability.get(key) and context.get(key)!=applicability[key]:
                    return False,'Source '+key.replace('_',' ')+' not established'
            for key in ('stock_thickness_mm','stock_diameter_mm'):
                interval=applicability.get(key)
                if interval:
                    value=context.get(key)
                    if value is None:return False,'Source size range requires an identified raw-stock '+key
                    if ('min' in interval and value<interval['min'] or 'max' in interval and value>interval['max'] or
                        'min_exclusive' in interval and value<=interval['min_exclusive'] or
                        'max_exclusive' in interval and value>=interval['max_exclusive']):
                        return False,'Raw-stock size is outside the source range'
            if applicability.get('temperature_c') is not None and context.get('temperature_c')!=applicability['temperature_c']:
                return False,'Source temperature condition not established'
            return True,''  # test method/value kind stays attached; no allowable is derived
        scope = original.get('scope_class', row['scope'])
        applies = scope in ('GRADE', 'GRADE_CONDITION', 'GRADE_CONDITION_PRODUCT_FORM', 'GRADE_CONDITION_FORM')
        if norm(row['entity_id']) != norm(identity['id']) or not applies:
            return False, 'Producer variant, form, thickness or test scope needs explicit confirmation'
    condition = row['condition'].strip()
    if condition and norm(condition) != norm(context.get('condition')):
        if domain == 'material':
            raw = identity['original']
            exact = '; '.join(str(raw.get(k) or '') for k in ('temper_condition', 'product_form'))
            if norm(condition) == norm(exact):
                return applies, ''
        return False, 'Conditional observation; operating/test condition not confirmed'
    return applies, ''


def resolved_engineering_facts(domain, identity_id, *, context=None, overrides=None, connection=None):
    return facts_batch(domain, [identity_id], contexts={identity_id: context or {}},
                       overrides={identity_id: overrides or {}}, connection=connection)[identity_id]


def facts_batch(domain, identifiers, *, contexts=None, overrides=None, connection=None):
    """Fixed query count, per-identity/property bounded rows; no evidence dump."""
    if domain not in PROPERTIES:
        raise ValueError('Unsupported engineering fact domain')
    identifiers = list(dict.fromkeys(identifiers))
    if not identifiers:
        return {}
    if len(identifiers) > 50:
        raise ValueError('At most 50 identities per engineering fact batch')
    if connection is None:
        with _connect() as db:
            return facts_batch(domain, identifiers, contexts=contexts, overrides=overrides, connection=db)
    db, contexts, overrides = connection, contexts or {}, overrides or {}
    marks = ','.join('?' for _ in identifiers)
    identities = {}
    for r in db.execute(f'''SELECT i.*,EXISTS(SELECT 1 FROM technical_identity_evidence l
        JOIN technical_evidence_sources s ON s.domain=l.domain AND s.evidence_id=l.evidence_id
        WHERE l.domain=i.domain AND l.identity_id=i.id) AS source_supported
        FROM technical_identities i WHERE domain=? AND id IN ({marks})''', [domain, *identifiers]):
        r = dict(r); r['original'] = json.loads(r.pop('original_json')); identities[r['id']] = r
    conflicts = defaultdict(list)
    for r in db.execute(f'''SELECT l.identity_id,c.* FROM technical_identity_conflicts l
        JOIN technical_conflicts c ON c.domain=l.domain AND c.id=l.conflict_id
        WHERE l.domain=? AND l.identity_id IN ({marks})''', [domain, *identifiers]):
        conflicts[r['identity_id']].append(dict(r))
    properties = list(PROPERTIES[domain])
    pmarks = ','.join('?' for _ in properties)
    reviewed={mid:r['original']['core_material'] for mid,r in identities.items()
              if r['original'].get('core_material',{}).get('status')=='ENGINEERING'}
    review_filter='';review_args=[]
    if reviewed:
        approved=sorted({eid for core in reviewed.values() for eid in core.get('parameter_evidence_ids',[])})
        review_filter=f" AND (v.identity_id NOT IN ({','.join('?' for _ in reviewed)})"
        review_args=list(reviewed)
        if approved:
            review_filter+=f" OR v.evidence_id IN ({','.join('?' for _ in approved)})"
            review_args+=approved
        review_filter+=')'
    rows = [dict(r) for r in db.execute(f'''SELECT * FROM (
        SELECT v.identity_id,v.status AS value_status,e.*,
        row_number() OVER(PARTITION BY v.identity_id,e.property ORDER BY e.id) AS position,
        count(*) OVER(PARTITION BY v.identity_id,e.property) AS total
        FROM technical_values v JOIN technical_evidence e ON e.domain=v.domain AND e.id=v.evidence_id
        WHERE v.domain=? AND v.identity_id IN ({marks}) AND v.property IN ({pmarks}) {review_filter})
        WHERE position<=32 ORDER BY identity_id,property,id''', [domain, *identifiers, *properties, *review_args])]
    sources = defaultdict(list)
    ids = list(dict.fromkeys(r['id'] for r in rows))
    if ids:
        for r in db.execute(f'''SELECT l.evidence_id,s.id,s.title,s.url FROM technical_evidence_sources l
            JOIN technical_sources s ON s.domain=l.domain AND s.id=l.source_id
            WHERE l.domain=? AND l.evidence_id IN ({','.join('?' for _ in ids)}) ORDER BY s.id''', [domain, *ids]):
            sources[r['evidence_id']].append(dict(r))
    grouped = defaultdict(list)
    for r in rows:
        grouped[r['identity_id']].append(r)
    result = {}
    for identifier in identifiers:
        identity = identities.get(identifier)
        facts, references, rejected, seen = {}, [], defaultdict(set), set()
        actionability = material_actionability(identity, conflicts[identifier]) if identity and domain == 'material' else None
        permitted = bool(identity and identity['disposition'] not in ('IDENTITY_AMBIGUOUS', 'RELATION_SOURCE_ONLY'))
        if domain == 'material':
            permitted = permitted and actionability['selectable'] and bool(identity.get('material_id'))
        candidates = defaultdict(list)
        for r in grouped[identifier]:
            prop, target = PROPERTIES[domain][r['property']]
            seen.add(prop)
            raw = json.loads(r['original_json'])
            reason = ''
            if not permitted:
                reason = actionability['reason'] if actionability and actionability['reason'] else 'Identity is not runtime-linked or is ambiguous/relation-only'
            elif r['evidence_class'] != 'parameter':
                reason = 'Evidence is not a technical parameter'
            elif not sources[r['id']] or str(raw.get('source_type', '')).upper() not in SOURCE_TYPES:
                reason = 'Source authority not established for engineering consumption'
            elif r['total'] > 32:
                reason = 'Summary limit reached; complete property resolution required'
            elif r['value_status']=='CONFLICT' and not any(c['property']==r['property'] and c.get('preferred_evidence_id')==r['id'] for c in conflicts[identifier]):
                reason = 'Unresolved value status'
            if not reason:
                for c in conflicts[identifier]:
                    if c['property'] != r['property']:
                        continue
                    if c.get('preferred_evidence_id') != r['id']:
                        reason = 'Unresolved property conflict or non-preferred observation'; break
            value = json.loads(r['normalized_value_json'])
            text_value = target == '' and isinstance(value,str) and value.strip() and not re.search(
                r'\b(NOT_FOUND|NOT_REPORTED|NOT_AVAILABLE|UNKNOWN|UNRESOLVED)\b|^N/A$',value,re.I)
            converted = (str(value), '') if text_value else _number(value, r['normalized_unit'], target)
            if not reason and converted is None:
                reason = 'No unambiguous normalized scalar/unit'
            # Some imported maximum_flow labels actually describe nominal capacity.
            if not reason and prop in ('maximum_flow', 'rated_flow') and re.search(r'\b(nominal|capacity)\b', r['condition'] + ' ' + str(raw.get('source_field_label', '')), re.I):
                reason = 'Nominal/capacity observation is not a maximum/rated flow limit'
            applies, scope_reason = _applicability(domain, identity, r, raw, contexts.get(identifier, {})) if identity else (False, '')
            if not reason and not applies:
                reason = scope_reason
            observation = dict(property=prop, value=converted[0] if converted else value,
                               unit=converted[1] if converted else r['normalized_unit'],
                               condition=r['condition'], scope=r['scope'], evidence_id=r['id'],
                               value_kind=raw.get('value_kind','SOURCE_VALUE'),applicability=raw.get('applies_to',{}),
                               sources=[{k:v for k,v in s.items() if k!='evidence_id'} for s in sources[r['id']][:2]])
            if reason:
                rejected[prop].add(reason)
                has_reference=converted or (value is not None and r['normalized_unit'] and
                    not isinstance(value,bool) and not re.search(r'NOT_FOUND|NOT_REPORTED|UNRESOLVED',str(value),re.I))
                if has_reference and len([x for x in references if x['property']==prop]) < 2:
                    references.append(observation | dict(status='UNRESOLVED', reason=reason, engineering_usable=False))
            else:
                candidates[prop].append(observation)
        for original_prop, (prop, unit) in PROPERTIES[domain].items():
            if prop in facts:
                continue
            choices = candidates[prop]
            distinct = {(str(c['value']), c['unit']) for c in choices}
            if len(distinct) == 1:
                chosen = choices[0]
                facts[prop] = chosen | dict(status='SOURCE_BACKED', source_backed=True, engineering_usable=True,
                                           evidence_ids=[c['evidence_id'] for c in choices][:4])
            else:
                reason = 'Different applicable normalized values; no supported preferred value' if choices else '; '.join(sorted(rejected[prop]))
                facts[prop] = dict(property=prop, value=None, unit=unit, status='UNRESOLVED' if prop in seen else 'NOT_AVAILABLE',
                                   source_backed=False, engineering_usable=False, reason=reason or 'No admitted applicable value')
        # Only an existing engineering field can be overridden. No arbitrary mappings.
        if domain == 'material' and overrides.get(identifier, {}).get('allowable_stress_mpa') is not None:
            value = _number(overrides[identifier]['allowable_stress_mpa'], 'MPa', 'MPa')
            if value and 0 < value[0] <= 5000:
                facts['allowable_stress_mpa'] = dict(property='allowable_stress_mpa', value=value[0], unit='MPa',
                    status='USER_OVERRIDE', source_backed=False, engineering_usable=True)
        result[identifier] = dict(domain=domain, identity_id=identifier,
            runtime_id=(identity.get('material_id') if domain=='material' else identity.get('cartridge_id')) if identity else None,
            disposition=identity['disposition'] if identity else 'NOT_RESEARCHED',
            identity=actionability, facts=facts, references=references,
            evidence_available=bool(grouped[identifier]), runtime_linked=permitted)
    return result


def promote_materials(db, *, refresh_metadata=False):
    """Explicit importer only; no startup writes, name merges or supplier-stock promotion."""
    report = []
    cursor = db.cursor(); cursor.row_factory = sqlite3.Row
    for r in cursor.execute("""SELECT i.*,EXISTS(SELECT 1 FROM technical_identity_evidence l
        JOIN technical_evidence_sources s ON s.domain=l.domain AND s.evidence_id=l.evidence_id
        WHERE l.domain=i.domain AND l.identity_id=i.id) AS source_supported
        FROM technical_identities i WHERE domain='material' ORDER BY id""").fetchall():
        identity = dict(r); identity['original'] = json.loads(identity.pop('original_json'))
        conflicts = [dict(c) for c in cursor.execute('''SELECT c.* FROM technical_identity_conflicts l
            JOIN technical_conflicts c ON c.domain=l.domain AND c.id=l.conflict_id WHERE l.domain='material' AND l.identity_id=?''', (r['id'],))]
        decision = material_actionability(identity, conflicts)
        if decision['selectable']:
            row = (decision['runtime_id'], decision['display_name'], decision['material_family'], 1)
            existing = db.execute('SELECT * FROM materials WHERE id=?', (row[0],)).fetchone()
            if existing and tuple(existing) != row:
                if not refresh_metadata or not identity['original'].get('core_material'):
                    raise ValueError('Stable promoted material identity conflicts with existing runtime material')
                if existing[3]!=1:raise ValueError('Material review cannot silently restore an archived identity')
                db.execute('UPDATE materials SET display_name=?,material_type=? WHERE id=?',(row[1],row[2],row[0]))
            if not existing:
                db.execute('INSERT INTO materials VALUES (?,?,?,?)', row)
            db.execute("UPDATE technical_identities SET material_id=? WHERE domain='material' AND id=?", (row[0], r['id']))
        report.append(dict(identity_id=r['id'], **decision))
    return report


def engineering_review(design):
    """Compare existing net requirements, without new FAIL or certification rules."""
    selected = {}
    for feature in design.features:
        if feature.cartridge_id:
            selected[feature.id] = (feature.cartridge_id, feature.interface_nets)
    for component in design.schematic_intent.components if design.schematic_intent else []:
        if component.cartridge_id and component.placement_id not in selected:
            selected[component.id] = (component.cartridge_id, component.interface_nets)
    identifiers = sorted({cid for cid, _ in selected.values()})
    facts = {}
    for start in range(0, len(identifiers), 50):
        facts.update(facts_batch('cartridge', identifiers[start:start+50]))
    checks = []
    from .engineering_conditions import effective_net
    nets = {net.id:effective_net(design,net) for net in design.nets}
    for subject, (cid, assignments) in selected.items():
        for nid in sorted(set(assignments.values())):
            if nid not in nets:
                continue
            for quantity, maximum, rated in (('pressure_bar', 'maximum_working_pressure', 'rated_pressure'),
                                              ('flow_lpm', 'maximum_flow', 'rated_flow')):
                required = getattr(nets[nid], quantity)
                if required is None:
                    continue
                available = [facts[cid]['facts'][p] for p in (maximum, rated) if facts[cid]['facts'][p]['status']=='SOURCE_BACKED']
                if not available:
                    checks.append(dict(subject=subject, cartridge_id=cid, net_id=nid, status='WARNING',
                        property=maximum, required=required, message='Applicable cartridge '+maximum.replace('_',' ')+' unresolved', fact=None))
                for fact in available:
                    exceeded = required > fact['value']
                    checks.append(dict(subject=subject, cartridge_id=cid, net_id=nid, status='WARNING' if exceeded else 'INFO',
                        property=fact['property'], required=required, fact=fact,
                        message=f"Required {required:g} {fact['unit']} {'exceeds' if exceeded else 'is within'} sourced {fact['property'].replace('_',' ')} {fact['value']:g} {fact['unit']}"))
    return dict(cartridges=facts, checks=checks, certification=False)


def ai_context(requirements='', cartridge_ids=()):
    """Small structured reference context; does not admit schematic claims or matches."""
    from .engineering_db import materials, search_cartridges
    rows = materials()
    identifiers = set(cartridge_ids)
    tokens = re.findall(r'\b[A-Z0-9][A-Z0-9_-]{3,30}\b', requirements)
    for token in list(dict.fromkeys(tokens))[:8]:
        for row in search_cartridges(token, limit=10)['items']:
            if norm(row['model']) == norm(token):
                identifiers.add(row['id'])
    summaries = facts_batch('cartridge', sorted(identifiers)[:12])
    return dict(materials=[dict(runtime_id=r['id'], display_name=r['display_name'],
        engineering_facts=r['engineering_facts_summary']) for r in rows if r.get('technical_identity_id')],
        cartridges=list(summaries.values()),
        instruction='Only SOURCE_BACKED engineering_usable facts apply. UNRESOLVED/reference observations are not limits. '
                    'Missing values remain missing. Exact runtime IDs required. Technical ratings never establish cavity compatibility.')
