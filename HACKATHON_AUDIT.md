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
| Actions | Evidence-specific local follow-up proposals can be approved. No GitHub/Jira write action is executed. |
| MCP tools | Not implemented. Graph access is through internal Python tools. |
| Advanced memory/concurrency | No semantic/procedural memory, tenant authentication, or concurrency validation. |
| Company knowledge freshness | Manual source refresh and file replacement work. Native chat connectors and automatic synchronization are absent. |

Track 1 is the closest fit, but MCP tool selection and a convincing graph-driven action demo remain gaps. Tracks 2 and 3 have partial foundations only. Do not claim all conditions or focus areas are satisfied.

## Validation and next demonstration

Regression tests cover missing README ingestion, Python import links, label-only answers, file refresh, source isolation, and persisted evidence. The repository from the reported failure was reimported with real code. Jira is tested with simulated responses; live credentials are still absent. AI synthesis is not validated without a configured provider key.

Before submission, configure and verify synthesis, demonstrate a real dependency investigation with an approved local action and a later-session recall, record that workflow, and complete the registration/submission form. Production work remains: authentication, permissions, durable import jobs, transactional refresh, and operational monitoring.
