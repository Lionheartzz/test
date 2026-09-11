"""Engineer choices, distinct from provider observations and immutable run data."""
from pydantic import Field
from ..schema import Strict, Face
from .models import Key, Digest, RecordId


class Binding(Strict):
    definition_key: str = Field(min_length=1, max_length=180)
    definition_sha256: Digest
    zone_ports: dict[str, Key] = Field(default_factory=dict, max_length=12)
    decision: str = Field(default='', max_length=2000)


class GenerationOptions(Strict):
    bindings: dict[Key, Binding] = Field(default_factory=dict, max_length=12)
    port_definitions: dict[Key, Binding] = Field(default_factory=dict, max_length=24)
    net_overrides: dict[Key, str] = Field(default_factory=dict, max_length=80)
    topology_decision: str = Field(default='', max_length=2000)
    component_faces: dict[Key, Face] = Field(default_factory=dict, max_length=12)
    port_faces: dict[Key, Face] = Field(default_factory=dict, max_length=24)
    placement_decision: str = Field(default='', max_length=2000)
    drilling_diameter: float = Field(default=8, ge=3, le=32)
    port_diameter: float = Field(default=12, ge=4, le=50)
    port_depth: float = Field(default=12, ge=6, le=50)
    minimum_wall: float = Field(default=7, ge=3, le=30)
    max_attempts: int = Field(default=4, ge=1, le=6)


class GenerationRequest(Strict):
    expected_revision: Digest
    run_id: RecordId
    options: GenerationOptions = Field(default_factory=GenerationOptions)
