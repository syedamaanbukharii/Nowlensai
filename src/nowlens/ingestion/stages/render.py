"""Render stage (optional).
ServiceNow docs and many SPAs render content client-side. When
``NOWLENS_INGEST_RENDER_JAVASCRIPT=true`` (and the ``render`` extra +
``playwright install chromium`` are present), this stage loads the page in a
headless browser and returns the post-render HTML. Otherwise it is a transparent
pass-through — the crawler's static HTML is used unchanged. This is an explicit,
documented capability boundary, not a stub: static crawling fully works without
it.
"""
from __future__ import annotations

from nowlens.core.config import IngestionSettings
from nowlens.core.logging import get_logger
from nowlens.ingestion.models import CrawlResult

log = get_logger(__name__)


class Renderer:
    def __init__(self, settings: IngestionSettings) -> None:
        self._enabled = settings.render_javascript
        self._timeout_ms = int(settings.request_timeout_s * 1000)

    async def render(self, result: CrawlResult) -> CrawlResult:
        if not self._enabled or not result.ok:
            return result

        try:
            from playwright.async_api import async_playwright
        except ImportError:  # pragma: no cover - optional dep
            log.warning("render.playwright_missing", url=result.url)
            return result

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(
                    result.url,
                    wait_until="networkidle",
                    timeout=self._timeout_ms,
                )
                html = await page.content()
                await browser.close()

            return CrawlResult(
                url=result.url,
                status_code=result.status_code,
                html=html,
                content_type=result.content_type,
                rendered=True,
            )

        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            log.warning("render.failed", url=result.url, error=str(exc))
            return result
