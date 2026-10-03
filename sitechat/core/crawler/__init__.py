import aiosqlite

from core.crawler.repository import build_seed_urls, crawl_loop, get_crawl_rules
from core.db.repository import insert_page, url_exists


async def crawl(db: aiosqlite.Connection, domain: str) -> None:
    rp, seed_urls = await get_crawl_rules(domain)
    if len(seed_urls) == 1:
        seed_urls = await build_seed_urls(seed_urls[0])

    for url in seed_urls:
        if not await url_exists(db, url):
            await insert_page(db, url, depth=0, parent_url=None)

    await crawl_loop(db, rp, domain)
