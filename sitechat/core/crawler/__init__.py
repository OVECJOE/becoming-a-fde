import asyncio

import aiosqlite
from chromadb import Collection

from core.config import settings
from core.crawler.repository import (
    collect_seed_urls,
    crawl_loop,
    get_crawl_rules,
)
from core.db.repository import insert_pages


async def crawl(db: aiosqlite.Connection, collection: Collection, domain: str):
    print(f"Resolving crawl rules for {domain}...")
    rp, seed_sitemaps = await get_crawl_rules(domain)
    print(f"Found {len(seed_sitemaps)} root sitemaps for {domain}.")

    # Expand the (possibly nested) sitemaps into concrete page URLs to seed the queue.
    seed_urls = await collect_seed_urls(
        seed_sitemaps, settings.user_agent, settings.sitemap_max_depth
    )
    print(f"Expanded sitemaps into {len(seed_urls)} seed URLs for {domain}.")

    # Store the seed urls for the crawl loop to pick up, in one batch.
    try:
        inserted = await insert_pages(db, seed_urls, depth=0, parent_url=None)
    except aiosqlite.DatabaseError as e:
        print(f"[ERROR] Could not seed pages for {domain} (reason: {e!s})")
    else:
        print(
            f"Seeded {inserted} new pages ({len(seed_urls) - inserted} already present)."
        )
    print("Seeding complete.")

    print(f"Starting crawl loop for {domain}...")
    return asyncio.create_task(crawl_loop(db, collection, rp, domain))
