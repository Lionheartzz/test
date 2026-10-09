"""Chat Completions transport with explicit controls and bounded diagnostic records."""
import asyncio
import base64
import codecs
import hashlib
import json
import time
import httpx
from pydantic import ValidationError
from .providers import ProviderResponse, ProviderFailure
from .semantic import CircuitReading, INSTRUCTIONS, normalize, prompt_schema
from .documents import render
from .diagnostics import Diagnostics, Attempt, NormalizationDetail, NormalizationFailure, TOKENS, aggregate, normalize_usage
from .transport_controls import reasoning_parameters
from .validation_details import safe_validation_errors
from .identity_admission import recover_unknown_identity
from .observation_adapter import adapt_observations
from .identity_reading import IdentityReading, INSTRUCTIONS as IDENTITY_INSTRUCTIONS, validate_reading
from .identity_lookup import lookup as lookup_identities


class MultimodalProvider:
    id = 'configured-multimodal'
    is_mock = False
    supported_media = ('image/png', 'image/jpeg', 'application/pdf')

    def __init__(self, settings):
        self.settings, self.model = settings, settings.model

    def analyze(self, request):
        settings = self.settings
        reasoning, controls, warnings, control = reasoning_parameters(settings, request.operation)
        diag = Diagnostics(operation=request.operation, reasoning=reasoning, reasoning_control=control,
            control_warnings=warnings, max_tokens=settings.max_tokens, max_tokens_parameter=settings.max_tokens_parameter,
            timeout_seconds=settings.timeout_seconds, configured_retries=settings.contract_retries,
            stream=settings.stream, document_count=len(request.documents)).model_dump()
        try:
            content = [dict(type='text', text='Original engineering requirements (verbatim JSON string; '
                            'the only source for requirements[].quote):\n' +
                            json.dumps(request.inputs.engineering_requirements, ensure_ascii=False)),
                       dict(type='text', text='Project metadata, not a user requirement: engineering unit context = ' +
                            request.inputs.project_context)]
            pages_by_doc, manifest = {}, []
            if request.engineering_facts_context:
                content.append(dict(type='text',text='PMC engineering reference facts (separate from schematic evidence):\n'+
                    json.dumps(request.engineering_facts_context,ensure_ascii=False)))
            for number, document in enumerate(request.documents, 1):
                pages = render(document, max_pages=settings.max_pages, max_side=settings.image_max_side)
                if len(manifest) + len(pages) > settings.max_pages:
                    raise ProviderFailure('DOCUMENT_LIMIT')
                pages_by_doc[document.document_id] = len(pages)
                for page in pages:
                    content.append(dict(type='text', text=f'Document {number}, original page {page["page"]}.'))
                    content.append(dict(type='image_url', image_url=dict(url='data:image/png;base64,' +
                                   base64.b64encode(page['data']).decode('ascii'), detail='high')))
                    diag['image_bytes'] += len(page['data'])
                    manifest.append(dict(document_id=document.document_id, page=page['page'], sha256=page['sha256'],
                                         width=page['width'], height=page['height']))
            schema = json.dumps(prompt_schema(), separators=(',', ':'))
            system = INSTRUCTIONS + '\nJSON schema:\n' + schema
            messages = [dict(role='system', content=system), dict(role='user', content=content)]
            diag.update(image_count=len(manifest), schema_chars=len(schema),
                        text_chars=len(system)+sum(len(p['text']) for p in content if p['type']=='text'),
                        prompt_sha256=hashlib.sha256(system.encode()).hexdigest(), phase='provider_call')
            result, identity_reading = asyncio.run(self._analyze(request, messages, pages_by_doc, controls, diag))
            metadata = dict(transport='chat-completions', schema='circuit-reading-1', requests=diag['request_count'],
                            document_pages=manifest, page_counts=pages_by_doc, image_max_side=settings.image_max_side,
                            endpoint_sha256=hashlib.sha256(settings.base_url.encode()).hexdigest(),
                            pipeline='source-captions/sqlite-reference/hydraulic-analysis',
                            identity_reading=identity_reading.model_dump())
            return ProviderResponse(result.model_dump(), metadata=metadata, diagnostics=diag,
                                    **{field: diag['usage'][field] for field in TOKENS})
        except ProviderFailure as exc:
            exc.diagnostics = aggregate(diag)
            raise
        except (ValueError, OSError):
            raise ProviderFailure('DOCUMENT_RENDER_FAILED' if diag['phase']=='document_render' else 'INVALID_PROVIDER_RESULT',
                                  diagnostics=aggregate(diag)) from None

    async def _analyze(self, request, messages, pages_by_doc, controls, diag):
        settings=self.settings
        # One deadline for the complete planned pipeline and any opted-in retries.
        deadline = time.monotonic() + settings.timeout_seconds
        caption_content=[part for part in messages[1]['content'] if part['type']=='image_url'
            or part['type']=='text' and part['text'].startswith('Document ')]
        caption_messages=[dict(role='system',content=IDENTITY_INSTRUCTIONS+'\nJSON schema:\n'+
                              json.dumps(prompt_schema(IdentityReading),separators=(',',':'))),
                          dict(role='user',content=caption_content)]
        inventory=await self._stage(request,caption_messages,pages_by_doc,controls,diag,deadline,
                                    'identity_reading')
        diag['phase']='knowledge_resolution'
        lookup_started=time.monotonic()
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ProviderFailure('PROVIDER_TIMEOUT')
        try:
            async with asyncio.timeout(remaining):
                reference=await asyncio.to_thread(lookup_identities,inventory,deadline=deadline)
        except TimeoutError:
            raise ProviderFailure('PROVIDER_TIMEOUT') from None
        context=json.dumps(reference,ensure_ascii=False,separators=(',',':'))
        diag.update(identity_lookup_tables=reference['searched_tables'],identity_caption_count=len(inventory.captions),
                    identity_lookup_matches=reference['matched_records'],
                    identity_lookup_ms=round((time.monotonic()-lookup_started)*1000,2),
                    identity_reference_sha256=hashlib.sha256(context.encode()).hexdigest())
        final_messages=[*messages,dict(role='user',content='Source identity reading and current SQLite identity-field '
            'reference matches, numbered by caption. Compare them before completing CircuitReading. Preserve '
            'both product models and machining interfaces, and attach identity_captions references. Similarity '
            'does not justify correcting source text or claiming geometry/compatibility.\n'+context)]
        try:
            result=await self._stage(request,final_messages,pages_by_doc,controls,diag,deadline,
                                     'hydraulic_analysis',inventory)
        except ProviderFailure as exc:
            exc.identity_reading=inventory.model_dump()
            raise
        return result,inventory

    async def _stage(self, request, messages, pages_by_doc, controls, diag, deadline, stage, inventory=None):
        settings=self.settings
        retry_budget=max(0,settings.contract_retries-diag['retry_count'])
        for index in range(retry_budget+1):
            if time.monotonic() >= deadline:
                raise ProviderFailure('PROVIDER_TIMEOUT')
            attempt = Attempt(index=len(diag['attempts'])+1,request_stage=stage,contract_attempt=index+1).model_dump()
            attempt['text_chars']=sum(len(message['content']) if isinstance(message['content'],str) else
                sum(len(part['text']) for part in message['content'] if part['type']=='text') for message in messages)
            attempt['image_count']=sum(part['type']=='image_url' for message in messages
                if isinstance(message['content'],list) for part in message['content'])
            attempt['prompt_sha256']=hashlib.sha256(messages[0]['content'].encode()).hexdigest()
            diag['attempts'].append(attempt)
            diag['text_chars']=sum(row.get('text_chars') or 0 for row in diag['attempts'])
            started = time.monotonic()
            body = dict(model=settings.model, messages=messages, stream=settings.stream, **controls)
            if settings.max_tokens is not None:
                body[settings.max_tokens_parameter] = settings.max_tokens
            if settings.json_mode:
                body['response_format'] = {'type': 'json_object'}
            if settings.stream and settings.stream_usage:
                body['stream_options'] = {'include_usage': True}
            try:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise ProviderFailure('PROVIDER_TIMEOUT')
                async with asyncio.timeout(remaining):
                    text = await self._request(body, attempt, remaining)
                if attempt['finish_reason'] == 'length':
                    raise ProviderFailure('PROVIDER_OUTPUT_TRUNCATED')
                if attempt['finish_reason'] == 'content_filter':
                    raise ProviderFailure('PROVIDER_CONTENT_FILTER')
                attempt['phase'] = 'structured_output_validation'
                identity_omissions = []
                if text.strip().startswith('```'):
                    lines = text.strip().splitlines()
                    if lines[-1].strip() == '```':
                        text = '\n'.join(lines[1:-1])
                if stage=='identity_reading':
                    try:reading=IdentityReading.model_validate_json(text)
                    except ValidationError as exc:
                        attempt['validation_error_count']=exc.error_count()
                        attempt['validation_errors']=safe_validation_errors(exc)
                        raise ProviderFailure('INVALID_STRUCTURED_OUTPUT') from None
                else:
                    raw, shape_details = adapt_observations(text)
                    if shape_details:
                        attempt['validation_errors'] = shape_details
                        attempt['validation_error_count'] = len(shape_details)
                    try:
                        reading = CircuitReading.model_validate(raw) if shape_details else CircuitReading.model_validate_json(text)
                    except ValidationError as exc:
                        attempt['validation_error_count'] = len(shape_details) + exc.error_count()
                        attempt['validation_errors'] = [*shape_details, *safe_validation_errors(exc)]
                        recovered = recover_unknown_identity(json.dumps(raw) if shape_details else text, exc)
                        if recovered is None:
                            raise ProviderFailure('INVALID_STRUCTURED_OUTPUT') from None
                        reading, identity_details, identity_omissions = recovered
                        attempt['validation_errors'] = [*shape_details, *identity_details]
                attempt['phase'] = 'normalization'
                try:
                    result = (validate_reading(reading,request.inputs,pages_by_doc) if stage=='identity_reading' else
                        normalize(reading, request.inputs, pages_by_doc, identity_omissions,
                                  requirement_omissions=attempt['normalization_omissions'],identity_reading=inventory))
                except (ValueError, TypeError, KeyError) as exc:
                    detail = exc.detail if isinstance(exc, NormalizationFailure) else NormalizationDetail(category='other_normalization_error')
                    attempt['normalization_error'] = detail.model_dump()
                    raise ProviderFailure('NORMALIZATION_FAILED') from None
                if time.monotonic() > deadline:
                    raise ProviderFailure('PROVIDER_TIMEOUT')
                attempt.update(status='completed', phase='completed')
                diag['phase'] = 'completed'
                return result
            except (TimeoutError, httpx.TimeoutException):
                attempt.update(status='failed', error='PROVIDER_TIMEOUT')
                raise ProviderFailure('PROVIDER_TIMEOUT') from None
            except httpx.HTTPError:
                attempt.update(status='failed', error='PROVIDER_NETWORK')
                raise ProviderFailure('PROVIDER_NETWORK') from None
            except ProviderFailure as exc:
                attempt.update(status='failed', error=exc.code)
                if index == retry_budget or exc.code not in ('INVALID_STRUCTURED_OUTPUT','NORMALIZATION_FAILED'):
                    raise
                # Opt-in fresh contract attempt. Never replay the response or reasoning text.
                errors = json.dumps(dict(validation_errors=attempt['validation_errors'],
                    normalization_error=attempt['normalization_error']),ensure_ascii=False,separators=(',',':'))
                messages = [*messages, dict(role='user', content='The preceding request failed semantic contract validation. '
                    'Return one schema-valid JSON object with exact original requirement quotes, valid source pages '
                    'and null for unknown observations. Do not include extra properties. '
                    'Correct these exact sanitized validation errors; paths are zero-based JSON field/index arrays. '
                    'Do not change or invent hydraulic facts merely to satisfy the schema. Errors: '+errors)]
            finally:
                attempt['latency_ms'] = round((time.monotonic()-started)*1000, 2)
                diag['phase'] = attempt['phase']
                diag.update(aggregate(diag))

    async def _request(self, body, attempt, remaining):
        headers = {'Content-Type': 'application/json'}
        key = self.settings.api_key.get_secret_value()
        if key:
            headers['Authorization'] = 'Bearer '+key
        async with httpx.AsyncClient(timeout=httpx.Timeout(remaining, connect=min(15, remaining)),
                                     follow_redirects=False, trust_env=False) as client:
            async with client.stream('POST', self.settings.base_url+'/chat/completions', headers=headers, json=body) as response:
                attempt['http_status'] = response.status_code
                if response.status_code != 200:
                    # Read only enough to classify a known parameter. Never retain error prose.
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk[:max(0,65536-len(raw))])
                        if len(raw) >= 65536:
                            break
                    attempt['response_bytes'] = len(raw)
                    try:
                        envelope = json.loads(raw)
                        self._usage(envelope, attempt, final=True)
                        error = envelope.get('error', {})
                        if isinstance(error, dict):
                            for name in ('max_completion_tokens','max_tokens','reasoning_effort','thinking','stream_options','stream','response_format','model','messages'):
                                if error.get('param') == name or name in str(error.get('message','')).lower():
                                    attempt['rejected_parameter'] = name
                                    break
                    except (ValueError, AttributeError, TypeError):
                        pass
                    code = {401:'PROVIDER_AUTH',403:'PROVIDER_AUTH',429:'PROVIDER_RATE_LIMIT'}.get(response.status_code)
                    raise ProviderFailure(code or ('PROVIDER_REQUEST_REJECTED' if 400 <= response.status_code < 500 else 'PROVIDER_HTTP_ERROR'))
                if self.settings.stream:
                    return await self._stream(response, attempt)
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    attempt['response_bytes'] += len(chunk)
                    raw.extend(chunk)
                attempt['phase'] = 'response_parse'
                try:
                    envelope = json.loads(raw)
                    self._usage(envelope, attempt, final=True)
                    choice = envelope['choices'][0]
                    self._finish(choice, attempt)
                    message = choice['message']
                    reasoning = message.get('reasoning_content', message.get('reasoning'))
                    if isinstance(reasoning, str):
                        attempt['reasoning_chars'] = len(reasoning)
                    text = message.get('content')
                    if text is None and attempt['finish_reason'] in ('length','content_filter'):
                        text = ''
                    if not isinstance(text, str):
                        raise ValueError()
                    attempt['content_chars'] = len(text)
                    return text
                except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                    raise ProviderFailure('PROVIDER_MALFORMED_RESPONSE') from None

    @staticmethod
    def _usage(envelope, attempt, final=False):
        usage = envelope.get('usage')
        if isinstance(usage, dict):
            normalized = normalize_usage(usage)
            # SSE usage snapshots are cumulative for this attempt; never sum chunks.
            attempt['usage'].update({k:v for k,v in normalized.items() if v is not None})
            attempt['usage_reported'] = True
            attempt['usage_final'] = attempt['usage_final'] or final

    @staticmethod
    def _finish(choice, attempt):
        finish = choice.get('finish_reason')
        if finish is not None:
            attempt['finish_reason'] = finish if finish in ('stop','length','content_filter','tool_calls','function_call') else 'other'

    async def _stream(self, response, attempt):
        parts, event = [], []
        attempt['stream_completed'] = False

        def consume():
            data = '\n'.join(event)
            event.clear()
            if data == '[DONE]':
                attempt['stream_completed'] = True
                return True
            try:
                envelope = json.loads(data)
                choices = envelope.get('choices')
                if not isinstance(choices, list):
                    raise ValueError()
                self._usage(envelope, attempt, final=not choices or any(isinstance(c,dict) and c.get('finish_reason') is not None for c in choices))
                for choice in choices:
                    if choice.get('index',0) != 0:
                        continue
                    self._finish(choice, attempt)
                    delta = choice.get('delta', {})
                    text = delta.get('content')
                    reasoning = delta.get('reasoning_content', delta.get('reasoning'))
                    if isinstance(reasoning, str):
                        attempt['reasoning_chars'] += len(reasoning)
                    if text is not None:
                        if not isinstance(text, str):
                            raise ValueError()
                        parts.append(text)
                        attempt['content_chars'] += len(text)
            except (ValueError, TypeError, KeyError, AttributeError):
                attempt['phase'] = 'response_parse'
                raise ProviderFailure('PROVIDER_MALFORMED_RESPONSE') from None
            return False

        async def lines():
            decoder = codecs.getincrementaldecoder('utf-8')()
            pending = ''
            async for chunk in response.aiter_bytes():
                attempt['response_bytes'] += len(chunk)
                pending += decoder.decode(chunk)
                while '\n' in pending:
                    line, pending = pending.split('\n',1)
                    yield line.rstrip('\r')
            pending += decoder.decode(b'',final=True)
            if pending:
                yield pending.rstrip('\r')
        try:
            async for line in lines():
                if line.startswith('data:'):
                    event.append(line[5:].lstrip(' '))
                elif not line and event and consume():
                    break
        except UnicodeError:
            attempt['phase'] = 'response_parse'
            raise ProviderFailure('PROVIDER_MALFORMED_RESPONSE') from None
        if event:
            consume()
        attempt['phase'] = 'response_parse'
        # [DONE] proves transport completion independently of optional finish metadata.
        # Usage alone cannot distinguish a final report from a cumulative snapshot.
        if not attempt['stream_completed']:
            raise ProviderFailure('PROVIDER_MALFORMED_RESPONSE')
        return ''.join(parts)
