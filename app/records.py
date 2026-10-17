"""Validated portable records allow other tools to participate without pretending to have a native connector."""
from hashlib import sha256
import re
from urllib.parse import urlparse

from .schema import ProjectData, RecordsRequest

RELATIONS = {"BLOCKS", "DEPENDS_ON", "REQUIRED_FOR", "OWNS", "OPENED", "PART_OF", "BELONGS_TO",
             "RESOLVES", "IMPLEMENTS", "CHANGES", "SUPPORTS", "RELATED_TO", "MENTIONS"}


def records_data(project_id: str, payload: dict) -> ProjectData:
    request = RecordsRequest.model_validate(payload)
    source_id = "records:" + sha256(request.name.strip().casefold().encode()).hexdigest()[:24]
    ids = {entity.id for entity in request.entities}
    if len(ids) != len(request.entities):
        raise ValueError("Every record must have a unique id")
    for entity in request.entities:
        if not entity.id or not entity.name.strip() or len(entity.description) > 200000:
            raise ValueError("Records need an id, name, and description under 200,000 characters")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,40}", entity.kind):
            raise ValueError("Record kinds must contain only letters and numbers")
        if entity.url and (urlparse(entity.url).scheme not in {"http", "https"} or not urlparse(entity.url).hostname):
            raise ValueError("Record URLs must be http or https links")
    for link in request.links:
        if link.source not in ids or link.target not in ids:
            raise ValueError("Every connection must reference records included in this upload")
        if link.kind not in RELATIONS or link.confidence not in {"confirmed", "candidate"}:
            raise ValueError("Unknown relationship kind or confidence; see the records format in the README")
    prefix = f"{source_id}:"
    entities = [entity.model_copy(update={"id": prefix + entity.id, "source": request.name}) for entity in request.entities]
    links = [link.model_copy(update={"source": prefix + link.source, "target": prefix + link.target}) for link in request.links]
    return ProjectData(project_id=project_id, name=request.name, entities=entities, links=links,
                       source_id=source_id, source_kind="records", source_name=request.name)
