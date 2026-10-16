from __future__ import annotations

from pydantic import BaseModel, Field


class Entity(BaseModel):
    id: str
    kind: str
    name: str
    status: str = ""
    source: str = "demo"
    url: str = ""
    updated_at: str = ""
    description: str = ""
    owner: str = ""


class Link(BaseModel):
    source: str
    target: str
    kind: str
    evidence: str = ""
    confidence: str = "confirmed"


class ProjectData(BaseModel):
    project_id: str
    name: str
    description: str = ""
    entities: list[Entity]
    links: list[Link]


class AskRequest(BaseModel):
    project_id: str = "atlas"
    question: str = Field(min_length=3, max_length=1000)
    session_id: str = "default"


class ImportRequest(BaseModel):
    url: str


class ProposalRequest(BaseModel):
    investigation_id: str
    title: str = Field(min_length=3, max_length=200)
    description: str = ""


class ApprovalRequest(BaseModel):
    approved: bool
