import asyncio

import aiosqlite
from chromadb import Collection

from core.crawler.repository import build_seed_urls, crawl_loop, get_crawl_rules
from core.db.repository import insert_page, url_exists


async def crawl(db: aiosqlite.Connection, collection: Collection, domain: str):
    print(f"Resolving crawl rules for {domain}...")
    rp, seed_urls = await get_crawl_rules(domain)
    print(f"Found {len(seed_urls)} seed URLs for {domain}.")
    if len(seed_urls) == 1:
        print(f"Expanding seed URL {seed_urls[0]}...")
        seed_urls = await build_seed_urls(seed_urls[0])
        print(f"Expanded to {len(seed_urls)} seed URLs.")

    print(f"Seeding {len(seed_urls)} URLs...")
    for url in seed_urls:
        if not await url_exists(db, url):
            await insert_page(db, url, depth=0, parent_url=None)
    print("Seeding complete.")

    print(f"Starting crawl loop for {domain}...")
    return asyncio.create_task(crawl_loop(db, collection, rp, domain))
