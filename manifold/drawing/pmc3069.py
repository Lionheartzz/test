"""PMC26-3069 paper convention, measured from the supplied three A2 sheets.

Only presentation is reproduced. Every feature, dimension and specification comes
from the selected build. No reference-product geometry or identity is embedded.
Coordinates below are paper millimetres from the top-left of the sheet.
"""
import math
from collections import OrderedDict
from .schema import Sheet, View, Table, Annotation, Schematic
from .projection import projected

from .pmc_standard import STANDARD_NOTES
FACE_LETTERS = {'front':'A','bottom':'B','top':'C','left':'D','right':'E','back':'F'}
DATUM = {'front':'B:001','bottom':'B:010','top':'B:001','left':'B:001','right':'B:100','back':'B:011'}


def configure(source, edit):
    b=source['resolved']['block'];l,w,h=b['length'],b['width'],b['height']
    edit.template.layout='pmc3069'
    # The reference's tolerance grid and stock specifications are metric. An
    # inch-context manifold still has canonical mm geometry; do not mislabel it.
    edit.metadata.unit='mm'
    edit.template.name='PMC Manufacturing Drawing · PMC26-3069'
    edit.template.standard_notes=STANDARD_NOTES
    edit.sheets=[Sheet(id='overview',title='Manifold overview'),Sheet(id='coordinates',title='Machining coordinates'),Sheet(id='internal',title='Internal drilling')]
    edit.views=[];edit.tables=[];edit.schematics=[]
    # One common orthographic scale; select the largest preferred engineering
    # scale that fits the reference's six-view slots without crossing tables.
    limit=min(92/max(l,w),76.5/w,79/h)
    scale=next((s for s in (2,1,.75,.5,1/3,.25,.2,.1,.05,.025,.01) if s<=limit),limit)
    iso_points=[projected((x,y,z),'iso') for x in (0,l) for y in (0,w) for z in (0,h)]
    iw=max(p[0] for p in iso_points)-min(p[0] for p in iso_points)
    ih=max(p[1] for p in iso_points)-min(p[1] for p in iso_points)
    iso_limit=min(120/iw,119/ih)
    iso_scale=next((s for s in (2,1,.75,.5,1/3,.25,.2,.1,.05,.025,.01) if s<=iso_limit),iso_limit)
    for sheet in edit.sheets:
        detail=sheet.id!='overview'
        # Same orthographic topology and paper regions as PMC26-3069. The second
        # and third sheets use its slightly shifted machining-view positions.
        centers={'left':103 if detail else 84,'front':239 if detail else 208,'right':366 if detail else 354,'back':500 if detail else 489}
        top_y=30 if detail else 24
        row_y=146 if detail else 153
        positions={face:(centers[face]-(w if face in ('left','right') else l)*scale/2,row_y) for face in centers}
        positions['top']=(centers['front']-l*scale/2,top_y)
        positions['bottom']=(centers['front']-l*scale/2,278)
        for face in ('top','left','front','right','back','bottom'):
            edit.views.append(View(id=(face if not detail else sheet.id+'-'+face),sheet=sheet.id,projection=face,
                position=positions[face],scale=scale,hidden=sheet.id=='internal',centerlines=True,
                presentation='pmc-overview' if not detail else 'pmc-coordinate' if sheet.id=='coordinates' else 'pmc-internal'))
        edit.views.append(View(id=sheet.id+'-iso',sheet=sheet.id,projection='iso',position=(456,20),scale=iso_scale,
            hidden=detail,centerlines=False,presentation='pmc-internal' if detail else 'pmc-overview'))
        edit.tables.append(Table(id=sheet.id+'-portings',sheet=sheet.id,kind='porting',position=(313,247),width=279,
            row_height=5.6,height=3.5,count=200,presentation='pmc-portings'))
    assets=source['authored'].get('schematics',[])
    if assets:edit.schematics=[Schematic(id=sheet.id+'-schematic',sheet=sheet.id,asset=assets[0]['sha256'],position=(20,8),width=94,height=103) for sheet in edit.sheets]
    return edit


def _spread(values,minimum=4.5):
    """Small extension-line jogs keep neighbouring ordinate numbers readable."""
    out=[]
    for value in values:out.append(max(value,(out[-1]+minimum) if out else value))
    if out:
        shift=(out[-1]-values[-1])/2
        out=[x-shift for x in out]
    return out


def annotations(source,edit,data,rows):
    from .render import text_width
    items=[]
    b=source['resolved']['block'];l,w,h=b['length'],b['width'],b['height']
    # Corner extrema in outward-view screen space, plus reference-style datums.
    extrema={'front':('B:000','B:100','B:001'),'back':('B:110','B:010','B:111'),
        'left':('B:010','B:000','B:011'),'right':('B:100','B:110','B:101'),
        'top':('B:001','B:101','B:011'),'bottom':('B:010','B:110','B:000')}
    for view in edit.views:
        face=view.projection
        if face not in extrema:continue
        face_rows=[r for r in rows if r['face']==face]
        label_boxes=[]
        for index,row in enumerate(face_rows):
            # The caption is evaluated from the source on each rendering. Paper
            # offsets remain editable and do not alter the feature position.
            anchor=data['F:'+row['id']];px,py=projected(anchor['point'],face)
            caption=anchor['label'] if view.presentation=='pmc-overview' else anchor['machining_label']
            length=text_width(caption,3.1)
            offset=(2.4,-2.3)
            for level in range(12):
                offset=(2.4,-2.3-level*4.2)
                box=(px*view.scale+offset[0],-py*view.scale+offset[1]-3.1,px*view.scale+offset[0]+length,-py*view.scale+offset[1]+.4)
                if not any(max(box[0],b[0])<min(box[2],b[2]) and max(box[1],b[1])<min(box[3],b[3]) for b in label_boxes):break
            label_boxes.append(box)
            items.append(Annotation(id=f'auto:{view.id}:{row["id"]}:label',kind='label' if level==0 else 'leader',sheet=view.sheet,view=view.id,
                anchors=['F:'+row['id']],position=offset,height=3.1,automatic=True))
        if view.presentation=='pmc-overview':
            # PMC overview dimensions the three stock axes once, beside the
            # front/right views. Coordinate sheets carry the detailed values.
            a,x,y=extrema[face]
            for axis,target,offset in ([('x',x,(0,10))] if face=='front' else [('x',x,(0,10)),('y',y,(-17,0))] if face=='right' else []):
                items.append(Annotation(id=f'auto:{view.id}:overall:{axis}',kind='dimension',sheet=view.sheet,view=view.id,
                    anchors=[a,target],measure=axis,position=offset,height=3.8,automatic=True))
            continue
        datum=DATUM[face];base=projected(data[datum]['point'],face)
        corner_points=[(key,projected(a['point'],face)) for key,a in data.items() if key.startswith('B:')]
        bounds=[min(p[0] for _,p in corner_points),min(p[1] for _,p in corner_points),max(p[0] for _,p in corner_points),max(p[1] for _,p in corner_points)]
        for axis in ('x','y'):
            index=0 if axis=='x' else 1
            candidates=[('F:'+r['id'],projected(data['F:'+r['id']]['point'],face)) for r in face_rows]
            far=max(corner_points,key=lambda v:abs(v[1][index]-base[index]))
            candidates=[(datum,base),*candidates,far]
            unique=OrderedDict()
            for key,p in candidates:unique.setdefault(round(abs(p[index]-base[index]),5),(key,p))
            values=sorted(unique.values(),key=lambda v:v[1][index],reverse=axis=='y')
            screen=[(p[0]-bounds[0])*view.scale if axis=='x' else (bounds[3]-p[1])*view.scale for _,p in values]
            spread=_spread(screen)
            for (key,p),before,after in zip(values,screen,spread):
                if axis=='x':offset=(after-before,-8)
                else:offset=((bounds[2]-bounds[0])*view.scale+8 if face in ('left','back') else -8,after-before)
                ident=key.replace('F:','').replace('B:','corner-')
                items.append(Annotation(id=f'auto:{view.id}:{ident}:{axis}',kind='dimension',sheet=view.sheet,view=view.id,
                    anchors=[datum,key],measure=axis,ordinate=True,position=offset,height=3.3,precision=2,automatic=True))
    return items
