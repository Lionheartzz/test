"""One editable project contract for people, local files and future AI providers."""
from .schema import Design
from .store import revision
from .workflow import asset_path


def inspect_project(design: Design):
    missing = [a.model_dump() for a in design.schematics if not asset_path(a).is_file()]
    return dict(design=design.model_dump(), revision=revision(design),
                summary=dict(name=design.name, features=len(design.features),
                             cavities=sum(f.kind == 'cavity' for f in design.features),
                             nets=len(design.nets), open_reviews=sum(r.status == 'open' for r in design.review_items),
                             unconfirmed_components=sum(c.status != 'confirmed' for c in design.components)),
                missing_assets=missing,
                message='Project JSON contains pinned cavity definitions, intent and review items. Schematic files are separate local assets. Import opens an editable draft; it never grants a validation PASS.')
