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
from ..kinematics import FACE_AXES, dimensions, clamp_placement, pose
from ..routing import terminal_points, route_cost
from ..engineering import calculate_sync,CalculationError
from . import service, library_resolution as library
from .models import TaskInput
from .intent import effective_result, interpret, parameter_for
from .generation_models import GenerationOptions


def context(key, run_id, expected):
    record = service.read(key)
    service.check(record, expected)
    run = service.load_run(key, run_id)
    if run['status'] != 'completed':
        raise ValueError('Select a completed analysis before generation')
    if run['input_revision'] != service.digest(record['inputs']):
        raise ValueError('Analysis is stale. Analyze the current inputs before generation.')
    inputs = TaskInput.model_validate(record['inputs'])
    reviews = copy.deepcopy(record['reviews'].get(run_id, {}))
    return record, run, inputs, effective_result(run, reviews), reviews


def topology(result, options):
    result = copy.deepcopy(result)
    ports = {p['id']: p for p in result['ports']}
    if not set(options.net_overrides) <= set(ports):
        raise ValueError('Net override refers to a missing port')
    if options.net_overrides and not options.topology_decision.strip():
        raise ValueError('Changing hydraulic connections needs an engineer decision')
    by_id = {n['id']: n for n in result['nets']}
    for port_id, target in options.net_overrides.items():
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
                    by_id[target] = dict(id=target, members=[], claim_ids=[])
                    result['nets'].append(by_id[target])
                    result['claims'].append(dict(id='LABEL_' + target, subject_id=target, predicate='label', value=name))
        for net in result['nets']:
            net['members'] = [p for p in net['members'] if p != port_id]
        by_id[target]['members'].append(port_id)
    result['nets'] = [n for n in result['nets'] if n['members']]
    return result


def prepare(inputs, result, options):
    result = topology(result, options)
    settings = interpret(result, options)
    blocked = list(settings['conflicts'])
    if len(result['components']) > 4 or len(result['ports']) > 40 or len(result['nets']) > 16:
        blocked.append('First-generation scope is at most 4 cartridges, 40 hydraulic terminals and 16 nets.')
    if not result['ports'] or not result['nets']:
        blocked.append('No usable hydraulic topology was recognized. Review the source and analyze again.')
    port_net = {p: n['id'] for n in result['nets'] for p in n['members']}
    for port in result['ports']:
        if port['id'] not in port_net:
            blocked.append(str(library.value(result, port['id'], 'label') or port['id']) + ': choose a hydraulic net for the unknown connection.')
    components = []
    known_components = {c['id'] for c in result['components']}
    known_external = {p['id'] for p in result['ports'] if p['component_id'] is None}
    if not set(options.bindings) <= known_components or not set(options.port_definitions) <= known_external:
        raise ValueError('Library choice refers to a missing component or external port')
    for component in result['components']:
        key = component['id']
        choices = library.candidates(inputs, result, component)
        resolution = library.resolution_status(inputs, result, component, choices)
        selected = options.bindings.get(key)
        automatic = False
        if selected:
            definition = library.load(inputs, selected.definition_key, selected.definition_sha256)
            mapping = selected.zone_ports
            decision = selected.decision.strip()
            resolution = {**resolution, 'code': 'manual_selection',
                          'message': 'An existing cavity has been selected explicitly.',
                          'action': 'Confirm the engineering decision and complete the hydraulic window mapping.'}
            if not decision:
                blocked.append(f'{library.value(result,key,"label") or key}: confirm the selected cavity and interface mapping.')
        else:
            usable = [row for row in choices if row['geometry_status'] != 'draft-projection' and not row['demo_only']]
            mapping = library.matching_zones(result, component, usable[0]['zones']) if len(usable) == 1 else None
            if mapping:
                row = usable[0]
                definition = library.load(inputs, row['key'], row['sha256'])
                automatic = True
                decision = row['reason'] + '; exact port-number/window labels matched by PMC. Engineer review remains required.'
            else:
                definition, mapping, decision = None, {}, ''
                blocked.append(f'{library.value(result,key,"label") or key}: {resolution["message"]} {resolution["action"]}')
        if definition:
            if definition.usage_role != 'cartridge-cavity':
                raise ValueError('An external-port definition cannot be used as a cartridge cavity')
            if set(mapping) != {z.id for z in definition.zones} or set(mapping.values()) != set(component['port_ids']) or len(set(mapping.values())) != len(mapping):
                blocked.append(f'{key}: map every cavity window to exactly one distinct schematic component port.')
        components.append(dict(id=key, label=library.value(result,key,'label') or key,
                               model=library.identity_value(result,key,'model') or '',
                               function=library.value(result,key,'functional_type') or '',
                               choices=choices, definition=definition, mapping=dict(mapping or {}),
                               automatic=automatic, decision=decision, resolution=resolution))
    external = []
    for port in result['ports']:
        if port['component_id'] is not None:
            continue
        selected = options.port_definitions.get(port['id'])
        definition = library.load(inputs, selected.definition_key, selected.definition_sha256) if selected else None
        if definition and (definition.usage_role != 'external-port' or len(definition.zones) != 1):
            raise ValueError('External ports require a source external-port definition with one hydraulic interface')
        if definition and not selected.decision.strip():
            blocked.append(f'{port["id"]}: confirm the external-port definition choice.')
        external.append(dict(id=port['id'], label=library.value(result,port['id'],'label') or port['id'],
                             specification=library.value(result,port['id'],'port_specification') or '',
                             definition=definition, decision=selected.decision if selected else ''))
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
                blocked.append(row['message'])
            else:
                row.update(status='applied', message='Targets remain distinct nets; cross-net physical intersections fail deterministic validation.')
    return dict(inputs=inputs, result=result, settings=settings, blocked=blocked, components=components,
                external=external, port_net=port_net, options=options)


def preflight(key, request):
    _, _, inputs, result, _ = context(key, request.run_id, request.expected_revision)
    plan = prepare(inputs, result, request.options)
    def entry(row):
        return {**{k:v for k,v in row.items() if k != 'definition'},
                'definition': library.summary('',row['definition']) if row['definition'] else None}
    return dict(ready=not plan['blocked'], blocked=plan['blocked'], components=[entry(c) for c in plan['components']],
                external_ports=[entry(p) for p in plan['external']], dispositions=plan['settings']['dispositions'],
                ports=[dict(id=p['id'], component_id=p['component_id'], label=library.value(result,p['id'],'label') or p['id'],
                            net=plan['port_net'].get(p['id'])) for p in result['ports']],
                nets=[dict(id=n['id'],label=library.value(result,n['id'],'label') or n['id']) for n in result['nets']])


def fid(generation_id, key, prefix):
    return prefix + '_' + hashlib.sha256((generation_id + ':' + key).encode()).hexdigest()[:20]


def candidate(plan, generation_id, variant):
    options, settings, inputs, result = (plan[x] for x in ('options','settings','inputs','result'))
    wall = options.minimum_wall
    libraries = {}
    aliases = {}
    for row in [*plan['components'], *plan['external']]:
        definition = row['definition']
        if definition:
            sha = service.digest(definition.model_dump())
            if sha not in libraries:
                definition = definition.model_copy(deep=True)
                # Two selected revisions of one catalog ID can coexist without a reference collision.
                if any(d.id == definition.id for d in libraries.values()):
                    definition.id = fid(generation_id,sha,'DEF')
                libraries[sha] = definition
            aliases[row['id']] = libraries[sha].id
    defs = list(libraries.values())
    by_definition = {d.id:d for d in defs}
    ncomponents = len(plan['components'])
    radii = [c['definition'].clearance_diameter/2 for c in plan['components']]
    clearance = max(radii or [10]) * 2 + wall*2 + (6 if settings['priority'] == 'compact' else 16)
    cols = max(1,math.ceil(math.sqrt(ncomponents)))
    rows = max(1,math.ceil(ncomponents/cols))
    depths = [max([s.end for s in d.stages] + [p.end for p in d.cutting_primitives]) for d in defs]
    base = [max(80,cols*clearance+wall*2), max(80,rows*clearance+wall*2), max(70,max(depths or [25])+wall*2+12)]
    # Non-top mounting consumes depth along its own inward axis.
    for c in plan['components']:
        face = settings['component_faces'].get(c['id'],'top')
        axis = FACE_AXES[face][2]
        base[axis] = max(base[axis], max(s.end for s in c['definition'].stages)+wall*2+12)
    scale = (1, 1.18, 1.35, 1.5, 1.7, 1.9)[variant]
    sizes = [max(lo,min(hi,math.ceil(size*scale/5)*5)) for size,lo,hi in zip(base,settings['minimum'],settings['maximum'])]
    block = dict(zip(('length','width','height'),sizes))
    block['material'] = settings['material']
    raw = dict(name=(inputs.title[:100] + ' - AI Draft'), project_context=inputs.project_context, block=block,
               library=[d.model_dump() for d in defs], features=[], components=[], nets=[],
               schematics=[d.asset.model_dump() for d in inputs.documents], rules=dict(minimum_wall=wall),
               constraints=dict(envelope_max=settings['maximum'],envelope_min=settings['minimum'],
                   forbidden_drilling_faces=settings['forbidden'],priority=settings['priority'],
                   notes='Original requirements and execution dispositions are linked from origin.ai_trace.'))
    design = Design.model_validate(raw)
    feature_map, terminal_map, net_ids = {}, {}, {}
    used_nets = set()
    for i,net in enumerate(result['nets'],1):
        label = str(library.value(result,net['id'],'label') or net['id'])
        name = label if re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}',label) and label not in used_nets else 'NET_'+str(i)
        while name in used_nets:
            name += '_'
        net_ids[net['id']] = name
        used_nets.add(name)
    groups = {}
    for component in plan['components']:
        groups.setdefault(settings['component_faces'].get(component['id'],'top'),[]).append(component)
    for face,group in groups.items():
        u_axis,v_axis,_,_=FACE_AXES[face]
        local_cols=max(1,math.ceil(math.sqrt(len(group))))
        local_rows=math.ceil(len(group)/local_cols)
        for i,c in enumerate(group):
            key=c['id'];definition=by_definition[aliases[key]]
            f=Feature(id=fid(generation_id,key,'CV'),kind='cavity',face=face,
                      u=sizes[u_axis]*(i%local_cols+1)/(local_cols+1),
                      v=sizes[v_axis]*(i//local_cols+1)/(local_rows+1),definition=definition.id,
                      circuits={zone:net_ids[plan['port_net'][port]] for zone,port in c['mapping'].items()},
                      cartridge_model=str(c['model'])[:120],schematic_id=key)
            f.u,f.v=clamp_placement(f,design,f.u,f.v,snap=0)
            design.features.append(f);feature_map[key]=f.id
            for zone,port in c['mapping'].items():terminal_map[port]=f.id+':'+zone
            from ..schema import SchematicComponent
            design.components.append(SchematicComponent(id=key[:39],label=str(c['label'])[:160],function=str(c['function'])[:200],
                cartridge_model=str(c['model'])[:120],cavity_definition=definition.id,feature_id=f.id,ports=f.circuits,
                status='unconfirmed' if c['automatic'] else 'confirmed'))
            if key in settings['hard_component_faces']:design.constraints.required_feature_faces[f.id]=face
    points=terminal_points(design)
    default_faces=('left','right','front','back')
    used_ports=[]
    for i,p in enumerate(plan['external']):
        key=p['id'];source_net=plan['port_net'][key]
        net=next(n for n in result['nets'] if n['id']==source_net)
        targets=[terminal_map[m] for m in net['members'] if m in terminal_map]
        face=settings['port_faces'].get(key,default_faces[(i+variant//2)%4])
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
            kwargs.update(definition=definition.id,diameter=min(s.diameter for s in definition.stages),
                          depth=definition.zones[0].end,clearance_diameter=definition.clearance_diameter,
                          clearance_height=definition.clearance_height,tip_angle=180,
                          port_type=definition.label,size=definition.thread_note[:80])
        else:
            kwargs.update(diameter=options.port_diameter,depth=options.port_depth,tip_angle=180,
                          clearance_diameter=max(20,options.port_diameter+6),clearance_height=20,
                          port_type='Provisional straight bore - no thread specified',size=f'Draft bore {options.port_diameter:g} mm')
        f=Feature(**kwargs);f.u,f.v=clamp_placement(f,design,f.u,f.v,snap=0)
        # Separate mouths sharing a face. Exact installed-envelope checks still decide.
        for previous in used_ports:
            if previous.face==face and math.hypot(f.u-previous.u,f.v-previous.v)<(f.clearance_diameter+previous.clearance_diameter)/2+2:
                f.u,f.v=clamp_placement(f,design,f.u,f.v+(f.clearance_diameter+previous.clearance_diameter)/2+wall,snap=0)
        used_ports.append(f);design.features.append(f);terminal_map[key]=f.id;feature_map[key]=f.id
        if key in settings['hard_port_faces']:design.constraints.required_feature_faces[f.id]=face
        design.constraints.preferred_port_faces[f.circuit]=face
    from ..schema import HydraulicNet
    for net in result['nets']:
        flow=parameter_for(result,settings['flows'],net)
        pressure=parameter_for(result,settings['pressures'],net)
        required=math.sqrt(4*(flow/60000)/6/math.pi)*1000 if flow else 0
        diameter=next((d for d in [4,5,6,8,10,12,16,20,25,32] if d>=max(options.drilling_diameter,required)),32)
        design.nets.append(HydraulicNet(id=net_ids[net['id']],label=str(library.value(result,net['id'],'label') or net['id'])[:120],
            members=[terminal_map[p] for p in net['members']],routing='automatic',diameter=diameter,
            flow_lpm=flow,pressure_bar=pressure))
    return Design.model_validate(design.model_dump()),feature_map,terminal_map


def review_items(plan, design, feature_map):
    from ..schema import EngineeringReview
    items=[]
    def add(kind,subject,description,severity='review',decision=''):
        items.append(EngineeringReview(id='AI_REVIEW_'+str(len(items)+1),kind=kind,subject=str(subject)[:120],
            description=description[:2000],severity=severity,status='accepted' if decision else 'open',resolution=decision[:2000]))
    add('source','AI generation','AI-generated Draft. Review schematic interpretation, placement and all engineering assumptions. Geometry checks are not production approval.')
    for c in plan['components']:
        add('component',feature_map[c['id']],str(c['label'])+': '+c['decision'],decision='' if c['automatic'] else c['decision'])
        if c['definition'].native and c['definition'].native.geometry_status=='draft-projection':
            add('dimension',feature_map[c['id']],'Selected source definition still has unresolved geometry mapping. This draft cannot establish cartridge geometry.',severity='blocking')
        if c['definition'].demo_only:
            add('dimension',feature_map[c['id']],'Engineer-selected demonstration cavity. Not a vendor machining specification.',severity='blocking')
        add('component',feature_map[c['id']],'Cartridge compatibility, pressure/flow ratings, seals and actual service envelope require source review; no values were invented.')
    for p in plan['external']:
        if not p['definition']:
            add('dimension',feature_map[p['id']],str(p['label'])+': provisional unthreaded straight bore. Requested specification: '+
                (str(p['specification']) or 'not supplied')+'. Select/confirm a real machining definition before manufacture.')
    for row in plan['settings']['dispositions']:
        if row['status']!='applied':
            add('assumption',row['intent_id'],row['property']+': '+row['message'],
                severity='blocking' if row['strength']=='requirement' and row['status'] in ('unsupported','conflict','review_required') else 'review')
    for item in plan['result']['unresolved'][:30]:
        add('source','schematic',item['description'])
    if plan['settings']['material'].startswith('Unspecified'):
        add('dimension','block','Material is unspecified. No pressure/material capability has been inferred.')
    if plan['options'].net_overrides:
        add('connection','schematic','Engineer revised the extracted topology.',decision=plan['options'].topology_decision)
    # Reserve space in the existing bounded Design review contract.
    design.review_items=items[:100]
    if len(items)>100:
        design.review_items[-1]=EngineeringReview(id='AI_REVIEW_OVERFLOW',kind='source',description='Additional review details are retained in the linked generation record.',severity='blocking')


def score(report, design):
    # Search can improve geometry without pretending unreviewed schematic facts are approved.
    geometry_failures=sum(c['status']=='FAIL' for c in report['checks'] if c['rule']!='engineering_review'
                         and not (c['rule']=='schematic_conformance' and c['actual'] is True))
    return (geometry_failures,report['counts']['FAIL'],report['counts']['WARNING'],
            route_cost(design,[f for f in design.features if f.kind=='drilling']))


def generate(key, request, progress=lambda message:None):
    record,run,inputs,result,reviews=context(key,request.run_id,request.expected_revision)
    service.verified_documents(inputs)
    plan=prepare(inputs,result,request.options)
    if plan['blocked']:
        return dict(status='needs_input',blocked=plan['blocked'],preflight=preflight(key,request))
    generation_id=uuid.uuid4().hex
    folder=store.OUTPUT/'ai-design'/key/'generations'/generation_id
    folder.mkdir(parents=True,exist_ok=False)
    attempts=[];best=None;started=time.monotonic()
    for index in range(request.options.max_attempts):
        progress(f'Exact candidate {index+1}/{request.options.max_attempts}: placement, routing, wall and connectivity checks')
        try:
            design,feature_map,terminal_map=candidate(plan,generation_id,index)
            from ..schema import DesignOrigin,AITrace
            design.origin=DesignOrigin(author='PMC AI Design',method='ai-assisted',provider=run['provider']['id'],model=run['provider']['model'],
                notes='AI-generated Draft. Original analysis and exact candidate evidence retained locally. No manufacturing approval.',
                ai_trace=AITrace(analysis_id=key,run_id=run['id'],generation_id=generation_id,input_sha256=run['input_revision'],
                                 result_sha256=service.digest(run['result']),original_requirements=inputs.engineering_requirements))
            review_items(plan,design,feature_map)
            checked=calculate_sync('validate',design.model_dump(),progress)
            resolved=Design.model_validate(checked['design']);routes=checked['routes'];report=checked['report']
            # Retain resolved routing choices in the authored draft so preview matches the evaluated proposal.
            for net in design.nets:
                net.routing_variant=next(n.routing_variant for n in resolved.nets if n.id==net.id)
            store.atomic_json(folder/f'attempt-{index:02}'/'design.json',design.model_dump())
            store.atomic_json(folder/f'attempt-{index:02}'/'resolved_design.json',resolved.model_dump())
            store.atomic_json(folder/f'attempt-{index:02}'/'validation.json',report)
            ranking=score(report,resolved)
            attempts.append(dict(index=index,score=ranking,counts=report['counts'],
                                 geometry_failures=ranking[0],block=design.block.model_dump(),routes=routes,
                                 failed_rules=sorted({c['rule'] for c in report['checks'] if c['status']=='FAIL'})))
            if best is None or ranking<best[0]:best=(ranking,design,report,index,feature_map,terminal_map)
            if ranking[0]==0:
                break
        except CalculationError:
            # A deadline/busy/native-worker failure needs explicit recovery, not
            # another expensive placement attempt hiding the execution failure.
            raise
        except (ValueError,RuntimeError) as exc:
            # Model/user content and arbitrary CAD exception bodies are not diagnostic output.
            attempts.append(dict(index=index,error=type(exc).__name__,message='Candidate could not be built; expanding/rearranging within requested bounds.'))
            store.atomic_json(folder/f'attempt-{index:02}'/'failure.json',attempts[-1])
        if time.monotonic()-started>480:
            break
    if best is None:
        packet=dict(id=generation_id,task_id=key,run_id=run['id'],status='no_buildable_candidate',attempts=attempts,
                    message='No candidate could be built within the requested envelope. Review selected cavity mapping and block constraints.')
    else:
        _,design,report,chosen,feature_map,terminal_map=best
        packet=dict(id=generation_id,task_id=key,run_id=run['id'],status='draft',design=design.model_dump(),validation=report,
                    selected_attempt=chosen,geometry_failures=best[0][0],attempts=attempts,feature_mapping=feature_map,
                    terminal_mapping=terminal_map,dispositions=plan['settings']['dispositions'],
                    message='Editable AI Draft; exact validation and engineering review status are separate from manufacturing approval.')
    packet.update(created_at=service.now(),provider=run['provider'],input_revision=run['input_revision'],
                  source_result_sha256=service.digest(run['result']),reviews=reviews,options=request.options.model_dump(),
                  engine_revision=store.engine_revision())
    store.atomic_json(folder/'generation.json',packet)
    with store.project_lock():
        latest=service.read(key)
        service.check(latest,request.expected_revision)
        updated={**latest,'generations':[*latest.get('generations',[]),dict(id=generation_id,run_id=run['id'],status=packet['status'],created_at=packet['created_at'])][-100:]}
        service.write(updated,latest)
    return packet


def load_generation(key,generation_id):
    service.read(key)
    path=store.OUTPUT/'ai-design'/service.identifier(key)/'generations'/service.identifier(generation_id)/'generation.json'
    return json.loads(path.read_text(encoding='utf-8'))
