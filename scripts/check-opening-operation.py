"""Isolate saved native CAD opening operations; no routing or layout search."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/runtime-checks/single-work-root-correction-20261014/opening'


def main():
    from manifold.cad import cq
    from manifold.cad_geometry import checked_intersection,checked_shape,solid_volume
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('prepare','common-section','operand-section','serial-section','clean-section'))
    parser.add_argument('--pair',type=int,default=0);args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.mode=='prepare':
        import itertools
        from manifold.schema import Design,CavityDefinition
        from manifold.geometry import feature_geometry
        old=ROOT/'output/runtime-checks/single-work-20261014/final-focused/test_rigid_three_net_calculati0/bounded-exact.json'
        saved=json.loads(old.read_text());request=json.loads((Path(saved['evidence'])/'request.json').read_text())['payload']
        d=Design.model_validate(saved['checkpoint']['design']);defs={k:CavityDefinition.model_validate(v) for k,v in request['definitions'].items()}
        _,nodes,circuits,_,_,placements,_=feature_geometry(d,defs,{},{});rows=[]
        for a,b in itertools.combinations(nodes,2):
            if circuits[a]!=circuits[b]:continue
            common=checked_intersection(nodes[a],nodes[b],'diagnostic.common')
            volume=solid_volume(common,'diagnostic.volume')
            if volume<=1e-6:continue
            i=len(rows)
            for tag,shape in (('a',nodes[a]),('b',nodes[b]),('common',common)):shape.exportBrep(str(OUT/f'{i}-{tag}.brep'))
            rows.append(dict(nodes=[a,b],volume=volume,directions=[placements[k.split(':')[0]]['direction'] for k in (a,b)]))
        (OUT/'pairs.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows));return
    row=json.loads((OUT/'pairs.json').read_text())[args.pair]
    a,b,common=[cq.Shape.importBrep(str(OUT/f'{args.pair}-{tag}.brep')) for tag in ('a','b','common')]
    started=time.monotonic();events=[]
    def event(name,**kw):
        events.append(dict(operation=name,seconds=time.monotonic()-started,**kw))
        (OUT/f'{args.pair}-{args.mode}.json').write_text(json.dumps(dict(pair=row,events=events),indent=2))
    common=cq.Compound.makeCompound(common.Solids());checked_shape(common,'diagnostic.solid_common')
    center=common.Center();size=common.BoundingBox().DiagonalLength*4+10;areas=[]
    for direction in row['directions']:
        event('plane',direction=direction)
        plane=cq.Face.makePlane(size,size,center,cq.Vector(*direction))
        if args.mode=='serial-section':
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
            event('serial_common_plane_boolean')
            section=common._bool_op(tuple(common.Solids()),(plane,),BRepAlgoAPI_Common(),parallel=False)
            checked_shape(section,'diagnostic.serial_section')
        elif args.mode=='clean-section':
            event('clean_common');clean=common.clean()
            event('clean_common_plane_boolean');section=checked_intersection(clean,plane,'diagnostic.clean_section')
        elif args.mode=='common-section':
            event('common_plane_boolean');section=checked_intersection(common,plane,'diagnostic.common_section')
        else:
            event('operand_plane_boolean');section=checked_intersection(a,plane,'diagnostic.operand_section')
            event('section_other_operand_boolean');section=checked_intersection(section,b,'diagnostic.clip_section')
        event('faces_area');area=sum(f.Area() for f in section.Faces());areas.append(area);event('area',value=area)
    event('completed',opening=min(areas))
    print(json.dumps(dict(pair=args.pair,mode=args.mode,areas=areas,seconds=time.monotonic()-started)))


if __name__=='__main__':main()
