from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse


TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url: str, base: str | None = None) -> str:
    if base:
        url = urljoin(base, url)
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        parsed = urlparse("https://" + url.strip())
    scheme = "https" if parsed.scheme in {"http", "https"} else parsed.scheme
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query = parse_qs(parsed.query, keep_blank_values=False)
    clean_query = {
        key: values
        for key, values in query.items()
        if key not in TRACKING_KEYS and not key.startswith(TRACKING_PREFIXES)
    }
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse((scheme, netloc, path, "", urlencode(clean_query, doseq=True), ""))


def domain_key(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    return parsed.netloc.lower()


def site_root_url(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    if not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme or "https", parsed.netloc, "/", "", "", ""))


def same_site(url: str, candidate: str) -> bool:
    return domain_key(url) == domain_key(candidate)
