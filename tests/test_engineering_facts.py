import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from manifold import engineering_db
from manifold.engineering_facts import (resolved_engineering_facts, facts_batch,
    material_actionability, promote_materials, ai_context, engineering_review)
from manifold.server import app
from test_technical_knowledge import inputs, package_files, write_package
from manifold.import_technical_knowledge import integrate


@pytest.fixture
def knowledge(tmp_path,monkeypatch):
    path=tmp_path/'facts.db'
    with sqlite3.connect(path) as db:
        engineering_db.initialize_schema(db)
        for cid,status in [('EXACT','PARTIAL_CONFIRMED'),('AMB','IDENTITY_AMBIGUOUS'),('REL','RELATION_SOURCE_ONLY')]:
            db.execute('INSERT INTO cartridges VALUES (?,?,?,?,?,?)',(cid,'Maker',cid,'','{}',1))
            db.execute('INSERT INTO technical_identities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                ('cartridge',cid,cid,None,'Maker',cid,'BASE','','',status,'COMPLETE','{}'))
        db.execute('INSERT INTO materials VALUES (?,?,?,?)',('material_1','Aluminum','',1))
        db.execute('INSERT INTO materials VALUES (?,?,?,?)',('material_2','DuraBar','',1))
        raw=dict(canonical_grade='6061',standard='ASTM B221 / UNS A96061',temper_condition='T6',product_form='Extrusion')
        db.execute('INSERT INTO technical_identities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            ('material','MAT-6061',None,None,'','6061','','T6','Aluminium','PARTIAL','COMPLETE',json.dumps(raw)))
        for domain in ('material','cartridge'):
            db.execute('INSERT INTO technical_sources VALUES (?,?,?,?,?,?)',(domain,'SRC','Producer sheet','https://example.test/facts','','{}'))
    value(path,'IDENTITY','canonical_grade','6061','',domain='material',identity='MAT-6061',evidence_class='identity',scope='GRADE')
    with sqlite3.connect(path) as db:promote_materials(db)
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(path))
    return path


def value(path,eid,prop,value,unit,*,identity='EXACT',domain='cartridge',scope='FULL_PART_NUMBER',
          condition='',evidence_class='parameter',entity=None,option='',source_type='manufacturer_official_datasheet',field=''):
    with sqlite3.connect(path) as db:
        raw=dict(source_type=source_type,source_field_label=field)
        db.execute('INSERT INTO technical_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (domain,eid,entity or identity,'Maker',prop,str(value),unit,json.dumps(value),unit,condition,scope,scope,'',option,evidence_class,json.dumps(raw)))
        db.execute('INSERT INTO technical_evidence_sources VALUES (?,?,?)',(domain,eid,'SRC'))
        db.execute('INSERT INTO technical_identity_evidence VALUES (?,?,?,?)',(domain,identity,eid,'EXACT'))
        db.execute('INSERT INTO technical_values VALUES (?,?,?,?,?,?,?)',(domain,eid,identity,eid,prop,'SOURCE_VALUE',None))


def conflict(path,preferred=None):
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO technical_conflicts VALUES (?,?,?,?,?,?,?,?,?)',
            ('cartridge','CONFLICT','EXACT','maximum_flow','VALUE_CONFLICT','RESOLVED' if preferred else 'OPEN','LINKED',preferred,'{}'))
        db.execute('INSERT INTO technical_identity_conflicts VALUES (?,?,?)',('cartridge','EXACT','CONFLICT'))


def test_explicit_vocabulary_units_and_universal_limit_boundaries(knowledge):
    value(knowledge,'P','maximum_working_pressure',30,'MPa')
    value(knowledge,'FLOW','rated_flow',20,'L/min')
    value(knowledge,'CAP','capacity',25,'L/min')
    value(knowledge,'NOM','maximum_flow',25,'L/min',condition='Nominal model capacity')
    value(knowledge,'UNKNOWN','made_up_rating',1000,'bar')
    value(knowledge,'MISSING','function_primary','NOT_FOUND','')
    facts=resolved_engineering_facts('cartridge','EXACT')['facts']
    assert facts['maximum_working_pressure']['value']==300
    assert facts['rated_flow']['value']==20 and facts['capacity']['value']==25
    assert facts['maximum_flow']['value'] is None
    assert 'made_up_rating' not in facts
    assert facts['function_primary']['value'] is None
    assert facts['maximum_working_pressure']['sources'][0]['id']=='SRC'
    context=ai_context(cartridge_ids=['EXACT'])['cartridges'][0]['facts']
    assert context['maximum_working_pressure']['status']=='SOURCE_BACKED' and context['maximum_working_pressure']['value']==300
    assert context['rated_pressure']['value'] is None and context['function_primary']['value'] is None


def test_conflicts_no_inferred_winner_and_supported_preferred(knowledge):
    value(knowledge,'A','maximum_flow',30,'L/min');value(knowledge,'B','maximum_flow',40,'L/min')
    assert resolved_engineering_facts('cartridge','EXACT')['facts']['maximum_flow']['status']=='UNRESOLVED'
    conflict(knowledge)
    assert resolved_engineering_facts('cartridge','EXACT')['facts']['maximum_flow']['value'] is None
    assert ai_context(cartridge_ids=['EXACT'])['cartridges'][0]['facts']['maximum_flow']['value'] is None
    with sqlite3.connect(knowledge) as db:
        db.execute("UPDATE technical_conflicts SET preferred_evidence_id='B',resolution='RESOLVED'")
    fact=resolved_engineering_facts('cartridge','EXACT')['facts']['maximum_flow']
    assert fact['status']=='SOURCE_BACKED' and fact['value']==40


@pytest.mark.parametrize('identity',['AMB','REL'])
def test_ambiguous_relation_only_do_not_supply_ai_facts(knowledge,identity):
    value(knowledge,'P','maximum_working_pressure',350,'bar',identity=identity)
    ctx=ai_context(cartridge_ids=[identity])
    facts=ctx['cartridges'][0]
    assert not facts['runtime_linked']
    assert facts['facts']['maximum_working_pressure']['value'] is None


def test_scope_option_condition_and_evidence_class(knowledge):
    value(knowledge,'FAMILY','maximum_working_pressure',350,'bar',scope='PRODUCT_FAMILY')
    value(knowledge,'OPT','rated_pressure',200,'bar',scope='OPTION_FAMILY',option='seals=EPDM',condition='Water glycol')
    value(knowledge,'REV','rated_flow',20,'L/min',evidence_class='source_review')
    value(knowledge,'IDENT','nominal_flow',10,'L/min',evidence_class='identity')
    value(knowledge,'STOCK','capacity',10,'L/min',evidence_class='stock')
    facts=resolved_engineering_facts('cartridge','EXACT')['facts']
    assert all(facts[p]['value'] is None for p in ['maximum_working_pressure','rated_pressure','rated_flow','nominal_flow','capacity'])
    facts=resolved_engineering_facts('cartridge','EXACT',context=dict(option='seals=EPDM',condition='Water glycol'))['facts']
    assert facts['rated_pressure']['value']==200
    assert facts['maximum_working_pressure']['value'] is None


def test_material_api_default_override_ai_and_batch_queries(knowledge):
    value(knowledge,'Y','yield_strength',276,'MPa',domain='material',identity='MAT-6061',scope='GRADE_CONDITION_FORM',condition='T6; Extrusion',source_type='PRIMARY_PRODUCER_DATASHEET')
    with TestClient(app) as client:
        rows=client.get('/api/materials').json()['items']
        legacy_rows=client.get('/api/materials?include_legacy=true').json()['items']
    assert len(rows)==1
    assert len(legacy_rows)==3
    material=next(r for r in rows if r['technical_identity_id'])
    assert material['id'].startswith('material_rev2_') and material['stock']==[]
    assert material['engineering_defaults']['allowable_stress_mpa'] is None
    assert material['engineering_facts_summary']['facts']['yield_strength']['value']==276
    override=resolved_engineering_facts('material','MAT-6061',overrides={'allowable_stress_mpa':120})
    assert override['facts']['allowable_stress_mpa']['status']=='USER_OVERRIDE'
    ctx=ai_context();assert ctx['materials'][0]['runtime_id']==material['id']
    assert ctx['materials'][0]['engineering_facts']['facts']['yield_strength']['status']=='SOURCE_BACKED'
    with engineering_db._connect() as db:
        queries=[];db.set_trace_callback(queries.append)
        facts_batch('material',['MAT-6061','MISSING'],connection=db)
    assert len([q for q in queries if q.startswith('SELECT')])==4
    assert {'material_1','material_2'} <= {r['id'] for r in engineering_db.materials(include_legacy=True)}


def test_material_identity_not_property_conflict_and_stable_states():
    raw=dict(canonical_grade='6061',standard='ASTM B221',temper_condition='T6',product_form='Extrusion')
    ident=dict(id='MAT',disposition='PARTIAL',original=raw,source_supported=True)
    a=material_actionability(ident,[dict(property='yield_strength',preferred_evidence_id=None)])
    assert a['selectable']
    assert a['runtime_id']!=material_actionability(ident|dict(original=raw|dict(temper_condition='T651')))['runtime_id']
    assert not material_actionability(ident|dict(original=raw|dict(temper_condition='suffix-specific')))['selectable']
    assert not material_actionability(ident|dict(original=raw|dict(standard='requires confirmation')))['selectable']


def test_two_rebuilds_promote_exact_material_and_rebuilding_promoted_source_is_stable(inputs,tmp_path):
    source,package,rev1=inputs;files=package_files()
    raw=json.loads(files['material/MATERIAL_MASTER.jsonl']);raw.update(standard='EN 10083',product_form='Round bar')
    files['material/MATERIAL_MASTER.jsonl']=(json.dumps(raw)+'\n').encode()
    write_package(package,files)
    outputs=[tmp_path/'a.db',tmp_path/'b.db',tmp_path/'c.db']
    a=integrate(source,package,rev1,outputs[0]);b=integrate(source,package,rev1,outputs[1])
    assert a['material_promotion']==b['material_promotion']
    assert a['material_promotion'][0]['selectable']
    integrate(outputs[0],package,rev1,outputs[2])
    snapshots=[]
    for path in outputs:
        with sqlite3.connect(path) as db:
            snapshots.append((db.execute('SELECT * FROM materials ORDER BY id').fetchall(),
                db.execute('SELECT id,material_id FROM technical_identities ORDER BY domain,id').fetchall()))
    assert snapshots[0]==snapshots[1]==snapshots[2]


def test_review_only_existing_quantities_no_missing_field_fail(knowledge):
    value(knowledge,'MAX','maximum_working_pressure',200,'bar')
    design=SimpleNamespace(features=[SimpleNamespace(id='CV',cartridge_id='EXACT',interface_nets={'1':'P'})],
        schematic_intent=None,nets=[SimpleNamespace(id='P',pressure_bar=250,flow_lpm=None)])
    review=engineering_review(design)
    assert len(review['checks'])==1 and review['checks'][0]['status']=='WARNING'
    assert 'exceeds' in review['checks'][0]['message']
    design.nets[0].pressure_bar=None;assert engineering_review(design)['checks']==[]
