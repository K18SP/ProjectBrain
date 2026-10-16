from __future__ import annotations

import os
import re
from collections import deque

import httpx

from .graph import GraphStore


STOP_WORDS = {"what", "when", "where", "which", "who", "why", "how", "can", "could", "would", "should",
              "does", "do", "did", "are", "is", "our", "the", "this", "that", "with", "from", "about",
              "project", "please", "show", "tell", "me", "for", "and", "any", "all", "will", "was"}


def terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2 and word not in STOP_WORDS}


def rank_entities(question: str, entities: list[dict]) -> list[dict]:
    query_terms = terms(question)
    scored = []
    for entity in entities:
        name_terms = terms(entity["name"])
        other_terms = terms((entity.get("description") or "") + " " + (entity.get("status") or ""))
        score = 4 * len(query_terms & name_terms) + len(query_terms & other_terms)
        if any(word in question.lower() for word in ("release", "launch", "deadline", "ship")) and entity["kind"] == "Milestone":
            score += 3
        if any(word in question.lower() for word in ("block", "risk", "delay")) and entity["status"] == "blocked":
            score += 2
        if score:
            scored.append((score, entity))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
    return [entity for _, entity in scored[:5]]


def evidence_paths(store: GraphStore, project_id: str, seeds: list[dict], max_depth: int = 3) -> tuple[list[dict], list[dict]]:
    """Every hop comes from a FalkorDB Cypher query, including cross-agent context."""
    visited = {entity["id"]: entity for entity in seeds}
    queue = deque([(entity["id"], 0) for entity in seeds])
    links: dict[tuple[str, str, str], dict] = {}
    while queue and len(visited) < 45:
        entity_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for row in store.neighborhood(project_id, entity_id):
            key = (row["source"], row["target"], row["relationship"])
            links[key] = {"source": row["source"], "target": row["target"], "kind": row["relationship"]}
            if row["id"] not in visited:
                visited[row["id"]] = {k: row.get(k) or "" for k in
                                      ("id", "kind", "name", "status", "url", "description", "owner")}
                queue.append((row["id"], depth + 1))
    return list(visited.values()), list(links.values())


def _finding_for(agent: str, question: str, nodes: list[dict], edges: list[dict]) -> tuple[str, str, list[str]] | None:
    by_id = {n["id"]: n for n in nodes}
    if agent == "Dependency agent":
        blockers = [e for e in edges if e["kind"] in {"BLOCKS", "DEPENDS_ON", "REQUIRED_FOR"}]
        if blockers:
            details = [f"{by_id[e['source']]['name']} {e['kind'].lower().replace('_', ' ')} {by_id[e['target']]['name']}" for e in blockers[:5] if e["source"] in by_id and e["target"] in by_id]
            ids = list({x for e in blockers[:5] for x in (e["source"], e["target"])})
            return "Dependency chain", "; ".join(details), ids
    if agent == "Ownership agent":
        owned = [n for n in nodes if n.get("owner")]
        if owned:
            details = [f"{n['owner']} owns {n['name']}" for n in owned[:4]]
            return "Responsible people", "; ".join(details), [n["id"] for n in owned[:4]]
    if agent == "Knowledge agent":
        knowledge = [n for n in nodes if n["kind"] in {"Decision", "Document", "Investigation"}]
        if knowledge:
            return "Recorded context", "; ".join(f"{n['name']}: {n.get('description','')[:140]}" for n in knowledge[:3]), [n["id"] for n in knowledge[:3]]
    return None


async def _llm_answer(question: str, findings: list[dict], previous: list[dict]) -> str | None:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    facts = "\n".join(f"- {f['agent']}: {f['body']} [entities: {', '.join(f['entity_ids'])}]" for f in findings)
    memories = "\n".join(f"- {m['question']}: {m['answer'][:250]}" for m in previous[:2])
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), "temperature": 0.1,
                      "messages": [
                          {"role": "system", "content": "You are ProjectBrain. Answer only from the supplied findings. Explain the connection path, distinguish a blocker from a proven cause, mention missing data, and cite supporting entity IDs in parentheses. Do not invent deadlines or actions."},
                          {"role": "user", "content": f"Question: {question}\nFindings:\n{facts}\nPrevious investigations:\n{memories}"},
                      ]},
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError):
        return None


async def investigate(store: GraphStore, project_id: str, question: str, session_id: str) -> dict:
    entities = store.entities(project_id)
    seeds = rank_entities(question, entities)
    if not seeds:
        return {"id": None, "answer": "I couldn't identify a matching project record. Try naming a task, person, service, or milestone that exists in the connected sources.",
                "findings": [], "nodes": [], "edges": [], "previous": [], "suggestions": []}
    investigation_id = store.create_investigation(project_id, question, session_id)
    nodes, edges = evidence_paths(store, project_id, seeds)
    for agent in ("Dependency agent", "Ownership agent", "Knowledge agent"):
        finding = _finding_for(agent, question, nodes, edges)
        if finding:
            store.save_finding(investigation_id, agent, *finding)
    previous = store.recent_investigations(project_id, investigation_id)
    related_previous = [p for p in previous if terms(question) & terms(p["question"])]
    if related_previous:
        store.save_finding(investigation_id, "Memory agent", "Previous investigation",
                           f"Earlier question: {related_previous[0]['question']}. Earlier answer: {related_previous[0]['answer'][:300]}", [])
    findings = store.findings(investigation_id)
    answer = await _llm_answer(question, findings, related_previous)
    if not answer:
        if findings:
            answer = "Based on the connected records: " + " ".join(f["body"] + "." for f in findings if f["agent"] != "Memory agent")
            if related_previous:
                answer += f" A previous investigation also covered this topic: {related_previous[0]['question']}."
            answer += " These links show impact and ownership; they do not by themselves prove a root cause."
        else:
            answer = "I found related records but no confirmed dependency, owner, or decision path. The available sources are not enough to draw a stronger conclusion."
    store.complete_investigation(investigation_id, answer)
    return {"id": investigation_id, "answer": answer, "findings": findings, "nodes": nodes,
            "edges": edges, "previous": related_previous[:3],
            "suggestions": ["Create a follow-up task", "Review the source records"] if findings else []}
