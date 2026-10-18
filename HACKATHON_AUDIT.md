# Hackathon readiness review

Updated 18 October 2026 against https://www.wemakedevs.org/hackathons/falkordb . This is an engineering assessment, not organizer approval. Track focus points are not all mandatory eligibility rules.

## Track 1 implementation

| Capability | Evidence and limits |
|---|---|
| FalkorDB central | Projects, entities, typed relationships, findings, memory and approved tasks persist in FalkorDB. No mock fallback. |
| Connected reasoning | Bounded three-hop traversal, explicit issue dependencies and Python imports; candidate relationships labeled. |
| MCP tool use | Actual MCP SDK discovery/calls; free model chooses scoped search, traversal, confirmed-path and recall tools. Four-call budget. Provider failures fall back visibly. |
| Actions | Approval atomically creates a persistent local follow-up Task with investigation/evidence edges. Concurrent approval is tested for deduplication. No external issue creation. |
| Explanation | Evidence references, source links, connections between cited records, persisted tool trace. Reference validation is not a proof of every claim. |
| Memory | Lexical search across completed investigations, persisted answers, changed-source warnings. No semantic/procedural memory. |
| Shared state | Sequential specialist findings share one investigation graph. Not autonomous multi-agent coordination. |
| Dynamic sources | GitHub, Jira Cloud, documents and portable records; manual refresh. Live Jira ticket import and refresh succeeded locally. |
| Hosting | Authenticated free Embarko deployment with shared workspace sign-in. Public GitHub only; no Jira/file imports or GitHub token forwarded. Owner explicitly approved unencrypted free database connection for public data only. |

## Validation

38 automated tests passed, including database integration, project isolation, real MCP protocol use, model-selected tools, repeated/concurrent approval, stale memory, citation rejection, authentication and hosted private-import blocking. JavaScript syntax validation passed. Docker build and startup succeeded. Free model routing is fixed to openrouter/free with zero maximum token prices and no paid fallback.

Hosted smoke checks also verified a real public import (167 nodes, 251 edges), a model-selected MCP traversal, a model answer, and repeated approval creating one task. Unauthenticated requests returned 401; Jira and file imports returned 403.

## Remaining submission and production limits

- Participant must confirm event-period eligibility, registration, team size (up to four), and submit the entry before 18 October 2026, 11:59 PM IST. Signed-in organizer form and its additional fields remain unverified.
- Submission package should include repository, working demo recording, local setup, and reviewer access to hosting. Deployment alone is not submission.
- AI coding assistance is disclosed; participant must understand and explain the work.
- Track 1 is the recommended entry. Tracks 2 and 3 have partial foundations only; do not claim all their focus areas are complete.
- Production use still needs individual authorization, encrypted database transport, durable jobs, transactional refresh, backups and operational monitoring. Shared password access is not tenant isolation.
- Free AI quota and anonymous GitHub rate limits can restrict demonstrations; visible evidence fallback is intentional.

## Delivered artifacts

`docs/projectbrain-demo.mp4` records the working UI, evidence fallback, task approval, created task and saved history. The final capture includes model-selected MCP calls; synthesis fell back to source evidence. Earlier live checks also verified synthesized answers. `docs/SUBMISSION.md` contains the entry draft and local setup. Registration and organizer submission remain external steps.


## Response-quality follow-up

The previous recording exposed weak synthesis and verbose fallback, so feature completion should not be mistaken for answer quality. The response flow now separates individual source findings, deduplicates file records, normalizes citation ranges while rejecting unknown references, and avoids copying old answers unless history was requested. Fallbacks are short labeled excerpts. The UI formats bold/code safely and keeps coverage details expandable. MCP follow-up schemas enumerate observed record IDs. These changes improve clarity; free model reliability and factual support still need review on each answer.

See `docs/SUBMISSION.md` for the deadline and the outstanding registration, reviewer-access and final submission steps. The existing video predates these response changes; a stronger recording is recommended before submitting.

Validation after the response update: 40 tests passed. Two live repository questions returned model answers; the API-flow question successfully used MCP search and traversal. Spot-checking confirmed the route and service-call evidence, but the model also inferred startup initialization from a partial main.py excerpt. Citation validity alone is not factual verification; this remains a model-quality limitation.
