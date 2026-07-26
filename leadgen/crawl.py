from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

from .extract import choose_followup_links, extract_contact
from .models import ExtractedContact
from .urltools import normalize_url, site_root_url


@dataclass
class CrawlResult:
    contact: ExtractedContact | None
    errors: list[str]


class Crawler:
    def __init__(
        self,
        user_agent: str | None = None,
        timeout_seconds: float | None = None,
        delay_seconds: float | None = None,
        max_followup_pages: int = 4,
    ) -> None:
        self.user_agent = user_agent or os.environ.get(
            "USER_AGENT", "LeadGeneratorBot/1.0 (+https://example.com/contact)"
        )
        self.timeout_seconds = timeout_seconds or float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "12"))
        self.delay_seconds = delay_seconds or float(os.environ.get("CRAWL_DELAY_SECONDS", "0.4"))
        self.max_followup_pages = max_followup_pages
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_fetch_at = 0.0

    def crawl(self, url: str) -> CrawlResult:
        errors: list[str] = []
        normalized = normalize_url(url)
        root_url = site_root_url(normalized)
        pages = [root_url]
        if normalized != root_url:
            pages.append(normalized)
        merged: ExtractedContact | None = None
        seen: set[str] = set()

        for page_url in pages:
            if page_url in seen:
                continue
            seen.add(page_url)
            if not self._allowed(page_url):
                errors.append(f"robots_disallowed:{page_url}")
                continue
            html = self._fetch(page_url, errors)
            if not html:
                continue
            contact = extract_contact(page_url, html)
            merged = merge_contacts(merged, contact)
            if page_url == root_url:
                pages.extend(choose_followup_links(root_url, contact.links, self.max_followup_pages))
        return CrawlResult(contact=merged, errors=errors)

    def _fetch(self, url: str, errors: list[str]) -> str:
        elapsed = time.time() - self._last_fetch_at
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type and "application/xhtml" not in content_type:
                    errors.append(f"non_html:{url}:{content_type}")
                    return ""
                body = response.read(1_500_000)
                self._last_fetch_at = time.time()
                return body.decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            errors.append(f"fetch_failed:{url}:{error}")
            return ""

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = self._robots.get(robots_url)
        if parser is None:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception:
                return True
            self._robots[robots_url] = parser
        return parser.can_fetch(self.user_agent, url)


def merge_contacts(left: ExtractedContact | None, right: ExtractedContact) -> ExtractedContact:
    if left is None:
        return right
    left.title = left.title or right.title
    left.description = left.description or right.description
    left.emails.update(right.emails)
    left.phones.update(right.phones)
    left.links.update(right.links)
    left.contact_pages.update(right.contact_pages)
    left.booking_urls.update(right.booking_urls)
    left.text_sample = (left.text_sample + " " + right.text_sample)[:3000]
    for key, values in right.social_links.items():
        left.social_links.setdefault(key, set()).update(values)
    return left
