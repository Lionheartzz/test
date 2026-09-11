"""Bounded provider evidence. No response text, reasoning text, URLs or credentials."""
from typing import Literal
from pydantic import Field
from ..schema import Strict
from .config import ReasoningSettings

Phase = Literal['document_render', 'provider_call', 'response_parse', 'structured_output_validation',
                'normalization', 'admission', 'knowledge_resolution', 'completed']
TOKENS = ('input_tokens', 'output_tokens', 'reasoning_tokens', 'cached_tokens', 'total_tokens')


class Usage(Strict):
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    reasoning_tokens: int | None = Field(default=None, ge=0, strict=True)
    cached_tokens: int | None = Field(default=None, ge=0, strict=True)
    total_tokens: int | None = Field(default=None, ge=0, strict=True)


class ValidationDetail(Strict):
    path: list[str | int]
    type: str
    explanation: str
    path_redacted: bool = False
    classification: Literal['schema','semantic']
    action: Literal['rejected','normalized'] = 'rejected'


class Attempt(Strict):
    index: int = Field(ge=1)
    phase: Phase = 'provider_call'
    status: Literal['running', 'completed', 'failed'] = 'running'
    error: str | None = Field(default=None, pattern=r'^[A-Z_]{1,80}$')
    latency_ms: float = Field(default=0, ge=0)
    http_status: int | None = Field(default=None, ge=100, le=599)
    rejected_parameter: Literal['max_tokens', 'max_completion_tokens', 'reasoning_effort', 'thinking',
                               'stream', 'stream_options', 'response_format', 'model', 'messages'] | None = None
    finish_reason: Literal['stop', 'length', 'content_filter', 'tool_calls', 'function_call', 'other'] | None = None
    usage: Usage = Field(default_factory=Usage)
    response_bytes: int = Field(default=0, ge=0)
    content_chars: int = Field(default=0, ge=0)
    reasoning_chars: int = Field(default=0, ge=0)
    usage_reported: bool = False
    usage_final: bool = False
    validation_error_count: int | None = Field(default=None, ge=0)
    validation_errors: list[ValidationDetail] = Field(default_factory=list)
    stream_completed: bool | None = None


class Diagnostics(Strict):
    version: int = 1
    operation: Literal['hydraulic_understanding', 'topology_reasoning', 'manifold_optimization'] = 'hydraulic_understanding'
    phase: Phase = 'document_render'
    request_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    configured_retries: int = Field(default=0, ge=0, le=1)
    attempts: list[Attempt] = Field(default_factory=list, max_length=2)
    reasoning: ReasoningSettings = Field(default_factory=ReasoningSettings)
    reasoning_control: Literal['provider_default', 'requested_unverified', 'partially_requested', 'not_sent'] = 'provider_default'
    control_warnings: list[Literal['reasoning_dialect_required', 'effort_required', 'effort_ignored_when_disabled',
                                 'provider_may_ignore_controls']] = Field(default_factory=list)
    max_tokens: int | None = Field(default=None, ge=1, strict=True)
    max_tokens_parameter: Literal['max_tokens', 'max_completion_tokens'] = 'max_tokens'
    stream: bool = False
    timeout_seconds: float = Field(default=120, gt=0)
    prompt_revision: Literal['circuit-reading-1-compact-v2'] = 'circuit-reading-1-compact-v2'
    prompt_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    schema_chars: int = Field(default=0, ge=0)
    text_chars: int = Field(default=0, ge=0)
    document_count: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)
    image_bytes: int = Field(default=0, ge=0)
    usage: Usage = Field(default_factory=Usage)
    reported_usage: Usage = Field(default_factory=Usage)


def normalize_usage(raw):
    if not isinstance(raw, dict):
        return Usage().model_dump()
    def at(*path):
        current = raw
        for key in path:
            current = current.get(key) if isinstance(current, dict) else None
        return current if isinstance(current, int) and not isinstance(current, bool) and current >= 0 else None
    def first(*paths):
        return next((n for path in paths if (n := at(*path)) is not None), None)
    return dict(input_tokens=first(('prompt_tokens',), ('input_tokens',)),
                output_tokens=first(('completion_tokens',), ('output_tokens',)),
                reasoning_tokens=first(('completion_tokens_details','reasoning_tokens'), ('output_tokens_details','reasoning_tokens'), ('reasoning_tokens',)),
                cached_tokens=first(('prompt_tokens_details','cached_tokens'), ('input_tokens_details','cached_tokens'), ('prompt_cache_hit_tokens',), ('cache_read_input_tokens',)),
                total_tokens=at('total_tokens'))


def aggregate(diag):
    attempts = diag['attempts']
    diag['request_count'] = len(attempts)
    diag['retry_count'] = max(0, len(attempts)-1)
    for field in TOKENS:
        reported = [a['usage'].get(field) for a in attempts if a['usage'].get(field) is not None]
        diag['reported_usage'][field] = sum(reported) if reported else None
        diag['usage'][field] = sum(reported) if attempts and len(reported) == len(attempts) and all(a['usage_final'] for a in attempts) else None
    return Diagnostics.model_validate(diag).model_dump()


FAILURE_HELP = {
    'PROVIDER_TIMEOUT': 'The configured provider deadline expired. Inspect reasoning settings and attempt usage; choose an appropriate deadline or enable streaming if supported. The provider may still bill work after the connection closes. Unreported usage is unavailable.',
    'PROVIDER_OUTPUT_TRUNCATED': 'The provider ended output with length before a usable JSON result. Review reported reasoning/completion tokens, the requested output budget and the model context limit. PMC did not reduce your token value or automatically retry this failure.',
    'PROVIDER_AUTH': 'The provider rejected authentication. Check the saved key and its access to this endpoint/model. No automatic retry.',
    'PROVIDER_RATE_LIMIT': 'The provider rate-limited this request. Wait for its quota or rate window before retrying. No automatic retry.',
    'PROVIDER_NETWORK': 'The provider connection failed. Check connectivity and endpoint availability. Delivery/billing may be uncertain; no automatic retry.',
    'PROVIDER_REQUEST_REJECTED': 'The provider rejected the request parameters (HTTP 4xx). Review the indicated parameter and model capabilities, including token budget, reasoning dialect, JSON mode and streaming. PMC does not clamp tokens or silently retry with different settings.',
    'PROVIDER_HTTP_ERROR': 'The provider returned an unsuccessful HTTP status. Check service availability and endpoint routing. No automatic retry.',
    'PROVIDER_MALFORMED_RESPONSE': 'The provider returned an incompatible response envelope or incomplete stream. Check Chat Completions compatibility and streaming support. No CAD was generated from this response.',
    'INVALID_STRUCTURED_OUTPUT': 'The response did not satisfy the semantic JSON contract. Review the attempt count, JSON mode and model structured-output capability. Only an explicitly enabled contract retry can issue another request.',
    'NORMALIZATION_FAILED': 'Parsed observations failed source/topology normalization. Check exact requirement quotes, page references and ambiguous connections; no invented replacement result was used.',
    'INVALID_PROVIDER_RESULT': 'The hydraulic result failed PMC admission or source validation. Review the source and contract compatibility; prior successful results remain available.',
    'UNSUPPORTED_MEDIA': 'The selected provider does not support this document format. Use a supported PDF/PNG/JPEG input or another configured adapter.',
    'DOCUMENT_LIMIT': 'The rendered document set exceeds the configured page budget. Adjust the page budget in settings; no pages were silently dropped.',
    'DOCUMENT_RENDER_FAILED': 'The source pages could not be rendered or verified before the provider call. Check PDF readability/password, page budget and local page cache. No provider request was sent.',
    'PROVIDER_RESPONSE_LIMIT': 'The provider response exceeded an applicable response limit. Review the adapter and provider response capabilities.',
    'PROVIDER_CONTENT_FILTER': 'The provider stopped or refused this response. Review its usage policy and the submitted source; no automatic retry.',
    'PROVIDER_FAILED': 'The provider operation failed without a more specific supported classification. Review the recorded failure stage and settings; inputs and previous results remain available.'
}


def failure_help(code):
    return FAILURE_HELP.get(code, FAILURE_HELP['PROVIDER_FAILED'])
