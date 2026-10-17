from __future__ import annotations

from pathlib import Path
from hashlib import sha256
from uuid import uuid4
import asyncio
import json
import os
import zipfile
from pypdf.errors import PdfReadError

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from dotenv import load_dotenv

from .agent import investigate
from .documents import document_project_data, extract_document
from .github_source import import_repository
from .jira import import_jira, jira_data
from .records import records_data
from .graph import GraphStore
from .schema import ApprovalRequest, AskRequest, ImportRequest, ProposalRequest, CreateProjectRequest, JiraRequest, SyncRequest


load_dotenv()
app = FastAPI(title="ProjectBrain", version="0.2.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(","))
web_dir = Path(__file__).resolve().parent.parent / "web"
app.mount("/assets", StaticFiles(directory=web_dir), name="assets")


@app.middleware("http")
async def local_request_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != str(request.base_url).rstrip("/"):
        return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(httpx.HTTPStatusError)
async def provider_error(request: Request, exc: httpx.HTTPStatusError):
    status = exc.response.status_code
    messages = {401: "Source authentication failed. Check the server credentials.",
                403: "Source access was denied or its rate limit was reached. Check permissions and try later.",
                404: "The source was not found or is not accessible with the configured credentials.",
                429: "The source rate limit was reached. Try again later."}
    return JSONResponse({"detail": messages.get(status, "The source provider could not complete this request. Try again later.")}, status_code=502)


@app.exception_handler(httpx.HTTPError)
async def provider_network_error(request: Request, exc: httpx.HTTPError):
    return JSONResponse({"detail": "The source could not be reached. Check the connection and try again."}, status_code=502)


def attach_to_project(graph: GraphStore, data, project_id: str | None):
    if project_id:
        project = graph.project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Select an existing project")
        data = data.model_copy(update={"project_id": project_id, "name": project["name"], "description": project["description"]})
    return graph.import_project(data)


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


@app.get("/api/projects")
def projects():
    return store().projects()


@app.post("/api/projects", status_code=201)
def create_project(request: CreateProjectRequest):
    graph = store()
    project_id = f"project:{uuid4()}"
    graph.query("CREATE (p:Project {id:$id,name:$name,description:$description})",
                {"id": project_id, "name": request.name, "description": request.description})
    return {"project_id": project_id}


@app.get("/api/connectors")
def connectors():
    return {"github_authenticated": bool(os.getenv("GITHUB_TOKEN")),
            "jira_configured": all(os.getenv(key) for key in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")),
            "answer_mode": "model" if os.getenv("OPENAI_API_KEY") else "evidence"}


@app.get("/api/projects/{project_id:path}/graph")
def project_graph(project_id: str):
    graph = store()
    project = graph.project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project, "nodes": graph.entities(project_id), "edges": graph.links(project_id),
            "investigations": graph.recent_investigations(project_id), "proposals": graph.proposals(project_id),
            "sources": graph.sources(project_id)}


@app.post("/api/projects/import/github")
async def github_import(request: ImportRequest):
    try:
        graph = await run_in_threadpool(store)
        data = await import_repository(request.url)
        return await run_in_threadpool(attach_to_project, graph, data, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/import/jira")
async def jira_import(request: JiraRequest):
    try:
        graph = await run_in_threadpool(store)
        data = await import_jira(request.reference)
        return await run_in_threadpool(attach_to_project, graph, data, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sources/sync")
async def sync_source(request: SyncRequest):
    graph = await run_in_threadpool(store)
    sources = await run_in_threadpool(graph.sources, request.project_id)
    source = next((item for item in sources if item["id"] == request.source_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found in this project")
    try:
        if source["kind"] == "github":
            data = await import_repository(source["url"])
        elif source["kind"] == "jira":
            data = await import_jira(source["url"])
        else:
            raise HTTPException(status_code=400, detail="Upload the updated file with the same filename or source name to refresh it")
        if data.source_id != source["id"]:
            raise HTTPException(status_code=409, detail="The source identity changed. Import it as a new source to review the change.")
        return await run_in_threadpool(attach_to_project, graph, data, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id:path}/documents")
@app.post("/api/projects/{project_id:path}/imports")
async def upload_document(project_id: str, file: UploadFile = File(...)):
    graph = await run_in_threadpool(store)
    project = await run_in_threadpool(graph.project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    payload = await file.read(5 * 1024 * 1024 + 1)
    try:
        if not payload or len(payload) > 5 * 1024 * 1024:
            raise ValueError("Upload a non-empty file smaller than 5 MB")
        filename = Path(file.filename or "document").name
        if filename.lower().endswith(".json"):
            parsed = json.loads(payload)
            if not isinstance(parsed, dict):
                raise ValueError("The JSON file must contain an object")
            if "issues" in parsed or ("key" in parsed and "fields" in parsed):
                source_id = "jira-export:" + sha256(filename.encode()).hexdigest()[:24]
                data = jira_data(parsed, filename, source_id)
            else:
                data = records_data(project_id, parsed)
        else:
            content = await run_in_threadpool(extract_document, filename, payload)
            if not content.strip():
                raise ValueError("The document contains no readable text")
            existing = await run_in_threadpool(graph.entities, project_id)
            data = document_project_data(project_id, project["name"], project["description"], filename, content, existing)
        return await run_in_threadpool(attach_to_project, graph, data, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file: " + str(exc)[:500]) from exc
    except (KeyError, TypeError, AttributeError, OSError, zipfile.BadZipFile, PdfReadError) as exc:
        raise HTTPException(status_code=400, detail="The file has an unsupported or incomplete structure") from exc


@app.post("/api/investigations")
async def ask(request: AskRequest):
    graph = await run_in_threadpool(store)
    if not await run_in_threadpool(graph.project, request.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return await run_in_threadpool(lambda: asyncio.run(investigate(graph, request.project_id, request.question, request.session_id)))


@app.post("/api/proposals")
def propose(request: ProposalRequest):
    return store().create_proposal(request.investigation_id, request.title, request.description)


@app.post("/api/proposals/{proposal_id}/decision")
def decide(proposal_id: str, request: ApprovalRequest):
    result = store().decide_proposal(proposal_id, request.approved)
    if not result:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return result
