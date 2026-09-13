"""Reusable presentation templates, with no copied engineering/source facts."""
from copy import deepcopy
import json
import uuid
from .. import store
from .schema import Edit,Template,Sheet,View,Table
from .storage import safe_folder


def listing():
    result=[dict(id='pmc-customer',name='PMC Customer Drawing',kind='customer'),
            dict(id='pmc-manufacturing',name='PMC Manufacturing Drawing',kind='manufacturing')]
    root=store.PROJECT.parent/'drawing-templates'
    if root.is_symlink():raise ValueError('Linked template storage is not supported')
    for path in root.glob('*/template.json'):
        row=read(path.parent.name)
        result.append({k:row[k] for k in ('id','name','kind')})
    return result


def read(key):
    path=safe_folder(store.PROJECT.parent/'drawing-templates',key)/'template.json'
    if path.is_symlink():raise ValueError('Linked template is not supported')
    return json.loads(path.read_text(encoding='utf-8'))


def save(name,doc):
    edit=Edit.model_validate(doc['edit'])
    key=uuid.uuid4().hex
    tables=[t.model_dump() for t in edit.tables]
    for table in tables:table.update(order=[],remarks={})
    template=edit.template.model_dump();template['name']=name;template['tolerance_confirmed']=False
    row=dict(id=key,name=name,kind=doc['kind'],template=template,sheets=[s.model_dump() for s in edit.sheets],
             views=[v.model_dump() for v in edit.views],tables=tables)
    store.atomic_json(safe_folder(store.PROJECT.parent/'drawing-templates',key)/'template.json',row)
    return {k:row[k] for k in ('id','name','kind')}


def apply(key,kind,edit):
    if not key or key=='pmc-'+kind:
        edit.template.name='PMC Customer Drawing' if kind=='customer' else 'PMC Manufacturing Drawing'
        return edit
    row=read(key)
    if row['kind']!=kind:raise ValueError('Template drawing type does not match the selected drawing')
    edit.template=Template.model_validate(row['template'])
    edit.sheets=[Sheet.model_validate(s) for s in row['sheets']]
    edit.views=[View.model_validate(v) for v in row['views']]
    edit.tables=[Table.model_validate(t) for t in row['tables']]
    # Source-specific assets, remarks, annotations and title metadata never carry over.
    edit.schematics=[]
    return Edit.model_validate(edit.model_dump())
