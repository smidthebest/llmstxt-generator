import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CrawlJob, GeneratedFile, Page, Site
from app.services.categorizer import categorize_page, compute_relevance
from app.services.crawler import Crawler, ExistingPageState
from app.services.extractor import PageMetadata
from app.services.generator import generate_llms_txt

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _has_meaningful_change(page: Page, metadata: PageMetadata) -> bool:
    return any(
        [
            (page.content_hash or "") != metadata.content_hash,
            (page.metadata_hash or "") != metadata.metadata_hash,
            (page.headings_hash or "") != metadata.headings_hash,
            (page.text_hash or "") != metadata.text_hash,
            (page.canonical_url or "") != (metadata.canonical_url or ""),
        ]
    )


async def run_crawl_job(
    db: AsyncSession,
    site_id: int,
    crawl_job_id: int | None = None,
    max_depth: int | None = None,
    max_pages: int | None = None,
) -> bool:
    """Execute a full crawl + categorize + generate pipeline."""
    site = await db.get(Site, site_id)
    if not site:
        logger.error("Site %s not found", site_id)
        return False

    if crawl_job_id:
        job = await db.get(CrawlJob, crawl_job_id)
        if not job:
            logger.error("Crawl job %s not found", crawl_job_id)
            return False
    else:
        job = CrawlJob(site_id=site_id, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)

    job.status = "running"
    job.max_pages = max_pages if max_pages is not None else settings.max_crawl_pages
    await db.commit()

    try:
        now = _utcnow()
        existing_result = await db.execute(select(Page).where(Page.site_id == site_id))
        existing_pages = existing_result.scalars().all()
        existing_by_url = {page.url: page for page in existing_pages}
        seen_urls: set[str] = set()

        counts = {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "unchanged": 0,
        }

        existing_state: dict[str, ExistingPageState] = {}
        for page in existing_pages:
            # Only use conditional requests when we have enough stored state for 304 reuse.
            if not (
                page.links_json
                and page.metadata_hash
                and page.headings_hash
                and page.text_hash
            ):
                continue
            existing_state[page.url] = ExistingPageState(
                title=page.title,
                description=page.description,
                content_hash=page.content_hash,
                metadata_hash=page.metadata_hash,
                headings_hash=page.headings_hash,
                text_hash=page.text_hash,
                links=page.links_json or [],
                canonical_url=page.canonical_url,
                etag=page.etag,
                last_modified=page.last_modified,
            )

        async def on_page_skipped(
            url: str, depth: int, reason: str, skipped_count: int
        ):
            job.pages_skipped = skipped_count
            await db.commit()

        async def on_page_crawled(
            metadata: PageMetadata, depth: int, crawled: int, found: int
        ):
            page_now = _utcnow()
            seen_urls.add(metadata.url)

            category = categorize_page(metadata.url, depth)
            relevance = compute_relevance(metadata.url, depth, category)
            existing = existing_by_url.get(metadata.url)

            if existing is None:
                page = Page(
                    site_id=site_id,
                    url=metadata.url,
                    canonical_url=metadata.canonical_url,
                    title=metadata.title,
                    description=metadata.description,
                    content_hash=metadata.content_hash,
                    metadata_hash=metadata.metadata_hash,
                    headings_hash=metadata.headings_hash,
                    text_hash=metadata.text_hash,
                    links_json=metadata.links,
                    etag=metadata.etag,
                    last_modified=metadata.last_modified,
                    http_status=metadata.http_status,
                    is_active=True,
                    first_seen_at=page_now,
                    last_seen_at=page_now,
                    last_checked_at=page_now,
                    category=category,
                    relevance_score=relevance,
                    depth=depth,
                )
                db.add(page)
                existing_by_url[metadata.url] = page
                counts["added"] += 1
            else:
                reactivated = not existing.is_active
                if reactivated:
                    counts["added"] += 1

                if metadata.not_modified:
                    if not reactivated:
                        counts["unchanged"] += 1
                    existing.http_status = 304
                else:
                    if not reactivated and _has_meaningful_change(existing, metadata):
                        counts["updated"] += 1
                    else:
                        if not reactivated:
                            counts["unchanged"] += 1
                    existing.title = metadata.title
                    existing.description = metadata.description
                    existing.content_hash = metadata.content_hash
                    existing.metadata_hash = metadata.metadata_hash
                    existing.headings_hash = metadata.headings_hash
                    existing.text_hash = metadata.text_hash
                    existing.links_json = metadata.links
                    existing.canonical_url = metadata.canonical_url
                    existing.http_status = metadata.http_status

                existing.category = category
                existing.relevance_score = relevance
                existing.depth = depth
                existing.etag = metadata.etag or existing.etag
                existing.last_modified = metadata.last_modified or existing.last_modified
                existing.last_seen_at = page_now
                existing.last_checked_at = page_now
                existing.is_active = True

            pages_changed = counts["added"] + counts["updated"]
            job.pages_crawled = crawled
            job.pages_found = found
            job.pages_changed = pages_changed
            job.pages_added = counts["added"]
            job.pages_updated = counts["updated"]
            job.pages_unchanged = counts["unchanged"]
            await db.commit()

        crawler_kwargs: dict = {}
        if max_depth is not None:
            crawler_kwargs["max_depth"] = max_depth
        if max_pages is not None:
            crawler_kwargs["max_pages"] = max_pages

        crawler = Crawler(
            site.url,
            existing_page_state=existing_state,
            on_page_crawled=on_page_crawled,
            on_page_skipped=on_page_skipped,
            **crawler_kwargs,
        )
        crawl_results = await crawler.crawl()

        # Update site title/description from root page
        if crawl_results:
            root_meta: PageMetadata = crawl_results[0][0]
            if root_meta.title:
                site.title = root_meta.title
            if root_meta.description:
                site.description = root_meta.description

        removed_urls: list[str] = []
        finalize_now = _utcnow()
        for page_url, page in existing_by_url.items():
            if page.is_active and page_url not in seen_urls:
                page.is_active = False
                page.last_checked_at = finalize_now
                removed_urls.append(page_url)

        counts["removed"] = len(removed_urls)
        pages_changed = counts["added"] + counts["updated"] + counts["removed"]

        active_pages_result = await db.execute(
            select(Page)
            .where(Page.site_id == site_id, Page.is_active.is_(True))
            .order_by(Page.relevance_score.desc(), Page.depth.asc())
        )
        active_pages = active_pages_result.scalars().all()

        job.pages_found = len(crawl_results)
        job.pages_crawled = len(crawl_results)
        job.pages_changed = pages_changed
        job.pages_added = counts["added"]
        job.pages_updated = counts["updated"]
        job.pages_removed = counts["removed"]
        job.pages_unchanged = counts["unchanged"]
        job.pages_skipped = crawler.skipped
        job.change_summary_json = {
            "added": counts["added"],
            "updated": counts["updated"],
            "removed": counts["removed"],
            "unchanged": counts["unchanged"],
            "removed_urls": removed_urls[:50],
            "active_pages": len(active_pages),
        }

        latest_generated_result = await db.execute(
            select(GeneratedFile)
            .where(GeneratedFile.site_id == site_id)
            .order_by(GeneratedFile.created_at.desc())
            .limit(1)
        )
        latest_generated = latest_generated_result.scalar_one_or_none()
        should_regenerate = pages_changed > 0 or latest_generated is None
        job.llms_regenerated = should_regenerate

        if should_regenerate:
            # Generate llms.txt only when meaningful changes occurred.
            if settings.llmstxt_openai_key:
                from app.services.llm_generator import generate_llms_txt_with_llm

                content, content_hash, site_desc = await generate_llms_txt_with_llm(
                    site, active_pages
                )
                if site_desc:
                    site.description = site_desc
            else:
                content, content_hash = generate_llms_txt(site, active_pages)

            generated = GeneratedFile(
                site_id=site_id,
                crawl_job_id=job.id,
                content=content,
                content_hash=content_hash,
            )
            db.add(generated)
        else:
            logger.info(
                "No meaningful changes for %s; skipped llms.txt regeneration",
                site.domain,
            )

        job.status = "completed"
        job.error_message = None
        await db.commit()

        logger.info(
            "Crawl completed for %s: %s pages, +%s ~%s -%s =%s (regen=%s, skipped=%s)",
            site.domain,
            len(crawl_results),
            counts["added"],
            counts["updated"],
            counts["removed"],
            counts["unchanged"],
            should_regenerate,
            crawler.skipped,
        )
        return True

    except Exception as exc:
        logger.exception("Crawl failed for site %s", site_id)
        job.status = "failed"
        job.error_message = str(exc)[:1024]
        await db.commit()
        return False
