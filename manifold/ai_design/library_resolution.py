"""Read-only use of the existing catalogs. Model names never manufacture compatibility."""
import re
from .. import catalog, workflow, projects
from ..schema import CavityDefinition
from .service import digest
from .identity_admission import usable_identity


def norm(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def summary(key, definition):
    return dict(key=key, sha256=digest(definition.model_dump()), label=definition.label,
                manufacturer=definition.manufacturer, role=definition.usage_role,
                zones=[z.model_dump() for z in definition.zones], demo_only=definition.demo_only,
                geometry_status=definition.native.geometry_status if definition.native else definition.provenance,
                unit=definition.native.record.unit_system if definition.native else 'project',
                source=definition.source, compatible_cartridges=[c.model_dump() for c in definition.compatible_cartridges])


def saved_definitions(inputs):
    result = []
    for item in workflow.library_entries():
        if item['preferred'] and not item['deleted']:
            definition = CavityDefinition.model_validate(item['definition'])
            if not definition.native or definition.native.record.unit_system == inputs.project_context:
                result.append(('pmc:' + item['sha256'], definition))
    if inputs.linked_project_id:
        for raw in projects.read(inputs.linked_project_id)['design']['library']:
            definition = CavityDefinition.model_validate(raw)
            if not definition.native or definition.native.record.unit_system == inputs.project_context:
                result.append(('project:' + definition.id, definition))
    return result


def search(inputs, query='', role='cartridge-cavity'):
    local = [(key, d) for key, d in saved_definitions(inputs) if d.usage_role == role and
             all(token in (d.label + ' ' + d.manufacturer + ' ' + ' '.join(c.model for c in d.compatible_cartridges)).lower()
                 for token in query.lower().split())]
    result = [summary(key, d) for key, d in local][:20]
    rows = catalog.search(q=query, unit=inputs.project_context,
                          kind='cavity' if role == 'cartridge-cavity' else 'port_definition', limit=20)['items']
    for row in rows:
        try:
            definition = catalog.definition(row['id'])
            result.append(summary('native:' + row['id'], definition))
        except ValueError:
            continue
    return result


def load(inputs, key, sha=None):
    if key.startswith('native:'):
        native_id = key[7:]
        if not native_id.startswith(inputs.project_context + ':'):
            raise ValueError('Definition is outside this analysis native unit context')
        definition = catalog.definition(native_id)
    else:
        definition = next((d for k, d in saved_definitions(inputs) if k == key), None)
        if definition is None:
            raise ValueError('Selected library definition is no longer available')
    if sha and digest(definition.model_dump()) != sha:
        raise ValueError('Selected definition changed. Search and confirm it again.')
    return definition


def value(result, subject, predicate):
    return next((c['value'] for c in result['claims'] if c['subject_id'] == subject and c['predicate'] == predicate), None)


def candidates(inputs, result, component):
    model = identity_value(result, component['id'], 'model')
    maker = identity_value(result, component['id'], 'manufacturer')
    cavity = identity_value(result, component['id'], 'cavity')
    found = []
    for key, d in saved_definitions(inputs):
        matches = [c for c in d.compatible_cartridges if c.status != 'unconfirmed' and model and
                   norm(c.model) == norm(model) and (not maker or norm(maker) in norm(c.manufacturer))]
        if matches and d.usage_role == 'cartridge-cavity':
            found.append(dict(**summary(key, d), reason='Existing documented/engineer-confirmed model relationship'))
    # Only confirmed schematic identity or explicit engineer review may match native names.
    if cavity:
        for row in search(inputs, str(cavity)):
            if norm(row['label']) == norm(cavity) and (not maker or norm(maker) in norm(row['manufacturer'])):
                found.append(dict(**row, reason='Exact cavity designation explicitly present in source; compatibility still needs review'))
    return list({row['key']: row for row in found}.values())


def identity_value(result, subject, predicate):
    return next((c['value'] for c in result['claims'] if c['subject_id'] == subject
                 and c['predicate'] == predicate and usable_identity(c)), None)


def resolution_status(inputs, result, component, choices):
    """Explain each trusted-resolution boundary without inventing product associations."""
    model = identity_value(result, component['id'], 'model')
    cavity = identity_value(result, component['id'], 'cavity')
    usable = [row for row in choices if row['geometry_status'] != 'draft-projection' and not row['demo_only']]
    if not choices:
        if not model and not cavity:
            code = 'identity_needs_review'
            message = 'No confirmed schematic or engineer-reviewed model/cavity identity is available.'
            action = 'Review product identity, or choose an existing cavity with an explicit engineering decision.'
        else:
            code = 'relationship_missing'
            message = f'No trusted model-to-cavity relationship or exact source cavity match was found in the current {inputs.project_context} Library.'
            action = 'Provide a documented cartridge-to-cavity relationship, or select a verified existing cavity; then map each source hydraulic window. A model name alone does not identify machining geometry.'
    elif not usable:
        code = 'geometry_needs_review'
        message = 'Matching definitions exist, but their geometry is demonstration-only or still requires mapping review.'
        action = 'Review the existing definition and machining interpretation before selecting it; automatic generation cannot approve it.'
    elif len(usable) > 1:
        code = 'ambiguous_cavities'
        message = f'{len(usable)} usable cavity candidates match; the relationship is not unique.'
        action = 'Choose the appropriate candidate and confirm its hydraulic window mapping.'
    elif matching_zones(result, component, usable[0]['zones']) is None:
        code = 'window_mapping_required'
        message = 'One usable cavity matches, but schematic port labels do not uniquely identify all Library windows.'
        action = 'Use the candidate below and map each window from documented port numbering. Inlet/outlet roles alone do not establish numbered windows.'
    else:
        code = 'resolved'
        message = 'One trusted cavity and an exact, complete port-label mapping were found.'
        action = 'Ready for draft generation; existing engineer review and exact validation still apply.'
    return dict(code=code, message=message, action=action, candidate_count=len(choices), usable_count=len(usable))


def matching_zones(result, component, zones):
    ports = {p['id']: value(result, p['id'], 'label') for p in result['ports'] if p['component_id'] == component['id']}
    mapping = {}
    for zone in zones:
        zone_label = re.sub(r'^port', '', norm(zone['id']))
        matches = [key for key, label in ports.items() if re.sub(r'^port', '', norm(label)) == zone_label]
        if len(matches) != 1:
            return None
        mapping[zone['id']] = matches[0]
    return mapping if set(mapping.values()) == set(component['port_ids']) else None
