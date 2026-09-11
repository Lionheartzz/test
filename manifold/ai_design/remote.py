"""Chat-completions multimodal adapter; the hydraulic contract is transport independent."""
import base64
import hashlib
import json
import time
import httpx
from pydantic import ValidationError
from .providers import ProviderResponse, ProviderFailure
from .semantic import CircuitReading, INSTRUCTIONS, normalize
from .documents import render


class MultimodalProvider:
    id = 'configured-multimodal'
    is_mock = False
    supported_media = ('image/png', 'image/jpeg', 'application/pdf')

    def __init__(self, settings):
        self.settings = settings
        self.model = settings.model

    def analyze(self, request):
        settings = self.settings
        content = [dict(type='text', text='Original engineering requirements (verbatim):\n' +
                        request.inputs.engineering_requirements + '\nEngineering unit context: ' + request.inputs.project_context)]
        page_counts = {}
        page_manifest = []
        total = 0
        for number, document in enumerate(request.documents, 1):
            pages = render(document, max_pages=settings.max_pages, max_side=settings.image_max_side)
            total += len(pages)
            if total > settings.max_pages:
                raise ProviderFailure('DOCUMENT_LIMIT')
            page_counts[document.document_id] = len(pages)
            for page in pages:
                content.append(dict(type='text', text=f'Document {number}, original page {page["page"]}.'))
                content.append(dict(type='image_url', image_url=dict(url='data:image/png;base64,' +
                               base64.b64encode(page['data']).decode('ascii'), detail='high')))
                page_manifest.append(dict(document_id=document.document_id, page=page['page'],
                                          sha256=page['sha256'], width=page['width'], height=page['height']))
        messages = [dict(role='system', content=INSTRUCTIONS + '\nJSON schema:\n' +
                         json.dumps(CircuitReading.model_json_schema(), separators=(',', ':'))),
                    dict(role='user', content=content)]
        endpoint = settings.base_url + '/chat/completions'
        headers = {'Content-Type': 'application/json'}
        key = settings.api_key.get_secret_value()
        if key:
            headers['Authorization'] = 'Bearer ' + key
        deadline = time.monotonic() + settings.timeout_seconds
        total_input = total_output = 0
        usage_known = True
        for attempt in range(2):
            body = dict(model=settings.model, messages=messages, max_tokens=settings.max_tokens, stream=False)
            if settings.json_mode:
                body['response_format'] = {'type': 'json_object'}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderFailure('PROVIDER_TIMEOUT')
            try:
                # No redirects, implicit environment proxies, SDK telemetry or raw-body logging.
                with httpx.Client(timeout=httpx.Timeout(remaining, connect=min(15, remaining)),
                                  follow_redirects=False, trust_env=False) as client:
                    with client.stream('POST', endpoint, headers=headers, json=body) as response:
                        if response.status_code in (401, 403):
                            raise ProviderFailure('PROVIDER_AUTH')
                        if response.status_code == 429:
                            raise ProviderFailure('PROVIDER_RATE_LIMIT')
                        if response.status_code != 200:
                            raise ProviderFailure('PROVIDER_HTTP_ERROR')
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 2_000_000:
                                raise ProviderFailure('PROVIDER_RESPONSE_LIMIT')
                            if time.monotonic() > deadline:
                                raise ProviderFailure('PROVIDER_TIMEOUT')
            except httpx.TimeoutException:
                raise ProviderFailure('PROVIDER_TIMEOUT') from None
            except httpx.HTTPError:
                raise ProviderFailure('PROVIDER_NETWORK') from None
            try:
                envelope = json.loads(raw)
                raw.clear()
                choice = envelope['choices'][0]
                if choice.get('finish_reason') == 'length':
                    raise ProviderFailure('PROVIDER_OUTPUT_TRUNCATED')
                text = choice['message']['content']
                if not isinstance(text, str):
                    raise ValueError('Text JSON result required')
                if text.strip().startswith('```'):
                    lines = text.strip().splitlines()
                    if lines[-1].strip() == '```':
                        text = '\n'.join(lines[1:-1])
                usage = envelope.get('usage') or {}
                for field in ('prompt_tokens', 'completion_tokens'):
                    count = usage.get(field)
                    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                        usage_known = False
                if usage_known:
                    total_input += usage['prompt_tokens']
                    total_output += usage['completion_tokens']
                reading = CircuitReading.model_validate_json(text)
                representation = normalize(reading, request.inputs, page_counts)
                return ProviderResponse(representation.model_dump(),
                    input_tokens=total_input if usage_known else None, output_tokens=total_output if usage_known else None,
                    metadata=dict(transport='chat-completions', schema='circuit-reading-1', requests=attempt+1,
                                  document_pages=page_manifest, page_counts=page_counts,image_max_side=settings.image_max_side,
                                  endpoint_sha256=hashlib.sha256(settings.base_url.encode()).hexdigest()))
            except ProviderFailure:
                raise
            except (ValueError, TypeError, KeyError, IndexError, ValidationError):
                if attempt:
                    raise ProviderFailure('INVALID_PROVIDER_RESULT') from None
                # One bounded contract retry, no fabricated fallback and no retry for HTTP/network errors.
                messages.append(dict(role='user', content='The previous response failed contract validation. '
                    'Return valid JSON matching the schema, exact original requirement quotes, valid page references, '
                    'and null for unknown values. Do not add bookkeeping IDs or properties outside the schema.'))
        raise ProviderFailure('INVALID_PROVIDER_RESULT')
