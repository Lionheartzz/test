from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator

Circuit = Literal['P', 'T', 'A', 'B', 'LS', 'Drain']
Face = Literal['left', 'right', 'front', 'back', 'bottom', 'top']
Positive = Annotated[float, Field(gt=0, le=2000, allow_inf_nan=False)]
Coordinate = Annotated[float, Field(ge=0, le=2000, allow_inf_nan=False)]
Identifier = Annotated[str, Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')]
COLORS = dict(P='#ef5959', T='#459cff', A='#41ca8b', B='#f2d454', LS='#f79b42', Drain='#b08bea')


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, validate_default=True)


class Block(Strict):
    length: Positive
    width: Positive
    height: Positive
    material: str = Field(min_length=1, max_length=120)


class Stage(Strict):
    start: Coordinate
    end: Positive
    diameter: Positive

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Stage end must exceed start')
        return self


class Zone(Stage):
    id: Identifier


class CavityDefinition(Strict):
    id: Identifier
    label: str = Field(max_length=120)
    source: str = Field(min_length=1, max_length=500)
    demo_only: bool = True
    thread_note: str = Field(max_length=300)
    stages: list[Stage] = Field(min_length=1, max_length=12)
    zones: list[Zone] = Field(min_length=1, max_length=8)
    clearance_diameter: Positive
    clearance_height: Positive

    @model_validator(mode='after')
    def consistent(self):
        end = 0
        previous_diameter = float('inf')
        for s in self.stages:
            if abs(s.start - end) > 1e-6 or s.diameter > previous_diameter:
                raise ValueError('Stages must be contiguous from zero and non-increasing in diameter')
            end, previous_diameter = s.end, s.diameter
        if len({z.id for z in self.zones}) != len(self.zones):
            raise ValueError('Duplicate cavity zone')
        for z in self.zones:
            if not any(s.start <= z.start < z.end <= s.end and z.diameter <= s.diameter for s in self.stages):
                raise ValueError('Each hydraulic zone must fit inside one cutting stage')
        for i, a in enumerate(self.zones):
            for b in self.zones[i + 1:]:
                if min(a.end, b.end) > max(a.start, b.start):
                    raise ValueError('Hydraulic zones must not overlap axially')
        if self.clearance_diameter < max(s.diameter for s in self.stages):
            raise ValueError('Installation envelope must cover the cavity mouth')
        return self


class Feature(Strict):
    id: Identifier
    kind: Literal['cavity', 'port', 'drilling']
    face: Face
    u: Coordinate
    v: Coordinate
    definition: Identifier | None = None
    circuits: dict[str, Circuit] = Field(default_factory=dict)
    circuit: Circuit | None = None
    diameter: Positive | None = None
    depth: Positive | None = None
    tip_angle: float = Field(default=118, ge=60, le=180)
    port_type: str = Field(default='Demo straight bore', max_length=120)
    size: str = Field(default='Custom', max_length=80)
    plugged: bool = False
    plug_length: Positive = 8
    clearance_diameter: Positive = 20
    clearance_height: Positive = 20
    connects_to: list[str] = Field(default_factory=list, max_length=40)

    @model_validator(mode='after')
    def fields_for_kind(self):
        if self.kind == 'cavity':
            if not self.definition or self.circuit is not None or self.diameter is not None or self.depth is not None or self.plugged:
                raise ValueError('Cavity uses definition and circuits, not bore fields')
        elif self.circuit is None or self.diameter is None or self.depth is None or self.definition or self.circuits:
            raise ValueError('Bore requires circuit, diameter, depth; no cavity definition')
        if self.plugged and (self.kind != 'drilling' or self.plug_length >= self.depth):
            raise ValueError('Plug requires a drilling deeper than its engagement')
        if self.kind == 'port' and self.clearance_diameter < self.diameter:
            raise ValueError('Port clearance diameter cannot be smaller than bore')
        return self


class Rules(Strict):
    minimum_wall: Positive = 7
    minimum_overlap_volume: float = Field(default=0.1, ge=0.01, le=10)
    max_depth_diameter_ratio: Positive = 20
    minimum_access_gap: Positive = 2


class Design(Strict):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    units: Literal['mm'] = 'mm'
    block: Block
    rules: Rules = Field(default_factory=Rules)
    library: list[CavityDefinition] = Field(min_length=1, max_length=30)
    features: list[Feature] = Field(min_length=1, max_length=60)

    @model_validator(mode='after')
    def references(self):
        ids = [f.id for f in self.features]
        lib = {d.id: d for d in self.library}
        if len(set(ids)) != len(ids) or len(lib) != len(self.library):
            raise ValueError('IDs must be unique')
        nodes = set()
        for f in self.features:
            if f.kind == 'cavity':
                if f.definition not in lib:
                    raise ValueError(f'{f.id}: missing library definition')
                if set(f.circuits) != {z.id for z in lib[f.definition].zones}:
                    raise ValueError(f'{f.id}: assign a circuit to every hydraulic zone')
                nodes.update(f'{f.id}:{z}' for z in f.circuits)
            else:
                nodes.add(f.id)
        for f in self.features:
            if len(set(f.connects_to)) != len(f.connects_to):
                raise ValueError(f'{f.id}: duplicate connection')
            for target in f.connects_to:
                if target not in nodes or target.split(':')[0] == f.id:
                    raise ValueError(f'{f.id}: invalid connection target {target}')
            if f.kind == 'cavity' and f.connects_to:
                raise ValueError('Declare cavity connections on incoming bores using cavity:zone IDs')
        return self
