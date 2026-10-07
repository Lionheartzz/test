import json
import sqlite3

import pytest

from manifold import closure_runtime as runtime,engineering_db
from manifold.generic_closures import admission_reason,reconcile,products,generic_record
from manifold.demo import demo
from manifold.schema import Design
from manifold.geometry import build_geometry,review_layer
from manifold.validation import validate


@pytest.fixture
def migrated(monkeypatch):
    src=engineering_db._connect();db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    engineering_db.initialize_schema(db)
    for table in ('thread_definitions','external_port_definitions','closure_definitions'):
        rows=src.execute('SELECT * FROM '+table).fetchall()
        db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in rows[0])+')',[tuple(r) for r in rows])
    src.close()
    before=[dict(r) for r in db.execute('SELECT * FROM closure_definitions')]
    # Active v7 is already reconciled. Build its equivalent v6 product rows for
    # a repeatable migration test without rewriting the real source database.
    if before and not before[0]['model']:
        src=engineering_db._connect()
        db.execute('DELETE FROM closure_definitions')
        for row in before:
            for product in products(src,row['id']):
                recipe=json.loads(row['machining_json']);entry=next(x for x in recipe if x['operation']=='SOURCE_EXPANDER_ENTRY')
                entry.update(manufacturer=product['manufacturer'],model=product['part_number'])
                for key in ('setting_stroke_mm','pressure_rating','note','source_evidence_ids'):
                    if key in product['properties']:entry[key]=product['properties'][key]
                old=dict(row);old['id']=product['id'].replace('closure_product_','closure_');old['model']=product['part_number'];old['machining_json']=json.dumps(recipe)
                alias=src.execute('SELECT source_port_definition_id FROM closure_definition_aliases WHERE alias_id=?',(old['id'],)).fetchone()
                if alias:old['construction_port_definition_id']=alias[0]
                db.execute('INSERT INTO closure_definitions VALUES ('+','.join('?' for _ in old)+')',tuple(old.values()))
        src.close()
        before=[dict(r) for r in db.execute('SELECT * FROM closure_definitions')]
    assert reconcile(db)==14
    rows=[dict(r) for r in db.execute('''SELECT c.*,p.unit_system,p.active AS port_active,p.usable AS port_usable
        FROM closure_definitions c JOIN external_port_definitions p ON p.id=c.construction_port_definition_id''')]
    for r in rows:r['machining']=json.loads(r['machining_json']);r['envelope']=json.loads(r['envelope_json'])
    monkeypatch.setattr(runtime,'catalog',lambda:tuple(rows))
    monkeypatch.setattr(runtime,'aliases',lambda:dict(db.execute('SELECT alias_id,closure_definition_id FROM closure_definition_aliases')))
    yield db,before,rows
    db.close()


@pytest.mark.parametrize('role,missing,expected',[
    ('EXPANDER_CLOSURE',None,None),('EXPANDER_CLOSURE','entry','MISSING_MACHINING'),
    ('EXPANDER_CLOSURE','engagement','MISSING_ENGAGEMENT'),('EXPANDER_CLOSURE','envelope','MISSING_ENVELOPE'),
    ('AMBIGUOUS',None,'AMBIGUOUS_ROLE'),('ORIFICE_PLUG',None,'NON_CONSTRUCTION_ROLE'),
    ('RESTRICTOR',None,'NON_CONSTRUCTION_ROLE'),('FULL_CAVITY_PLUG',None,'NON_CONSTRUCTION_ROLE'),
    ('PORT_PLUG',None,'NON_CONSTRUCTION_ROLE'),('THREADED_CONSTRUCTION_PLUG',None,'INCOMPLETE_THREAD_MACHINING')])
def test_generic_admission_requires_role_and_geometry_not_sku(role,missing,expected):
    args=dict(entry=dict(diameter_mm=9,depth_mm=9.8,hydraulic_diameter_max_mm=8,transition_angle_degrees=120),
              engagement=10,envelope=dict(diameter_mm=9.1,height_mm=0))
    if missing:args[missing]=None
    assert admission_reason(role,**args)==expected


def test_generic_row_admitted_without_manufacturer_or_sku():
    row=generic_record('source-port','Expander Plug Ø9','EXPANDER_CLOSURE',
                       dict(diameter_mm=9,depth_mm=9.8,hydraulic_diameter_max_mm=8,transition_angle_degrees=120),
                       10,dict(diameter_mm=9.1,height_mm=0))
    assert row['usable']==1 and row['model']==''
    assert 'manufacturer' not in row and 'product_id' not in row


def test_all_38_ids_and_effective_geometry_preserved(migrated):
    db,before,rows=migrated;after={r['id']:r for r in rows}
    assert len(after)==14
    assert db.execute('SELECT count(*) FROM closure_definition_aliases').fetchone()[0]==24
    assert db.execute('SELECT count(*) FROM closure_products').fetchone()[0]==38
    for old in before:
        new=after[runtime.aliases().get(old['id'],old['id'])];entry=runtime.profile(new)
        assert new['model']=='' and new['display_name'].startswith('Expander Plug Ø')
        assert 'manufacturer' not in entry and 'model' not in entry
        old_entry=next(x for x in json.loads(old['machining_json']) if x['operation']=='SOURCE_EXPANDER_ENTRY')
        for key in ('diameter_mm','depth_mm','hydraulic_diameter_max_mm','transition_angle_degrees'):
            assert entry[key]==old_entry[key]
        assert new['engagement_mm']==old['engagement_mm'] and new['envelope_json']==old['envelope_json']
        assert old['model'] in [p['part_number'] for p in products(db,new['id'])]
        d=demo();f=next(f for f in d.features if f.plugged)
        f.closure_definition_id=old['id'];f.diameter=min(1,entry['hydraulic_diameter_max_mm']);f.depth=1000
        d=Design.model_validate_json(d.model_dump_json())
        assert engineering_db.closure_definitions_for_design(d,connection=db)[old['id']]['id']==new['id']
        assert runtime.compatible(next(f for f in d.features if f.plugged),new)


def test_optional_products_do_not_control_geometry_or_manufacturing_pass(migrated):
    db,_,_=migrated;d=demo();d.features=runtime.bind_route(d,d.features)
    f=next(f for f in d.features if f.plugged);before=build_geometry(d)
    db.execute('DELETE FROM closure_definition_products');db.execute('DELETE FROM closure_products')
    assert products(db,f.closure_definition_id)==[]
    after=build_geometry(d);r=validate(d,after)
    assert before.production.Volume()==pytest.approx(after.production.Volume())
    assert r['status']=='PASS' and r['manufacturing_ready'] and r['unresolved_plug_entries']==[]


def test_different_generic_selection_updates_exact_feature_and_void_layers(migrated):
    d=demo();original=next(f for f in d.features if f.plugged)
    options=runtime.choices(original,d.project_context)
    a=options[0]
    # Same access and same hydraulic bore; select a truly different source entry.
    b=next(c for c in options if c['engagement_mm']!=a['engagement_mm'] and runtime.profile(c)['diameter_mm']!=runtime.profile(a)['diameter_mm'])
    results=[]
    for c in (a,b):
        copy=d.model_copy(deep=True);f=next(f for f in copy.features if f.plugged);f.closure_definition_id=c['id']
        copy=runtime.normalize_design(copy);f=next(f for f in copy.features if f.plugged)
        g=build_geometry(copy);report=validate(copy,g)
        assert report['status']=='PASS' and report['manufacturing_ready']
        features=review_layer(copy,g,'features');void=review_layer(copy,g,'void')
        results.append((f.closure_definition_id,f.plug_length,g.cuts[f.id].Volume(),void[0]['volume_mm3'],
                        next(x for x in features if x['id']==f.id+':machining')['vertices']))
        assert f.diameter==original.diameter==8
        assert g.production.isValid() and len(g.production.Solids())==1
    assert all(a!=b for a,b in zip(*results))
