import re
import xml.etree.ElementTree as ET

import httpx


def _xml_namespace(tag: str) -> str | None:
    m = re.match(r"\{(.*)\}", tag)
    return m.group(1) if m else None


async def parse_sitemap(url: str, user_agent: str) -> list[str]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            follow_redirects=True,
            timeout=15.0,
            headers={"Accept": "application/xml", "User-Agent": user_agent},
        )
        response.raise_for_status()

    sitemap_xml = ET.fromstring(response.text)
    ns = _xml_namespace(sitemap_xml.tag)
    locs = sitemap_xml.findall(".//sm:loc", namespaces={"sm": ns} if ns else None)
    return [loc.text for loc in locs if loc.text]
