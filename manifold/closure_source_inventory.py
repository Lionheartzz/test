"""Finite, read-only MDTools closure inventory for explicit operator review."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path

from .engineering_db import _connect
from .import_mdtools import DEFAULT_SOURCE,mdb_rows


def inventory(source=DEFAULT_SOURCE,database=None,*,read_mdb=True):
    with closing(_connect(database)) as db:
        mapped={r[0] for r in db.execute('SELECT construction_port_definition_id FROM closure_definitions')}
        if db.execute('PRAGMA user_version').fetchone()[0]>=7 and db.execute("SELECT 1 FROM sqlite_master WHERE name='closure_definition_aliases'").fetchone():
            mapped.update(r[0] for r in db.execute('SELECT source_port_definition_id FROM closure_definition_aliases'))
        records=[]
        for line in (source/'cavities_master.jsonl').read_text(encoding='utf-8').splitlines():
            raw=json.loads(line);family=raw['display_family']
            active=next(r for r in raw['revisions'] if r['active']);r=active['row']
            text=' '.join(str(r.get(k) or '') for k in ('CavityName','FootPrintOEMName','Comments','PortApplicationName'))
            if family not in ('Expander Plug Ports','SAE Plugs','Orifice Plugs') and str(r.get('PlugPort'))!='1' and not any(t in text.lower() for t in ('plug','closure','expander','restrictor')):continue
            port=db.execute('SELECT * FROM external_port_definitions WHERE id=?',(raw['canonical_id'],)).fetchone()
            if family=='Orifice Plugs':role,reason='ORIFICE_PLUG','NON_CONSTRUCTION_ROLE'
            elif family=='SAE Plugs':
                role='THREADED_CONSTRUCTION_PLUG' if str(r.get('PlugPort'))=='1' else 'AMBIGUOUS'
                thread=db.execute('SELECT * FROM thread_definitions WHERE id=?',(port['thread_definition_id'],)).fetchone() if port else None
                reason='INCOMPLETE_THREAD_MACHINING' if not thread or not thread['usable'] or not thread['tap_diameter_mm'] else 'UNSUPPORTED_THREAD_ENTRY'
                if role=='AMBIGUOUS':reason='AMBIGUOUS_ROLE'
            elif family=='Expander Plug Ports':
                role='EXPANDER_CLOSURE';reason=None if raw['canonical_id'] in mapped else 'MISSING_VERIFIED_ENGAGEMENT_ENVELOPE'
            elif r.get('CavityType')=='Port':role,reason='AMBIGUOUS','UNPROVEN_CONSTRUCTION_ROLE'
            elif 'CAVITY PLUG' in text.upper():role,reason='REFERENCE_ONLY','NOT_A_CONSTRUCTION_ACCESS'
            else:role,reason='AMBIGUOUS','NOT_A_CONSTRUCTION_ACCESS'
            records.append(dict(id=raw['canonical_id'],unit=raw['unit'],family=family,name=raw['display_name'],role=role,
                                runtime_port=bool(port),eligible=reason is None,reason=reason,
                                active_source=active['sources'],insertion_depth=r.get('InsertionDepth'),plug_head_height=r.get('PlugHeadHeight')))
        summary=[]
        for family,unit in sorted({(r['family'],r['unit']) for r in records}):
            group=[r for r in records if r['family']==family and r['unit']==unit]
            summary.append(dict(family=family,unit=unit,master_records=len(group),runtime_ports=sum(r['runtime_port'] for r in group),
                                eligible=sum(r['eligible'] for r in group),reasons=dict(Counter(r['reason'] for r in group if r['reason']))))
        support=dict(threads=db.execute('SELECT count(*) FROM thread_definitions').fetchone()[0],
                     modifiers=[dict(r) for r in db.execute('SELECT kind,count(*) AS count FROM machining_modifiers GROUP BY kind')])
    raw=[]
    if read_mdb:
        for release in ('2026-R2','legacy'):
            for unit,filename in [('inch','InchVESTMDToolsLibrary.mdb'),('metric','MMVESTMDToolsLibrary.mdb')]:
                name=filename if release=='2026-R2' else '../legacy/'+filename
                for entry in mdb_rows(source,name,'LibraryNameIndex'):
                    if any(t in entry['LibraryName'].lower() for t in ('plug','closure','expander','restrictor')):
                        rows=mdb_rows(source,name,entry['CavityDataTableName'])
                        raw.append(dict(release=release,unit=unit,filename=filename,**entry,records=len(rows)))
            for unit,filename in [('inch','INCHVESTMDToolsPLUGLibrary.mdb'),('metric','MMVESTMDToolsPLUGLibrary.mdb')]:
                for table in ('ConPlugTable','PlugFilePath'):
                    rows=mdb_rows(source,filename if release=='2026-R2' else '../legacy/'+filename,table)
                    raw.append(dict(release=release,unit=unit,filename=filename,table=table,records=len(rows)))
    converted=source.parent/'PMC_Library_Converted_v05'
    indexes={str(p.relative_to(converted)):len(json.loads(p.read_text(encoding='utf-8'))) for p in converted.glob('*/plugs_index.json')}
    return dict(source=str(source),summary=summary,records=records,mdb_inventory=raw,converted_plug_indexes=indexes,
                support=support,rejected=dict(Counter(r['reason'] for r in records if r['reason'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
    result=inventory();Path(a.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result['summary'],indent=2));print(result['rejected'])
