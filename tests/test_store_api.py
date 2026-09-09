import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from manifold import store
from manifold.demo import demo
from manifold.server import app


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    project = tmp_path / 'projects' / 'demo.json'
    output = tmp_path / 'output'
    monkeypatch.setattr(store, 'PROJECT', project)
    monkeypatch.setattr(store, 'OUTPUT', output)
    original_read = store.read_design
    monkeypatch.setattr(store, 'read_design', lambda: original_read(project))
    import manifold.server as server
    monkeypatch.setattr(server, 'read_design', lambda: original_read(project))
    monkeypatch.setattr(server, 'OUTPUT', output)
    store.atomic_json(project, demo().model_dump())
    return project, output


def test_stale_edit_rejected_without_modifying_project(isolated):
    project, output = isolated
    before = project.read_bytes()
    with pytest.raises(ValueError, match='changed on disk'):
        store.rebuild(demo(), '0' * 64)
    assert project.read_bytes() == before
    assert store.current() is None


def test_revision_stable_after_json_roundtrip(isolated):
    assert store.revision(demo()) == store.revision(store.read_design())


def test_cad_exception_keeps_previous_design_and_pointer(isolated, monkeypatch):
    project, output = isolated
    store.atomic_json(output / 'current.json', {'build_id': 'previous'})
    before = project.read_bytes()
    def broken(*args): raise RuntimeError('CAD failure')
    monkeypatch.setattr(store, 'build_outputs', broken)
    with pytest.raises(RuntimeError): store.rebuild(demo(), store.revision(demo()))
    assert project.read_bytes() == before
    assert store.current() == {'build_id': 'previous'}


def test_edit_during_build_not_overwritten(isolated, monkeypatch):
    project, output = isolated
    def concurrent_edit(*args):
        changed = demo().model_dump(); changed['name'] = 'newer disk edit'
        store.atomic_json(project, changed)
        return dict(status='PASS', counts={})
    monkeypatch.setattr(store, 'build_outputs', concurrent_edit)
    with pytest.raises(ValueError, match='during build'): store.rebuild(demo(), store.revision(demo()))
    assert json.loads(project.read_text(encoding='utf-8'))['name'] == 'newer disk edit'
    assert store.current() is None


def test_lock_excludes_second_builder(isolated):
    def second():
        with store.project_lock(): return True
    with store.project_lock():
        with ThreadPoolExecutor() as executor:
            with pytest.raises((RuntimeError, BlockingIOError)):
                executor.submit(second).result()


def test_api_origin_header_schema_and_path_guards(isolated):
    client = TestClient(app,base_url='http://127.0.0.1:8765')
    assert client.get('/api/state').status_code == 200
    assert client.get('/api/state', headers={'Host': 'evil.example'}).status_code == 403
    body = dict(expected_revision=store.revision(demo()))
    assert client.post('/api/build', json=body).status_code == 403
    headers = {'X-PMC-Request': 'local-console', 'Origin': 'https://evil.example'}
    assert client.post('/api/build', json=body, headers=headers).status_code == 403
    headers['Origin'] = 'http://127.0.0.1:8765'
    assert client.post('/api/build', json={'expected_revision': 'bad'}, headers=headers).status_code == 422
    assert client.post('/api/build', json={'expected_revision': '0' * 64}, headers=headers).status_code == 409
    assert client.post('/api/build', content='x' * 8_000_001, headers={**headers, 'Content-Type': 'application/json'}).status_code == 413
    assert client.get('/api/artifacts/bad/server.py').status_code == 404
    assert client.post('/api/check-design', json=demo().model_dump(), headers=headers).status_code == 200
    assert client.post('/api/check-design', json={'name': 'bad'}, headers=headers).status_code == 422


def test_failed_step_export_is_blocked(isolated):
    project, output = isolated
    folder = output / 'builds' / ('a' * 32)
    store.atomic_json(folder / 'validation.json', {'status': 'FAIL'})
    (folder / 'production.step').write_text('diagnostic only')
    client = TestClient(app)
    assert client.get('/api/artifacts/' + 'a' * 32 + '/production.step').status_code == 409


def test_invalid_disk_file_marks_state_unavailable(isolated):
    project, output = isolated
    project.write_text('{broken')
    assert TestClient(app).get('/api/state').status_code == 422
