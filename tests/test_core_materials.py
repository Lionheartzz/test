import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from manifold import engineering_db,technical_schema
from manifold.engineering_facts import resolved_engineering_facts
from manifold.import_technical_knowledge import integrate
from manifold.material_supplement import read_supplement
from manifold.server import app
from test_technical_knowledge import inputs,package_files,write_package,csv_data

CORE=Path(__file__).resolve().parents[1]/'data/knowledge/core_materials_2026-10-01.json'


@pytest.fixture
def core_inputs(inputs,tmp_path):
    source,package,rev1=inputs
    data=read_supplement(CORE)[0]
    files=package_files()
    masters=[];evidence=[]
    for row in data['identities']:
        if not row['update']:continue
        mid=row['id'];eid='BASE-'+mid
        masters.append(dict(material_id=mid,canonical_grade=row['canonical_grade'],standard=row['standard'],
            temper_condition=row['temper_condition'],product_form=row['product_form'],material_family=row['material_family'],
            collection_status='PARTIAL',evidence_ids=[eid]))
        evidence.append(dict(evidence_id=eid,entity_id=mid,property='density',raw_value='Unresolved baseline',
            normalized_value=None,normalized_unit='',scope='GRADE',source_id='MS',source_type='PRIMARY_PRODUCER_DATASHEET'))
    files['material/MATERIAL_MASTER.jsonl']=b''.join((json.dumps(r)+'\n').encode() for r in masters)
    files['material/MATERIAL_PROPERTY_EVIDENCE.jsonl']=b''.join((json.dumps(r)+'\n').encode() for r in evidence)
    write_package(package,files)
    data['base_rev2_sha256']=hashlib.sha256(package.read_bytes()).hexdigest()
    supplement=tmp_path/'core.json';supplement.write_text(json.dumps(data),encoding='utf-8')
    with sqlite3.connect(source) as db:
        db.executemany('INSERT INTO materials VALUES (?,?,?,?)',[('material_1','Aluminum','',1),('material_2','DuraBar','',1)])
    return source,package,rev1,supplement


@pytest.fixture
def core_db(core_inputs,tmp_path,monkeypatch):
    source,package,rev1,supplement=core_inputs;path=tmp_path/'core.db'
    integrate(source,package,rev1,path,material_supplement=supplement)
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(path));return path


def digest_rows(db,table,where=''):
    return db.execute(f'SELECT * FROM {table} {where} ORDER BY 1,2').fetchall()


def test_independent_material_rebuilds_keys_facts_stock_and_cartridges_identical(core_inputs,tmp_path,monkeypatch):
    source,package,rev1,supplement=core_inputs;before=source.read_bytes()
    outputs=[tmp_path/'a.db',tmp_path/'b.db']
    reports=[integrate(source,package,rev1,p,material_supplement=supplement) for p in outputs]
    assert source.read_bytes()==before
    assert reports[0]['material_promotion']==reports[1]['material_promotion']
    assert sum(r['selectable'] for r in reports[0]['material_promotion'])==12
    with sqlite3.connect(source) as old,sqlite3.connect(outputs[0]) as a,sqlite3.connect(outputs[1]) as b:
        for table in [*technical_schema.TABLES,'materials','material_stock']:
            if table=='technical_import_batches':continue
            assert digest_rows(a,table)==digest_rows(b,table),table
        assert digest_rows(old,'cartridge_cavities')==digest_rows(a,'cartridge_cavities')
        assert digest_rows(old,'material_stock')==digest_rows(a,'material_stock')
        assert a.execute('PRAGMA user_version').fetchone()[0]==engineering_db.SCHEMA_VERSION
        assert not a.execute('PRAGMA foreign_key_check').fetchall()
    summaries=[]
    for path in outputs:
        monkeypatch.setenv('PMC_ENGINEERING_DB',str(path));summaries.append(engineering_db.materials())
    assert summaries[0]==summaries[1]


def test_normal_selector_hides_generic_legacy_and_old_projects_round_trip(core_db):
    with TestClient(app) as client:
        items=client.get('/api/materials').json()['items']
        assert len(items)==12 and all(r['source_backed'] and r['selectable'] for r in items)
        assert not {'material_1','material_2'}&{r['id'] for r in items}
        complete=client.get('/api/materials?include_legacy=true').json()['items']
        for mid,label in [('material_1','Aluminum'),('material_2','DuraBar')]:
            row=next(r for r in complete if r['id']==mid)
            assert row['legacy_unspecified'] and not row['selectable']
            assert row['display_name'].startswith('Legacy unspecified')
            selected=client.get('/api/materials?current_id='+mid).json()['items']
            assert mid in {r['id'] for r in selected}
            raw=dict(schema_version=2,name='Legacy round trip',block=dict(length=160,width=100,height=100,material=label,material_id=mid))
            loaded=client.post('/api/import-project',headers={'X-PMC-Request':'local-console'},json=raw)
            assert loaded.status_code==200,loaded.text
            exported=client.post('/api/export-project',headers={'X-PMC-Request':'local-console'},json=loaded.json()['design'])
            assert exported.json()['block']['material_id']==mid and exported.json()['block']['material']==label
        research=client.get('/api/materials/technical').json()['items']
        assert len(research)==17
        assert all(r['research_reason'] for r in research if r['research_only'])


def test_resolved_and_unresolved_precise_material_identities(core_db):
    rows=engineering_db.materials();by_research={r['technical_identity_id']:r for r in rows}
    assert {'MAT-CORE-DURABAR-65-45-12','MAT-CORE-DURABAR-80-55-06','MAT-CORE-7075-T651-PLATE'}<=by_research.keys()
    for mid in ('MAT-CORE-DURABAR-65-45-12','MAT-CORE-DURABAR-80-55-06'):
        facts=by_research[mid]['engineering_facts_summary'];identity=facts['identity']
        assert identity['standard']=='ASTM A536' and identity['state']=='As-cast'
        assert identity['product_form']=='Continuous cast bar' and identity['material_family']=='Ductile iron'
        assert facts['facts']['yield_strength']['status']=='SOURCE_BACKED'
        assert facts['facts']['yield_strength']['value_kind']=='MINIMUM'
    assert 'MAT-1045' not in by_research and 'MAT-7075' not in by_research and 'MAT-S355' not in by_research
    assert 'Exact normalized 1045 bar product standard' in resolved_engineering_facts('material','MAT-1045')['identity']['reason']
    assert 'T6 tube/pipe' in resolved_engineering_facts('material','MAT-7075')['identity']['reason']
    assert 'exact suffix/state/product form' in resolved_engineering_facts('material','MAT-S355')['identity']['reason']
    assert not any(r['engineering_facts_summary']['identity']['grade'].startswith('S355') for r in rows)
    assert all(r['engineering_defaults']['allowable_stress_mpa'] is None for r in rows)
    assert all(r['stock']==[] for r in rows)


def test_product_form_size_temperature_and_producer_conditions_do_not_generalize(core_db):
    mid='MAT-CORE-7075-T651-PLATE'
    default=resolved_engineering_facts('material',mid)
    assert default['facts']['yield_strength']['value']==503
    wrong=resolved_engineering_facts('material',mid,context={'product_form':'Extruded bar'})
    assert wrong['facts']['yield_strength']['value'] is None
    assert default['facts']['density']['value'] is None
    assert resolved_engineering_facts('material',mid,context={'temperature_c':20})['facts']['density']['value']==2800
    thin=resolved_engineering_facts('material','MAT-6082',context={'source_profile':'open profile','stock_thickness_mm':4})
    thick=resolved_engineering_facts('material','MAT-6082',context={'source_profile':'open profile','stock_thickness_mm':10})
    assert thin['facts']['yield_strength_Rp0.2']['value']==250
    assert thick['facts']['yield_strength_Rp0.2']['value']==260
    assert resolved_engineering_facts('material','MAT-6082')['facts']['yield_strength_Rp0.2']['value'] is None
    assert resolved_engineering_facts('material','MAT-6082',context={'stock_thickness_mm':10})['facts']['yield_strength_Rp0.2']['value'] is None
    assert resolved_engineering_facts('material','MAT-C45',context={'stock_diameter_mm':10})['facts']['yield_strength_Rp0.2']['value'] is None
    assert not any('oem_manifold_pressure' in k for k in default['facts'])


@pytest.mark.parametrize('error',['identity','source','base','form','preferred'])
def test_rejected_supplement_never_changes_source_or_leaves_output(core_inputs,tmp_path,error):
    source,package,rev1,supplement=core_inputs;data=json.loads(supplement.read_text(encoding='utf-8'))
    if error=='identity':data['evidence'][0]['normalized_value']['grade']='UNRELATED'
    elif error=='source':data['sources'][0]['url']='file:///private.pdf'
    elif error=='base':data['base_rev2_sha256']='wrong'
    elif error=='form':data['identities'][0]['core_material']['stock_product_form']='Tube'
    else:data['conflicts'][0]['preferred_evidence_id']='MISSING'
    supplement.write_text(json.dumps(data),encoding='utf-8');before=source.read_bytes();target=tmp_path/'bad.db'
    with pytest.raises(ValueError):integrate(source,package,rev1,target,material_supplement=supplement)
    assert source.read_bytes()==before and not target.exists()
