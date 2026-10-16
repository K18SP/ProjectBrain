from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from falkordb import FalkorDB

from .schema import Entity, Link, ProjectData


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GraphStore:
    """FalkorDB is the source for project relationships and investigation memory."""

    def __init__(self) -> None:
        options = {
            "host": os.getenv("FALKORDB_HOST", "localhost"),
            "port": int(os.getenv("FALKORDB_PORT", "6379")),
        }
        if os.getenv("FALKORDB_PASSWORD"):
            options["password"] = os.environ["FALKORDB_PASSWORD"]
        self.db = FalkorDB(**options)
        self.graph = self.db.select_graph("projectbrain")

    def query(self, cypher: str, params: dict | None = None) -> list[list]:
        return self.graph.query(cypher, params=params or {}).result_set

    def ping(self) -> bool:
        self.query("RETURN 1")
        return True

    def import_project(self, data: ProjectData) -> dict:
        self.query(
            "MERGE (p:Project {id:$id}) SET p.name=$name, p.description=$description, p.updated_at=$now",
            {"id": data.project_id, "name": data.name, "description": data.description, "now": utc_now()},
        )
        for entity in data.entities:
            payload = entity.model_dump()
            payload["project_id"] = data.project_id
            payload["updated_at"] = entity.updated_at or utc_now()
            self.query(
                "MERGE (e:Entity {id:$id, project_id:$project_id}) "
                "SET e.kind=$kind, e.name=$name, e.status=$status, e.source=$source, "
                "e.url=$url, e.updated_at=$updated_at, e.description=$description, e.owner=$owner",
                payload,
            )
        for link in data.links:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", link.kind):
                raise ValueError("Invalid relationship kind")
            self.query(
                f"MATCH (a:Entity {{id:$source, project_id:$project_id}}), "
                f"(b:Entity {{id:$target, project_id:$project_id}}) "
                f"MERGE (a)-[r:{link.kind}]->(b) "
                "SET r.evidence=$evidence, r.confidence=$confidence",
                {**link.model_dump(), "project_id": data.project_id},
            )
        return {"project_id": data.project_id, "nodes": len(data.entities), "edges": len(data.links)}

    def projects(self) -> list[dict]:
        rows = self.query("MATCH (p:Project) RETURN p.id,p.name,p.description ORDER BY p.name")
        return [{"id": r[0], "name": r[1], "description": r[2]} for r in rows]

    def project(self, project_id: str) -> dict | None:
        rows = self.query("MATCH (p:Project {id:$id}) RETURN p.id,p.name,p.description", {"id": project_id})
        return {"id": rows[0][0], "name": rows[0][1], "description": rows[0][2]} if rows else None

    def entities(self, project_id: str, limit: int = 350) -> list[dict]:
        rows = self.query(
            "MATCH (e:Entity {project_id:$project_id}) "
            "RETURN e.id,e.kind,e.name,e.status,e.source,e.url,e.updated_at,e.description,e.owner "
            "ORDER BY e.kind,e.name LIMIT $limit",
            {"project_id": project_id, "limit": limit},
        )
        return [dict(zip(("id", "kind", "name", "status", "source", "url", "updated_at", "description", "owner"), r)) for r in rows]

    def links(self, project_id: str, limit: int = 800) -> list[dict]:
        rows = self.query(
            "MATCH (a:Entity {project_id:$project_id})-[r]->(b:Entity {project_id:$project_id}) "
            "RETURN a.id,b.id,type(r),r.evidence,r.confidence LIMIT $limit",
            {"project_id": project_id, "limit": limit},
        )
        return [dict(zip(("source", "target", "kind", "evidence", "confidence"), r)) for r in rows]

    def neighborhood(self, project_id: str, entity_id: str) -> list[dict]:
        rows = self.query(
            "MATCH (a:Entity {id:$id,project_id:$project_id})-[r]-(b:Entity {project_id:$project_id}) "
            "RETURN b.id,b.kind,b.name,b.status,b.url,b.description,b.owner,type(r),startNode(r).id,endNode(r).id,r.confidence "
            "LIMIT 100",
            {"id": entity_id, "project_id": project_id},
        )
        return [dict(zip(("id", "kind", "name", "status", "url", "description", "owner", "relationship", "source", "target", "confidence"), r)) for r in rows]

    def create_investigation(self, project_id: str, question: str, session_id: str) -> str:
        investigation_id = str(uuid4())
        self.query(
            "CREATE (i:Investigation {id:$id,project_id:$project_id,question:$question,"
            "session_id:$session_id,created_at:$created_at,status:'running'})",
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
                "MATCH (f:Finding {id:$finding_id}),(e:Entity {id:$entity_id}) "
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
            "RETURN f.id,f.agent,f.title,f.body,collect(e.id) ORDER BY f.created_at",
            {"id": investigation_id},
        )
        return [dict(zip(("id", "agent", "title", "body", "entity_ids"), r)) for r in rows]

    def create_proposal(self, investigation_id: str, title: str, description: str) -> dict:
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
        rows = self.query("MATCH (p:Proposal {id:$id}) RETURN p.status,p.title", {"id": proposal_id})
        if not rows:
            return None
        if rows[0][0] != "pending":
            return {"id": proposal_id, "status": rows[0][0], "title": rows[0][1]}
        status = "approved" if approved else "rejected"
        self.query("MATCH (p:Proposal {id:$id}) SET p.status=$status,p.decided_at=$now",
                   {"id": proposal_id, "status": status, "now": utc_now()})
        return {"id": proposal_id, "status": status, "title": rows[0][1]}

    def proposals(self, project_id: str) -> list[dict]:
        rows = self.query(
            "MATCH (i:Investigation {project_id:$project_id})-[:PROPOSED]->(p:Proposal) "
            "RETURN p.id,p.title,p.description,p.status,p.created_at ORDER BY p.created_at DESC LIMIT 30",
            {"project_id": project_id},
        )
        return [dict(zip(("id", "title", "description", "status", "created_at"), r)) for r in rows]
