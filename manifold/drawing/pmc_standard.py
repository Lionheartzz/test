"""Common PMC sheet furniture, shared by Customer and Manufacturing layouts.

Measured from the supplied PMC title blocks. Product values come only from the
Drawing metadata and pinned Manifold. Drawing-area content belongs to layouts.
"""
import math

INK = '#151515'
MAGENTA = '#a72c6f'
GREY = '#69666d'
STANDARD_NOTES = 'BREAK ALL SHARP EDGES.\nSURFACE FINISH:\nGENERAL TOLERANCE IS APPLICABLE TO\nALL DIMENSIONS WITHOUT SPECIFICATIONS.'


def furniture(doc,edit,sheet,text,poly,rect,image):
    """Measured PMC borders and title cells; no application status on the paper."""
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
