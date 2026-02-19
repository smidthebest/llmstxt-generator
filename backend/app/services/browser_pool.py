"""Global Playwright browser pool.

Singleton, lazy-init, semaphore-gated.  One Chromium process is shared across
all crawl tasks on the worker.  Max concurrent page renders is capped by an
asyncio.Semaphore to stay within the 1 GB RAM budget.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserPool:
    def __init__(self, max_pages: int = 2):
        self._pw = None
        self._browser = None
        self._max_pages = max_pages
        self._sem = asyncio.Semaphore(max_pages)
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> None:
        if self._browser is not None and self._browser.is_connected():
            return
        async with self._lock:
            if self._browser is not None and self._browser.is_connected():
                return
            # Clean up dead browser if needed
            if self._browser is not None:
                logger.info("Browser died, restarting...")
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._pw is not None:
                try:
                    await self._pw.stop()
                except Exception:
                    pass
                self._pw = None
            logger.info("Starting headless Chromium (max_pages=%s)", self._max_pages)
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--metrics-recording-only",
                    "--no-first-run",
                ],
            )

    async def render(self, url: str, timeout_ms: int = 30_000) -> str | None:
        """Render a page with headless Chromium and return the final HTML.

        Returns None if Playwright is not installed or if the render fails.
        Blocks on the semaphore to limit concurrent page count.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return None

        async with self._sem:
            try:
                await self._ensure_browser()
            except Exception:
                logger.exception("Failed to start headless Chromium")
                return None

            try:
                page = await self._browser.new_page()
            except Exception:
                # Browser died between _ensure_browser and new_page — restart once
                logger.warning("Browser connection lost, restarting...")
                self._browser = None
                try:
                    await self._ensure_browser()
                    page = await self._browser.new_page()
                except Exception:
                    logger.exception("Failed to restart headless Chromium")
                    return None

            try:
                await page.goto(url, wait_until="load", timeout=timeout_ms)
                # Give JS frameworks (Angular, React, Vue) time to render.
                # Wait up to 5s for meaningful content to appear in the DOM.
                try:
                    await page.wait_for_function(
                        "document.querySelectorAll('a[href]').length > 3"
                        " || document.body.innerText.length > 500",
                        timeout=5000,
                    )
                except Exception:
                    pass  # timeout is fine — best-effort wait
                html = await page.content()
                return html
            except Exception:
                logger.warning("Playwright render failed for %s", url)
                return None
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

    async def shutdown(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        logger.info("Headless Chromium shut down")


# ── Module-level singleton ──────────────────────────────────────────────

_pool: BrowserPool | None = None


async def get_pool() -> BrowserPool:
    """Return the shared BrowserPool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = BrowserPool(max_pages=2)
    return _pool


async def shutdown_pool() -> None:
    """Shut down the shared BrowserPool (call on worker exit)."""
    global _pool
    if _pool is not None:
        await _pool.shutdown()
        _pool = None
