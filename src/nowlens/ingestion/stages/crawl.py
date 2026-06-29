"""Crawl stage.

Async HTTP fetching with polite defaults: configurable user-agent, per-host
``robots.txt`` enforcement (cached), a concurrency semaphore, and a crawl delay.
Network/HTTP failures are captured on the :class:`CrawlResult` rather than
raised, so the pipeline's retry/skip logic stays in one place.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from nowlens.core.config import IngestionSettings
from nowlens.core.logging import get_logger
from nowlens.ingestion.models import CrawlResult

log = get_logger(__name__)


class Crawler:
    def __init__(self, settings: IngestionSettings) -> None:
        self._cfg = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._robots: dict[str, RobotFileParser | None] = {}
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.request_timeout_s,
            follow_redirects=True,
        )

    async def _allowed(self, url: str) -> bool:
        if not self._cfg.respect_robots:
            return True
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        if host not in self._robots:
            parser: RobotFileParser | None
            try:
                resp = await self._client.get(f"{host}/robots.txt")
                if resp.status_code == 200:
                    parser = RobotFileParser()
                    parser.parse(resp.text.splitlines())
                else:
                    parser = None  # no robots => allow
            except httpx.HTTPError:
                parser = None
            self._robots[host] = parser
        parser = self._robots[host]
        return parser is None or parser.can_fetch(self._cfg.user_agent, url)

    async def fetch(self, url: str) -> CrawlResult:
        async with self._semaphore:
            if not await self._allowed(url):
                log.info("crawl.robots_disallow", url=url)
                return CrawlResult(
                    url=url, status_code=0, html="", error="disallowed by robots.txt"
                )
            try:
                return await self._fetch_capped(url)
            except httpx.HTTPError as exc:
                log.warning("crawl.error", url=url, error=str(exc))
                return CrawlResult(url=url, status_code=0, html="", error=str(exc))

    async def _fetch_capped(self, url: str) -> CrawlResult:
        """Fetch a URL, reading at most ``max_document_bytes`` of the body.

        We stream rather than buffer so an oversized (or maliciously large)
        response is rejected as soon as it crosses the limit, instead of being
        fully read into memory first.
        """

        max_bytes = self._cfg.max_document_bytes
        async with self._client.stream("GET", url) as resp:
            content_type = resp.headers.get("content-type", "text/html").split(";")[0]
            is_textual = "html" in content_type or "xml" in content_type

            declared = resp.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > max_bytes:
                return CrawlResult(
                    url=str(resp.url),
                    status_code=resp.status_code,
                    html="",
                    content_type=content_type,
                    error=f"response exceeds {max_bytes} byte limit",
                )

            body = bytearray()
            async for chunk in resp.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    return CrawlResult(
                        url=str(resp.url),
                        status_code=resp.status_code,
                        html="",
                        content_type=content_type,
                        error=f"response exceeds {max_bytes} byte limit",
                    )

            await asyncio.sleep(self._cfg.crawl_delay_s)
            html = ""
            if is_textual:
                html = bytes(body).decode(resp.encoding or "utf-8", errors="replace")
            return CrawlResult(
                url=str(resp.url),
                status_code=resp.status_code,
                html=html,
                content_type=content_type,
            )

    async def aclose(self) -> None:
        await self._client.aclose()
