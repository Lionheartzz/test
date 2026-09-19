import math
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
    material_id: Identifier | None = None
    stock_id: Identifier | None = None
    stock_dimensions: tuple[Positive, Positive, Positive] | None = None
    machining_allowance: tuple[float, float, float] | None = None

    @model_serializer(mode='wrap')
    def compact_optional_master_state(self,handler):
        value=handler(self)
        for key in ('material_id','stock_id','stock_dimensions','machining_allowance'):
            if value.get(key) is None:value.pop(key,None)
        return value

    @model_validator(mode='after')
    def stock_is_not_finished_geometry(self):
        selected=bool(self.stock_id)
        if selected != bool(self.stock_dimensions) or selected != bool(self.machining_allowance):
            raise ValueError('Stock selection requires its separate stock dimensions and machining allowance')
        if self.stock_id and not self.material_id:
            raise ValueError('Stock selection requires a source-backed material')
        if self.machining_allowance and any(value < 0 or value > 200 for value in self.machining_allowance):
            raise ValueError('Machining allowance must be between 0 and 200 mm')
        if self.stock_dimensions and any(stock + 1e-6 < finished+2*allowance for stock,finished,allowance in
                                         zip(self.stock_dimensions,(self.length,self.width,self.height),self.machining_allowance)):
            raise ValueError('Selected stock must contain the finished block plus declared machining allowance on both sides')
        return self


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


class ComponentBoundary(Strict):
    category: Literal['mounting-footprint','external-body','service','tool'] = 'mounting-footprint'
    points: list[tuple[float,float]] = Field(default_factory=list,max_length=100)
    circle: tuple[float,float,Positive] | None = None
    height: float = Field(default=0,ge=0,le=2000)

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
    """Executable engineering definition loaded from SQLite, never project state."""
    id: Identifier
    label: str = Field(max_length=120)
    family: str = Field(default='',max_length=160)
    unit_system: Literal['metric','inch','custom'] = 'custom'
    thread_note: str = Field(default='',max_length=300)
    thread_definition_id: Identifier | None = None
    stages: list[Stage] = Field(min_length=1, max_length=40)
    zones: list[Zone] = Field(default_factory=list, max_length=64)
    clearance_diameter: Positive
    clearance_height: Positive
    manufacturer: str = Field(default='', max_length=120)
    cutting_primitives: list[CuttingPrimitive] = Field(default_factory=list, max_length=180)
    boundaries: list[ComponentBoundary] = Field(default_factory=list,max_length=40)
    machining: list[dict] = Field(default_factory=list,max_length=100)
    usable: bool = True
    unusable_reason: str = Field(default='',max_length=1000)
    active: bool = True
    kind: Literal['cavity','external-port'] = 'cavity'

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


class MachiningModifierPlacement(Strict):
    modifier_id: Identifier
    start: Coordinate = 0


class Feature(Strict):
    id: Identifier
    kind: Literal['cavity', 'port', 'drilling', 'mounting']
    face: Face
    u: Coordinate
    v: Coordinate
    cavity_id: Identifier | None = None
    port_definition_id: Identifier | None = None
    interface_nets: dict[str, Circuit] = Field(default_factory=dict)
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
    cartridge_id: Identifier | None = None
    schematic_id: str = Field(default='', max_length=80)
    route_net: Circuit | None = None
    frozen_net: Circuit | None = None
    direction: tuple[float,float,float] | None = None
    machining_id: str = Field(default='', max_length=60)
    parent_id: Identifier | None = None
    local_offset: tuple[float, float] = (0, 0)
    through: bool = False
    mounting_mode: Literal['plain','threaded'] = 'plain'
    thread_definition_id: Identifier | None = None
    thread_depth: Positive | None = None
    closure_definition_id: Identifier | None = None
    machining_modifiers: list[MachiningModifierPlacement] = Field(default_factory=list,max_length=20)

    @property
    def definition(self):
        return self.cavity_id if self.kind=='cavity' else self.port_definition_id

    @definition.setter
    def definition(self,value):
        if self.kind=='cavity':self.cavity_id=value
        else:self.port_definition_id=value

    @property
    def circuits(self):return self.interface_nets

    @circuits.setter
    def circuits(self,value):self.interface_nets=value

    @model_serializer(mode='wrap')
    def preserve_legacy_shape(self,handler):
        value=handler(self)
        if self.kind!='mounting':
            value.pop('through',None);value.pop('mounting_mode',None);value.pop('thread_definition_id',None);value.pop('thread_depth',None)
        elif self.mounting_mode=='plain':
            value.pop('mounting_mode',None);value.pop('thread_definition_id',None);value.pop('thread_depth',None)
        if self.kind!='drilling':value.pop('closure_definition_id',None)
        elif value.get('closure_definition_id') is None:value.pop('closure_definition_id',None)
        if not value.get('machining_modifiers'):value.pop('machining_modifiers',None)
        return value

    @model_validator(mode='after')
    def fields_for_kind(self):
        if self.through and self.kind!='mounting':
            raise ValueError('Only an explicit non-hydraulic mounting hole may declare an opposite-face exit')
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
        if self.kind=='mounting':
            if self.circuit is not None or self.interface_nets or self.connects_to or self.definition or self.plugged or self.depth is None or self.closure_definition_id:
                raise ValueError('Mounting hole requires machining depth and no hydraulic identity, cavity, closure or contacts')
            if self.mounting_mode=='plain' and (self.diameter is None or self.thread_definition_id or self.thread_depth):
                raise ValueError('Plain mounting hole requires an explicit diameter and no thread definition')
            if self.mounting_mode=='threaded' and (self.diameter is not None or not self.thread_definition_id or self.thread_depth is None or self.thread_depth>self.depth):
                raise ValueError('Threaded mounting hole requires a thread definition and thread depth no greater than drill depth; tap diameter comes from SQLite')
            if self.through and self.tip_angle!=180:
                raise ValueError('Through mounting geometry uses an explicit flat-ended cut at the exit face')
        elif self.kind == 'cavity':
            if not self.cavity_id or self.port_definition_id or self.circuit is not None or self.diameter is not None or self.depth is not None or self.plugged:
                raise ValueError('Cavity uses definition and circuits, not bore fields')
        elif self.kind=='port' and self.port_definition_id:
            if self.cavity_id or self.circuit is None or self.interface_nets or self.plugged:
                raise ValueError('Definition port requires one hydraulic net and no cartridge circuits')
        elif self.circuit is None or self.diameter is None or self.depth is None or self.definition or self.interface_nets:
            raise ValueError('Bore requires circuit, diameter, depth; no cavity definition')
        if self.plugged and (self.kind != 'drilling' or self.plug_length >= self.depth):
            raise ValueError('Plug requires a drilling deeper than its engagement')
        if self.closure_definition_id and (self.kind!='drilling' or not self.plugged):
            raise ValueError('A closure definition may only bind a plugged construction drilling')
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
    members: list[str] = Field(default_factory=list, max_length=60, exclude=True)
    routing: Literal['manual', 'automatic'] = 'manual'
    drilling_mode: Literal['orthogonal','allow-angled','simplest'] = 'orthogonal'
    diameter: Positive = 8
    diameter_mode: Literal['automatic','manual'] = 'automatic'

    @model_validator(mode='before')
    @classmethod
    def legacy_diameter(cls, value):
        # V1 serialized its unsized 8 mm default everywhere. Preserve other legacy
        # diameter choices; new explicit overrides (including 8) carry their mode.
        if isinstance(value,dict) and 'diameter_mode' not in value and value.get('diameter',8)!=8:
            value={**value,'diameter_mode':'manual'}
        return value
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
    cartridge_id: Identifier | None = None
    cavity_id: Identifier | None = None
    expected_interfaces: list[Identifier] = Field(default_factory=list, max_length=40)
    interface_nets: dict[str, Circuit] = Field(default_factory=dict)
    interface_dispositions: dict[str, Literal['connected','blocked','terminated','unknown']] = Field(default_factory=dict)
    placement_id: Identifier | None = None

    @model_validator(mode='after')
    def expected_port_state(self):
        if not self.expected_interfaces and self.interface_nets:
            self.expected_interfaces=list(self.interface_nets)
        if len(set(self.expected_interfaces))!=len(self.expected_interfaces):
            raise ValueError('Duplicate expected schematic interface')
        if set(self.interface_nets)-set(self.expected_interfaces):
            raise ValueError('Mapped schematic interface must be explicitly expected')
        if set(self.interface_dispositions)-set(self.expected_interfaces):
            raise ValueError('Interface disposition must reference an expected schematic interface')
        for identifier in self.expected_interfaces:
            disposition=self.interface_dispositions.setdefault(identifier,'connected' if identifier in self.interface_nets else 'unknown')
            if disposition=='connected' and identifier not in self.interface_nets:
                continue
            if disposition!='connected' and identifier in self.interface_nets:
                raise ValueError('Blocked, terminated or unknown schematic interfaces cannot map to a hydraulic net')
        return self

    @property
    def feature_id(self):return self.placement_id
    @property
    def cavity_definition(self):return self.cavity_id
    @property
    def ports(self):return self.interface_nets


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


class SchematicIntent(Strict):
    assets: list[SchematicAsset] = Field(default_factory=list,max_length=20)
    components: list[SchematicComponent] = Field(default_factory=list,max_length=60)


class Rules(Strict):
    minimum_wall: Positive = 7
    minimum_overlap_volume: float = Field(default=0.1, ge=0.01, le=10)
    max_depth_diameter_ratio: Positive = 20
    minimum_access_gap: Positive = 2
    allowable_stress_mpa: float | None = Field(default=None, gt=0, le=5000)
    pressure_safety_factor: float = Field(default=2, ge=1, le=10)


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


class DesignOrigin(Strict):
    author: str = Field(default='', max_length=120)
    method: Literal['manual', 'ai-assisted', 'drawing-import', 'unknown'] = 'unknown'
    provider: str = Field(default='', max_length=120)
    model: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=2000)


class Engraving(Strict):
    """A shallow authored production marking; it has no hydraulic identity."""
    id: Identifier
    face: Face
    u: Coordinate
    v: Coordinate
    text: str = Field(min_length=1,max_length=40)
    rotation: float = Field(default=0,ge=-360,le=360)
    text_height: float = Field(default=5,gt=0,le=50)
    depth: float = Field(default=.3,gt=0,le=5)


class BlockModifier(Strict):
    """Deliberately limited stock machining, not a general solid-model feature."""
    id: Identifier
    kind: Literal['rectangular-cutout','chamfer']
    face: Face
    u: Coordinate = 0
    v: Coordinate = 0
    width: Positive | None = None
    height: Positive | None = None
    depth: Positive | None = None
    rotation: float = Field(default=0,ge=-360,le=360)
    size: float | None = Field(default=None,gt=0,le=100)

    @model_validator(mode='after')
    def parameters_for_kind(self):
        if self.kind=='rectangular-cutout' and (None in (self.width,self.height,self.depth) or self.size is not None):
            raise ValueError('Rectangular cutout requires width, height and depth only')
        if self.kind=='chamfer' and (self.size is None or any(value is not None for value in (self.width,self.height,self.depth))):
            raise ValueError('Chamfer requires a size only')
        return self


class Design(Strict):
    schema_version: Literal[2] = 2
    name: str = Field(min_length=1, max_length=120)
    units: Literal['mm'] = 'mm'
    project_context: Literal['metric', 'inch'] = 'metric'
    block: Block
    rules: Rules = Field(default_factory=Rules)
    features: list[Feature] = Field(default_factory=list, max_length=120)
    nets: list[HydraulicNet] = Field(default_factory=list, max_length=40)
    schematic_intent: SchematicIntent | None = None
    constraints: DesignConstraints = Field(default_factory=DesignConstraints)
    review_items: list[EngineeringReview] = Field(default_factory=list, max_length=100)
    origin: DesignOrigin = Field(default_factory=DesignOrigin)
    engravings: list[Engraving] = Field(default_factory=list,max_length=80)
    block_modifiers: list[BlockModifier] = Field(default_factory=list,max_length=40)

    @property
    def components(self):return self.schematic_intent.components if self.schematic_intent else []
    @property
    def schematics(self):return self.schematic_intent.assets if self.schematic_intent else []

    @model_validator(mode='after')
    def references(self):
        if len({r.id for r in self.review_items}) != len(self.review_items):
            raise ValueError('Engineering review IDs must be unique')
        ids = [f.id for f in self.features]
        authored_ids=ids+[row.id for row in self.engravings]+[row.id for row in self.block_modifiers]
        if len(set(authored_ids)) != len(authored_ids):
            raise ValueError('IDs must be unique')
        from .kinematics import FACE_AXES,dimensions
        dims=dimensions(self.block)
        for row in self.engravings:
            u,v,_,_=FACE_AXES[row.face]
            if row.u>dims[u] or row.v>dims[v]:raise ValueError(f'{row.id}: engraving origin is outside its block face')
        for row in self.block_modifiers:
            u,v,axis,_=FACE_AXES[row.face]
            if row.kind=='rectangular-cutout':
                angle=math.radians(row.rotation)
                extent_u=(abs(row.width*math.cos(angle))+abs(row.height*math.sin(angle)))/2
                extent_v=(abs(row.width*math.sin(angle))+abs(row.height*math.cos(angle)))/2
                if row.u<extent_u or row.u+extent_u>dims[u] or row.v<extent_v or row.v+extent_v>dims[v] or row.depth>dims[axis]:
                    raise ValueError(f'{row.id}: rectangular cutout must remain within the finished block')
            elif row.size>=min(dims)/2:
                raise ValueError(f'{row.id}: chamfer size is too large for the block')
        nodes = set()
        for f in self.features:
            if f.kind == 'cavity':
                nodes.update(f'{f.id}:{z}' for z in f.circuits)
            elif f.kind!='mounting':
                nodes.add(f.id)
            if f.kind=='mounting' and f.through:
                from .kinematics import FACE_AXES,dimensions
                if abs(f.depth-dimensions(self.block)[FACE_AXES[f.face][2]])>1e-6:
                    raise ValueError(f'{f.id}: through mounting depth must equal the block thickness on its declared axis')
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
        access_owners = {a.id:n.id for n in self.nets for a in n.construction_access}
        if len(set(accesses)) != len(accesses) or any(a in ids for a in accesses):
            # Resolved and deliberately frozen routes may contain the implementation
            # of an explicitly declared construction access on the same net.
            for access in accesses:
                matches = [f for f in self.features if f.id == access]
                owner=access_owners[access]
                if len(set(accesses)) != len(accesses) or (matches and not all(f.route_net==owner or f.frozen_net==owner for f in matches)):
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
        net_ids={net.id for net in self.nets}
        if set(terminals.values())-net_ids:
            raise ValueError('Every cavity interface and external port must reference an existing net')
        for net in self.nets:
            net.members=sorted(key for key,value in terminals.items() if value==net.id)
        if len({c.id for c in self.components}) != len(self.components):
            raise ValueError('Duplicate schematic component ID')
        for component in self.components:
            if component.placement_id and component.placement_id not in ids:
                raise ValueError(f'{component.id}: missing placed feature')
        return self
