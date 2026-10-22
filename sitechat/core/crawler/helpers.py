import xml.etree.ElementTree as ET
from typing import Literal

import httpx
from selectolax.lexbor import LexborHTMLParser

from core.constants import BLOCK_SELECTORS, NOISE_SELECTORS

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(follow_redirects=True, timeout=15.0)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _local_name(tag: object) -> str:
    """Element local name with any `{namespace}` prefix stripped."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


async def fetch_page(
    url: str, user_agent: str, content_type: str = "text/html", timeout: float = 15.0
) -> str | None:
    print(f"Fetching {url}...")
    try:
        response = await get_client().get(
            url,
            follow_redirects=True,
            timeout=timeout,
            headers={"Accept": content_type, "User-Agent": user_agent},
        )
        response.raise_for_status()
        print(f"Fetched {url}.")
        return response.text
    except httpx.HTTPError:
        print(f"[WARNING]: could not fetch Page({url})")
        return None


def extract_locs(root: ET.Element) -> list[str]:
    """Every `<loc>` text in the document, namespace-agnostic.

    Sitemaps sometimes omit `xmlns`, so matching on the qualified name (`sm:loc`)
    breaks; match on the local name instead.
    """
    return [
        el.text.strip()
        for el in root.iter()
        if _local_name(el.tag) == "loc" and el.text and el.text.strip()
    ]


def sitemap_kind(root: ET.Element) -> Literal["index", "urlset", "unknown"]:
    name = _local_name(root.tag).lower()
    if name == "sitemapindex":
        return "index"
    if name == "urlset":
        return "urlset"
    return "unknown"


async def fetch_sitemap_root(url: str, user_agent: str) -> ET.Element:
    content = await fetch_page(url, user_agent, content_type="application/xml")
    if content is None:
        raise httpx.HTTPError(f"could not fetch sitemap {url}")
    return ET.fromstring(content)


def extract_blocks(tree: LexborHTMLParser) -> list[str]:
    for selector in NOISE_SELECTORS:
        for node in tree.css(selector):
            node.decompose()

    blocks = []
    for node in tree.css(BLOCK_SELECTORS):
        text = node.text(separator=" ", strip=True)
        if text:
            blocks.append(text)
    return blocks
