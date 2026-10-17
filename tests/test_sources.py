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
