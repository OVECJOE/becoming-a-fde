import asyncio
from collections import deque
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiosqlite
import httpx
from selectolax.lexbor import LexborHTMLParser

from core.config import settings
from core.crawler.helpers import extract_blocks, fetch_page, parse_sitemap
from core.db.repository import (
    PageStatus,
    fetch_pending,
    insert_page,
    insert_page_chunk,
    mark_status,
    url_exists,
)
from schemas import Page


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


def extract_links(
    html_tree: LexborHTMLParser, base_url: str, target_domain: str
) -> list[str]:
    seed_urls: set[str] = set()
    anchors = html_tree.css("a[href]")
    for anchor in anchors:
        href = anchor.attributes["href"]
        if not href or href.startswith("#"):
            continue

        absolute_url = urljoin(base_url, href).split("#", 1)[0]
        if urlparse(absolute_url).netloc == target_domain:
            seed_urls.add(absolute_url)
    return list(seed_urls)


async def build_seed_urls(homepage: str) -> list[str]:
    parsed = urlparse(homepage)
    html_content = await fetch_page(homepage, settings.user_agent)
    return extract_links(LexborHTMLParser(html_content), homepage, parsed.netloc)


async def process_page(
    db: aiosqlite.Connection, rp: RobotFileParser, page: Page, target_domain: str
) -> None:
    url = page.url.encoded_string()

    if not rp.can_fetch(settings.user_agent, url):
        await mark_status(db, url, PageStatus.FAILED)
        return

    try:
        html_content = await fetch_page(url, settings.user_agent)
    except httpx.HTTPError:
        await mark_status(db, url, PageStatus.FAILED)
        return

    tree = LexborHTMLParser(html_content)
    links = extract_links(tree, url, target_domain)

    for link in links:
        if await url_exists(db, link):
            continue
        new_depth = page.depth + 1
        if new_depth > settings.max_depth:
            continue
        try:
            await insert_page(db, link, new_depth, url)
        except aiosqlite.DatabaseError as e:
            print(
                f"[ERROR] Could not complete link processing for '{link}' (reason: {e!s})"
            )

    # extract and persist main text content from `tree`
    chunks = chunk_blocks(extract_blocks(tree), 500)
    await asyncio.gather(
        *[
            insert_page_chunk(db, page.id, chunk_idx, chunk)
            for chunk_idx, chunk in enumerate(chunks)
        ]
    )

    await mark_status(db, url, PageStatus.CRAWLED, crawled_at=datetime.now(UTC))


async def crawl_loop(db, rp, domain: str) -> None:
    while True:
        batch = await fetch_pending(db, limit=1)
        if not batch:
            break
        page = Page(id=batch[0]["id"], url=batch[0]["url"], depth=batch[0]["depth"])

        delay = rp.crawl_delay(settings.user_agent) or settings.crawl_delay_seconds
        await asyncio.sleep(float(delay))

        await process_page(db, rp, page, domain)


def chunk_blocks(blocks: list[str], target_chars: int = 1000) -> list[str]:
    chunks: list[str] = []
    current_chunk: str = ""

    pending = deque(blocks)
    while pending:
        piece = pending.popleft()
        if len(piece) > target_chars:
            split = piece.rsplit("\n", 1)
            if len(split) == 2:
                pending.appendleft(split[1])
                pending.appendleft(split[0])
                continue

        candidate = f"{current_chunk}\n{piece}" if current_chunk else piece
        if len(candidate) > target_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = piece
        else:
            current_chunk = candidate

    if current_chunk:
        chunks.append(current_chunk)
    return chunks
