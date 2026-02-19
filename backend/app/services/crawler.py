import asyncio
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from robotexclusionrulesparser import RobotExclusionRulesParser

from app.config import settings
from app.services.extractor import PageMetadata, extract_metadata

logger = logging.getLogger(__name__)

# Suppress per-request httpx logging (INFO:httpx:HTTP Request: GET ...)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".mp4", ".mp3", ".wav",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
}

# Realistic browser headers to avoid WAF/bot-detection blocks
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Note: Do NOT set Accept-Encoding — let httpx negotiate automatically.
    # Setting "br" without the brotli library installed causes garbled responses.
    "Cache-Control": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Patterns that indicate a bot-protection / challenge page
_BOT_PROTECTION_PATTERNS = [
    re.compile(r"Access Denied", re.IGNORECASE),
    re.compile(r"Just a moment\.\.\.", re.IGNORECASE),
    re.compile(r"Enable JavaScript and cookies to continue", re.IGNORECASE),
    re.compile(r"challenge-platform", re.IGNORECASE),
    re.compile(r"Checking your browser", re.IGNORECASE),
    re.compile(r"Attention Required.*Cloudflare", re.IGNORECASE | re.DOTALL),
    re.compile(r"cf-browser-verification", re.IGNORECASE),
    re.compile(r"Pardon Our Interruption", re.IGNORECASE),
    re.compile(r"Please verify you are a human", re.IGNORECASE),
    re.compile(r"blocked.*bot", re.IGNORECASE),
]


def _is_bot_protected(html: str) -> bool:
    """Check if the HTML response is a bot-protection / challenge page."""
    # Only check the first 5000 chars for performance
    sample = html[:5000]
    return any(pattern.search(sample) for pattern in _BOT_PROTECTION_PATTERNS)


@dataclass
class ExistingPageState:
    title: str | None
    description: str | None
    content_hash: str | None
    metadata_hash: str | None
    headings_hash: str | None
    text_hash: str | None
    links: list[str]
    canonical_url: str | None
    etag: str | None
    last_modified: str | None


class Crawler:
    def __init__(
        self,
        root_url: str,
        max_depth: int = settings.max_crawl_depth,
        max_pages: int = settings.max_crawl_pages,
        concurrency: int = settings.crawl_concurrency,
        delay_ms: int = settings.crawl_delay_ms,
        existing_page_state: dict[str, ExistingPageState] | None = None,
        on_page_crawled=None,
        on_page_skipped=None,
    ):
        self.root_url = self._normalize_url(root_url)
        parsed = urlparse(self.root_url)
        self.domain = parsed.netloc
        self.scheme = parsed.scheme
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.delay = delay_ms / 1000.0
        self.existing_page_state = existing_page_state or {}
        self.on_page_crawled = on_page_crawled
        self.on_page_skipped = on_page_skipped

        self.visited: set[str] = set()
        self.results: list[tuple[PageMetadata, int]] = []  # (metadata, depth)
        self.skipped: int = 0
        self.robot_parser: RobotExclusionRulesParser | None = None
        self._blocked_count: int = 0
        self._use_playwright: bool = False
        self._js_probe_attempts: int = 0
        self._js_probe_failures: int = 0
        self._started_at_monotonic: float | None = None
        self._last_progress_at_monotonic: float | None = None
        self._request_count: int = 0
        self._timeout_count: int = 0
        self._consecutive_timeouts: int = 0
        self._success_count: int = 0
        self._circuit_open_count: int = 0
        self._circuit_open_until_monotonic: float | None = None
        self._abort_reason: str | None = None
        self._abort_detail: str | None = None

    def _timeout_rate(self) -> float:
        if self._request_count == 0:
            return 0.0
        return self._timeout_count / self._request_count

    def _mark_progress(self) -> None:
        self._last_progress_at_monotonic = time.monotonic()

    def _record_non_timeout_attempt(self) -> None:
        self._request_count += 1
        self._consecutive_timeouts = 0

    def _record_timeout(self) -> None:
        self._request_count += 1
        self._timeout_count += 1
        self._consecutive_timeouts += 1

    def _abort_crawl(self, reason: str, detail: str) -> None:
        if self._abort_reason is not None:
            return
        self._abort_reason = reason
        self._abort_detail = detail[:400]
        logger.warning("Aborting crawl for %s: %s", self.domain, self._abort_detail)

    def _check_duration_budget(self) -> None:
        max_duration = settings.crawl_max_duration_seconds
        if self._abort_reason is not None or max_duration <= 0:
            return
        if self._started_at_monotonic is None:
            return
        elapsed = time.monotonic() - self._started_at_monotonic
        if elapsed > max_duration:
            self._abort_crawl(
                "duration_budget_exceeded",
                f"elapsed={elapsed:.1f}s budget={max_duration}s",
            )

    def _check_timeout_circuit(self, url: str) -> None:
        if self._abort_reason is not None:
            return

        now = time.monotonic()
        last_progress = self._last_progress_at_monotonic or self._started_at_monotonic or now
        stalled_for = max(0.0, now - last_progress)
        timeout_rate = self._timeout_rate()

        streak_hit = (
            self._consecutive_timeouts >= settings.crawl_timeout_streak_threshold
            and self._request_count >= settings.crawl_timeout_min_samples
        )

        rate_hit = (
            self._request_count >= settings.crawl_timeout_min_samples
            and timeout_rate >= settings.crawl_timeout_rate_threshold
            and stalled_for >= settings.crawl_progress_stall_seconds
        )

        if not (streak_hit or rate_hit):
            return

        self._circuit_open_count += 1
        self._circuit_open_until_monotonic = now + max(
            settings.crawl_circuit_cooldown_seconds, 0
        )
        trigger = "streak" if streak_hit else "rate+stall"
        self._abort_crawl(
            "timeout_circuit_open",
            (
                f"trigger={trigger} url={url} "
                f"timeouts={self._timeout_count}/{self._request_count} "
                f"streak={self._consecutive_timeouts} stalled_for={stalled_for:.1f}s"
            ),
        )

    def health_summary(self) -> dict:
        timeout_rate = self._timeout_rate()
        return {
            "request_count": self._request_count,
            "timeout_count": self._timeout_count,
            "timeout_rate": round(timeout_rate, 4),
            "consecutive_timeouts": self._consecutive_timeouts,
            "success_count": self._success_count,
            "circuit_open_count": self._circuit_open_count,
            "aborted": self._abort_reason is not None,
            "abort_reason": self._abort_reason,
            "abort_detail": self._abort_detail,
            "js_probe_attempts": self._js_probe_attempts,
            "js_probe_failures": self._js_probe_failures,
            "js_mode": self._use_playwright,
        }

    async def crawl(self) -> list[tuple[PageMetadata, int]]:
        async with httpx.AsyncClient(
            timeout=settings.crawl_request_timeout_seconds,
            follow_redirects=True,
            http2=True,
            headers=BROWSER_HEADERS,
            limits=httpx.Limits(
                max_connections=self.concurrency + 5,
                max_keepalive_connections=self.concurrency,
            ),
        ) as client:
            self.client = client
            self._started_at_monotonic = time.monotonic()
            self._mark_progress()

            # Resolve redirects so self.domain matches the final host
            # (e.g. cnn.com → www.cnn.com)
            try:
                head = await client.head(self.root_url)
                final_url = self._normalize_url(str(head.url))
                final_parsed = urlparse(final_url)
                if final_parsed.netloc and final_parsed.netloc != self.domain:
                    logger.info(
                        "Root redirect: %s → %s", self.domain, final_parsed.netloc
                    )
                    self.domain = final_parsed.netloc
                    self.scheme = final_parsed.scheme
                    self.root_url = final_url
            except Exception:
                pass  # proceed with original domain

            await self._load_robots()
            sitemap_urls = await self._load_sitemap()

            self._queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
            self._queue.put_nowait((self.root_url, 0))
            for url in sitemap_urls:
                if url not in self.visited:
                    self._queue.put_nowait((url, 1))

            workers = [
                asyncio.create_task(self._crawl_worker())
                for _ in range(self.concurrency)
            ]
            await self._queue.join()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            # If we got no results and any pages were blocked, fall back to
            # building pages from sitemap URLs alone.
            if (
                self._abort_reason is None
                and not self.results
                and sitemap_urls
                and self._blocked_count > 0
            ):
                logger.info(
                    "Site %s is bot-protected; falling back to %d sitemap URLs",
                    self.domain,
                    len(sitemap_urls),
                )
                await self._sitemap_fallback(sitemap_urls)

        return self.results

    async def _sitemap_fallback(self, sitemap_urls: list[str]) -> None:
        """Build minimal page entries from sitemap URLs when pages can't be
        fetched due to bot protection.  We infer title from the URL path and
        run the normal categoriser / relevance scorer so the LLM generator
        still has useful structure to work with."""
        from app.services.categorizer import categorize_page

        for url in sitemap_urls[: self.max_pages]:
            parsed = urlparse(url)
            # Derive a readable title from the URL path
            path = parsed.path.strip("/")
            if path:
                title = path.split("/")[-1].replace("-", " ").replace("_", " ").title()
            else:
                title = parsed.netloc

            category = categorize_page(url, 1)
            metadata = PageMetadata(
                url=url,
                title=title,
                description=None,
                content_hash="",
                metadata_hash="",
                headings_hash="",
                text_hash="",
                links=[],
                canonical_url=None,
                http_status=0,  # sentinel: never actually fetched
            )
            self.results.append((metadata, 1))
            if self.on_page_crawled:
                await self.on_page_crawled(
                    metadata, 1, len(self.results), len(self.results)
                )

    async def _crawl_worker(self) -> None:
        while True:
            url, depth = await self._queue.get()
            try:
                if self._abort_reason is not None:
                    continue

                self._check_duration_budget()
                if self._abort_reason is not None:
                    continue

                url = self._normalize_url(url)
                if url in self.visited or depth > self.max_depth:
                    continue
                if len(self.results) >= self.max_pages:
                    continue
                self.visited.add(url)

                if self.delay > 0:
                    await asyncio.sleep(self.delay)

                self._check_duration_budget()
                if self._abort_reason is not None:
                    continue

                metadata, skip_reason = await self._fetch_page(url, depth)

                if metadata is None:
                    if skip_reason and self.on_page_skipped:
                        self.skipped += 1
                        await self.on_page_skipped(
                            url, depth, skip_reason, self.skipped
                        )
                    continue

                if len(self.results) >= self.max_pages:
                    continue

                if metadata.url not in self.visited:
                    self.visited.add(metadata.url)
                self.results.append((metadata, depth))
                self._success_count += 1
                self._mark_progress()
                if self.on_page_crawled:
                    await self.on_page_crawled(
                        metadata, depth, len(self.results), len(self.visited)
                    )

                if depth < self.max_depth:
                    for link in metadata.links:
                        if self._should_crawl(link) and link not in self.visited:
                            self._queue.put_nowait((link, depth + 1))
            finally:
                self._queue.task_done()

    async def _render_with_playwright(self, url: str) -> tuple[PageMetadata | None, str | None]:
        """Tier 2: render a page with headless Chromium."""
        from app.services.browser_pool import get_pool

        pool = await get_pool()
        html = await pool.render(url)
        if html is None:
            return None, "Playwright render failed"
        final_url = self._normalize_url(url)
        metadata = extract_metadata(final_url, html, http_status=200)
        if metadata is None:
            return None, "Empty content after JS render"
        return metadata, None

    async def _fetch_page(self, url: str, depth: int = 0) -> tuple[PageMetadata | None, str | None]:
        # ── Tier 2 fast-path: domain already promoted to JS mode ──
        if self._use_playwright:
            metadata, render_error = await self._render_with_playwright(url)
            if metadata is not None:
                return metadata, None
            logger.warning(
                "Playwright fast-path failed for %s (%s); falling back to httpx",
                url,
                render_error or "unknown error",
            )
            # Degrade gracefully for this crawl if Chromium rendering starts failing.
            self._use_playwright = False

        # ── Tier 1: httpx ──
        try:
            headers = {}
            existing = self.existing_page_state.get(url)
            if existing and existing.etag:
                headers["If-None-Match"] = existing.etag
            if existing and existing.last_modified:
                headers["If-Modified-Since"] = existing.last_modified

            resp = await self.client.get(url, headers=headers)
            self._record_non_timeout_attempt()

            if resp.status_code == 304:
                if not existing:
                    return None, "HTTP 304 without cached page state"
                return (
                    PageMetadata(
                        url=url,
                        title=existing.title,
                        description=existing.description,
                        content_hash=existing.content_hash or "",
                        metadata_hash=existing.metadata_hash or "",
                        headings_hash=existing.headings_hash or "",
                        text_hash=existing.text_hash or "",
                        links=existing.links,
                        canonical_url=existing.canonical_url,
                        etag=existing.etag,
                        last_modified=existing.last_modified,
                        http_status=304,
                        not_modified=True,
                    ),
                    None,
                )

            if resp.status_code == 403:
                self._blocked_count += 1
                return None, "HTTP 403 (access denied)"
            if resp.status_code != 200:
                return None, f"HTTP {resp.status_code}"
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                return None, f"Non-HTML ({content_type.split(';')[0].strip()})"

            html_text = resp.text

            # Detect bot-protection / challenge pages — try Playwright
            if _is_bot_protected(html_text):
                self._blocked_count += 1
                logger.info("Bot protection detected on %s, trying Playwright", url)
                result = await self._render_with_playwright(url)
                if result[0] is not None:
                    self._use_playwright = True
                    logger.info("Playwright bypassed bot protection on %s", self.domain)
                    return result
                return None, "Bot protection (challenge page)"

            final_url = self._normalize_url(str(resp.url))
            metadata = extract_metadata(
                final_url,
                html_text,
                etag=resp.headers.get("etag"),
                last_modified=resp.headers.get("last-modified"),
                http_status=resp.status_code,
            )
            if metadata is None:
                return None, "Empty or unparseable HTML"

            # ── Low-yield probe ──
            # If the page yielded very few crawlable links at a shallow depth,
            # try a Playwright render.  If JS rendering produces materially
            # more links, promote the entire domain to Playwright mode.
            if (
                not self._use_playwright
                and depth <= settings.crawl_js_probe_max_depth
                and self._js_probe_attempts < settings.crawl_js_probe_max_attempts
                and self._js_probe_failures < 2
            ):
                crawlable = sum(
                    1 for link in metadata.links if self._should_crawl(link)
                )
                if crawlable <= settings.crawl_js_probe_low_links:
                    self._js_probe_attempts += 1
                    rendered, _err = await self._render_with_playwright(url)
                    if rendered is not None:
                        rendered_crawlable = sum(
                            1 for link in rendered.links
                            if self._should_crawl(link)
                        )
                        if rendered_crawlable >= settings.crawl_js_probe_promote_links:
                            self._use_playwright = True
                            logger.info(
                                "JS probe promoted %s to Playwright mode "
                                "(static=%d links, rendered=%d links)",
                                self.domain,
                                crawlable,
                                rendered_crawlable,
                            )
                            return rendered, None
                        logger.info(
                            "JS probe for %s: no improvement "
                            "(static=%d, rendered=%d)",
                            url, crawlable, rendered_crawlable,
                        )
                    else:
                        self._js_probe_failures += 1
                        logger.warning(
                            "JS probe render failed for %s (attempt %d)",
                            url, self._js_probe_attempts,
                        )

            return metadata, None
        except httpx.TimeoutException:
            self._record_timeout()
            self._check_timeout_circuit(url)
            logger.warning("Timeout fetching %s", url)
            return None, "Timeout"
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None, str(e)[:100]

    def _should_crawl(self, url: str) -> bool:
        url = self._normalize_url(url)
        parsed = urlparse(url)
        if parsed.netloc != self.domain:
            return False
        if parsed.query:
            return False
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return False
        if any(seg in path for seg in ["/login", "/signin", "/signup", "/register", "/admin"]):
            return False
        if self.robot_parser and not self.robot_parser.is_allowed("*", url):
            return False
        return True

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return url
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"

    async def _load_robots(self):
        self._robots_txt = ""
        try:
            resp = await self.client.get(f"{self.scheme}://{self.domain}/robots.txt")
            if resp.status_code == 200:
                self._robots_txt = resp.text
                self.robot_parser = RobotExclusionRulesParser()
                self.robot_parser.parse(resp.text)
        except Exception:
            pass

    def _sitemap_urls_from_robots(self) -> list[str]:
        """Extract Sitemap: directives from robots.txt."""
        urls = []
        for line in self._robots_txt.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("sitemap:"):
                # "Sitemap: https://example.com/sitemap.xml" → grab everything after "Sitemap:"
                url = stripped[len("sitemap:"):].strip()
                if url:
                    urls.append(url)
        return urls

    async def _load_sitemap(self) -> list[str]:
        urls: list[str] = []

        # Try sitemaps declared in robots.txt first
        robots_sitemaps = self._sitemap_urls_from_robots()
        for sm_url in robots_sitemaps:
            try:
                await self._parse_sitemap(sm_url, urls, depth=0)
            except Exception:
                pass
            if len(urls) >= self.max_pages:
                return urls[: self.max_pages]

        # Fall back to conventional /sitemap.xml if robots.txt had none
        if not robots_sitemaps:
            try:
                await self._parse_sitemap(
                    f"{self.scheme}://{self.domain}/sitemap.xml", urls, depth=0
                )
            except Exception:
                pass

        return urls[:self.max_pages]

    async def _parse_sitemap(
        self, sitemap_url: str, urls: list[str], depth: int
    ) -> None:
        if depth > 2 or len(urls) >= self.max_pages:
            return
        try:
            resp = await self.client.get(sitemap_url)
            if resp.status_code != 200:
                return
            content_type = resp.headers.get("content-type", "")
            if "xml" not in content_type and "text" not in content_type:
                return
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "lxml-xml")

            # Handle sitemap index (nested sitemaps)
            sub_sitemaps = soup.find_all("sitemap")
            if sub_sitemaps:
                for sm in sub_sitemaps:
                    loc = sm.find("loc")
                    if loc and len(urls) < self.max_pages:
                        await self._parse_sitemap(
                            loc.get_text(strip=True), urls, depth + 1
                        )
                return

            # Handle regular urlset
            for loc in soup.find_all("loc"):
                url = self._normalize_url(loc.get_text(strip=True))
                if self._should_crawl(url):
                    urls.append(url)
                    if len(urls) >= self.max_pages:
                        return
        except Exception:
            pass
