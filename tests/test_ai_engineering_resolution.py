"""Small source-linked SQLite fixtures; never changes the production master."""
import copy
import json
import sqlite3
from pathlib import Path
import pytest
from manifold import engineering_db as db
from manifold.ai_design import generation,library_resolution as lib
from manifold.ai_design.cartridge_identity import resolve_cartridge_identity
from manifold.ai_design.models import TaskInput
from manifold.ai_design.generation_models import GenerationOptions

def insert(connection,table,**values):
    columns=connection.execute('PRAGMA table_info('+table+')').fetchall()
    row={r[1]:'' for r in columns if r[3] and r[4] is None and r[2]=='TEXT'};row.update(values)
    connection.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',list(row.values()))

@pytest.fixture
def source_db(tmp_path,monkeypatch):
    path=tmp_path/'master.db';connection=sqlite3.connect(path);db.initialize_schema(connection)
    insert(connection,'cartridges',id='CART',manufacturer='SourceCo',model='BASE')
    geometry=dict(stages_json=json.dumps([dict(start=0,end=20,diameter=12)]),primitives_json='[]',boundaries_json='[]',machining_json='[]',clearance_diameter=20,clearance_height=10,usable=1)
    insert(connection,'cavities',id='CAV',name='Source cavity',family='Source',unit_system='metric',**geometry)
    for i,(a,b) in enumerate(((5,9),(11,15)),1):insert(connection,'cavity_interfaces',cavity_id='CAV',interface_id='port'+str(i),start=a,end=b,diameter=8)
    insert(connection,'cartridge_cavities',cartridge_id='CART',cavity_id='CAV')
    insert(connection,'technical_identities',domain='cartridge',id='CART',cartridge_id='CART',full_part_number='BASE',base_model='BASE',manufacturer_original='SourceCo',disposition='PARTIAL_CONFIRMED',original_json='{}')
    insert(connection,'technical_sources',domain='cartridge',id='SRC',title='Source identity',url='https://example.test/source',sha256='a'*64,original_json='{}')
    insert(connection,'technical_evidence',domain='cartridge',id='ALIAS',entity_id='CART',manufacturer='SourceCo',property='full_part_number',raw_value='BASE-OPTION',normalized_value_json='"BASE-OPTION"',scope='FULL_PART_NUMBER',scope_original='FULL_PART_NUMBER',applicable_option='BASE-OPTION',evidence_class='identity',original_json='{}')
    insert(connection,'technical_evidence_sources',domain='cartridge',evidence_id='ALIAS',source_id='SRC')
    insert(connection,'technical_identity_evidence',domain='cartridge',identity_id='CART',evidence_id='ALIAS',attribution='EXPLICIT_SOURCE_IDENTITY')
    insert(connection,'thread_definitions',id='THREAD',display_name='G1/4-19',family='BSPP',nominal_size='1/4',pitch_tpi='G1/4-19',tap_diameter_mm=11,unit_system='inch',usable=1)
    def port(identifier='PORT',unit='metric',depth=20,label='G1/4',family='ISO 1179-1',thread='THREAD',spec='G1/4-19'):
        insert(connection,'external_port_definitions',id=identifier,name=label,family=family,unit_system=unit,thread_spec=spec,thread_definition_id=thread,
            interface_json=json.dumps(dict(id='port1',start=10,end=depth,diameter=12,clip_to_cut=True)),**{**geometry,'stages_json':json.dumps([dict(start=0,end=depth,diameter=12)])})
        connection.commit()
    port();connection.commit();monkeypatch.setenv('PMC_ENGINEERING_DB',str(path))
    yield connection,port,geometry
    connection.close()

def result(model='BASE',spec='1/4" BSPP'):
    return dict(components=[dict(id='C1',port_ids=['CP','CA'],label='Valve',facts={'model':model,'working_pressure':280,'passage_diameter':12},identity_valid={'model':True})],
        ports=[dict(id='CP',component_id='C1',label='1',facts={},disposition='connected'),dict(id='CA',component_id='C1',label='2',facts={},disposition='connected'),
               dict(id='P',component_id=None,label='P',facts={'port_specification':spec},disposition='connected'),dict(id='A',component_id=None,label='A',facts={'port_specification':spec},disposition='connected')],
        nets=[dict(id='NP',label='P',members=['CP','P']),dict(id='NA',label='A',members=['CA','A'])],design_intent=[],unresolved=[],warnings=[])

@pytest.mark.parametrize('model,method',[('BASE','exact_model'),('BASE-OPTION','source_backed_alias')])
def test_exact_and_source_backed_ordering_alias_auto_resolve(source_db,model,method):
    r=result(model);before=copy.deepcopy(r);plan=generation.prepare(TaskInput(title='QA'),r,GenerationOptions())
    assert not plan['blocked'] and plan['components'][0]['automatic']
    assert plan['components'][0]['resolution']['identity']['method']==method
    assert plan['components'][0]['cartridge_id']=='CART' and r==before
    assert plan['components'][0]['recognized_facts']['working_pressure']==280

def test_no_string_only_suffix_guessing(source_db):
    assert resolve_cartridge_identity('BASE-UNSOURCED')['code']=='cartridge_identity_missing'

def test_explicit_source_base_identity_resolves_without_suffix_guessing(source_db):
    c,_,_=source_db;c.execute("UPDATE cartridges SET model='ORDER-CODE'");c.execute("UPDATE technical_identities SET full_part_number='ORDER-CODE'");c.commit()
    assert resolve_cartridge_identity('BASE')['method']=='source_backed_base_identity'

def test_unsourced_alias_and_generic_product_family_do_not_become_model_identity(source_db):
    c,_,_=source_db;c.execute("UPDATE technical_identities SET original_json=?,product_family='Valve family'",(json.dumps({'aliases':['UNSOURCED']}),));c.execute('DELETE FROM technical_evidence_sources');c.commit()
    assert resolve_cartridge_identity('UNSOURCED')['code']=='cartridge_identity_missing'
    assert resolve_cartridge_identity('Valve family')['code']=='cartridge_identity_missing'

def test_conflicted_source_alias_is_not_automatically_admitted(source_db):
    c,_,_=source_db;insert(c,'technical_conflicts',domain='cartridge',id='CONFLICT',entity_id='CART',property='alias',resolution='UNRESOLVED',original_json='{}')
    insert(c,'technical_identity_conflicts',domain='cartridge',identity_id='CART',conflict_id='CONFLICT');c.commit()
    assert resolve_cartridge_identity('BASE-OPTION')['code']=='cartridge_identity_missing'

def test_missing_relation_is_separate_from_identity(source_db):
    c,_,_=source_db;c.execute('DELETE FROM cartridge_cavities');c.commit()
    plan=generation.prepare(TaskInput(title='QA'),result(),GenerationOptions())
    assert plan['components'][0]['resolution']['code']=='relationship_missing'
    assert 'Cartridge resolved' in plan['blocked'][0]

def test_distinct_logical_cavities_remain_ambiguous(source_db):
    c,_,g=source_db;insert(c,'cavities',id='OTHER',name='Other cavity',unit_system='metric',**g);insert(c,'cavity_interfaces',cavity_id='OTHER',interface_id='port1',start=5,end=9,diameter=8)
    insert(c,'cartridge_cavities',cartridge_id='CART',cavity_id='OTHER');c.commit()
    plan=generation.prepare(TaskInput(title='QA'),result(),GenerationOptions())
    assert plan['components'][0]['resolution']['code']=='ambiguous_cavities'

def test_ambiguous_cartridge_identity_never_picks_first(source_db):
    c,_,_=source_db;insert(c,'cartridges',id='OTHER',manufacturer='OtherCo',model='BASE');c.commit()
    assert resolve_cartridge_identity('BASE')['code']=='cartridge_identity_ambiguous'
    assert resolve_cartridge_identity('BASE','SourceCo')['cartridge_id']=='CART'

@pytest.mark.parametrize('spec',['1/4 BSPP','1/4" BSPP','G1/4','G 1/4','G 1 / 4'])
def test_supported_spec_spellings_resolve_same_semantics(source_db,spec):
    resolution=lib.resolve_port_specification(TaskInput(title='QA'),spec)
    assert resolution['code']=='resolved' and resolution['logical_count']==1 and resolution['canonical']['key']=='db:PORT'

def test_equivalent_physical_rows_collapse_and_canonical_is_deterministic(source_db):
    _,port,_=source_db;port('DUPLICATE',unit='inch',label='G 1/4-19')
    resolution=lib.resolve_port_specification(TaskInput(title='QA',project_context='metric'),'G1/4')
    assert resolution['physical_count']==2 and resolution['logical_count']==1 and resolution['canonical']['key']=='db:PORT'
    assert lib.resolve_port_specification(TaskInput(title='QA',project_context='inch'),'G1/4')['canonical']['key']=='db:DUPLICATE'

def test_different_geometry_remains_one_grouped_engineering_decision(source_db):
    _,port,_=source_db;port('DIFFERENT',depth=25)
    plan=generation.prepare(TaskInput(title='QA'),result(),GenerationOptions())
    assert len(plan['port_groups'])==1 and len(plan['blocked'])==1
    assert 'applies to P, A' in plan['blocked'][0]
    resolution=plan['external'][0]['resolution'];assert resolution is plan['external'][1]['resolution'] and resolution['logical_count']==2

def test_explicit_group_choice_and_manual_cavity_binding_remain_supported(source_db):
    _,port,_=source_db;port('DIFFERENT',depth=25)
    cavity=db.get_definition('CAV');selected=lib.summary('db:PORT',db.get_definition('PORT'))
    options=GenerationOptions(bindings={'C1':dict(definition_key='db:CAV',definition_sha256=lib.digest(cavity.model_dump()),zone_ports={'port1':'CP','port2':'CA'},decision='Explicit cavity choice.')},
        port_definitions={i:dict(definition_key=selected['key'],definition_sha256=selected['sha256'],decision='Explicit common port choice.') for i in ('P','A')})
    plan=generation.prepare(TaskInput(title='QA'),result(),options)
    assert not plan['blocked'] and plan['components'][0]['resolution']['code']=='manual_selection'
    assert all(p['definition'].id=='PORT' for p in plan['external'])

@pytest.mark.parametrize('preference',['metric','inch'])
def test_unit_preference_does_not_exclude_executable_other_native_standard(source_db,preference):
    assert lib.resolve_port_specification(TaskInput(title='QA',project_context=preference),'G1/4')['code']=='resolved'

def test_imperial_preference_accepts_source_metric_iso_port(source_db):
    _,port,_=source_db;port('ISO',family='ISO 6149',thread=None,label='M10x1',spec='ISO 6149 M10x1')
    assert lib.resolve_port_specification(TaskInput(title='QA',project_context='inch'),'ISO 6149 M10x1')['canonical']['key']=='db:ISO'

def test_sealing_family_and_explicit_thread_pitch_are_not_collapsed(source_db):
    _,port,_=source_db;port('SEALING',family='Other sealing port')
    assert lib.resolve_port_specification(TaskInput(title='QA'),'G1/4')['logical_count']==2
    assert lib.resolve_port_specification(TaskInput(title='QA'),'G1/4-20 BSPP')['physical_count']==0

def test_different_required_tap_classes_are_not_equivalent(source_db):
    c,port,_=source_db;port('OTHER')
    for key,thread_class in (('PORT','6H'),('OTHER','6G')):
        c.execute('UPDATE external_port_definitions SET machining_json=? WHERE id=?',
            (json.dumps([{'operation':'TAP','diameter':'G1/4-'+thread_class,'depth_mm':14}]),key))
    c.commit();assert lib.resolve_port_specification(TaskInput(title='QA'),'G1/4')['logical_count']==2

def test_geometry_and_unit_diagnostics_remain_distinct(source_db):
    c,_,_=source_db;c.execute("UPDATE cavities SET usable=0");c.commit()
    plan=generation.prepare(TaskInput(title='QA'),result(),GenerationOptions());assert plan['components'][0]['resolution']['code']=='geometry_unusable'
    c.execute("UPDATE cavities SET usable=1,unit_system='inch'");c.commit()
    plan=generation.prepare(TaskInput(title='QA'),result(),GenerationOptions());assert plan['components'][0]['resolution']['code']=='unit_context_unavailable'

def test_explicit_standard_cannot_be_replaced_by_one_off_or_wrong_size(source_db):
    plan=generation.prepare(TaskInput(title='QA'),result(),GenerationOptions(provisional_ports={'P':'Use straight bore.'}))
    assert any('cannot be replaced by a straight bore' in b for b in plan['blocked'])
    r=result(spec='G1/2');selected=lib.summary('db:PORT',db.get_definition('PORT'))
    plan=generation.prepare(TaskInput(title='QA'),r,GenerationOptions(port_definitions={'P':dict(definition_key='db:PORT',definition_sha256=selected['sha256'],decision='Wrong size.')}))
    assert any('conflicts with explicit source standard' in b for b in plan['blocked'])

def test_actual_saved_rdha_lcn_analysis_keeps_recognition_and_groups_p_a_once():
    # Read the current master. No synthetic compatibility or rewritten claims.
    r=json.loads((Path(__file__).parent/'fixtures'/'rdha-lcn-analysis.json').read_text(encoding='utf-8'))['result'];before=copy.deepcopy(r)
    plan=generation.prepare(TaskInput(title='Actual schematic regression'),r,GenerationOptions())
    assert r==before and plan['components'][0]['model']=='RDHA-LCN'
    assert plan['components'][0]['recognized_facts']['crack_pressure']==280
    assert plan['components'][0]['recognized_facts']['P1_bore']==12 and plan['components'][0]['recognized_facts']['P2_bore']==12
    assert len(plan['port_groups'])==1
    group=next(iter(plan['port_groups'].values()));assert group['labels']==['P','A']
    assert group['physical_count']>=group['logical_count']>0
    assert plan['external'][0]['resolution'] is plan['external'][1]['resolution']
    assert sum('G1/4 BSPP' in b for b in plan['blocked'])<=1
    if group['logical_count']>1:assert group['canonical'] is None
