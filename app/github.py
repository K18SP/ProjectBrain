from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import httpx

from .schema import Entity, Link, ProjectData


def parse_public_repo(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise ValueError("Enter a public https://github.com/owner/repository URL")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
        raise ValueError("Enter a repository URL without an issue, branch, or file path")
    return parts[0], parts[1].removesuffix(".git")


async def import_public_repo(url: str) -> ProjectData:
    owner, repo = parse_public_repo(url)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ProjectBrain/0.1"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    base = f"https://api.github.com/repos/{owner}/{repo}"
    async with httpx.AsyncClient(headers=headers, timeout=20) as client:
        response = await client.get(base)
        response.raise_for_status()
        metadata = response.json()
        issue_response = await client.get(base + "/issues", params={"state": "all", "per_page": 60})
        issue_response.raise_for_status()
        issues = issue_response.json()
    project_id = f"github:{owner.lower()}/{repo.lower()}"
    entities = [Entity(id=f"repo:{project_id}", kind="Repository", name=f"{owner}/{repo}",
                       source="github", url=metadata["html_url"], description=metadata.get("description") or "",
                       updated_at=metadata.get("updated_at") or "")]
    links: list[Link] = []
    known_ids: set[str] = set()
    for item in issues:
        number = item["number"]
        is_pr = "pull_request" in item
        kind = "PullRequest" if is_pr else "Task"
        entity_id = f"{project_id}:{'pr' if is_pr else 'issue'}:{number}"
        known_ids.add(entity_id)
        user = item.get("user") or {}
        login = user.get("login") or ""
        entities.append(Entity(id=entity_id, kind=kind, name=f"#{number} {item['title']}",
                               status=item.get("state") or "", source="github", url=item.get("html_url") or "",
                               updated_at=item.get("updated_at") or "", description=(item.get("body") or "")[:1500],
                               owner=login))
        links.append(Link(source=entity_id, target=f"repo:{project_id}", kind="BELONGS_TO",
                          evidence=item.get("html_url") or ""))
        if login:
            person_id = f"github:user:{login.lower()}"
            if not any(e.id == person_id for e in entities):
                entities.append(Entity(id=person_id, kind="Person", name=login, source="github",
                                       url=user.get("html_url") or ""))
            links.append(Link(source=person_id, target=entity_id, kind="OPENED",
                              evidence=item.get("html_url") or ""))
    # Only link explicit GitHub references within the imported page. No relationship is guessed from similarity.
    for item in issues:
        source_id = f"{project_id}:{'pr' if 'pull_request' in item else 'issue'}:{item['number']}"
        body = item.get("body") or ""
        for match in re.finditer(r"(?i)\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)\b", body):
            target_id = f"{project_id}:issue:{match.group(1)}"
            if target_id in known_ids and source_id != target_id:
                links.append(Link(source=source_id, target=target_id, kind="RESOLVES",
                                  evidence=item.get("html_url") or ""))
        for match in re.finditer(r"(?i)\b(?:blocked by|depends on)\s+#(\d+)\b", body):
            target_id = f"{project_id}:issue:{match.group(1)}"
            if target_id in known_ids and source_id != target_id:
                links.append(Link(source=target_id, target=source_id, kind="BLOCKS",
                                  evidence=item.get("html_url") or ""))
    return ProjectData(project_id=project_id, name=f"{owner}/{repo}",
                       description=metadata.get("description") or "Public GitHub repository", entities=entities, links=links)
