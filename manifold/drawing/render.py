"""One paper scene for SVG editing and vector PDF; all dimensions evaluated here."""
import base64
from functools import lru_cache
from html import escape
import io
import math
import re
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab import rl_config
from .schema import Edit
from .generate import anchors, paper, projection_key
from .projection import projected


@lru_cache
def font_path(cjk=False):
    candidates = [Path('C:/Windows/Fonts/simhei.ttf')] if cjk else [Path('C:/Windows/Fonts/arial.ttf')]
    candidates += [Path(p)/'Vera.ttf' for p in rl_config.TTFSearchPath]
    return next(p for p in candidates if p.is_file())


@lru_cache
def font_name(cjk=False):
    name='PMC-CJK' if cjk else 'PMC-Text'
    pdfmetrics.registerFont(TTFont(name,str(font_path(cjk))))
    return name


def text_width(text,height):
    return pdfmetrics.stringWidth(text,font_name(any(ord(c)>0x2e80 for c in text)),height)


def wrap(text,width,height):
    lines=[]
    for paragraph in str(text).split('\n'):
        if not paragraph:
            lines.append(''); continue
        line=''
        for word in paragraph.split(' '):
            candidate=(line+' '+word).strip()
            if text_width(candidate,height)<=width:
                line=candidate; continue
            if line: lines.append(line)
            line=''
            # Also wrap unspaced IDs and CJK without dropping text.
            for char in word:
                if line and text_width(line+char,height)>width:
                    lines.append(line); line=''
                line+=char
        lines.append(line)
    return lines


def point(view,geometry,world):
    x,y=projected(world,view.projection)
    left,bottom,right,top=geometry['bounds']
    return [view.position[0]+(x-left)*view.scale,view.position[1]+(top-y)*view.scale]


def measure(item,view,data):
    values=[data.get(k) for k in item.anchors]
    if any(v is None for v in values):
        return None
    if item.measure in ('x','y','aligned'):
        a,b=[projected(v['point'],view.projection) for v in values]
        dx,dy=b[0]-a[0],b[1]-a[1]
        return abs(dx) if item.measure=='x' else abs(dy) if item.measure=='y' else math.hypot(dx,dy)
    value=values[0].get('diameter' if item.measure=='radius' else item.measure)
    return value/2 if item.measure=='radius' and value is not None else value


def dimension_text(value,item,unit):
    angular=item.measure=='angle'
    n=value if angular or unit=='mm' else value/25.4
    prefix={'diameter':'Ø','radius':'R','depth':'DEPTH ','angle':'AXIS / Z '}.get(item.measure,'')
    return prefix+f'{n:.{item.precision}f}'+('°' if angular else '')


def issue(code,message,item=None,severity='warning'):
    return dict(code=code,message=message,item=item,severity=severity)


def check_drawing(doc,layouts=True):
    from .storage import source_current
    edit=Edit.model_validate(doc['edit'])
    data,rows,operations=anchors(doc['source'])
    issues=[]
    if not any(v.visible for v in edit.views):issues.append(issue('views-missing','Add at least one visible engineering view before release.',severity='error'))
    if not source_current(doc):issues.append(issue('source-changed','Source manifold/build changed. Regenerate before issuing a current drawing.',severity='error'))
    validation=doc['source']['validation']
    if validation.get('status')!='PASS':
        issues.append(issue('engineering-fail','Source build has engineering FAILs. Correct and validate the manifold before release.',severity='error'))
    if not validation.get('manufacturing_ready',False) and doc['kind']=='manufacturing':
        issues.append(issue('manufacturing-review','Source manufacturing readiness is unresolved. Review pinned machining/plug data and record any permitted exception.'))
    for index,check in enumerate(validation.get('checks',[])):
        if check.get('status')=='WARNING':issues.append(issue('engineering-warning:'+str(index),check.get('message','Source engineering warning')+' Items: '+', '.join(check.get('items',[]))))
    for index,review in enumerate(doc['source']['resolved'].get('review_items',[])):
        if review['status']=='open':issues.append(issue('source-review:'+str(index),'Source engineering review '+review['id']+': '+review['description'],severity='error' if review['severity']=='blocking' else 'warning'))
    if not edit.template.tolerance_confirmed:
        issues.append(issue('tolerance-review','Confirm the template tolerance/standard notes apply to this drawing, or record an exception.'))
    viewmap={v.id:v for v in edit.views}
    for item in edit.annotations:
        if not item.visible:continue
        if item.id in doc.get('broken',{}) or any(k not in data for k in item.anchors):
            issues.append(issue('broken:'+item.id,'Broken engineering reference. Rebind or delete this annotation; it is excluded from current dimensions.',item.id,'error'))
        elif item.kind=='dimension' and measure(item,viewmap[item.view],data) is None:
            issues.append(issue('dimension:'+item.id,'This anchor does not provide the requested engineering measurement.',item.id,'error'))
        if item.kind in ('label','leader') and item.text and item.anchors and item.text!=data.get(item.anchors[0],{}).get('label'):
            issues.append(issue('label-override:'+item.id,'Label uses manually entered text. Review it against the linked source before release.',item.id))
        if item.height<2.5:issues.append(issue('small:'+item.id,'Text below 2.5 mm; check print readability.',item.id))
    for view in edit.views:
        if not view.visible:continue
        geometry=doc['geometry'].get(projection_key(view))
        if not geometry:
            issues.append(issue('projection:'+view.id,'Projection/section must be regenerated before use.',view.id,'error'));continue
        w,h=paper(next(s for s in edit.sheets if s.id==view.sheet))
        b=geometry['bounds']
        if view.position[0]<10 or view.position[1]<20 or view.position[0]+(b[2]-b[0])*view.scale>w-10 or view.position[1]+(b[3]-b[1])*view.scale>h-65:
            issues.append(issue('bounds:'+view.id,'View overlaps the paper margin/title block. Move, scale, or place it on another sheet.',view.id,'error'))
    displayed=set()
    for table in edit.tables:
        if table.visible and table.kind=='porting':
            if table.presentation=='pmc-portings':
                from .pmc3069 import porting_groups
                displayed.update(key for r in porting_groups(rows,table) for key in r['ids'])
            else:displayed.update(r['id'] for r in table_rows(table,rows,operations))
    if any(r['id'] not in displayed for r in rows):
        issues.append(issue('porting-coverage','Some features are missing from the visible porting tables. Add/extend a table or record the intended omission.'))
    if doc['kind']=='manufacturing':
        covered={r['id'] for t in edit.tables if t.visible and t.kind=='machining' for r in table_rows(t,rows,operations)}
        if any(r['id'] not in covered for r in operations):
            issues.append(issue('machining-coverage','Verify machining information is complete in the referenced cavity specifications and the dimensioned views; add sourced detail dimensions or a supplemental schedule where needed.' if edit.template.layout=='pmc3069' else 'Some machining operations are missing from the visible schedules. Add a continued table.'))
    for schematic in edit.schematics:
        if not schematic.visible:continue
        try: asset_image(doc,schematic)
        except (ValueError,OSError,RuntimeError):issues.append(issue('asset:'+schematic.id,'Schematic page is missing, invalid or outside its page/crop bounds.',schematic.id,'error'))
    if layouts:
        for sheet in edit.sheets:issues.extend(scene(doc,sheet.id)['issues'])
    return issues


def table_rows(table,rows,operations):
    source=list(rows if table.kind=='porting' else operations)
    order={key:i for i,key in enumerate(table.order)}
    source.sort(key=lambda r:(order.get(r['id'],len(order)),r['face'],[int(s) if s.isdigit() else s for s in re.split(r'(\d+)',r['id'])]))
    return source[table.start:table.start+table.count]


def table_cells(table,rows):
    headers=['ID / FACE','SPECIFICATION / SOURCE DATA','REMARKS'] if table.kind=='porting' else ['ID / OP / FACE','U / V mm','CUT Ø / DEPTH mm','SPECIFICATION / REMARKS']
    fractions=[.16,.62,.22] if table.kind=='porting' else [.16,.16,.24,.44]
    cells=[headers]
    for row in rows:
        if table.kind=='porting':
            values=[row['label']+' / '+row['face'],row['specification']+((' / '+row['model']) if row['model'] else ''),table.remarks.get(row['id'],'')]
        else:
            spec=row['specification']
            if row.get('tip_angle') is not None:spec+=f' / TIP {row["tip_angle"]:g}°'
            if row.get('offset_u') or row.get('offset_v'):
                spec+=f' / LOCAL OFFSET U,V {row["offset_u"]:g}, {row["offset_v"]:g} mm / ROTATION {row.get("rotation",0):g}° in face U,V'
            if sum(abs(x)>1e-5 for x in row['direction'])>1:spec+=' / AXIS '+', '.join(f'{x:.6g}' for x in row['direction'])
            if row.get('machining_notes'):spec+=' / '+row['machining_notes']
            if row.get('tooling'):spec+=' / SOURCE TOOLING: '+'; '.join(row['tooling'])
            profile=f'{row["profile"]} Ø{row["diameter"]:g}'
            if row.get('end_diameter') is not None:profile+=f' → Ø{row["end_diameter"]:g}'
            if row.get('inner_diameter') is not None:profile+=f' / inner Ø{row["inner_diameter"]:g}'
            values=[f'{row["label"]} / {row["operation"]} / {row["face"]}',f'{row["u"]:g} / {row["v"]:g}',profile+f' / {row["start"]:g}–{row["end"]:g}',spec+' '+table.remarks.get(row['id'],'')]
        cells.append(values)
    widths=[table.width*f for f in fractions]
    return widths,[([wrap(value,w-4,table.height) for value,w in zip(values,widths)]) for values in cells]


def row_height(table,lines):
    return max(table.row_height,max(map(len,lines))*table.height*1.35+3)


def fitting_rows(table,rows,available):
    _,cells=table_cells(table,rows)
    height=row_height(table,cells[0]);count=0
    for lines in cells[1:]:
        height+=row_height(table,lines)
        if height>available:break
        count+=1
    return count


def asset_file(doc,asset):
    from ..schema import SchematicAsset
    from ..workflow import asset_path
    from .generate import digest
    row=next((a for a in doc['source']['authored'].get('schematics',[]) if a['sha256']==asset),None)
    if row is None:raise ValueError('Schematic must belong to this drawing source')
    path=asset_path(SchematicAsset.model_validate(row))
    if path.is_symlink() or not path.is_file() or digest(path.read_bytes())!=asset:
        raise ValueError('Schematic source is missing or changed')
    return path,row


def asset_image(doc,item):
    from PIL import Image
    path,row=asset_file(doc,item.asset)
    if row['media_type']=='application/pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(str(path)) as pdf:
            if item.page>=len(pdf):raise ValueError('Schematic page does not exist')
            page=pdf[item.page]
            scale=min(2,1600/max(page.get_size()))
            im=page.render(scale=scale).to_pil().copy()
            page.close()
    else:
        if item.page:raise ValueError('Image has only one page')
        with Image.open(path) as original:im=original.convert('RGB')
    l,t,r,b=item.crop
    im=im.crop((round(l*im.width),round(t*im.height),round(r*im.width),round(b*im.height)))
    output=io.BytesIO();im.save(output,format='PNG')
    return output.getvalue()


def scene(doc,sheet_id):
    edit=Edit.model_validate(doc['edit'])
    sheet=next((s for s in edit.sheets if s.id==sheet_id),None)
    if sheet is None:raise ValueError('Drawing sheet does not exist')
    width,height=paper(sheet)
    data,rows,operations=anchors(doc['source'])
    primitives=[]
    hitpoints=[]
    render_issues=[]
    group='paper'
    def poly(points,color='#161b22',stroke=.25,dash=False,fill=None):
        primitives.append(dict(kind='polyline',points=points,color=color,stroke=stroke,dash=dash,group=group,fill=fill,
                               dash_pattern=[.8,.4] if edit.template.layout=='pmc3069' else [2,1]))
    def rect(x,y,w,h,color='#161b22'):
        poly([[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]],color)
    def text(x,y,value,size=3,align='left',color='#161b22',max_width=None,rotation=0):
        for i,line in enumerate(wrap(value,max_width,size) if max_width else str(value).split('\n')):
            primitives.append(dict(kind='text',x=x,y=y+i*size*1.35,text=line,size=size,align=align,color=color,group=group,rotation=rotation))
    def arrow(p,towards):
        dx,dy=towards[0]-p[0],towards[1]-p[1];length=math.hypot(dx,dy)
        if length<1e-8:return
        ux,uy=dx/length,dy/length
        points=[[p[0]+ux*2-uy*.7,p[1]+uy*2+ux*.7],p,[p[0]+ux*2+uy*.7,p[1]+uy*2-ux*.7]]
        if edit.template.layout=='pmc3069':points.append(points[0])
        poly(points,stroke=.15 if edit.template.layout=='pmc3069' else .2,fill='#161b22' if edit.template.layout=='pmc3069' else None)
    pmc=edit.template.layout=='pmc3069'
    title_y=383 if pmc else height-59
    margin=2 if pmc else 8
    if pmc:
        from .pmc3069 import furniture
        def logo(x,y,w,h):
            data=(Path(__file__).parent/'assets'/'pmc-logo.png').read_bytes()
            primitives.append(dict(kind='image',x=x,y=y,width=w,height=h,data=base64.b64encode(data).decode(),group='paper',schematic=None))
        furniture(doc,edit,sheet,text,poly,rect,logo)
    else:
        rect(8,8,width-16,height-16)
        text(14,17,edit.metadata.number,4)
        text(width-14,17,sheet.title,3,align='right')
        title_y=height-59
        rect(8,title_y,width-16,51)
        poly([[width*.58,title_y],[width*.58,height-8]])
        text(13,title_y+6,edit.template.company,3.5)
        text(13,title_y+11,edit.template.address+' · '+edit.template.website,2.5)
        text(13,title_y+16,edit.template.standard_notes,2.5,max_width=width*.55)
        text(13,title_y+29,edit.template.general_tolerance,2.3,max_width=width*.55)
        text(13,height-12,edit.metadata.notes,2.5,max_width=width*.55)
        x=width*.58+5
        text(x,title_y+7,edit.metadata.title,4,max_width=width*.39)
        text(x,title_y+19,f'DRAWING {edit.metadata.number}    REV {edit.metadata.revision}',3)
        material=doc['source']['resolved']['block']['material']
        b=doc['source']['resolved']['block']
        text(x,title_y+25,f'MATERIAL {material}   SIZE {b["length"]:g} × {b["width"]:g} × {b["height"]:g} mm',2.7,max_width=width*.38)
        text(x,title_y+32,f'DRAWN {edit.metadata.drawn_by}   CHECKED {edit.metadata.checked_by}   {edit.metadata.date}',2.5)
        text(x,title_y+38,f'THIRD ANGLE   UNITS {edit.metadata.unit}   SCALE: PER VIEW   SHEET {edit.sheets.index(sheet)+1}/{len(edit.sheets)}',2.5)
        state='RELEASED' if doc['status']=='Released' else 'DRAFT / ENGINEERING REVIEW'
        if doc['status']!='Released':
            from .storage import source_current
            if doc['source']['validation'].get('status')!='PASS':state='DRAFT / SOURCE ENGINEERING FAIL'
            elif not source_current(doc):state='DRAFT / SOURCE CHANGED'
        if doc['kind']=='customer':state+=' · CUSTOMER REFERENCE'
        text(x,title_y+45,state,2.7,color='#8a3450' if doc['status']!='Released' else '#161b22')
        text(14,height-3,f'SOURCE {doc["source"]["design_revision"][:12]} / BUILD {doc["source"]["build_id"][:12]} · {edit.metadata.revision_note}',2)
        if edit.metadata.customer:text(13,title_y+24,'CUSTOMER '+edit.metadata.customer,2.5,max_width=width*.44)
        if edit.template.show_logo:
            logo=(Path(__file__).parent/'assets'/'pmc-logo.png').read_bytes()
            primitives.append(dict(kind='image',x=width*.58-53,y=title_y+3,width=48,height=48*16.5/58.5,
                data=base64.b64encode(logo).decode(),group='paper',schematic=None))
        # Third-angle projection symbol: frustum side view and end view to its right.
        sx,sy=width*.53,title_y+41
        poly([[sx,sy-3],[sx+7,sy-2],[sx+7,sy+2],[sx,sy+3],[sx,sy-3]],stroke=.2)
        for radius in (3,2):poly([[sx+13+radius*math.cos(i*math.pi/24),sy+radius*math.sin(i*math.pi/24)] for i in range(49)],stroke=.2)
        poly([[sx-2,sy],[sx+18,sy]],stroke=.12,dash=True)
        if doc.get('release',{}):
            exceptions=doc['release'].get('exceptions',{})
            if exceptions:text(14,25,'RELEASED WITH RECORDED EXCEPTIONS — see release notes',3,color='#9a2d28')
    for view in edit.views:
        if view.sheet!=sheet_id or not view.visible:continue
        group=view.id
        geo=doc['geometry'].get(projection_key(view))
        if geo is None:
            text(*view.position,'REGENERATE VIEW',4,color='#b42318');continue
        left,bottom,right,top=geo['bounds']
        def transform(p):return [view.position[0]+(p[0]-left)*view.scale,view.position[1]+(top-p[1])*view.scale]
        stride=max(1,math.ceil(2*math.sqrt(2)/(3*view.scale)))
        for path in geo.get('hatching',[])[::stride]:poly([transform(p) for p in path],stroke=.12)
        for paths,hidden in [(geo['hidden'],True),(geo['visible'],False)]:
            if hidden and not view.hidden:continue
            for path in paths:poly([transform(p) for p in path],stroke=(.13 if hidden else .18) if pmc else (.16 if hidden else .3),dash=hidden)
        scale_text=f'{view.scale:g}:1' if view.scale>=1 else f'1:{1/view.scale:g}'
        if view.presentation=='standard':text(view.position[0],view.position[1]-5,(view.title or view.projection.upper())+f'   SCALE {scale_text}',3)
        elif view.projection=='iso':text(view.position[0]+(right-left)*view.scale,view.position[1]+(top-bottom)*view.scale+4,'ISO '+scale_text,2.4,align='right',color='#69666d')
        elif view.presentation in ('pmc-coordinate','pmc-internal'):
            from .pmc3069 import FACE_LETTERS
            cx,cy=view.position[0]+4,view.position[1]+4
            poly([[cx+2.2*math.cos(i*math.pi/3),cy+2.2*math.sin(i*math.pi/3)] for i in range(7)],'#a72c6f',.18)
            text(cx,cy+1,FACE_LETTERS[view.projection],2.6,align='center',color='#a72c6f')
        if view.id.startswith('detail-'):
            from ..kinematics import FACE_AXES
            u,v,*_=FACE_AXES[view.projection]
            datum={'front':'B:000','back':'B:010','left':'B:000','right':'B:100','top':'B:001','bottom':'B:000'}[view.projection]
            p=point(view,geo,data[datum]['point'])
            text(view.position[0],view.position[1]-11,f'FACE DATUM: U=+{"XYZ"[u]}, V=+{"XYZ"[v]} · coordinates from marked 0',2.8)
            text(p[0]+2,p[1]+4,'0',2.8)
        for key,a in data.items():
            p=point(view,geo,a['point'])
            hitpoints.append(dict(key=key,view=view.id,x=p[0],y=p[1],label=a['label']))
            if view.centerlines and a.get('face')==view.projection and not key.endswith(':end'):
                radius=max(3,a.get('diameter',0)*view.scale/2+2)
                poly([[p[0]-radius,p[1]],[p[0]+radius,p[1]]],stroke=.15,dash=True)
                poly([[p[0],p[1]-radius],[p[0],p[1]+radius]],stroke=.15,dash=True)
        for item in edit.annotations:
            if item.view!=view.id or item.sheet!=sheet_id or not item.visible:continue
            group=item.id
            values=[data.get(k) for k in item.anchors]
            if item.id in doc.get('broken',{}) or any(v is None for v in values):
                continue
            points=[point(view,geo,v['point']) for v in values]
            if item.kind=='dimension':
                val=measure(item,view,data)
                if val is None:continue
                a=points[0];b=points[-1]
                if item.ordinate:
                    value=dimension_text(val,item,edit.metadata.unit).rstrip('0').rstrip('.') if item.precision else dimension_text(val,item,edit.metadata.unit)
                    if item.measure=='x':
                        end=[b[0]+item.position[0],view.position[1]+item.position[1]]
                        poly([b,[b[0],view.position[1]-3],end],stroke=.18)
                        arrow(end,[end[0],end[1]-4])
                        text(end[0]+.9,end[1]-2,value,item.height,rotation=-90)
                    else:
                        end=[view.position[0]+item.position[0],b[1]+item.position[1]]
                        edge=view.position[0]-3 if item.position[0]<0 else view.position[0]+(right-left)*view.scale+3
                        poly([b,[edge,b[1]],end],stroke=.18)
                        arrow(end,[end[0]+(-4 if item.position[0]<0 else 4),end[1]])
                        text(end[0]+(-2 if item.position[0]<0 else 2),end[1]+1,value,item.height,align='right' if item.position[0]<0 else 'left')
                elif item.measure=='x':
                    y=max(a[1],b[1])+item.position[1]
                    aa=[a[0],y];bb=[b[0],y]
                    poly([a,aa]);poly([b,bb]);poly([aa,bb]);arrow(aa,bb);arrow(bb,aa)
                    text((a[0]+b[0])/2+item.position[0],y-1,dimension_text(val,item,edit.metadata.unit),item.height,align='center')
                elif item.measure=='y':
                    x=min(a[0],b[0])+item.position[0]
                    aa=[x,a[1]];bb=[x,b[1]]
                    poly([a,aa]);poly([b,bb]);poly([aa,bb]);arrow(aa,bb);arrow(bb,aa)
                    text(x-1,(a[1]+b[1])/2+item.position[1],dimension_text(val,item,edit.metadata.unit),item.height,align='center' if pmc else 'right',rotation=-90 if pmc else 0)
                elif item.measure=='aligned':
                    aa=[a[0]+item.position[0],a[1]+item.position[1]];bb=[b[0]+item.position[0],b[1]+item.position[1]]
                    poly([a,aa]);poly([b,bb]);poly([aa,bb]);arrow(aa,bb);arrow(bb,aa)
                    text((aa[0]+bb[0])/2,(aa[1]+bb[1])/2-2,dimension_text(val,item,edit.metadata.unit),item.height,align='center')
                else:
                    end=[a[0]+item.position[0],a[1]+item.position[1]]
                    poly([a,end]);arrow(a,end)
                    text(end[0]+2,end[1]-1,dimension_text(val,item,edit.metadata.unit),item.height)
            else:
                a=points[0];end=[a[0]+item.position[0],a[1]+item.position[1]]
                if item.kind=='leader':poly([a,end]);arrow(a,end)
                caption=values[0].get('machining_label',values[0]['label']) if view.presentation in ('pmc-coordinate','pmc-internal') else values[0]['label']
                text(end[0],end[1],item.text or caption,item.height,color='#151515' if view.presentation in ('pmc-coordinate','pmc-internal') else '#a72c6f')
    for item in edit.annotations:
        if item.sheet==sheet_id and item.kind=='text' and item.visible:
            group=item.id;text(*item.position,item.text,item.height)
    for table in edit.tables:
        if table.sheet!=sheet_id or not table.visible:continue
        group=table.id
        if table.presentation=='pmc-portings':
            from .pmc3069 import table_layout,MAGENTA
            x,y=table.position;cw=table.width/6
            rect(x,y,table.width,5.5,MAGENTA);text(x+table.width/2,y+4.3,'PORTINGS',3.6,align='center',color=MAGENTA)
            y+=5.5
            for row in table_layout(table,rows):
                for i,lines in enumerate(row['cells']):
                    rect(x+i*cw,y,cw,row['height'],MAGENTA)
                    for j,line in enumerate(lines):text(x+(i+.5)*cw,y+table.height+j*table.height*1.15,line,table.height,align='center',color=MAGENTA)
                y+=row['height']
            if y>364.1 and table.position==(313,247):render_issues.append(issue('table-bounds:'+table.id,'PORTINGS overlaps the PMC company block. Reduce the row range or add a continuation sheet.',table.id,'error'))
            continue
        selected=table_rows(table,rows,operations)
        x,y=table.position
        widths,cells=table_cells(table,selected)
        text(x,y-3,'PORTING TABLE' if table.kind=='porting' else 'MACHINING SCHEDULE · source depth excludes drill point',3)
        for lines in cells:
            rh=row_height(table,lines)
            xx=x
            for line,w in zip(lines,widths):
                rect(xx,y,w,rh);text(xx+2,y+table.height+1,'\n'.join(line),table.height);xx+=w
            y+=rh
        if y>title_y-3 or x+table.width>width-8:
            render_issues.append(issue('table-bounds:'+table.id,'Table crosses the drawing area. Reduce row count and add a continued table on another sheet.',table.id,'error'))
    for item in edit.schematics:
        if item.sheet!=sheet_id or not item.visible:continue
        group=item.id
        try:
            content=asset_image(doc,item)
            from PIL import Image
            with Image.open(io.BytesIO(content)) as im:iw,ih=im.size
            factor=min(item.width/iw,item.height/ih)
            w,h=iw*factor,ih*factor;x,y=item.position[0]+(item.width-w)/2,item.position[1]+(item.height-h)/2
            primitives.append(dict(kind='image',x=x,y=y,width=w,height=h,
                                   data=base64.b64encode(content).decode(),group=group,schematic={**item.model_dump(),'position':[x,y],'width':w,'height':h}))
        except (ValueError,OSError,RuntimeError):text(*item.position,'SCHEMATIC UNAVAILABLE',3,color='#b42318')
    if pmc:
        overview_views={v.id for v in edit.views if v.presentation=='pmc-overview'}
        dimension_groups={a.id for a in edit.annotations if a.kind=='dimension' and a.view in overview_views}
        for primitive in primitives:
            if primitive['group'] in dimension_groups:
                primitive['color']='#a72c6f'
                if primitive.get('fill'):primitive['fill']='#a72c6f'
    boxes=[];warned=set();outside=set()
    for index,p in enumerate(primitives):
        if p['kind']=='text':
            length=text_width(p['text'],p['size'])
            left=p['x']-({'left':0,'center':.5,'right':1}[p['align']])*length
            bounds=(left,p['y']-p['size'],left+length,p['y']+.2)
            if p.get('rotation'):
                angle=math.radians(p['rotation']);c,s=math.cos(angle),math.sin(angle)
                corners=[(p['x']+(x-p['x'])*c-(y-p['y'])*s,p['y']+(x-p['x'])*s+(y-p['y'])*c) for x in (bounds[0],bounds[2]) for y in (bounds[1],bounds[3])]
                bounds=(min(x for x,y in corners),min(y for x,y in corners),max(x for x,y in corners),max(y for x,y in corners))
            if p['text'] and (p['group']!='paper' or p['y']>=title_y):boxes.append((p['group'] if p['group']!='paper' else 'paper:'+str(index),bounds))
        elif p['kind']=='image':bounds=(p['x'],p['y'],p['x']+p['width'],p['y']+p['height'])
        elif p['group']!='paper':
            pts=p['points'];bounds=(min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts))
        else:continue
        if p['group']!='paper' and (bounds[0]<margin or bounds[1]<margin or bounds[2]>width-margin or bounds[3]>title_y-2):outside.add(p['group'])
        elif p['group']=='paper' and (bounds[0]<margin or bounds[2]>width-margin or bounds[3]>height):outside.add('paper')
    for i,(key,a) in enumerate(boxes):
        for other,b in boxes[i+1:]:
            if key!=other and max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3]):warned.update([key,other])
    if any(k.startswith('paper:') for k in warned):render_issues.append(issue('title-block-overlap','Title block text overlaps. Shorten the metadata/template text or move long notes onto the sheet.',severity='error'))
    for key in sorted(warned):
        if not key.startswith('paper:'):render_issues.append(issue('overlap:'+key,'Text overlaps another item. Move the label/dimension or adjust the layout before print.',key))
    for key in sorted(outside):render_issues.append(issue('outside:'+key,'Drawing item crosses the printable drawing area. Move it, resize it or use another sheet.',key,'error'))
    return dict(width=width,height=height,primitives=primitives,anchors=hitpoints,issues=render_issues)


def svg(scene):
    def n(x):return f'{x:.4f}'
    result=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{scene["width"]}mm" height="{scene["height"]}mm" viewBox="0 0 {scene["width"]} {scene["height"]}">',
            '<rect width="100%" height="100%" fill="white"/>']
    last=None
    for p in scene['primitives']:
        if p['group']!=last:
            if last is not None:result.append('</g>')
            last=p['group'];result.append(f'<g data-item="{escape(last,quote=True)}">')
        if p['kind']=='polyline':
            coords=' '.join(','.join(map(n,point)) for point in p['points'])
            dash=' stroke-dasharray="'+','.join(map(n,p.get('dash_pattern',[2,1])))+'"' if p['dash'] else ''
            result.append(f'<polyline points="{coords}" stroke="{p["color"]}" stroke-width="{n(p["stroke"])}" fill="{p.get("fill") or "none"}"{dash}/>')
        elif p['kind']=='text':
            anchor={'left':'start','center':'middle','right':'end'}[p['align']]
            family='PMC-CJK' if any(ord(c)>0x2e80 for c in p['text']) else 'PMC-Text'
            length=text_width(p['text'],p['size'])
            transform=f' transform="rotate({p["rotation"]} {n(p["x"])} {n(p["y"])})"' if p.get('rotation') else ''
            result.append(f'<text x="{n(p["x"])}" y="{n(p["y"])}" font-size="{n(p["size"])}" font-family="{family},sans-serif" text-anchor="{anchor}" fill="{p["color"]}" textLength="{n(length)}" lengthAdjust="spacingAndGlyphs"{transform}>{escape(p["text"])}</text>')
        else:
            result.append(f'<image x="{n(p["x"])}" y="{n(p["y"])}" width="{n(p["width"])}" height="{n(p["height"])}" preserveAspectRatio="none" href="data:image/png;base64,{p["data"]}"/>')
    if last is not None:result.append('</g>')
    result.append('</svg>')
    return ''.join(result)
