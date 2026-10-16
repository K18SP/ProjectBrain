from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agent import investigate
from .demo import demo_project
from .documents import document_project_data, extract_document
from .github import import_public_repo
from .graph import GraphStore
from .schema import ApprovalRequest, AskRequest, ImportRequest, ProposalRequest


app = FastAPI(title="ProjectBrain", version="0.1.0")
web_dir = Path(__file__).resolve().parent.parent / "web"
app.mount("/assets", StaticFiles(directory=web_dir), name="assets")


def store() -> GraphStore:
    try:
        graph = GraphStore()
        graph.ping()
        return graph
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"FalkorDB is unavailable: {type(exc).__name__}") from exc


@app.get("/")
def index():
    return FileResponse(web_dir / "index.html")


@app.get("/api/health")
def health():
    try:
        store()
        return {"status": "ready", "graph": "connected"}
    except HTTPException:
        return {"status": "waiting", "graph": "unavailable"}


@app.post("/api/demo/seed")
def seed_demo():
    return store().import_project(demo_project())


@app.get("/api/projects")
def projects():
    return store().projects()


@app.get("/api/projects/{project_id:path}/graph")
def project_graph(project_id: str):
    graph = store()
    project = graph.project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project, "nodes": graph.entities(project_id), "edges": graph.links(project_id),
            "investigations": graph.recent_investigations(project_id), "proposals": graph.proposals(project_id)}


@app.post("/api/projects/import/github")
async def github_import(request: ImportRequest):
    try:
        data = await import_public_repo(request.url)
        return store().import_project(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = "GitHub repository was not found or is not publicly accessible" if status == 404 else f"GitHub returned {status}"
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach GitHub") from exc


@app.post("/api/projects/{project_id:path}/documents")
async def upload_document(project_id: str, file: UploadFile = File(...)):
    graph = store()
    project = graph.project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    payload = await file.read(5 * 1024 * 1024 + 1)
    try:
        content = extract_document(file.filename or "", payload)
        if not content.strip():
            raise ValueError("The document contains no readable text")
        data = document_project_data(project_id, project["name"], project["description"], file.filename or "document", content,
                                     graph.entities(project_id))
        return graph.import_project(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/investigations")
async def ask(request: AskRequest):
    graph = store()
    if not graph.project(request.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return await investigate(graph, request.project_id, request.question, request.session_id)


@app.post("/api/proposals")
def propose(request: ProposalRequest):
    return store().create_proposal(request.investigation_id, request.title, request.description)


@app.post("/api/proposals/{proposal_id}/decision")
def decide(proposal_id: str, request: ApprovalRequest):
    result = store().decide_proposal(proposal_id, request.approved)
    if not result:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return result
