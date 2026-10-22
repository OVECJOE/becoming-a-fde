import asyncio

import aiosqlite
from chromadb import Collection
from protego import Protego

from core.config import settings
from core.crawler.repository import (
    build_seed_urls,
    collect_seed_urls,
    crawl_loop,
    get_crawl_rules,
)
from core.db.helpers import init_db
from core.db.repository import get_or_create_site, insert_pages

_running: dict[int, tuple[dict, asyncio.Task]] = {}


async def _run_crawl_loop(collection: Collection, rp: Protego, site: dict) -> None:
    db = await init_db()
    try:
        await crawl_loop(db, collection, rp, site)
    finally:
        await db.close()


async def crawl(
    db: aiosqlite.Connection, collection: Collection, domain: str
) -> tuple[dict, asyncio.Task] | None:
    site = await get_or_create_site(db, domain)
    existing = _running.get(site["id"])
    if existing is not None and not existing[1].done():
        return None

    site_domain = site["domain"]
    print(f"Resolving crawl rules for {site_domain}...")
    rp, seed_sitemaps = await get_crawl_rules(site_domain)
    print(f"Found {len(seed_sitemaps)} root sitemaps for {site_domain}.")

    seed_urls = await collect_seed_urls(
        seed_sitemaps, settings.user_agent, settings.sitemap_max_depth
    )
    print(f"Expanded sitemaps into {len(seed_urls)} seed URLs for {site_domain}.")
    if len(seed_urls) == 0:
        seed_urls = await build_seed_urls(f"https://{site_domain}", site_domain)

    try:
        inserted = await insert_pages(
            db, site["id"], ((url, 0, None) for url in seed_urls)
        )
    except aiosqlite.DatabaseError as e:
        print(f"[ERROR] Could not seed pages for {site_domain} (reason: {e!s})")
    else:
        print(
            f"Seeded {inserted} new pages ({len(seed_urls) - inserted} already present)."
        )
    print("Seeding complete.")

    print(f"Starting crawl loop for {site_domain}...")
    task = asyncio.create_task(_run_crawl_loop(collection, rp, site))
    _running[site["id"]] = (site, task)
    return site, task


def active_crawl_domains() -> list[str]:
    return [
        site["domain"]
        for site, task in _running.values()
        if not task.done()
    ]


async def cancel_active_crawls() -> None:
    tasks = [task for _, task in _running.values()]
    _running.clear()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
