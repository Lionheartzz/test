"""Bounded paper-edit contract. Generated geometry is never accepted from a client."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from ..schema import Strict

Key = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$')]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
ID = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
Paper = Annotated[float, Field(ge=-5000, le=5000)]
Point = tuple[Paper, Paper]
Text = Annotated[str, Field(max_length=2000)]


class Sheet(Strict):
    id: Key
    title: str = Field(default='', max_length=120)
    size: Literal['A4', 'A3', 'A2', 'A1', 'A0'] = 'A2'
    landscape: bool = True


class Metadata(Strict):
    number: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=180)
    revision: str = Field(default='A', min_length=1, max_length=30)
    customer: str = Field(default='', max_length=160)
    drawn_by: str = Field(default='', max_length=100)
    checked_by: str = Field(default='', max_length=100)
    designed_by: str = Field(default='', max_length=100)
    approved_by: str = Field(default='', max_length=100)
    quantity: int = Field(default=1, ge=1, le=100000)
    date: str = Field(default='', max_length=30)
    revision_note: Text = ''
    notes: Text = ''
    unit: Literal['mm', 'inch'] = 'mm'

    @model_validator(mode='after')
    def required_text(self):
        if not all(s.strip() for s in (self.number,self.title,self.revision)):
            raise ValueError('Drawing number, title and revision cannot be blank')
        return self


class Template(Strict):
    layout: Literal['legacy', 'pmc3069', 'pmc3092'] = 'legacy'
    name: str = Field(default='PMC', max_length=100)
    company: str = Field(default='POWER & MOTION CONTROL PTE. LTD.', max_length=160)
    address: str = Field(default='14 Tuas South Link 3, Singapore 638814', max_length=200)
    website: str = Field(default='www.pmcont.com', max_length=100)
    standard_notes: Text = 'BREAK ALL SHARP EDGES.\nGENERAL TOLERANCES APPLY ONLY WHERE NO SPECIFIC TOLERANCE IS STATED.'
    general_tolerance: Text = 'PMC reference: linear mm 1–6 ±0.1; >6–30 ±0.2; >30–120 ±0.3; >120–315 ±0.5; >315–1000 ±0.8; >1000–2000 ±1.2.\nConfirm applicability before release.'
    tolerance_confirmed: bool = False
    show_logo: bool = True
    telephone: str = Field(default='6261 6606', max_length=100)
    fax: str = Field(default='6265 7789', max_length=100)
    email: str = Field(default='pmcont@singnet.com.sg', max_length=100)
    linear_tolerances: list[Annotated[str,Field(max_length=20)]] = Field(default_factory=lambda:['±0.1','±0.2','±0.3','±0.5','±0.8','±1.2','±2.0'], min_length=7, max_length=7)


    @property
    def is_pmc(self):
        return self.layout in ('pmc3069','pmc3092')


class View(Strict):
    id: Key
    sheet: Key
    projection: Literal['front', 'back', 'left', 'right', 'top', 'bottom', 'iso', 'section-x', 'section-y', 'section-z']
    position: Point
    scale: float = Field(default=1, gt=0, le=20)
    hidden: bool = False
    centerlines: bool = True
    visible: bool = True
    title: str = Field(default='', max_length=120)
    section_at: float | None = Field(default=None, ge=0, le=2000)
    presentation: Literal['standard','pmc-overview','pmc-coordinate','pmc-internal'] = 'standard'


class Annotation(Strict):
    id: Key
    kind: Literal['dimension', 'label', 'leader', 'text']
    sheet: Key
    view: Key | None = None
    anchors: list[Key] = Field(default_factory=list, max_length=2)
    measure: Literal['x', 'y', 'aligned', 'diameter', 'radius', 'depth', 'angle'] = 'x'
    position: Point = (0, 0)
    text: Text = ''
    precision: int = Field(default=2, ge=0, le=4)
    height: float = Field(default=3, ge=2, le=20)
    visible: bool = True
    automatic: bool = False
    ordinate: bool = False

    @model_validator(mode='after')
    def association(self):
        if self.kind == 'text' and (self.view is not None or self.anchors):
            raise ValueError('Independent text cannot assert an engineering association')
        if self.kind == 'dimension':
            count = 2 if self.measure in ('x', 'y', 'aligned') else 1
            if not self.view or len(self.anchors) != count:
                raise ValueError('Dimension requires a view and its engineering anchors')
            if self.text:
                raise ValueError('Dimension values are computed; use a separate note for commentary')
        if self.ordinate and (self.kind!='dimension' or self.measure not in ('x','y')):
            raise ValueError('Ordinate presentation requires an associated X or Y dimension')
        if self.kind in ('label', 'leader') and (not self.view or len(self.anchors) != 1):
            raise ValueError('Leader/label requires one engineering anchor and a view')
        return self


class Table(Strict):
    id: Key
    sheet: Key
    kind: Literal['porting', 'machining']
    position: Point
    width: float = Field(default=170, ge=80, le=800)
    row_height: float = Field(default=7, ge=5, le=25)
    height: float = Field(default=2.8, ge=2, le=10)
    start: int = Field(default=0, ge=0, le=5000)
    count: int = Field(default=20, ge=1, le=200)
    display_rows: int | None = Field(default=None, ge=1, le=200)
    order: list[Key] = Field(default_factory=list, max_length=500)
    remarks: dict[Key, Annotated[str, Field(max_length=240)]] = Field(default_factory=dict, max_length=500)
    visible: bool = True
    presentation: Literal['standard','pmc-portings','pmc-customer-portings'] = 'standard'


class Schematic(Strict):
    id: Key
    sheet: Key
    asset: Digest
    page: int = Field(default=0, ge=0, le=199)
    position: Point
    width: float = Field(default=100, ge=10, le=1000)
    height: float = Field(default=75, ge=10, le=1000)
    crop: tuple[float, float, float, float] = (0, 0, 1, 1)
    visible: bool = True

    @model_validator(mode='after')
    def crop_bounds(self):
        l, t, r, b = self.crop
        if not (0 <= l < r <= 1 and 0 <= t < b <= 1):
            raise ValueError('Crop must be normalized left/top/right/bottom within the original page')
        return self


class Edit(Strict):
    metadata: Metadata
    template: Template = Field(default_factory=Template)
    sheets: list[Sheet] = Field(min_length=1, max_length=100)
    views: list[View] = Field(default_factory=list, max_length=100)
    annotations: list[Annotation] = Field(default_factory=list, max_length=5000)
    tables: list[Table] = Field(default_factory=list, max_length=100)
    schematics: list[Schematic] = Field(default_factory=list, max_length=40)
    suppressed: list[Key] = Field(default_factory=list, max_length=5000)

    @model_validator(mode='after')
    def references(self):
        if self.template.is_pmc:
            if self.metadata.unit!='mm' or any(s.size!='A2' or not s.landscape for s in self.sheets):
                raise ValueError('PMC standard templates use A2 landscape sheets and millimetre dimensions/tolerances')
        sheets = {s.id for s in self.sheets}
        views = {v.id: v for v in self.views}
        ids = [s.id for s in self.sheets]
        for objects in (self.views, self.annotations, self.tables, self.schematics):
            for item in objects:
                ids.append(item.id)
                if item.sheet not in sheets:
                    raise ValueError(f'{item.id}: sheet does not exist')
        if len(ids) != len(set(ids)):
            raise ValueError('Drawing object IDs must be unique')
        for item in self.annotations:
            if item.view and (item.view not in views or views[item.view].sheet != item.sheet):
                raise ValueError(f'{item.id}: associated view must exist on the same sheet')
            if item.kind=='dimension' and views[item.view].projection=='iso' and item.measure in ('x','y','aligned'):
                raise ValueError('Place linear dimensions on an orthographic or section view; an isometric projection is foreshortened')
        return self


class Create(Strict):
    expected_source: Digest
    kind: Literal['customer', 'manufacturing']
    number: str = Field(default='', max_length=100)
    template_id: Key | None = None


class Save(Strict):
    expected_revision: Digest
    edit: Edit


class Regenerate(Save):
    expected_source: Digest


class Revision(Strict):
    expected_revision: Digest
    revision: str = Field(min_length=1, max_length=30)
    note: str = Field(default='', max_length=2000)


class Release(Strict):
    expected_revision: Digest
    released_by: str = Field(min_length=1, max_length=100)
    exceptions: dict[Key, Annotated[str, Field(min_length=5, max_length=1000)]] = Field(default_factory=dict, max_length=300)

    @model_validator(mode='after')
    def attributed(self):
        if not self.released_by.strip() or any(len(note.strip())<5 for note in self.exceptions.values()):
            raise ValueError('Release requires an identified engineer and written exception decisions')
        return self
