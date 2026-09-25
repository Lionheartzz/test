import json

import pytest

from manifold.drawing.generate import anchors
from manifold.demo import CAVITY_ID
from manifold.engineering_db import (
    _connect,
    get_definition,
    materials,
    normalized_port_family,
    resolve_machining_tools,
    search_definitions,
    search_threads,
    select_tool,
    validate_references,
)
from manifold.geometry import build_geometry
from manifold.kinematics import definition_planar_radius
from manifold.import_mdtools import thread_record
from manifold.manufacturing import manufacturing_outputs
from manifold.routing import authorize_generated_contacts, resolve_design
from manifold.schema import Design
from manifold.validation import validate


def m12_thread():
    rows=search_threads('M12x1.75',unit='metric',usable_only=True,limit=500)
    return next(row for row in rows if row['display_name']=='M12x1.75-6H' and row['tap_diameter_mm']==pytest.approx(10.25)
                and select_tool(row['tap_diameter_mm'],25,exact_diameter=True))


def test_thread_import_never_reuses_an_unrelated_generic_drill_as_tap_bore():
    ambiguous=thread_record(dict(ThreadPitch='M10x1',ThreadClass='6H',MachineOperation1='DRILL',
        MachineDia1='$STEP12',Circle12Dia=2),1)
    assert not ambiguous['usable'] and ambiguous['tap_diameter_mm'] is None
    explicit=thread_record(dict(ThreadPitch='M10x1',ThreadClass='6H',MachineOperation1='TAP DRILL',
        MachineDia1='$STEP12',Circle12Dia=8.8,MachineOperation2='TAP',MachineDia2='M10x1-6H'),1)
    assert explicit['usable'] and explicit['tap_diameter_mm']==pytest.approx(8.8)
    impossible=thread_record(dict(ThreadPitch='M8x1',MachineOperation1='TAP DRILL',MachineDia1='$STEP12',
        Circle12Dia=8.42,MachineOperation2='TAP',MachineDia2='M8x1'),1)
    assert not impossible['usable'] and 'major diameter' in impossible['unusable_reason']
    decimal=thread_record(dict(ThreadPitch='M6x1',MachineOperation1='TAP DRILL',MachineDia1='$STEP12',
        Circle12Dia=5,MachineOperation2='TAP',MachineDia2='M6x1.0'),1)
    assert decimal['usable']
    unrelated=thread_record(dict(ThreadPitch='9/16 -12 UNF',ThreadClass='2B',MachineOperation1='TAP DRILL',
        MachineDia1='$STEP12',Circle12Dia=.4,MachineOperation2='TAP',MachineDia2='2'),25.4)
    assert not unrelated['usable'] and 'identity conflicts' in unrelated['unusable_reason']


def threaded_design(*, depth=25, block_length=100, face='top'):
    thread=m12_thread()
    return Design(name='Threaded mounting QA',block=dict(length=block_length,width=80,height=50,material='QA'),
        features=[dict(id='MH1',kind='mounting',face=face,u=40,v=25,mounting_mode='threaded',
            thread_definition_id=thread['id'],thread_depth=min(20,depth),diameter=None,depth=depth)]),thread


def test_source_thread_drives_exact_bore_manufacturing_and_drawing(tmp_path):
    design,thread=threaded_design()
    validate_references(design)
    geometry=build_geometry(design)
    report=validate(design,geometry)
    assert next(row for row in report['checks'] if row['rule']=='source_tool_available')['status']=='PASS'
    manufacturing_outputs(design,geometry,tmp_path)
    manufacturing=json.loads((tmp_path/'manufacturing.json').read_text(encoding='utf-8'))
    profile=manufacturing['machining_profiles'][0]
    assert profile['thread_facts']['id']==thread['id']
    assert profile['cylinder_diameter_mm']==pytest.approx(thread['tap_diameter_mm'])
    assert profile['selected_tool']['diameter_mm']==pytest.approx(thread['tap_diameter_mm'])
    csv_row=(tmp_path/'drill-chart.csv').read_text(encoding='utf-8-sig').splitlines()
    assert 'thread_depth' in csv_row[0] and thread['display_name'] in csv_row[1]
    _,rows,_=anchors(dict(resolved=design.model_dump(),manufacturing=manufacturing))
    assert rows[0]['pmc_specification']=='M12x1.75-6H THD HOLE'
    assert 'TAP DRILL' in rows[0]['specification']


@pytest.mark.parametrize(('family','name','designation'),[
    ('BSP Ports-ISO 1179-1','G 1/4','G 1/4-19'),
    ('NPT Ports','NPT 1/4','1/4-18 NPT'),
])
def test_source_standard_port_keeps_complete_identity_and_exact_machining(tmp_path,family,name,designation):
    with _connect() as connection:
        identifier=connection.execute(
            'SELECT id FROM external_port_definitions WHERE active=1 AND usable=1 AND unit_system=? AND family=? AND name=? ORDER BY id LIMIT 1',
            ('metric',family,name)).fetchone()[0]
    definition=get_definition(identifier)
    design=Design(name=designation,project_context='metric',block=dict(length=100,width=80,height=50,material='QA'),
        features=[dict(id='PORT_P',kind='port',face='front',u=50,v=25,circuit='P',port_definition_id=identifier)])
    validate_references(design)
    geometry=build_geometry(design)
    assert geometry.production.isValid() and geometry.cuts['PORT_P'].Volume()>0
    assert definition.thread_note==designation and definition.zones
    manufacturing_outputs(design,geometry,tmp_path)
    manufacturing=json.loads((tmp_path/'manufacturing.json').read_text(encoding='utf-8'))
    profile=manufacturing['machining_profiles'][0]
    assert profile['definition_facts']['thread_specification']==designation
    assert len(profile['cutting_steps'])>1
    _,rows,_=anchors(dict(resolved=design.model_dump(),manufacturing=manufacturing))
    assert designation in rows[0]['pmc_specification']
    assert Design.model_validate(design.model_dump()).features[0].port_definition_id==identifier


def test_source_tool_depth_is_a_deterministic_manufacturing_failure():
    design,_=threaded_design(depth=160,block_length=200,face='left')
    geometry=build_geometry(design)
    row=next(row for row in validate(design,geometry)['checks'] if row['rule']=='source_tool_available')
    assert row['status']=='FAIL'


def test_source_modifier_and_limited_block_machining_are_exact():
    with _connect() as connection:
        modifier=connection.execute("SELECT id FROM machining_modifiers WHERE active=1 AND usable=1 AND kind='o-ring-groove' AND unit_system='metric' ORDER BY id LIMIT 1").fetchone()[0]
    base=Design(name='Plain',block=dict(length=100,width=80,height=40,material='QA'),
        features=[dict(id='M1',kind='mounting',face='top',u=50,v=40,diameter=8,depth=12)])
    design=Design.model_validate({**base.model_dump(),
        'features':[{**base.features[0].model_dump(),'machining_modifiers':[{'modifier_id':modifier,'start':0}]}],
        'engravings':[dict(id='ENG_P',face='top',u=20,v=20,text='P',text_height=5,depth=.3)],
        'block_modifiers':[dict(id='CUT1',kind='rectangular-cutout',face='front',u=20,v=20,width=12,height=8,depth=4,rotation=15),
                           dict(id='CH1',kind='chamfer',face='top',size=1)]})
    validate_references(design)
    plain=build_geometry(base,definitions={},thread_definitions={},modifier_definitions={})
    geometry=build_geometry(design)
    assert geometry.production.isValid() and geometry.production.Volume()<plain.production.Volume()
    assert set(geometry.manufacturing_features)=={'ENG_P','CUT1','CH1'}
    checks=[row for row in validate(design,geometry)['checks'] if row['rule']=='authored_block_machining']
    assert len(checks)==3 and all(row['status']=='PASS' for row in checks)


def test_material_stock_remains_separate_from_finished_geometry():
    material=next(row for row in materials() if row['stock'])
    stock=max(material['stock'],key=lambda row:row['size_1_mm']*row['size_2_mm'])
    width=min(stock['size_1_mm'],stock['size_2_mm'])-2
    height=max(stock['size_1_mm'],stock['size_2_mm'])-2
    design=Design(name='Stock QA',block=dict(length=100,width=width,height=height,material=material['display_name'],
        material_id=material['id'],stock_id=stock['id'],stock_dimensions=[110,min(stock['size_1_mm'],stock['size_2_mm']),max(stock['size_1_mm'],stock['size_2_mm'])],
        machining_allowance=[0,min(stock['allowance_1_mm'],stock['allowance_2_mm']),max(stock['allowance_1_mm'],stock['allowance_2_mm'])],
        stock_excess=[5,1,1]))
    validate_references(design)
    geometry=build_geometry(design,definitions={},thread_definitions={},modifier_definitions={})
    assert geometry.block.BoundingBox().xlen==pytest.approx(100)
    assert design.block.stock_dimensions[0]==110
    assert design.block.machining_allowance != design.block.stock_excess


def test_mixed_standard_catalog_and_cross_native_tool_resolution():
    threads=search_threads('',usable_only=True,limit=500)
    metric=next(row for row in threads if row['display_name']=='M12x1.75-6H' and row['tap_diameter_mm']==pytest.approx(10.25))
    unified=next(row for row in threads if row['display_name']=='3/8-16 UNC-2B' and row['tap_diameter_mm']==pytest.approx(7.9502))
    assert metric['normalized_family']=='Metric' and unified['normalized_family']=='UNC'
    assert select_tool(metric['tap_diameter_mm'],25,unit='inch',exact_diameter=True)['unit_system']=='metric'
    assert select_tool(unified['tap_diameter_mm'],25,unit='metric',exact_diameter=True)['unit_system']=='inch'
    ports=search_definitions(kind='port_definition',status='usable',limit=500)['items']
    assert any(row['normalized_family']=='BSPP' and row['unit_system']=='inch' for row in ports)
    assert any(row['normalized_family']=='NPT' and row['unit_system']=='metric' for row in ports)
    assert normalized_port_family(dict(name='1/4-18 NPTF',family='',thread_spec='1/4-18 NPTF'))=='NPTF'


def test_definition_operations_use_matching_source_tool_types():
    definition=next(get_definition(row['id']) for row in search_definitions(kind='port_definition',status='usable',limit=500)['items']
                    if row['name']=='G 1/4' and row['unit_system']=='inch')
    resolved=resolve_machining_tools(definition,'metric')
    assert resolved and resolved[0]['tool_type']=='drill' and resolved[0]['tool']
    unavailable=definition.model_copy(update={'machining':[dict(operation="C'BORE",tool_type='flat-bottom-drill',diameter_mm=123.456,depth_mm=5)]})
    missing=resolve_machining_tools(unavailable,'metric')[0]
    assert missing['tool_type']=='flat-bottom-drill' and missing['status']=='UNRESOLVED'
    spotface=definition.model_copy(update={'machining':[dict(operation='SPOTFACE',tool_type='spotface',diameter_mm=123.456,depth_mm=5)]})
    missing=resolve_machining_tools(spotface,'inch')[0]
    assert missing['tool_type']=='spotface' and missing['status']=='UNRESOLVED'
    counterbore=next(get_definition(row['id']) for row in search_definitions(kind='port_definition',status='usable',limit=500)['items']
                     if row['name']=='#10 SAE [7/8] [M]')
    assert any(row['tool_type']=='flat-bottom-drill' and row['status']=='RESOLVED'
               for row in resolve_machining_tools(counterbore,'inch'))


def test_source_boundary_expands_ai_placement_clearance():
    definition=next(get_definition(row['id']) for row in search_definitions(kind='cavity',status='usable',limit=7000)['items']
                    if get_definition(row['id']).boundaries)
    assert definition_planar_radius(definition)>definition.clearance_diameter/2


def test_blocked_cavity_interface_remains_exact_but_is_not_routed():
    definition=get_definition(CAVITY_ID)
    connected,blocked=[zone.id for zone in definition.zones]
    design=Design(name='Blocked terminal QA',block=dict(length=100,width=80,height=60,material='QA'),
        features=[dict(id='CV1',kind='cavity',face='top',u=50,v=40,cavity_id=CAVITY_ID,
                       interface_nets={connected:'P'})],
        nets=[dict(id='P',members=[f'CV1:{connected}'],routing='manual',diameter=8)],
        schematic_intent=dict(components=[dict(id='COMP1',placement_id='CV1',cavity_id=CAVITY_ID,
            expected_interfaces=[connected,blocked],interface_nets={connected:'P'},
            interface_dispositions={connected:'connected',blocked:'blocked'})]))
    validate_references(design)
    geometry=build_geometry(design)
    assert f'CV1:{connected}' in geometry.nodes and f'CV1:{blocked}' not in geometry.nodes
    conformance=next(row for row in validate(design,geometry)['checks'] if row['rule']=='schematic_conformance')
    assert conformance['status']=='PASS'


def test_metric_and_inch_projects_keep_mixed_standard_ids_cad_tools_and_drawing(tmp_path):
    bsp=get_definition('cav_4b8ba46ae1ccb0e430e4')  # inch-native G 1/4 BSPP
    npt=get_definition('cav_5c2f2ebdebe3d0105e41')  # metric-native 1/2-14 NPT
    threads=search_threads('',usable_only=True,limit=500)
    choose=lambda name,tap:next(row for row in threads if row['display_name']==name and row['tap_diameter_mm']==pytest.approx(tap))
    unified=choose('3/8-16 UNC-2B',7.9502)
    for context,metric_thread in [('metric',choose('M12x1.75-6H',10.25)),('inch',choose('M10x1.5-6H',8.0))]:
        design=Design(name=f'Mixed standards {context}',project_context=context,
            block=dict(length=180,width=120,height=100,material='QA'),features=[
                dict(id='CV',kind='cavity',face='top',u=90,v=60,cavity_id=CAVITY_ID,interface_nets={'port2':'P','port1':'T'}),
                dict(id='P',kind='port',face='left',u=60,v=79,circuit='P',port_definition_id=bsp.id),
                dict(id='T',kind='port',face='right',u=60,v=48,circuit='T',port_definition_id=npt.id),
                dict(id='MH1',kind='mounting',face='top',u=30,v=20,mounting_mode='threaded',
                     thread_definition_id=metric_thread['id'],thread_depth=16,depth=20),
                dict(id='MH2',kind='mounting',face='top',u=150,v=100,mounting_mode='threaded',
                     thread_definition_id=unified['id'],thread_depth=16,depth=20)],
            nets=[dict(id='P',members=['P','CV:port2'],routing='automatic',diameter=8),
                  dict(id='T',members=['T','CV:port1'],routing='automatic',diameter=8)])
        validate_references(design)
        reopened=Design.model_validate(design.model_dump())
        assert [f.definition or f.thread_definition_id for f in reopened.features]==[
            CAVITY_ID,bsp.id,npt.id,metric_thread['id'],unified['id']]
        resolved,_=resolve_design(reopened,exact=False)
        geometry=build_geometry(resolved);authorize_generated_contacts(resolved,geometry)
        assert validate(resolved,geometry)['status']=='PASS'
        folder=tmp_path/context;folder.mkdir()
        manufacturing_outputs(resolved,geometry,folder)
        manufacturing=json.loads((folder/'manufacturing.json').read_text(encoding='utf-8'))
        profiles={row['feature']:row for row in manufacturing['machining_profiles']}
        assert profiles['MH1']['selected_tool']['unit_system']=='metric'
        assert profiles['MH2']['selected_tool']['unit_system']=='inch'
        callouts={row['feature']:row['pmc_specification'] for row in anchors(
            {'resolved':resolved.model_dump(),'manufacturing':manufacturing})[1]}
        assert 'G 1/4' in callouts['P'] and '1/2-14 NPT' in callouts['T']
        assert metric_thread['display_name'] in callouts['MH1'] and '3/8-16 UNC-2B' in callouts['MH2']


def test_source_slenderness_policy_controls_when_stricter_than_project_rule():
    design=Design(name='Slenderness QA',block=dict(length=80,width=80,height=120,material='QA'),
        rules=dict(max_depth_diameter_ratio=30),features=[dict(id='MH1',kind='mounting',face='top',u=40,v=40,diameter=4,depth=104)])
    row=next(row for row in validate(design,build_geometry(design))['checks'] if row['rule']=='drill_reach')
    assert row['required']==25 and 'MDTools manufacturing policy' in row['message'] and row['status']=='WARNING'
