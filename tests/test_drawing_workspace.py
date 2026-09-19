"""Focused contracts for drawings without rerouting or changing engineering authority."""
import io
import json
import sqlite3
import time
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from manifold import store, projects
from manifold.schema import Design
from manifold.server import app
from manifold.drawing import storage
from manifold.drawing.generate import snapshot, initial_edit, auto_annotations, add_tables, geometry_for
from manifold.drawing.projection import projected
from manifold.drawing.render import scene, measure, check_drawing
from manifold.drawing.pdf import export_pdf
from manifold.drawing.schema import Edit, Annotation

HEADERS={'X-PMC-Request':'local-console'}


@pytest.fixture
def drawing(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'PROJECT',tmp_path/'projects'/'demo.json')
    monkeypatch.setattr(store,'OUTPUT',tmp_path/'output')
    d=Design(name='Drawing test',block=dict(length=100,width=80,height=60,material='S50C'),
             features=[dict(id='P1',kind='port',face='top',u=40,v=35,circuit='P',diameter=10,depth=30,size='Custom bore',connects_to=['P2']),
                       dict(id='P2',kind='port',face='front',u=40,v=35,circuit='P',diameter=10,depth=45,size='Custom bore',connects_to=['P1'])])
    p=projects.save(d)
    p=projects.build(p['project_id'],p['revision'])
    assert p['build']['status']=='PASS'
    source,solid=snapshot(p['project_id'],p['revision'])
    edit=initial_edit(source,'customer','PMC-TEST')
    edit.annotations=auto_annotations(source,edit)
    doc=storage.save_new(p['project_id'],source,edit,geometry_for(source,solid,edit.views),'customer')
    return p,doc


def test_drawing_snapshot_and_open_do_not_resolve_current_engineering_master(drawing,monkeypatch):
    p,doc=drawing
    monkeypatch.setattr(projects,'snapshot',lambda record: (_ for _ in ()).throw(AssertionError('current engineering master queried')))
    source,solid=snapshot(p['project_id'],p['revision'])
    assert source['build_id']==p['build']['build_id'] and solid.isValid()
    opened=storage.public(storage.read(p['project_id'],doc['id']))
    assert opened['source_current'] is True
    copied=storage.save_new(p['project_id'],source,Edit.model_validate(doc['edit']),doc['geometry'],'customer',expected_project=p['revision'])
    assert copied['source']['sha256']==source['sha256']


def test_exact_projection_axes_and_dimensions(drawing):
    p,doc=drawing
    assert doc['geometry']['front']['bounds']==pytest.approx([0,0,100,60])
    assert doc['geometry']['back']['bounds']==pytest.approx([-100,0,0,60])
    assert doc['geometry']['left']['bounds']==pytest.approx([-80,0,0,60])
    assert projected((20,30,40),'bottom')==[20,-30]
    from manifold.drawing.generate import anchors
    data=anchors(doc['source'])[0]
    edit=Edit.model_validate(doc['edit']);view=next(v for v in edit.views if v.id=='top')
    item=Annotation(id='manual',kind='dimension',view='top',sheet='overview',anchors=['F:P1'],measure='diameter')
    assert measure(item,view,data)==10
    with pytest.raises(ValueError,match='computed'):
        Annotation(id='fake',kind='dimension',view='top',sheet='overview',anchors=['F:P1'],measure='diameter',text='25')
    edit.annotations.append(Annotation(id='foreshortened',kind='dimension',view='iso',sheet='overview',anchors=['B:000','B:100']))
    with pytest.raises(ValueError,match='foreshortened'):
        Edit.model_validate(edit.model_dump())


def test_save_preserves_source_and_optimistic_revision(drawing):
    p,doc=drawing
    before=projects.path(p['project_id']).read_bytes()
    edit=Edit.model_validate(doc['edit']);edit.views[0].position=(170,40)
    removed=edit.annotations.pop(0).id
    changed=storage.save_edit(p['project_id'],doc['id'],storage.revision(doc),edit)
    assert changed['source']==doc['source'] and removed in changed['edit']['suppressed']
    assert projects.path(p['project_id']).read_bytes()==before
    assert storage.read(p['project_id'],doc['id'])['edit']['views'][0]['position']==[170,40]
    with pytest.raises(ValueError,match='another window'):
        storage.save_edit(p['project_id'],doc['id'],storage.revision(doc),edit)


def test_pdf_is_vector_correct_sheet_size_and_contains_real_values(drawing):
    p,doc=drawing
    data=export_pdf(doc)
    pdf=PdfReader(io.BytesIO(data))
    assert len(pdf.pages)==1
    page=pdf.pages[0]
    assert float(page.mediabox.width)==pytest.approx(594*72/25.4,abs=.001)
    text=page.extract_text()
    assert 'PMC-TEST' in text and 'S50C' in text and '100.00' in text
    assert 'FOR CUSTOMER REFERENCE ONLY' in text and 'DRAFT' not in text
    assert b' l' in page.get_contents().get_data()
    assert any('/FontDescriptor' in f.get_object() or '/DescendantFonts' in f.get_object() for f in page['/Resources']['/Font'].values())


def test_api_guards_and_release_cannot_bypass_canonical_failures(drawing):
    p,doc=drawing
    client=TestClient(app,base_url='http://127.0.0.1:8765')
    url=f'/api/drawings/{p["project_id"]}/{doc["id"]}'
    assert client.get(url).status_code==200
    assert dict(id='P1',label='P1 / top') in client.get(url).json()['table_sources']['porting']
    payload=dict(expected_revision=storage.revision(doc),edit=doc['edit'])
    assert client.post(url+'/save',json=payload).status_code==403
    assert client.post(url+'/save',json={**payload,'source':doc['source']},headers=HEADERS).status_code==422
    assert client.post(url+'/save',json=payload,headers={**HEADERS,'Origin':'https://evil.example'}).status_code==403
    changed=deepcopy(doc);changed['source']['validation']['status']='FAIL'
    assert any(i['code']=='engineering-fail' and i['severity']=='error' for i in check_drawing(changed))
    assert client.get('/api/drawings/not-an-id').status_code==422


def test_manufacturing_and_section_from_existing_build(drawing):
    p,doc=drawing
    source,solid=snapshot(p['project_id'],p['revision'])
    edit=initial_edit(source,'manufacturing');edit.annotations=auto_annotations(source,edit);add_tables(source,edit,'manufacturing')
    geo=geometry_for(source,solid,edit.views)
    manufacture=storage.save_new(p['project_id'],source,edit,geo,'manufacturing')
    assert len(edit.sheets)==3 and len(edit.views)==21
    assert all({v.projection for v in edit.views if v.sheet==s.id}=={'top','bottom','front','back','left','right','iso'} for s in edit.sheets)
    assert any(a.id=='auto:coordinates-top:P1:x' and a.ordinate for a in edit.annotations)
    pdf=PdfReader(io.BytesIO(export_pdf(manufacture)))
    assert len(pdf.pages)==len(edit.sheets)
    assert all('PORTINGS' in page.extract_text() for page in pdf.pages)
    # Exact sections remain available when engineering finishing needs one;
    # they are no longer mandatory extra sheets in the default PMC layout.
    from manifold.drawing.schema import View
    section=View(id='section-test',sheet='internal',projection='section-z',section_at=30,position=(20,30))
    detail=geometry_for(source,solid,[section])['section-z:30']
    assert detail['visible'] and detail['hatching']


def completed(client,project_id,response):
    assert response.status_code==200,response.text
    key=response.json()['job_id']
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        result=client.get(f'/api/drawings/{project_id}/jobs/{key}').json()
        if result['state'] in ('completed','failed','cancelled'):
            assert result['state']=='completed',result
            return result['result']
        time.sleep(.03)
    pytest.fail('Local drawing job did not finish')


def test_update_preserves_layout_suppression_and_broken_refs_until_rebind(drawing):
    p,doc=drawing
    client=TestClient(app);url=f'/api/drawings/{p["project_id"]}/{doc["id"]}'
    edit=Edit.model_validate(doc['edit']);edit.views[0].position=(170,45)
    removed=next(a.id for a in edit.annotations if a.kind=='dimension')
    edit.annotations=[a for a in edit.annotations if a.id!=removed]
    edit.annotations.append(Annotation(id='note',kind='text',sheet='overview',position=(20,25),text='Keep my note'))
    d=Design.model_validate(p['design']);d.features[0].face='bottom'
    p=projects.save(d,p['project_id'],p['revision']);p=projects.build(p['project_id'],p['revision'])
    assert not storage.source_current(doc)
    result=completed(client,p['project_id'],client.post(url+'/update',headers=HEADERS,json=dict(expected_revision=storage.revision(doc),expected_source=p['revision'],edit=edit.model_dump())))
    assert storage.revision(storage.read(p['project_id'],doc['id']))==storage.revision(doc) # preview has no effect
    assert result['broken']['auto:top:P1:label']
    applied=client.post(url+'/apply-update',headers=HEADERS,json=dict(candidate_id=result['candidate_id'],expected_revision=storage.revision(doc)))
    assert applied.status_code==200,applied.text
    current=storage.read(p['project_id'],doc['id'])
    copied=storage.duplicate(p['project_id'],doc['id'],storage.revision(current))
    assert copied['broken']==current['broken']
    assert current['edit']['views'][0]['position']==[170,45]
    assert removed in current['edit']['suppressed']
    assert any(a['id']=='note' for a in current['edit']['annotations'])
    # Updating the same source again cannot silently re-confirm a changed feature.
    result=completed(client,p['project_id'],client.post(url+'/update',headers=HEADERS,json=dict(expected_revision=storage.revision(current),expected_source=p['revision'],edit=current['edit'])))
    assert 'auto:top:P1:label' in result['broken']
    response=client.post(url+'/rebind',headers=HEADERS,json=dict(expected_revision=storage.revision(current),edit=current['edit'],annotation='auto:top:P1:label'))
    assert response.status_code==200,response.text
    assert 'auto:top:P1:label' not in storage.read(p['project_id'],doc['id'])['broken']
    assert client.post(url+'/apply-update',headers=HEADERS,json=dict(candidate_id=result['candidate_id'],expected_revision=storage.revision(current))).status_code==409


def test_release_revision_history_and_archive_are_strict(drawing):
    p,doc=drawing;client=TestClient(app)
    url=f'/api/drawings/{p["project_id"]}/{doc["id"]}'
    edit=Edit.model_validate(doc['edit']);edit.template.tolerance_confirmed=True
    doc=storage.save_edit(p['project_id'],doc['id'],storage.revision(doc),edit)
    problems=check_drawing(doc)
    assert not [i for i in problems if i['severity']=='error'],problems
    exceptions={i['code']:'Engineer reviewed this stated limitation for customer reference.' for i in problems}
    response=client.post(url+'/release',headers=HEADERS,json=dict(expected_revision=storage.revision(doc),released_by='Test engineer',exceptions=exceptions))
    assert response.status_code==200,response.text
    released=response.json();release_id=released['release']['id']
    tampered=deepcopy(released['edit']);tampered['metadata']['title']='Not the issued drawing'
    assert client.post(url+'/render',headers=HEADERS,json=dict(edit=tampered,sheet='overview')).status_code==409
    original=client.get(url+'/revisions/'+release_id+'/pdf').content
    assert original.startswith(b'%PDF')
    assert client.post(url+'/save',headers=HEADERS,json=dict(expected_revision=released['revision'],edit=released['edit'])).status_code==409
    response=client.post(url+'/revision',headers=HEADERS,json=dict(expected_revision=released['revision'],revision='B',note='New customer issue'))
    assert response.status_code==200,response.text
    draft=response.json();assert draft['status']=='Draft'
    assert client.get(url+'/revisions/'+release_id+'/pdf').content==original
    history=client.get(url+'/history').json()
    issued_state=next(row for row in history if row['status']=='Released')
    assert client.get(url+'/history/'+issued_state['id']+'/pdf').content==original
    record=projects.read(p['project_id']);record['archived']=True;projects.write(record)
    for endpoint,payload in [('save',dict(edit=draft['edit'])),('revision',dict(revision='C')),('release',dict(released_by='Test engineer'))]:
        assert client.post(url+'/'+endpoint,headers=HEADERS,json=dict(expected_revision=draft['revision'],**payload)).status_code==409


def test_moved_feature_updates_values_and_replaced_id_never_silently_rebinds(drawing):
    p,doc=drawing;client=TestClient(app)
    url=f'/api/drawings/{p["project_id"]}/{doc["id"]}'
    d=Design.model_validate(p['design']);d.features[0].u=42;d.features[1].u=42
    p=projects.save(d,p['project_id'],p['revision']);p=projects.build(p['project_id'],p['revision'])
    assert p['build']['status']=='PASS'
    result=completed(client,p['project_id'],client.post(url+'/update',headers=HEADERS,json=dict(expected_revision=storage.revision(doc),expected_source=p['revision'],edit=doc['edit'])))
    assert not result['broken']
    assert result['document']['anchors']['F:P1']['point'][0]==42
    assert storage.read(p['project_id'],doc['id'])['source']==doc['source'] # discarded preview keeps the old drawing
    d.features[0].id='REPLACEMENT';d.features[1].connects_to=['REPLACEMENT']
    for net in d.nets:net.members=['REPLACEMENT' if key=='P1' else key for key in net.members]
    p=projects.save(d,p['project_id'],p['revision']);p=projects.build(p['project_id'],p['revision'])
    result=completed(client,p['project_id'],client.post(url+'/update',headers=HEADERS,json=dict(expected_revision=storage.revision(doc),expected_source=p['revision'],edit=doc['edit'])))
    assert 'auto:top:P1:label' in result['broken']
    assert 'auto:top:REPLACEMENT:label' in result['added']
    assert 'F:P1' not in result['document']['anchors']
    assert storage.read(p['project_id'],doc['id'])['source']==doc['source']


def test_jobs_cancel_before_commit_and_reject_cross_project():
    from threading import Event
    from manifold.drawing import jobs
    ready=Event();resume=Event();writes=[]
    def operation(progress):
        ready.set();resume.wait(10)
        return progress.commit(lambda:writes.append('saved'))
    job=jobs.start('a'*32,operation)['job_id'];assert ready.wait(5)
    with pytest.raises(FileNotFoundError):jobs.get('b'*32,job)
    jobs.cancel('a'*32,job);resume.set()
    for _ in range(100):
        if jobs.get('a'*32,job)['state']=='cancelled':break
        time.sleep(.02)
    assert jobs.get('a'*32,job)['state']=='cancelled' and writes==[]


def test_template_reuses_only_presentation_and_project_deletes_owned_drawings(drawing):
    from manifold.drawing import templates
    p,doc=drawing;client=TestClient(app)
    url=f'/api/drawings/{p["project_id"]}/{doc["id"]}'
    doc['edit']['tables'][0]['remarks']={'P1':'Do not copy this identity-specific instruction'}
    row=templates.save('PMC finishing layout',doc)
    reused=templates.apply(row['id'],'customer',initial_edit(doc['source'],'customer','NEW-DRAWING'))
    assert reused.metadata.number=='NEW-DRAWING' and reused.tables[0].remarks=={}
    assert reused.annotations==[] and reused.schematics==[]
    assert reused.template.tolerance_confirmed is False
    assert client.get('/api/drawings/templates').status_code==200
    base=storage.folder(p['project_id'],doc['id'])
    response=client.post('/api/projects/'+p['project_id']+'/delete',headers=HEADERS,json=dict(expected_revision=p['revision'],confirm_name=p['design']['name']))
    assert response.status_code==200,response.text
    assert not base.exists() and (store.OUTPUT/'builds'/p['build']['build_id']/'production.step').exists()


@pytest.mark.parametrize('kind',['customer','manufacturing'])
def test_original_schematic_pdf_is_vector_and_crop_preserves_aspect(drawing,kind):
    from reportlab.pdfgen.canvas import Canvas
    from manifold.workflow import save_asset
    from manifold.drawing.generate import digest
    p,doc=drawing
    original=io.BytesIO();c=Canvas(original,pagesize=(400,200));c.drawString(40,100,'VECTOR-CIRCUIT-P1-P2');c.line(20,90,380,90)
    c.linkURL('https://example.invalid/source-action',(20,90,380,110),relative=0);c.save()
    assert PdfReader(io.BytesIO(original.getvalue())).pages[0]['/Annots']
    asset=save_asset(original.getvalue(),'connection.pdf','application/pdf')
    doc['source']['authored']['schematic_intent']={'assets':[asset.model_dump()],'components':[]}
    doc['source']['authored'].pop('schematics',None)
    doc['source']['sha256']=digest({k:v for k,v in doc['source'].items() if k!='sha256'})
    edit=initial_edit(doc['source'],kind)
    if kind=='customer':
        assert edit.schematics[0].position==(20,16)
        assert edit.schematics[0].asset==asset.sha256
    doc['edit']=edit.model_dump()
    assert storage.public(doc,with_checks=False)['assets'][0]['sha256']==asset.sha256
    current=scene(doc,'overview');image=next(p for p in current['primitives'] if p['kind']=='image' and p.get('schematic'))
    assert image['width']/image['height']==pytest.approx(2)
    exported=PdfReader(io.BytesIO(export_pdf(doc)))
    assert len(exported.pages)==(3 if kind=='manufacturing' else 1)
    assert all('VECTOR-CIRCUIT-P1-P2' in page.extract_text() for page in exported.pages)
    # Original PDF text/path operators survive; schematic is not replaced by a bitmap.
    assert len(list(exported.pages[0].images))==1 # only the print-resolution company logo
    assert not exported.pages[0].get('/Annots')


def test_pmc3069_api_layout_dimensions_and_pdf_are_source_linked(drawing):
    from manifold.drawing.generate import anchors,regenerate_edit
    p,old=drawing;client=TestClient(app)
    before=projects.path(p['project_id']).read_bytes()
    result=completed(client,p['project_id'],client.post('/api/drawings/'+p['project_id'],headers=HEADERS,
        json=dict(expected_source=p['revision'],kind='manufacturing',template_id='pmc-manufacturing',number='PMC-DYNAMIC-42')))
    doc=storage.read(p['project_id'],result['drawing_id'])
    assert projects.path(p['project_id']).read_bytes()==before
    edit=Edit.model_validate(doc['edit'])
    assert edit.template.layout=='pmc3069' and len(edit.sheets)==3
    assert all(s.size=='A2' and s.landscape for s in edit.sheets)
    assert len(edit.views)==21 and len(edit.tables)==3
    assert all(t.presentation=='pmc-portings' and t.position==(313,247) for t in edit.tables)
    assert all(v.hidden for v in edit.views if v.sheet=='internal')
    assert not any(v.hidden for v in edit.views if v.sheet=='overview')
    assert not [i for i in check_drawing(doc) if i['severity']=='error']
    data,rows,_=anchors(doc['source'])
    from manifold.drawing.pmc_portings import porting_groups
    porting_text=' '.join(r['labels'] for r in porting_groups(rows,edit.tables[0]))
    assert all(r['label'] in porting_text and r['machining_label'] in porting_text for r in rows)
    dimensions={a.id:a for a in edit.annotations if a.kind=='dimension'}
    top=next(v for v in edit.views if v.id=='coordinates-top')
    front=next(v for v in edit.views if v.id=='coordinates-front')
    assert measure(dimensions['auto:coordinates-top:P1:x'],top,data)==40
    assert measure(dimensions['auto:coordinates-front:P2:y'],front,data)==25 # measured down from the top datum
    sc=scene(doc,'coordinates')
    assert any(p['kind']=='text' and p.get('rotation')==-90 and p['text']=='40' for p in sc['primitives'])
    assert any(p['kind']=='polyline' and p['dash'] for p in scene(doc,'internal')['primitives'] if p['group']=='internal-front')
    # Presentation edits survive persistence and source regeneration. A changed
    # coordinate changes the value, never its manually positioned dimension.
    dimensions['auto:coordinates-top:P1:x'].position=(4,-12)
    edit.metadata.quantity=7;edit.metadata.designed_by='Engineer';edit.metadata.approved_by='Reviewer'
    saved=storage.save_edit(p['project_id'],doc['id'],storage.revision(doc),edit)
    changed=deepcopy(doc['source']);changed['resolved']['features'][0]['u']=43
    regenerated,_=regenerate_edit(changed,Edit.model_validate(saved['edit']))
    a=next(a for a in regenerated.annotations if a.id=='auto:coordinates-top:P1:x')
    assert a.position==(4,-12) and measure(a,top,anchors(changed)[0])==43
    pdf=PdfReader(io.BytesIO(export_pdf(saved)))
    assert len(pdf.pages)==3
    for page in pdf.pages:
        assert float(page.mediabox.width)==pytest.approx(594*72/25.4,abs=.001)
        assert float(page.mediabox.height)==pytest.approx(420*72/25.4,abs=.001)
        text=page.extract_text()
        assert 'PMC-DYNAMIC-42' in text and 'L100XW80XH60' in text and 'S50C' in text and 'PORTINGS' in text
        assert 'DRAWING NO' in text and 'QTY' in text and 'Engineer' in text and 'Reviewer' in text
        assert '3069' not in text and 'SOURCE' not in text and 'BUILD' not in text and 'DRAFT' not in text
        assert b' l' in page.get_contents().get_data()
    assert pdf.metadata.subject=='PMC engineering drawing' and doc['source']['build_id'] not in str(pdf.metadata)
    failed=deepcopy(doc);failed['source']['validation']['status']='FAIL'
    assert any(i['code']=='engineering-fail' and i['severity']=='error' for i in check_drawing(failed))
    invalid=edit.model_dump();invalid['sheets'][0]['size']='A4'
    assert client.post(f'/api/drawings/{p["project_id"]}/{doc["id"]}/render',headers=HEADERS,json=dict(edit=invalid,sheet='overview')).status_code==422
    # The previously stored Customer/legacy template stays unchanged.
    assert Edit.model_validate(storage.read(p['project_id'],old['id'])['edit'])==Edit.model_validate(old['edit'])


def test_pmc_portings_overflow_preserves_every_source_identifier():
    from manifold.drawing.pmc_portings import add_overflow,porting_groups,table_layout
    from manifold.drawing.pmc3069 import configure
    source=dict(resolved=dict(block=dict(length=187,width=228.6,height=228.6)),authored={})
    edit=configure(source,Edit(metadata=dict(number='INCH-CONTEXT',title='Table test',unit='inch'),sheets=[dict(id='overview')]))
    assert edit.metadata.unit=='mm'
    invalid=edit.model_dump();invalid['metadata']['unit']='inch'
    with pytest.raises(ValueError,match='millimetre'):Edit.model_validate(invalid)
    # More than the contract's 200 rows must paginate rather than disappear.
    rows=[dict(id=f'H{i}',label=f'H{i}',kind='drilling',specification=f'Ø{i+1} × 20 DEEP') for i in range(225)]
    add_overflow(source,edit,rows)
    assert len(edit.sheets)>3
    covered={key for t in edit.tables for r in porting_groups(rows,t) for key in r['ids']}
    assert covered=={r['id'] for r in rows}
    for t in edit.tables:
        grid=table_layout(t,rows)
        assert all(len(row['cells'])==6 for row in grid)
        assert sum(r['height'] for r in grid)+5.5<=117.001
    # Dense but identical source holes use lossless ranges, not 120 new pages.
    for row in rows[:120]:row['specification']='Ø6 × 12 DEEP'
    compact=configure(source,Edit(metadata=dict(number='DENSE',title='Dense'),sheets=[dict(id='overview')]))
    add_overflow(source,compact,rows[:120])
    assert len(compact.sheets)==3
    groups=porting_groups(rows[:120],compact.tables[0])
    assert groups[0]['labels']=='H0-H119' and len(groups[0]['ids'])==120
    # Wrapped specifications should fill all three column pairs before adding
    # a continuation; sub-micron paper rounding is not genuine overflow.
    compact=configure(source,Edit(metadata=dict(number='WRAPPED',title='Wrapped'),sheets=[dict(id='overview')]))
    mixed=[dict(id=f'F{i}',label=f'F{i}',kind='cavity',specification=f'Cavity {i} / explicit engineering source specification with wrapped thread information') for i in range(5)]
    add_overflow(source,compact,mixed)
    assert len(compact.sheets)==3


def test_pmc_portings_display_rows_are_physical_and_never_truncate_groups():
    from manifold.drawing.pmc_portings import table_layout,required_physical_rows
    from manifold.drawing.schema import Table
    rows=[dict(id=f'P{i}',label=f'P{i}',kind='port',specification=f'SPEC {i}') for i in range(6)]
    table=Table(id='ports',sheet='overview',kind='porting',position=(10,10),presentation='pmc-portings')
    assert len(table_layout(table,rows))==2
    assert len(table_layout(table.model_copy(update={'display_rows':5}),rows))==5
    protected=table_layout(table.model_copy(update={'display_rows':1}),rows)
    assert len(protected)==2 and {item for row in protected for item in row['ids']}=={r['id'] for r in rows}
    batched=[dict(id=f'PORT_{i:02}_LONG_IDENTIFIER',label=f'PORT_{i:02}_LONG_IDENTIFIER',kind='port',specification='SAME') for i in range(12)]
    grouped=table.model_copy(update={'count':4})
    assert required_physical_rows(grouped,batched)==2


def test_drawing_save_rejects_fewer_rows_than_grouped_renderer_requires(drawing):
    from manifold.drawing.render import table_metrics
    p,doc=drawing;edit=Edit.model_validate(doc['edit']);table=edit.tables[0]
    table.remarks={'P2':'Keep this source group separate'}
    required=table_metrics(doc['source'],edit)[table.id]['required_physical_rows']
    assert required==2
    table.display_rows=1
    with pytest.raises(ValueError,match='display_rows must be at least 2'):
        storage.save_edit(p['project_id'],doc['id'],storage.revision(doc),edit)


def test_customer_pmc3092_api_and_shared_title_block(drawing):
    p,old=drawing;client=TestClient(app)
    before=projects.path(p['project_id']).read_bytes()
    result=completed(client,p['project_id'],client.post('/api/drawings/'+p['project_id'],headers=HEADERS,
        json=dict(expected_source=p['revision'],kind='customer',template_id='pmc-customer',number='PMC-CUSTOMER-42')))
    doc=storage.read(p['project_id'],result['drawing_id']);edit=Edit.model_validate(doc['edit'])
    assert edit.template.layout=='pmc3092' and len(edit.sheets)==1 and len(edit.views)==7
    views={v.id:v for v in edit.views}
    assert views['top'].position[0]==views['front'].position[0]==views['bottom'].position[0]
    assert {views[face].position[1] for face in ('left','front','right','back')}=={135}
    assert edit.tables[0].presentation=='pmc-customer-portings' and edit.tables[0].position==(459,250)
    edit.metadata.customer='Customer example';edit.metadata.notes='Customer note from this Project only.'
    edit.metadata.designed_by='Designer';edit.metadata.approved_by='Reviewer';edit.metadata.quantity=7
    edit.metadata.revision_note='Customer approval issue'
    edit.views[0].position=(edit.views[0].position[0]+3,edit.views[0].position[1])
    url=f'/api/drawings/{p["project_id"]}/{doc["id"]}'
    saved=client.post(url+'/save',headers=HEADERS,json=dict(expected_revision=storage.revision(doc),edit=edit.model_dump()))
    assert saved.status_code==200,saved.text
    doc=storage.read(p['project_id'],doc['id'])
    assert Edit.model_validate(client.get(url).json()['edit'])==edit
    assert projects.path(p['project_id']).read_bytes()==before
    assert not [i for i in check_drawing(doc) if i['severity']=='error']
    customer_scene=scene(doc,'overview')
    furniture=[p for p in customer_scene['primitives'] if p['group']=='paper']
    # Same source/title values and sheet scale/count produce exactly the same
    # furniture in both layouts, including the logo and tolerance/signoff grids.
    manufacture=deepcopy(doc)
    me=initial_edit(doc['source'],'manufacturing')
    me.metadata=edit.metadata.model_copy(deep=True)
    me.sheets=me.sheets[:1];me.views=[v for v in me.views if v.sheet=='overview']
    me.tables=[t for t in me.tables if t.sheet=='overview']
    manufacture['edit']=me.model_dump();manufacture['kind']='manufacturing'
    assert [p for p in scene(manufacture,'overview')['primitives'] if p['group']=='paper']==furniture
    body=[p for p in customer_scene['primitives'] if p['kind']=='text' and p['group']!='paper']
    for content in ('FOR CUSTOMER REFERENCE ONLY','Customer note from this Project only.','CUSTOMER: Customer example','PORTINGS'):
        assert any(p['text']==content and p['y']<383 for p in body)
        assert not any(p.get('text')==content for p in furniture)
    pdf=PdfReader(io.BytesIO(client.get(url+'/pdf').content))
    text=pdf.pages[0].extract_text()
    assert all(t in text for t in ('GENERAL TOLERANCE','ALTERATION','DESIGN','DRAWN','CHECKED','APPROVED','PMC-CUSTOMER-42','L100XW80XH60'))
    assert not any(t in text for t in ('SOURCE','BUILD','DRAFT','3069','3092'))
    assert pdf.metadata.subject=='PMC engineering drawing'
    # Manual table placement is constrained by actual furniture, not its
    # default lower-right slot. Lower-left remains available for finishing.
    moved=deepcopy(doc);moved['edit']['tables'][0]['position']=[20,340]
    assert not [i for i in scene(moved,'overview')['issues'] if i['severity']=='error']
    moved['edit']['tables'][0]['position']=[459,355]
    assert any(i['code']=='table-bounds:porting' and i['severity']=='error' for i in scene(moved,'overview')['issues'])
    invalid=edit.model_dump();invalid['metadata']['unit']='inch'
    assert client.post(url+'/render',headers=HEADERS,json=dict(edit=invalid,sheet='overview')).status_code==422
    # A custom finishing template may have removed the front view. Generating
    # annotations must still work and must not recreate the deleted view.
    edit.views=[v for v in edit.views if v.id!='front']
    edit.annotations=[]
    assert auto_annotations(doc['source'],edit)


def test_customer_portings_continue_without_losing_source_rows_or_notice():
    from manifold.drawing.pmc3092 import configure
    from manifold.drawing.pmc_portings import add_overflow,porting_groups,table_layout,table_height
    source=dict(resolved=dict(block=dict(length=250,width=130,height=250)),authored={})
    edit=configure(source,Edit(metadata=dict(number='CUSTOMER',title='Customer'),sheets=[dict(id='overview')]))
    rows=[dict(id=f'P{i}',label=f'P{i}',kind='port',specification=f'G{i+1}/4 source thread') for i in range(25)]
    add_overflow(source,edit,rows)
    assert len(edit.sheets)>1
    assert {key for t in edit.tables for r in porting_groups(rows,t) for key in r['ids']}=={r['id'] for r in rows}
    for table in edit.tables:
        assert all(len(row['cells'])==2 for row in table_layout(table,rows))
        assert table_height(table,rows)<=105.001
    assert {a.sheet for a in edit.annotations if a.text=='FOR CUSTOMER REFERENCE ONLY'}=={s.id for s in edit.sheets[1:]}


def test_pinned_build_facts_survive_inactive_master_and_preserve_operations(tmp_path,monkeypatch):
    from manifold.demo import demo
    from manifold.engineering_db import get_definition,initialize_schema
    from manifold.drawing.generate import anchors
    from manifold.drawing.render import table_cells
    from manifold.drawing.schema import Table
    source=demo()
    definition=get_definition(source.features[0].cavity_id).model_dump()
    definition['id']='QA_DRAWING_PROFILE'
    definition['clearance_diameter']=40 # The offset test profile needs its own explicit installation envelope.
    definition['cutting_primitives']=[dict(kind='cone',diameter=24,end_diameter=20,start=0,end=10,offset_u=4,offset_v=2),
                                      dict(kind='annulus',diameter=20,inner_diameter=8,start=10,end=20),
                                      dict(kind='cylinder',diameter=16,start=20,end=62)]
    definition['machining']=[dict(note='Illustrative source note, not vendor machining approval',tool='Illustrative tool reference')]
    path=tmp_path/'engineering.db';connection=sqlite3.connect(path);initialize_schema(connection)
    connection.execute('INSERT INTO cavities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (definition['id'],definition['label'],definition['family'],definition['unit_system'],definition['manufacturer'],definition['thread_note'],
         json.dumps(definition['stages']),json.dumps(definition['cutting_primitives']),json.dumps(definition['boundaries']),json.dumps(definition['machining']),
         definition['clearance_diameter'],definition['clearance_height'],1,'',1))
    for zone in definition['zones']:
        connection.execute('INSERT INTO cavity_interfaces VALUES (?,?,?,?,?,?,?,?)',
            (definition['id'],zone['id'],zone['start'],zone['end'],zone['diameter'],zone['offset_u'],zone['offset_v'],int(zone['clip_to_cut'])))
    connection.commit();connection.close();monkeypatch.setenv('PMC_ENGINEERING_DB',str(path))
    d=Design(name='Pinned source mapping',block=source.block,
             features=[dict(id='C1',kind='cavity',face='top',u=45,v=60,rotation=90,
                cavity_id=definition['id'],interface_nets={definition['zones'][0]['id']:'P',definition['zones'][1]['id']:'A'}),
                dict(id='D1',kind='drilling',face='top',u=80,v=60,diameter=8,depth=20,direction=[.6,0,-.8],circuit='P')],
             schematic_intent=dict(components=[dict(id='V1',placement_id='C1',cavity_id=definition['id'])]))
    facts=dict(id=definition['id'],label=definition['label'],thread_specification=definition['thread_note'],
               machining_operations=definition['machining'])
    manufacturing=dict(machining_profiles=[dict(feature='C1',definition=definition['id'],
        cutting_steps=definition['cutting_primitives'],hydraulic_interfaces=definition['zones'],definition_facts=facts)],
        drill_chart=[],native_recipes=[])
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE cavities SET active=0 WHERE id=?",(definition['id'],))
    monkeypatch.setenv('PMC_ENGINEERING_DB',str(tmp_path/'master-unavailable.db'))
    data,rows,operations=anchors(dict(resolved=d.model_dump(),manufacturing=manufacturing))
    assert data['F:C1:step:1:start']['point']==pytest.approx([43,64,100])
    assert data['F:C1:step:1:end']['point']==pytest.approx([43,64,90])
    assert data['F:C1:step:1:end']['diameter']==20
    cylinder=next(op for op in operations if op['id']=='C1:3')
    assert cylinder['end_diameter'] is None and cylinder['inner_diameter'] is None
    assert data['F:D1:end']['point']==pytest.approx([92,60,84])
    assert next(r for r in rows if r['id']=='C1')['model']==''
    table=Table(id='schedule',sheet='overview',kind='machining',position=(20,30),width=540)
    _,cells=table_cells(table,operations)
    text=' '.join(line for row in cells for cell in row for line in cell)
    assert 'ROTATION 90°' in text and 'LOCAL OFFSET U,V 4, 2 mm' in text
    assert 'inner Ø8' in text and 'AXIS 0.6, 0, -0.8' in text
    assert definition['label'] in text and definition['machining'][0]['note'] in text and definition['machining'][0]['tool'] in text
    assert '→ Ø0' not in text and 'inner Ø0' not in text


def test_dense_table_pagination_accounts_for_wrapped_rows(drawing):
    from manifold.drawing.schema import Table
    from manifold.drawing.render import fitting_rows,table_cells,row_height
    _,doc=drawing
    t=Table(id='table',sheet='overview',kind='porting',position=(20,35),width=100,height=3)
    rows=[dict(id=str(i),label='FEATURE-'+str(i),face='front',specification='Explicit reviewed source specification with several wrapped lines '*3,model='') for i in range(30)]
    count=fitting_rows(t,rows,280)
    _,cells=table_cells(t,rows[:count]);_,next_cells=table_cells(t,rows[:count+1])
    assert 1<count<30
    assert sum(row_height(t,c) for c in cells)<=280<sum(row_height(t,c) for c in next_cells)
