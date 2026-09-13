"""Create a separate, identified local acceptance project; never edit a user's manifold."""
import json
from manifold import projects,store
from manifold.schema import Design
from manifold.drawing import storage
from manifold.drawing.generate import snapshot,initial_edit,auto_annotations,add_tables,geometry_for

def main():
    d=Design(name='V2.3 acceptance — source-linked drawing',block=dict(length=105,width=95,height=50,material='S50C'),
             features=[dict(id='P1',kind='port',face='top',u=52,v=55,circuit='P',diameter=12,depth=30,size='Explicit Ø12 bore',connects_to=['T1']),
                       dict(id='T1',kind='port',face='front',u=52,v=25,circuit='P',diameter=10,depth=65,size='Explicit Ø10 bore',connects_to=['P1'])])
    fixture=store.OUTPUT/'drawing-acceptance'/'fixture.json'
    if fixture.exists():
        old=json.loads(fixture.read_text(encoding='utf-8'))
        p=projects.snapshot(projects.read(old['project_id']))
        p=projects.save(d,p['project_id'],p['revision'])
    else:p=projects.save(d)
    p=projects.build(p['project_id'],p['revision'])
    source,solid=snapshot(p['project_id'],p['revision'])
    docs={}
    out=store.OUTPUT/'drawing-acceptance';out.mkdir(parents=True,exist_ok=True)
    from manifold.drawing.pdf import export_pdf
    for kind in ('customer','manufacturing'):
        edit=initial_edit(source,kind,'PMC-V23-'+kind.upper());edit.annotations=auto_annotations(source,edit);add_tables(source,edit,kind)
        doc=storage.save_new(p['project_id'],source,edit,geometry_for(source,solid,edit.views),kind)
        docs[kind]=doc['id'];(out/(kind+'.pdf')).write_bytes(export_pdf(doc))
    (out/'fixture.json').write_text(json.dumps(dict(project_id=p['project_id'],drawings=docs)),encoding='utf-8')
    print(json.dumps(dict(project_id=p['project_id'],drawings=docs,status=p['build']['status'])))

if __name__=='__main__':main()
