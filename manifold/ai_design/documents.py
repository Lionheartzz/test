"""Bounded page rendering in a separate process, independent of the CAD DLLs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from .. import store


def render(document, *, max_pages=12, max_side=2400):
    root = store.OUTPUT / 'ai-documents' / document.sha256 / str(max_side)
    manifest = root / 'pages.json'
    if not manifest.exists():
        stage = root.parent / (str(max_side) + '-' + uuid.uuid4().hex)
        stage.mkdir(parents=True, exist_ok=False)
        source = stage / 'source.bin'
        source.write_bytes(document.data)
        try:
            command = [sys.executable, str(Path(__file__).with_name('document_worker.py')),
                       str(source), str(stage), document.media_type, str(max_side), str(max_pages)]
            result = subprocess.run(command, capture_output=True, timeout=60,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode != 0:
                raise ValueError('Document could not be rendered. Check the PDF, password and page limit.')
            data = json.loads((stage / 'pages.json').read_text())
            root.mkdir(parents=True, exist_ok=True)
            for page in data['pages']:
                os.replace(stage / page['file'], root / page['file'])
            store.atomic_json(manifest, data)
        except subprocess.TimeoutExpired:
            raise ValueError('Document rendering exceeded 60 seconds') from None
        finally:
            # Every path is a fixed immediate child of the private staging directory.
            for item in stage.iterdir():
                if item.is_file() and not item.is_symlink():
                    item.unlink()
            stage.rmdir()
    data = json.loads(manifest.read_text())
    if data['page_count'] > max_pages:
        raise ValueError(f'Document has {data["page_count"]} pages; configured limit is {max_pages}. Split it or raise the limit.')
    pages = []
    for entry in data['pages']:
        page_path = root / entry['file']
        if page_path.parent != root or page_path.suffix != '.png':
            raise ValueError('Invalid rendered page cache')
        content = page_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise ValueError('Rendered page identity mismatch')
        pages.append(dict(**entry, data=content))
    return pages
