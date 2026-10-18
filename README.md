# ProjectBrain

ProjectBrain is a graph-backed project investigation workspace built for **Graph Hacks: Context for AI Agents**. It connects work, people, decisions, and source records in FalkorDB. A question starts an investigation; specialist agents traverse connected records, save findings to the graph, and return an answer with inspectable evidence. Investigations remain available in later sessions.

## What works today

- A polished workspace with project signals, a searchable graph explorer, an assistant, investigation history, and a task approval screen.
- Starts empty: every project and source comes from user imports. Synthetic fixtures exist only under tests.
- Upload of TXT, Markdown, PDF, or DOCX files. Extracted sections connect to existing project records when their names are mentioned; these links are marked as candidates.
- Read-only paginated import of GitHub issues, pull requests, assignees, milestones, and README sections. The default is up to 1,000 work records, configurable with `IMPORT_MAX_RECORDS` (maximum 5,000). Explicit `fixes #N`, `closes #N`, `resolves #N`, `blocked by #N`, and `depends on #N` references become relationships when both records are present.
- FalkorDB-backed project records, relationships, investigation findings, prior-session recall, and local action proposals.
- Dynamic natural-language question handling. The agent ranks relevant entities, traverses their FalkorDB relationships up to three hops, and combines dependency, ownership, knowledge, and memory findings.
- Optional model-generated wording with `OPENROUTER_API_KEY`; without a key, deterministic evidence-based wording still works.

**Current boundaries:** This is a working hackathon application with shared-workspace password protection for hosting, not a multi-tenant production service. Imports run within requests and refreshes are not transactional. Connectors read source systems; approved proposals create persistent local tasks linked to their evidence. Retrieval combines lexical ranking, bounded graph traversal, and optional model-selected MCP tools. Free model availability varies. Citation validation checks reference IDs, not factual entailment. Keep private company data in a properly secured environment.

**Hosted demo:** https://projectbrain-k18sp.embarko.app (workspace sign-in required). The free demo accepts public GitHub sources only. Jira and file imports are disabled there. Its database connection is unencrypted by explicit owner approval; never enter private information. Local Jira/file support remains available. Owner sign-in details are saved in ignored `data/hosting.env` and must be shared privately with reviewers.


## Run locally

The easiest route is Docker Desktop:

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). FalkorDB Browser is at [http://localhost:3000](http://localhost:3000). An empty installation starts with onboarding. Add your own source. There is no demo seeding route.

Alternatively, run FalkorDB in Docker and the API in a local Python environment:

```bash
docker compose up -d falkordb
python -m venv .venv
# Activate the environment for your shell, then:
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` if you want to set credentials. Docker Compose and the local API load these settings; credentials remain on the server. Never commit `.env`. `GITHUB_TOKEN` is optional but helps avoid GitHub's anonymous API rate limit. `OPENROUTER_API_KEY` is optional.

### Windows Docker Desktop startup issue

Some Docker Desktop versions fail before the Linux engine starts because Windows cannot remove transient `dockerInference` or `engine.sock` socket files. If Docker logs show this exact error, see [Docker's issue report](https://github.com/docker/desktop-feedback/issues/531). After Docker Desktop has fully stopped, move both `%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine` aside to uniquely named backup folders, set `"EnableDockerAI": false` in a backed-up `%APPDATA%\Docker\settings-store.json`, and restart Docker Desktop. These are runtime socket folders; keep the backups until the engine and your containers are verified. Do not use Docker Desktop's factory reset to resolve this socket error, because it can remove local container data and volumes.

## Connect your own sources

Use **Add a source** to create a project or attach several sources to an existing project. Questions, suggestions, records, and evidence are based on the selected project. Sources show their last refresh time and coverage warnings. Use **Refresh** for GitHub or Jira; upload a file again with the same filename (or portable source name) to refresh it. Refresh is manual, not continuous synchronization. Partial imports retain older records outside the fetched sample; check timestamps and warnings before relying on answers.

For Jira Cloud, put these values in your local `.env`, then recreate the app with `docker compose up --build -d`:

```dotenv
JIRA_BASE_URL=https://your-team.atlassian.net
JIRA_EMAIL=your-account@example.com
JIRA_API_TOKEN=your-token
```

The Jira tab accepts a ticket URL, a ticket key such as `TEAM-123`, or a project key such as `TEAM`. It imports accessible tickets, assignees, statuses, parent relationships, and explicit issue links. Jira references in other sources become candidate mentions, not confirmed dependencies. Live ticket import and refresh were verified against the owner’s Jira Cloud workspace on 18 October 2026. Automated tests also cover simulated Jira responses.

Upload TXT, Markdown, PDF, DOCX, Jira JSON exports, or portable JSON for other tools. Native Slack, Notion, and other connectors are not implemented. Portable JSON uses this structure:

```json
{
  "name": "Team tracker",
  "entities": [
    {"id": "task-1", "kind": "Task", "name": "Prepare launch", "status": "open"},
    {"id": "person-1", "kind": "Person", "name": "Ada"}
  ],
  "links": [{"source": "person-1", "target": "task-1", "kind": "OWNS"}]
}
```

IDs must be unique within the upload and all link endpoints must exist. Supported relations: `BLOCKS`, `DEPENDS_ON`, `REQUIRED_FOR`, `OWNS`, `OPENED`, `PART_OF`, `BELONGS_TO`, `RESOLVES`, `IMPLEMENTS`, `CHANGES`, `SUPPORTS`, `RELATED_TO`, `MENTIONS`. Confidence is `confirmed` or `candidate`. Files must be smaller than 5 MB; documents are limited to 200,000 characters and PDFs to 100 pages. README ingestion is limited to 48,000 characters. Large-source imports report their coverage limits.

## Graph model

The `projectbrain` graph contains `Project`, `Source`, `Entity`, `Investigation`, `Finding`, and `Proposal` nodes. `Entity.kind` identifies records such as `Task`, `Person`, `PullRequest`, `Milestone`, `Decision`, and `Document`. Project relationships use typed edges including `BLOCKS`, `REQUIRED_FOR`, `OWNS`, `IMPLEMENTS`, `CHANGES`, `SUPPORTS`, and `RESOLVES`. Each imported GitHub record keeps its source URL and update time. `Investigation` connects to `Finding` via `HAS_FINDING`; `Finding` connects to supporting `Entity` records via `SUPPORTED_BY`.

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
ORDER BY i.created_at DESC LIMIT 20
```

The implementation additionally filters question/answer text for relevant terms and flags changed source versions; retrieval searches beyond the latest eight investigations. This supports cross-session memory. Findings and evidence are stored separately so a later agent can inspect what supported an answer.

## Architecture

```text
Browser UI → FastAPI → investigation orchestrator → bounded graph tools → FalkorDB
                    ↘ GitHub / Jira / file adapters ↗
```

The orchestrator ranks question-relevant records, traverses graph edges, and saves independent dependency, ownership, knowledge, and memory findings. A free model can select project-scoped MCP search, connection traversal, confirmed-path and memory tools through the MCP SDK. Two model turns permit at most four calls; a separate synthesis step validates source references. Tool traces and citation IDs are persisted. The graph remains authoritative for links and source provenance.

The connector boundary accepts normalized `Entity` and `Link` records through `ProjectData`. Adapters normalize GitHub, Jira, documents, and portable records. Sources carry stable identities and refresh metadata. Organization-wide deployment still requires individual identities, permissions, durable jobs, transactional refresh, encrypted database access, and operational monitoring.

## Tests

```bash
pytest -q
node --check web/app.js
```

Run database integration tests against a running FalkorDB with `$env:RUN_GRAPH_TESTS="1"; pytest -q` in PowerShell. Each test uses a separate temporary graph and deletes only that graph. An end-to-end check requires FalkorDB running. The project does not silently fall back to a mock store: `/api/health` reports `waiting` and graph endpoints return 503 when FalkorDB is unavailable.

## Hackathon alignment

| Requirement | Demonstrated behavior |
|---|---|
| Follow connections | Multi-hop traversal across tasks, milestones, people, changes, and decisions |
| Remember across sessions | Persisted investigation answers and findings |
| Share state between agents | Specialist findings are written to one shared investigation graph |
| Connect people, projects, and decisions | Imported assignees, tickets, files, and explicit portable decision records |
| Show the path behind an answer | Findings link to supporting graph entities |

The clearest current entry is **Track 1: Agents That Act on Connected Data**. Track 2 and Track 3 foundations are present, but full multi-agent coordination and company-wide knowledge ingestion need further work before making broad claims about those tracks.

AI coding assistance was used in developing this project. The submitter should review, test, and explain its architecture and code before submission.

## Repository questions and answer modes

A repository with no README still imports a file listing and selected code. Up to 500 eligible file records and content for 24 prioritized files (each at most 40 KB) are imported. Generated/vendor folders and common credential filenames are excluded; this is not a secret scanner. Python imports become explicit `IMPORTS` edges; code sections retain file/line links. Other languages are searchable text. No imported code runs. Selection is bounded, not an exhaustive code audit, and coverage appears beside each answer.

Without `OPENROUTER_API_KEY`, chat shows source excerpts and connections. This mode does not provide free-form AI synthesis. For AI-written explanations, configure that key in local `.env` and recreate the app. A provider failure falls back visibly to source evidence. Missing source content produces an explicit limitation instead of a repository-name-only answer.

See [HACKATHON_AUDIT.md](HACKATHON_AUDIT.md) for the implementation and submission gaps. The standard HTML/CSS/JavaScript files are the UI application, not hardcoded project data.

## Free-only OpenRouter

Set `OPENROUTER_API_KEY` in the ignored local `.env` file and recreate the app. Model routing is fixed in code to `openrouter/free`, with maximum prompt and completion prices set to zero. No paid model or OpenAI fallback is available. If free capacity, quota, or credentials are unavailable, the app shows source evidence instead. Account-level free limits still apply. Keys are not returned by the API or copied into the Docker image.

The demo recording is in [docs/projectbrain-demo.mp4](docs/projectbrain-demo.mp4). It shows the local app using a real public repository, source-evidence investigation, follow-up approval, and persisted history after a new session.

## MCP and approved actions

Run an external scoped MCP server with `PROJECTBRAIN_PROJECT_ID` set and `python -m app.mcp_tools`. The app itself uses the SDK’s in-memory JSON-RPC transport. Tools are read-only and never accept raw Cypher. Specialist functions are sequential; they are not independent autonomous agents.

Approving a proposal atomically creates one Task and links it to its investigation and supporting records. Repeated or concurrent approval returns the same task. Rejection does not create work. These tasks stay inside ProjectBrain; no GitHub or Jira issue is created.

## Deployment

`scripts/deploy_embarko.py` builds a source-only package; `--deploy` uses the saved authenticated Embarko token and configured external FalkorDB. It excludes credentials and local records, sets workspace authentication, disables private connectors, and verifies graph health. Use only the approved free tier. Do not disable database TLS for a private-data deployment.

See [submission notes](docs/SUBMISSION.md) and [readiness audit](HACKATHON_AUDIT.md) for verified features and remaining external steps.

Recording note: the final recording shows source-evidence fallback because free synthesis did not return an acceptable answer during capture. The recording includes model-selected MCP search and a rejected traversal request using an invalid record ID; earlier live verification also confirmed synthesized answers. Free capacity is not guaranteed. The video has no narration and runs at actual capture timing.
