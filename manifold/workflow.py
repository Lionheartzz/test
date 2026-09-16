"""Local schematic assets and optional Codex handoff preparation."""
import hashlib
import io
import uuid
from pathlib import Path

from PIL import Image

from . import store
from .schema import SchematicAsset


def save_asset(data, name, media_type):
    if not 0 < len(data) <= 20_000_000:
        raise ValueError('Asset must be between 1 byte and 20 MB')
    if media_type == 'application/pdf':
        if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]:
            raise ValueError('Invalid PDF signature or incomplete PDF')
        suffix = '.pdf'
    elif media_type in ('image/png','image/jpeg'):
        with Image.open(io.BytesIO(data)) as image:
            if image.width*image.height > 40_000_000 or image.format != {'image/png':'PNG','image/jpeg':'JPEG'}[media_type]:
                raise ValueError('Image type mismatch or exceeds 40 megapixels')
            image.verify()
        suffix = '.png' if media_type == 'image/png' else '.jpg'
    else:
        raise ValueError('Use PDF, PNG or JPEG')
    digest=hashlib.sha256(data).hexdigest()
    folder=store.PROJECT.parent/'assets';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(digest+suffix)
    if not path.exists():
        with path.open('xb') as handle:handle.write(data)
    return SchematicAsset(sha256=digest,name=Path(name.replace('\\','/')).name[:180] or 'schematic'+suffix,media_type=media_type,size=len(data))


def asset_path(asset):
    suffix={'application/pdf':'.pdf','image/png':'.png','image/jpeg':'.jpg'}[asset.media_type]
    return store.PROJECT.parent/'assets'/(asset.sha256+suffix)


def prepare_handoff(design, expected_revision, project_id=None):
    with store.project_lock():
        if project_id:
            from .projects import snapshot,read
            saved_revision=snapshot(read(project_id))['revision']
        else:
            saved_revision=store.revision(store.read_design())
        if saved_revision != expected_revision:
            raise ValueError('Project changed; reload before preparing a handoff')
        for asset in design.schematics:
            path=asset_path(asset)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=asset.sha256:
                raise ValueError('Schematic asset is missing or hash differs')
        folder=store.PROJECT.parent/'handoffs'/uuid.uuid4().hex
        store.atomic_json(folder/'design.json',design.model_dump())
        store.atomic_json(folder/'manifest.json',dict(project_id=project_id,base_revision=expected_revision,
            draft_revision=store.revision(design),assets=[dict(**a.model_dump(),path=str(asset_path(a))) for a in design.schematics]))
        prompt=f'''Work in {store.ROOT}. Read AGENTS.md and README first.
Read design.json and manifest.json beside this request. Inspect the actual schematic assets.
Use PMC engineering definitions only through data/pmc_engineering.db or PMC_ENGINEERING_DB.
Return schema 2 project state with cavity_id, optional cartridge_id, interface_nets and optional schematic_intent.
Do not copy engineering definitions into the project. Do not infer cartridge compatibility.
Run exact CadQuery/OCCT validation and preserve the existing project revision boundary.
'''
        (folder/'request.md').write_text(prompt,encoding='utf-8')
        return dict(status='READY_FOR_CODEX',request_path=str(folder/'request.md'),
                    prompt=f'Read and execute the local manifold design request at {folder / "request.md"}.',
                    message='Paste this prompt into the current Codex task.')
