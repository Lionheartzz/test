from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer

Circuit = Annotated[str, Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')]
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
    offset_u: float = Field(default=0,ge=-2000,le=2000)
    offset_v: float = Field(default=0,ge=-2000,le=2000)
    clip_to_cut: bool = False


class CuttingPrimitive(Strict):
    """Explicit mm CAD mapping, independent of native dimensions and recipe operands."""
    source_ref: str = ''
    start: Coordinate
    end: Positive
    diameter: Positive
    end_diameter: float = Field(default=0,ge=0,le=2000)
    kind: Literal['cylinder', 'cone', 'annulus'] = 'cylinder'
    inner_diameter: Coordinate = 0
    offset_u: float = Field(default=0,ge=-2000,le=2000)
    offset_v: float = Field(default=0,ge=-2000,le=2000)

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start or self.kind == 'annulus' and self.inner_diameter >= self.diameter:
            raise ValueError('Invalid cutting primitive extent or annular diameter')
        return self


class LibraryRecord(BaseModel):
    """Lossless native record. Extensions from newer converters survive project round trips."""
    model_config = ConfigDict(extra='allow', allow_inf_nan=False)
    source_schema: str = Field(alias='schema')
    kind: str
    id: str
    unit_system: Literal['metric', 'inch']
    name: str
    geometry: dict = Field(default_factory=dict)
    hydraulic: dict = Field(default_factory=dict)
    threads: list[dict] = Field(default_factory=list)
    machining: list[dict] = Field(default_factory=list)
    engineering: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)

    @model_serializer(mode='wrap')
    def lossless(self, handler):
        data = handler(self)
        data = {k:v for k,v in data.items() if k in self.model_fields_set or k in (self.model_extra or {})}
        data['schema'] = data.pop('source_schema')
        return data


class NativeLibrarySnapshot(Strict):
    record: LibraryRecord
    related_records: list[dict] = Field(default_factory=list, max_length=200)
    mapping_record: LibraryRecord | None = None
    mapping_related_records: list[dict] | None = Field(default=None,max_length=200)
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    origin: str = 'VEST MDTools 930'
    geometry_status: Literal['draft-projection', 'imported-dimensional', 'engineer-mapped'] = 'draft-projection'
    geometry_notes: list[str] = Field(default_factory=list)
    mapping_decision: str = Field(default='', max_length=2000)
    machining_status: Literal['unresolved', 'engineer-reviewed'] = 'unresolved'
    machining_decision: str = Field(default='', max_length=2000)
    derived_from: str = ''
    datum_mode: Literal['step0-relative', 'surface-relative'] = 'step0-relative'

    @model_validator(mode='after')
    def decisions(self):
        if self.geometry_status == 'engineer-mapped' and not self.mapping_decision.strip():
            raise ValueError('Geometry mapping requires an engineering decision')
        if self.machining_status == 'engineer-reviewed' and not self.machining_decision.strip():
            raise ValueError('Machining review requires an engineering decision')
        return self


class LibraryLineage(Strict):
    kind: Literal['imported-mdtools','pmc-derived','pmc-custom','demo-provisional']
    original_source: str = Field(max_length=500)
    source_sha256: str | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')
    derived_from: str = Field(default='',max_length=240)
    revision_history: list[str] = Field(default_factory=list,max_length=100)


class CartridgeCompatibility(Strict):
    model: str = Field(min_length=1,max_length=120)
    manufacturer: str = Field(default='',max_length=120)
    source: str = Field(min_length=1,max_length=500)
    status: Literal['documented','engineer-confirmed','unconfirmed'] = 'unconfirmed'


class ComponentBoundary(Strict):
    category: Literal['mounting-footprint','external-body','service','tool'] = 'mounting-footprint'
    points: list[tuple[float,float]] = Field(default_factory=list,max_length=100)
    circle: tuple[float,float,Positive] | None = None
    height: float = Field(default=0,ge=0,le=2000)
    source: str = Field(min_length=1,max_length=500)
    status: Literal['source-mapped','engineer-confirmed'] = 'source-mapped'
    source_role: str = Field(default='',max_length=80)
    source_type: str = Field(default='',max_length=120)
    source_raw: str = Field(default='',max_length=20000)
    source_sha256: str | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')
    association: Literal['source-linked','engineer-selected'] = 'source-linked'

    @model_validator(mode='after')
    def finite_boundary(self):
        if (self.circle is None and len(self.points)<3) or (self.circle and self.points):
            raise ValueError('Boundary requires a polygon or an exact circle, not both')
        if any(abs(v)>2000 for p in self.points for v in p):
            raise ValueError('Boundary coordinate exceeds 2000 mm')
        if self.circle and any(abs(v)>2000 for v in self.circle):
            raise ValueError('Boundary circle exceeds 2000 mm')
        return self


class CavityDefinition(Strict):
    id: Identifier
    label: str = Field(max_length=120)
    source: str = Field(min_length=1, max_length=500)
    demo_only: bool = True
    thread_note: str = Field(max_length=300)
    stages: list[Stage] = Field(min_length=1, max_length=40)
    zones: list[Zone] = Field(default_factory=list, max_length=64)
    clearance_diameter: Positive
    clearance_height: Positive
    manufacturer: str = Field(default='PMC Demo', max_length=120)
    cartridge_models: list[str] = Field(default_factory=list, max_length=40)
    valve_function: str = Field(default='Unspecified', max_length=160)
    revision: str = Field(default='1', min_length=1, max_length=80)
    provenance: Literal['demo', 'candidate', 'drawing-verified'] = 'demo'
    drawing_asset: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    machining_notes: str = Field(default='', max_length=2000)
    tooling: list[str] = Field(default_factory=list, max_length=30)
    native: NativeLibrarySnapshot | None = None
    cutting_primitives: list[CuttingPrimitive] = Field(default_factory=list, max_length=180)
    catalog_id: str = Field(default='',max_length=120)
    lineage: LibraryLineage | None = None
    compatible_cartridges: list[CartridgeCompatibility] = Field(default_factory=list,max_length=100)
    boundaries: list[ComponentBoundary] = Field(default_factory=list,max_length=40)
    usage_role: Literal['cartridge-cavity','external-port'] | None = None
    usage_decision: str = Field(default='',max_length=1000)

    @model_validator(mode='after')
    def consistent(self):
        # Legacy definitions retain their source role; window count is never a role.
        source_type = ''
        if self.native:
            record = self.native.record.model_dump()
            source_type = str(record.get('cavity_type', record.get('source_identity', {}).get('cavity_type', ''))).upper()
        source_role = 'external-port' if source_type in ('P','PORT') else 'cartridge-cavity'
        if self.usage_role is None:
            self.usage_role = source_role
        if self.usage_role != source_role and not self.usage_decision.strip():
            raise ValueError('Changing definition usage role requires an explicit engineering decision')
        if self.lineage is None:
            kind = ('pmc-derived' if self.native.derived_from else 'imported-mdtools') if self.native else ('demo-provisional' if self.demo_only else 'pmc-custom')
            self.lineage = LibraryLineage(kind=kind,original_source=self.source,
                                         source_sha256=self.native.source_sha256 if self.native else None,
                                         derived_from=self.native.derived_from if self.native else '')
        end = 0
        previous_diameter = float('inf')
        for s in self.stages:
            if abs(s.start - end) > 1e-6 or s.diameter > previous_diameter:
                raise ValueError('Stages must be contiguous from zero and non-increasing in diameter')
            end, previous_diameter = s.end, s.diameter
        if len({z.id for z in self.zones}) != len(self.zones):
            raise ValueError('Duplicate cavity zone')
        for z in self.zones:
            if not any(s.start <= z.start < z.end <= s.end and z.diameter <= s.diameter for s in self.stages) and not self.cutting_primitives:
                raise ValueError('Each hydraulic zone must fit inside one cutting stage')
        for i, a in enumerate(self.zones):
            for b in self.zones[i + 1:]:
                if not self.cutting_primitives and a.offset_u == b.offset_u and a.offset_v == b.offset_v and min(a.end, b.end) > max(a.start, b.start):
                    raise ValueError('Hydraulic zones must not overlap axially')
        if self.clearance_diameter < max(s.diameter for s in self.stages):
            raise ValueError('Installation envelope must cover the cavity mouth')
        import math
        if any(2*math.hypot(s.offset_u,s.offset_v)+max(s.diameter,s.end_diameter)>self.clearance_diameter+1e-6 for s in self.cutting_primitives):
            raise ValueError('Installation envelope must cover all mapped footprint cuts')
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
    suppressed: bool = False
    rotation: float = Field(default=0, ge=-360, le=360)
    cartridge_model: str = Field(default='', max_length=120)
    schematic_id: str = Field(default='', max_length=80)
    route_net: Circuit | None = None
    frozen_net: Circuit | None = None
    direction: tuple[float,float,float] | None = None
    machining_id: str = Field(default='', max_length=60)
    parent_id: Identifier | None = None
    local_offset: tuple[float, float] = (0, 0)

    @model_validator(mode='after')
    def fields_for_kind(self):
        if self.route_net or self.frozen_net:
            owner = self.route_net or self.frozen_net
            if self.kind != 'drilling' or self.circuit != owner or self.route_net and self.frozen_net:
                raise ValueError('Route circuit must match its single owner net; reroute or explicitly detach before changing hydraulic intent')
        if self.direction is not None:
            import math
            from .kinematics import FACE_AXES
            _,_,axis,sign=FACE_AXES[self.face]
            length=math.sqrt(sum(x*x for x in self.direction))
            if self.kind!='drilling' or length<1e-6 or self.direction[axis]*sign/length<0.25:
                raise ValueError('Angled direction requires an inward drilling axis with entry cosine >= 0.25')
            self.direction=tuple(x/length for x in self.direction)
        if self.kind == 'cavity':
            if not self.definition or self.circuit is not None or self.diameter is not None or self.depth is not None or self.plugged:
                raise ValueError('Cavity uses definition and circuits, not bore fields')
        elif self.kind=='port' and self.definition:
            if self.circuit is None or self.circuits or self.plugged:
                raise ValueError('Definition port requires one hydraulic net and no cartridge circuits')
        elif self.circuit is None or self.diameter is None or self.depth is None or self.definition or self.circuits:
            raise ValueError('Bore requires circuit, diameter, depth; no cavity definition')
        if self.plugged and (self.kind != 'drilling' or self.plug_length >= self.depth):
            raise ValueError('Plug requires a drilling deeper than its engagement')
        if self.kind == 'port' and not self.definition and self.clearance_diameter < self.diameter:
            raise ValueError('Port clearance diameter cannot be smaller than bore')
        return self


class ConstructionAccess(Strict):
    id: Identifier
    face: Face
    fraction: float = Field(default=0.72, ge=0.1, le=0.9)


class HydraulicNet(Strict):
    id: Circuit
    label: str = Field(default='', max_length=120)
    members: list[str] = Field(default_factory=list, max_length=60)
    routing: Literal['manual', 'automatic'] = 'manual'
    drilling_mode: Literal['orthogonal','allow-angled','simplest'] = 'orthogonal'
    diameter: Positive = 8
    preferred_axis: Literal['auto', 'x', 'y', 'z'] = 'auto'
    entry_preference: Literal['nearest', 'positive', 'negative'] = 'nearest'
    construction_access: list[ConstructionAccess] = Field(default_factory=list, max_length=8)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    flow_lpm: float | None = Field(default=None, gt=0, le=10000)
    pressure_bar: float | None = Field(default=None, gt=0, le=2000)
    velocity_limit: float = Field(default=6, gt=0, le=100)
    routing_variant: str | None = Field(default=None, pattern=r'^([xyz]{3}:(nearest|positive|negative):(direct|offset_[xyz]_[pm]2?)|simple_[0-9]+)$')


class SchematicComponent(Strict):
    id: Identifier
    label: str = Field(default='', max_length=160)
    function: str = Field(default='', max_length=200)
    cartridge_model: str = Field(default='', max_length=120)
    cavity_definition: Identifier | None = None
    ports: dict[str, Circuit] = Field(default_factory=dict)
    feature_id: Identifier | None = None
    status: Literal['unconfirmed', 'confirmed'] = 'unconfirmed'


class DesignConstraints(Strict):
    preferred_wall_margin: float = Field(default=4, ge=0, le=50)
    envelope_max: tuple[Positive, Positive, Positive] | None = None
    envelope_min: tuple[Positive, Positive, Positive] | None = None
    required_feature_faces: dict[Identifier, Face] = Field(default_factory=dict, max_length=120)
    preferred_component_faces: list[Face] = Field(default_factory=lambda: ['top'])
    preferred_port_faces: dict[Circuit, Face] = Field(default_factory=dict)
    priority: Literal['compact', 'fewer_plugs', 'simple_machining', 'short_drills'] = 'fewer_plugs'
    standard_drills: list[Positive] = Field(default_factory=lambda: [4, 5, 6, 8, 10, 12, 16, 20])
    forbidden_drilling_faces: list[Face] = Field(default_factory=list, max_length=6)
    notes: str = Field(default='', max_length=4000)


class SchematicAsset(Strict):
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    name: str = Field(min_length=1, max_length=180)
    media_type: Literal['application/pdf', 'image/png', 'image/jpeg']
    size: int = Field(gt=0, le=20_000_000)


class Rules(Strict):
    minimum_wall: Positive = 7
    minimum_overlap_volume: float = Field(default=0.1, ge=0.01, le=10)
    max_depth_diameter_ratio: Positive = 20
    minimum_access_gap: Positive = 2


class EngineeringReview(Strict):
    """Uncertainty travels with the editable design, independent of its author/provider."""
    id: Identifier
    kind: Literal['assumption', 'component', 'dimension', 'connection', 'source', 'other'] = 'assumption'
    subject: str = Field(default='', max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    proposed_value: str = Field(default='', max_length=1000)
    severity: Literal['review', 'blocking'] = 'review'
    status: Literal['open', 'accepted', 'resolved'] = 'open'
    resolution: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def reviewed(self):
        if self.status != 'open' and not self.resolution.strip():
            raise ValueError('Accepted or resolved review items require an engineering decision note')
        return self


class AITrace(Strict):
    analysis_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    run_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    generation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    input_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    result_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    original_requirements: str = Field(default='', max_length=20000)


class DesignOrigin(Strict):
    author: str = Field(default='', max_length=120)
    method: Literal['manual', 'ai-assisted', 'drawing-import', 'unknown'] = 'unknown'
    provider: str = Field(default='', max_length=120)
    model: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=2000)
    ai_trace: AITrace | None = None


class EngineeringLibraryResource(Strict):
    id: str = Field(min_length=1,max_length=200)
    unit_system: Literal['metric','inch','shared']
    kind: str = Field(min_length=1,max_length=80)
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    record: dict | list


class Design(Strict):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    units: Literal['mm'] = 'mm'
    project_context: Literal['metric', 'inch'] = 'metric'
    block: Block
    rules: Rules = Field(default_factory=Rules)
    library: list[CavityDefinition] = Field(default_factory=list, max_length=30)
    features: list[Feature] = Field(default_factory=list, max_length=120)
    nets: list[HydraulicNet] = Field(default_factory=list, max_length=40)
    components: list[SchematicComponent] = Field(default_factory=list, max_length=60)
    schematics: list[SchematicAsset] = Field(default_factory=list, max_length=20)
    constraints: DesignConstraints = Field(default_factory=DesignConstraints)
    review_items: list[EngineeringReview] = Field(default_factory=list, max_length=100)
    origin: DesignOrigin = Field(default_factory=DesignOrigin)
    library_resources: list[EngineeringLibraryResource] = Field(default_factory=list,max_length=100)

    @model_validator(mode='after')
    def references(self):
        if len({r.id for r in self.review_items}) != len(self.review_items):
            raise ValueError('Engineering review IDs must be unique')
        ids = [f.id for f in self.features]
        lib = {d.id: d for d in self.library}
        if len(set(ids)) != len(ids) or len(lib) != len(self.library):
            raise ValueError('IDs must be unique')
        nodes = set()
        for f in self.features:
            if f.kind=='port' and f.definition:
                if f.definition not in lib:raise ValueError(f'{f.id}: missing port machining definition')
                d=lib[f.definition]
                if d.usage_role != 'external-port':
                    raise ValueError(f'{f.id}: definition usage role is not external-port')
                if len(d.zones)!=1 or d.zones[0].offset_u or d.zones[0].offset_v:
                    raise ValueError(f'{f.id}: external port definition requires one centered hydraulic interface')
                centered=[p.diameter for p in d.cutting_primitives if p.kind=='cylinder' and not p.offset_u and not p.offset_v]
                f.diameter=min(centered or [s.diameter for s in d.stages])
                f.depth=d.zones[0].end
                f.tip_angle=180
                f.clearance_diameter=d.clearance_diameter
                f.clearance_height=d.clearance_height
            if f.kind == 'cavity':
                if f.definition not in lib:
                    raise ValueError(f'{f.id}: missing library definition')
                if lib[f.definition].usage_role != 'cartridge-cavity':
                    raise ValueError(f'{f.id}: definition usage role is not cartridge-cavity')
                if set(f.circuits) != {z.id for z in lib[f.definition].zones}:
                    raise ValueError(f'{f.id}: assign a circuit to every hydraulic zone')
                nodes.update(f'{f.id}:{z}' for z in f.circuits)
            else:
                nodes.add(f.id)
        for f in self.features:
            if len(set(f.connects_to)) != len(f.connects_to):
                raise ValueError(f'{f.id}: duplicate connection')
            for target in f.connects_to:
                generated = target.startswith('R-') and any(n.routing == 'automatic' for n in self.nets)
                if (target not in nodes and not generated) or target.split(':')[0] == f.id:
                    raise ValueError(f'{f.id}: invalid connection target {target}')
            if f.kind == 'cavity' and f.connects_to:
                raise ValueError('Declare cavity connections on incoming bores using cavity:zone IDs')
            if f.parent_id:
                parents = {item.id: item for item in self.features}
                seen = {f.id}
                p = f.parent_id
                while p:
                    if p not in parents or p in seen:
                        raise ValueError('Parent links must exist and form an acyclic hierarchy')
                    seen.add(p)
                    p = parents[p].parent_id
        if len({n.id for n in self.nets}) != len(self.nets):
            raise ValueError('Duplicate hydraulic net ID')
        accesses = [a.id for n in self.nets for a in n.construction_access]
        if len(set(accesses)) != len(accesses) or any(a in ids for a in accesses):
            # Resolved snapshots may contain the generated implementation of an access.
            for access in accesses:
                matches = [f for f in self.features if f.id == access]
                if len(set(accesses)) != len(accesses) or (matches and not all(f.route_net for f in matches)):
                    raise ValueError('Construction access IDs must be unique and not collide with authored features')
        for f in self.features:
            if f.route_net and (f.kind != 'drilling' or not any(n.id == f.route_net and n.routing == 'automatic' for n in self.nets)):
                raise ValueError('Generated drilling requires an automatic owner net')
        terminals = {f'{f.id}:{z}': net for f in self.features if f.kind == 'cavity' for z, net in f.circuits.items()}
        terminals.update({f.id: f.circuit for f in self.features if f.kind == 'port'})
        if not self.nets:
            self.nets = [HydraulicNet(id=n, members=sorted(k for k, v in terminals.items() if v == n))
                         for n in sorted(set(terminals.values()))]
        for f in self.features:
            if f.frozen_net and not any(n.id == f.frozen_net and n.routing == 'manual' for n in self.nets):
                raise ValueError('Frozen drilling requires its existing manual owner net; use Reroute to change route intent')
        declared = {}
        for net in self.nets:
            if len(set(net.members)) != len(net.members):
                raise ValueError(f'{net.id}: duplicate interface')
            for member in net.members:
                if member not in terminals or terminals[member] != net.id or member in declared:
                    raise ValueError(f'{net.id}: invalid or conflicting interface {member}')
                declared[member] = net.id
        if set(declared) != set(terminals):
            raise ValueError('Every cavity interface and external port must belong to exactly one net')
        if len({c.id for c in self.components}) != len(self.components):
            raise ValueError('Duplicate schematic component ID')
        for component in self.components:
            if component.feature_id and component.feature_id not in ids:
                raise ValueError(f'{component.id}: missing placed feature')
            if component.cavity_definition and component.cavity_definition not in lib:
                raise ValueError(f'{component.id}: missing cavity definition')
        return self
