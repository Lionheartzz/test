"""Provider-neutral completion compatibility; all requests use a local fixture."""
import json
import httpx
import pytest
from test_provider_diagnostics import client, adapter, transport, request_for, reading, Stream, event
from manifold.ai_design.providers import ProviderFailure

USAGE = {'prompt_tokens': 2520, 'completion_tokens': 1910, 'total_tokens': 4430,
         'completion_tokens_details': {'reasoning_tokens': 0}}


def run_stream(client, monkeypatch, chunks):
    stream = Stream(chunks)
    async def handle(request):
        return httpx.Response(200, stream=stream, headers={'Content-Type': 'text/event-stream'})
    transport(monkeypatch, handle)
    return adapter(stream=True).analyze(request_for(client))


def chunks_for(text, finish=None, done=True, usage=True):
    choice = {'delta': {'content': text}}
    if finish is not None:
        choice['finish_reason'] = finish
    chunks = [event({'choices': [choice]})]
    if usage:
        chunks.append(event({'choices': [], 'usage': USAGE}))
    if done:
        chunks.append(b'data: [DONE]\r\n\r\n')
    return chunks


@pytest.mark.parametrize('finish', [None, 'stop'])
@pytest.mark.parametrize('usage', [False, True])
def test_completed_stream_with_optional_finish_reason(client, monkeypatch, finish, usage):
    text = json.dumps(reading())
    result = run_stream(client, monkeypatch, chunks_for(text, finish, usage=usage))
    attempt = result.diagnostics['attempts'][0]
    assert attempt['finish_reason'] == finish
    assert attempt['stream_completed'] and attempt['status'] == 'completed'
    assert attempt['content_chars'] == len(text)
    assert result.diagnostics['request_count'] == 1
    assert attempt['usage_final'] == usage
    if usage:
        assert (result.input_tokens, result.output_tokens, result.total_tokens, result.reasoning_tokens) == (2520, 1910, 4430, 0)


@pytest.mark.parametrize('finish,code', [('length', 'PROVIDER_OUTPUT_TRUNCATED'),
                                       ('content_filter', 'PROVIDER_CONTENT_FILTER')])
def test_explicit_failure_finish_keeps_behavior(client, monkeypatch, finish, code):
    with pytest.raises(ProviderFailure) as exc:
        run_stream(client, monkeypatch, chunks_for(json.dumps(reading()), finish))
    assert exc.value.code == code
    attempt = exc.value.diagnostics['attempts'][0]
    assert attempt['finish_reason'] == finish and attempt['usage_final']


@pytest.mark.parametrize('finish', [None, 'stop'])
def test_usage_and_eof_without_done_are_incomplete(client, monkeypatch, finish):
    with pytest.raises(ProviderFailure) as exc:
        run_stream(client, monkeypatch, chunks_for(json.dumps(reading()), finish, done=False))
    assert exc.value.code == 'PROVIDER_MALFORMED_RESPONSE'
    assert not exc.value.diagnostics['attempts'][0]['stream_completed']


@pytest.mark.parametrize('bad', [b'data: {broken}\n\n', b'data: {"choices": [null]}\n\n', b'data: \xff\n\n'])
def test_malformed_sse_stays_rejected(client, monkeypatch, bad):
    chunks = chunks_for(json.dumps(reading()))
    chunks.insert(-1, bad)
    with pytest.raises(ProviderFailure) as exc:
        run_stream(client, monkeypatch, chunks)
    assert exc.value.code == 'PROVIDER_MALFORMED_RESPONSE'


@pytest.mark.parametrize('case', ['empty', 'json', 'schema', 'semantic', 'normalization'])
def test_done_without_finish_still_requires_valid_semantics(client, monkeypatch, case):
    raw = reading()
    if case == 'semantic':
        raw['components'][0]['manufacturer']['source'] = {}
    elif case == 'normalization':
        raw['components'][0]['manufacturer']['source']['page'] = 999
    text = {'empty': '', 'json': '{', 'schema': '{"bogus": 1}'}.get(case, json.dumps(raw))
    with pytest.raises(ProviderFailure) as exc:
        run_stream(client, monkeypatch, chunks_for(text))
    assert exc.value.code == ('NORMALIZATION_FAILED' if case == 'normalization' else 'INVALID_STRUCTURED_OUTPUT')
    attempt = exc.value.diagnostics['attempts'][0]
    assert attempt['stream_completed'] and attempt['finish_reason'] is None
