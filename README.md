# ProjectBrain

ProjectBrain is a graph-backed project investigation workspace built for **Graph Hacks: Context for AI Agents**. It connects work, people, decisions, and source records in FalkorDB. A question starts an investigation; specialist agents traverse connected records, save findings to the graph, and return an answer with inspectable evidence. Investigations remain available in later sessions.

## What works today

- A polished workspace with project signals, a searchable graph explorer, an assistant, investigation history, and a task approval screen.
- A repeatable Atlas demo project with blockers, ownership, pull requests, a release, a decision, a document, and a past investigation.
- Upload of TXT, Markdown, PDF, or DOCX files. Extracted sections connect to existing project records when their names are mentioned; these links are marked as candidates.
- Read-only import of the first 60 issues and pull requests from **any public GitHub repository**. Explicit `fixes #N`, `closes #N`, `resolves #N`, `blocked by #N`, and `depends on #N` references become relationships when both records are present.
- FalkorDB-backed project records, relationships, investigation findings, prior-session recall, and local action proposals.
- Dynamic natural-language question handling. The agent ranks relevant entities, traverses their FalkorDB relationships up to three hops, and combines dependency, ownership, knowledge, and memory findings.
- Optional model-generated wording with `OPENAI_API_KEY`; without a key, deterministic evidence-based wording still works.

**Current boundaries:** GitHub import is public and read-only. Jira OAuth, organization authentication, external writes, and multi-tenant isolation are designed future work, not live features. Uploaded document text is stored in FalkorDB and can be read through the unauthenticated local API; use only public or synthetic documents. Approved proposals stay inside ProjectBrain. This is a production-shaped prototype, not a system for processing private company data yet.

## Run locally

The easiest route is Docker Desktop:

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). FalkorDB Browser is at [http://localhost:3000](http://localhost:3000). On first load, ProjectBrain seeds the Atlas example if no projects exist.

Alternatively, run FalkorDB in Docker and the API in a local Python environment:

```bash
docker compose up -d falkordb
python -m venv .venv
# Activate the environment for your shell, then:
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` if you want to set credentials. The app reads environment variables; your shell or container runtime must load them. `GITHUB_TOKEN` is optional but helps avoid GitHub's anonymous API rate limit. `OPENAI_API_KEY` is optional.

## Use the demo

1. Open the workspace; the Atlas demo is loaded automatically.
2. Ask: **What is blocking the public beta launch?**
3. Inspect the three agent findings and connected source records.
4. Prepare a follow-up task, then approve it on the Investigations screen.
5. Ask a related question in a new browser session to see earlier investigation memory.
6. Use **Add a source** to import a public GitHub repository or upload a document to the selected project. The selector lets you switch between projects.

GitHub imports use the first page of issues and pull requests. On large repositories, this is a sample, not a complete repository analysis.

## Graph model

The `projectbrain` graph contains `Project`, `Entity`, `Investigation`, `Finding`, and `Proposal` nodes. `Entity.kind` identifies records such as `Task`, `Person`, `PullRequest`, `Milestone`, `Decision`, and `Document`. Project relationships use typed edges including `BLOCKS`, `REQUIRED_FOR`, `OWNS`, `IMPLEMENTS`, `CHANGES`, `SUPPORTS`, and `RESOLVES`. Each imported GitHub record keeps its source URL and update time. `Investigation` connects to `Finding` via `HAS_FINDING`; `Finding` connects to supporting `Entity` records via `SUPPORTED_BY`.

Core Cypher queries include:

```cypher
MATCH (a:Entity {id:$id, project_id:$project_id})-[r]-(b:Entity {project_id:$project_id})
RETURN b.id, b.kind, b.name, type(r), startNode(r).id, endNode(r).id
LIMIT 100
```

This neighborhood query is executed at each traversal step. The agent cannot form its dependency or evidence answer without FalkorDB.

```cypher
MATCH (i:Investigation {project_id:$project_id})
WHERE i.status='complete' AND i.id <> $exclude_id
RETURN i.id, i.question, i.answer, i.created_at
ORDER BY i.created_at DESC LIMIT 8
```

This retrieves cross-session memory. Findings and evidence are stored separately so a later agent can inspect what supported an answer.

## Architecture

```text
Browser UI → FastAPI → investigation orchestrator → bounded graph tools → FalkorDB
                    ↘ public GitHub importer ↗
```

The orchestrator ranks question-relevant records, traverses graph edges, and saves independent dependency, ownership, knowledge, and memory findings. The optional LLM only writes an answer from those findings. The graph remains authoritative for links and source provenance.

The connector boundary accepts normalized `Entity` and `Link` records through `ProjectData`. The document adapter extracts sections and identifies candidate mentions; future Jira and private-source adapters require authentication, permission rules, refresh logic, and entity resolution before handling real organizations.

## Tests

```bash
pytest -q
node --check web/app.js
```

An end-to-end check requires FalkorDB running. The project does not silently fall back to a mock store: `/api/health` reports `waiting` and graph endpoints return 503 when FalkorDB is unavailable.

## Hackathon alignment

| Requirement | Demonstrated behavior |
|---|---|
| Follow connections | Multi-hop traversal across tasks, milestones, people, changes, and decisions |
| Remember across sessions | Persisted investigation answers and findings |
| Share state between agents | Specialist findings are written to one shared investigation graph |
| Connect people, projects, and decisions | Atlas model and graph explorer |
| Show the path behind an answer | Findings link to supporting graph entities |

The clearest current entry is **Track 1: Agents That Act on Connected Data**. Track 2 and Track 3 foundations are present, but full multi-agent coordination and company-wide knowledge ingestion need further work before making broad claims about those tracks.

AI coding assistance was used in developing this project. The submitter should review, test, and explain its architecture and code before submission.
