"""Discard unsupported optional identity at the model boundary, never invent facts."""
import json
from pydantic import ValidationError
from .semantic import CircuitReading
from .validation_details import safe_validation_errors

IDENTITY_FIELDS = ('manufacturer', 'model', 'cavity')
MISSING_PROVENANCE = 'A value needs a source or explicit inference provenance'


def recover_unknown_identity(text, error):
    paths = []
    for item in error.errors(include_input=False, include_url=False):
        loc = item.get('loc', ())
        if not (len(loc) == 3 and loc[0] == 'components' and type(loc[1]) is int
                and loc[2] in IDENTITY_FIELDS and item['type'] == 'value_error'
                and str((item.get('ctx') or {}).get('error', '')) == MISSING_PROVENANCE):
            return None  # Critical or malformed content still rejects the whole attempt.
        paths.append(loc)
    if not paths:
        return None
    raw = json.loads(text)
    for _, index, field in paths:
        raw['components'][index][field] = {}  # Unknown/null; do not retain unsupported values.
    try:
        reading = CircuitReading.model_validate(raw)
    except ValidationError:
        return None
    details = safe_validation_errors(error)
    for detail in details:
        detail.update(action='normalized', explanation='Unsupported product identity was discarded and replaced with unknown. Confirm from source evidence or an explicit engineer correction; no product or library fact was inferred.')
    return reading, details, [(index, field) for _, index, field in paths]


def usable_identity(claim):
    """A review decision may authorize identity; a model inference alone cannot."""
    review = claim.get('engineer_review') or {}
    return claim.get('status') == 'confirmed' and (
        claim.get('kind') == 'schematic' or review.get('status') in ('confirmed', 'corrected'))
