import json
import sqlite3

import pytest

from manifold.engineering_db import (
    compatible,
    get_definition,
    initialize_schema,
    validate_database,
    validate_references,
)
from manifold.geometry import build_geometry
from manifold.import_mdtools import import_database
from manifold.project_migration import convert
from manifold.routing import alternative_proposals
from manifold.schema import Design
from manifold.validation import validate


def seed_database(path):
    connection=sqlite3.connect(path)
    initialize_schema(connection)
    stages=json.dumps([dict(start=0,end=20,diameter=10)],separators=(',',':'))
    primitives=json.dumps([dict(kind='cylinder',source_ref='test',start=0,end=20,diameter=10,
        end_diameter=0,inner_diameter=0,offset_u=0,offset_v=0)],separators=(',',':'))
    connection.execute('INSERT INTO cavities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        ('CAV_A','Test cavity','Test family','metric','PMC','',stages,primitives,'[]','[{"operation":"bore"}]',16,20,1,'',1))
    connection.execute('INSERT INTO cavity_interfaces VALUES (?,?,?,?,?,?,?,?)',
        ('CAV_A','port1',10,20,10,0,0,1))
    connection.execute('INSERT INTO cartridges VALUES (?,?,?,?,?,?)',
        ('CART_OK','PMC','MODEL-OK','Test valve','{}',1))
    connection.execute('INSERT INTO cartridges VALUES (?,?,?,?,?,?)',
        ('CART_BAD','PMC','MODEL-BAD','Test valve','{}',1))
    connection.execute('INSERT INTO cartridge_cavities VALUES (?,?,?)',('CART_OK','CAV_A',1))
    connection.commit();connection.close()


@pytest.fixture
def engineering_db(tmp_path,monkeypatch):
    path=tmp_path/'pmc_engineering.db';seed_database(path)
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(path))
    return path


def cavity_only(cartridge_id=None,schematic_intent=None):
    return Design.model_validate(dict(schema_version=2,name='Cavity only',
        block=dict(length=100,width=100,height=100,material='Aluminium'),
        features=[
            dict(id='CV1',kind='cavity',face='top',u=50,v=50,cavity_id='CAV_A',
                 cartridge_id=cartridge_id,interface_nets={'port1':'P'}),
            dict(id='P1',kind='port',face='front',u=50,v=85,circuit='P',diameter=8,depth=60,
                 tip_angle=180,clearance_diameter=16,clearance_height=10,size='test',connects_to=['CV1:port1']),
        ],schematic_intent=schematic_intent))


def test_cavity_only_has_no_cartridge_or_schematic_failure_and_exact_geometry_runs(engineering_db):
    design=cavity_only()
    validate_references(design)
    assert design.features[0].cartridge_id is None
    assert design.schematic_intent is None and design.components==[]
    report=validate(design,build_geometry(design))
    assert report['status']=='PASS'
    assert not any(row['rule']=='schematic_conformance' for row in report['checks'])
    assert any(row['rule']=='solid_validity' and row['status']=='PASS' for row in report['checks'])
    payload=design.model_dump()
    assert 'library' not in payload and 'library_resources' not in payload


def test_optional_cartridge_uses_explicit_many_to_many_relationship(engineering_db):
    validate_references(cavity_only('CART_OK'))
    assert compatible('CART_OK','CAV_A')
    assert not compatible('CART_BAD','CAV_A')
    with pytest.raises(ValueError,match='not compatible'):
        validate_references(cavity_only('CART_BAD'))
    validate_references(cavity_only(None))


def test_schematic_conformance_exists_only_when_intent_exists(engineering_db):
    intent=dict(assets=[],components=[dict(id='COMP1',label='Valve intent',function='directional valve',
        cartridge_id=None,cavity_id='CAV_A',interface_nets={'port1':'P'},placement_id='CV1')])
    with_intent=cavity_only(schematic_intent=intent)
    report=validate(with_intent,build_geometry(with_intent))
    rows=[row for row in report['checks'] if row['rule']=='schematic_conformance']
    assert len(rows)==1 and rows[0]['status']=='PASS' and rows[0]['actual'] is True
    without_intent=with_intent.model_copy(update={'schematic_intent':None})
    report=validate(without_intent,build_geometry(without_intent))
    assert not any(row['rule']=='schematic_conformance' for row in report['checks'])


def test_non_routing_failure_produces_no_route_candidates(engineering_db):
    design=cavity_only()
    report=dict(counts={'FAIL':1,'WARNING':0},checks=[dict(
        rule='engineering_review',status='FAIL',items=['REVIEW_1'],actual='open',required='resolved')])
    assert alternative_proposals(design,design,[],report,{'P'},set())==[]


def test_runtime_database_is_required_and_never_created(tmp_path,monkeypatch):
    missing=tmp_path/'missing.db';monkeypatch.setenv('PMC_ENGINEERING_DB',str(missing))
    with pytest.raises(RuntimeError,match='missing'):
        validate_database()
    assert not missing.exists()
    invalid=tmp_path/'invalid.db';invalid.write_text('not sqlite',encoding='utf-8')
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(invalid))
    with pytest.raises(RuntimeError,match='invalid'):
        validate_database()


def test_zero_footprint_import_uses_cavity_engineering_data(tmp_path,monkeypatch):
    source=tmp_path/'merged';source.mkdir()
    revision_id='rev_1'
    identity=dict(canonical_id='ZERO_FP',display_name='Zero footprint cavity',display_family='QA',unit='metric',
        active_revision_id=revision_id,revisions=[dict(revision_id=revision_id,active=True,row={
            'CavityType':'CV','Circle0Dia':10,'Circle0Depth':20,'NumberofPorts':1,
            'Port1Depth':15,'Port1Diameter':4,'MachineOperation1':'Bore','MachineTool1':'T10'})])
    (source/'cavities_master.jsonl').write_text(json.dumps(identity)+'\n',encoding='utf-8')
    (source/'footprints_master.jsonl').write_text('',encoding='utf-8')
    destination=tmp_path/'imported.db'
    report=import_database(source,destination)
    assert report['zero_footprint']==1 and report['unusable']==0 and report['cavities']==1
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(destination))
    definition=get_definition('ZERO_FP')
    assert definition.usable and definition.stages and definition.cutting_primitives


def test_schema1_migration_drops_fake_intent_and_ai_evidence(engineering_db):
    raw=dict(schema_version=1,name='Legacy cavity-only',units='mm',project_context='metric',
        block=dict(length=100,width=100,height=100,material='Aluminium'),library=[],features=[],
        nets=[dict(id='P',label='P',members=['COMP1'],routing='automatic',diameter=8)],
        schematics=[],components=[dict(id='COMP1',label='Fake component',status='unconfirmed')],
        review_items=[dict(id='REVIEW_CV1',kind='component',subject='Fake review',description='Template state',status='open')],
        origin=dict(method='manual',notes='Legacy project',ai_trace={'claims':[{'id':'old'}]}))
    from manifold.engineering_db import _connect
    with _connect(engineering_db,writable=True) as connection:
        migrated=convert(raw,connection)
    assert migrated['schema_version']==2
    assert migrated['schematic_intent'] is None
    assert migrated['review_items']==[]
    assert migrated['origin']['method']=='manual' and migrated['origin']['notes']=='Legacy project'
    assert not any(migrated['origin'][key] for key in ('author','provider','model'))
    assert 'members' not in migrated['nets'][0]
    assert 'library' not in migrated and 'components' not in migrated and 'ai_trace' not in migrated['origin']
