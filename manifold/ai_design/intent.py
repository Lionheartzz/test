"""Execute supported design intent and explicitly account for the rest."""
import copy
import math
import re
from .library_resolution import value
from ..engineering_db import normalized_thread_family

FACES = {'left', 'right', 'top', 'bottom', 'front', 'back'}


def mounting_from_intent(result, intent):
    """Keep explicit structured fields; recover only literal count/thread from older runs."""
    fields=dict(intent.get('mounting') or {})
    claim=next((c for c in result.get('claims',[]) if c['id']==intent.get('claim_id')),None)
    evidence={e['id']:e for e in result.get('evidence',[])}
    quote=' '.join(evidence[e]['quote'] for e in claim.get('evidence_ids',[]) if e in evidence and evidence[e].get('quote')) if claim else ''
    count=re.search(r'\b(\d{1,2})\s*[x×]\s*(?=M\s*\d|\d+\s*/\s*\d+)',quote,re.I)
    thread=re.search(r'\bM\s*\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?(?:-\d+[A-Z])?|\b\d+\s*/\s*\d+\s*-\s*\d+\s*(?:UNC|UNF)(?:-\d+[AB])?',quote,re.I)
    if quote:
        # The model's structured reading is not authority for words absent from
        # the exact source quote. Keep unresolved fields unresolved.
        fields['count']=int(count.group(1)) if count else None
        fields['thread_designation']=re.sub(r'\s+','',thread.group()).upper() if thread else None
        if fields.get('face') and not re.search(r'\b'+re.escape(fields['face'])+r'\b',quote,re.I):fields.pop('face')
        if fields.get('positions') and any(not all(re.search(r'(?<!\d)'+re.escape(f'{coord:g}')+r'(?!\d)',quote) for coord in pair)
                                           for pair in fields['positions']):fields.pop('positions')
        if fields.get('through') is not None and not re.search(r'\b(through|blind)\b',quote,re.I):fields.pop('through')
        for key in ('drill_depth','thread_depth'):
            if fields.get(key) is not None and not re.search(r'(?<!\d)'+re.escape(f'{fields[key]:g}')+r'(?!\d)',quote):fields.pop(key)
    if fields.get('thread_designation'):
        fields['thread_family']=normalized_thread_family({'display_name':fields['thread_designation']})
    return fields


def reconcile_mounting(requirements, mounting):
    blocked=[]
    sole=requirements[0]['intent_id'] if len(requirements)==1 else None
    known={row['intent_id'] for row in requirements}
    for entry in mounting:
        chosen=entry['hole'].requirement_id
        if requirements and (chosen and chosen not in known or not chosen and not sole):
            blocked.append('Every resolved mounting hole must be assigned to an existing mounting requirement.')
    for row in requirements:
        req=row['mounting']
        holes=[entry for entry in mounting if (entry['hole'].requirement_id or sole)==row['intent_id']]
        expected=req.get('count')
        if not req.get('thread_designation') or expected is None:
            row.update(status='review_required',message='Mounting count and exact thread identity must be source-backed or explicitly corrected.')
        elif not holes:
            row.update(status='review_required',message='No explicitly positioned mounting holes resolve this requirement.')
        else:
            wrong=[]
            designation=re.sub(r'[^A-Z0-9]','',req['thread_designation'].upper())
            for entry in holes:
                hole,thread=entry['hole'],entry['thread']
                actual=re.sub(r'[^A-Z0-9]','',thread['display_name'].upper())
                if not actual.startswith(designation):wrong.append('thread')
                if req.get('thread_family') and normalized_thread_family(thread)!=req['thread_family']:wrong.append('family')
                if req.get('face') and hole.face!=req['face']:wrong.append('face')
                if req.get('through') is not None and hole.through!=req['through']:wrong.append('through/blind')
                if req.get('drill_depth') is not None and abs(hole.depth-req['drill_depth'])>1e-6:wrong.append('drill depth')
                if req.get('thread_depth') is not None and abs(hole.thread_depth-req['thread_depth'])>1e-6:wrong.append('thread depth')
            positions=req.get('positions')
            if positions is not None and sorted((round(h['hole'].u,6),round(h['hole'].v,6)) for h in holes)!=sorted((round(u,6),round(v,6)) for u,v in positions):wrong.append('positions')
            if wrong or len(holes)>expected:
                row.update(status='conflict',message='Mounting requirement conflicts with resolved '+', '.join(sorted(set(wrong or ['count'])))+'.')
            elif len(holes)<expected:
                row.update(status='partially_applied',message=f'{len(holes)} of {expected} required mounting holes resolved.')
            else:
                row.update(status='applied',message='Exact thread, count and all declared placement/depth constraints match resolved holes.')
        if row['status']!='applied':blocked.append(f"{row['intent_id']}: {row['message']}")
    return blocked


def effective_result(run):
    return copy.deepcopy(run['result'])


def interpret(result, options):
    settings = dict(maximum=[2000.0]*3, minimum=[1.0]*3, port_faces={}, component_faces={},
                    hard_port_faces={}, hard_component_faces={}, forbidden=[], material='Unspecified - review required',
                    priority='fewer_plugs', flows={}, pressures={}, mounting_requirements=[], dispositions=[], conflicts=[])
    port_labels = {p['id']: str(value(result, p['id'], 'label') or p['id']) for p in result['ports'] if p['component_id'] is None}
    component_labels = {c['id']: str(value(result, c['id'], 'label') or c['id']) for c in result['components']}
    seen = {}

    def assign(table, keys, val, intent, row):
        for key in keys:
            identity = (table, key)
            if identity in seen and seen[identity] != val:
                row.update(status='conflict', message='Conflicting requirements for ' + key)
                settings['conflicts'].append(row['message'])
            else:
                settings[table][key] = val
                seen[identity] = val

    def targets(labels, selected):
        if any(target not in labels and target not in labels.values() for target in selected):
            return []
        return [key for key, label in labels.items() if label in selected or key in selected]

    # Only terminal operating values have an unambiguous net scope. Component
    # ratings, settings and inferred values must not become drilling design loads.
    port_ids = {p['id'] for p in result['ports']}
    for port in result['ports']:
        for predicate,number in port.get('facts',{}).items():
            category = {'flow': 'flow', 'flow_lpm': 'flow', 'working_pressure': 'pressure'}.get(predicate)
            if not category or port.get('fact_kinds',{}).get(predicate) not in ('schematic','user_requirement'):
                continue
            unit=(port.get('fact_units',{}).get(predicate) or '').lower()
            scales = {'bar': 1, 'psi': 0.0689475729} if category == 'pressure' else {'l/min': 1, 'lpm': 1, 'gpm': 3.785411784}
            if isinstance(number,bool) or not isinstance(number,(int,float)) or unit not in scales:continue
            number*=scales[unit]
            if not 0<number<=(2000 if category=='pressure' else 10000):continue
            settings['pressures' if category=='pressure' else 'flows'][(port['id'],)]=number
            settings['dispositions'].append(dict(intent_id='OPERATING_'+port['id']+'_'+predicate,category=category,property=predicate,
                value=port['facts'][predicate],unit=unit,targets=[port['id']],strength='requirement',status='partially_applied',
                message='Explicit terminal operating value used for net metadata and flow screening.'))

    for intent in result['design_intent']:
        val, unit = intent.get('value'), intent.get('unit', '')
        category, prop, op = intent['category'], intent['property'], intent['operator']
        row = dict(intent_id=intent['id'], category=category, property=prop, value=val, unit=unit,
                   targets=intent['target_labels'], strength=intent['strength'], status='unsupported',
                   message='This requirement is retained for engineer review; this generator cannot execute it.')
        settings['dispositions'].append(row)
        if category == 'mounting':
            row['mounting']=mounting_from_intent(result,intent)
            settings['mounting_requirements'].append(row)
            row.update(status='review_required',message='Thread identity and every hole position must be resolved explicitly before generation; no coordinates are inferred.')
            continue
        if val is None:
            row.update(status='review_required', message='Requirement value is unknown or rejected; resolve it before relying on the draft.')
            continue
        if category == 'envelope' and prop in ('length', 'width', 'height') and op in ('equal', 'minimum', 'maximum'):
            if isinstance(val, bool) or not isinstance(val, (int, float)) or unit.lower() not in ('mm', 'in', 'inch'):
                continue
            number = val * (25.4 if unit.lower() in ('in', 'inch') else 1)
            if not 1 <= number <= 2000:
                row.update(status='conflict', message='Requested dimension is outside the supported 1–2000 mm range.')
                settings['conflicts'].append(row['message'])
                continue
            i = ('length', 'width', 'height').index(prop)
            if op in ('equal', 'maximum'):
                settings['maximum'][i] = min(settings['maximum'][i], number)
            if op in ('equal', 'minimum'):
                settings['minimum'][i] = max(settings['minimum'][i], number)
            row.update(status='applied', message='Enforced in generated block size and the existing deterministic validator.')
        elif category == 'port_face' and prop == 'preferred_face' and val in FACES:
            keys = targets(port_labels, intent['target_labels'])
            if not keys:
                row.update(status='review_required', message='No external port matches these labels; no face was silently reassigned.')
                continue
            assign('port_faces', keys, val, intent, row)
            if intent['strength'] == 'requirement':
                assign('hard_port_faces', keys, val, intent, row)
            if row['status'] != 'conflict':
                row.update(status='applied', message='External-port face controls placement; all generated candidates keep this face.')
        elif category == 'serviceability' and prop == 'component_face' and val in FACES:
            keys = targets(component_labels, intent['target_labels'])
            if not keys:
                row.update(status='review_required', message='No component matches the requested face target.')
                continue
            assign('component_faces', keys, val, intent, row)
            if intent['strength'] == 'requirement':
                assign('hard_component_faces', keys, val, intent, row)
            if row['status'] != 'conflict':
                row.update(status='partially_applied', message='Mounting face applied; actual adjustment/coil orientation requires sourced body data.')
        elif category == 'routing' and prop == 'cross_drilling_face' and op == 'avoid' and val in FACES:
            settings['forbidden'].append(val)
            row.update(status='applied', message='Excluded from automatic drilling entries and checked on future manual/rerouted drillings.')
        elif category == 'priority' and prop == 'design_priority' and val in ('compact', 'simple_machining', 'fewer_plugs', 'short_drills'):
            settings['priority'] = val
            row.update(status='applied', message='Used in initial layout size and existing route cost ranking; finite search, not a global optimum.')
        elif category == 'material' and isinstance(val, str):
            settings['material'] = val[:120]
            row.update(status='partially_applied', message='Material recorded on block; pressure/material suitability is not certified by this geometry engine.')
        elif category in ('pressure', 'flow') and isinstance(val, (int, float)) and not isinstance(val, bool):
            scale = {'bar': 1, 'psi': 0.0689475729} if category == 'pressure' else {'l/min': 1, 'lpm': 1, 'gpm': 3.785411784}
            if unit.lower() not in scale or val <= 0:
                continue
            converted = val * scale[unit.lower()]
            if converted > (2000 if category == 'pressure' else 10000):
                continue
            settings['pressures' if category == 'pressure' else 'flows'][tuple(intent['target_labels'])] = converted
            row.update(status='partially_applied', message='Pressure metadata retained; ratings are not inferred.' if category == 'pressure'
                       else 'Flow participates in drilling sizing and exact opening-area/velocity screening; pressure loss and flow distribution remain unverified.')
        elif category == 'component_selection':
            row.update(status='review_required', message='Existing model/cavity evidence and your library choices control selection; manufacturer preference cannot invent a compatible replacement.')
        elif category == 'separation' and op == 'separate':
            # Final resolved topology is checked in the compiler, including engineer overrides.
            row.update(status='pending', message='Will compare requested labels against final net membership.')
        elif category == 'source_instruction':
            row.update(status='review_required', message='Sent to the model during interpretation. Its semantic compliance still needs source review.')
    if any(a > b for a, b in zip(settings['minimum'], settings['maximum'])):
        settings['conflicts'].append('Minimum/exact block dimensions conflict with maximum dimensions.')
    settings['forbidden'] = sorted(set(settings['forbidden']))
    if options.port_faces or options.component_faces:
        if not options.placement_decision.strip():
            raise ValueError('Changing proposed mounting faces needs an engineer decision')
        for table, choices in [('port_faces', options.port_faces), ('component_faces', options.component_faces)]:
            known = port_labels if table == 'port_faces' else component_labels
            if not set(choices) <= set(known):
                raise ValueError('Face choice refers to a missing analysis entity')
            for key, val in choices.items():
                if key in settings['hard_' + table] and settings['hard_' + table][key] != val:
                    settings['conflicts'].append('Engineer face choice conflicts with a required face; correct the requirement claim first.')
                else:
                    settings[table][key] = val
    return settings


def parameter_for(result, table, net):
    labels = {net['id'], str(value(result, net['id'], 'label') or '')}
    labels.update(net['members'])
    labels.update(str(value(result, member, 'label') or '') for member in net['members'])
    matches = [number for targets, number in table.items() if not targets or labels.intersection(targets)]
    return max(matches) if matches else None
