from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Entity(BaseModel):
    id: str
    kind: str
    name: str
    status: str = ""
    source: str = "import"
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
    source_id: str = ""
    source_kind: str = ""
    source_url: str = ""
    source_name: str = ""
    warnings: list[str] = Field(default_factory=list)
    partial: bool = False


class AskRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=250)
    question: str = Field(min_length=3, max_length=1000)
    session_id: str = "default"


class ImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    project_id: str | None = None


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if len(value.strip()) < 2:
            raise ValueError("Use a project name with at least two characters")
        return value.strip()


class JiraRequest(BaseModel):
    reference: str = Field(min_length=2, max_length=2000)
    project_id: str | None = None


class RecordsRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    entities: list[Entity] = Field(min_length=1, max_length=2000)
    links: list[Link] = Field(default_factory=list, max_length=8000)


class SyncRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=250)
    source_id: str = Field(min_length=1, max_length=250)


class ProposalRequest(BaseModel):
    investigation_id: str
    title: str = Field(min_length=3, max_length=200)
    description: str = ""


class ApprovalRequest(BaseModel):
    approved: bool
