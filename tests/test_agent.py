from app.agent import rank_entities, terms
from app.demo import demo_project
from app.github import parse_public_repo
from app.documents import document_project_data, extract_document
from fastapi.testclient import TestClient
from app.main import app


def test_dynamic_question_selects_relevant_milestone_and_blocker():
    project = demo_project()
    entities = [entity.model_dump() for entity in project.entities]
    ranked = rank_entities("What is blocking the public beta launch?", entities)
    ids = {entity["id"] for entity in ranked}
    assert "milestone:launch" in ids
    assert "task:auth" in ids


def test_public_repo_url_rejects_non_github_host_and_deep_links():
    assert parse_public_repo("https://github.com/K18SP/ProjectBrain.git") == ("K18SP", "ProjectBrain")
    for url in ("https://github.com.evil.test/a/b", "https://github.com/a/b/issues/1", "http://github.com/a/b"):
        try:
            parse_public_repo(url)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted invalid URL: {url}")


def test_question_terms_ignore_filler():
    assert terms("Who owns the security review?") == {"owns", "security", "review"}


def test_document_mentions_are_candidates_and_original_record_is_preserved():
    text = extract_document("notes.md", b"# Review\nComplete security review before release.")
    data = document_project_data("atlas", "Atlas", "Product analytics platform", "notes.md", text,
                                 [{"id": "task:security", "kind": "Task", "name": "Complete security review"}])
    assert data.description == "Product analytics platform"
    assert any(link.target == "task:security" and link.confidence == "candidate" for link in data.links)


def test_ui_is_served_without_graph_connection():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "ProjectBrain" in response.text
