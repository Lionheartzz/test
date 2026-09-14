"""The shipped app exposes configured AI only; test doubles stay in tests."""
from fastapi.testclient import TestClient
from manifold.server import app
from manifold.ai_design import config, providers


def test_unconfigured_app_has_no_mock_fallback(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'path',lambda:tmp_path/'provider.json')
    assert providers.available_providers()=={}
    assert TestClient(app).get('/api/ai-design/providers').json()==[]


def test_configured_app_exposes_only_real_provider(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'path',lambda:tmp_path/'provider.json')
    client=TestClient(app)
    response=client.post('/api/ai-design/settings',headers={'X-PMC-Request':'local-console'},json=dict(
        enabled=True,base_url='https://example.invalid/v1',model='operator-model',api_key='test-only'))
    assert response.status_code==200
    rows=client.get('/api/ai-design/providers').json()
    assert len(rows)==1 and rows[0]['id']=='configured'
    assert rows[0]['is_mock'] is False and rows[0]['network_required'] is True
    assert 'mock-safe' not in providers.available_providers()
    assert 'mock-example' not in providers.available_providers()
    assert client.get('/ai-demo.png').status_code==404
