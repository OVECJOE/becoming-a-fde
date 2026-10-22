import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
TRACKING_PARAM_PREFIXES = ("utm_", "mtm_", "pk_", "hsa_")
TRACKING_PARAMS = frozenset(
    {
        "_hsenc",
        "_hsmi",
        "dclid",
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "ref",
        "referrer",
        "source",
        "twclid",
        "yclid",
    }
)
DEFAULT_PORTS = frozenset({80, 443})


def _normalize_escapes(segment: str) -> str:
    def replace(match: re.Match[str]) -> str:
        char = bytes([int(match.group(1), 16)]).decode("latin-1")
        return char if char in UNRESERVED else f"%{match.group(1).upper()}"

    return PERCENT_ESCAPE.sub(replace, segment)


def _normalize_path(raw_path: str) -> str:
    escaped = quote(_normalize_escapes(raw_path), safe="/:@!$&'()*+,;=%")
    segments: list[str] = []
    for segment in escaped.split("/"):
        if not segment or segment == ".":
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    return "/" + "/".join(segments)


def _is_tracking_param(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PARAM_PREFIXES)


def _normalize_query(raw_query: str) -> str:
    pairs = [
        (key, value)
        for key, value in parse_qsl(raw_query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    return urlencode(sorted(pairs))


def _normalize_host(host: str) -> str:
    candidate = host.rstrip(".").lower()
    if candidate.startswith("www."):
        candidate = candidate[4:]
    if not candidate or candidate.isascii():
        return candidate
    try:
        return candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return candidate


def normalize_host(host: str) -> str:
    candidate = host.strip()
    if "://" not in candidate:
        candidate = f"//{candidate}"
    try:
        parsed = urlsplit(candidate)
        normalized = _normalize_host(parsed.hostname or "")
    except ValueError:
        normalized = ""
    return normalized or host.strip().lower()


def normalize_url(url: str) -> str:
    """Canonical form: https scheme, lowercase www-stripped host, IDNA-encoded,
    no userinfo/port/fragment, resolved dot-segments, collapsed slashes, no
    trailing slash, percent-escapes normalized, tracking params dropped,
    remaining query params sorted. Idempotent; non-http(s) input returned stripped."""
    candidate = url.strip()
    try:
        parsed = urlsplit(candidate)
        host = _normalize_host(parsed.hostname or "")
        port = parsed.port
    except ValueError:
        return candidate
    if parsed.scheme.lower() not in ("http", "https") or not host:
        return candidate

    authority = host if port is None or port in DEFAULT_PORTS else f"{host}:{port}"
    query = _normalize_query(parsed.query)
    return f"https://{authority}{_normalize_path(parsed.path)}" + (
        f"?{query}" if query else ""
    )


def url_host(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return ""
    return _normalize_host(parsed.hostname or "")
