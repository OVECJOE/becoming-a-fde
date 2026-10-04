import re
import xml.etree.ElementTree as ET

import httpx
from selectolax.lexbor import LexborHTMLParser

from core.constants import BLOCK_SELECTORS, NOISE_SELECTORS


def _xml_namespace(tag: str) -> str | None:
    m = re.match(r"\{(.*)\}", tag)
    return m.group(1) if m else None


async def fetch_page(url: str, user_agent: str, content_type: str = "text/html") -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            follow_redirects=True,
            timeout=15.0,
            headers={"Accept": content_type, "User-Agent": user_agent},
        )
        response.raise_for_status()
        return response.text


async def parse_sitemap(url: str, user_agent: str) -> list[str]:
    xml_content = await fetch_page(url, user_agent, "application/xml")
    sitemap_xml = ET.fromstring(xml_content)
    ns = _xml_namespace(sitemap_xml.tag)
    locs = sitemap_xml.findall(".//sm:loc", namespaces={"sm": ns} if ns else None)
    return [loc.text for loc in locs if loc.text]


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
