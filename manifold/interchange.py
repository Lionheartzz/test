"""One editable project contract for people, local files and future AI providers."""
from .schema import Design
from .store import revision
from .workflow import asset_path


def inspect_project(design: Design):
    from .engineering_db import definitions_for_design,thread_definitions_for_design,validate_references
    validate_references(design)
    definitions={key:value.model_dump() for key,value in definitions_for_design(design).items()}
    threads=thread_definitions_for_design(design)
    missing = [a.model_dump() for a in design.schematics if not asset_path(a).is_file()]
    return dict(design=design.model_dump(),engineering=dict(definitions=definitions,threads=threads),revision=revision(design),
                summary=dict(name=design.name, features=len(design.features),
                             cavities=sum(f.kind == 'cavity' for f in design.features),
                             nets=len(design.nets), open_reviews=sum(r.status == 'open' for r in design.review_items),
                             schematic_components=len(design.components)),
                missing_assets=missing,
                message='Project JSON contains project state and engineering database IDs. Schematic files are separate local assets. Import opens an editable draft; it never grants a validation PASS.')
