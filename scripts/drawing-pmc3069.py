"""Generate a PMC26-3069-format drawing from an existing saved Project build."""
import argparse
import json
from pathlib import Path
from manifold import projects
from manifold.drawing import storage
from manifold.drawing.generate import snapshot,initial_edit,auto_annotations,add_tables,geometry_for
from manifold.drawing.pdf import export_pdf
from manifold.drawing.render import check_drawing


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    parser.add_argument('--number',default='')
    parser.add_argument('--title',default='',help='Optional drawing title presentation; does not rename the source Manifold')
    parser.add_argument('--output',default='output/pmc3069-review/manufacturing.pdf')
    args=parser.parse_args()
    project=projects.snapshot(projects.read(args.project))
    source,solid=snapshot(args.project,project['revision'])
    edit=initial_edit(source,'manufacturing',args.number)
    if args.title:edit.metadata.title=args.title
    edit.annotations=auto_annotations(source,edit);add_tables(source,edit,'manufacturing')
    drawing=storage.save_new(args.project,source,edit,geometry_for(source,solid,edit.views),'manufacturing')
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(export_pdf(drawing))
    result=dict(project=args.project,drawing=drawing['id'],source_build=source['build_id'],sheets=len(edit.sheets),
        views=len(edit.views),annotations=len(edit.annotations),issues=check_drawing(drawing))
    path.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
