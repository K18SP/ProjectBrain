from __future__ import annotations

import base64
import os
import re

import httpx

from .github import parse_public_repo
from .schema import Entity, Link, ProjectData
from .source_http import remote_json
from .repository_code import repository_code


async def import_repository(url: str) -> ProjectData:
    owner, repo = parse_public_repo(url)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ProjectBrain/0.2"}
    if os.getenv("GITHUB_TOKEN") and os.getenv("DEMO_PUBLIC_SOURCES_ONLY") != "true":
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    base = f"https://api.github.com/repos/{owner}/{repo}"
    limit = max(100, min(int(os.getenv("IMPORT_MAX_RECORDS", "1000")), 5000))
    issues, warnings, readme = [], [], None
    partial = False
    async with httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=False) as client:
        metadata, _ = await remote_json(client, "GET", base)
        if os.getenv("DEMO_PUBLIC_SOURCES_ONLY") == "true" and metadata.get("private"):
            raise ValueError("Only public repositories are allowed in this demo")
        for page in range(1, (limit + 99) // 100 + 1):
            batch, response_headers = await remote_json(client, "GET", base + "/issues",
                params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 100, "page": page})
            issues.extend(batch)
            if 'rel="next"' not in response_headers.get("link", ""):
                break
        else:
            partial = True
            warnings.append(f"Import reached the {limit}-record limit. Answers cover the imported sample only.")
        issues = issues[:limit]
        try:
            readme, _ = await remote_json(client, "GET", base + "/readme")
        except httpx.HTTPStatusError as exc:
            warnings.append("No README is available; answers will use imported code and work records." if exc.response.status_code == 404 else "Repository README could not be loaded.")
        except (ValueError, httpx.HTTPError):
            warnings.append("Repository README could not be loaded.")
    full_name = metadata.get("full_name") or f"{owner}/{repo}"
    project_id = f"github:{full_name.lower()}"
    repo_id = f"repo:{project_id}"
    entities = {repo_id: Entity(id=repo_id, kind="Repository", name=full_name, source="github",
        url=metadata["html_url"], description=metadata.get("description") or "",
        updated_at=metadata.get("updated_at") or "")}
    links = []
    issue_ids = {item["number"]: f"{project_id}:{'pr' if 'pull_request' in item else 'issue'}:{item['number']}" for item in issues}
    for item in issues:
        entity_id = issue_ids[item["number"]]
        assignees = item.get("assignees") or []
        labels = [label["name"] if isinstance(label, dict) else label for label in item.get("labels", [])]
        status = item.get("state") or "unknown"
        if status == "open" and any(re.search(r"\b(blocked|on hold)\b", label, re.I) for label in labels):
            status = "blocked"
        body = (item.get("body") or "")[:12000]
        if labels:
            body += "\nLabels: " + ", ".join(labels)
        entities[entity_id] = Entity(id=entity_id, kind="PullRequest" if "pull_request" in item else "Task",
            name=f"#{item['number']} {item['title']}", status=status, source="github",
            url=item.get("html_url") or "", updated_at=item.get("updated_at") or "", description=body,
            owner=", ".join(person["login"] for person in assignees))
        links.append(Link(source=entity_id, target=repo_id, kind="BELONGS_TO", evidence=item.get("html_url") or ""))
        for person, relation in [(person, "OWNS") for person in assignees] + [(item.get("user") or {}, "OPENED")]:
            if not person.get("login"):
                continue
            person_id = f"{project_id}:person:{person['login'].lower()}"
            entities[person_id] = Entity(id=person_id, kind="Person", name=person["login"], source="github", url=person.get("html_url") or "")
            links.append(Link(source=person_id, target=entity_id, kind=relation, evidence=item.get("html_url") or ""))
        milestone = item.get("milestone")
        if milestone:
            milestone_id = f"{project_id}:milestone:{milestone['number']}"
            entities[milestone_id] = Entity(id=milestone_id, kind="Milestone", name=milestone["title"],
                status=milestone.get("state") or "", source="github", url=milestone.get("html_url") or "",
                description=(milestone.get("description") or "") + (f"\nDue: {milestone['due_on']}" if milestone.get("due_on") else ""))
            links.append(Link(source=entity_id, target=milestone_id, kind="PART_OF"))
        for pattern, kind in [(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)\b", "RESOLVES"),
                              (r"\b(?:blocked by|depends on)\s+#(\d+)\b", "DEPENDS_ON")]:
            for match in re.finditer(pattern, body, re.I):
                target_id = issue_ids.get(int(match.group(1)))
                if target_id and target_id != entity_id:
                    links.append(Link(source=entity_id, target=target_id, kind=kind, evidence=item.get("html_url") or ""))
    if readme and readme.get("content"):
        text = base64.b64decode(readme["content"]).decode("utf-8", errors="replace")
        if len(text) > 48000:
            warnings.append("README content is limited to its first 48,000 characters.")
        doc_id = f"{project_id}:readme"
        entities[doc_id] = Entity(id=doc_id, kind="Document", name=f"{full_name} README", source="github",
            url=readme.get("html_url") or "", description=text[:1200])
        links.append(Link(source=doc_id, target=repo_id, kind="PART_OF"))
        for offset in range(0, min(len(text), 48000), 2000):
            section_id = f"{doc_id}:{offset // 2000 + 1}"
            entities[section_id] = Entity(id=section_id, kind="DocumentSection", name=f"README section {offset // 2000 + 1}",
                description=text[offset:offset + 2000], source="github", url=readme.get("html_url") or "")
            links.append(Link(source=section_id, target=doc_id, kind="PART_OF"))
    async with httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=False) as client:
        code_entities, code_links, code_warnings = await repository_code(client, base, metadata, project_id, repo_id)
    entities.update({entity.id: entity for entity in code_entities})
    links.extend(code_links)
    warnings.extend(code_warnings)
    return ProjectData(project_id=project_id, name=full_name, description=metadata.get("description") or "GitHub repository",
        entities=list(entities.values()), links=links, source_id=project_id, source_kind="github",
        source_url=metadata["html_url"], source_name=full_name, warnings=warnings, partial=partial)
