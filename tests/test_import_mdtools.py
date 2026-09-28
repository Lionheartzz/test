"""Real MDTools rows pin the source's axial and machining semantics."""
import json
from pathlib import Path

import pytest

from manifold.import_mdtools import DEFAULT_SOURCE, active_revision, interfaces, machining, number, profile, profile_datum


@pytest.fixture(scope='module')
def source_rows():
    rows = {}
    with (DEFAULT_SOURCE/'cavities_master.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            identity = json.loads(line)
            revision = active_revision(identity)
            if revision:
                rows[(identity['display_family'], identity['display_name'], identity['unit'])] = (identity, revision['row'])
    return rows


def test_sequential_profile_cone_and_step_roles():
    row = dict(CavityType='CV', Circle0Dia=30, Circle0Depth=1,
               Circle1Dia=20, Circle1Depth=0, Circle1Angle=45,
               Circle2Dia=10, Circle2Depth=10, Circle2Angle=90,
               Circle12Dia=5, Circle12Depth=100, Circle12Angle=59,
               NumberofPorts=1, Port1Depth=10, Port1Diameter=0,
               MachineOperation1='FORM', MachineDia1='$STEP2', MachineDepth1='$STEP2',
               MachineOperation2='DRILL', MachineDia2='$STEP12', MachineDepth2='$STEP12')
    stages, cuts = profile(row, 1)
    for stage, expected in zip(stages, [(0,1,30),(1,6,20),(6,11,10)],strict=True):
        assert (stage['start'],stage['end'],stage['diameter'])==pytest.approx(expected)
    cone=next(p for p in cuts if p['kind']=='cone')
    assert (cone['start'],cone['end'])==pytest.approx((1,6))
    assert all(p['source_ref']!='circle12' for p in cuts)
    assert interfaces(row, cuts, 1, stages=stages)[0]['start'] == pytest.approx(6)
    assert interfaces(row, cuts, 1, stages=stages)[0]['end'] == pytest.approx(11)
    ops=machining(row)
    assert ops[0]['depth_mm']==11 and ops[0]['geometry_role']=='cut'
    assert ops[1]['depth_mm']==100 and ops[1]['geometry_role']=='pilot_reference'
    inch_stages, inch_cuts=profile(row,25.4)
    assert inch_stages[-1]['end']==pytest.approx(11*25.4)
    assert inch_cuts[1]['diameter']==pytest.approx(20*25.4)


def test_port_and_footprint_pilots_are_fixed_cuts():
    row=dict(CavityType='Port',Circle0Dia=20,Circle0Depth=5,
             Circle1Dia=10,Circle1Depth=12,Circle12Dia=6,Circle12Depth=20,Circle12Angle=59)
    stages, cuts=profile(row,1)
    assert profile_datum(row,1)==0
    assert [(p['source_ref'],p['start'],p['end']) for p in cuts if p['kind']=='cylinder'] == [
        ('circle0',0,5),('circle1',0,12),('circle12',12,20)]
    assert cuts[-1]['kind']=='cone' and cuts[-1]['start']==20
    assert stages[-1]['end']>20
    with (DEFAULT_SOURCE/'footprints_master.jsonl').open(encoding='utf-8') as handle:
        child=next(json.loads(line) for line in handle if '"port_application":"bh1"' in line and '"active":true' in line)
    unit={item.get('unit') for item in child['sources'] if item.get('unit')}.pop()
    scale=25.4 if unit=='inch' else 1.0
    offset_u=float(child['row'].get('CavityXDim') or 0)*scale
    offset_v=float(child['row'].get('CavityYDim') or 0)*scale
    _, cuts=profile(child['row'],scale,offset_u=offset_u,offset_v=offset_v)
    assert cuts and all(p['offset_u']==offset_u and p['offset_v']==offset_v for p in cuts)
    assert any(p['source_ref']=='circle12' for p in cuts)
    with (DEFAULT_SOURCE/'footprints_master.jsonl').open(encoding='utf-8') as handle:
        fractional=next(json.loads(line) for line in handle
                        if '"Circle12Dia":"25/64"' in line and '"active":true' in line)
    assert fractional['row']['CavityType']=='BH'
    _,fractional_cuts=profile(fractional['row'],25.4)
    assert any(p['source_ref']=='circle12' and p['diameter']==pytest.approx(25/64*25.4)
               for p in fractional_cuts)


def test_source_inch_fractions_are_executable_dimensions(source_rows):
    assert number('7/8')==0.875
    assert number('1-1/16')==1.0625
    assert number('25/64')==0.390625
    assert number(' ') is None
    _,row=source_rows['HydraForce','VC10-2','inch']
    stages,cuts=profile(row,25.4)
    assert any(p['diameter']==pytest.approx(0.875*25.4) for p in cuts)
    assert stages and all(a['end']==pytest.approx(b['start']) for a,b in zip(stages,stages[1:]))


def test_source_depth_bounds_a_nominal_cone_angle():
    row=dict(CavityType='CV',Circle0Dia=22,Circle0Depth=0,
             Circle1Dia=20,Circle1Depth=0,Circle1Angle=15,
             Circle2Dia=10,Circle2Depth=2,Circle2Angle=90,
             MachineOperation1='FORM',MachineDepth1='$STEP2')
    stages,cuts=profile(row,1)
    transition=next(p for p in cuts if p['kind']=='cone')
    assert (transition['start'],transition['end'])==pytest.approx((0,2))
    assert stages[-1]['end']==pytest.approx(2)
    assert machining(row)[0]['depth_mm']==pytest.approx(2)


@pytest.mark.parametrize('index',range(13))
@pytest.mark.parametrize('scale',[1.0,25.4])
def test_every_step_operand_uses_its_source_axis_and_unit(index,scale):
    row={'CavityType':'CV','Circle0Dia':30,'Circle0Depth':1,
         'Circle12Dia':5,'Circle12Depth':30,
         'MachineOperation1':'DRILL','MachineDia1':f'$STEP{index}',
         'MachineDepth1':f'$STEP{index}'}
    row.update({f'Circle{i}Dia':30-i for i in range(1,12)})
    row.update({f'Circle{i}Depth':i for i in range(1,12)})
    operation=machining(row,scale)[0]
    expected_depth=(1 if index==0 else 30 if index==12 else index+1)*scale
    expected_diameter=(30 if index==0 else 5 if index==12 else 30-index)*scale
    assert operation['depth_mm']==pytest.approx(expected_depth)
    assert operation['diameter_mm']==pytest.approx(expected_diameter)
    assert operation['geometry_role']==('pilot_reference' if index==12 else 'cut')


def test_real_sun_t10a_excludes_socket_envelope_and_unbounded_pilot(source_rows):
    _,row=source_rows['Sun Hydraulics','T-10A','metric']
    stages,cuts=profile(row,1)
    assert profile_datum(row,1)==pytest.approx(float(row['LSMinDepth']))
    assert not any(p['source_ref'] in ('circle0','circle12') for p in cuts)
    assert [(round(s['end'],3),round(s['diameter'],3)) for s in stages] == [
        (7.935,25.4),(11.93,21.85),(12.363,21.16),(16.22,20.66),
        (24.63,20.0),(44.645,18.59),(51.8,17.48)]
    assert stages[-1]['end']==pytest.approx(float(row['Circle7Depth'])+float(row['LSMinDepth']))
    assert max(s['diameter'] for s in stages)==pytest.approx(float(row['Circle1Dia']))
    assert number(row['Circle12Dia'])<=number(row['MaxCircle12Dia'])
    zones=interfaces(row,cuts,1,stages=stages)
    assert [(z['id'],round(z['start'],3),round(z['end'],3)) for z in zones] == [
        ('port1',44.645,51.8),('port2',21.445,43.675)]
    ops=machining(row)
    assert [o['geometry_role'] for o in ops]==['pilot_reference','cut','tool_clearance']
    assert [o['depth_mm'] for o in ops]==pytest.approx([127.0,11.93,33.32])
    _,inch=source_rows['Sun Hydraulics','T-10A','inch']
    inch_stages,_=profile(inch,25.4)
    assert inch_stages[-1]['end']==pytest.approx(stages[-1]['end'],abs=.03)
    assert inch_stages[0]['diameter']==pytest.approx(stages[0]['diameter'],abs=.02)


def test_deep_circle0_is_not_an_axial_datum_for_special_port(source_rows):
    _,row=source_rows['BSP Ports-ISO 1179-1','BSP PORT G 1/4-19 SPECIAL','metric']
    assert profile_datum(row,1)==0
    stages,cuts=profile(row,1)
    assert stages[-1]['end']==pytest.approx(12)
    assert max(p['end'] for p in cuts)==pytest.approx(12)
    assert machining(row)[1]['depth_mm']==pytest.approx(6)


@pytest.mark.parametrize('family,name,unit,last_circle,expected',[
    ('Sun Hydraulics','SC-08-04','inch',6,
     [(2.891,20.599),(14.3,19.05),(18.864,17.45),(33.085,15.875),(47.262,14.275),(56.596,12.7)]),
    ('HydraForce','HVC06-2','inch',5,
     [(0.787,24.867),(4.103,15.697),(13.487,14.287),(18.552,12.903),(26.187,11.125),(26.441,7.645)]),
    ('Parker','CAVT11A','inch',6,
     [(24.765,25.4),(41.3,21.844),(45.593,20.65),(54.0,19.99),(69.24,18.593),(76.429,17.475)]),
    ('Danfoss (Comatrol)','CP04-2','inch',4,
     [(0.787,15.875),(3.648,12.433),(12.217,11.112),(18.46,9.792),(32.981,7.95)]),
    ('Eaton','A12196','inch',7,
     [(0.305,35.992),(1.889,33.274),(13.31,31.445),(17.528,29.261),(29.312,27.0),
      (34.643,25.502),(56.594,24.536),(65.616,23.038)]),
    ('Bucher Hydraulics','AA','inch',2,
     [(1.012,20.168),(14.853,18.999),(26.589,18.009)]),
    ('Rexroth','003','inch',5,
     [(0.762,42.012),(5.716,34.544),(5.893,33.503),(20.752,33.249),(40.767,30.759),(52.895,28.042)]),
    ('HYDAC','03030','metric',4,
     [(1.0,15.0),(17.0,9.8),(19.684,8.79),(24.0,8.0),(30.0,7.8)]),
])
def test_real_manufacturer_profile_and_step_alignment(source_rows,family,name,unit,last_circle,expected):
    identity,row=source_rows[family,name,unit]
    scale=25.4 if unit=='inch' else 1.0
    stages,cuts=profile(row,scale)
    assert stages and cuts and stages[0]['start']==0
    assert [(round(s['end'],3),round(s['diameter'],3)) for s in stages]==expected
    assert all(s['end']>s['start'] and s['diameter']>0 for s in stages)
    assert all(a['end']==pytest.approx(b['start']) and a['diameter']>=b['diameter']
               for a,b in zip(stages,stages[1:]))
    assert not any(p['source_ref']=='circle12' for p in cuts)
    assert stages[-1]['end'] < float(row['Circle12Depth'])*scale+1e-6
    assert any(p['kind']=='cone' for p in cuts)
    datum=profile_datum(row,scale)
    for cone in (p for p in cuts if p['kind']=='cone'):
        index=int(cone['source_ref'].removeprefix('circle'))
        source_depth=float(row[f'Circle{index}Depth'])*scale+(datum if 1<=index<=11 else 0)
        assert cone['start']==pytest.approx(source_depth,abs=.02)
        assert cone['end']>cone['start']
        following=next((i for i in range(index+1,12) if row.get(f'Circle{i}Dia') not in (None,'')),None)
        if following is not None:
            assert cone['end']<=float(row[f'Circle{following}Depth'])*scale+datum+.02
    source_end=float(row[f'Circle{last_circle}Depth'])*scale+datum
    assert stages[-1]['end']>=source_end-1e-6
    assert stages[-1]['end']-source_end < max(p['diameter'] for p in cuts)
    assert max(p['end'] for p in cuts)==pytest.approx(stages[-1]['end'])
    expected_diameters=[float(row[f'Circle{i}Dia'])*scale for i in range(1,last_circle+1)
                        if row.get(f'Circle{i}Dia') not in (None,'')]
    assert expected_diameters==sorted(expected_diameters,reverse=True)
    assert any(p['diameter']==pytest.approx(expected_diameters[0]) for p in cuts)
    for operation in machining(row,scale):
        raw=str(operation['depth'] or '').upper()
        if raw.startswith('$STEP') and raw[5:].isdigit() and 1<=int(raw[5:])<=11:
            source=float(row[f'Circle{int(raw[5:])}Depth'])*scale+datum
            assert operation['depth_mm']==pytest.approx(source)
