"""Compile reviewed hydraulic understanding into the existing editable Design.

No provider writes cavity geometry. Bounded placement/routing trials keep every
failed exact report; a generation never overwrites a saved user project.
"""
import copy
import hashlib
import json
import math
import re
import time
import uuid
from .. import store
from ..schema import Design, Feature, CavityDefinition
from ..kinematics import FACE_AXES, dimensions, clamp_placement, pose,definition_planar_radius
from ..routing import terminal_points
from ..engineering import CalculationError
from . import service, library_resolution as library
from .models import TaskInput
from .intent import effective_result, interpret, parameter_for
from .generation_models import GenerationOptions
from ..limits import PROJECT_FEATURES, PROJECT_NETS


def context(key, run_id, expected):
    record = service.read(key)
    service.check(record, expected)
    run = service.load_run(key, run_id)
    if run['status'] != 'completed':
        raise ValueError('Select a completed analysis before generation')
    if run['input_revision'] != service.digest(record['inputs']):
        raise ValueError('Analysis is stale. Analyze the current inputs before generation.')
    inputs = TaskInput.model_validate(record['inputs'])
    return record, run, inputs, effective_result(run,record.get('port_corrections')),


def topology(result, options):
    result = copy.deepcopy(result)
    ports = {p['id']: p for p in result['ports']}
    if not set(options.net_overrides) <= set(ports):
        raise ValueError('Net override refers to a missing port')
    by_id = {n['id']: n for n in result['nets']}
    for port_id, target in options.net_overrides.items():
        if ports[port_id].get('disposition') in ('blocked', 'terminated'):
            raise ValueError('Blocked or terminated ports cannot be assigned to a hydraulic net')
        if not target.strip() or len(target) > 120:
            raise ValueError('Enter a nonempty net ID or label of at most 120 characters')
        if target not in by_id:
            matches = [n for n in result['nets'] if library.value(result, n['id'], 'label') == target]
            if len(matches) > 1:
                raise ValueError('Net label is ambiguous; choose its ID')
            if matches:
                target = matches[0]['id']
            else:
                name = target
                target = 'ENGINEER_' + hashlib.sha256(name.encode()).hexdigest()[:12]
                if target not in by_id:
                    by_id[target] = dict(id=target, members=[], label=name)
                    result['nets'].append(by_id[target])
        for net in result['nets']:
            net['members'] = [p for p in net['members'] if p != port_id]
        by_id[target]['members'].append(port_id)
    result['nets'] = [n for n in result['nets'] if n['members']]
    return result


def topology_signature(inputs,result):
    return service.digest(dict(documents=[(d.id,d.asset.sha256) for d in inputs.documents],
        components=[dict(id=c['id'],ports=c['port_ids']) for c in result['components']],
        ports=[{key:p.get(key) for key in ('id','component_id','label','disposition')} for p in result['ports']],
        nets=[{key:n.get(key) for key in ('id','label','status','members')} for n in result['nets']]))


def prepare(inputs, result, options):
    result = topology(result, options)
    settings = interpret(result, options)
    from ..engineering_db import materials
    def material_names(row):
        identity=(row.get('engineering_facts_summary') or {}).get('identity') or {}
        return [row['display_name'], ' '.join([identity.get('grade',''),identity.get('state','')]),
                identity.get('grade','')+'-'+identity.get('state','')]
    material_matches=[row for row in materials() if any(library.norm(name)==library.norm(settings['material']) for name in material_names(row) if name)]
    settings['material_id']=material_matches[0]['id'] if len(material_matches)==1 else None
    settings['engineering_facts']=material_matches[0].get('engineering_facts_summary') if len(material_matches)==1 else None
    if len(material_matches)==1:settings['material']=material_matches[0]['display_name']
    # Preserve the existing admission messages/policy, but identify their UI owner.
    blocked = []
    decisions = []
    def block(message, section='requirements', target_id=None, field=None):
        blocked.append(message)
        decisions.append(dict(message=message,section=section,target_id=target_id,field=field))
    for message in settings['conflicts']:block(message)
    signature=topology_signature(inputs,result)
    # Advancing to generation accepts the displayed assignments. Actual missing
    # ports, conflicting nets and interface mappings remain admission blockers.
    authored_count=len(result['components'])+sum(p['component_id'] is None and p.get('disposition') not in ('blocked','terminated') for p in result['ports'])+len(options.threaded_mounting_holes)
    if authored_count>PROJECT_FEATURES:
        block(f'This circuit needs {authored_count} authored features; the editable project supports {PROJECT_FEATURES} total features including generated drillings. Split the circuit into projects.', 'analysis')
    if len(result['nets'])>PROJECT_NETS:
        block(f'This circuit has {len(result["nets"])} nets; the editable project supports {PROJECT_NETS}. Split the circuit into projects; the complete analysis is retained.', 'analysis')
    if not result['ports'] or not result['nets'] and any(p.get('disposition')=='connected' for p in result['ports']):
        block('No usable hydraulic topology was recognized. Review the source and analyze again.', 'analysis')
    port_net = {p: n['id'] for n in result['nets'] for p in n['members']}
    for port in result['ports']:
        if port.get('disposition','unknown')=='unknown' and port['id'] in port_net:port['disposition']='connected'
    for port in result['ports']:
        if port.get('disposition','unknown') in ('connected','unknown') and port['id'] not in port_net:
            block(library.display_label(result,port) + ': choose a hydraulic net for the unknown connection.', 'topology', port['id'], 'net')
    components = []
    known_components = {c['id'] for c in result['components']}
    known_external = {p['id'] for p in result['ports'] if p['component_id'] is None}
    if not set(options.bindings) <= known_components or not set(options.port_definitions) <= known_external:
        raise ValueError('Library choice refers to a missing component or external port')
    if not set(options.provisional_ports) <= known_external:
        raise ValueError('Provisional-port choice refers to a missing external port')
    for component in result['components']:
        key = component['id']
        label=library.display_label(result,component)
        identity=library.component_identity(result,component)
        choices = library.candidates(inputs, result, component,identity)
        resolution = library.resolution_status(inputs, result, component, choices,identity)
        selected = options.bindings.get(key)
        automatic = False
        mapping_blocked = False
        if selected:
            definition = library.load(inputs, selected.definition_key, selected.definition_sha256)
            if identity.get('interface_requirements') and definition.id not in identity.get('interface_ids',[]):
                block(f'{label}: selected interface conflicts with the declared source interface; correct or clarify the source requirement.', 'component', key, 'interface')
            mapping = selected.zone_ports
            decision = selected.decision.strip()
            resolution = {**resolution, 'code': 'manual_selection',
                          'message': 'An existing machining interface has been selected explicitly.',
                          'action': 'Complete the hydraulic interface mapping.'}
        else:
            chosen, _ = library.automatic_choice(inputs, choices,identity)
            if chosen:
                row = chosen
                definition = library.load(inputs, row['key'], row['sha256'])
                contract=library.interface_port_contract(result,component,chosen['zones'])
                mapping=contract['mapping']
                automatic=contract['status']=='matched'
                decision=row['reason'] + '; exact hydraulic interface labels matched by PMC. Engineer review remains required.' if automatic else ''
                if not automatic:
                    block(f'{label}: {resolution["message"]} {resolution["action"]}', 'component', key, 'mapping')
                    mapping_blocked=True
            else:
                definition, mapping, decision = None, {}, ''
                block(f'{label}: {resolution["message"]} {resolution["action"]}', 'component', key,
                      'mapping' if resolution['code']=='window_mapping_required' else 'interface')
        if definition:
            if definition.kind != 'cavity':
                raise ValueError('An external-port definition cannot be used as a cartridge cavity')
            if not definition.active or not definition.usable:
                block(f'{label}: selected cavity geometry is unavailable: {definition.unusable_reason}', 'component', key, 'interface')
            if not mapping_blocked and (set(mapping) != {z.id for z in definition.zones} or set(mapping.values()) != set(component['port_ids']) or len(set(mapping.values())) != len(mapping)):
                block(f'{label}: map every cavity window to exactly one distinct schematic component port.', 'component', key, 'mapping')
        cartridge_id=next((row.get('cartridge_id') for row in choices if definition and row['key']=='db:'+definition.id),None)
        components.append(dict(id=key, label=label,
                               model=identity['recognized_model'] or '',
                               recognized_interface=' / '.join(str(value) for value in identity.get('interface_requirements',[])),
                               recognized_facts=dict(component.get('facts',{})),
                               observed_identity_annotations=list(component.get('observed_identity_annotations',[])),
                               cartridge_id=cartridge_id,
                               function=library.value(result,key,'functional_type') or '',
                               choices=choices, definition=definition, mapping=dict(mapping or {}),
                               port_contract=library.interface_port_contract(result,component,[z.model_dump() for z in definition.zones]) if definition else None,
                               automatic=automatic, decision=decision, resolution=resolution))
    external = [];spec_resolutions={};port_groups={};port_blocks={}
    for port in result['ports']:
        if port['component_id'] is not None or port.get('disposition') in ('blocked','terminated'):continue
        selected=options.port_definitions.get(port['id'])
        specification=library.value(result,port['id'],'port_specification') or ''
        normalized=library.normalized_port_specification(specification)
        group_key=normalized or ('unspecified',port['id'])
        if group_key not in spec_resolutions:spec_resolutions[group_key]=library.resolve_port_specification(inputs,specification)
        resolution=spec_resolutions[group_key]
        group=port_groups.setdefault(group_key,dict(id='PORTSPEC_'+service.digest(group_key)[:12],**resolution,port_ids=[],labels=[],unresolved_ids=[]))
        label=library.display_label(result,port)
        group['port_ids'].append(port['id']);group['labels'].append(label)
        automatic=False;definition=library.load(inputs,selected.definition_key,selected.definition_sha256) if selected else None
        if not definition and resolution['canonical']:
            chosen=resolution['canonical'];definition=library.load(inputs,chosen['key'],chosen['sha256']);automatic=True
        if definition and (definition.kind!='external-port' or len(definition.zones)!=1):
            raise ValueError('External ports require a source external-port definition with one hydraulic interface')
        if definition and (not definition.active or not definition.usable):
            block(f'{label}: selected port machining definition is unavailable: {definition.unusable_reason}', 'external_port', port['id'], 'interface')
        requested_standard,requested_size=library.port_standard(specification)
        if definition and requested_standard and (not requested_size or definition.id not in {
                row['key'][3:] for row in library.exact_port_candidates(inputs,specification)}):
            block(f'{label}: selected port conflicts with explicit source standard “{specification}”. Correct the source requirement before selecting a different standard.', 'external_port', port['id'], 'interface')
        provisional=port['id'] in options.provisional_ports
        thread=resolution['thread_resolution']['definition']
        if provisional and requested_standard:
            block(f'{label}: explicit thread/standard {specification} cannot be replaced by a straight bore.', 'external_port', port['id'], 'interface')
        if provisional and not options.provisional_ports[port['id']].strip():
            block(f'{label}: explicit one-off straight-bore use requires an engineering decision.', 'external_port', port['id'], 'decision')
        if not definition and not thread and not provisional:
            group['unresolved_ids'].append(port['id']);port_blocks.setdefault((group_key,'','missing'),[]).append(label)
        external.append(dict(id=port['id'],label=label,specification=specification,definition=definition,
            thread=thread,state='full_definition' if definition else 'thread_defined' if thread else 'custom_bore' if provisional else 'unresolved',
            decision=selected.decision if selected else options.provisional_ports.get(port['id'],''),
            automatic=automatic or bool(thread and not selected),provisional=provisional,standard=requested_standard,resolution=resolution,group_id=group['id']))
    for (key,choice,reason),labels in port_blocks.items():
        resolution=spec_resolutions[key];label=resolution['specification'] or ', '.join(labels)
        if resolution['code']=='thread_identity_ambiguous':detail='Thread identity has conflicting source definitions; resolve the thread requirement.'
        elif resolution['code']=='thread_machining_unavailable':detail='Thread identity was found, but SQLite has no usable source tap-drill data for an executable draft hole.'
        elif resolution['code']=='thread_definition_missing':detail='No matching source-backed thread definition is available.'
        elif resolution['code']=='port_specification_ambiguous':detail='Multiple non-equivalent complete machining definitions exist. Choose one.'
        elif resolution['normalized']:detail='No usable complete source-backed external-port definition is available.'
        else:detail='No complete external-port definition was selected. Select an existing definition or explicitly approve a one-off Custom Straight Bore.'
        block(f'{label} · applies to {", ".join(labels)}: {detail}', 'port_group', port_groups[key]['id'], 'interface')
    from ..engineering_db import thread_definition
    mounting=[]
    if options.threaded_mounting_holes and not options.mounting_decision.strip():
        block('Threaded mounting-hole placement requires an explicit engineering decision.', 'mounting', field='decision')
    for index,hole in enumerate(options.threaded_mounting_holes,1):
        thread=thread_definition(hole.thread_definition_id)
        if not thread['active'] or not thread['usable']:
            block(f'Mounting hole {index}: thread definition is unavailable: {hole.thread_definition_id}', 'mounting')
        if hole.thread_depth>hole.depth:
            block(f'Mounting hole {index}: thread depth exceeds tap-drill depth.', 'mounting')
        mounting.append(dict(hole=hole,thread=thread))
    from .intent import reconcile_mounting
    for message in reconcile_mounting(settings['mounting_requirements'],mounting):block(message,'mounting')
    for row in settings['dispositions']:
        if row['category'] == 'separation' and row['status'] == 'pending':
            sets = []
            for label in row['targets']:
                matches = [p['id'] for p in result['ports'] if library.value(result,p['id'],'label') == label]
                sets.append({port_net[p] for p in matches if p in port_net})
            if len(sets) < 2 or any(not s for s in sets):
                row.update(status='review_required', message='Separation target cannot be resolved to hydraulic terminals.')
            elif any(a & b for i,a in enumerate(sets) for b in sets[i+1:]):
                row.update(status='conflict', message='Requested separation conflicts with the interpreted/confirmed topology. Correct the net assignment first.')
                block(row['message'],'topology',field='decision')
            else:
                row.update(status='applied', message='Targets remain distinct nets; cross-net physical intersections fail deterministic validation.')
    return dict(inputs=inputs, result=result, settings=settings, blocked=blocked, decisions=decisions, components=components,
                topology_review=dict(signature=signature,required=False,acceptance='generate_action'),
                external=external,port_groups=port_groups,mounting=mounting, port_net=port_net, options=options)


def preflight(key, request):
    record, run, inputs, result = context(key, request.run_id, request.expected_revision)
    plan = prepare(inputs, result, request.options)
    def entry(row):
        return {**{k:v for k,v in row.items() if k != 'definition'},
                'definition': library.summary('db:'+row['definition'].id,row['definition']) if row['definition'] else None}
    corrections=record.get('port_corrections') or {}
    if corrections.get('run_id')!=run['id'] or corrections.get('input_revision')!=run['input_revision']:corrections={}
    excluded=set(corrections.get('excluded_port_ids',[]))
    owners={c['id']:c['label'] for c in run['result']['components']}
    excluded_ports=[dict(id=p['id'],component_id=p['component_id'],label=p['label'],owner_label=owners[p['component_id']])
                    for p in run['result']['ports'] if p['id'] in excluded]
    return dict(ready=not plan['blocked'], blocked=plan['blocked'], decisions=plan['decisions'], components=[entry(c) for c in plan['components']],
                topology_review=plan['topology_review'],port_corrections=corrections,excluded_ports=excluded_ports,
                external_ports=[entry(p) for p in plan['external']], external_port_groups=list(plan['port_groups'].values()), dispositions=plan['settings']['dispositions'],
                mounting_requirements=plan['settings']['mounting_requirements'],mounting_holes=[dict(hole=row['hole'].model_dump(),thread=row['thread']) for row in plan['mounting']],
                ports=[dict(id=p['id'], component_id=p['component_id'], label=library.display_label(result,p),
                            net=plan['port_net'].get(p['id']),disposition=p.get('disposition','unknown')) for p in result['ports']],
                nets=[dict(id=n['id'],label=library.display_label(result,n),status=n.get('status')) for n in result['nets']],
                material_engineering_facts=plan['settings']['engineering_facts'])


def packing(group,face,wall,gap,maximum,*,rectangular=False):
    from ..layout import packing_dimensions
    return packing_dimensions(group,face,wall,gap,maximum,rectangular=rectangular)


def fid(generation_id, key, prefix):
    return prefix + '_' + hashlib.sha256((generation_id + ':' + key).encode()).hexdigest()[:20]


def candidate(plan, generation_id, variant):
    options, settings, inputs, result = (plan[x] for x in ('options','settings','inputs','result'))
    wall = options.minimum_wall or (inputs.project_engineering.rules.minimum_wall if inputs.project_engineering else None) or 0
    aliases = {}
    for row in [*plan['components'], *plan['external']]:
        definition = row['definition']
        if definition:
            aliases[row['id']] = definition.id
    defs = [row['definition'] for row in [*plan['components'],*plan['external']] if row['definition']]
    defs = list({d.id:d for d in defs}.values())
    by_definition = {d.id:d for d in defs}
    groups={}
    for component in plan['components']:
        groups.setdefault(settings['component_faces'].get(component['id'],options.preferred_component_face or 'top'),[]).append(component)
    maximum=list(settings['maximum']);minimum=list(settings['minimum'])
    if inputs.project_engineering:
        if inputs.project_engineering.constraints.envelope_max:maximum=[min(a,b) for a,b in zip(maximum,inputs.project_engineering.constraints.envelope_max)]
        if inputs.project_engineering.constraints.envelope_min:minimum=[max(a,b) for a,b in zip(minimum,inputs.project_engineering.constraints.envelope_min)]
    layouts={face:packing(group,face,wall,6 if settings['priority']=='compact' else 16,maximum,rectangular=variant%2==1) for face,group in groups.items()}
    base=[80,80,70];required=[1,1,1]
    for face,(_,_,width,height,_) in layouts.items():
        u,v,_,_=FACE_AXES[face];base[u]=max(base[u],width);base[v]=max(base[v],height)
        required[u]=max(required[u],width);required[v]=max(required[v],height)
    # Non-top mounting consumes depth along its own inward axis.
    for c in plan['components']:
        face = settings['component_faces'].get(c['id'],options.preferred_component_face or 'top')
        axis = FACE_AXES[face][2]
        depth=max([s.end for s in c['definition'].stages]+[p.end for p in c['definition'].cutting_primitives])
        base[axis]=max(base[axis],depth+wall*2+12);required[axis]=max(required[axis],depth+wall)
    for i,p in enumerate(plan['external']):
        face=settings['port_faces'].get(p['id'],options.preferred_port_face or ('left','right','front','back')[(i+variant//2)%4])
        axis=FACE_AXES[face][2]
        depth=max([s.end for s in p['definition'].stages]+[cut.end for cut in p['definition'].cutting_primitives]) if p['definition'] else options.port_depth
        required[axis]=max(required[axis],depth+wall)
        base[axis]=max(base[axis],depth+wall*2+12)
    scale = (1, 1.18, 1.35, 1.5, 1.7, 1.9)[variant]
    if any(size>hi for size,hi in zip(required,maximum)):
        raise ValueError('Source cavity machining depth/footprints exceed the requested block envelope; enlarge the block or revise the mounting faces.')
    sizes = [max(lo,min(hi,math.ceil(size*scale/5)*5)) for size,lo,hi in zip(base,minimum,maximum)]
    block = dict(zip(('length','width','height'),sizes))
    block['material'] = settings['material']
    if settings.get('material_id'):block['material_id']=settings['material_id']
    elif inputs.project_engineering and settings['material']=='Unspecified - review required':
        block['material']=inputs.project_engineering.block.material
        if inputs.project_engineering.block.material_id:block['material_id']=inputs.project_engineering.block.material_id
    assets=[d.asset.model_dump() for d in inputs.documents]
    raw = dict(schema_version=3,name=(inputs.title[:100] + ' - AI Draft'), project_context=inputs.project_context, block=block,
               features=[], nets=[],schematic_intent=dict(assets=assets,components=[]), rules=dict(minimum_wall=options.minimum_wall),
               constraints=dict(envelope_max=settings['maximum'],envelope_min=settings['minimum'],
                   forbidden_drilling_faces=settings['forbidden'],priority=settings['priority'],
                   notes='AI-generated draft from the current normalized schematic intent.'))
    design = Design.model_validate(raw)
    if inputs.project_engineering:
        design.project_defaults=inputs.project_engineering.project_defaults.model_copy(deep=True)
        design.rules=inputs.project_engineering.rules.model_copy(deep=True)
        design.constraints.preferred_wall_margin=inputs.project_engineering.constraints.preferred_wall_margin
        design.constraints.priority=inputs.project_engineering.constraints.priority
        if inputs.project_engineering.constraints.envelope_max:design.constraints.envelope_max=tuple(min(a,b) for a,b in zip(settings['maximum'],inputs.project_engineering.constraints.envelope_max))
        if inputs.project_engineering.constraints.envelope_min:design.constraints.envelope_min=tuple(max(a,b) for a,b in zip(settings['minimum'],inputs.project_engineering.constraints.envelope_min))
    if settings['material']!='Unspecified - review required' and not settings.get('material_id'):
        from ..schema import EngineeringReview
        design.review_items.append(EngineeringReview(id='AI_MATERIAL_REVIEW',kind='component',subject='block',
            description=f'Explicit material requirement “{settings["material"]}” has no unique source-backed SQLite material match. Material properties and stock suitability remain unresolved.'))
    feature_map, terminal_map, net_ids = {}, {}, {}
    used_nets = set()
    for i,net in enumerate(result['nets'],1):
        label = str(library.value(result,net['id'],'label') or net['id'])
        name = label if re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}',label) and label not in used_nets else 'NET_'+str(i)
        while name in used_nets:
            name += '_'
        net_ids[net['id']] = name
        used_nets.add(name)
    for face,group in groups.items():
        u_axis,v_axis,_,_=FACE_AXES[face]
        local_cols,local_rows,_,_,pitch=layouts[face]
        pitch_u=max(pitch,(sizes[u_axis]-2*wall)/local_cols)
        pitch_v=max(pitch,(sizes[v_axis]-2*wall)/local_rows)
        origin_u=(sizes[u_axis]-(local_cols-1)*pitch_u)/2
        origin_v=(sizes[v_axis]-(local_rows-1)*pitch_v)/2
        for i,c in enumerate(group):
            key=c['id'];definition=by_definition[aliases[key]]
            f=Feature(id=fid(generation_id,key,'CV'),kind='cavity',face=face,
                      u=origin_u+(i%local_cols)*pitch_u,
                      v=origin_v+(i//local_cols)*pitch_v,cavity_id=definition.id,
                      interface_nets={zone:net_ids[plan['port_net'][port]] for zone,port in c['mapping'].items() if port in plan['port_net']},
                      cartridge_id=c.get('cartridge_id'),schematic_id=key)
            design.features.append(f);feature_map[key]=f.id
            for zone,port in c['mapping'].items():terminal_map[port]=f.id+':'+zone
            from ..schema import SchematicComponent
            port_dispositions={zone:next(p.get('disposition','unknown') for p in result['ports'] if p['id']==port) for zone,port in c['mapping'].items()}
            design.schematic_intent.components.append(SchematicComponent(id=key[:39],label=str(c['label'])[:160],function=str(c['function'])[:200],
                cartridge_id=c.get('cartridge_id'),cavity_id=definition.id,placement_id=f.id,
                expected_interfaces=list(c['mapping']),interface_nets=f.circuits,interface_dispositions=port_dispositions))
            if key in settings['hard_component_faces']:design.constraints.required_feature_faces[f.id]=face
    points=terminal_points(design)
    default_faces=('left','right','front','back')
    for i,p in enumerate(plan['external']):
        key=p['id'];source_net=plan['port_net'][key]
        net=next(n for n in result['nets'] if n['id']==source_net)
        targets=[terminal_map[m] for m in net['members'] if m in terminal_map]
        face=settings['port_faces'].get(key,options.preferred_port_face or default_faces[(i+variant//2)%4])
        u_axis,v_axis,axis,sign=FACE_AXES[face]
        target=points[targets[0]] if targets else tuple(s/2 for s in sizes)
        u,v=target[u_axis],target[v_axis]
        if targets:
            owner=next(f for f in design.features if f.id==targets[0].split(':')[0])
            if FACE_AXES[owner.face][2]==axis:
                # Approach parallel to a cavity outside its protected machining body,
                # then let the router enter the selected side window transversely.
                radius=by_definition[owner.definition].clearance_diameter/2
                shift=radius+wall+options.port_diameter/2+variant*3
                if i%2:u-=shift
                else:u+=shift
        if not targets:
            u=sizes[u_axis]*(i+1)/(len(plan['external'])+1)
        kwargs=dict(id=fid(generation_id,key,'PORT'),kind='port',face=face,u=max(0,u),v=max(0,v),
                    circuit=net_ids[source_net],schematic_id=str(p['label'])[:80])
        if p['definition']:
            definition=by_definition[aliases[key]]
            kwargs.update(port_definition_id=definition.id,diameter=min(s.diameter for s in definition.stages),
                          depth=definition.zones[0].end,clearance_diameter=definition.clearance_diameter,
                          clearance_height=definition.clearance_height,tip_angle=180,
                          port_type=definition.label,size=definition.thread_note[:80])
        elif p.get('thread'):
            # Only the SQLite tap-drill diameter is source-backed here. Entry
            # depth/point are editable draft assumptions; thread depth and the
            # sealing/machining recipe remain unresolved.
            thread=p['thread']
            kwargs.update(thread_definition_id=thread['id'],diameter=thread['tap_diameter_mm'],
                          depth=options.port_depth,clearance_diameter=thread['tap_diameter_mm'],clearance_height=0,
                          port_type='Thread-defined port - machining / sealing unresolved',
                          size=p['resolution']['thread_resolution']['label'][:80])
        else:
            kwargs.update(diameter=options.port_diameter,depth=options.port_depth,tip_angle=180,
                          clearance_diameter=max(20,options.port_diameter+6),clearance_height=20,
                          port_type='Provisional straight bore - no thread specified',size=f'Draft bore {options.port_diameter:g} mm')
        f=Feature(**kwargs)
        radius=definition_planar_radius(p['definition']) if p['definition'] else f.clearance_diameter/2
        margin=radius+wall
        occupied=[(previous.u,previous.v,definition_planar_radius(by_definition[previous.definition]) if previous.definition else previous.clearance_diameter/2)
                  for previous in design.features if previous.face==face]
        preferred=(max(margin,min(sizes[u_axis]-margin,f.u)),max(margin,min(sizes[v_axis]-margin,f.v)))
        pitch=2*radius+2*wall+2
        probes=[preferred]+[(x,y) for x in [margin+j*pitch for j in range(max(0,math.floor((sizes[u_axis]-2*margin)/pitch)+1))]
                           for y in [margin+j*pitch for j in range(max(0,math.floor((sizes[v_axis]-2*margin)/pitch)+1))]]
        legal=[point for point in probes if margin<=point[0]<=sizes[u_axis]-margin and margin<=point[1]<=sizes[v_axis]-margin
               and all(math.hypot(point[0]-x,point[1]-y)>=radius+r+wall for x,y,r in occupied)]
        if not legal:raise ValueError(f'{p["label"]}: no non-overlapping source port/installed envelope fits the requested {face} face. Enlarge the block or change the port face.')
        f.u,f.v=min(legal,key=lambda point:(math.dist(point,preferred),point))
        design.features.append(f);terminal_map[key]=f.id;feature_map[key]=f.id
        if f.thread_only:
            from ..schema import EngineeringReview
            design.review_items.append(EngineeringReview(id=fid(generation_id,key,'THREAD_REVIEW'),kind='dimension',subject=f.id,
                description=f'{p["label"]}: thread {p["resolution"]["thread_resolution"]["label"]} is source-backed. '
                            f'Tap-drill Ø{f.diameter:g} mm uses SQLite {f.thread_definition_id}; entry depth {f.depth:g} mm and drill point are draft proposals. '
                            'Thread depth, sealing/complete port machining and installation clearance remain unresolved.',
                proposed_value=p['resolution']['thread_resolution']['label']))
        if key in settings['hard_port_faces']:design.constraints.required_feature_faces[f.id]=face
    for index,row in enumerate(plan['mounting'],1):
        hole=row['hole'];axis=FACE_AXES[hole.face][2];through_depth=sizes[axis] if hole.through else hole.depth
        feature=Feature(id=fid(generation_id,f'MOUNTING_{index}','MNT'),kind='mounting',face=hole.face,u=hole.u,v=hole.v,
                        mounting_mode='threaded',thread_definition_id=hole.thread_definition_id,thread_depth=through_depth if hole.through else hole.thread_depth,
                        diameter=None,depth=through_depth,through=hole.through,tip_angle=180 if hole.through else 118)
        feature.u,feature.v=clamp_placement(feature,design,feature.u,feature.v,snap=0,definitions=by_definition)
        design.features.append(feature)
    from ..schema import HydraulicNet
    for net in result['nets']:
        flow=parameter_for(result,settings['flows'],net)
        pressure=parameter_for(result,settings['pressures'],net)
        from ..engineering_conditions import effective_conditions
        prototype=HydraulicNet(id=net_ids[net['id']],flow_lpm=flow,pressure_bar=pressure)
        if inputs.project_engineering:
            previous=next((n for n in inputs.project_engineering.nets if n.id==prototype.id),None)
            if previous:
                for field in ('flow_lpm','pressure_bar','velocity_limit','drilling_mode'):
                    if getattr(prototype,field) is None:setattr(prototype,field,getattr(previous,field))
        conditions=effective_conditions(design,prototype)
        required=math.sqrt(4*(conditions['flow_lpm']/60000)/conditions['velocity_limit']/math.pi)*1000 if conditions['flow_lpm'] else 0
        from ..engineering_db import select_tool
        tool=select_tool(max(options.drilling_diameter,required),0,unit=inputs.project_context)
        if not tool:
            raise ValueError(f'{net["id"]}: no source-backed drill meets the requested/hydraulic minimum diameter')
        diameter=tool['diameter_mm']
        design.nets.append(HydraulicNet(id=net_ids[net['id']],label=str(library.value(result,net['id'],'label') or net['id'])[:120],
            members=[terminal_map[p] for p in net['members']],routing='automatic',diameter=diameter,
            flow_lpm=prototype.flow_lpm,pressure_bar=prototype.pressure_bar,velocity_limit=prototype.velocity_limit,drilling_mode=prototype.drilling_mode))
    from ..layout import initial_placement
    design=initial_placement(design,by_definition)
    return Design.model_validate(design.model_dump()),feature_map,terminal_map


def generate(key, request, progress=lambda message:None,*,cancelled=lambda:False):
    """Compile one normal project. Model owns routing, preview and validation."""
    started=time.monotonic()
    record,run,inputs,result=context(key,request.run_id,request.expected_revision)
    service.verified_documents(inputs)
    plan=prepare(inputs,result,request.options)
    if plan['blocked']:
        return dict(status='needs_input',blocked=plan['blocked'],preflight=preflight(key,request))
    if cancelled():raise CalculationError('Draft creation cancelled; analysis retained.',409)
    progress(dict(message='Arranging resolved engineering components in a standard project',
        progress=dict(stage='layout',stage_text='Arranging engineering components',percent=5,elapsed_s=0)))
    generation_id=uuid.uuid4().hex
    folder=store.OUTPUT/'ai-design'/key/'generations'/generation_id
    folder.mkdir(parents=True,exist_ok=False)
    design,feature_map,terminal_map=candidate(plan,generation_id,0)
    from ..schema import DesignOrigin
    design.origin=DesignOrigin(author='PMC AI Design',method='ai-assisted',provider=run['provider']['id'],model=run['provider']['model'],
        notes='Resolved schematic compiled into an editable project. Shared Model routing and Validate remain explicit engineering operations.')
    store.atomic_json(folder/'authored-draft.json',design.model_dump())
    progress(dict(message='Preparing editable project',progress=dict(stage='finalizing',
        stage_text='Preparing editable project',percent=90,elapsed_s=round(time.monotonic()-started,3))))
    packet=dict(id=generation_id,task_id=key,run_id=run['id'],status='draft',design=design.model_dump(),
        validation=None,attempts=[],feature_mapping=feature_map,terminal_mapping=terminal_map,
        dispositions=plan['settings']['dispositions'],route_status='NOT_ROUTED_NOT_VALIDATED',
        message='Editable project created. Open in Model to start the shared routing proposal; edit, Save and Validate there. No layout optimization or CAD validation was performed during draft creation.')
    packet['elapsed_s']=round(time.monotonic()-started,2)
    packet['resource_limits']=dict(total_features=PROJECT_FEATURES,nets=PROJECT_NETS,placement_attempts=1,
                                  exact_route_attempts_per_placement=0,total_seconds=None)
    packet['topology_acceptance']=dict(action='generate',signature=plan['topology_review']['signature'])
    packet.update(created_at=service.now(),provider=run['provider'],input_revision=run['input_revision'],
                  source_task_revision=request.expected_revision,
                  options=request.options.model_dump(),
                  engine_revision=store.engine_revision())
    corrections=record.get('port_corrections')
    if corrections and corrections['run_id']==run['id'] and corrections['input_revision']==run['input_revision']:
        packet['port_corrections']=corrections
    store.atomic_json(folder/'generation.json',packet)
    with store.project_lock():
        latest=service.read(key)
        if service.revision(latest)!=request.expected_revision:
            packet['status']='superseded_draft' if packet.get('design') else 'superseded'
            packet['message']='Analysis changed during generation. This result belongs to the original run; newer inputs were preserved. Review the retained source draft before using it.'
            store.atomic_json(folder/'generation.json',packet)
        updated={**latest,'generations':[*latest.get('generations',[]),dict(id=generation_id,run_id=run['id'],status=packet['status'],created_at=packet['created_at'])][-100:]}
        service.write(updated,latest)
    return packet


def load_generation(key,generation_id):
    service.read(key)
    path=store.OUTPUT/'ai-design'/service.identifier(key)/'generations'/service.identifier(generation_id)/'generation.json'
    return json.loads(path.read_text(encoding='utf-8'))
