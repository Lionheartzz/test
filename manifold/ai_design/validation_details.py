"""Safe Pydantic diagnostics: schema paths and fixed explanations, never inputs."""
import math
from typing import get_args
from pydantic_core import ErrorType
from .semantic import CircuitReading

ERROR_TYPES = set(get_args(ErrorType))
CUSTOM = {
    'Component-selection preference cannot establish an observed component fact': 'Keep component-selection preferences in requirements. They do not establish observed manufacturer, model, cavity or functional type facts; retain independent observation provenance.',
    'Unknown observation must have null value': 'Unknown observations must have a null value. Do not assert a value while marking it unknown.',
    'Clear observation needs a value': 'A clear observation requires a non-null value. If the source is unclear, preserve uncertainty instead of inventing a value.',
    'A value needs a source or explicit inference provenance': 'A non-null value needs schematic/user provenance or explicit AI-inference provenance; unknown provenance cannot support an asserted value.',
    'Labels must be unique within their component or external-port group': 'Labels must be unique within the component or external-port group; do not merge distinct hydraulic entities to resolve this.',
    'Net names must be nonempty text or null': 'A net name must be nonempty text or null. Do not invent a connection for an unknown net.',
}
EXPLANATIONS = {
    'missing': 'Required field is missing.',
    'extra_forbidden': 'Unexpected field is not allowed by the schema. Its name is redacted when it is not a known schema field.',
    'literal_error': 'Value must match one of the field’s schema literals exactly; refer to the supplied JSON schema.',
    'string_type': 'Expected a JSON string.', 'int_type': 'Expected a JSON integer.',
    'int_parsing': 'Value cannot be parsed as an integer.', 'int_from_float': 'Expected an integer without a fractional part.',
    'float_type': 'Expected a JSON number.', 'float_parsing': 'Value cannot be parsed as a number.',
    'bool_type': 'Expected a JSON boolean.', 'bool_parsing': 'Value cannot be parsed as a boolean.',
    'list_type': 'Expected a JSON array.', 'tuple_type': 'Expected a JSON array of the specified length.',
    'dict_type': 'Expected a JSON object.', 'model_type': 'Expected an object matching this schema.',
    'model_attributes_type': 'Expected an object matching this schema.',
    'finite_number': 'Number must be finite.', 'json_invalid': 'Response is not valid JSON; repair the JSON syntax.',
    'json_type': 'Expected JSON text.', 'string_unicode': 'String must contain valid Unicode.',
    'value_error': 'Observation or topology invariant failed. Review values, certainty, provenance and unique labels; do not invent engineering facts.',
}
LIMITS = {'greater_than':('gt','Value must be greater than'), 'greater_than_equal':('ge','Value must be at least'),
          'less_than':('lt','Value must be less than'), 'less_than_equal':('le','Value must be at most'),
          'too_short':('min_length','Collection must contain at least'), 'too_long':('max_length','Collection must contain at most'),
          'string_too_short':('min_length','String must contain at least'), 'string_too_long':('max_length','String must contain at most')}


def schema_fields():
    fields=set()
    def visit(node):
        if isinstance(node,dict):
            fields.update(node.get('properties',{}))
            for v in node.values():visit(v)
        elif isinstance(node,list):
            for v in node:visit(v)
    visit(CircuitReading.model_json_schema())
    return fields | {'str','int','float','bool'}  # Pydantic scalar-union branch labels.


def safe_validation_errors(exc):
    allowed=schema_fields()
    details=[]
    for error in exc.errors(include_input=False,include_url=False):
        path=[];redacted=False
        for part in error.get('loc',()):
            if type(part) is int and part>=0:path.append(part)
            elif isinstance(part,str) and part in allowed:path.append(part)
            else:path.append('[redacted-field]');redacted=True
        kind=error.get('type')
        kind=kind if kind in ERROR_TYPES else 'validation_error'
        context=error.get('ctx') or {}
        explanation=EXPLANATIONS.get(kind,'Value does not satisfy the supplied schema at this path.')
        if kind in LIMITS:
            key,prefix=LIMITS[kind];limit=context.get(key)
            if type(limit) in (int,float) and math.isfinite(limit):explanation=f'{prefix} {limit}.'
        if kind=='value_error':
            # Only exact messages authored in PMC may replace the fixed generic explanation.
            explanation=CUSTOM.get(str(context.get('error','')),explanation)
        details.append(dict(path=path,type=kind,explanation=explanation,path_redacted=redacted,
                            classification='semantic' if kind=='value_error' else 'schema',action='rejected'))
    return details
