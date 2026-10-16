from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from docx import Document
from pypdf import PdfReader

from .schema import Entity, Link, ProjectData


MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}


def extract_document(filename: str, payload: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Supported formats: TXT, Markdown, PDF, and DOCX")
    if not payload or len(payload) > MAX_DOCUMENT_BYTES:
        raise ValueError("Upload a non-empty document smaller than 5 MB")
    if suffix in {".txt", ".md"}:
        return payload.decode("utf-8", errors="replace")
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(payload)).pages[:40])
    return "\n".join(p.text for p in Document(BytesIO(payload)).paragraphs)


def document_project_data(project_id: str, project_name: str, project_description: str, filename: str, text: str,
                          existing: list[dict]) -> ProjectData:
    document_id = f"document:{uuid4()}"
    entities = [Entity(id=document_id, kind="Document", name=Path(filename).name,
                       source="upload", description=text[:1800])]
    links: list[Link] = []
    # Sections remain small enough to inspect and cite individually.
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) > 850 and current:
            chunks.append(current)
            current = ""
        current += ("\n" if current else "") + paragraph[:850]
    if current:
        chunks.append(current)
    for index, chunk in enumerate(chunks[:30]):
        section_id = f"{document_id}:section:{index + 1}"
        entities.append(Entity(id=section_id, kind="DocumentSection", name=f"{Path(filename).name} · section {index + 1}",
                               source="upload", description=chunk))
        links.append(Link(source=section_id, target=document_id, kind="PART_OF"))
        for entity in existing:
            name = entity["name"]
            if entity["kind"] not in {"Document", "DocumentSection"} and len(name) >= 5 and name.casefold() in chunk.casefold():
                links.append(Link(source=section_id, target=entity["id"], kind="MENTIONS",
                                  confidence="candidate"))
    return ProjectData(project_id=project_id, name=project_name, description=project_description,
                       entities=entities, links=links)
