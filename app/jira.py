from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import httpx

from .schema import Entity, Link, ProjectData
from .source_http import remote_json


def jira_site(value: str) -> str:
    parsed = urlparse(value.strip())
    if (parsed.scheme != "https" or not re.fullmatch(r"[a-zA-Z0-9-]+\.atlassian\.net", parsed.hostname or "")
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Jira Cloud requires an https://your-team.atlassian.net site")
    return f"https://{parsed.hostname}"


def jira_reference(value: str, site: str) -> str:
    value = value.strip()
    if "://" in value:
        if jira_site(value) != site:
            raise ValueError("This ticket belongs to a different Jira site than the server connection")
        match = re.fullmatch(r"/browse/([A-Za-z][A-Za-z0-9_]*-\d+)/?", urlparse(value).path)
        if not match:
            raise ValueError("Enter a Jira ticket URL, ticket key, or project key")
        value = match.group(1)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:-\d+)?", value):
        raise ValueError("Enter a ticket key such as TEAM-123 or project key such as TEAM")
    return value.upper()


def rich_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("type") == "text":
            return value.get("text", "")
        return " ".join(rich_text(child) for child in value.get("content", []))
    return ""


def jira_data(payload: dict, name: str, source_id: str, site: str = "", reference: str = "", partial: bool = False) -> ProjectData:
    issues = payload.get("issues") if isinstance(payload, dict) else None
    if issues is None and isinstance(payload, dict) and "key" in payload and "fields" in payload:
        issues = [payload]
    if not isinstance(issues, list) or not issues or len(issues) > 5000:
        raise ValueError("Use a Jira JSON issue or an object containing 1–5,000 issues with key and fields")
    if any(not isinstance(issue, dict) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", str(issue.get("key", "")))
           or not isinstance(issue.get("fields"), dict) for issue in issues):
        raise ValueError("Each Jira issue needs a valid key and fields object")
    partial = partial or bool(payload.get("nextPageToken")) or payload.get("isLast") is False or (payload.get("total", len(issues)) > len(issues))
    entities, links = {}, []
    ids = {issue["key"]: f"{source_id}:issue:{issue['key']}" for issue in issues}
    missing_links = 0
    for issue in issues:
        fields, key = issue["fields"], issue["key"]
        assignee = fields.get("assignee") or {}
        entity_id = ids[key]
        status = (fields.get("status") or {}).get("name") or "unknown"
        url = f"{site}/browse/{key}" if site else ""
        description = rich_text(fields.get("description"))[:12000]
        if fields.get("duedate"):
            description += f"\nDue: {fields['duedate']}"
        entities[entity_id] = Entity(id=entity_id, kind="Task", name=f"{key} {fields.get('summary') or key}",
            status=status, source="jira", url=url, description=description,
            owner=assignee.get("displayName") or "", updated_at=fields.get("updated") or "")
        if assignee.get("accountId") or assignee.get("name"):
            person_id = f"{source_id}:person:{assignee.get('accountId') or assignee['name']}"
            entities[person_id] = Entity(id=person_id, kind="Person", name=assignee.get("displayName") or "Jira user", source="jira")
            links.append(Link(source=person_id, target=entity_id, kind="OWNS", evidence=url))
        parent = (fields.get("parent") or {}).get("key")
        if parent in ids:
            links.append(Link(source=entity_id, target=ids[parent], kind="PART_OF", evidence=url))
        for relation in fields.get("issuelinks") or []:
            other = relation.get("outwardIssue") or relation.get("inwardIssue") or {}
            if other.get("key") not in ids:
                missing_links += 1
                continue
            direction = "outward" if relation.get("outwardIssue") else "inward"
            label = (relation.get("type") or {}).get(direction, "relates to").lower()
            target = ids[other["key"]]
            source, kind = entity_id, "RELATED_TO"
            if label == "blocks":
                kind = "BLOCKS"
            elif "blocked by" in label:
                source, target, kind = target, entity_id, "BLOCKS"
            elif "depends on" in label:
                kind = "DEPENDS_ON"
            links.append(Link(source=source, target=target, kind=kind, evidence=f"{url} ({label})"))
    warnings = []
    if partial:
        warnings.append("This Jira import is a partial snapshot. Answers cover imported tickets only.")
    if missing_links:
        warnings.append(f"{missing_links} linked-ticket references point outside this import; their details are not available.")
    return ProjectData(project_id=source_id, name=name, description="Imported Jira work",
        entities=list(entities.values()), links=links, source_id=source_id,
        source_kind="jira" if reference else "jira-export", source_url=reference, source_name=name,
        warnings=warnings, partial=partial)


async def import_jira(reference: str) -> ProjectData:
    if not all(os.getenv(key) for key in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")):
        raise ValueError("Jira Cloud is not connected. Set JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN on the server, or upload a Jira JSON export.")
    site = jira_site(os.environ["JIRA_BASE_URL"])
    key = jira_reference(reference, site)
    source_id = f"jira:{urlparse(site).hostname}:{key}"
    fields = ["summary", "description", "status", "assignee", "updated", "duedate", "issuelinks", "parent"]
    limit = max(100, min(int(os.getenv("IMPORT_MAX_RECORDS", "1000")), 5000))
    async with httpx.AsyncClient(auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
                                headers={"Accept": "application/json"}, timeout=20, follow_redirects=False) as client:
        if re.search(r"-\d+$", key):
            issue, _ = await remote_json(client, "GET", f"{site}/rest/api/3/issue/{key}", params={"fields": ",".join(fields)})
            return jira_data(issue, key, source_id, site, key)
        issues, token, partial = [], None, False
        for _ in range((limit + 99) // 100):
            body = {"jql": f'project = "{key}" ORDER BY updated DESC', "fields": fields, "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            payload, _ = await remote_json(client, "POST", f"{site}/rest/api/3/search/jql", json=body)
            issues.extend(payload.get("issues", []))
            token = payload.get("nextPageToken")
            if payload.get("isLast") or not token:
                break
        else:
            partial = True
    if not issues:
        raise ValueError("No Jira tickets were returned. Check the project key and the token's permissions.")
    return jira_data({"issues": issues[:limit]}, key, source_id, site, key, partial)
