"""Read-only comparison and structural scan for an explicitly rebuilt MDTools DB."""
import argparse
import importlib.util
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from manifold.import_mdtools import DEFAULT_SOURCE, active_revision, number, profile_datum


def definitions(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory = sqlite3.Row
        result = {}
        for table in ('cavities', 'external_port_definitions'):
            for row in db.execute(f'SELECT * FROM {table}'):
                item = dict(row)
                for key in ('stages_json', 'primitives_json', 'machining_json'):
                    item[key] = json.loads(item[key])
                result[item['id']] = item | {'table': table}
        zones = defaultdict(list)
        for row in db.execute('SELECT * FROM cavity_interfaces'):
            zones[row['cavity_id']].append(dict(row))
        for item in result.values():
            if item['table'] == 'cavities':
                item['zones'] = zones[item['id']]
            else:
                item['zones'] = [json.loads(item['interface_json'])] if item['interface_json'] not in ('', '{}') else []
        return result


def sources(path):
    result = {}
    with (path/'cavities_master.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            identity = json.loads(line)
            revision = active_revision(identity)
            if revision:
                result[identity['canonical_id']] = (identity, revision['row'])
    return result


def scan(items, source):
    issues = Counter()
    examples = defaultdict(list)
    checked_steps = 0

    def flag(kind, identifier):
        issues[kind] += 1
        if len(examples[kind]) < 8:
            examples[kind].append(identifier)

    for identifier, item in items.items():
        stages, cuts = item['stages_json'], item['primitives_json']
        if not stages or not cuts:
            flag('empty_profile', identifier)
            continue
        if abs(stages[0]['start']) > 1e-6:
            flag('stage_start_gap', identifier)
        if any(s['start'] >= s['end'] for s in stages):
            flag('stage_start_at_or_after_end', identifier)
        if any(s['start'] < 0 or s['end'] < 0 or p['start'] < 0 or p['end'] < 0
               for s in stages for p in cuts):
            flag('negative_depth', identifier)
        if any(s['diameter'] <= 0 for s in stages) or any(p['diameter'] <= 0 for p in cuts):
            flag('nonpositive_diameter', identifier)
        if any(b['start'] < a['start']-1e-6 or abs(a['end']-b['start']) > 1e-6
               for a,b in zip(stages, stages[1:])):
            flag('nonsequential_stages', identifier)
        if any(b['diameter'] > a['diameter']+1e-6 for a,b in zip(stages, stages[1:])):
            flag('diameter_increase', identifier)
        if any(p['start'] >= p['end'] for p in cuts):
            flag('invalid_primitive_interval', identifier)
        beyond = [p for p in cuts if p['end'] > stages[-1]['end']+1e-6]
        if beyond:
            flag('preserved_legacy_profile' if identifier not in source else
                 'source_backed_footprint_extension' if all(p['source_ref'].startswith('fp_') for p in beyond)
                 else 'primitive_beyond_stage_profile', identifier)
        for zone in item['zones']:
            if not zone or zone['start'] < -1e-6 or zone['end'] > max(p['end'] for p in cuts)+1e-6 or zone['start'] >= zone['end']:
                flag('interface_outside_axial_cut', identifier)
                continue
            if not any(p['end'] > zone['start']+1e-6 and p['start'] < zone['end']-1e-6
                       and abs(p.get('offset_u',0)-zone.get('offset_u',0)) < 1e-6
                       and abs(p.get('offset_v',0)-zone.get('offset_v',0)) < 1e-6 for p in cuts):
                flag('interface_without_mapped_cut', identifier)
        if identifier not in source:
            continue  # Preserved custom/legacy definitions have no active MDTools row.
        identity, row = source[identifier]
        scale = 25.4 if identity['unit'] == 'inch' else 1.0
        pilot_diameter, pilot_limit = number(row.get('Circle12Dia')), number(row.get('MaxCircle12Dia'))
        if pilot_diameter is not None and pilot_limit is not None and pilot_diameter > pilot_limit+1e-6:
            flag('pilot_diameter_exceeds_source_max', identifier)
        if str(row.get('CavityType') or '').upper() == 'CV':
            core = [(i,number(row.get(f'Circle{i}Dia')),number(row.get(f'Circle{i}Depth')))
                    for i in range(1,12) if number(row.get(f'Circle{i}Dia')) and number(row.get(f'Circle{i}Depth')) is not None]
            if core:
                end = max(depth for _,_,depth in core)*scale + profile_datum(row,scale)
                for current, following in zip(core,core[1:]):
                    angle = number(row.get(f'Circle{current[0]}Angle')) or 90
                    if 0 < angle < 90 and current[1] > following[1]:
                        nominal = (current[1]-following[1])*scale/2/math.tan(math.radians(angle))
                        available = (following[2]-current[2])*scale
                        if nominal > available+0.02:
                            flag('source_angle_depth_conflict', identifier)
                last = core[-1]
                pilot = number(row.get('Circle12Dia'))
                angle = number(row.get(f'Circle{last[0]}Angle')) or 90
                if pilot and 0 < angle < 90 and pilot < last[1]:
                    end += (last[1]-pilot)*scale/2/math.tan(math.radians(angle))
                if not row.get('IsSunCavity'):
                    end = max(end, (number(row.get('Circle0Depth')) or 0)*scale)
                if any(p['source_ref'].startswith('main:') and p['end'] > end+0.02 for p in cuts):
                    flag('unexplained_main_depth_jump', identifier)
                if any(p['source_ref'] == 'main:circle12' for p in cuts):
                    flag('unbounded_cv_pilot_executed', identifier)
                if row.get('IsSunCavity') and any(p['source_ref'] == 'main:circle0' for p in cuts):
                    flag('socket_envelope_executed', identifier)
        for operation in item['machining_json']:
            for key, suffix in (('diameter','Dia'),('depth','Depth')):
                match = re.fullmatch(r'\$STEP(\d+)',str(operation.get(key) or '').strip(),re.I)
                if not match:
                    continue
                index = int(match.group(1))
                expected = number(row.get(f'Circle{index}{suffix}'))
                if expected is None:
                    continue
                if suffix == 'Depth' and 1 <= index <= 11:
                    expected += profile_datum(row,1.0)
                checked_steps += 1
                actual = operation.get('diameter_mm' if suffix == 'Dia' else 'depth_mm')
                if actual is None or abs(actual-expected*scale) > 1e-5:
                    flag('machining_step_mismatch', identifier)
    return issues, examples, checked_steps


def stage_table(before, after):
    old, new = before['stages_json'], after['stages_json']
    lines = ['| Stage | Old start–end / Ø mm | New start–end / Ø mm |', '|---:|---|---|']
    for index in range(max(len(old),len(new))):
        def cell(rows):
            return (f"{rows[index]['start']:.2f}–{rows[index]['end']:.2f} / Ø{rows[index]['diameter']:.2f}"
                    if index < len(rows) else '—')
        lines.append(f'| {index+1} | {cell(old)} | {cell(new)} |')
    return '\n'.join(lines)


def raw_t10a_reference(source, identity, row):
    spec=importlib.util.spec_from_file_location('jetmdb',source/'tools'/'jetmdb.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    revision=active_revision(identity)
    original=next(item for item in revision['sources'] if item['release']=='2026-R2')
    filename='InchVESTMDToolsLibrary.mdb' if identity['unit']=='inch' else 'MMVESTMDToolsLibrary.mdb'
    database=module.JetMDB(source/'raw'/'2026-R2'/filename)
    _,records=database.read(original['table'])
    raw=next(item for item in records if item['CavityIndex']==original['cavity_index'])
    fields=('Circle0Dia','Circle0Depth','Circle1Dia','Circle1Depth','Circle12Dia','Circle12Depth','LSMinDepth')
    if any(abs(number(raw[key])-number(row[key]))>1e-6 for key in fields):
        raise ValueError(f'T-10A merged row differs from raw {filename}:{original["table"]}')
    return f'{filename}:{original["table"]} / CavityIndex {original["cavity_index"]}'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    before,after=definitions(args.before),definitions(args.after)
    source=sources(args.source)
    issues,examples,steps=scan(after,source)
    changed=[identifier for identifier in before.keys() & after.keys()
             if any(before[identifier][key]!=after[identifier][key] for key in ('stages_json','primitives_json'))]
    by_table=Counter(after[identifier]['table'] for identifier in changed)
    chosen=[('Sun Hydraulics','T-10A','metric'),('Sun Hydraulics','SC-08-04','inch'),
            ('HydraForce','HVC06-2','inch'),('Parker','CAVT11A','inch'),
            ('Danfoss (Comatrol)','CP04-2','inch'),('Eaton','A12196','inch'),
            ('Bucher Hydraulics','AA','inch'),('Rexroth','003','inch'),('HYDAC','03030','metric')]
    lookup={(identity['display_family'],identity['display_name'],identity['unit']):identifier
            for identifier,(identity,_) in source.items()}
    lines=['# MDTools cavity geometry conversion audit','',
           f'Source: `{args.source}`. Before: `{args.before}`. Rebuilt staging: `{args.after}`.',
           'Both databases were read only for this report. The current runtime database was not replaced.','',
           '## Source interpretation','',
           'Circle1–11 give ordered form diameters at cumulative depths from the locating shoulder. '
           'An explicit LSMinDepth defines that datum; otherwise a CV uses a shallow Circle0Depth as its entry '
           'datum. If Circle0 extends beyond the entire form sequence, it is an independent bore and adds no datum. '
           'Circle0 is an independent entry cut on ordinary profiles. With the MDTools IsSunCavity profile flag, '
           'Circle0 is socket/tool access and is excluded from the fixed form cut. Circle12 is a predrill: '
           'its transition cone is fixed on a CV, while the long pilot reach is a machining reference for a future '
           'connection. On ports, direct holes and bolt/locator footprints, an explicit pilot is a fixed cut. '
           'STEP0 and STEP12 retain their source dimensions and carry tool_clearance/pilot_reference roles where '
           'they are not executable cavity stock removal. Hydraulic windows use the same CV datum and a zero-size '
           'nose port uses the final form land. Source inch fractions such as 7/8 and 1-1/16 are converted '
           'numerically. A nominal cone is limited to the next declared STEP depth when the source angle and '
           'depth disagree. Footprint BH/DH/LP Circle rows with explicit DRILL/TAP operations remain offset '
           'machining cuts; EnvelopDimensions remains a mounting boundary, not a subtraction.','',
           'The SUN first-party general-information drawing identifies Ø31.8 mm as socket-wrench clearance '
           '(not included on the form drill), a separate locating shoulder, and Ø13.49 mm as a maximum nose '
           'dimension: https://www.sunhydraulics.com/sites/default/files/media_library/tech_resources/uk_bm_geninfo.pdf',
           '', '## Before / after','',
           f'- Matched imported definitions with changed stage or primitive geometry: **{len(changed)}** '
           f'({by_table["cavities"]} cavities, {by_table["external_port_definitions"]} external ports).',
           f'- Unchanged matched definitions: **{len(before.keys() & after.keys())-len(changed)}**.',
           '', '| Manufacturer | Name | Unit | Old max depth / Ø mm | New max depth / Ø mm | ID |',
           '|---|---|---|---:|---:|---|']
    for family,name,unit in chosen:
        identifier=lookup.get((family,name,unit))
        if identifier not in before or identifier not in after:
            continue
        old,new=before[identifier],after[identifier]
        measure=lambda item:f"{max(p['end'] for p in item['primitives_json']):.2f} / {max(p['diameter'] for p in item['primitives_json']):.2f}"
        lines.append(f'| {family} | {name} | {unit} | {measure(old)} | {measure(new)} | `{identifier}` |')
    t10a=lookup['Sun Hydraulics','T-10A','metric']
    raw_metric=raw_t10a_reference(args.source,*source[t10a])
    raw_inch=raw_t10a_reference(args.source,*source[lookup['Sun Hydraulics','T-10A','inch']])
    lines += ['', '### SUN T-10A (metric) stage sequence','', stage_table(before[t10a],after[t10a]),'',
              f'Raw MDB parity checked: `{raw_metric}` and `{raw_inch}` match the merged Circle0, Circle1, '
              'Circle12 and LS source fields.',
              f'LSCircleNumber {source[t10a][1]["LSCircleNumber"]} points to '
              f'Circle2Dia {number(source[t10a][1]["Circle2Dia"]):.2f} mm, matching the SUN drawing’s '
              'Ø21.82–21.87 mm locating shoulder. LSMinDepth 0.8 mm supplies the surface offset; '
              'Circle0Depth 33.32 mm is the separate socket/tool access depth.',
              f'Thread note `{after[t10a]["thread_spec"]}` remains present; installation/tool clearance '
              f'Ø{after[t10a]["clearance_diameter"]:.2f} mm is retained outside cutting_primitives. '
              'Machining rows preserve STEP12 as pilot_reference and STEP0 as tool_clearance.','',
              '## Whole-library structural scan','',
              f'- Definitions scanned: **{len(after)}**; resolved source STEP operands checked: **{steps}**.',
              '| Check | Count | Representative IDs |','|---|---:|---|']
    required=('stage_start_at_or_after_end','nonsequential_stages','negative_depth','nonpositive_diameter',
              'unexplained_main_depth_jump','primitive_beyond_stage_profile','machining_step_mismatch',
              'interface_outside_axial_cut','interface_without_mapped_cut','unbounded_cv_pilot_executed',
              'socket_envelope_executed','empty_profile','stage_start_gap','diameter_increase','invalid_primitive_interval',
              'source_backed_footprint_extension','preserved_legacy_profile','source_angle_depth_conflict',
              'pilot_diameter_exceeds_source_max')
    for name in required:
        lines.append(f'| `{name}` | {issues[name]} | {", ".join(f"`{x}`" for x in examples[name]) or "—"} |')
    lines += ['', '`source_backed_footprint_extension` is informational: offset child BH/DH/LP cuts may be '
              'deeper than the main cavity axis, and their source_ref identifies the actual child row.',
              '`preserved_legacy_profile` identifies read-only custom/legacy rows copied unchanged from the prior DB.',
              '`source_angle_depth_conflict` counts source rows where a nominal taper angle would pass the next '
              'declared STEP depth; the executable cone is bounded by the source depth so machining STEP endpoints '
              'remain aligned. These source inconsistencies remain visible for engineering review.',
              'Stages are conservative axial envelopes of the main-axis cylinders/cones; '
              'primitives include source-backed offset footprint cuts and are the CAD subtraction shapes. '
              'This scan checks conversion structure, '
              'not pressure or manufacturing certification.']
    args.output.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(changed=len(changed),by_table=dict(by_table),issues=dict(issues),checked_steps=steps),indent=2))


if __name__=='__main__':
    main()
