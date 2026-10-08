"""Engineer choices, distinct from provider observations and immutable run data."""
from pydantic import Field
from ..schema import Strict, Face
from .models import Key, Digest, RecordId
from ..limits import ANALYSIS_COMPONENTS, ANALYSIS_PORTS, COMPONENT_INTERFACES


class Binding(Strict):
    definition_key: str = Field(min_length=1, max_length=180)
    definition_sha256: Digest
    zone_ports: dict[str, Key] = Field(default_factory=dict, max_length=COMPONENT_INTERFACES)
    decision: str = Field(default='', max_length=2000)


class ThreadedMountingHole(Strict):
    requirement_id: Key | None = None
    thread_definition_id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
    face: Face = 'top'
    u: float = Field(ge=0,le=2000)
    v: float = Field(ge=0,le=2000)
    depth: float = Field(gt=0,le=2000)
    thread_depth: float = Field(gt=0,le=2000)
    through: bool = False


class GenerationOptions(Strict):
    preferred_component_face: Face | None = None
    preferred_port_face: Face | None = None
    bindings: dict[Key, Binding] = Field(default_factory=dict, max_length=ANALYSIS_COMPONENTS)
    port_definitions: dict[Key, Binding] = Field(default_factory=dict, max_length=ANALYSIS_PORTS)
    provisional_ports: dict[Key, str] = Field(default_factory=dict,max_length=ANALYSIS_PORTS)
    threaded_mounting_holes: list[ThreadedMountingHole] = Field(default_factory=list,max_length=40)
    mounting_decision: str = Field(default='',max_length=2000)
    net_overrides: dict[Key, str] = Field(default_factory=dict, max_length=ANALYSIS_PORTS)
    topology_decision: str = Field(default='', max_length=2000)
    component_faces: dict[Key, Face] = Field(default_factory=dict, max_length=ANALYSIS_COMPONENTS)
    port_faces: dict[Key, Face] = Field(default_factory=dict, max_length=ANALYSIS_PORTS)
    placement_decision: str = Field(default='', max_length=2000)
    drilling_diameter: float = Field(default=8, ge=3, le=32)
    port_diameter: float = Field(default=12, ge=4, le=50)
    port_depth: float = Field(default=12, ge=6, le=50)
    minimum_wall: float | None = Field(default=None, gt=0, le=30)
    max_attempts: int = Field(default=4, ge=1, le=6)
    max_exact_attempts: int = Field(default=2, ge=1, le=8)
    # Existing total generation budget, now enforced even during native CAD.
    max_runtime_s: int = Field(default=480, ge=10, le=480)


class GenerationRequest(Strict):
    expected_revision: Digest
    run_id: RecordId
    options: GenerationOptions = Field(default_factory=GenerationOptions)
