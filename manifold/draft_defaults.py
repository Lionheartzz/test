"""Deterministic editable-project proposals from existing engineering data.

No operating load, material property, stock identity or approval is invented.
The normal Model strength/wall resolver remains authoritative.
"""
import re
import unicodedata
from .engineering_conditions import effective_conditions,material_strength,feature_ligament
from .layout import propose_dimensions
from .schema import EngineeringReview


def _tokens(value):
    text=unicodedata.normalize('NFKC',str(value or '')).casefold().replace('aluminium','aluminum')
    return set(re.findall(r'[a-z0-9]+',text))


def propose_material(design,definitions,*,explicit=None,inherited=None,inherited_label=None,restrictions=(),preferred_dimensions=None):
    from .engineering_db import materials
    placeholder={'unspecified','unknown','review','required','material','none','not','selected'}
    linked=bool(inherited or (_tokens(inherited_label)-placeholder)) and not explicit
    catalog=materials(include_legacy=linked,current_id=inherited)
    candidates=[];rejected=[];matched=[]
    loads=[effective_conditions(design,n) for n in design.nets]
    pressure=max((r['pressure_bar'] or 0 for r in loads),default=0)
    for row in catalog:
        identity=(row.get('engineering_facts_summary') or {}).get('identity') or {}
        if linked:
            if inherited:
                if row['id']!=inherited:continue
            elif _tokens(row['display_name'])!=_tokens(inherited_label):continue
        else:
            if not row.get('selectable') or not row.get('source_backed') or row.get('legacy_unspecified'):continue
            form=str(identity.get('product_form','')).casefold()
            if not any(word in form for word in ('bar','plate','billet','solid')):continue
            if explicit:
                text=' '.join(str(value) for value in [row['display_name'],row['material_type'],identity.get('grade'),
                    identity.get('state'),identity.get('standard'),identity.get('product_form')])
                requested=_tokens(explicit)-{'material','grade','alloy'}
                if not requested<=_tokens(text):continue
        matched.append(row)
        probe=design.model_copy(deep=True)
        probe.block.material_id=row['id'];probe.block.material=row['display_name']
        # A user legacy stress override remains in the final design. It cannot
        # make an otherwise unsupported source material appear qualified here.
        probe.rules.allowable_stress_mpa=None
        strength=material_strength(probe)
        if restrictions:
            rejected.append(dict(material_id=row['id'],reason='Explicit environmental/treatment applicability is not resolved by current material facts.'));continue
        if strength['design_strength_mpa'] is None and not row.get('legacy_unspecified'):
            rejected.append(dict(material_id=row['id'],reason='No applicable source-backed yield/proof strength.'));continue
        if pressure and (strength['design_strength_mpa'] is None or pressure/10>=strength['design_strength_mpa']):
            rejected.append(dict(material_id=row['id'],reason='Stated working pressure exceeds or cannot be compared with source design strength.'))
            continue
        try:
            sizes=propose_dimensions(probe,definitions,preferred_dimensions)
            ligaments=[feature_ligament(probe,f,definitions)['automatic_mm'] for f in probe.features if not f.suppressed]
            if design.rules.allowable_stress_mpa is not None:
                # Preserve a linked/user legacy rule while reserving enough
                # space for BOTH the source basis and the actual shared rule.
                # A permissive override cannot qualify a weaker source grade.
                probe.rules.allowable_stress_mpa=design.rules.allowable_stress_mpa
                actual=material_strength(probe)['design_strength_mpa']
                if pressure and (actual is None or pressure/10>=actual):
                    rejected.append(dict(material_id=row['id'],reason='Existing explicit stress rule cannot support the stated working pressure.'));continue
                actual_sizes=propose_dimensions(probe,definitions,preferred_dimensions)
                sizes=tuple(max(a,b) for a,b in zip(sizes,actual_sizes))
                ligaments.extend(feature_ligament(probe,f,definitions)['automatic_mm'] for f in probe.features if not f.suppressed)
        except ValueError as exc:
            rejected.append(dict(material_id=row['id'],reason=str(exc)));continue
        if pressure and any(value is None for value in ligaments):continue
        maximum_wall=max([probe.rules.minimum_wall or 0]+[v for v in ligaments if v is not None])
        form=identity.get('product_form','').casefold()
        common=identity.get('grade')=='6061' and identity.get('state','').upper()=='T651'
        stock_fits=any((s['size_1_mm']-2*s['allowance_1_mm']>=sizes[1] and s['size_2_mm']-2*s['allowance_2_mm']>=sizes[2]) or
            (s['size_1_mm']-2*s['allowance_1_mm']>=sizes[2] and s['size_2_mm']-2*s['allowance_2_mm']>=sizes[1]) for s in row.get('stock',[]))
        # This is a stable PMC proposal preference after actual applicability,
        # pressure and fit screening, never a universal grade pressure rating.
        rank=(not common,not stock_fits,maximum_wall,'bar' not in form,row['id'])
        candidates.append((rank,row,strength,sizes,maximum_wall))
    if not candidates:
        # An explicit or inherited identity is not silently replaced because
        # its engineering qualification fails. Carry it with a real open issue.
        specified=next((r for r in catalog if (linked and r['id']==inherited) or
            (explicit and r['id']==design.block.material_id)),None)
        if specified is None and (explicit or linked) and len(matched)==1:specified=matched[0]
        return specified,dict(source='explicit' if explicit else 'linked_project' if linked else 'pmc_policy',
            automatic=not explicit and not linked,status='UNRESOLVED',material_id=specified['id'] if specified else None,
            material=specified['display_name'] if specified else explicit,
            proposed_dimensions=[design.block.length,design.block.width,design.block.height],
            reason='No existing material satisfies the stated identity, source-strength, environment and envelope requirements.',
            rejected=rejected[:12])
    _,row,strength,sizes,wall=min(candidates,key=lambda c:c[0])
    pressure_note=(f'Stated pressure up to {pressure:g} bar screened with the existing safety factor {design.rules.pressure_safety_factor:g} and ligament calculation.'
                   if pressure else 'Working pressure is unknown; preliminary material proposal only.')
    return row,dict(source='explicit' if explicit else 'linked_project' if linked else 'pmc_policy',
        automatic=not explicit and not linked,status='PROPOSED' if strength['design_strength_mpa'] is not None else 'UNRESOLVED',
        material_id=row['id'],material=row['display_name'],
        source_strength=strength,maximum_required_wall_mm=wall,proposed_dimensions=list(sizes),
        reason=('Linked legacy material retained; source-strength qualification remains unresolved. ' if row.get('legacy_unspecified') else
                'Existing exact grade/state and solid-stock form; applicable library yield/proof strength. ')+pressure_note,
        qualification='Not a pressure rating or manufacturing approval',rejected=rejected[:12])


def apply_draft_defaults(design,definitions,*,explicit=None,inherited=None,inherited_label=None,restrictions=(),preferred_dimensions=None):
    result=design.model_copy(deep=True)
    row,selection=propose_material(result,definitions,explicit=explicit,inherited=inherited,inherited_label=inherited_label,
        restrictions=restrictions,preferred_dimensions=preferred_dimensions)
    if row:
        result.block.material_id=row['id'];result.block.material=row['display_name']
        result.review_items.append(EngineeringReview(id='DRAFT_MATERIAL_PROPOSAL',kind='assumption',subject='block',
            description=('Automatically proposed: ' if selection['automatic'] else 'Selected material: ')+row['display_name']+'. '+selection['reason'],
            proposed_value=row['display_name'],status='resolved' if selection['status']=='PROPOSED' else 'open',
            resolution='Recorded deterministic engineering proposal; material remains editable. This is not engineering or manufacturing approval.' if selection['status']=='PROPOSED' else ''))
    if selection['status']=='PROPOSED':
        sizes=selection['proposed_dimensions']
        for key,size in zip(('length','width','height'),sizes):setattr(result.block,key,size)
    else:
        try:
            sizes=propose_dimensions(result,definitions,preferred_dimensions)
            for key,size in zip(('length','width','height'),sizes):setattr(result.block,key,size)
        except ValueError as exc:
            result.review_items.append(EngineeringReview(id='DRAFT_ENVELOPE_UNRESOLVED',kind='dimension',subject='block',
                severity='blocking',description=str(exc)+' Existing dimensions and constraints retained; adjust them in Model.'))
        if not row:
            result.review_items.append(EngineeringReview(id='DRAFT_MATERIAL_UNRESOLVED',kind='component',subject='block',
                description=selection['reason']+' Resolve material or conflicting requirements in Model.'))
    for f in result.features:
        if f.kind=='mounting' and f.through:
            from .kinematics import FACE_AXES,dimensions
            previous=f.depth;f.depth=dimensions(result.block)[FACE_AXES[f.face][2]]
            if f.mounting_mode=='threaded' and f.thread_depth==previous:f.thread_depth=f.depth
    unknown={field:[] for field in ('pressure_bar','flow_lpm')}
    for net in result.nets:
        for field in unknown:
            if effective_conditions(result,net)[field] is None:unknown[field].append(net.label or net.id)
    for field,nets in unknown.items():
        if not nets:continue
        label='working pressure' if field=='pressure_bar' else 'hydraulic flow'
        result.review_items.append(EngineeringReview(id='DRAFT_'+field.upper(),kind='dimension',subject='project',
            description=f'Actual {label} is not specified for '+', '.join(nets)[:1400]+'. Enter operating conditions in Project Settings / Net overrides. Product ratings were not substituted.'))
    return result,selection
