"""Drawing generation from an immutable resolved build, never from routing or a mesh."""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from .. import projects, store
from ..schema import Design
from ..kinematics import pose, dimensions, FACE_AXES
from ..cad import cq
from .projection import project, projected, CAD_LOCK
from .schema import Edit, Metadata, Sheet, Annotation, Table

PAPER = {'A4': (210, 297), 'A3': (297, 420), 'A2': (420, 594), 'A1': (594, 841), 'A0': (841, 1189)}


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(value).hexdigest()


def paper(sheet):
    a, b = PAPER[sheet.size]
    return (b, a) if sheet.landscape else (a, b)


def snapshot(project_id, expected, *, load_solid=True):
    record = projects.read(project_id)
    current = projects.snapshot(record)
    if current['revision'] != expected:
        raise ValueError('Source project changed. Refresh the project before creating or updating the drawing.')
    build = current['build']
    if not build or build['design_revision'] != expected:
        raise ValueError('No build matches the saved manifold. Save & Validate in Manifold Studio, then retry Create Drawing.')
    from .storage import safe_folder
    folder = safe_folder(store.OUTPUT / 'builds', build['build_id'])
    names = ('design.json', 'resolved_design.json', 'validation.json', 'production.step', 'manufacturing.json')
    files = {}
    for name in names:
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Build evidence is missing or linked. Save & Validate again before drawing.')
        files[name] = path.read_bytes()
    authored = json.loads(files['design.json'])
    resolved = json.loads(files['resolved_design.json'])
    validation = json.loads(files['validation.json'])
    if validation.get('design_revision') != expected or store.revision(Design.model_validate(authored)) != expected:
        raise ValueError('Build evidence does not match its project revision. Rebuild before drawing.')
    Design.model_validate(resolved)
    solid=None
    if load_solid:
        with CAD_LOCK:
            solid = cq.importers.importStep(str(folder / 'production.step')).val()
            if not solid.isValid() or len(solid.Solids()) != 1:
                raise ValueError('Build has no valid single solid. Correct the manifold before drawing.')
    result = dict(project_id=project_id, design_revision=expected, build_id=build['build_id'],
                  engine_revision=validation.get('engine_revision'), files={k: digest(v) for k, v in files.items()},
                  authored=authored, resolved=resolved, validation=validation,
                  manufacturing=json.loads(files['manufacturing.json']))
    result['sha256'] = digest(result)
    return result, solid


def anchors(source):
    design = Design.model_validate(source['resolved'])
    result = {}
    sizes = dimensions(design.block)
    for a in range(2):
        for b in range(2):
            for c in range(2):
                key = f'B:{a}{b}{c}'
                result[key] = dict(point=[a*sizes[0], b*sizes[1], c*sizes[2]], label=f'Block {a}{b}{c}', signature='block-corner')
    components = {c.feature_id: c for c in design.components if c.feature_id}
    rows, machining = [], []
    profiles = {p['feature']: p for p in source['manufacturing'].get('machining_profiles', [])}
    recipes = {p['definition']: p.get('operations', []) for p in source['manufacturing'].get('native_recipes', [])}
    machining_ids={p['feature']:p['machining_id'] for p in source['manufacturing'].get('drill_chart',[])}
    for f in design.features:
        if f.suppressed:
            continue
        origin, direction = pose(f, design.block)
        profile = profiles.get(f.id, {})
        facts = profile.get('definition_facts') or {}
        definition_id = profile.get('definition') or f.definition
        steps = profile.get('cutting_steps') or []
        diameter = max((s['diameter'] for s in steps), default=f.diameter or 0)
        depth = max((s['end'] for s in steps), default=f.depth or 0)
        identity_pending = f.id in components and bool(components[f.id].cartridge_id) and components[f.id].cartridge_id != f.cartridge_id
        label = f.schematic_id or (components[f.id].label if f.id in components and components[f.id].label else '') or f.machining_id
        if not label and f.kind=='port':
            same=[p for p in design.features if p.kind=='port' and p.circuit==f.circuit and not p.suppressed]
            label=f.circuit+(str(same.index(f)+1) if len(same)>1 else '')
        label=label or machining_ids.get(f.id,f.id)
        model = 'Identity pending review' if identity_pending else (f.cartridge_id or '')
        key = f'F:{f.id}'
        signature = digest(dict(kind=f.kind, definition=definition_id, engineering_definition=facts or profile,
                                face=f.face, parent=f.parent_id))
        result[key] = dict(point=origin, label=label, feature=f.id, face=f.face, direction=direction,
                           machining_label=f.machining_id or machining_ids.get(f.id,label),
                           diameter=diameter, depth=depth, angle=math.degrees(math.acos(min(1, max(-1, abs(direction[2]))))),
                           signature=signature, model=model)
        result[key+':end'] = dict(point=[o+d*depth for o,d in zip(origin,direction)], label=f'{label} depth end', signature=signature)
        thread_spec = facts.get('thread_specification', '')
        definition_label = facts.get('label') or definition_id
        spec = thread_spec if definition_id else (f.size if f.kind == 'port' else f'Ø{f.diameter:g} × {f.depth:g} deep')
        if definition_id:
            spec = f'{definition_label} [{definition_id}]' + (f' / {spec}' if spec else '')
        if f.kind=='mounting':spec=f'MOUNTING Ø{f.diameter:g} '+('THROUGH' if f.through else f'/ {f.depth:g} deep')+' / explicit plain bore; no thread inferred'
        if f.plugged:
            spec += f' / plug engagement {f.plug_length:g}; entry machining unresolved'
        # Display the pinned engineering definition, never a guessed product
        # identity or an internal database key in the PMC PORTINGS cells.
        if definition_id:
            pmc_spec=definition_label
            if thread_spec:pmc_spec+=' / '+thread_spec
        elif f.kind=='mounting' and f.through:pmc_spec=f'Ø{f.diameter:g} THRU'
        elif f.kind in ('mounting','drilling'):pmc_spec=f'Ø{f.diameter:g} × {f.depth:g} DEEP / {f.tip_angle:g}° POINT'
        else:pmc_spec=f.size
        if f.plugged:pmc_spec+=f' / PLUG {f.plug_length:g}; ENTRY SPEC REQUIRED'
        row = dict(id=f.id, feature=f.id, face=f.face, label=label, specification=spec,
                   machining_label=result[key]['machining_label'],
                   kind=f.kind,pmc_specification=pmc_spec,
                   model=model, u=f.u, v=f.v, diameter=diameter, depth=depth,
                    source='Immutable build engineering facts' if definition_id else 'Manifold feature parameters')
        rows.append(row)
        for index, step in enumerate(steps or [dict(diameter=f.diameter, start=0, end=f.depth)], 1):
            theta=math.radians(f.rotation)
            du,dv=step.get('offset_u',0),step.get('offset_v',0)
            start=list(origin);ua,va,*_=FACE_AXES[f.face]
            start[ua]+=du*math.cos(theta)-dv*math.sin(theta)
            start[va]+=du*math.sin(theta)+dv*math.cos(theta)
            stage_signature=digest([signature,index,step.get('kind','cylinder'),[(s.get('kind','cylinder'),s['start'],s.get('offset_u',0),s.get('offset_v',0)) for s in steps]])
            for suffix,depth_at in [('start',step['start']),('end',step['end'])]:
                result[f'{key}:step:{index}:{suffix}']=dict(point=[o+d*depth_at for o,d in zip(start,direction)],
                    label=f'{label} operation {index} {suffix}',signature=stage_signature,
                    diameter=step.get('end_diameter',step['diameter']) if suffix=='end' and step.get('kind')=='cone' else step['diameter'],depth=step['end']-step['start'])
            machining.append(dict(id=f'{f.id}:{index}', feature=f.id, face=f.face, label=label,
                u=f.u, v=f.v, operation=index, diameter=step['diameter'], start=step['start'], end=step['end'],
                end_diameter=step.get('end_diameter') if step.get('kind')=='cone' else None,
                inner_diameter=step.get('inner_diameter') if step.get('kind')=='annulus' else None,
                offset_u=step.get('offset_u', 0), offset_v=step.get('offset_v', 0),
                rotation=f.rotation,
                machining_notes=json.dumps(facts.get('machining_operations',recipes.get(definition_id,[])),ensure_ascii=False) if definition_id else '',tooling=[],
                profile=step.get('kind', 'cylinder'), tip_angle=None if definition_id or (f.kind=='mounting' and f.through) else f.tip_angle,
                direction=direction, specification=spec, source=row['source'], closure=profile.get('closure')))
    return result, rows, machining


def projection_key(view):
    return view.projection + (f':{view.section_at:g}' if view.section_at is not None else '')


def geometry_for(source, solid, views, progress=lambda *_: None):
    result = {}
    for view in views:
        key = projection_key(view)
        if key not in result:
            progress(f'Projecting {view.projection}', len(result))
            result[key] = project(solid, view.projection, view.section_at)
    return result


def initial_edit(source, kind, number=''):
    d = Design.model_validate(source['resolved'])
    meta = Metadata(number=number.strip() or d.name[:100], title=d.name,
                    date=datetime.now(timezone.utc).date().isoformat(), unit='inch' if d.project_context=='inch' else 'mm')
    edit = Edit(metadata=meta, sheets=[Sheet(id='overview', title='Customer reference' if kind=='customer' else 'Manufacturing overview')])
    if kind=='manufacturing':
        from .pmc3069 import configure
        return configure(source,edit)
    from .pmc3092 import configure
    return configure(source,edit)


def auto_annotations(source, edit):
    data, rows, operations = anchors(source)
    if edit.template.layout=='pmc3092':
        from .pmc3092 import annotations
        return annotations(source,edit,data,rows)
    if edit.template.layout=='pmc3069':
        from .pmc3069 import annotations
        return annotations(source,edit,data,rows)
    items = []
    # Opposite-side views have explicit outward axes; dimensions remain positive distances.
    corners = {'front': ('B:000', 'B:100', 'B:001'), 'back': ('B:110', 'B:010', 'B:111'),
               'left': ('B:010', 'B:000', 'B:011'), 'right': ('B:100', 'B:110', 'B:101'),
               'top': ('B:001', 'B:101', 'B:011'), 'bottom': ('B:010', 'B:110', 'B:000')}
    for view in edit.views:
        if view.projection not in corners:
            continue
        corner, right, up = corners[view.projection]
        face_rows = [r for r in rows if r['face'] == view.projection]
        used={'x':set(),'y':set()}
        overall=22+min(len(face_rows),8)*7 if view.id.startswith('detail-') else 14
        for axis, target, offset in [('x', right, (0, overall)), ('y', up, (-overall, 0))]:
            items.append(Annotation(id=f'auto:{view.id}:overall:{axis}', kind='dimension', sheet=view.sheet, view=view.id,
                                    anchors=[corner, target], measure=axis, position=offset, automatic=True))
        for index, row in enumerate(face_rows):
            key = 'F:'+row['id']
            items.append(Annotation(id=f'auto:{view.id}:{row["id"]}:label', kind='leader', sheet=view.sheet, view=view.id,
                                    anchors=[key], text='', position=(4, -3), automatic=True))
            if view.id.startswith('detail-'):
                datum={'back':'B:010','left':'B:000','bottom':'B:000'}.get(view.projection,corner)
                for axis in ('x','y'):
                    axis_index=0 if axis=='x' else 1
                    a=projected(data[datum]['point'],view.projection);b=projected(data[key]['point'],view.projection)
                    value=round(abs(b[axis_index]-a[axis_index]),6)
                    if value in used[axis] or value<1e-6:continue
                    level=len(used[axis]);used[axis].add(value)
                    corner_points=[projected(v['point'],view.projection) for k,v in data.items() if k.startswith('B:')]
                    if axis=='x':offset=(0,(min(a[1],b[1])-min(p[1] for p in corner_points))*view.scale+16+(level%8)*7)
                    else:offset=((min(p[0] for p in corner_points)-min(a[0],b[0]))*view.scale-16-(level%8)*7,0)
                    items.append(Annotation(id=f'auto:{view.id}:{row["id"]}:{axis}', kind='dimension', sheet=view.sheet, view=view.id,
                                            anchors=[datum, key], measure=axis, position=offset, automatic=True))
    return items


def add_tables(source, edit, kind):
    from .render import fitting_rows,table_rows
    _, rows, operations = anchors(source)
    if edit.template.is_pmc:
        from .pmc_portings import add_overflow
        return add_overflow(source,edit,rows)
    first=edit.tables[0]
    first.count=max(1,fitting_rows(first,table_rows(first,rows,operations),90))
    for table_kind,start,total in [('porting',first.count,len(rows)),('machining',0,len(operations) if kind=='manufacturing' else 0)]:
        while start<total:
            sid=f'{table_kind}-{start}'
            table=Table(id=sid+'-table',sheet=sid,kind=table_kind,position=(25,35),width=540,start=start,count=200,row_height=8)
            table.count=max(1,fitting_rows(table,table_rows(table,rows,operations),315))
            edit.sheets.append(Sheet(id=sid,title='Porting table continued' if table_kind=='porting' else 'Machining schedule'))
            edit.tables.append(table);start+=table.count
    Edit.model_validate(edit.model_dump())


def regenerate_edit(source, previous):
    edit = previous.model_copy(deep=True)
    current = {a.id:a for a in auto_annotations(source, edit)}
    existing = {a.id:a for a in edit.annotations}
    added = []
    for key, item in current.items():
        if key not in existing and key not in edit.suppressed:
            edit.annotations.append(item)
            added.append(key)
    return edit, added
