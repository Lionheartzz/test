"""Focused API coverage for designs produced by the five-step Guided flow."""
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from manifold.engineering_db import initialize_schema
from manifold.schema import Design
from manifold.server import app


HEADERS = {'X-PMC-Request': 'local-console'}


@pytest.fixture
def guided_database(tmp_path, monkeypatch):
    path = tmp_path / 'engineering.db'
    with sqlite3.connect(path) as connection:
        initialize_schema(connection)
        stages = json.dumps([dict(start=0, end=20, diameter=10)])
        primitives = json.dumps([dict(kind='cylinder', source_ref='source-backed fixture', start=0,
                                      end=20, diameter=10, end_diameter=0, inner_diameter=0,
                                      offset_u=0, offset_v=0)])
        for cavity_id, usable in [('CAV_ONE', 1), ('CAV_TWO', 1), ('CAV_UNUSABLE', 0)]:
            connection.execute('INSERT INTO cavities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                               (cavity_id, cavity_id, 'fixture', 'metric', 'Fixture', '', stages,
                                primitives, '[]', '[]', 16, 20, usable,
                                '' if usable else 'Source geometry is incomplete', 1))
            for index, net in enumerate(('P', 'T', 'A', 'B')):
                connection.execute('INSERT INTO cavity_interfaces VALUES (?,?,?,?,?,?,?,?)',
                                   (cavity_id, net, 0, 20, 10, index, 0, 1))
        connection.execute('INSERT INTO external_port_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           ('PORT_MASTER', 'Source-backed port', 'fixture', 'metric', 'Fixture', 'M10',
                            stages, primitives, '[]', '[]', json.dumps(dict(id='port', start=0, end=20,
                            diameter=10)), 16, 20, 1, '', 1, None))
        connection.execute('INSERT INTO materials VALUES (?,?,?,?)',
                           ('MAT_SOURCE', 'Source-backed material', 'metal', 1))
    monkeypatch.setenv('PMC_ENGINEERING_DB', str(path))
    return path


def guided_design():
    ports = []
    for index, net in enumerate(('P', 'T', 'A', 'B'), start=1):
        source_backed = net in ('P', 'A')
        port = dict(id=f'PORT{index}', kind='port', face='front', u=20*index, v=50,
                    circuit=net, size='M10' if source_backed else 'Custom',
                    port_type='Source-backed port' if source_backed else 'Custom straight bore',
                    diameter=10 if source_backed else 12, depth=20 if source_backed else 16,
                    clearance_diameter=16 if source_backed else 20)
        if source_backed:
            port.update(port_definition_id='PORT_MASTER', clearance_height=20, tip_angle=180)
        ports.append(port)
    cavities = [dict(id=f'CV{index}', kind='cavity', face='top', u=45*index, v=75,
                     cavity_id=cavity_id, interface_nets={net:net for net in ('P', 'T', 'A', 'B')})
                for index, cavity_id in enumerate(('CAV_ONE', 'CAV_TWO'), start=1)]
    return Design.model_validate(dict(schema_version=2, name='Guided fixture', units='mm',
        project_context='metric', block=dict(length=160, width=150, height=150,
                                             material='Source-backed material', material_id='MAT_SOURCE'),
        features=ports+cavities,
        nets=[dict(id=net, label=net, routing='automatic', diameter=8, color='#ef5959')
              for net in ('P', 'T', 'A', 'B')],
        origin=dict(method='manual', notes='Guided setup'),
        review_items=[dict(id=f'PORT_SPEC_{index}', kind='component', subject=f'PORT{index}',
                           description='Review one-off port machining', status='open')
                      for index in (2, 4)]))


def test_guided_style_design_with_material_ports_and_two_cavities_is_accepted(guided_database):
    design = guided_design()
    response = TestClient(app).post('/api/check-design', json=design.model_dump(), headers=HEADERS)
    assert response.status_code == 200
    checked = response.json()
    assert checked['block']['material_id'] == 'MAT_SOURCE'
    assert checked['block']['material'] == 'Source-backed material'
    assert not any(key.startswith('stock') or key == 'machining_allowance' for key in checked['block'])
    assert len(checked['features']) == 6
    assert {feature['port_definition_id'] for feature in checked['features'][:4]
            if feature['port_definition_id']} == {'PORT_MASTER'}
    assert all(set(feature['interface_nets']) == {'P', 'T', 'A', 'B'}
               for feature in checked['features'][4:])


def test_guided_reference_error_is_a_useful_422(guided_database):
    design = guided_design().model_dump()
    design['features'][4]['cavity_id'] = 'CAV_UNUSABLE'
    response = TestClient(app).post('/api/check-design', json=design, headers=HEADERS)
    assert response.status_code == 422
    assert 'CV1: cavity is unusable: Source geometry is incomplete' in response.json()['detail']


def test_unexpected_check_design_failure_is_not_swallowed(guided_database, monkeypatch):
    from manifold import engineering_db

    def programmer_error(_design):
        raise TypeError('unexpected programmer error')

    monkeypatch.setattr(engineering_db, 'validate_references', programmer_error)
    response = TestClient(app, raise_server_exceptions=False).post(
        '/api/check-design', json=guided_design().model_dump(), headers=HEADERS)
    assert response.status_code == 500
