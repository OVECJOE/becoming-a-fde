import asyncio
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin

import aiosqlite
import httpx
import openai
from chromadb import Collection
from protego import Protego
from selectolax.lexbor import LexborHTMLParser

from core.chat.embedder import add_page_chunks
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
    insert_page_chunks,
    insert_pages,
    mark_pages,
)
from core.urls import normalize_url, url_host
from schemas import Page


@dataclass
class CrawlOutcome:
    page_id: int
    url: str
    status: PageStatus
    crawled_at: datetime | None = None
    links: set[str] = field(default_factory=set)
    chunks: list[str] = field(default_factory=list)


async def collect_seed_urls(
    root_sitemaps: set[str],
    user_agent: str,
    max_depth: int = 3,
    seen: set[str] | None = None,
) -> set[str]:
    seen = seen if seen is not None else set()
    page_urls: set[str] = set()

    async def walk(sitemap_url: str, depth: int) -> None:
        normalized = normalize_url(sitemap_url)
        if depth > max_depth or normalized in seen:
            return
        seen.add(normalized)

        try:
            root = await fetch_sitemap_root(normalized, user_agent)
        except (httpx.HTTPError, ET.ParseError) as e:
            print(f"[WARNING] Skipping sitemap {normalized} ({type(e).__name__}): {e}")
            return

        kind = sitemap_kind(root)
        if kind == "index":
            children = extract_locs(root)
            print(
                f"Sitemap {normalized} is an index -> {len(children)} child sitemaps (depth {depth})."
            )
            await asyncio.gather(*(walk(child, depth + 1) for child in children))
        elif kind == "urlset":
            locs = extract_locs(root)
            print(
                f"Sitemap {normalized} is a leaf -> {len(locs)} page URLs (depth {depth})."
            )
            page_urls.update(normalize_url(loc) for loc in locs)
        else:
            print(
                f"[WARNING] {normalized} has unrecognized root <{root.tag}>; ignoring."
            )

    await asyncio.gather(*(walk(s, 0) for s in root_sitemaps))
    return page_urls


async def attempt_to_find_sitemaps(domain: str) -> set[str]:
    client = get_client()
    for location in RECOGNISED_SITEMAP_LOCATIONS:
        url = f"https://{domain}{location}"
        try:
            response = await client.head(url, timeout=5.0)
            response.raise_for_status()
            return {url}
        except httpx.HTTPError:
            print(
                f"[WARNING] '{location}' is not the root sitemap location for '{domain}'"
            )
    return set()


async def get_crawl_rules(domain: str) -> tuple[Protego, set[str]]:
    print(f"Loading robots.txt for {domain}...")
    robots_txt = await fetch_page(
        url=f"https://{domain}/robots.txt",
        user_agent=settings.user_agent,
        content_type="text/plain",
    )
    rp = Protego.parse(robots_txt or "")
    print(f"Loaded robots.txt for {domain}.")

    sitemaps = set(rp.sitemaps) or await attempt_to_find_sitemaps(domain)
    return rp, sitemaps


def extract_links(
    html_tree: LexborHTMLParser, base_url: str, site_domain: str
) -> set[str]:
    links: set[str] = set()
    for anchor in html_tree.css("a[href]"):
        href = anchor.attributes["href"]
        if not href or href.startswith("#"):
            continue
        absolute_url = normalize_url(urljoin(base_url, href))
        if url_host(absolute_url) == site_domain:
            links.add(absolute_url)
    return links


async def build_seed_urls(homepage: str, site_domain: str) -> set[str]:
    print(f"Fetching homepage {homepage} for links...")
    html_content = await fetch_page(homepage, settings.user_agent)
    if html_content is None:
        return set()
    links = extract_links(LexborHTMLParser(html_content), homepage, site_domain)
    print(f"Found {len(links)} links on {homepage}.")
    return links


async def process_page(
    rp: Protego,
    page: Page,
    site_domain: str,
) -> CrawlOutcome:
    url = page.url.encoded_string()
    print(f"Processing {url}...")

    if not rp.can_fetch(url, settings.user_agent):
        print(f"Skipping {url}: blocked by robots.txt.")
        return CrawlOutcome(page_id=page.id, url=url, status=PageStatus.FAILED)

    html_content = await fetch_page(url, settings.user_agent)
    if html_content is None:
        print(f"Skipping {url}: fetch failed.")
        return CrawlOutcome(page_id=page.id, url=url, status=PageStatus.FAILED)

    tree = LexborHTMLParser(html_content)
    return CrawlOutcome(
        page_id=page.id,
        url=url,
        status=PageStatus.CRAWLED,
        crawled_at=datetime.now(UTC),
        links=extract_links(tree, url, site_domain),
        chunks=chunk_blocks(extract_blocks(tree), 500),
    )


async def persist_outcomes(
    db: aiosqlite.Connection,
    collection: Collection,
    site: dict,
    pages: list[Page],
    outcomes: list[CrawlOutcome],
) -> None:
    entries: list[tuple[str, int, str | None]] = []
    for page, outcome in zip(pages, outcomes):
        new_depth = page.depth + 1
        if outcome.links and new_depth <= settings.max_depth:
            parent = page.url.encoded_string()
            entries.extend((url, new_depth, parent) for url in outcome.links)
    if entries:
        try:
            await insert_pages(db, site["id"], entries)
        except aiosqlite.DatabaseError as e:
            print(f"[ERROR] Could not insert discovered links (reason: {e!s})")

    stored: list[tuple[CrawlOutcome, list[int]]] = []
    for outcome in outcomes:
        if not outcome.chunks:
            continue
        try:
            chunk_ids = await insert_page_chunks(
                db,
                [
                    (outcome.page_id, index, text)
                    for index, text in enumerate(outcome.chunks)
                ],
            )
        except aiosqlite.DatabaseError as e:
            print(
                f"[ERROR] Could not persist chunks for '{outcome.url}' (reason: {e!s})"
            )
            continue
        stored.append((outcome, chunk_ids))

    if stored:
        print(f"Embedding chunks for {len(stored)} pages...")
        try:
            await asyncio.gather(
                *[
                    add_page_chunks(
                        collection,
                        outcome.page_id,
                        outcome.url,
                        site["id"],
                        site["domain"],
                        chunk_ids,
                        outcome.chunks,
                    )
                    for outcome, chunk_ids in stored
                ]
            )
        except openai.APIError as e:
            print(
                f"[WARNING] Embedding failed ({e!s}); affected pages still marked crawled."
            )

    await mark_pages(
        db,
        [(outcome.page_id, outcome.status, outcome.crawled_at) for outcome in outcomes],
    )
    for outcome in outcomes:
        if outcome.status == PageStatus.CRAWLED:
            print(f"Crawled {outcome.url}.")


async def crawl_loop(
    db: aiosqlite.Connection, collection: Collection, rp: Protego, site: dict
) -> None:
    site_domain = site["domain"]
    delay = float(rp.crawl_delay(settings.user_agent) or settings.crawl_delay_seconds)
    print(f"Crawl loop started for {site_domain}.")
    while True:
        batch = await fetch_pending(db, site["id"], limit=settings.crawl_batch_size)
        if not batch:
            print(f"Crawl queue empty for {site_domain}, finishing.")
            break

        pages = [
            Page(id=row["id"], url=row["url"], depth=row["depth"]) for row in batch
        ]
        print(f"Crawling {', '.join(page.url.encoded_string() for page in pages)}...")
        await asyncio.sleep(delay)

        outcomes = await asyncio.gather(
            *(process_page(rp, page, site_domain) for page in pages)
        )
        await persist_outcomes(db, collection, site, pages, outcomes)
    print(f"Crawl loop finished for {site_domain}.")


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
