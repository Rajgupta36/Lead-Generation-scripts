from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from .models import ExtractedContact
from .urltools import normalize_url, same_site


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
CONTACT_HINTS = ("contact", "about", "service", "work-with", "booking", "book", "consultation")
BOOKING_HINTS = ("calendly.com", "acuityscheduling.com", "book", "booking", "schedule", "consultation")
SOCIAL_HOSTS = {
    "linkedin": "linkedin.com",
    "instagram": "instagram.com",
    "youtube": "youtube.com",
}


class LeadHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.description = ""
        self.links: set[str] = set()
        self._in_title = False
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.description = attrs_dict.get("content", "")
        if tag.lower() == "a" and attrs_dict.get("href"):
            href = attrs_dict["href"].strip()
            if href.startswith(("mailto:", "tel:")):
                self.links.add(href)
            elif href and not href.startswith(("javascript:", "#")):
                self.links.add(normalize_url(href, self.base_url))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if not clean:
            return
        if self._in_title:
            self.title += clean + " "
        self.text_parts.append(clean)


def extract_contact(url: str, html: str) -> ExtractedContact:
    parser = LeadHTMLParser(url)
    parser.feed(html)
    text = " ".join(parser.text_parts)
    contact = ExtractedContact(
        url=normalize_url(url),
        title=parser.title.strip(),
        description=parser.description.strip(),
        links=parser.links,
        text_sample=text[:2000],
    )

    contact.emails.update(email.lower() for email in EMAIL_RE.findall(html) if is_valid_email(email))
    for link in parser.links:
        if link.startswith("mailto:"):
            email = link.removeprefix("mailto:").split("?", 1)[0].strip()
            if email and is_valid_email(email):
                contact.emails.add(email.lower())
        if link.startswith("tel:"):
            phone = link.removeprefix("tel:").strip()
            digits = re.sub(r"\D", "", phone)
            if phone and is_valid_phone_candidate(phone, digits):
                contact.phones.add(phone)

    for phone in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", phone)
        if is_valid_phone_candidate(phone, digits):
            contact.phones.add(" ".join(phone.split()))

    for link in parser.links:
        lower = link.lower()
        if any(hint in lower for hint in CONTACT_HINTS) and same_site(url, link):
            contact.contact_pages.add(link)
        if any(hint in lower for hint in BOOKING_HINTS):
            contact.booking_urls.add(link)
        parsed_host = urlparse(link).netloc.lower()
        for name, host in SOCIAL_HOSTS.items():
            if host in parsed_host:
                contact.social_links.setdefault(name, set()).add(link)

    return contact


def choose_followup_links(base_url: str, links: set[str], max_links: int) -> list[str]:
    scored: list[tuple[int, str]] = []
    for link in links:
        if not same_site(base_url, link):
            continue
        lower = link.lower()
        score = 0
        for index, hint in enumerate(CONTACT_HINTS):
            if hint in lower:
                score += 20 - index
        if score:
            scored.append((score, link))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [link for _, link in scored[:max_links]]


def is_valid_email(email: str) -> bool:
    if "%" in email or "\ufffd" in email:
        return False
    local, _, domain = email.partition("@")
    blocked_domains = {
        "sentry.io",
        "sentry.wixpress.com",
        "sentry-next.wixpress.com",
        "ingest.us.sentry.io",
    }
    blocked_tlds = {"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js"}
    tld = domain.rsplit(".", 1)[-1].lower() if "." in domain else ""
    if domain.lower() in blocked_domains or domain.lower().endswith(".sentry.io") or "sentry" in domain.lower():
        return False
    return bool(local and domain and "." in domain and len(email) <= 254 and tld not in blocked_tlds)


def is_valid_phone_candidate(raw_phone: str, digits: str) -> bool:
    if not (10 <= len(digits) <= 16):
        return False
    if re.search(r"202[0-9]", raw_phone):
        return False
    if raw_phone.strip().isdigit():
        return False
    if re.search(r"\d+\.\d+$", raw_phone.strip()) and not re.search(r"[+\s()-]", raw_phone):
        return False
    if "0123456789" in digits or "9876543210" in digits:
        return False
    if not (
        raw_phone.strip().startswith("+")
        or "(" in raw_phone
        or re.search(r"\d{3}[-.\s]\d{3}[-.\s]\d{4}", raw_phone)
        or re.search(r"\d{2,4}\s\d{2}\s\d{2}\s\d{2}\s\d{2}", raw_phone)
    ):
        return False
    return True
