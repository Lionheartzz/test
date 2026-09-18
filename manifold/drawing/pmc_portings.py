"""Source-driven PMC PORTINGS, with Customer and Manufacturing arrangements."""
import math
import re
from collections import OrderedDict
from .schema import Sheet


def column_pairs(table):
    return 1 if table.presentation=='pmc-customer-portings' else 3


def table_height(table,rows):
    return sum(r['height'] for r in table_layout(table,rows))+(9 if column_pairs(table)==1 else 5.5)


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
        if column_pairs(table)==1:return row['label']
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
    # Customer uses one ID/specification pair; Manufacturing repeats three.
    pairs=column_pairs(table)
    per_column=max(1,math.ceil(len(groups)/pairs))
    col_width=table.width/(2*pairs)
    required=max(1,per_column)
    displayed=max(required,table.display_rows or required)
    grid=[]
    for i in range(displayed):
        cells=[];ids=[]
        for col in range(pairs):
            index=col*per_column+i
            row=groups[index] if i<per_column and index<len(groups) else None
            cells.extend([wrap(row['labels'],col_width-2,table.height),wrap(row['specification'],col_width-2,table.height)] if row else [[],[]])
            if row:ids.extend(row['ids'])
        grid.append(dict(cells=cells,height=max(table.row_height,max(map(len,cells),default=1)*table.height*1.15+1),ids=ids))
    return grid


def add_overflow(source,edit,rows):
    """Additional sheets only when the source PORTINGS content actually overflows."""
    if not edit.tables:return
    first=edit.tables[0]
    capacity=105 if column_pairs(first)==1 else 117
    groups=porting_groups(rows,edit.tables[0],all_groups=True);limit=min(200,len(groups))
    # Preserve each layout's reference table region. Find a batch that
    # fits there; remaining real data gets a continuation rather than clipping.
    while limit>1:
        probe=edit.tables[0].model_copy(update={'count':limit})
        if table_height(probe,rows)<=capacity+.001:break
        limit-=1
    for table in edit.tables:table.count=max(1,limit)
    start=max(1,limit)
    while start<len(groups):
        limit=min(200,len(groups)-start)
        probe=edit.tables[0].model_copy(update={'start':start,'count':limit})
        while limit>1 and table_height(probe,rows)>capacity+.001:
            limit-=1;probe.count=limit
        sid=f'portings-{start}';edit.sheets.append(Sheet(id=sid,title='Portings continued'))
        edit.tables.append(first.model_copy(deep=True,update=dict(id=sid+'-table',sheet=sid,start=start,count=max(1,limit))))
        if column_pairs(first)==1:
            from .schema import Annotation
            edit.annotations.append(Annotation(id=sid+'-customer-reference',kind='text',sheet=sid,
                position=(127,365),text='FOR CUSTOMER REFERENCE ONLY',height=3.5,automatic=True))
        start+=max(1,limit)
