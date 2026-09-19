import json

import pytest

from manifold.drawing.generate import anchors
from manifold.engineering_db import (
    _connect,
    get_definition,
    materials,
    search_threads,
    select_tool,
    validate_references,
)
from manifold.geometry import build_geometry
from manifold.import_mdtools import thread_record
from manifold.manufacturing import manufacturing_outputs
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
        machining_allowance=[5,1,1]))
    validate_references(design)
    geometry=build_geometry(design,definitions={},thread_definitions={},modifier_definitions={})
    assert geometry.block.BoundingBox().xlen==pytest.approx(100)
    assert design.block.stock_dimensions[0]==110
