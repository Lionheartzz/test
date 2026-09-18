import json
import sqlite3

import pytest

from manifold.engineering_db import (
    compatible,
    create_custom_cavity,
    create_custom_external_port,
    database_path,
    get_definition,
    initialize_schema,
    search_definitions,
    set_custom_active,
    validate_database,
    validate_references,
)
from manifold.presentation import feature_name, identity_name
from manifold.geometry import build_geometry
from manifold.import_mdtools import import_database
from manifold.project_migration import convert
from manifold.migrate_saved_projects import migrate
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


def test_explicit_validation_connection_owns_compatibility_lookup(engineering_db,monkeypatch):
    import manifold.engineering_db as module
    connection=sqlite3.connect(engineering_db);connection.row_factory=sqlite3.Row
    monkeypatch.setattr(module,'_connect',lambda *args,**kwargs:pytest.fail('validation escaped its explicit transaction'))
    try:validate_references(cavity_only('CART_OK'),connection=connection)
    finally:connection.close()


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


def test_manual_schematic_expected_interface_can_be_unmapped_then_bound(engineering_db):
    intent=dict(assets=[],components=[dict(id='COMP1',label='Manual valve',function='control',
        cavity_id='CAV_A',expected_interfaces=['port1'],interface_nets={},placement_id='CV1')])
    design=cavity_only(schematic_intent=intent)
    report=validate(design,build_geometry(design))
    assert next(row for row in report['checks'] if row['rule']=='schematic_conformance')['status']=='FAIL'
    design.schematic_intent.components[0].interface_nets={'port1':'P'}
    report=validate(design,build_geometry(design))
    assert next(row for row in report['checks'] if row['rule']=='schematic_conformance')['status']=='PASS'


def test_manual_schematic_conformance_accepts_real_non_port_interface_ids(engineering_db):
    with sqlite3.connect(engineering_db) as connection:
        connection.execute("""INSERT INTO cavities
            SELECT 'CAV_PTAB','Four-interface cavity',family,unit_system,manufacturer,thread_spec,
                   stages_json,primitives_json,boundaries_json,machining_json,clearance_diameter,
                   clearance_height,usable,unusable_reason,active FROM cavities WHERE id='CAV_A'""")
        for interface_id,offset_u,offset_v in [('P',-2,-2),('T',2,-2),('A',-2,2),('B',2,2)]:
            connection.execute('INSERT INTO cavity_interfaces VALUES (?,?,?,?,?,?,?,?)',
                ('CAV_PTAB',interface_id,10,20,2,offset_u,offset_v,1))
    mappings={interface_id:interface_id for interface_id in ('P','T','A','B')}
    design=Design.model_validate(dict(schema_version=2,name='Manual PTAB intent',
        block=dict(length=100,width=100,height=100,material='Aluminium'),
        features=[dict(id='CV1',kind='cavity',face='top',u=50,v=50,cavity_id='CAV_PTAB',
                       cartridge_id=None,interface_nets=mappings)],
        schematic_intent=dict(assets=[],components=[dict(id='COMP1',label='Manual valve',function='control',
            cavity_id='CAV_PTAB',expected_interfaces=list(mappings),interface_nets=mappings,placement_id='CV1')])))
    validate_references(design)
    report=validate(design,build_geometry(design))
    row=next(row for row in report['checks'] if row['rule']=='schematic_conformance')
    assert row['status']=='PASS' and row['actual'] is True


def test_engineering_review_owned_by_cavity_produces_no_route_candidates(engineering_db):
    design=cavity_only()
    report=dict(counts={'FAIL':1,'WARNING':0},checks=[dict(
        rule='engineering_review',status='FAIL',items=['REVIEW_1','CV1'],actual='open',required='resolved')])
    assert alternative_proposals(design,design,[],report,{'P'},set())==[]


def test_cavity_collision_produces_no_route_candidates(engineering_db):
    design=cavity_only()
    raw=design.model_dump()
    raw['features'].append(dict(id='CV2',kind='cavity',face='top',u=65,v=50,cavity_id='CAV_A',
                                cartridge_id=None,interface_nets={'port1':'P'}))
    design=Design.model_validate(raw)
    report=dict(counts={'FAIL':1,'WARNING':0},checks=[dict(
        rule='cavity_collision',status='FAIL',items=['CV1','CV2'],actual=1,required=0)])
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


def test_relative_database_path_is_application_root_relative(tmp_path,monkeypatch):
    import manifold.engineering_db as module
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setenv('PMC_ENGINEERING_DB','configured/engineering.db')
    assert database_path()==(tmp_path/'configured'/'engineering.db').resolve()


def test_custom_cavity_is_new_searchable_sqlite_definition(engineering_db):
    master=get_definition('CAV_A')
    custom=create_custom_cavity(master.model_copy(update={'label':'Operator T-10A custom','unit_system':'custom'}))
    assert custom.id.startswith('custom_') and custom.id!='CAV_A'
    assert get_definition('CAV_A').label=='Test cavity'
    assert get_definition(custom.id).label=='Operator T-10A custom'
    found=search_definitions(query='Operator T-10A',unit='custom',status='usable')
    assert [row['id'] for row in found['items']]==[custom.id]
    design=cavity_only().model_copy(deep=True);design.features[0].cavity_id=custom.id
    validate_references(design)
    set_custom_active(custom.id,False)
    assert search_definitions(query='Operator T-10A',unit='custom')['total']==0
    validate_references(design)
    set_custom_active(custom.id,True)
    assert search_definitions(query='Operator T-10A',unit='custom')['total']==1


def test_custom_external_port_and_custom_archive_use_sqlite_active_state(engineering_db):
    cavity=get_definition('CAV_A')
    source=cavity.model_copy(update={'kind':'external-port','label':'Reusable SAE port'})
    saved=create_custom_external_port(source)
    assert saved.id.startswith('custom_port_')
    assert get_definition(saved.id).kind=='external-port'
    assert search_definitions(query='Reusable SAE',kind='port_definition')['items'][0]['id']==saved.id
    design=cavity_only().model_copy(deep=True);design.features[1].port_definition_id=saved.id
    validate_references(design)
    set_custom_active(saved.id,False)
    assert search_definitions(query='Reusable SAE',kind='port_definition')['total']==0
    assert get_definition(saved.id,include_inactive=True).active is False
    validate_references(design)
    set_custom_active(saved.id,True)
    assert get_definition(saved.id).active is True
    with pytest.raises(ValueError,match='Imported master'):
        set_custom_active('CAV_A',False)


def test_python_presentation_matches_owner_aware_multi_cavity_routes():
    design={'nets':[{'id':'NET_P','label':'P'}],'features':[
        {'id':'CV1','kind':'cavity','interface_nets':{'port1':'NET_P'}},
        {'id':'CV2','kind':'cavity','interface_nets':{'port1':'NET_P'}},
        {'id':'R-hash-1','kind':'drilling','route_net':'NET_P','connects_to':['CV1:port1']},
        {'id':'R-hash-2','kind':'drilling','route_net':'NET_P','connects_to':['CV1:port1','R-hash-1']},
        {'id':'R-hash-3','kind':'drilling','route_net':'NET_P','connects_to':['CV2:port1']},
        {'id':'R-hash-4','kind':'drilling','route_net':'NET_P','connects_to':['R-hash-1','R-hash-3']},
    ]}
    assert identity_name(design,'NET_P')=='P'
    assert [feature_name(design,row) for row in design['features'][2:]]==['CV1-P1','CV1-P2','CV2-P1','P1']


def test_net_color_and_label_survive_project_json(engineering_db):
    design=cavity_only();design.nets[0].label='Pressure supply';design.nets[0].color='#12Ab34'
    restored=Design.model_validate_json(design.model_dump_json())
    assert restored.nets[0].label=='Pressure supply' and restored.nets[0].color=='#12Ab34'


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
    assert definition.family=='QA' and definition.manufacturer==''


def test_import_admission_and_source_boundaries_are_conservative(tmp_path,monkeypatch):
    source=tmp_path/'merged';source.mkdir()
    def identity(identifier, row, **revision_fields):
        revision_id='rev_'+identifier
        return dict(canonical_id=identifier,display_name=identifier,display_family='Family only',unit='metric',
                    active_revision_id=revision_id,revisions=[dict(revision_id=revision_id,active=True,row=row,**revision_fields)])
    base=dict(CavityType='CV',Circle0Dia=10,Circle0Depth=20,NumberofPorts=1,
              Port1Depth=15,Port1Diameter=4,MachineOperation1='Bore')
    records=[
        identity('SUN_DATUM',base|{'IsSunCavity':True,'LSMinDepth':4,'LSCircleNumber':1}),
        identity('MISSING_WINDOW',base|{'NumberofPorts':2}),
        identity('SPECIAL_CUT',base,special_feature_refs={'undercuts':[{'index':1}]}),
        identity('BOUNDARY_OK',base),identity('BOUNDARY_BAD',base),
    ]
    (source/'cavities_master.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records),encoding='utf-8')
    def footprint(identifier,envelope):
        return dict(footprint_id='fp_'+identifier,cavity_revision_id='rev_'+identifier,port_application='bh1',active=True,
                    row=dict(CavityType='BH',Circle0Dia=4,Circle0Depth=10,CavityXDim=0,CavityYDim=0,
                             EnvelopDimensions=envelope,PortApplicationName='BH1'))
    footprints=[footprint('BOUNDARY_OK','L;0;0;20;0;L;20;0;20;10;L;20;10;0;10;L;0;10;0;0;'),
                footprint('BOUNDARY_BAD','L;0;0;20;0;')]
    (source/'footprints_master.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in footprints),encoding='utf-8')
    destination=tmp_path/'imported.db';report=import_database(source,destination)
    assert report['unusable']==4
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(destination))
    assert 'Sun/LS installation datum' in get_definition('SUN_DATUM').unusable_reason
    assert 'hydraulic windows' in get_definition('MISSING_WINDOW').unusable_reason
    assert 'special cut' in get_definition('SPECIAL_CUT').unusable_reason
    boundary=get_definition('BOUNDARY_OK').boundaries[0]
    assert boundary.points==[(0,0),(20,0),(20,10),(0,10)]
    assert get_definition('BOUNDARY_OK').usable
    assert 'mounting boundary' in get_definition('BOUNDARY_BAD').unusable_reason


def test_inactive_definition_resolves_for_existing_project_but_not_selection(engineering_db):
    with sqlite3.connect(engineering_db) as connection:
        connection.execute("UPDATE cavities SET active=0 WHERE id='CAV_A'")
    with pytest.raises(ValueError,match='inactive'):
        get_definition('CAV_A')
    validate_references(cavity_only())
    assert search_definitions(kind='cavity')['total']==0


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


def test_reusable_t10a_metric_variant_recovers_as_distinct_sqlite_definition(engineering_db):
    variant=dict(id='OLD_T10A_M',label='T-10A [M]',manufacturer='Sun Hydraulics',thread_note='M20x1.5',native={'record':{'unit_system':'metric'}},
        stages=[dict(start=0,end=24,diameter=12)],zones=[dict(id='port1',start=12,end=24,diameter=10)],
        cutting_primitives=[],boundaries=[],machining=[],clearance_diameter=18,clearance_height=24)
    raw=dict(schema_version=1,name='Legacy reusable custom',units='mm',project_context='metric',
        block=dict(length=100,width=100,height=100,material='Aluminium'),library=[variant],
        features=[dict(id='CV1',kind='cavity',face='top',u=50,v=50,definition='OLD_T10A_M',circuits={'port1':'P'})],
        nets=[dict(id='P',label='P',routing='automatic',diameter=8)],constraints={},rules={})
    from manifold.engineering_db import _connect
    with _connect(engineering_db,writable=True) as connection,connection:
        migrated=convert(raw,connection)
    recovered=migrated['features'][0]['cavity_id']
    assert recovered.startswith('legacy_') and recovered!='CAV_A'
    assert get_definition(recovered).label=='T-10A [M]' and get_definition(recovered).unit_system=='metric'
    assert recovered in {row['id'] for row in search_definitions(query='T-10A [M]',scope='custom')['items']}


def test_failed_project_migration_rolls_back_legacy_definition(engineering_db,tmp_path):
    source=tmp_path/'saved';source.mkdir()
    legacy=dict(id='LEGACY_NEW',label='Legacy new',manufacturer='',thread_note='',
                stages=[dict(start=0,end=12,diameter=11)],zones=[dict(id='port1',start=8,end=12,diameter=11)],
                cutting_primitives=[],boundaries=[],machining=[],clearance_diameter=12,clearance_height=12)
    design=dict(schema_version=1,name='Invalid migrated project',units='mm',project_context='metric',
                block=dict(length=100,width=100,height=100,material='Aluminium'),library=[legacy],
                features=[dict(id='CV1',kind='cavity',face='top',u=50,v=50,definition='LEGACY_NEW',circuits={})],
                nets=[],constraints={},rules={})
    (source/'project.json').write_text(json.dumps(dict(design=design,build=None)),encoding='utf-8')
    with sqlite3.connect(engineering_db) as connection:
        before=connection.execute("SELECT count(*) FROM cavities WHERE id LIKE 'legacy_%'").fetchone()[0]
    with pytest.raises(ValueError,match='assign a hydraulic net'):
        migrate(source,tmp_path/'staging',tmp_path/'backup')
    with sqlite3.connect(engineering_db) as connection:
        after=connection.execute("SELECT count(*) FROM cavities WHERE id LIKE 'legacy_%'").fetchone()[0]
    assert after==before
