import asyncio
from itertools import chain
from urllib.robotparser import RobotFileParser

from core.config import settings
from core.crawler.helpers import parse_sitemap


async def get_crawl_rules(domain: str) -> tuple[RobotFileParser, list[str]]:
    rp = RobotFileParser(url=f"https://{domain}/robots.txt")
    rp.read()

    sitemaps = rp.site_maps() or [f"https://{domain}/sitemap.xml"]
    results = await asyncio.gather(
        *[parse_sitemap(sitemap, settings.user_agent) for sitemap in sitemaps]
    )

    seed_urls = (
        list(chain.from_iterable(results)) if any(results) else [f"https://{domain}"]
    )
    return rp, seed_urls
