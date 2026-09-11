"""Operator-selected wire controls, independent of hydraulic business logic."""


def reasoning_parameters(settings, operation):
    chosen = settings.operation_reasoning.get(operation, settings.reasoning)
    mode, effort = chosen.mode, chosen.effort
    body, warnings = {}, []
    requested = mode != 'provider_default' or effort != 'provider_default'
    if chosen.dialect == 'provider_default':
        if requested:
            warnings.append('reasoning_dialect_required')
        return chosen.model_dump(), body, warnings, 'not_sent' if requested else 'provider_default'
    if chosen.dialect == 'thinking':
        if mode != 'provider_default':
            body['thinking'] = {'type': mode}
        if effort != 'provider_default' and mode != 'disabled':
            body['reasoning_effort'] = effort
    else:
        if mode == 'disabled':
            body['reasoning_effort'] = 'none'
        elif effort != 'provider_default':
            body['reasoning_effort'] = effort
        elif mode == 'enabled':
            warnings.append('effort_required')
    if mode == 'disabled' and effort not in ('provider_default', 'none'):
        warnings.append('effort_ignored_when_disabled')
    if body:
        warnings.append('provider_may_ignore_controls')
    control = ('partially_requested' if len(warnings)>1 else 'requested_unverified') if body else ('not_sent' if requested else 'provider_default')
    return chosen.model_dump(), body, warnings, control
