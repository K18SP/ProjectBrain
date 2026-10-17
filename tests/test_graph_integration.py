"""Opt-in real FalkorDB tests. Each test owns and removes its unique test graph."""
import asyncio
import os
from uuid import uuid4

import pytest

from app.agent import investigate
from app.graph import GraphStore
from app.records import records_data
from app.schema import Entity, Link, ProjectData


@pytest.fixture
def graph(monkeypatch):
    if os.getenv('RUN_GRAPH_TESTS') != '1':
        pytest.skip('Set RUN_GRAPH_TESTS=1 with FalkorDB running')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    store = GraphStore()
    name = f'projectbrain_test_{uuid4().hex}'
    store.graph = store.db.select_graph(name)
    store.ping()
    try:
        yield store
    finally:
        store.graph.delete()


def snapshot(project='orion', assigned=True, partial=False):
    entities = [Entity(id='work', kind='Task', name='ORB-1 Telemetry', status='open', source='tracker', owner='Ada' if assigned else '')]
    links = []
    if assigned:
        entities.append(Entity(id='person', kind='Person', name='Ada', source='tracker'))
        links.append(Link(source='person', target='work', kind='OWNS'))
    return ProjectData(project_id=project, name=project, entities=entities, links=links,
                       source_id='tracker', source_kind='records', partial=partial)


def test_upload_api_refresh_and_invalid_documents(graph, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(main, 'store', lambda: graph)
    client = TestClient(main.app)
    project = client.post('/api/projects', json={'name': 'Upload verification'}).json()['project_id']
    route = f'/api/projects/{project}/imports'
    for content in (b'First release notes', b'Updated release notes'):
        response = client.post(route, files={'file': ('notes.txt', content, 'text/plain')})
        assert response.status_code == 200, response.text
    assert len(graph.sources(project)) == 1
    assert any('Updated release' in item['description'] for item in graph.entities(project))
    assert not any('First release' in item['description'] for item in graph.entities(project))
    for filename in ('broken.pdf', 'broken.docx'):
        response = client.post(route, files={'file': (filename, b'not a valid document')})
        assert response.status_code == 400, response.text


def test_source_refresh_replaces_assignee_edges_even_when_partial(graph):
    graph.import_project(snapshot())
    graph.import_project(snapshot(assigned=False, partial=True))
    assert not any(link['kind'] == 'OWNS' for link in graph.links('orion'))
    assert next(item for item in graph.entities('orion') if item['id'] == 'work')['owner'] == ''


def test_reimport_archives_missing_records_without_duplicates(graph):
    graph.import_project(snapshot())
    graph.import_project(snapshot(assigned=False))
    graph.import_project(snapshot(assigned=False))
    assert len(graph.entities('orion')) == 1
    assert len(graph.sources('orion')) == 1


def test_investigation_is_project_scoped_and_answers_real_records(graph):
    graph.import_project(snapshot('orion'))
    other = snapshot('other')
    other.entities[0].name = 'Unrelated secret project'
    graph.import_project(other)
    result = asyncio.run(investigate(graph, 'orion', 'Who owns ORB-1?', 'test-session'))
    assert 'Ada' in result['answer'] and 'Unrelated' not in result['answer']
    assert result['findings'] and graph.recent_investigations('orion')
    rows = graph.query('MATCH (i:Investigation {id:$id})-[:HAS_FINDING]->(:Finding)-[:SUPPORTED_BY]->(e:Entity) RETURN e.project_id', {'id': result['id']})
    assert {row[0] for row in rows} == {'orion'}


def test_cross_source_ticket_mentions_are_candidates(graph):
    graph.import_project(snapshot())
    graph.import_project(records_data('orion', {'name': 'Meeting notes', 'entities': [
        {'id': 'doc', 'kind': 'Document', 'name': 'Review', 'description': 'Discuss ORB-1 before release.'}]}))
    mentions = [link for link in graph.links('orion') if link['kind'] == 'MENTIONS']
    assert len(mentions) == 1 and mentions[0]['confidence'] == 'candidate'


def test_repository_label_is_not_an_answer(graph):
    graph.import_project(ProjectData(project_id='empty', name='Empty', entities=[Entity(id='repo', kind='Repository', name='Empty')], links=[]))
    answer = asyncio.run(investigate(graph, 'empty', 'Explain what this repo is about', 'test'))
    assert 'not enough source content' in answer['answer']


def test_code_question_uses_connected_content(graph):
    graph.import_project(ProjectData(project_id='code', name='Code', entities=[
        Entity(id='repo', kind='Repository', name='Team/code'),
        Entity(id='file', kind='CodeFile', name='pipeline.py', description='RetrievalPipeline: Retrieves documents then generates an answer.'),
        Entity(id='section', kind='CodeSection', name='pipeline.py lines 1-20', description='retrieved = retriever.search(question)\nanswer = generator.generate(retrieved)')],
        links=[Link(source='file', target='repo', kind='PART_OF'), Link(source='section', target='file', kind='PART_OF')]))
    answer = asyncio.run(investigate(graph, 'code', 'Explain how retrieval works', 'test'))
    assert 'Retrieves documents' in answer['answer'] or 'retriever.search' in answer['answer']
    assert answer['edges']
    assert any('section' in finding['entity_ids'] or 'file' in finding['entity_ids'] for finding in answer['findings'])
