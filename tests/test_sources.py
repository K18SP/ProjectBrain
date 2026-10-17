import asyncio
import base64

import httpx
import pytest

from app import github_source, jira
from app.documents import document_project_data
from app.records import records_data


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_github_pagination_and_assignee_not_author(monkeypatch):
    pages = []
    def handler(request):
        if request.url.path.endswith('/readme'):
            return httpx.Response(200, json={"content": base64.b64encode(b'Orion deploys satellites.').decode()})
        if request.url.path.endswith('/issues'):
            page = int(request.url.params['page'])
            pages.append(page)
            return httpx.Response(200, headers={'link': '<next>; rel="next"'} if page == 1 else {}, json=[{
                'number': page, 'title': f'Work {page}', 'body': 'depends on #2' if page == 1 else '',
                'state': 'open', 'user': {'login': 'author'}, 'assignees': [{'login': 'owner'}] if page == 1 else []}])
        return httpx.Response(200, json={'full_name': 'team/orion', 'html_url': 'https://github.com/team/orion'})
    mock_client(monkeypatch, handler)
    data = asyncio.run(github_source.import_repository('https://github.com/team/orion'))
    assert pages == [1, 2]
    issues = [entity for entity in data.entities if entity.kind == 'Task']
    assert [entity.owner for entity in issues] == ['owner', '']
    assert any(link.kind == 'DEPENDS_ON' for link in data.links)
    assert any(entity.kind == 'DocumentSection' for entity in data.entities)
    assert not data.partial


def test_jira_cloud_paginates_and_preserves_link_direction(monkeypatch):
    monkeypatch.setenv('JIRA_BASE_URL', 'https://team.atlassian.net')
    monkeypatch.setenv('JIRA_EMAIL', 'test@example.test')
    monkeypatch.setenv('JIRA_API_TOKEN', 'test-token')
    def handler(request):
        import json
        body = json.loads(request.content)
        if body.get('nextPageToken'):
            return httpx.Response(200, json={'isLast': True, 'issues': [{'key': 'ORB-2', 'fields': {'summary': 'Launch'}}]})
        return httpx.Response(200, json={'nextPageToken': 'next', 'issues': [{'key': 'ORB-1', 'fields': {
            'summary': 'Telemetry', 'assignee': {'accountId': 'user-1', 'displayName': 'Ada'},
            'issuelinks': [{'type': {'outward': 'blocks'}, 'outwardIssue': {'key': 'ORB-2'}}]}}]})
    mock_client(monkeypatch, handler)
    data = asyncio.run(jira.import_jira('ORB'))
    link = next(link for link in data.links if link.kind == 'BLOCKS')
    assert link.source.endswith('ORB-1') and link.target.endswith('ORB-2')
    assert next(entity for entity in data.entities if entity.name.startswith('ORB-1')).owner == 'Ada'


@pytest.mark.parametrize('url', ['http://team.atlassian.net', 'https://localhost', 'https://team.atlassian.net.evil.test', 'https://user:pass@team.atlassian.net'])
def test_jira_rejects_untrusted_sites(url):
    with pytest.raises(ValueError):
        jira.jira_site(url)


def test_portable_records_reject_dangling_links_and_unsafe_urls():
    payload = {'name': 'Tracker', 'entities': [{'id': 'one', 'kind': 'Task', 'name': 'Task'}],
               'links': [{'source': 'one', 'target': 'missing', 'kind': 'BLOCKS'}]}
    with pytest.raises(ValueError):
        records_data('p', payload)
    payload['links'] = []
    payload['entities'][0]['url'] = 'javascript:alert(1)'
    with pytest.raises(ValueError):
        records_data('p', payload)


def test_document_reupload_identity_and_long_paragraph_preserved():
    text = 'x' * 2500
    first = document_project_data('p', 'Project', '', 'notes.txt', text, [])
    second = document_project_data('p', 'Project', '', 'notes.txt', 'Updated', [])
    assert first.source_id == second.source_id
    assert ''.join(entity.description for entity in first.entities if entity.kind == 'DocumentSection') == text


def test_cross_origin_write_is_rejected():
    from fastapi.testclient import TestClient
    from app.main import app
    response = TestClient(app).post('/api/projects', headers={'Origin': 'https://untrusted.example'}, json={'name': 'Blocked'})
    assert response.status_code == 403


def test_repository_without_readme_imports_code_and_import_edges(monkeypatch):
    code = {'pipeline.py': 'from worker import retrieve\nclass Pipeline:\n    """Retrieve documents and generate an answer."""\n    pass\n',
            'worker.py': 'def retrieve():\n    """Search indexed document chunks."""\n    return []\n'}
    def handler(request):
        path = request.url.path
        if path.endswith('/readme'):
            return httpx.Response(404)
        if path.endswith('/issues'):
            return httpx.Response(200, json=[])
        if '/git/trees/' in path:
            return httpx.Response(200, json={'tree': [{'path': name, 'type': 'blob', 'mode': '100644', 'sha': name, 'size': len(text)} for name, text in code.items()]})
        if '/git/blobs/' in path:
            return httpx.Response(200, json={'content': base64.b64encode(code[path.split('/')[-1]].encode()).decode()})
        return httpx.Response(200, json={'full_name': 'team/code', 'html_url': 'https://github.com/team/code', 'default_branch': 'main'})
    mock_client(monkeypatch, handler)
    data = asyncio.run(github_source.import_repository('https://github.com/team/code'))
    assert any(entity.kind == 'CodeSection' and 'Search indexed' in entity.description for entity in data.entities)
    assert any(link.kind == 'IMPORTS' and link.source.endswith('pipeline.py') and link.target.endswith('worker.py') for link in data.links)
    assert any('No README' in warning for warning in data.warnings)


def test_code_filters_and_excerpt_relevance():
    from app.repository_code import eligible
    from app.agent import relevant_excerpt
    assert not eligible('.env')
    assert not eligible('node_modules/a/index.js')
    assert not eligible('credentials.json')
    assert eligible('src/pipeline.py')
    text = ('unrelated setup line\n' * 100) + 'retrieval searches document embeddings\n'
    assert 'retrieval searches' in relevant_excerpt(text, {'retrieval'})


def test_source_root_resolution_stays_candidate_and_rejects_ambiguity():
    from app.repository_code import resolve_import
    assert resolve_import('worker', {'backend/worker.py': 'one'}) == ('one', 'candidate')
    assert resolve_import('worker', {'backend/worker.py': 'one', 'other/worker.py': 'two'})[0] is None
    assert resolve_import('backend.worker', {'backend/worker.py': 'one'}) == ('one', 'confirmed')
