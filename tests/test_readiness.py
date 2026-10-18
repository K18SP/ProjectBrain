from app.agent import valid_citations
from fastapi.testclient import TestClient
from app.main import app


def test_unknown_citations_and_uncited_model_output_rejected():
    assert valid_citations('Owner is Ada [E1]', {'E1':'person'})
    assert not valid_citations('Owner is Ada [E2]', {'E1':'person'})
    assert not valid_citations('Owner is Ada', {'E1':'person'})
    assert not valid_citations('Ada [E1] and links [E2-E9]', {'E1':'person'})
    assert not valid_citations('Ada [E1] and links [E2–E9]', {'E1':'person'})


def test_public_deployment_requires_password(monkeypatch):
    monkeypatch.setenv('PUBLIC_DEPLOYMENT','true')
    monkeypatch.delenv('APP_PASSWORD',raising=False)
    assert TestClient(app).get('/').status_code == 503


def test_workspace_auth_protects_reads_and_writes(monkeypatch):
    monkeypatch.setenv('APP_PASSWORD','test-private-password')
    client = TestClient(app)
    assert client.get('/api/projects').status_code == 401
    assert client.post('/api/projects',json={'name':'blocked'}).status_code == 401
    assert client.get('/',auth=('reviewer','wrong')).status_code == 401
    assert client.get('/',auth=('reviewer','test-private-password')).status_code == 200


def test_public_demo_blocks_private_import_routes(monkeypatch):
    monkeypatch.setenv('DEMO_PUBLIC_SOURCES_ONLY','true')
    monkeypatch.delenv('APP_PASSWORD',raising=False)
    monkeypatch.setenv('PUBLIC_DEPLOYMENT','false')
    client = TestClient(app)
    assert client.post('/api/projects/import/jira',json={'reference':'KAN'}).status_code == 403
    assert client.post('/api/projects/example/imports',files={'file':('notes.txt',b'private')}).status_code == 403
    assert client.get('/api/connectors').json()['public_sources_only'] is True


def test_generated_followup_not_reused_as_source_for_code_question():
    from app.agent import rank_entities
    nodes=[{'id':'followup:1','name':'API RAG connections','kind':'Task','description':'An earlier generated answer'},
           {'id':'file:1','name':'routes.py','kind':'CodeSection','description':'API RAG connections'}]
    assert [n['id'] for n in rank_entities('Explain API RAG connections',nodes)] == ['file:1']
    assert any(n['id']=='followup:1' for n in rank_entities('Show follow-up tasks about API',nodes))


def test_citation_ranges_expand_but_unknown_sources_still_rejected():
    from app.agent import normalize_citations
    assert normalize_citations('Path [E1–E3]') == 'Path [E1] [E2] [E3]'
    assert not valid_citations(normalize_citations('Path [E1–E3]'), {'E1':'a','E2':'b'})


def test_evidence_fallback_is_short_and_uses_exact_sources():
    from app.agent import concise_evidence
    records=[{'id':'a','name':'service.py','description':'"""Retrieves relevant documents."""'+('\ncode()'*1000)}]
    answer=concise_evidence(records,[],records,{'E1':'a'},'How does retrieval work?')
    assert '[E1]' in answer and 'Retrieves relevant documents' in answer
    assert len(answer)<600 and 'code()' not in answer
