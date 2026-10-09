"""Read-only runtime Knowledge Base boundary. No library import, copy or mutation."""
from typing import Protocol
import hashlib
from .models import KnowledgeLookup, HydraulicRepresentation, Unresolved
from .identity_admission import usable_identity


class KnowledgeResolver(Protocol):
    def resolve(self, queries: list[KnowledgeLookup]) -> list[KnowledgeLookup]: ...


class UnavailableKnowledgeResolver:
    def resolve(self,queries):
        return [q.model_copy(update=dict(status='unresolved',candidates=[],message='Knowledge Base resolver is not connected. No cavity or rating inferred.')) for q in queries]


class SQLiteKnowledgeResolver:
    """Exact admitted identity lookup; similarity context never comes through here."""
    def resolve(self,queries):
        from .library_resolution import component_identity
        from .models import KnowledgeReference
        from ..engineering_db import database_path,get_definition
        from .service import digest
        revision=str(database_path().stat().st_mtime_ns)
        results=[]
        for query in queries:
            values={name:getattr(query,name) for name in ('model','manufacturer','cavity','mounting_interface')}
            component=dict(id=query.component_id,facts=values,identity_valid={name:bool(value) for name,value in values.items()})
            identity=component_identity(dict(components=[component]),component)
            references=[]
            if identity['code']=='resolved':
                if identity.get('interface_only'):
                    references=[KnowledgeReference(resolver='sqlite-engineering-interface',record_id=key,
                        revision=revision,sha256=digest(get_definition(key).model_dump())) for key in identity['interface_ids']]
                else:
                    references=[KnowledgeReference(resolver='sqlite-cartridge',record_id=row['id'],revision=revision,
                        sha256=digest(row)) for row in identity['candidates']]
                status='resolved' if len(references)==1 else 'ambiguous'
                message='Exact runtime identity found; compatibility, physical geometry and port mapping are checked separately.' if status=='resolved' else 'Identity found with multiple physical variants; choose the required engineering definition.'
            else:
                status='ambiguous' if identity['code']=='cartridge_identity_ambiguous' else 'unresolved'
                message='Observed product or interface identity needs review against the runtime library; no identity was substituted.'
            results.append(query.model_copy(update=dict(status=status,candidates=references[:20],message=message)))
        return results


def resolve_knowledge(result: HydraulicRepresentation, resolver: KnowledgeResolver):
    queries=[]
    claims={c.id:c for c in result.claims}
    for component in result.components:
        values={claims[c].predicate:claims[c].value for c in component.claim_ids
                if usable_identity(claims[c].model_dump())}
        queries.append(KnowledgeLookup(id='KB_'+hashlib.sha256(component.id.encode()).hexdigest()[:24],component_id=component.id,
            manufacturer=str(values.get('manufacturer') or ''),model=str(values.get('model') or ''),
            cavity=str(values.get('cavity') or ''),mounting_interface=str(values.get('mounting_interface') or '')))
    resolved=resolver.resolve(queries)
    if {q.id for q in resolved}!={q.id for q in queries}:raise ValueError('Knowledge resolver query identity mismatch')
    result=result.model_copy(deep=True);result.knowledge=resolved
    for lookup in resolved:
        if lookup.status!='resolved':result.unresolved.append(Unresolved(id='UNRESOLVED_'+lookup.id,subject_ids=[lookup.component_id],reason='ambiguous' if lookup.status=='ambiguous' else 'knowledge_unavailable',description=lookup.message))
    return HydraulicRepresentation.model_validate(result.model_dump())
