"""Reproducible source-defined density benchmark; not a reconstruction of unknown CT geometry."""
import json
import time
import argparse
from pathlib import Path
from manifold import projects,store
from manifold.schema import Design
from manifold.drawing import storage
from manifold.drawing.generate import snapshot,initial_edit,auto_annotations,add_tables,geometry_for
from manifold.drawing.pdf import export_pdf
from manifold.drawing.render import check_drawing


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-project',help='Regenerate drawings from an existing saved benchmark build without repeating CAD construction.')
    args=parser.parse_args()
    start=time.perf_counter();features=[]
    for face in ('top','bottom','front','back','left','right'):
        for i in range(5):
            for j in range(4):
                n=len(features)+1
                features.append(dict(id=f'H{n}',machining_id=f'H{n}',kind='mounting',face=face,u=60+i*60,
                    v=60+j*60 if face in ('top','bottom') else 30+j*30,diameter=6,depth=12))
    d=Design(name='V2.3 density benchmark — 120 explicit plain bores',block=dict(length=420,width=360,height=160,material='S50C'),features=features)
    if args.reuse_project:
        p=projects.snapshot(projects.read(args.reuse_project))
        if p['design']['name']!=d.name or len(p['design']['features'])!=120:
            raise ValueError('Reuse requires the identified 120-hole drawing benchmark project.')
    else:
        p=projects.save(d);p=projects.build(p['project_id'],p['revision'])
    built=time.perf_counter()
    source,solid=snapshot(p['project_id'],p['revision'])
    edit=initial_edit(source,'manufacturing','PMC-V23-DENSE');edit.annotations=auto_annotations(source,edit);add_tables(source,edit,'manufacturing')
    doc=storage.save_new(p['project_id'],source,edit,geometry_for(source,solid,edit.views),'manufacturing');generated=time.perf_counter()
    root=store.OUTPUT/'drawing-acceptance';root.mkdir(parents=True,exist_ok=True)
    data=export_pdf(doc);(root/'dense-manufacturing.pdf').write_bytes(data)
    result=dict(project_id=p['project_id'],drawing_id=doc['id'],build_status=p['build']['status'],features=len(features),
                sheets=len(edit.sheets),annotations=len(edit.annotations),pdf_bytes=len(data),build_seconds=None if args.reuse_project else round(built-start,3),
                reused_build=bool(args.reuse_project),
                generation_seconds=round(generated-built,3),pdf_seconds=round(time.perf_counter()-generated,3),issues=check_drawing(doc))
    (root/'density.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='issues'}));print(json.dumps(result['issues']))


if __name__=='__main__':main()
