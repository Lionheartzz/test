"""PMC26-3069 paper convention, measured from the supplied three A2 sheets.

Only presentation is reproduced. Every feature, dimension and specification comes
from the selected build. No reference-product geometry or identity is embedded.
Coordinates below are paper millimetres from the top-left of the sheet.
"""
import math
import re
from collections import OrderedDict
from .schema import Sheet, View, Table, Annotation, Schematic
from .projection import projected

INK = '#151515'
MAGENTA = '#a72c6f'
GREY = '#69666d'
FACE_LETTERS = {'front':'A','bottom':'B','top':'C','left':'D','right':'E','back':'F'}
DATUM = {'front':'B:001','bottom':'B:010','top':'B:001','left':'B:001','right':'B:100','back':'B:011'}


def configure(source, edit):
    b=source['resolved']['block'];l,w,h=b['length'],b['width'],b['height']
    edit.template.layout='pmc3069'
    # The reference's tolerance grid and stock specifications are metric. An
    # inch-context manifold still has canonical mm geometry; do not mislabel it.
    edit.metadata.unit='mm'
    edit.template.name='PMC Manufacturing Drawing · PMC26-3069'
    edit.template.standard_notes='BREAK ALL SHARP EDGES.\nSURFACE FINISH:\nGENERAL TOLERANCE IS APPLICABLE TO\nALL DIMENSIONS WITHOUT SPECIFICATIONS.'
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


def compact_labels(labels):
    """Lossless consecutive identifiers, e.g. H1-H20; never guessed members."""
    ordered=sorted(set(labels),key=lambda s:[int(x) if x.isdigit() else x for x in re.split(r'(\d+)',s)])
    result=[];i=0
    while i<len(ordered):
        m=re.fullmatch(r'(.*?)(\d+)',ordered[i]);j=i+1
        if m:
            while j<len(ordered) and ordered[j]==m[1]+str(int(m[2])+j-i):j+=1
        if j-i>=3:result.append(ordered[i]+'-'+ordered[j-1]);i=j
        else:result.append(ordered[i]);i+=1
    return ', '.join(result)


def porting_groups(rows,table,all_groups=False):
    order={key:i for i,key in enumerate(table.order)}
    selected=sorted(rows,key=lambda r:(order.get(r['id'],len(order)),{'cavity':0,'port':1,'drilling':2,'mounting':3}.get(r.get('kind'),4),r['id']))
    grouped=OrderedDict()
    for row in selected:
        spec=row.get('pmc_specification',row['specification'])
        remark=table.remarks.get(row['id'],'')
        key=(row.get('kind'),spec,remark)
        grouped.setdefault(key,[]).append(row)
    result=[]
    def caption(row):
        machine=row.get('machining_label',row['label'])
        return row['label'] if machine==row['label'] else f'{row["label"]} ({machine})'
    for (_,spec,remark),members in grouped.items():
        batches=[[]]
        for member in members:
            if batches[-1] and len(compact_labels([caption(m) for m in [*batches[-1],member]]))>65:batches.append([])
            batches[-1].append(member)
        for batch in batches:
            result.append(dict(ids=[m['id'] for m in batch],labels=compact_labels([caption(m) for m in batch]),
                specification=spec+(' / '+remark if remark else '')))
    return result if all_groups else result[table.start:table.start+table.count]


def table_layout(table,rows):
    from .render import wrap
    groups=porting_groups(rows,table)
    # Three repeated ID/specification pairs, column-major, as in the reference.
    per_column=max(1,math.ceil(len(groups)/3))
    col_width=table.width/6
    grid=[]
    for i in range(max(15,per_column)):
        cells=[];ids=[]
        for col in range(3):
            index=col*per_column+i
            row=groups[index] if i<per_column and index<len(groups) else None
            cells.extend([wrap(row['labels'],col_width-2,table.height),wrap(row['specification'],col_width-2,table.height)] if row else [[],[]])
            if row:ids.extend(row['ids'])
        grid.append(dict(cells=cells,height=max(table.row_height,max(map(len,cells),default=1)*table.height*1.15+1),ids=ids))
    # The reference keeps the PORTINGS lower rule aligned with the logo area;
    # distribute spare space over its rows rather than leave an unrelated gap.
    extra=max(0,111.5-sum(r['height'] for r in grid))/len(grid)
    for row in grid:row['height']+=extra
    return grid


def add_overflow(source,edit,rows):
    """Additional sheets only when the source PORTINGS content actually overflows."""
    from .schema import Sheet
    groups=porting_groups(rows,edit.tables[0],all_groups=True);limit=min(200,len(groups))
    # Preserve the reference table region on all three sheets. Find a batch that
    # fits there; remaining real data gets a continuation rather than clipping.
    while limit>1:
        probe=edit.tables[0].model_copy(update={'count':limit})
        if sum(r['height'] for r in table_layout(probe,rows))+5.5<=117.001:break
        limit-=1
    for table in edit.tables:table.count=max(1,limit)
    start=max(1,limit)
    while start<len(groups):
        limit=min(200,len(groups)-start)
        probe=edit.tables[0].model_copy(update={'start':start,'count':limit})
        while limit>1 and sum(r['height'] for r in table_layout(probe,rows))+5.5>117.001:
            limit-=1;probe.count=limit
        sid=f'portings-{start}';edit.sheets.append(Sheet(id=sid,title='Portings continued'))
        edit.tables.append(Table(id=sid+'-table',sheet=sid,kind='porting',position=(313,247),width=279,
            row_height=5.6,height=3.5,start=start,count=max(1,limit),presentation='pmc-portings'))
        start+=max(1,limit)


def furniture(doc,edit,sheet,text,poly,rect,image):
    """Measured PMC borders and title cells; no application status on the paper."""
    width,height=594,420
    from .render import wrap
    rect(2,2,590,416)
    # Top-right stock summary, repeated on every reference sheet.
    xs=[399,445,501,547,592];ys=[2,7,12]
    for y in ys:poly([[xs[0],y],[xs[-1],y]],MAGENTA,.18)
    for x in xs:poly([[x,2],[x,12]],MAGENTA,.18)
    block=doc['source']['resolved']['block']
    values=[edit.metadata.number,f'L{block["length"]:g}XW{block["width"]:g}XH{block["height"]:g}',block['material'],str(edit.metadata.quantity)]
    for i,label in enumerate(('DRAWING NO','SIZE','MATERIAL','QTY')):
        center=(xs[i]+xs[i+1])/2
        text(center,6.2,label,3.5,align='center',color=MAGENTA)
        text(center,11.2,values[i],min(3.3,(xs[i+1]-xs[i]-2)/max(1,len(values[i]))*1.6),align='center',color=MAGENTA)
    # Notes, tolerance grid, ownership notice, alteration grid, design signoff,
    # company/logo and title block keep the reference's exact paper regions.
    text(4,395,'NOTE:',3.3)
    notes=edit.template.standard_notes.splitlines()
    for i,line in enumerate(notes):text(5 if i<3 else 14,400+i*5.2,('•  ' if i<3 else '')+line,3.1)
    if edit.metadata.notes:text(5,374,edit.metadata.notes,3,max_width=110)
    rect(118,383,117,35)
    poly([[118,389],[235,389]],INK,.18)
    text(176.5,388,'GENERAL TOLERANCE',3.7,align='center')
    # Linear tolerance bands, retained as reviewed template data.
    tx=[118,137,146,156,172,187,205,224,235]
    for y in (396,402):poly([[118,y],[235,y]],INK,.18)
    for x in tx[1:-1]:poly([[x,389],[x,402]],INK,.18)
    for i,v in enumerate(['SIZE','1-6','>6-30','>30-120','>120-315','>315-1000','>1000-2000','>2000']):text((tx[i]+tx[i+1])/2,394.6,v,2.45,align='center')
    for i,v in enumerate(['MACHINING',*edit.template.linear_tolerances]):text((tx[i]+tx[i+1])/2,400.5,v,2.45,align='center')
    bx=[118,137,146,156,172,180,197,211,224,235]
    for x in bx[1:]:poly([[x,402],[x,418]],INK,.18)
    poly([[118,413],[180,413]],INK,.18);poly([[197,413],[235,413]],INK,.18)
    text(127.5,406,'CHAMFER/',2.4,align='center');text(127.5,409.5,'RADII(SIZE)',2.4,align='center')
    for i,v in enumerate(('0.5-3','>3-6','>6-30','>30')):text((bx[i+1]+bx[i+2])/2,408.8,v,2.45,align='center')
    for i,v in enumerate(('MACHINING','±0.2','±0.5','±1','±2')):text((bx[i]+bx[i+1])/2,417,v,2.45,align='center')
    text(188.5,405,'ANGLE',2.4,align='center');text(188.5,408.5,'(SHORTER',2.3,align='center');text(188.5,412,'SIDE)',2.3,align='center')
    for i,v in enumerate(('1-10','>10-50','>50')):text((bx[i+6]+bx[i+7])/2,408.8,v,2.45,align='center')
    for i,v in enumerate(('±60′','±30′','±20′')):text((bx[i+6]+bx[i+7])/2,417,v,2.45,align='center')
    rect(235,383,56,35)
    rights=['ALL TECHNICAL DATA DISCLOSED','HERE IN IS THE PROPERTY OF','POWER & MOTION CONTROL PTE LTD','AND SHALL NOT BE USED BY OTHERS','FOR MANUFACTURE, PROCUREMENT,','OR DISCLOSURE WITHOUT THE','WRITTEN PERMISSION OF THE OWNER.']
    for i,line in enumerate(rights):text(237,386.5+i*4.1,line,2.3)
    text(237,416.8,'ALL RIGHTS RESERVED.',3.4)
    rect(291,383,108,35)
    rx=[291,301,320,351,363,378,399]
    for x in rx[1:-1]:poly([[x,383],[x,411]],INK,.18)
    for y in (389,396,403.5,411):poly([[291,y],[399,y]],INK,.18)
    for i,v in enumerate(('REV','DATE','DESCRIPTION','BY',"CHK’D","APP’D")):text((rx[i]+rx[i+1])/2,408.6,v,2.6,align='center')
    if edit.metadata.revision_note:
        for x,v,maxw in ((296,edit.metadata.revision,8),(310.5,edit.metadata.date,17),(335.5,edit.metadata.revision_note,28),(357,edit.metadata.drawn_by,10)):
            text(x,386.7,v,2.2,align='center',max_width=maxw)
    text(345,416,'ALTERATION',2.9,align='center')
    rect(399,383,51,35)
    for y in (389,396,403.5,411):poly([[399,y],[450,y]],INK,.18)
    for x in (416,430):poly([[x,383],[x,411]],INK,.18)
    text(423,387,'BY',2.8,align='center');text(440,387,'DATE',2.8,align='center')
    for y,label,person in ((394,'DESIGN',edit.metadata.designed_by),(401,'DRAWN',edit.metadata.drawn_by),(408.5,'CHECKED',edit.metadata.checked_by)):
        text(407.5,y,label,2.7,align='center');text(423,y,person,2.5,align='center');text(440,y,edit.metadata.date if person else '',2.3,align='center')
    text(408,416,'APPROVED',2.6,align='center');text(437,416,edit.metadata.approved_by,2.5,align='center')
    rect(450,364,142,54);poly([[513,364],[513,383]],INK,.18)
    if edit.template.show_logo:image(456,365,48,48*16.5/58.5)
    text(515,367,'ADDRESS :',2.8,color=GREY)
    contact=[edit.template.company,edit.template.address,'TEL: '+edit.template.telephone+'  FAX: '+edit.template.fax,'EMAIL: '+edit.template.email,'WEBSITE: '+edit.template.website]
    for i,line in enumerate(contact):text(534,367+i*3.2,line,2.05,color=GREY,max_width=56)
    for y in (383,396,408):poly([[450,y],[592,y]],INK,.18)
    poly([[487,396],[487,418]],INK,.18)
    for x in (468,543,567):poly([[x,408],[x,418]],INK,.18)
    text(452,387.5,'TITLE :',3.8,color=GREY);text(517,391,edit.metadata.title,4.2,align='center',color=GREY,max_width=125)
    text(490,399.5,'DWG NO. :',2.9,color=GREY);text(539,405.2,edit.metadata.number,4.2,align='center',color=GREY)
    text(451,399.5,'THIRD ANGLE PROJ.',2.7,color=GREY)
    # The PMC reference places the circular end view to the left of the frustum.
    for radius in (2.6,1.8):poly([[461+radius*math.cos(i*math.pi/24),404+radius*math.sin(i*math.pi/24)] for i in range(49)],INK,.18)
    poly([[468,402.5],[476,401.5],[476,406.5],[468,405.5],[468,402.5]],INK,.18)
    poly([[457,404],[478,404]],MAGENTA,.15)
    for x,label in ((459,'SCALE'),(477.5,'SHEET'),(555,'MATERIAL')):text(x,411.5,label,2.7,align='center',color=GREY)
    standard=next((v.scale for v in edit.views if v.projection!='iso' and v.sheet==sheet.id),None)
    scale=(f'{standard:g}:1' if standard>=1 else f'1:{1/standard:g}') if standard else 'NTS'
    text(459,416.5,scale,2.9,align='center',color=GREY)
    text(477.5,416.5,f'{edit.sheets.index(sheet)+1} OF {len(edit.sheets)}',2.9,align='center',color=GREY)
    text(489,412,"ALL DIMENSIONS ARE IN 'MM'",2.05,color=GREY);text(489,416,'UNLESS OTHERWISE SPECIFIED',2.05,color=GREY)
    material_size=2.6
    while material_size>1.5 and len(wrap(block['material'],22,material_size))>2:material_size-=.1
    material_lines=wrap(block['material'],22,material_size)
    for i,line in enumerate(material_lines):text(555,414.5+i*3,line,material_size,align='center',color=GREY)
    text(579.5,416.5,edit.metadata.revision,2.8,align='center',color=GREY)
