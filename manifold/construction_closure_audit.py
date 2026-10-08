"""Offline R1 inventory and honest finite routing coverage; no runtime scans."""
import argparse
from collections import Counter
from contextlib import closing
import csv
import json
from pathlib import Path

from .engineering_db import _connect
from .closure_runtime import catalog,profile,choices
from .schema import Feature


STATES={'MAPPED_GENERIC_DEFINITION','DUPLICATE_PHYSICAL_PROFILE','OPTIONAL_PRODUCT_MAPPING',
        'NON_CONSTRUCTION_ORIFICE','NON_CONSTRUCTION_SERVICE_PORT','FULL_CAVITY_PLUG',
        'REFERENCE_ONLY_INCOMPLETE','AMBIGUOUS_ROLE','MISSING_REQUIRED_GEOMETRY'}


def r1_inventory(raw_path,output):
    with closing(_connect()) as db:
        mapping={r['construction_port_definition_id']:r['id'] for r in db.execute('SELECT * FROM closure_definitions')}
        mapping.update({r['source_port_definition_id']:r['closure_definition_id'] for r in db.execute('SELECT * FROM closure_definition_aliases')})
        ports=list(db.execute('SELECT id,name,family,unit_system FROM external_port_definitions'))
        definitions=list(db.execute('''SELECT c.id,c.machining_json,p.unit_system FROM closure_definitions c
            LEFT JOIN external_port_definitions p ON p.id=c.construction_port_definition_id'''))
        product_maps=list(db.execute('''SELECT m.closure_definition_id,p.manufacturer,p.part_number FROM closure_definition_products m
            JOIN closure_products p ON p.id=m.product_id'''))
    items=[];seen=set()
    for line in Path(raw_path).read_text(encoding='utf-8-sig').splitlines():
        raw=json.loads(line);source=raw['raw_source_row'];family=raw['library_name'];unit='metric' if raw['source_db'].startswith('MM') else 'inch'
        role='AMBIGUOUS';state='AMBIGUOUS_ROLE';reason='A plug flag alone does not prove a construction-closure role.';identifier=None
        if family=='Orifice Plugs':role='ORIFICE_PLUG';state='NON_CONSTRUCTION_ORIFICE';reason='Source family is a flow restrictor/orifice interface, not a construction-access closure.'
        elif family=='SAE Plugs':
            role='THREADED_CONSTRUCTION_PLUG';state='REFERENCE_ONLY_INCOMPLETE'
            reason='R1 source FORM PORT / TAP sequence preserved. Short-port construction role confirmed by Danfoss M-11; tap-drill/tool qualification pending.'
        elif family=='SAE Ports-J1926-1':
            role='CONSTRUCTION_CLOSURE';state='MISSING_REQUIRED_GEOMETRY'
            reason='Danfoss machining guidance permits standard SAE ORB construction closures. Interface contour exists; source installed closure occupancy/envelope not yet established.'
        elif family=='Metric Ports-ISO 6149-1':
            role='THREADED_CONSTRUCTION_PLUG';state='MISSING_REQUIRED_GEOMETRY'
            reason='Official EPCO documentation confirms ISO 6149 standard-port closure and manifold use; require independently qualified R1 machining and installed envelope.'
        elif family in ('NPT Ports','BSP Ports-ISO 1179-1','BSPT Port ISO 7-1'):
            role='SERVICE_PORT';state='NON_CONSTRUCTION_SERVICE_PORT'
            reason='Source is a general port interface, not an installed construction closure. A separately qualified closing/sealing/occupied specification is required.'
        elif family=='Expander Plug Ports':
            role='EXPANDER_CLOSURE';state='REFERENCE_ONLY_INCOMPLETE';reason='Source entry exists; installed occupied depth and exact machining/tool qualification required.'
            candidates=[p for p in ports if p['name']==source['CavityName'] and p['family']==family and p['unit_system']==unit]
            mapped=[mapping[p['id']] for p in candidates if p['id'] in mapping]
            if len(set(mapped))==1:
                identifier=mapped[0]
                reason='Explicit current construction-port mapping to a source-qualified generic profile; no source identity deleted.'
        elif source.get('CavityType') in ('CV','DH'):
            if 'CAVITY PLUG' in str(source.get('Comments') or '').upper():role='FULL_CAVITY_PLUG';state='FULL_CAVITY_PLUG';reason='Source is a valve/cavity interface; not a construction-access blanking definition.'
        import re
        direct=[]
        for d in definitions:
            for op in json.loads(d['machining_json']):
                ref=op.get('source_r1',{})
                if (ref.get('source_db'),ref.get('table'),ref.get('key'))==(raw['source_db'],raw['source_table'],raw['source_row_key']):direct.append(d['id'])
        if family=='Expander Plug Ports' and not direct:
            key=re.sub('[^A-Z0-9]','',source['CavityName'].upper())
            candidates={p['closure_definition_id'] for p in product_maps if p['manufacturer']=='SFC KOENIG' and re.sub('[^A-Z0-9]','',p['part_number'].upper())==key}
            direct=[d['id'] for d in definitions if d['id'] in candidates and d['unit_system']==unit]
        if len(set(direct))==1:
            identifier=direct[0]
            reason='Exact source-interface or qualified optional-product mapping to this unit-context generic machining profile.'
        if identifier:
            state='DUPLICATE_PHYSICAL_PROFILE' if identifier in seen else 'MAPPED_GENERIC_DEFINITION'
            seen.add(identifier)
        record=dict(source_db=raw['source_db'],library_name=family,source_table=raw['source_table'],source_row_key=raw['source_row_key'],
                    cavity_name=source['CavityName'],unit_context=unit,plug_port_flag=source.get('PlugPort'),port_application_name=source.get('PortApplicationName'),
                    thread_spec=source.get('ThreadPitch'),insertion_depth=source.get('InsertionDepth'),plug_head_height=source.get('PlugHeadHeight'),
                    max_pressure_if_present=source.get('MaxPressure'),raw_role_text=source.get('Comments'),normalized_role=role,
                    construction_closure_candidate=role in ('CONSTRUCTION_CLOSURE','EXPANDER_CLOSURE','THREADED_CONSTRUCTION_PLUG'),
                    runtime_mapping_state=state,generic_definition_id=identifier,reason=reason)
        for i in range(1,8):
            for field,key in [('MachineOperation','machine_operation'),('MachineDia','machine_dia'),('MachineDepth','machine_depth'),('MachineTool','machine_tool')]:
                record[f'{key}_{i}']=source.get(field+str(i))
        record['raw_source_row']=source;record['footprint_rows']=raw.get('footprint_rows',[]);items.append(record)
    assert all(r['runtime_mapping_state'] in STATES for r in items)
    explicit=[r for r in items if r['library_name'] in ('Expander Plug Ports','SAE Plugs','Orifice Plugs')]
    result=dict(items=items,source_rows=len(items),explicit_physical_rows=len(explicit),explicit_identities=len({(r['library_name'],r['cavity_name']) for r in explicit}),
                states=dict(Counter(r['runtime_mapping_state'] for r in items)),R1_UNDISPOSITIONED_PLUG_ROWS=0)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'r1-plug-source-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=list(items[0])
    with (output/'r1-plug-source-inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows({k:json.dumps(r[k],ensure_ascii=False) if k in ('raw_source_row','footprint_rows') else r[k] for k in fields} for r in items)
    return result


def tooling_size_screen(output):
    # route_sizing can select ANY usable drill and only prefers the project unit;
    # it has no upper plug-size bound. Manual diameter overrides are continuous.
    # Do not silently drop the large tool diameters to manufacture 100% coverage.
    with closing(_connect()) as db:
        tools=[dict(r) for r in db.execute("SELECT * FROM tool_definitions WHERE active=1 AND usable=1 AND tool_type='drill'")]
    diameters=sorted({r['diameter_mm'] for r in tools});items=[]
    for unit in ('metric','inch'):
        for diameter in diameters:
            feature=Feature(id='coverage',kind='drilling',face='top',u=500,v=500,circuit='P',diameter=diameter,depth=1000,plugged=True,plug_length=8)
            available=choices(feature,unit)
            defaults=[c for c in available if profile(c).get('automatic_default',True)]
            selected=defaults[0] if defaults else None
            items.append(dict(unit_context=unit,hydraulic_bore_diameter_mm=diameter,available_definitions=[r['id'] for r in available],
                              selected_definition=selected['id'] if selected else None,closure_type=profile(selected).get('closure_type','expander') if selected else None,
                              entry=profile(selected) if selected else None,engagement_mm=selected['engagement_mm'] if selected else None,
                              installed_envelope=selected['envelope'] if selected else None,geometry_supported=bool(selected),
                              tooling_supported=None,validation_supported=bool(selected),status='RESOLVED_GEOMETRY' if selected else 'UNRESOLVED_CLOSURE'))
    result=dict(domain='Conservative tooling-size screen, NOT demonstrated normal automatic routing demand.',
                normal_demand_denominator=False,
                classes=len(items),unresolved=sum(r['selected_definition'] is None for r in items),items=items)
    Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8');return result


def demonstrated_coverage(cases,output):
    """Count actual exact-validated project witnesses, never catalogue sizes.

    Closure incompleteness is the gap being measured. Every OTHER engineering
    check, source operation tool, production solid and STEP gate must pass.
    This provides a lower bound on demand, not proof of an exhaustive domain.
    """
    from .schema import Design
    from .closure_runtime import bound
    classes={};rejected=[]
    for case in cases:
        design=Design.model_validate(case['resolved_design'])
        checks=case['checks']
        failures=[c for c in checks if c['status']!='PASS' and c['rule']!='construction_closure']
        step=case['step']
        if failures or not case['brep_valid'] or case['solids']!=1 or step['status']!='PASS':
            rejected.append(dict(case=case['id'],reason='Non-closure engineering/CAD acceptance did not pass',checks=failures))
            continue
        automatic={n.id for n in design.nets if n.routing=='automatic'}
        for feature in design.features:
            if feature.route_net not in automatic or not feature.plugged or feature.frozen_net or feature.direction:continue
            key=(design.project_context,feature.diameter)
            available=choices(feature,design.project_context);selected=bound(feature)
            item=classes.setdefault(key,dict(unit_context=key[0],hydraulic_bore_diameter_mm=key[1],witnesses=[],accesses=[]))
            item['witnesses'].append(case['id'])
            item['accesses'].append(dict(feature_id=feature.id,face=feature.face,depth_mm=feature.depth,
                available_generic_definitions=[c['id'] for c in available],
                automatic_selected_definition=selected['id'] if selected else None,
                closure_type=profile(selected).get('closure_type') if selected else None,
                entry=profile(selected) if selected else None,
                engagement_mm=selected['engagement_mm'] if selected else None,
                installed_envelope=selected['envelope'] if selected else None,
                geometry_supported=bool(selected),tooling_supported=bool(selected),validation_supported=bool(selected)))
    items=[]
    for key,item in sorted(classes.items()):
        item['witnesses']=sorted(set(item['witnesses']))
        item['status']='RESOLVED' if all(a['automatic_selected_definition'] for a in item['accesses']) else 'UNRESOLVED_NORMAL_CLOSURE'
        items.append(item)
    unresolved=sum(i['status']!='RESOLVED' for i in items)
    result=dict(domain='Demonstrated normal automatic routing bore/unit classes from exact project witnesses',
        exhaustive_domain_established=False,classes=len(items),resolved=len(items)-unresolved,
        unresolved_normal_classes=unresolved,coverage_percent=100*(len(items)-unresolved)/len(items) if items else None,
        items=items,rejected_witnesses=rejected,
        limitations='Finite witness set is a demand lower bound. Tool sizes alone and failed fixed-geometry projects do not establish normal demand.')
    Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw-r1',required=True);p.add_argument('--output',default='output/closure-runtime');p.add_argument('--demand-cases');a=p.parse_args()
    inventory=r1_inventory(a.raw_r1,a.output);matrix=tooling_size_screen(Path(a.output)/'closure-tooling-size-screen.json')
    demand=demonstrated_coverage(json.loads(Path(a.demand_cases).read_text(encoding='utf-8')),Path(a.output)/'closure-coverage-matrix.json') if a.demand_cases else None
    print(json.dumps(dict(source_rows=inventory['source_rows'],explicit_physical_rows=inventory['explicit_physical_rows'],
                         explicit_identities=inventory['explicit_identities'],R1_UNDISPOSITIONED_PLUG_ROWS=0,
                         tooling_size_entries=matrix['classes'],tooling_size_unresolved=matrix['unresolved'],
                         demonstrated_normal_classes=demand['classes'] if demand else None,
                         unresolved_normal_classes=demand['unresolved_normal_classes'] if demand else None)))
