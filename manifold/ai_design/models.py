"""Versioned circuit/intent contract, independent of physical manifold placement."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from ..schema import Strict, SchematicAsset

Key=Annotated[str,Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')]
Digest=Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]
RecordId=Annotated[str,Field(pattern=r'^[0-9a-f]{32}$')]
Text=Annotated[str,Field(max_length=4000)]
Scalar=Annotated[str,Field(max_length=2000)] | float | bool | None
Origin=Literal['schematic','user_requirement','knowledge_base','ai_inference','unknown','mock_fixture']


class InputDocument(Strict):
    id: Key
    asset: SchematicAsset
    # Unknown PDF page counts stay unknown until a document adapter verifies them.
    page_count: int | None = Field(default=None,ge=1,le=1000)


class TaskInput(Strict):
    title: str = Field(min_length=1,max_length=120)
    documents: list[InputDocument] = Field(default_factory=list,max_length=20)
    engineering_requirements: str = Field(default='',max_length=20000)
    project_context: Literal['metric','inch'] = 'metric'
    linked_project_id: RecordId | None = None

    @model_validator(mode='after')
    def unique_documents(self):
        if len({d.id for d in self.documents})!=len(self.documents):raise ValueError('Duplicate document ID')
        if sum(d.asset.size for d in self.documents)>100_000_000:raise ValueError('Analysis documents exceed 100 MB')
        return self


class KnowledgeReference(Strict):
    resolver: str = Field(min_length=1,max_length=120)
    record_id: str = Field(min_length=1,max_length=240)
    revision: str = Field(min_length=1,max_length=120)
    sha256: Digest


class Evidence(Strict):
    id: Key
    kind: Origin
    document_id: Key | None = None
    page: int | None = Field(default=None,ge=1,le=1000)
    # Normalized top-left x,y,width,height in the displayed, unrotated page.
    bbox: tuple[float,float,float,float] | None = None
    quote: Text = ''
    requirement_span: tuple[int,int] | None = None
    knowledge: KnowledgeReference | None = None
    explanation: Text = ''

    @model_validator(mode='after')
    def coordinates(self):
        if self.bbox:
            x,y,w,h=self.bbox
            if min(x,y)<0 or min(w,h)<=0 or x+w>1.000001 or y+h>1.000001:raise ValueError('Invalid normalized source box')
            if not self.document_id or not self.page:raise ValueError('Source box needs a document and page')
        if self.kind=='schematic' and (not self.document_id or not self.page):raise ValueError('Schematic evidence needs a document and page')
        if self.kind=='user_requirement' and self.requirement_span is None:raise ValueError('User evidence needs an exact text span')
        if self.kind=='knowledge_base' and self.knowledge is None:raise ValueError('Knowledge evidence needs a versioned source')
        if self.requirement_span is not None and (self.kind!='user_requirement' or not 0<=self.requirement_span[0]<self.requirement_span[1]):raise ValueError('Invalid requirement span')
        if self.knowledge and self.kind!='knowledge_base':raise ValueError('Knowledge reference needs knowledge provenance')
        return self


class Claim(Strict):
    id: Key
    subject_id: Key
    predicate: str = Field(min_length=1,max_length=80)
    value: Scalar = None
    unit: str = Field(default='',max_length=40)
    kind: Origin
    status: Literal['confirmed','uncertain','unresolved'] = 'unresolved'
    confidence: float | None = Field(default=None,ge=0,le=1)
    evidence_ids: list[Key] = Field(default_factory=list,max_length=20)
    alternatives: list[Annotated[str,Field(max_length=300)]] = Field(default_factory=list,max_length=12)
    explanation: Text = ''

    @model_validator(mode='after')
    def unknown_is_not_fact(self):
        if self.kind=='unknown' and (self.value is not None or self.status!='unresolved'):raise ValueError('Unknown claims must remain unresolved with null value')
        if self.value is None and self.status=='confirmed':raise ValueError('A null value cannot be confirmed')
        if self.kind in ('schematic','user_requirement','knowledge_base','mock_fixture') and not self.evidence_ids:raise ValueError('Source-backed claims require evidence')
        return self


class Component(Strict):
    id: Key
    port_ids: list[Key] = Field(default_factory=list,max_length=40)
    claim_ids: list[Key] = Field(min_length=1,max_length=80)


class HydraulicPort(Strict):
    id: Key
    component_id: Key | None = None  # None means an external manifold terminal.
    claim_ids: list[Key] = Field(min_length=1,max_length=40)
    disposition: Literal['connected','blocked','terminated','unknown'] = 'unknown'


class HydraulicNet(Strict):
    id: Key
    members: list[Key] = Field(min_length=1,max_length=100)
    claim_ids: list[Key] = Field(min_length=1,max_length=40)


class DesignIntent(Strict):
    id: Key
    category: Literal['component_selection','port_face','envelope','material','mounting','pressure','flow','routing','separation','priority','serviceability','source_instruction','other']
    target_labels: list[Annotated[str,Field(max_length=120)]] = Field(default_factory=list,max_length=30)
    property: str = Field(min_length=1,max_length=80)
    operator: Literal['equal','maximum','minimum','prefer','avoid','separate','context']
    strength: Literal['requirement','preference','context'] = 'requirement'
    claim_id: Key
    # Labels are not silently bound to an internal port/component ID.
    bound_entity_ids: list[Key] = Field(default_factory=list,max_length=30)


class Unresolved(Strict):
    id: Key
    subject_ids: list[Key] = Field(default_factory=list,max_length=40)
    reason: Literal['missing','ambiguous','conflict','knowledge_unavailable','unsupported','review_required']
    description: Text
    question: Text = ''


class KnowledgeLookup(Strict):
    id: Key
    component_id: Key
    manufacturer: str = Field(default='',max_length=120)
    model: str = Field(default='',max_length=120)
    status: Literal['unresolved','ambiguous','resolved'] = 'unresolved'
    candidates: list[KnowledgeReference] = Field(default_factory=list,max_length=20)
    message: Text = ''


class HydraulicRepresentation(Strict):
    schema_version: Literal[1] = 1
    components: list[Component] = Field(default_factory=list,max_length=120)
    ports: list[HydraulicPort] = Field(default_factory=list,max_length=600)
    nets: list[HydraulicNet] = Field(default_factory=list,max_length=300)
    claims: list[Claim] = Field(default_factory=list,max_length=2000)
    evidence: list[Evidence] = Field(default_factory=list,max_length=2000)
    design_intent: list[DesignIntent] = Field(default_factory=list,max_length=200)
    unresolved: list[Unresolved] = Field(default_factory=list,max_length=1000)
    knowledge: list[KnowledgeLookup] = Field(default_factory=list,max_length=120)
    warnings: list[Text] = Field(default_factory=list,max_length=100)

    @model_validator(mode='after')
    def references(self):
        def index(rows):
            result={r.id:r for r in rows}
            if len(result)!=len(rows):raise ValueError('Duplicate representation ID')
            return result
        entities=index([*self.components,*self.ports,*self.nets,*self.design_intent])
        claims=index(self.claims);evidence=index(self.evidence)
        index(self.unresolved);index(self.knowledge)
        ports=index(self.ports);components=index(self.components)
        for claim in self.claims:
            if claim.subject_id not in entities:raise ValueError('Claim subject is missing')
            for key in claim.evidence_ids:
                if key not in evidence:raise ValueError('Claim evidence is missing')
            if claim.kind in ('schematic','user_requirement','knowledge_base','mock_fixture') and not any(evidence[k].kind==claim.kind for k in claim.evidence_ids):raise ValueError('Claim/evidence provenance mismatch')
        for entity in [*self.components,*self.ports,*self.nets]:
            for key in entity.claim_ids:
                if key not in claims or claims[key].subject_id!=entity.id:raise ValueError('Entity claim does not belong to that entity')
        for component in self.components:
            if len(set(component.port_ids))!=len(component.port_ids):raise ValueError('Duplicate component port')
            if set(component.port_ids)!={p.id for p in self.ports if p.component_id==component.id}:raise ValueError('Component/port ownership mismatch')
        for port in self.ports:
            if port.component_id and port.component_id not in components:raise ValueError('Port owner missing')
        assigned=set()
        for net in self.nets:
            if any(p not in ports or p in assigned for p in net.members) or len(set(net.members))!=len(net.members):raise ValueError('Port is missing or assigned to multiple nets')
            assigned.update(net.members)
            if not any(claims[c].predicate=='connection' for c in net.claim_ids):raise ValueError('Net topology requires a connection claim with provenance')
        for intent in self.design_intent:
            if intent.claim_id not in claims or claims[intent.claim_id].subject_id!=intent.id:raise ValueError('Intent claim missing')
            if any(i not in entities for i in intent.bound_entity_ids):raise ValueError('Intent entity binding missing')
        for item in self.unresolved:
            if any(i not in entities for i in item.subject_ids):raise ValueError('Unresolved subject missing')
        for lookup in self.knowledge:
            if lookup.component_id not in components:raise ValueError('Knowledge component missing')
        return self


class ClaimReview(Strict):
    claim_id: Key
    status: Literal['confirmed','corrected','rejected']
    corrected_value: Scalar = None
    corrected_unit: str = Field(default='',max_length=40)
    decision: str = Field(min_length=1,max_length=2000)

    @model_validator(mode='after')
    def meaningful_decision(self):
        if not self.decision.strip():raise ValueError('Engineer review needs a decision')
        return self


def validate_context(result: HydraulicRepresentation, inputs: TaskInput, *, provider_output=True):
    documents={d.id:d for d in inputs.documents}
    for evidence in result.evidence:
        if evidence.document_id:
            if evidence.document_id not in documents:raise ValueError('Unknown source document')
            document=documents[evidence.document_id]
            limit=1 if document.asset.media_type.startswith('image/') else document.page_count
            if evidence.page is None or limit and evidence.page>limit:raise ValueError('Source page is outside document')
        if evidence.requirement_span:
            start,end=evidence.requirement_span
            if end>len(inputs.engineering_requirements) or inputs.engineering_requirements[start:end]!=evidence.quote:raise ValueError('Requirement evidence does not match original instruction')
    if provider_output and (any(c.kind=='knowledge_base' for c in result.claims) or any(e.kind=='knowledge_base' for e in result.evidence) or result.knowledge):
        raise ValueError('Providers cannot assert authoritative knowledge resolution')
    return result
