"""Converted MDTools catalog; no MDB, raw archive or QC report runtime dependency.

Native records and footprint relationships remain separate, content-pinned objects.
The conservative cylinder projection is explicitly a draft, never a vendor cavity.
"""
import hashlib
import copy
import json
import math
from functools import lru_cache
from pathlib import Path
from .schema import CavityDefinition

ROOT = Path(__file__).resolve().parents[1] / 'PMC_MDTools_Library' / 'PMC_Library_Converted_v05'


GROUPS = ('cavities', 'footprints', 'o_ring_grooves', 'undercuts', 'plugs',
          'assembly_envelopes', 'drill_tools', 'flat_bottom_drill_tools',
          'spot_face_tools', 'material_stock', 'tooling', 'materials')
KIND_GROUPS = dict(port_definition=('cavities',),cavity=('cavities',),footprint=('footprints',),o_ring_groove=('o_ring_grooves',),
                   undercut=('undercuts',),plug=('plugs',),assembly_envelope=('assembly_envelopes',),
                   tool=('drill_tools','flat_bottom_drill_tools','spot_face_tools','tooling'),material_stock=('material_stock','materials'))

@lru_cache(maxsize=40)
def group_records(root, unit, group):
    result={}
    for path in sorted((Path(root)/unit/group).rglob('*.json')):
        if path.stem.endswith('_index'):continue
        data=json.loads(path.read_text(encoding='utf-8'))
        for record in data if isinstance(data,list) else [data]:
            if isinstance(record,dict) and isinstance(record.get('id'),str):result[record['id']]=(record,path)
    return result

@lru_cache(maxsize=1)
def records():
    return {key:value for unit in ('metric','inch') for group in GROUPS
            for key,value in group_records(str(ROOT),unit,group).items()}

def get_record(id):
    import re
    match=re.fullmatch(r'(metric|inch):lib([0-9]+):(cavity|footprint):([0-9]+)',id)
    if match:
        unit,lib,kind,index=match.groups()
        # Filename and folder only locate candidates. Identity always comes from the full record.
        group='cavities' if kind=='cavity' else 'footprints'
        for path in (ROOT/unit/group/('lib_'+lib)).glob(f'{int(index):05d}_*.json'):
            record=json.loads(path.read_text(encoding='utf-8'))
            if record.get('id')==id:return record
    for record,_ in records().values():
        if record['id']==id:return copy.deepcopy(record)
    raise ValueError('Converted library record not found')


def digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def pmc_id(id):
    return 'MD_' + id.replace(':', '_')


@lru_cache(maxsize=4)
def footprint_index(root,unit):
    path=Path(root)/unit/'footprint_index.json'
    if not path.is_file():return None
    result={}
    for row in json.loads(path.read_text(encoding='utf-8')):
        result.setdefault(row.get('cavity_ref'),set()).add(row['id'])
    return result


def related(record):
    unit = record.get('unit_system',str(record['id']).split(':')[0])
    index=footprint_index(str(ROOT),unit)
    if index is not None:
        candidates=[get_record(id) for id in sorted(index.get(record['id'],()))]
    else:candidates=[r for r,_ in group_records(str(ROOT),unit,'footprints').values()]
    result=[r for r in candidates if r.get('unit_system')==unit and r.get('source_identity',{}).get('cavity_ref')==record['id']]
    for group, refs in record.get('special_feature_refs', {}).items():
        for ref in refs if isinstance(refs,list) else []:
            for key, value in ref.items():
                if key.endswith('_index'):
                    for candidate, _ in records().values():
                        if candidate.get('unit_system') == unit and candidate.get(key) == value:
                            if candidate not in result:
                                result.append(candidate)
    return result


def shared_resources():
    result=[]
    for name in ('manufacturing_rules','material_catalog'):
        path=ROOT/'shared'/(name+'.json')
        if path.is_file():
            value=json.loads(path.read_text(encoding='utf-8'))
            result.append(dict(id='shared:'+name,kind=name,unit_system='shared',source_sha256=digest(value),record=value))
    return result


def resource(id):
    if id.startswith('shared:'):
        found=next((r for r in shared_resources() if r['id']==id),None)
        if found is None: raise ValueError('Shared resource not found')
        return found
    record=get_record(id)
    return dict(id=id,unit_system=record.get('unit_system',id.split(':')[0]),kind=record.get('kind',id.split(':')[1]),source_sha256=digest(record),record=record)


def search(q='', unit='', kind='cavity', manufacturer='', cavity_type='', thread='', offset=0, limit=40, include_deleted=False, family=''):
    from .workflow import _catalog_state
    hidden = set(_catalog_state()['hidden_ids'])
    rows = []
    candidates={key:value for selected_unit in ((unit,) if unit in ('metric','inch') else ('metric','inch')) for group in KIND_GROUPS.get(kind,GROUPS) for key,value in group_records(str(ROOT),selected_unit,group).items()}
    for record, _ in candidates.values():
        if not include_deleted and pmc_id(record['id']) in hidden:
            continue
        record_unit = record.get('unit_system',record['id'].split(':')[0])
        record_kind = record.get('kind',record['id'].split(':')[1])
        if unit and record_unit != unit or kind and record_kind != ('cavity' if kind=='port_definition' else kind):
            continue
        if family and record.get('family') != family:
            continue
        maker = record.get('library', {}).get('name', '')
        typ = record.get('cavity_type', record.get('source_identity', {}).get('cavity_type', ''))
        if kind=='port_definition' and typ.upper() not in ('P','PORT'):continue
        threads = ' / '.join(' '.join(str(t.get(k, '')) for k in ('size', 'pitch', 'class')) for t in record.get('threads', []))
        haystack = ' '.join([record['id'], record.get('name', ''), maker, typ, threads, record.get('comments', ''),
                            record.get('family',''),record.get('material_name',''),
                            ' '.join(str(record.get(k,{}).get('raw','')) for k in ('diameter','max_depth','size_1','size_2'))]).lower()
        if not all(token in haystack for token in q.lower().split()) or manufacturer.lower() not in maker.lower() or cavity_type.lower() not in typ.lower() or thread.lower() not in threads.lower():
            continue
        label = record.get('name') or record.get('material_name') or record.get('family',record['id'])
        dimensions = ' / '.join(str(record[k]['raw'])+' '+str(record[k].get('unit','')) for k in ('diameter','max_depth','size_1','size_2') if isinstance(record.get(k),dict))
        rows.append(dict(id=record['id'], pmc_id=pmc_id(record['id']), name=label + (' · '+dimensions if dimensions else ''),family=record.get('family',''),
                         unit=record_unit, kind=record_kind, manufacturer=maker,
                         cavity_type=typ, thread=threads, deleted=pmc_id(record['id']) in hidden))
    rows.sort(key=lambda r: (r['manufacturer'], r['name'], r['id']))
    page=rows[offset:offset+limit]
    for row in page:row['sha256']=digest(candidates[row['id']][0])
    return dict(total=len(rows), offset=offset, limit=limit, items=page,
                available=ROOT.is_dir(), source='VEST MDTools 930 · converted v0.5')


def mm(value):
    if not isinstance(value, dict) or not isinstance(value.get('value'), (float, int)):
        return None
    # Derive from native value, rather than trusting a rounded display conversion.
    scale = 25.4 if value.get('unit') in ('inch', 'in') else 1 if value.get('unit') == 'mm' else None
    return value['value'] * scale if scale is not None else None


def profile_primitives(record, u=0, v=0, datum='step0-relative'):
    """Each source step is a drill-like cylinder/cone. VEST defines steps 1–11 from step 0.

    Step 12 is the pilot depth from the entry plane. Sun/LS records retain a
    separate provisional surface convention until its installation datum is reviewed.
    Zero cylinder length is meaningful: a seat cone can start at the datum.
    """
    profile = record.get('geometry', {}).get('axial_profile', [])
    step0 = next((mm(p.get('depth')) for p in profile if p.get('circle')==0),0) or 0
    pieces = []
    for index, p in enumerate(profile):
        diameter, depth = mm(p.get('diameter')), mm(p.get('depth'))
        if not diameter or depth is None or diameter<=0 or depth<0:
            continue
        depth += step0 if datum == 'step0-relative' and 1<=p.get('circle',0)<=11 else 0
        ref = record['id'] + ':circle:' + str(p.get('circle',index))
        if depth>0:
            pieces.append(dict(kind='cylinder',source_ref=ref,start=0,end=depth,diameter=diameter,offset_u=u,offset_v=v))
        angle = p.get('angle_deg',90)
        next_d = mm(profile[index+1].get('diameter')) if index+1<len(profile) else 0
        if isinstance(angle,(int,float)) and 0<angle<90 and next_d is not None and 0<=next_d<diameter:
            height = (diameter-next_d)/2/math.tan(math.radians(angle))
            pieces.append(dict(kind='cone',source_ref=ref,start=depth,end=depth+height,diameter=diameter,end_diameter=next_d,offset_u=u,offset_v=v))
    return pieces


def interface_windows(record, primitives, u=0, v=0, prefix='', datum='step0-relative'):
    """MDTools declared working bands, clipped to the actual cut; never infer circuit identity."""
    if not primitives:
        return []
    profile = record.get('geometry',{}).get('axial_profile',[])
    step0 = next((mm(p.get('depth')) for p in profile if p.get('circle')==0),0) or 0
    base = step0 if datum == 'step0-relative' else 0
    end = max(p['end'] for p in primitives)
    diameter = max(p['diameter'] for p in primitives)
    typ = record.get('cavity_type',record.get('source_identity',{}).get('cavity_type',''))
    typ=typ.upper()
    if typ in ('BH','LP'):
        return []
    bands=[]
    if typ == 'CV':
        hyd=record.get('hydraulic',{})
        for port in hyd.get('ports',[])[:hyd.get('declared_port_count',0)]:
            depth=mm(port.get('depth')); size=mm(port.get('diameter'))
            if depth is None:
                continue
            if port['port']==1 and not size:
                start, stop = base+depth,end
            elif size and size>0:
                start, stop = base+depth-size/2, base+depth+size/2
            else:
                continue
            if 0<=start<stop<=end:
                bands.append(dict(id=prefix+'port'+str(port['port']),start=start,end=stop,diameter=diameter,offset_u=u,offset_v=v,clip_to_cut=True))
    elif typ in ('DH','P','PORT'):
        insertion=mm(record.get('engineering',{}).get('insertion_depth')) or 0
        if insertion<end:
            name=record.get('hydraulic',{}).get('port_application_name',record.get('port_application_name','port1'))
            import re
            name=re.sub(r'[^A-Za-z0-9_-]','_',name or 'port1')
            if not name[0].isalpha(): name='port_'+name
            bands.append(dict(id=(prefix+name)[:40],start=insertion,end=end,diameter=diameter,offset_u=u,offset_v=v,clip_to_cut=True))
    return bands


def definition(id):
    return map_record(get_record(id))


def map_record(record, related_records=None, datum_mode=None):
    record=copy.deepcopy(record)
    related_records=copy.deepcopy(related_records) if related_records is not None else None
    id = record['id']
    if record['kind'] != 'cavity':
        raise ValueError('Choose a cavity to insert; footprints retain their parent cavity relationship')
    profile = record.get('geometry', {}).get('axial_profile', [])
    datum = datum_mode or ('surface-relative' if record.get('source_identity',{}).get('is_sun_cavity') else 'step0-relative')
    primitives = profile_primitives(record,datum=datum)
    cylinders = [(p['diameter'],p['end']) for p in primitives if p['kind']=='cylinder']
    cylinders = [(d, h) for d, h in cylinders if d and h and 0 < d <= 2000 and 0 < h <= 2000]
    if not cylinders:
        raise ValueError('No numeric cutting dimensions. Edit the native record and map geometry before insertion.')
    # Union of source cylinders: useful conservative placement draft, not an interpretation
    # of ambiguous Circle/Angle legacy geometry. Original angles and depths are not altered.
    stages, start = [], 0
    for end in sorted({h for _, h in cylinders}):
        diameter = max(d for d, h in cylinders if h >= end)
        if stages and stages[-1]['diameter'] == diameter:
            stages[-1]['end'] = end
        else:
            stages.append(dict(start=start, end=end, diameter=diameter))
        start = end
    notes = ['Native stepped cylinders and bottom cones mapped in mm. Steps 1–11 use the Step 0 datum; pilot depth uses the entry plane. Threads, tolerances and machining recipes remain structured metadata.']
    status='imported-dimensional'
    if datum=='surface-relative':
        notes.append('Sun locating-shoulder datum requires installation review. Source depths are provisionally surface-relative; verify LS depth and socket counterbore before release. Original source values are unchanged.')
        status='draft-projection'
    relations = copy.deepcopy(related(record)) if related_records is None else related_records
    zones = interface_windows(record,primitives,datum=datum)
    for footprint in relations:
        if footprint.get('kind') == 'footprint':
            u,v = mm(footprint.get('placement',{}).get('x')), mm(footprint.get('placement',{}).get('y'))
            if u is not None and v is not None:
                children = profile_primitives(footprint,u,v)
                primitives.extend(children)
                prefix='fp'+str(footprint['source_identity']['footprint_index'])+'_'
                zones.extend(interface_windows(footprint,children,u,v,prefix))
    if relations:
        notes.append(f'{len(relations)} related records pinned separately. Numeric footprint bores use source local offsets; verify mounting geometry, special features and envelope before release.')
    # Do not invent sealing windows from nominal connecting-hole diameters.
    if record.get('special_feature_refs'):
        notes.append('Referenced special cuts retained; map mandatory undercuts / grooves before geometry release.')
        status='draft-projection'
    declared=record.get('hydraulic',{}).get('declared_port_count',0)
    if record.get('cavity_type')=='CV' and len([z for z in zones if z['id'].startswith('port')])!=declared:
        notes.append('One or more declared hydraulic windows lacks a complete dimensional mapping; review native port records.')
        status='draft-projection'
    diameter = max([s['diameter'] for s in stages]+[2*math.hypot(p['offset_u'],p['offset_v'])+p['diameter'] for p in primitives])
    threads = ' / '.join(' '.join(str(t.get(k, '')) for k in ('size', 'pitch', 'class')) for t in record.get('threads', []))
    from .boundaries import mapped_boundaries
    boundaries = mapped_boundaries(record,relations)
    if not boundaries:
        notes.append('No supported closed mounting boundary; external body and service footprint require engineering review.')
    body = dict(id=pmc_id(id), label=record['name'][:120], source='VEST MDTools 930 / '+id,
                demo_only=False, thread_note=threads[:300], stages=stages, zones=zones,
                clearance_diameter=diameter, clearance_height=max(1, mm(record.get('engineering', {}).get('insertion_depth')) or 20),
                manufacturer=record.get('library', {}).get('name', '')[:120],
                cartridge_models=[], valve_function=record.get('cavity_type', 'Unspecified'),
                revision=digest(record)[:16], provenance='candidate', machining_notes='Native machining recipe retained independently; expressions require review.',
                cutting_primitives=primitives, boundaries=boundaries,
                native=dict(record=record, related_records=relations, source_sha256=digest(record), geometry_notes=notes,geometry_status=status,datum_mode=datum))
    return CavityDefinition.model_validate(body)


def manifest():
    path = ROOT / 'manifest.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'counts': {}, 'available': False}


@lru_cache(maxsize=1)
def mapping_report():
    items=[];mapped=0
    for record,_ in records().values():
        if record.get('kind')!='cavity':continue
        d=map_record(record,related(record))
        if d.native.geometry_status=='draft-projection':
            items.append(dict(id=record['id'],name=record['name'],source_sha256=d.native.source_sha256,
                              status=d.native.geometry_status,reasons=d.native.geometry_notes))
        else:mapped+=1
    return dict(total=mapped+len(items),dimensional=mapped,provisional=len(items),items=items,
                scope='Geometry mapping only; machining review and manufacturer approval are independent.')
