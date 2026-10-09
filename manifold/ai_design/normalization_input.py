"""Private typed failure input for local investigation, never executable analysis."""
from typing import Literal
from pydantic import Field
from ..schema import Strict
from .models import Digest, RecordId
from .semantic import CircuitReading
from .identity_reading import IdentityReading


class NormalizationInput(Strict):
    schema_version: Literal[1] = 1
    rejected: Literal[True] = True
    task_id: RecordId
    run_id: RecordId
    input_revision: Digest
    reading: CircuitReading
    identity_reading: IdentityReading | None = None
    page_counts: dict[str,int]
    identity_omissions: list[tuple[int,Literal['manufacturer','model','cavity','mounting_interface']]] = Field(default_factory=list)
