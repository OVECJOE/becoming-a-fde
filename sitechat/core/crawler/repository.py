import asyncio
from urllib.robotparser import RobotFileParser

from core.config import settings
from core.crawler.helpers import parse_sitemap


async def get_crawl_rules(domain: str) -> tuple[RobotFileParser, list[str]]:
    rp = RobotFileParser(url=f"https://{domain}/robots.txt")
    rp.read()

    sitemaps = rp.site_maps() or [f"https://{domain}/sitemap.xml"]
    results = await asyncio.gather(
        *[parse_sitemap(sitemap, settings.user_agent) for sitemap in sitemaps],
        return_exceptions=True,
    )

    seed_urls: list[str] = []
    for idx, result in enumerate(results):
        if isinstance(result, BaseException):
            print(
                f"[WARNING] Could not parse sitemap '{sitemaps[idx]}'; check and confirm it exists."
            )
            continue

        seed_urls.extend(result)

    return rp, seed_urls or [f"https://{domain}"]
