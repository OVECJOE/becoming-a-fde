import asyncio
import xml.etree.ElementTree as ET
from collections import deque
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import aiosqlite
import httpx
import openai
from chromadb import Collection
from protego import Protego
from selectolax.lexbor import LexborHTMLParser

from core.chat.embedder import embed_and_store_chunk
from core.config import settings
from core.constants import RECOGNISED_SITEMAP_LOCATIONS
from core.crawler.helpers import (
    extract_blocks,
    extract_locs,
    fetch_page,
    fetch_sitemap_root,
    get_client,
    sitemap_kind,
)
from core.db.repository import (
    PageStatus,
    fetch_pending,
    insert_pages,
    mark_status,
)
from schemas import Page


async def collect_seed_urls(
    root_sitemaps: list[str],
    user_agent: str,
    max_depth: int = 3,
    seen: set[str] | None = None,
) -> list[str]:
    """Expand root sitemaps into concrete page URLs.

    A root sitemap is either a leaf `<urlset>` (its `<loc>`s are pages) or a
    `<sitemapindex>` whose `<loc>`s point to more sitemaps, which may themselves
    be indexes. Recurse into indexes up to `max_depth`, skipping any sitemap
    already visited so a cycle (or a self-referencing index) can't spin forever.
    """
    seen = seen if seen is not None else set()
    page_urls: set[str] = set()

    async def walk(sitemap_url: str, depth: int) -> None:
        norm = sitemap_url.split("#", 1)[0]
        if depth > max_depth or norm in seen:
            return
        seen.add(norm)

        try:
            root = await fetch_sitemap_root(sitemap_url, user_agent)
        except (httpx.HTTPError, ET.ParseError) as e:
            print(f"[WARNING] Skipping sitemap {sitemap_url} ({type(e).__name__}): {e}")
            return

        kind = sitemap_kind(root)
        if kind == "index":
            children = extract_locs(root)
            print(
                f"Sitemap {sitemap_url} is an index -> {len(children)} child sitemaps (depth {depth})."
            )
            await asyncio.gather(*(walk(child, depth + 1) for child in children))
        elif kind == "urlset":
            locs = extract_locs(root)
            print(
                f"Sitemap {sitemap_url} is a leaf -> {len(locs)} page URLs (depth {depth})."
            )
            page_urls.update(locs)
        else:
            print(
                f"[WARNING] {sitemap_url} has unrecognized root <{root.tag}>; ignoring."
            )

    await asyncio.gather(*(walk(s, 0) for s in root_sitemaps))
    return list(page_urls)


async def attempt_to_find_sitemaps(domain: str) -> list[str]:
    client = get_client()
    for location in RECOGNISED_SITEMAP_LOCATIONS:
        url = f"https://{domain}{location}"
        try:
            response = await client.head(url, timeout=5.0)
            response.raise_for_status()
            return [url]
        except httpx.HTTPError:
            print(
                f"[WARNING] '{location}' is not the root sitemap location for '{domain}'"
            )
    return []


async def get_crawl_rules(domain: str) -> tuple[Protego, list[str]]:
    print(f"Loading robots.txt for {domain}...")
    robots_txt = await fetch_page(
        url=f"https://{domain}/robots.txt",
        user_agent=settings.user_agent,
        content_type="text/plain",
    )
    rp = Protego.parse(robots_txt)
    print(f"Loaded robots.txt for {domain}.")

    sitemaps = list(rp.sitemaps) or await attempt_to_find_sitemaps(domain)
    return rp, sitemaps


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
    print(f"Fetching homepage {homepage} for links...")
    parsed = urlparse(homepage)
    html_content = await fetch_page(homepage, settings.user_agent)
    links = extract_links(LexborHTMLParser(html_content), homepage, parsed.netloc)
    print(f"Found {len(links)} links on {homepage}.")
    return links


async def process_page(
    db: aiosqlite.Connection,
    collection: Collection,
    rp: Protego,
    page: Page,
    target_domain: str,
) -> None:
    url = page.url.encoded_string()
    print(f"Processing {url}...")

    if not rp.can_fetch(url, settings.user_agent):
        print(f"Skipping {url}: blocked by robots.txt.")
        await mark_status(db, url, PageStatus.FAILED)
        return

    try:
        html_content = await fetch_page(url, settings.user_agent)
    except httpx.HTTPError:
        print(f"Skipping {url}: fetch failed.")
        await mark_status(db, url, PageStatus.FAILED)
        return

    tree = LexborHTMLParser(html_content)
    links = extract_links(tree, url, target_domain)

    new_depth = page.depth + 1
    if new_depth <= settings.max_depth and links:
        try:
            await insert_pages(db, links, new_depth, url)
        except aiosqlite.DatabaseError as e:
            print(
                f"[ERROR] Could not insert links discovered on '{url}' (reason: {e!s})"
            )

    # extract and persist main text content from `tree`
    chunks = chunk_blocks(extract_blocks(tree), 500)
    print(f"Saving {len(chunks)} chunks for {url}...")
    try:
        await asyncio.gather(
            *[
                embed_and_store_chunk(db, collection, page, chunk_idx, chunk)
                for chunk_idx, chunk in enumerate(chunks)
            ]
        )
    except openai.APIError as e:
        print(
            f"[WARNING] Embedding failed for {url} ({e!s}); page still marked crawled."
        )

    await mark_status(db, url, PageStatus.CRAWLED, crawled_at=datetime.now(UTC))
    print(f"Crawled {url}.")


async def crawl_loop(db, collection: Collection, rp, domain: str) -> None:
    print(f"Crawl loop started for {domain}.")
    while True:
        batch = await fetch_pending(db, limit=1)
        if not batch:
            print(f"Crawl queue empty for {domain}, finishing.")
            break
        page = Page(id=batch[0]["id"], url=batch[0]["url"], depth=batch[0]["depth"])
        print(f"Crawling {page.url.encoded_string()}...")

        delay = rp.crawl_delay(settings.user_agent) or settings.crawl_delay_seconds
        print(f"Waiting {float(delay)}s before fetch...")
        await asyncio.sleep(float(delay))

        await process_page(db, collection, rp, page, domain)
    print(f"Crawl loop finished for {domain}.")


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
