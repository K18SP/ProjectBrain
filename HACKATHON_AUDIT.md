# Hackathon readiness review

Checked 17 October 2026 against https://www.wemakedevs.org/hackathons/falkordb . This is an engineering assessment, not organizer approval. Track focus points are not all stated as mandatory eligibility rules.

## Rules and submission

- FalkorDB must be central: met technically. Records, relationships, traversal and investigation memory use the live database; no mock fallback.
- Main submission work must be new during the event: local commits indicate event-period implementation; the participant must confirm eligibility and disclose reused infrastructure.
- Solo or up to four participants: registration/team status unverified.
- Deadline: 18 October 2026, 11:59 PM IST. Submission status unverified.
- Deployment is preferred; a local submission requires setup instructions and a working demo video. Setup instructions exist. Public deployment and demo video are outstanding.
- Coding assistants are allowed, with participant responsibility: assistance is disclosed in README; the participant still needs to review and explain the implementation.

## Product evidence

| Capability | Assessment |
|---|---|
| Connected reasoning | Implemented with bounded FalkorDB traversal, explicit issue dependencies and Python import links. Not exhaustive program analysis. |
| Cross-session memory | Answers and findings persist; previous investigations can be retrieved. Relevance is lexical, not a complete memory system. |
| Shared agent state | Specialist functions read persisted findings. They are sequential rules, not autonomous agents with robust handoffs. |
| People, projects, decisions | Assignees and work records import dynamically. Decisions need explicit uploaded records; automatic decision extraction is absent. |
| Explanation paths | Source links, file line references and explored relationships are shown. Explored paths are not proof of causality. |
| Actions | Evidence-specific local proposals can be approved, but approval only changes a status field. It does not create a work item or execute a GitHub/Jira action. |
| MCP tools | Not implemented. Graph access is through internal Python tools. |
| Advanced memory/concurrency | No semantic/procedural memory, tenant authentication, or concurrency validation. |
| Company knowledge freshness | Manual source refresh and file replacement work. Native chat connectors and automatic synchronization are absent. |

Track 1 is the closest fit, but MCP tool selection and a convincing graph-driven action demo remain gaps. Tracks 2 and 3 have partial foundations only. Do not claim all conditions or focus areas are satisfied.

## Validation and next demonstration

Regression tests cover missing README ingestion, Python import links, label-only answers, file refresh, source isolation, and persisted evidence. The repository from the reported failure was reimported with real code. Jira is tested with simulated responses; live credentials are still absent. Free-only OpenRouter synthesis was subsequently configured and verified with a live repository question. Paid fallback is disabled and tested.

Before submission, demonstrate a real dependency investigation with an approved local action and a later-session recall, record that workflow, and complete the registration/submission form. Production work remains: authentication, permissions, durable import jobs, transactional refresh, and operational monitoring.

## Updated implementation checklist after free-model integration

Review baseline: commit `0dd476b`, 17 October 2026. The last completed suite passed 28 tests; this documentation review did not rerun unchanged tests. Live health check passed. Two imported projects and 12 completed investigations were present. One approved proposal exists, but this is not evidence of action execution. No recording or deployment artifact was found in the repository; an externally created recording is unverified.

The priorities below are engineering recommendations for a convincing Track 1 entry, not additional organizer rules.

| Priority | Remaining work | Completion evidence |
|---|---|---|
| 1 | Give the agent bounded, project-scoped MCP tools for search, neighborhood traversal, dependency/impact paths and memory lookup. Add model-driven tool selection with a call budget. | A question causes the model to select and call graph tools; the trace records tool inputs and results. Confirm the chosen free model supports tool calling, and preserve free-only routing. |
| 1 | Make an approved proposal perform a concrete local action, such as creating a persistent follow-up work item linked to the investigation and cited records. External issue creation is optional. | Approval creates one work item; repeated approval does not duplicate it; failure is visible; the user can inspect the evidence and outcome. |
| 1 | Validate generated citations and display the exact supporting path rather than all explored edges. | Unknown citation IDs are rejected or flagged, candidate edges remain labeled, and unsupported assertions are not presented as established facts. |
| 1 | Demonstrate a question that needs multiple connected records. A README summary alone does not establish the graph's value. | Use actual imported records to show dependency/impact, ownership and supporting documentation; compare what is known before and after a source update. |
| 1 | Record and package the demonstration; confirm registration and submission fields in the signed-in organizer panel. | Working demo video, repository link, reproducible setup and submitted entry. Public hosting can be added if feasible. |
| 2 | Improve memory retrieval beyond overlap with eight recent questions, and validate recall in a new session. | A related earlier investigation is found and cited; changed source evidence takes precedence over stale conclusions. |
| 2 | Verify Jira with real credentials if the demo claims live Jira support. | A ticket/project imports and refreshes successfully, with correct owners and link directions. Otherwise label Jira as connector-tested only. |
| 2 | Exercise a clean setup and free-model unavailability path. | A new installation starts empty, imports a source and answers; unavailable free AI visibly falls back without a paid request. |

## Scope decisions

- Track 1: closest current fit; central graph retrieval works, but autonomous tool use and executed actions remain incomplete.
- Track 2: persistence is implemented; separate tenant memory, semantic/procedural memory, robust handoffs and concurrent operation are not. Do not present sequential specialist functions as fully autonomous agents.
- Track 3: docs, tickets and code can share a project graph; chat integration, automatic decision capture and continuous updates remain incomplete.
- Production hardening is separate from entry eligibility: authentication, authorization, durable jobs, transactional ingestion and monitoring remain necessary before a public company-data deployment.
- A blog post is optional for the separate blog prize. No judging percentages or guaranteed winning formula were published on the reviewed public page.
- The public registration panel did not expose signed-in submission fields during this review. Its additional requirements, if any, remain unverified.

## Suggested recording sequence

1. Show the empty or user-imported project and its source timestamp.
2. Import a real repository plus a relevant ticket or decision document.
3. Ask a dependency/impact question supported by those records.
4. Show graph queries, source references, and confirmed versus candidate relationships.
5. Execute and inspect an approved local follow-up once action execution is implemented.
6. Start a fresh session and retrieve the earlier investigation.
7. Refresh changed source content and show the updated evidence.
8. State bounded import coverage and remaining limitations accurately.
