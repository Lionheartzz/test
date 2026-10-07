"""Explicit admission into a new clone; no startup import or blanket promotion."""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from .engineering_db import _connect,validate_database
from .replace_relation_knowledge import encode,file_hash


def plan(db):
    targets=list(db.execute("SELECT * FROM library_targets WHERE domain='Closures / Plugs' ORDER BY id"))
    ports=[dict(r) for r in db.execute("SELECT * FROM external_port_definitions WHERE active=1 AND usable=1 AND unit_system='metric'")]
    admitted={};classifications=[]
    for target in targets:
        reason='MISSING_MACHINING_ENGAGEMENT_ENVELOPE'
        if target['status']!='VERIFIED':reason='PARTIAL_IDENTITY'
        else:
            if target['target_type']=='legacy_closure_family_observation':reason='REFERENCE_ONLY_LEGACY_IDENTITY'
            evidence=[json.loads(r[0]) for r in db.execute('''SELECT e.original_json FROM library_target_evidence l
                JOIN library_evidence e ON e.id=l.evidence_id WHERE l.target_id=? ORDER BY e.id''',(target['id'],))]
            dimensions=[r for r in evidence if r.get('property')=='official_exact_item_identity_dimensions_and_installation_type']
            installations=[r for r in evidence if r.get('property')=='size_specific_installation_stroke_ball_position_and_method'
                           and 'metric table' in r.get('scope','').lower()]
            if dimensions and installations:
                detail=json.loads(dimensions[0]['raw_value']);spec=detail['specifications'];part=detail['manufacturer_part_number']
                installation=json.loads(installations[0]['raw_value'])
                if installation.get('part_number')!=part:reason='AMBIGUOUS_COMPATIBILITY'
                else:
                    try:
                        d=float(spec['d2 +0.10 / -0']);maximum=float(spec['d3 Max']);depth=float(spec['l3 min.'])
                        engagement=float(spec['l1']);initial_length=float(spec['(l2) ~ Ref.'])
                        if not all(math.isfinite(v) and v>0 for v in (d,maximum,depth,engagement,initial_length-engagement)):
                            raise ValueError('Invalid dimensions')
                    except (KeyError,ValueError):reason='MISSING_EXACT_GEOMETRY'
                    else:
                        name=part.replace(' ','-')
                        matches=[]
                        for port in ports:
                            if port['name']!=name:continue
                            stages=json.loads(port['stages_json'])
                            if len(stages)<2:continue
                            first,second=stages[:2]
                            if abs(first['diameter']-d)<1e-6 and abs(first['end']-depth)<1e-6 and abs(second['diameter']-maximum)<1e-6:
                                matches.append(port)
                        if len(matches)!=1:reason='MISSING_INTERFACE' if not matches else 'AMBIGUOUS_COMPATIBILITY'
                        else:
                            port=matches[0];identifier='closure_'+hashlib.sha256(('SFC KOENIG\n'+part).encode()).hexdigest()[:24]
                            machining=[dict(operation='SOURCE_EXPANDER_ENTRY',diameter_mm=d,depth_mm=depth,
                                hydraulic_diameter_max_mm=maximum,transition_angle_degrees=120,hole_tolerance_plus_mm=0.1,
                                roundness_max_mm=0.05,roughness_Rz_um=dict(value=[10,30],condition='Hard materials; manufacturer MB installation instructions'),manufacturer='SFC KOENIG',model=part,
                                source_evidence_ids=[dimensions[0]['evidence_id'],installations[0]['evidence_id']],
                                dimensional_drawing=dict(archive_member='baseline/knowledge_collection_v2/remaining_domains/raw_sources/sfc_koenig_mb_exact_pages_2026_10_03/SFC_Koenig_Catalog_4095_2024.pdf',
                                    sha256='a5ac43ed9df42e88b72af277f8460e04abd5733b42ffbf228f9e897355c9999a'),
                                setting_stroke_mm=float(installation['setting_stroke_S']),pressure_rating=None,
                                note='Flush sleeve installation. Material/pressure suitability and press tooling require the manufacturer instructions. No pressure rating inferred.')]
                            machining.extend([dict(operation="C'BORE",diameter_mm=d,depth_mm=depth),
                                dict(operation='CHAMFER',angle=120,start=depth,end_diameter='$HYDRAULIC_BORE'),
                                dict(operation='INSTALL EXPANDER',model=part,setting_stroke_mm=float(installation['setting_stroke_S']))])
                            envelope=dict(diameter_mm=d+0.1,height_mm=0,
                                installed_length_mm=engagement,installed_head_height_mm=0,
                                scope='Installed product: sleeve flush at the block face, ball below sleeve edge. Occupied depth uses source L1; no setting-tool envelope is claimed.')
                            admitted[identifier]=(identifier,'SFC KOENIG '+part,port['id'],part,encode(machining),engagement,encode(envelope),1,'',1)
                            reason='RUNTIME_READY_WITH_LIMITED_RATING'
        classifications.append(dict(target_id=target['id'],state=reason))
    return sorted(admitted.values()),dict(knowledge_total=len(targets),runtime_definitions=len(admitted),
        target_states=dict(Counter(r['state'] for r in classifications)),classifications=classifications,
        construction_ports_added=0,construction_ports_reused=sorted({r[2] for r in admitted.values()}))


def admit(source,output,report):
    source,output=Path(source).resolve(),Path(output).resolve()
    validate_database(source,schema_version=6)
    if output.exists():raise FileExistsError(output)
    with closing(_connect(source)) as db:
        rows,result=plan(db)
        result['source_sha256']=file_hash(source)
        with output.open('xb'):pass
        with closing(sqlite3.connect(output)) as target:
            db.backup(target);target.execute('PRAGMA foreign_keys=ON')
            with target:
                target.executemany('INSERT INTO closure_definitions VALUES (?,?,?,?,?,?,?,?,?,?)',rows)
            assert target.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
            assert not target.execute('PRAGMA foreign_key_check').fetchall()
    result.update(output=str(output),schema=6,size_delta=output.stat().st_size-source.stat().st_size,output_sha256=file_hash(output))
    Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(encode({k:result[k] for k in ['knowledge_total','runtime_definitions','target_states','size_delta']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--report',required=True)
    args=p.parse_args();admit(args.source,args.output,args.report)
