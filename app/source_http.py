"""Bounded requests to known provider hosts; never follow source redirects."""
import asyncio
import json

import httpx


async def remote_json(client: httpx.AsyncClient, method: str, url: str, **kwargs):
    for attempt in range(3):
        async with client.stream(method, url, **kwargs) as response:
            if response.status_code in {429, 502, 503, 504} and attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > 8 * 1024 * 1024:
                    raise ValueError("The source response is too large. Import a smaller scope.")
            try:
                return json.loads(content), dict(response.headers)
            except ValueError as exc:
                raise ValueError("The source returned an unreadable response") from exc
    raise RuntimeError("Source request retries exhausted")
