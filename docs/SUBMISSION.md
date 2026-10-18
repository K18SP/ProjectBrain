# ProjectBrain — submission draft

Track: Agents That Act on Connected Data (Track 1).
Repository: https://github.com/K18SP/ProjectBrain
Demo app: https://projectbrain-k18sp.embarko.app (reviewer credentials supplied privately).

ProjectBrain helps developers investigate a project across code, work items, people, and previous decisions. Rather than treating each record as an isolated text chunk, it follows typed FalkorDB relationships, selects bounded MCP tools, and attaches source references to answers. Approved follow-ups become persistent tasks connected to the investigation and its evidence.

Architecture: browser → FastAPI → free-model MCP tool selection + graph investigation → FalkorDB → cited answer → approved local task. Source adapters normalize GitHub, Jira and documents. Investigations survive browser sessions and older memory is flagged when source versions change.

FalkorDB is the core storage and traversal system, not an optional integration. The demo can explain which relationship is confirmed, inspect supporting records, and revisit an investigation later. The hosted demo is restricted to public GitHub data; local Jira import and refresh were separately verified.

Recording: [projectbrain-demo.mp4](projectbrain-demo.mp4). The recording covers investigation, approved action and fresh-session history; source replacement and stale-memory handling are additionally covered by integration tests.

## Demonstration sequence

1. Select a real imported repository and inspect source coverage.
2. Ask how its API connects to its retrieval service.
3. Inspect source references, graph connections and model tool trace.
4. Suggest and approve a follow-up; open the resulting persistent task.
5. Open a fresh session and inspect saved history.
6. Refresh a source or replace a local document; distinguish stale memory from current records.

## Reproducible local setup

Copy `.env.example` to `.env`, optionally configure an OpenRouter key, then run `docker compose up --build`. Open http://localhost:8000. Add a source; there is no demo-seeding route. Only free OpenRouter routing is supported. Without free capacity the app returns explicit source evidence.

## Honest scope and disclosure

This is a hackathon application, not a complete enterprise platform. Imports and graph searches are bounded. Memory is lexical; specialist functions are sequential. Approval creates local tasks only. Hosting uses shared authentication and an owner-approved unencrypted database link for public-source data. Private source imports are disabled there.

AI coding assistance was used. The participant should review and explain the design and tests. Confirm registration, eligibility, reviewer access and the organizer’s final submission fields before submitting. This file is a draft, not confirmation that an entry was submitted.

Recording note: the final recording shows source-evidence fallback because free synthesis did not return an acceptable answer during capture. The recording includes model-selected MCP search and a rejected traversal request using an invalid record ID; earlier live verification also confirmed synthesized answers. Free capacity is not guaranteed. The video has no narration and runs at actual capture timing.


## Submission checklist — checked 18 October 2026

Official page: https://www.wemakedevs.org/hackathons/falkordb
Deadline: 18 October 2026, 11:59 PM IST.

Ready: public GitHub repository, deployed app, local setup, demo recording, architecture description, AI-assistance disclosure, and Track 1 core features (FalkorDB context, graph tools/MCP, evidence-linked local action).

Still required from the participant:
- Sign in on the official page and confirm registration and team details (solo or up to four).
- Confirm the main submission and FalkorDB implementation were built during the event.
- Select Track 1 and fill in every field in the signed-in submission panel. Exact fields are not visible on the public page and remain unverified.
- Include repository/deployment links and privately provide reviewer access. Verify reviewers can open the app and video without your local computer.
- Submit the entry and retain its confirmation before the deadline. No submission confirmation has been verified.

Quality recommendation, not an additional stated eligibility rule: replace the older demo recording with a clean explanation of the improved answer flow, a successful multi-hop investigation, an approved task and later recall. The existing video shows fallback behavior and a rejected model tool call; it is a weak showcase even though the app runs.

A blog is optional for the separate blog prize. Full semantic/procedural memory, tenant isolation and company chat ingestion are not required to enter Track 1; do not claim Tracks 2/3 are complete. This is a hackathon prototype with production limitations, not a fully hardened enterprise platform.

Response evaluation: 40 tests passed and two live questions returned substantially clearer model answers. Exact citation IDs are checked, but full claim-level verification is not implemented; partial-code inferences remain a limitation to disclose.
