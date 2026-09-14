"""Print-sized vector PDF, with original PDF schematic content composed as vectors."""
from copy import deepcopy
import io
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader, PdfWriter, Transformation
from .schema import Edit
from .render import scene, font_name, asset_file


def export_pdf(doc):
    edit=Edit.model_validate(doc['edit'])
    buffer=io.BytesIO()
    canvas=Canvas(buffer,pageCompression=1,invariant=1)
    canvas.setTitle(edit.metadata.number+' · '+edit.metadata.title)
    canvas.setAuthor(edit.template.company)
    canvas.setSubject('PMC engineering drawing' if edit.template.is_pmc else f'{doc["kind"]}; {doc["status"]}; source {doc["source"]["design_revision"]}; build {doc["source"]["build_id"]}')
    overlays=[]
    for sheet in edit.sheets:
        current=scene(doc,sheet.id)
        w,h=current['width'],current['height']
        canvas.setPageSize((w*mm,h*mm))
        pdf_assets=[]
        for p in current['primitives']:
            if p['kind']=='polyline':
                canvas.setStrokeColor(p['color']);canvas.setLineWidth(p['stroke']*mm)
                canvas.setDash([v*mm for v in p.get('dash_pattern',[2,1])] if p['dash'] else [])
                if p.get('fill'):canvas.setFillColor(p['fill'])
                path=canvas.beginPath()
                for i,(x,y) in enumerate(p['points']):
                    (path.moveTo if i==0 else path.lineTo)(x*mm,(h-y)*mm)
                canvas.drawPath(path,stroke=1,fill=bool(p.get('fill')))
            elif p['kind']=='text':
                canvas.setFillColor(p['color'])
                canvas.setFont(font_name(any(ord(c)>0x2e80 for c in p['text'])),p['size']*mm)
                fn={'left':canvas.drawString,'center':canvas.drawCentredString,'right':canvas.drawRightString}[p['align']]
                if p.get('rotation'):
                    canvas.saveState();canvas.translate(p['x']*mm,(h-p['y'])*mm);canvas.rotate(-p['rotation'])
                    fn(0,0,p['text']);canvas.restoreState()
                else:fn(p['x']*mm,(h-p['y'])*mm,p['text'])
            elif p['kind']=='image':
                item=p['schematic']
                if not item:
                    import base64
                    canvas.drawImage(ImageReader(io.BytesIO(base64.b64decode(p['data']))),p['x']*mm,(h-p['y']-p['height'])*mm,p['width']*mm,p['height']*mm)
                    continue
                path,row=asset_file(doc,item['asset'])
                if row['media_type']=='application/pdf':pdf_assets.append((path,item))
                else:
                    import base64
                    canvas.drawImage(ImageReader(io.BytesIO(base64.b64decode(p['data']))),p['x']*mm,(h-p['y']-p['height'])*mm,p['width']*mm,p['height']*mm)
        overlays.append((h,pdf_assets));canvas.showPage()
    # Exceptions travel inside the issued file, not only in a UI badge.
    if doc.get('release') and doc['release'].get('exceptions'):
        from .render import wrap
        canvas.setPageSize((210*mm,297*mm))
        y=280
        canvas.setFont(font_name(),12)
        canvas.drawString(15*mm,y*mm,edit.metadata.number+' / '+edit.metadata.revision+' — RELEASE EXCEPTIONS')
        y-=10
        for code,note in doc['release']['exceptions'].items():
            value=code+': '+note
            for line in wrap(value,180,3.2):
                if y<20:canvas.showPage();canvas.setPageSize((210*mm,297*mm));y=280
                canvas.setFont(font_name(any(ord(c)>0x2e80 for c in line)),3.2*mm)
                canvas.drawString(15*mm,y*mm,line);y-=5
            y-=4
        canvas.showPage()
    canvas.save()
    reader=PdfReader(io.BytesIO(buffer.getvalue()))
    writer=PdfWriter(clone_from=reader)
    for index,page in enumerate(writer.pages):
        if index<len(overlays):
            h,pdf_assets=overlays[index]
            for path,item in pdf_assets:
                original=PdfWriter(clone_from=PdfReader(path)).pages[item['page']]
                for key in ('/Annots','/AA','/Metadata'):
                    if key in original:del original[key] # Do not carry active annotations into engineering exports.
                original.transfer_rotation_to_content()
                box=original.cropbox
                w0,h0=float(box.width),float(box.height)
                l,t,r,b=item['crop']
                left=float(box.left)+l*w0;right=float(box.left)+r*w0
                bottom=float(box.bottom)+(1-b)*h0;top=float(box.bottom)+(1-t)*h0
                original.cropbox.lower_left=(left,bottom);original.cropbox.upper_right=(right,top)
                transform=(Transformation().translate(-left,-bottom)
                           .scale(item['width']*mm/(right-left),item['height']*mm/(top-bottom))
                           .translate(item['position'][0]*mm,(h-item['position'][1]-item['height'])*mm))
                page.merge_transformed_page(original,transform,over=False,expand=False)
    writer.add_metadata({'/Title':edit.metadata.number+' '+edit.metadata.title,'/Author':edit.template.company,
                         '/Subject':'PMC engineering drawing' if edit.template.is_pmc else f'Source {doc["source"]["design_revision"]}; build {doc["source"]["build_id"]}; {doc["status"]}'})
    output=io.BytesIO();writer.write(output)
    return output.getvalue()
