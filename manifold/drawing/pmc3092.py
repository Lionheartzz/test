"""Customer drawing layout from the supplied PMC26-3092 first sheet.

Only layout is prescribed. No engraving instruction, product identifier or
schematic from the example is copied into another Project's drawing.
"""
from .schema import Sheet, View, Table, Annotation, Schematic
from .projection import projected
from .pmc_standard import STANDARD_NOTES


def configure(source, edit):
    b=source['resolved']['block'];l,w,h=b['length'],b['width'],b['height']
    edit.template.layout='pmc3092'
    edit.template.name='PMC Customer Drawing · PMC26-3092'
    edit.template.standard_notes=STANDARD_NOTES
    edit.metadata.unit='mm'
    edit.sheets=[Sheet(id='overview',title='Customer reference')]
    # PMC26-3092: top/bottom aligned with front, four faces in the middle,
    # schematic upper left, ISO above/right, customer notes lower left.
    limit=min(90/l,62/w,84/h)
    scales=(2,1,.75,.5,1/3,.25,.2,.1,.05,.025,.01)
    scale=next((s for s in scales if s<=limit),limit)
    centers={'left':120,'front':222,'right':339,'back':450}
    positions={face:(center-(w if face in ('left','right') else l)*scale/2,135) for face,center in centers.items()}
    positions['top']=(222-l*scale/2,32)
    positions['bottom']=(222-l*scale/2,268)
    edit.views=[View(id=face,sheet='overview',projection=face,position=positions[face],scale=scale,
        centerlines=True,presentation='pmc-overview') for face in ('top','left','front','right','back','bottom')]
    points=[projected((x,y,z),'iso') for x in (0,l) for y in (0,w) for z in (0,h)]
    iw=max(p[0] for p in points)-min(p[0] for p in points)
    ih=max(p[1] for p in points)-min(p[1] for p in points)
    iso_limit=min(110/iw,108/ih)
    iso_scale=next((s for s in scales if s<=iso_limit),iso_limit)
    edit.views.append(View(id='iso',sheet='overview',projection='iso',position=(354,20),scale=iso_scale,
        centerlines=False,presentation='pmc-overview'))
    edit.tables=[Table(id='porting',sheet='overview',kind='porting',position=(459,250),width=110,
        row_height=10,height=4,count=200,presentation='pmc-customer-portings')]
    assets=source['authored'].get('schematics',[])
    edit.schematics=[Schematic(id='schematic',sheet='overview',asset=assets[0]['sha256'],position=(20,16),width=104,height=73)] if assets else []
    return edit


def annotations(source,edit,data,rows):
    from .pmc3069 import annotations as face_annotations
    items=face_annotations(source,edit,data,rows)
    # Keep the three stock measurements, with height beside the front view as
    # in the Customer reference. Source anchors still determine every value.
    front=next((v for v in edit.views if v.id=='front' and v.projection=='front'),None)
    for item in items:
        if item.id=='auto:right:overall:y' and front is not None:
            item.id='auto:front:overall:y';item.view=front.id;item.anchors=['B:000','B:001']
            item.sheet=front.sheet
            item.position=(source['resolved']['block']['length']*front.scale+12,0)
    for sheet in edit.sheets:
        items.append(Annotation(id=sheet.id+'-customer-reference',kind='text',sheet=sheet.id,
            position=(127,365),text='FOR CUSTOMER REFERENCE ONLY',height=3.5,automatic=True))
    return items
