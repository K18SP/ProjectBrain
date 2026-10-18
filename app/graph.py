from __future__ import annotations

import os
import re
import json
import threading
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from falkordb import FalkorDB

from .schema import Entity, Link, ProjectData

_IMPORT_LOCK = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GraphStore:
    """FalkorDB is the source for project relationships and investigation memory."""

    def __init__(self) -> None:
        options = {
            "host": os.getenv("FALKORDB_HOST", "localhost"),
            "port": int(os.getenv("FALKORDB_PORT", "6379")),
            "socket_connect_timeout": 3,
            "socket_timeout": 15,
        }
        if os.getenv("FALKORDB_USERNAME"):
            options["username"] = os.environ["FALKORDB_USERNAME"]
        if os.getenv("FALKORDB_SSL", "false").lower() == "true":
            options["ssl"] = True
            options["ssl_cert_reqs"] = "required"
        if os.getenv("FALKORDB_PASSWORD"):
            options["password"] = os.environ["FALKORDB_PASSWORD"]
        self.db = FalkorDB(**options)
        self.graph = self.db.select_graph(os.getenv("FALKORDB_GRAPH", "projectbrain"))

    def query(self, cypher: str, params: dict | None = None) -> list[list]:
        return self.graph.query(cypher, params=params or {}).result_set

    def ping(self) -> bool:
        self.query("RETURN 1")
        return True

    def import_project(self, data: ProjectData) -> dict:
        # One writer per process prevents two refreshes from interleaving source snapshots.
        with _IMPORT_LOCK:
            return self._import_project(data)

    def _import_project(self, data: ProjectData) -> dict:
        self.query(
            "MERGE (p:Project {id:$id}) SET p.name=$name, p.description=$description, p.updated_at=$now",
            {"id": data.project_id, "name": data.name, "description": data.description, "now": utc_now()},
        )
        source_id = data.source_id or f"import:{data.project_id}"
        grouped = defaultdict(list)
        for link in data.links:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", link.kind):
                raise ValueError("Invalid relationship kind")
            grouped[link.kind].append(link.model_dump())
        payload = [entity.model_dump() for entity in data.entities]
        for offset in range(0, len(payload), 200):
            self.query(
                "UNWIND $entities AS item MERGE (e:Entity {id:item.id,project_id:$project_id}) "
                "SET e.kind=item.kind,e.name=item.name,e.status=item.status,e.source=item.source,"
                "e.url=item.url,e.updated_at=item.updated_at,e.description=item.description,e.owner=item.owner,"
                "e.source_id=$source_id,e.archived=false",
                {"entities": payload[offset:offset + 200], "project_id": data.project_id, "source_id": source_id},
            )
        ids = [entity.id for entity in data.entities]
        if not data.partial:
            self.query("MATCH (e:Entity {project_id:$project_id,source_id:$source_id}) "
                       "WHERE NOT e.id IN $ids SET e.archived=true",
                       {"project_id": data.project_id, "source_id": source_id, "ids": ids})
        # On partial imports, keep links for records outside the fetched window.
        self.query("MATCH (a:Entity {project_id:$project_id})-[r]->(b:Entity {project_id:$project_id}) "
                   "WHERE r.source_id=$source_id AND ($partial=false OR "
                   "(a.id IN $ids AND NOT a.kind IN ['Person','Repository','Project']) OR "
                   "(b.id IN $ids AND NOT b.kind IN ['Person','Repository','Project'])) DELETE r",
                   {"project_id": data.project_id, "source_id": source_id, "ids": ids, "partial": data.partial})
        for kind, links in grouped.items():
            for offset in range(0, len(links), 200):
                self.query(
                    "UNWIND $links AS item MATCH (a:Entity {id:item.source,project_id:$project_id}),"
                    "(b:Entity {id:item.target,project_id:$project_id}) "
                    f"MERGE (a)-[r:{kind} {{source_id:$source_id}}]->(b) "
                    "SET r.evidence=item.evidence,r.confidence=item.confidence",
                    {"links": links[offset:offset + 200], "project_id": data.project_id, "source_id": source_id})
        self.query("MERGE (s:Source {id:$id,project_id:$project_id}) "
                   "SET s.kind=$kind,s.name=$name,s.url=$url,s.synced_at=$now,s.record_count=$count,"
                   "s.partial=$partial,s.warnings=$warnings",
                   {"id": source_id, "project_id": data.project_id, "kind": data.source_kind or "records",
                    "name": data.source_name or data.name, "url": data.source_url, "now": utc_now(),
                    "count": len(data.entities), "partial": data.partial, "warnings": json.dumps(data.warnings)})
        self.connect_mentions(data.project_id)
        return {"project_id": data.project_id, "nodes": len(data.entities), "edges": len(data.links),
                "source_id": source_id, "warnings": data.warnings, "partial": data.partial}

    def sources(self, project_id: str) -> list[dict]:
        rows = self.query("MATCH (s:Source {project_id:$project_id}) "
                          "RETURN s.id,s.kind,s.name,s.url,s.synced_at,s.record_count,s.partial,s.warnings ORDER BY s.name",
                          {"project_id": project_id})
        result = [dict(zip(("id", "kind", "name", "url", "synced_at", "record_count", "partial", "warnings"), row)) for row in rows]
        for item in result:
            item["warnings"] = json.loads(item["warnings"] or "[]")
        return result

    def connect_mentions(self, project_id: str) -> None:
        """Cross-source mentions are candidates, never inferred ownership or blockers."""
        nodes = self.entities(project_id, limit=5000)
        references = defaultdict(list)
        for node in nodes:
            if re.match(r"^[A-Z][A-Z0-9_]*-\d+\b", node["name"]):
                references[node["name"].split()[0]].append(node)
        links = []
        for node in nodes:
            if not node.get("description"):
                continue
            for token in set(re.findall(r"\b[A-Z][A-Z0-9_]*-\d+\b", node["description"])):
                for target in references[token]:
                    if node.get("source_id") != target.get("source_id"):
                        links.append({"source": node["id"], "target": target["id"], "evidence": token})
        self.query("MATCH (a:Entity {project_id:$project_id})-[r:MENTIONS]->(b:Entity {project_id:$project_id}) "
                   "WHERE r.source_id='cross-source' DELETE r", {"project_id": project_id})
        for offset in range(0, len(links), 200):
            self.query("UNWIND $links AS item MATCH (a:Entity {id:item.source,project_id:$project_id}),"
                       "(b:Entity {id:item.target,project_id:$project_id}) "
                       "MERGE (a)-[r:MENTIONS {source_id:'cross-source'}]->(b) "
                       "SET r.confidence='candidate',r.evidence=item.evidence",
                       {"project_id": project_id, "links": links[offset:offset + 200]})

    def projects(self) -> list[dict]:
        rows = self.query("MATCH (p:Project) RETURN p.id,p.name,p.description ORDER BY p.name")
        return [{"id": r[0], "name": r[1], "description": r[2]} for r in rows]

    def project(self, project_id: str) -> dict | None:
        rows = self.query("MATCH (p:Project {id:$id}) RETURN p.id,p.name,p.description", {"id": project_id})
        return {"id": rows[0][0], "name": rows[0][1], "description": rows[0][2]} if rows else None

    def entities(self, project_id: str, limit: int = 5000) -> list[dict]:
        rows = self.query(
            "MATCH (e:Entity {project_id:$project_id}) WHERE coalesce(e.archived,false)=false "
            "RETURN e.id,e.kind,e.name,e.status,e.source,e.url,e.updated_at,e.description,e.owner,e.source_id "
            "ORDER BY e.kind,e.name LIMIT $limit",
            {"project_id": project_id, "limit": limit},
        )
        return [dict(zip(("id", "kind", "name", "status", "source", "url", "updated_at", "description", "owner", "source_id"), r)) for r in rows]

    def links(self, project_id: str, limit: int = 10000) -> list[dict]:
        rows = self.query(
            "MATCH (a:Entity {project_id:$project_id})-[r]->(b:Entity {project_id:$project_id}) "
            "WHERE coalesce(a.archived,false)=false AND coalesce(b.archived,false)=false "
            "RETURN a.id,b.id,type(r),r.evidence,r.confidence LIMIT $limit",
            {"project_id": project_id, "limit": limit},
        )
        return [dict(zip(("source", "target", "kind", "evidence", "confidence"), r)) for r in rows]

    def neighborhood(self, project_id: str, entity_id: str) -> list[dict]:
        rows = self.query(
            "MATCH (a:Entity {id:$id,project_id:$project_id})-[r]-(b:Entity {project_id:$project_id}) "
            "WHERE coalesce(b.archived,false)=false "
            "RETURN b.id,b.kind,b.name,b.status,b.url,b.description,b.owner,type(r),startNode(r).id,endNode(r).id,r.confidence "
            "LIMIT 100",
            {"id": entity_id, "project_id": project_id},
        )
        return [dict(zip(("id", "kind", "name", "status", "url", "description", "owner", "relationship", "source", "target", "confidence"), r)) for r in rows]

    def create_investigation(self, project_id: str, question: str, session_id: str) -> str:
        investigation_id = str(uuid4())
        self.query(
            "MATCH (p:Project {id:$project_id}) CREATE (i:Investigation {id:$id,project_id:$project_id,question:$question,"
            "session_id:$session_id,source_version:coalesce(p.updated_at,''),created_at:$created_at,status:'running'})",
            {"id": investigation_id, "project_id": project_id, "question": question,
             "session_id": session_id, "created_at": utc_now()},
        )
        return investigation_id

    def save_finding(self, investigation_id: str, agent: str, title: str, body: str, entity_ids: list[str]) -> None:
        finding_id = str(uuid4())
        self.query(
            "MATCH (i:Investigation {id:$investigation_id}) "
            "CREATE (f:Finding {id:$id,agent:$agent,title:$title,body:$body,created_at:$created_at}) "
            "CREATE (i)-[:HAS_FINDING]->(f)",
            {"investigation_id": investigation_id, "id": finding_id, "agent": agent,
             "title": title, "body": body, "created_at": utc_now()},
        )
        for entity_id in entity_ids:
            self.query(
                "MATCH (i:Investigation)-[:HAS_FINDING]->(f:Finding {id:$finding_id}),(e:Entity {id:$entity_id}) "
                "WHERE i.project_id=e.project_id "
                "MERGE (f)-[:SUPPORTED_BY]->(e)",
                {"finding_id": finding_id, "entity_id": entity_id},
            )

    def complete_investigation(self, investigation_id: str, answer: str) -> None:
        self.query(
            "MATCH (i:Investigation {id:$id}) SET i.status='complete',i.answer=$answer,i.completed_at=$now",
            {"id": investigation_id, "answer": answer, "now": utc_now()},
        )

    def recent_investigations(self, project_id: str, exclude_id: str = "") -> list[dict]:
        rows = self.query(
            "MATCH (i:Investigation {project_id:$project_id}) WHERE i.status='complete' AND i.id <> $exclude_id "
            "RETURN i.id,i.question,i.answer,i.created_at ORDER BY i.created_at DESC LIMIT 8",
            {"project_id": project_id, "exclude_id": exclude_id},
        )
        return [dict(zip(("id", "question", "answer", "created_at"), r)) for r in rows]

    def findings(self, investigation_id: str) -> list[dict]:
        rows = self.query(
            "MATCH (i:Investigation {id:$id})-[:HAS_FINDING]->(f:Finding) "
            "OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(e:Entity) "
            "RETURN f.id,f.agent,f.title,f.body,collect(e.id),f.created_at AS created_at ORDER BY created_at",
            {"id": investigation_id},
        )
        return [dict(zip(("id", "agent", "title", "body", "entity_ids"), r)) for r in rows]

    def create_proposal(self, investigation_id: str, title: str, description: str) -> dict:
        if not self.query("MATCH (i:Investigation {id:$id,status:'complete'}) RETURN i.id", {"id": investigation_id}):
            raise ValueError("A completed investigation is required before proposing an action")
        proposal_id = str(uuid4())
        self.query(
            "MATCH (i:Investigation {id:$investigation_id}) "
            "CREATE (p:Proposal {id:$id,title:$title,description:$description,status:'pending',created_at:$now}) "
            "CREATE (i)-[:PROPOSED]->(p)",
            {"investigation_id": investigation_id, "id": proposal_id, "title": title,
             "description": description, "now": utc_now()},
        )
        return {"id": proposal_id, "title": title, "description": description, "status": "pending", "destination": "ProjectBrain"}

    def decide_proposal(self, proposal_id: str, approved: bool) -> dict | None:
        # One query atomically applies the decision and action; stable task ID makes retries idempotent.
        if approved:
            rows = self.query(
                "MATCH (i:Investigation)-[:PROPOSED]->(p:Proposal {id:$id}) "
                "WHERE p.status IN ['pending','approved'] "
                "MERGE (t:Entity {id:$task_id,project_id:i.project_id}) "
                "ON CREATE SET t.kind='Task',t.name=p.title,t.description=p.description,t.status='open',"
                "t.source='ProjectBrain',t.source_id='local:actions',t.owner='',t.url='',t.archived=false,t.updated_at=$now "
                "SET p.status='approved',p.task_id=t.id,p.executed_at=$now,p.decided_at=$now "
                "MERGE (p)-[:CREATED]->(t) MERGE (t)-[:FOLLOWS_UP]->(i) "
                "WITH i,p,t OPTIONAL MATCH (i)-[:HAS_FINDING]->(:Finding)-[:SUPPORTED_BY]->(e:Entity) "
                "WHERE e.project_id=i.project_id "
                "WITH p,t,collect(DISTINCT e) AS evidence "
                "FOREACH (e IN evidence | MERGE (t)-[:BASED_ON]->(e)) "
                "RETURN p.status,p.title,t.id",
                {"id": proposal_id, "task_id": "followup:" + proposal_id, "now": utc_now()})
        else:
            rows = self.query("MATCH (p:Proposal {id:$id}) WHERE p.status='pending' "
                              "SET p.status='rejected',p.decided_at=$now RETURN p.status,p.title,p.task_id",
                              {"id": proposal_id, "now": utc_now()})
        if not rows:
            rows = self.query("MATCH (p:Proposal {id:$id}) RETURN p.status,p.title,p.task_id", {"id": proposal_id})
        return {"id": proposal_id, "status": rows[0][0], "title": rows[0][1], "task_id": rows[0][2]} if rows else None

    def search_memory(self, project_id: str, question: str, exclude_id: str = "") -> list[dict]:
        tokens = [word for word in re.findall(r"[a-z0-9]+", question.lower()) if len(word) > 3
                  and word not in {'what','when','where','which','about','before','previous','earlier','remember','time','last','learn','learned'}][:20]
        rows = self.query(
            "MATCH (p:Project {id:$project_id}),(i:Investigation {project_id:$project_id,status:'complete'}) "
            "WHERE i.id <> $exclude_id AND (size($tokens)=0 OR any(term IN $tokens WHERE "
            "toLower(i.question) CONTAINS term OR toLower(i.answer) CONTAINS term)) "
            "RETURN i.id,i.question,i.answer,i.created_at,coalesce(i.source_version,'')<>coalesce(p.updated_at,'') "
            "ORDER BY i.created_at DESC LIMIT 20", {"project_id": project_id,"exclude_id": exclude_id,"tokens": tokens})
        return [dict(zip(('id','question','answer','created_at','stale'), row)) for row in rows]

    def save_trace(self, investigation_id: str, trace: list[dict], citations: list[str]) -> None:
        self.query("MATCH (i:Investigation {id:$id}) SET i.tool_trace=$trace,i.citations=$citations",
                   {"id": investigation_id,"trace": json.dumps(trace),"citations": json.dumps(citations)})

    def proposals(self, project_id: str) -> list[dict]:
        rows = self.query(
            "MATCH (i:Investigation {project_id:$project_id})-[:PROPOSED]->(p:Proposal) "
            "RETURN p.id,p.title,p.description,p.status,p.created_at,p.task_id ORDER BY p.created_at DESC LIMIT 30",
            {"project_id": project_id},
        )
        return [dict(zip(("id", "title", "description", "status", "created_at", "task_id"), r)) for r in rows]
