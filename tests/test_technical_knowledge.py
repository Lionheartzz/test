import csv
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from manifold import engineering_db, technical_schema
from manifold.import_technical_knowledge import Package, REQUIRED, REV1_REQUIRED, integrate, preserved_tables
from manifold.server import app
from manifold.technical_knowledge import summary


def csv_data(rows, fields=None):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields or list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def package_files():
    files = {name: b'' for name in REQUIRED}
    for name in files:
        if name.endswith('.csv'):
            files[name] = b'placeholder\n'
        elif name.endswith('.json'):
            files[name] = b'{}'
    targets = [dict(manufacturer='Maker', cartridge_part_number=model,
                    technical_disposition=status, research_stage='RESEARCH_COMPLETE')
               for model, status in [('NORMAL', 'PARTIAL_CONFIRMED'), ('AMB', 'IDENTITY_AMBIGUOUS'), ('REL', 'RELATION_SOURCE_ONLY')]]
    files['normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv'] = csv_data(targets)
    files['normalized/GLOBAL_FULL_PART_TO_BASE_MODEL.csv'] = csv_data([dict(manufacturer='Maker', full_part_number='NORMAL', base_model_or_spec_sheet='BASE')])
    evidence = [dict(evidence_id=eid, manufacturer='Maker', entity_id='NORMAL', property=prop,
                     raw_value=value, raw_unit='L/min', normalized_value=value, normalized_unit='L/min',
                     scope=scope, scope_original=scope, source_id='SOURCE', source_url='https://example.test/data',
                     confidence='0.9', evidence_text='Exact source quote', source_title='Technical sheet')
                for eid, prop, value, scope in [('MAX', 'maximum_flow', 30, 'FULL_PART_NUMBER'),
                                                 ('CAP', 'capacity', 20, 'BASE_MODEL'),
                                                 ('MAX2', 'maximum_flow', 40, 'FULL_PART_NUMBER')]]
    files['evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl'] = b''.join((json.dumps(row)+'\n').encode() for row in evidence)
    files['normalized/GLOBAL_CARTRIDGE_TECHNICAL_MASTER.jsonl'] = (json.dumps(dict(manufacturer='Maker', full_part_number='NORMAL', base_model='BASE', evidence_ids=['MAX','CAP','MAX2']))+'\n').encode()
    files['sources/GLOBAL_SOURCE_REGISTRY.csv'] = csv_data([dict(source_id='SOURCE', canonical_url='https://example.test/data', source_name='Technical sheet')])
    files['conflicts/GLOBAL_CARTRIDGE_CONFLICTS.csv'] = csv_data([dict(manufacturer='Maker', entity_id='NORMAL', property='maximum_flow', conflict_type='VALUE_CONFLICT',
        evidence_a='30', evidence_b='40', resolution='OPEN; no preferred value', evidence_link_status='LINKED', evidence_a_ids_json='["MAX"]', evidence_b_ids_json='["MAX2"]')])
    disposition_counts = {'PARTIAL_CONFIRMED':1,'IDENTITY_AMBIGUOUS':1,'RELATION_SOURCE_ONLY':1}
    files['evidence/SOURCE_REVIEW_EVIDENCE.jsonl'] = (json.dumps(dict(evidence_id='REVIEW',entity_id='NORMAL',manufacturer='Maker',property='source_review_disposition',raw_value='Reviewed source',scope='FULL_PART_NUMBER',source_id='SOURCE',evidence_class='SOURCE_REGISTRY_INSPECTION_RECORD'))+'\n').encode()
    for name in ['reports/GLOBAL_COVERAGE.json', 'reports/GLOBAL_CONVERGENCE_AUDIT.json']:
        files[name] = json.dumps(dict(result='RESEARCH_CONVERGED', target_identities=3, target_disposition_counts=disposition_counts, conflict_rows=1)).encode()
    files['reports/GLOBAL_FIELD_GAP_LEDGER.csv'] = csv_data([dict(manufacturer='Maker', cartridge_part_number='NORMAL', field_group=group, field_gap_state=state)
        for group,state in [('seals','NOT_REPORTED'),('electrical','NOT_APPLICABLE')]])
    material = dict(material_id='MAT-C45', canonical_grade='C45', aliases=['EN C45'], temper_condition='Normalized', material_family='Steel', collection_status='PARTIAL', evidence_ids=['YIELD'])
    files['material/MATERIAL_MASTER.jsonl'] = (json.dumps(material)+'\n').encode()
    files['material/MATERIAL_PROPERTY_EVIDENCE.jsonl'] = (json.dumps(dict(evidence_id='YIELD',entity_id='MAT-C45', property='yield_strength',raw_value=300,raw_unit='MPa',scope='GRADE_CONDITION_FORM',scope_class='GRADE_CONDITION_FORM',source_id='MS',condition='Normalized'))+'\n').encode()
    files['material/MATERIAL_SOURCE_REGISTRY.csv'] = csv_data([dict(source_id='MS',url='https://example.test/stock',title='Material producer')])
    files['material/MATERIAL_SURFACE_TREATMENT.jsonl'] = (json.dumps(dict(material='C45',treatment='nitriding',status='CONDITIONAL'))+'\n').encode()
    files['material/MATERIAL_CONFLICTS.csv'] = b'entity_id,property,conflict_type,evidence_a_ids_json,evidence_b_ids_json\n'
    stocks = [dict(material='C45',product_form='Angle',width='10',height='10',length='100',diameter='',unit='mm',stock_code='',notes='LISTED_SIZE; thickness '+t,supplier='Supplier',country='SG',source_url='https://example.test/stock',retrieved_date='2026-10-01') for t in ('2','3')]
    files['material/MATERIAL_STOCK_MASTER.csv'] = csv_data(stocks)
    stock_evidence = [dict(evidence_id='COLLIDING_STOCK_ID',entity_type='MATERIAL_STOCK_LISTING',entity_id='C45',property='stock_listing',
        raw_value=json.dumps({key:row[key] for key in ('product_form','width','height','length','diameter','unit','stock_code','notes')}),scope='PRODUCT_FORM',source_id='MS',source_url=row['source_url']) for row in stocks]
    files['material/MATERIAL_STOCK_EVIDENCE.jsonl'] = b''.join((json.dumps(row)+'\n').encode() for row in stock_evidence)
    return files


def write_package(path, files):
    manifest = [dict(archive_path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in files.items()]
    with zipfile.ZipFile(path,'w') as archive:
        for name,data in files.items():
            archive.writestr(name,data)
        archive.writestr('MANIFEST_SHA256.csv',csv_data(manifest))


@pytest.fixture
def inputs(tmp_path):
    source=tmp_path/'production.db'
    with sqlite3.connect(source) as db:
        engineering_db._initialize_base_schema(db)
        db.executemany('INSERT INTO cartridges VALUES (?,?,?,?,?,?)',[(model,'Maker',model,'','{}',1) for model in ('NORMAL','AMB','REL')])
        db.execute('INSERT INTO cavities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('CAV','Cavity','Maker','metric','Maker','','[]','[]','[]','[]',10,20,0,'Geometry incomplete',1))
        db.execute('INSERT INTO cartridge_cavities VALUES (?,?,?)',('NORMAL','CAV',1))
        db.execute('INSERT INTO materials VALUES (?,?,?,?)',('RUNTIME','Steel','Steel',1))
        db.execute('INSERT INTO material_stock VALUES (?,?,?,?,?,?,?,?)',('STOCK','RUNTIME','metric',100,100,2,2,1))
    package=tmp_path/'technical.zip';write_package(package,package_files())
    rev1=tmp_path/'rev1.zip'
    with zipfile.ZipFile(rev1,'w') as archive:
        for name in REV1_REQUIRED:
            archive.writestr(name,'relation_id\nRELATION\n' if name.endswith('relations.csv') else '{}')
    return source,package,rev1


def test_explicit_upgrade_preserves_domains_and_deterministic_keys(inputs,tmp_path,monkeypatch):
    source,package,rev1=inputs;before=source.read_bytes()
    outputs=[tmp_path/'first.db',tmp_path/'second.db']
    reports=[integrate(source,package,rev1,path) for path in outputs]
    assert source.read_bytes()==before
    assert reports[0]['preserved_before']==reports[0]['preserved_after']
    assert reports[0]['stock_stable_internal_ids']==2
    with sqlite3.connect(outputs[0]) as first,sqlite3.connect(outputs[1]) as second:
        for name in technical_schema.TABLES:
            if name=='technical_import_batches':continue
            assert first.execute(f'SELECT * FROM {name} ORDER BY 1,2').fetchall()==second.execute(f'SELECT * FROM {name} ORDER BY 1,2').fetchall()
        assert first.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert first.execute('SELECT count(*) FROM material_supplier_stock').fetchone()[0]==2
        assert first.execute('SELECT count(*) FROM material_stock').fetchone()[0]==1
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(outputs[0]))
    assert engineering_db.validate_database()['schema_version']==4
    assert engineering_db.compatible('NORMAL','CAV')
    assert engineering_db.compatible_cavity_ids('NORMAL')==['CAV']
    assert engineering_db.compatible_logical_cavities('NORMAL')==[dict(cavity_id='CAV',logical_id='physical:CAV')]
    assert engineering_db.search_cartridges('BASE')['total']==0
    assert engineering_db.search_cartridges('BASE',technical=True)['total']==1
    normal=summary('cartridge','NORMAL')
    assert {r['property'] for r in normal['values']}=={'maximum_flow','capacity'}
    assert {r['status'] for r in normal['field_status']}=={'NOT_REPORTED','NOT_APPLICABLE'}
    assert all(r['preferred_evidence_id'] is None for r in normal['values'])
    assert summary('cartridge','AMB')['values']==[]
    assert summary('cartridge','REL')['values']==[]
    with pytest.raises(ValueError,match='new staging'):
        integrate(source,package,rev1,outputs[0])


@pytest.mark.parametrize('problem',['reference','source','scope','duplicate','manifest','audit'])
def test_validation_failure_never_creates_staging(inputs,tmp_path,problem):
    source,package,rev1=inputs;files=package_files()
    if problem=='reference':files['normalized/GLOBAL_CARTRIDGE_TECHNICAL_MASTER.jsonl']=b'{"evidence_ids":["MISSING"]}\n'
    elif problem=='source':files['sources/GLOBAL_SOURCE_REGISTRY.csv']=b'source_id,canonical_url\nOTHER,https://example.test/data\n'
    elif problem=='scope':files['evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl']=files['evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl'].replace(b'FULL_PART_NUMBER',b'BAD_SCOPE')
    elif problem=='duplicate':files['evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl']+=files['evidence/GLOBAL_CARTRIDGE_PARAMETER_EVIDENCE.jsonl'].splitlines()[0].replace(b'30',b'99')+b'\n'
    elif problem=='audit':files['reports/GLOBAL_COVERAGE.json']=b'{"target_identities":4,"target_disposition_counts":{}}'
    write_package(package,files)
    if problem=='manifest':
        with zipfile.ZipFile(package,'a') as archive:archive.writestr('UNREGISTERED.txt','x')
    before=source.read_bytes();output=tmp_path/'blocked.db'
    with pytest.raises(ValueError):integrate(source,package,rev1,output)
    assert not output.exists() and source.read_bytes()==before


def test_read_only_api_pagination_conflicts_and_material_stock(inputs,tmp_path,monkeypatch):
    source,package,rev1=inputs;output=tmp_path/'staging.db';integrate(source,package,rev1,output)
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(output));before=output.read_bytes()
    with TestClient(app) as client:
        data=client.get('/api/cartridges/NORMAL/technical').json()
        assert data['execution_permission'] is False and data['counts']['conflicts']==1
        page=client.get('/api/cartridges/NORMAL/technical/evidence?property=maximum_flow&limit=1&offset=1').json()
        assert page['total']==2 and len(page['items'])==1 and page['items'][0]['sources']
        conflicts=client.get('/api/cartridges/NORMAL/technical/conflicts').json()['items']
        assert conflicts[0]['sides']['a']['items'][0]['raw_value']=='30'
        assert conflicts[0]['preferred_evidence_id'] is None
        assert client.get('/api/cartridges/NORMAL/technical/evidence?limit=1000').status_code==422
        assert client.get('/api/cartridges/ABSENT/technical').status_code==404
        assert client.get('/api/materials').json()['items'][0]['id']=='RUNTIME'
        assert client.get('/api/materials/technical').json()['items'][0]['id']=='MAT-C45'
        material=client.get('/api/materials/technical/MAT-C45').json()
        assert material['engineering_stock']==[] and material['supplier_stock_count']==2
        assert material['surface_treatments'][0]['status']=='CONDITIONAL'
        stock=client.get('/api/materials/technical/MAT-C45/stock?limit=1&offset=1').json()
        assert stock['total']==2 and stock['items'][0]['availability']=='LISTED_SIZE'
    assert output.read_bytes()==before


def test_runtime_refuses_v3_without_migration(inputs):
    source,_,_=inputs
    with pytest.raises(RuntimeError,match='version 3'):engineering_db.validate_database(source)
    with sqlite3.connect(source) as db:assert db.execute('PRAGMA user_version').fetchone()[0]==3


def test_verified_manufacturer_alias_does_not_merge_existing_cartridge_ids(inputs,tmp_path):
    source,package,rev1=inputs
    with sqlite3.connect(source) as db:
        db.execute('INSERT INTO cartridges VALUES (?,?,?,?,?,?)',('ALIAS_NORMAL','Maker Alias','NORMAL','','{}',1))
    files=package_files()
    targets=list(csv.DictReader(io.StringIO(files['normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv'].decode())))
    targets.append(targets[0] | {'manufacturer':'Maker Alias'})
    files['normalized/GLOBAL_CARTRIDGE_TARGET_DISPOSITION.csv']=csv_data(targets)
    files['normalized/MANUFACTURER_ALIAS_INDEX.csv']=csv_data([dict(manufacturer_alias='Maker Alias',canonical_manufacturer='Maker',status='VERIFIED_ALIAS')])
    for name in ['reports/GLOBAL_COVERAGE.json','reports/GLOBAL_CONVERGENCE_AUDIT.json']:
        value=json.loads(files[name]);value['target_identities']=4;value['target_disposition_counts']['PARTIAL_CONFIRMED']=2;files[name]=json.dumps(value).encode()
    write_package(package,files);output=tmp_path/'aliases.db';integrate(source,package,rev1,output)
    with sqlite3.connect(output) as db:
        assert db.execute("SELECT id FROM technical_identities WHERE domain='cartridge' ORDER BY id").fetchall()==[('ALIAS_NORMAL',),('AMB',),('NORMAL',),('REL',)]
        assert db.execute('SELECT manufacturer,model FROM cartridges WHERE id=?',('ALIAS_NORMAL',)).fetchone()==('Maker Alias','NORMAL')
        assert db.execute("SELECT count(*) FROM technical_identity_evidence WHERE identity_id='ALIAS_NORMAL'").fetchone()[0]>=3


def test_ambiguous_stock_reference_is_rejected_instead_of_selecting_a_thickness(inputs,tmp_path):
    source,package,rev1=inputs;files=package_files()
    files['material/MATERIAL_CONFLICTS.csv']=csv_data([dict(entity_id='MAT-C45',property='stock_listing',conflict_type='VALUE_CONFLICT',resolution='OPEN',evidence_link_status='LINKED',evidence_a_ids_json='["COLLIDING_STOCK_ID"]',evidence_b_ids_json='["YIELD"]')])
    write_package(package,files);output=tmp_path/'ambiguous.db'
    with pytest.raises(ValueError,match='Ambiguous stock evidence'):
        integrate(source,package,rev1,output)
    assert not output.exists()


def test_empty_v4_baseline_can_be_integrated_but_populated_source_is_refused(inputs,tmp_path):
    source,package,rev1=inputs
    with sqlite3.connect(source) as db:technical_schema.initialize(db)
    output=tmp_path/'v4-import.db';report=integrate(source,package,rev1,output)
    assert report['source_schema']==4
    with pytest.raises(ValueError,match='already contains technical knowledge'):
        integrate(output,package,rev1,tmp_path/'refused.db')
    assert not (tmp_path/'refused.db').exists()
