from __future__ import annotations

import re
from urllib.parse import urlparse


def parse_public_repo(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username
            or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Enter an https://github.com/owner/repository URL")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
        raise ValueError("Enter a repository URL without an issue, branch, or file path")
    repository = parts[1].removesuffix(".git")
    if not repository or repository in {".", ".."} or parts[0] in {".", ".."}:
        raise ValueError("Enter a valid repository owner and name")
    return parts[0], repository
