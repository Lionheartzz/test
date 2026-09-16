"""Explicit, one-time conversion of saved projects to schema 2."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from pathlib import Path

from .engineering_db import _connect,validate_references
from .project_migration import convert


def migrate(source: Path, staging: Path, backup: Path, *, install: bool=False):
    source,staging,backup=source.resolve(),staging.resolve(),backup.resolve()
    if staging.exists() or backup.exists():raise ValueError('Staging and backup paths must not already exist')
    files=sorted(source.glob('*.json'))
    staging.mkdir(parents=True)
    report=dict(projects=0,legacy_definitions_before=0,schema2=0)
    with _connect(writable=True) as connection:
        before=connection.execute("SELECT count(*) FROM cavities WHERE unit_system='custom'").fetchone()[0]
        for path in files:
            record=json.loads(path.read_text(encoding='utf-8'))
            design=convert(record['design'],connection)
            from .schema import Design
            parsed=Design.model_validate(design)
            record['design']=parsed.model_dump();record['build']=None
            target=staging/path.name
            target.write_text(json.dumps(record,indent=2),encoding='utf-8')
            report['projects']+=1
        connection.commit()
        for path in staging.glob('*.json'):
            from .schema import Design
            validate_references(Design.model_validate(json.loads(path.read_text(encoding='utf-8'))['design']))
        after=connection.execute("SELECT count(*) FROM cavities WHERE unit_system='custom'").fetchone()[0]
        report['legacy_definitions_before']=before;report['legacy_definitions_added']=after-before
    report['schema2']=sum(json.loads(p.read_text(encoding='utf-8'))['design']['schema_version']==2 for p in staging.glob('*.json'))
    if install:
        backup.mkdir(parents=True)
        for path in files:shutil.copy2(path,backup/path.name)
        for path in staging.glob('*.json'):
            os.replace(path,source/path.name)
        staging.rmdir();report['installed']=True;report['backup']=str(backup)
    else:report['installed']=False;report['staging']=str(staging)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('projects/saved'))
    parser.add_argument('--staging',type=Path,required=True)
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--install',action='store_true')
    args=parser.parse_args(argv)
    print(json.dumps(migrate(args.source,args.staging,args.backup,install=args.install),indent=2))


if __name__=='__main__':main()
