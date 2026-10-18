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
    monkeypatch.setenv('FALKORDB_HOST','localhost')
    monkeypatch.setenv('FALKORDB_PORT','6379')
    for name in ('FALKORDB_PASSWORD','FALKORDB_USERNAME','FALKORDB_SSL'):
        monkeypatch.delenv(name,raising=False)
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

def test_approved_followup_executes_once_with_evidence(graph):
    from concurrent.futures import ThreadPoolExecutor
    graph.import_project(snapshot())
    investigation = asyncio.run(investigate(graph, 'orion', 'Who owns ORB-1?', 'action'))
    proposal = graph.create_proposal(investigation['id'], 'Review telemetry ownership', 'Confirm current assignment.')
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: graph.decide_proposal(proposal['id'], True), range(3)))
    assert len({result['task_id'] for result in results}) == 1
    task_id = results[0]['task_id']
    assert len([item for item in graph.entities('orion') if item['id'] == task_id]) == 1
    assert any(edge['source'] == task_id and edge['kind'] == 'BASED_ON' for edge in graph.links('orion'))
    assert graph.decide_proposal(proposal['id'], False)['status'] == 'approved'


def test_rejected_action_creates_no_task_and_invalid_investigation_rejected(graph):
    graph.import_project(snapshot())
    investigation = asyncio.run(investigate(graph, 'orion', 'Who owns ORB-1?', 'action'))
    proposal = graph.create_proposal(investigation['id'], 'Review telemetry', 'Check evidence')
    assert graph.decide_proposal(proposal['id'], False)['status'] == 'rejected'
    assert graph.decide_proposal(proposal['id'], True)['task_id'] is None
    with pytest.raises(ValueError): graph.create_proposal('missing', 'Invalid action', '')


def test_memory_beyond_recent_eight_and_stale_source_flag(graph):
    graph.import_project(snapshot())
    earlier = graph.create_investigation('orion', 'Why telemetry uses caching?', 'old-session')
    graph.complete_investigation(earlier, 'The telemetry caching decision was documented.')
    for index in range(10):
        other = graph.create_investigation('orion', f'Unrelated item {index}', 'new-session')
        graph.complete_investigation(other, 'Unrelated response')
    result = graph.search_memory('orion', 'telemetry caching')
    assert result[0]['id'] == earlier and not result[0]['stale']
    graph.import_project(snapshot(assigned=False))
    assert graph.search_memory('orion', 'telemetry caching')[0]['stale']


def test_real_mcp_protocol_scoping_and_path(graph):
    from app.mcp_tools import project_server
    from mcp.shared.memory import create_connected_server_and_client_session
    graph.import_project(snapshot())
    async def run():
        async with create_connected_server_and_client_session(project_server(graph, 'orion')) as client:
            listing = await client.list_tools()
            assert {tool.name for tool in listing.tools} == {'search_records','follow_connections','find_path','recall_investigations'}
            result = await client.call_tool('find_path', {'source_id':'person','target_id':'work'})
            assert not result.isError
            import json
            content = result.structuredContent or json.loads(result.content[0].text)
            assert content['edges'][0]['kind'] == 'OWNS'
            invalid = await client.call_tool('follow_connections', {'entity_id':'another-project-record'})
            assert invalid.isError
    asyncio.run(run())

def test_model_selects_actual_mcp_tools(graph, monkeypatch):
    import httpx,json
    from app.mcp_tools import collect_context
    graph.import_project(snapshot())
    monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
    requests=[]
    def handler(request):
        payload=json.loads(request.content); requests.append(payload)
        assert payload['model']=='openrouter/free'
        assert payload['provider']['max_price']=={'prompt':0,'completion':0}
        if len(requests)==1:
            return httpx.Response(200,json={'choices':[{'message':{'tool_calls':[{'id':'search','type':'function','function':{'name':'search_records','arguments':json.dumps({'query':'Telemetry'})}}]}}]})
        assert payload['messages'][-1]['role']=='tool'
        return httpx.Response(200,json={'choices':[{'message':{'tool_calls':[{'id':'neighbors','type':'function','function':{'name':'follow_connections','arguments':json.dumps({'entity_id':'work','depth':2})}}]}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    result=asyncio.run(collect_context(graph,'orion','Who owns telemetry?'))
    assert result['status']=='used'
    assert [step['tool'] for step in result['trace']]==['search_records','follow_connections']
    assert any(edge['kind']=='OWNS' for edge in result['edges'])
