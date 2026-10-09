"""Discard unsupported optional identity at the model boundary, never invent facts."""
import json
from pydantic import ValidationError
from .semantic import CircuitReading
from .validation_details import safe_validation_errors

IDENTITY_FIELDS = ('manufacturer', 'model', 'cavity', 'mounting_interface')
MISSING_PROVENANCE = 'A value needs a source or explicit inference provenance'
UNKNOWN_WITH_VALUE = 'Unknown observation must have null value'


def recover_unknown_identity(text, error):
    paths = []
    errors = error.errors(include_input=False, include_url=False)
    for item in errors:
        loc = item.get('loc', ())
        if not (len(loc) == 3 and loc[0] == 'components' and type(loc[1]) is int
                and loc[2] in IDENTITY_FIELDS and item['type'] == 'value_error'
                and str((item.get('ctx') or {}).get('error', '')) in (MISSING_PROVENANCE, UNKNOWN_WITH_VALUE)):
            return None  # Critical or malformed content still rejects the whole attempt.
        paths.append(loc)
    if not paths:
        return None
    raw = json.loads(text)
    for (_, index, field), item in zip(paths, errors):
        observation = raw['components'][index][field]
        reason = str((item.get('ctx') or {}).get('error', ''))
        # Discard identity, but retain any explicit source for normal source/page/quote checks.
        raw['components'][index][field] = ({'source': observation.get('source', {})}
                                           if reason == UNKNOWN_WITH_VALUE else {})
    try:
        reading = CircuitReading.model_validate(raw)
    except ValidationError:
        return None
    details = safe_validation_errors(error)
    for detail, item in zip(details, errors):
        reason = str((item.get('ctx') or {}).get('error', ''))
        explanation = ('Product identity was marked unknown but contained a value; the value was discarded and identity remains unknown. '
                       'Confirm from source or engineer review; no product or library fact was inferred.' if reason == UNKNOWN_WITH_VALUE else
                       'Unsupported product identity was discarded and replaced with unknown. Confirm from source evidence or an explicit engineer correction; no product or library fact was inferred.')
        detail.update(action='normalized', explanation=explanation)
    return reading, details, [(index, field) for _, index, field in paths]


def usable_identity(claim):
    """A review decision may authorize identity; a model inference alone cannot."""
    review = claim.get('engineer_review') or {}
    return claim.get('status') == 'confirmed' and (
        claim.get('kind') == 'schematic' or review.get('status') in ('confirmed', 'corrected'))
