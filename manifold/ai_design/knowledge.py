"""Read-only future Knowledge Base boundary. No library import, copy or mutation."""
from typing import Protocol
import hashlib
from .models import KnowledgeLookup, HydraulicRepresentation, Unresolved


class KnowledgeResolver(Protocol):
    def resolve(self, queries: list[KnowledgeLookup]) -> list[KnowledgeLookup]: ...


class UnavailableKnowledgeResolver:
    def resolve(self,queries):
        return [q.model_copy(update=dict(status='unresolved',candidates=[],message='Knowledge Base resolver is not connected. No cavity or rating inferred.')) for q in queries]


def resolve_knowledge(result: HydraulicRepresentation, resolver: KnowledgeResolver):
    queries=[]
    claims={c.id:c for c in result.claims}
    for component in result.components:
        values={claims[c].predicate:claims[c].value for c in component.claim_ids}
        queries.append(KnowledgeLookup(id='KB_'+hashlib.sha256(component.id.encode()).hexdigest()[:24],component_id=component.id,
            manufacturer=str(values.get('manufacturer') or ''),model=str(values.get('model') or '')))
    resolved=resolver.resolve(queries)
    if {q.id for q in resolved}!={q.id for q in queries}:raise ValueError('Knowledge resolver query identity mismatch')
    result=result.model_copy(deep=True);result.knowledge=resolved
    for lookup in resolved:
        if lookup.status!='resolved':result.unresolved.append(Unresolved(id='UNRESOLVED_'+lookup.id,subject_ids=[lookup.component_id],reason='knowledge_unavailable',description=lookup.message))
    return HydraulicRepresentation.model_validate(result.model_dump())
