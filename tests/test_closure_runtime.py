import json
from pathlib import Path
import sqlite3

import pytest

from manifold import engineering_db,library_schema
from manifold.admit_construction_closures import plan
from manifold.closure_runtime import bind_route,bound,compatible,normalize_design
from manifold.demo import demo
from manifold.geometry import build_geometry,cylinder,placement
from manifold.validation import validate


@pytest.fixture
def admission_db():
    """Only relevant source rows in memory; never mutate the real engineering DB."""
    src=engineering_db._connect();db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    engineering_db.initialize_schema(db);library_schema.initialize(db)
    for table in ['thread_definitions','external_port_definitions','library_targets','library_evidence','library_target_evidence']:
        rows=src.execute('SELECT * FROM '+table).fetchall()
        if rows:db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in rows[0])+')',[tuple(r) for r in rows])
    src.close()
    yield db
    db.close()


def test_admission_does_not_promote_verified_or_partial_blindly(admission_db):
    rows,report=plan(admission_db)
    assert report['knowledge_total']==443
    assert len(rows)==38<380
    assert report['target_states']['PARTIAL_IDENTITY']==63
    assert all(r[5]>0 and json.loads(r[4])[0]['pressure_rating'] is None for r in rows)
    assert report['construction_ports_added']==0


@pytest.mark.parametrize('missing',['l1','d2 +0.10 / -0','(l2) ~ Ref.'])
def test_missing_engagement_machining_or_envelope_prevents_admission(admission_db,missing):
    for row in admission_db.execute("SELECT id,original_json FROM library_evidence WHERE json_extract(original_json,'$.property')='official_exact_item_identity_dimensions_and_installation_type'").fetchall():
        e=json.loads(row[1]);value=json.loads(e['raw_value']);value['specifications'].pop(missing,None)
        e['raw_value']=json.dumps(value);admission_db.execute('UPDATE library_evidence SET original_json=? WHERE id=?',(json.dumps(e),row[0]))
    assert not plan(admission_db)[0]


def test_ambiguous_interface_is_not_picked_by_similarity(admission_db):
    row=dict(admission_db.execute("SELECT * FROM external_port_definitions WHERE name='MB-600-080' AND unit_system='metric' AND usable=1").fetchone())
    row['id']='duplicate-interface';admission_db.execute('INSERT INTO external_port_definitions VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
    rows,report=plan(admission_db)
    assert len(rows)==37 and report['target_states']['AMBIGUOUS_COMPATIBILITY']>0


@pytest.mark.parametrize('unit',['metric','inch'])
def test_real_closure_entry_engagement_and_manufacturing_ready(unit):
    design=demo();design.project_context=unit
    before=design.model_dump_json()
    first=bind_route(design,design.features);second=bind_route(design,design.features)
    assert [f.model_dump() for f in first]==[f.model_dump() for f in second]
    assert design.model_dump_json()==before
    target=design.model_copy(update={'features':first})
    from manifold.schema import Design
    target=Design.model_validate_json(target.model_dump_json())
    feature=next(f for f in target.features if f.plugged);source=bound(feature)
    assert source and compatible(feature,source) and feature.plug_length==source['engagement_mm']!=8
    assert feature.diameter==8  # Internal passage stays routing-derived.
    g=build_geometry(target);report=validate(target,g)
    assert g.production.isValid() and len(g.production.Solids())==1
    assert report['status']=='PASS' and report['manufacturing_ready']
    assert report['unresolved_plug_entries']==[]
    assert not any(r['rule']=='construction_closure' and r['status']!='PASS' for r in report['checks'])
    origin,direction=placement(feature,target.block)
    plain=cylinder(origin,direction,feature.diameter,0,feature.depth)
    assert g.cuts[feature.id].Volume()>plain.Volume()
    assert g.plugs[feature.id].Volume()>3.14*(feature.diameter/2)**2*feature.plug_length
    assert not any(g.plugs[feature.id].intersect(cut).Volume()>1e-6 for id,cut in g.cuts.items() if id!=feature.id)


def test_legacy_unresolved_and_invalid_selected_closure_remain_nonready():
    legacy=demo();g=build_geometry(legacy);r=validate(legacy,g)
    assert any(c['rule']=='construction_closure' and c['status']=='WARNING' for c in r['checks'])
    assert r['unresolved_plug_entries'] and not r['manufacturing_ready']
    invalid=legacy.model_copy(deep=True);next(f for f in invalid.features if f.plugged).closure_definition_id='missing-closure'
    r=validate(invalid,g)
    assert any(c['rule']=='construction_closure' and c['status']=='FAIL' for c in r['checks'])
    assert not r['manufacturing_ready']


def test_selected_source_length_overrides_legacy_length_without_loading_writes():
    design=demo();design.features=bind_route(design,design.features)
    f=next(f for f in design.features if f.plugged);expected=f.plug_length;f.plug_length=8
    target=normalize_design(design)
    assert next(f for f in target.features if f.plugged).plug_length==expected
    assert next(f for f in design.features if f.plugged).plug_length==8


def test_real_runtime_choices_and_library_count_read_only():
    from fastapi.testclient import TestClient
    from manifold.server import app
    with TestClient(app) as client:
        page=client.get('/api/closures/compatible',params={'diameter':8,'depth':60,'unit':'metric'})
        assert page.status_code==200 and page.json()['items']
        assert all(row['engagement_mm']>0 and row['display_name'].startswith(('SFC KOENIG','Expander Plug','SAE construction plug','ISO 6149 construction plug')) for row in page.json()['items'])
        library=client.get('/api/engineering-library/categories').json()['items']
        card=next(r for r in library if r['key']=='closures')
        version=engineering_db.validate_database()['schema_version']
        with engineering_db._connect() as db:count=db.execute('SELECT count(*) FROM closure_definitions WHERE active=1').fetchone()[0]
        assert card['definition_count']==count and card['knowledge_count']==443
        assert client.get('/api/closures/compatible',params={'diameter':8,'depth':0}).status_code==422
