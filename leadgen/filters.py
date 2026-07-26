from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import SearchResult
from .urltools import normalize_url


BLOCKED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "podcasts.apple.com",
    "open.spotify.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "clutch.co",
    "zoominfo.com",
    "rocketreach.co",
    "datacaptive.com",
    "easyleadz.com",
    "apollo.io",
    "crunchbase.com",
    "scribd.com",
    "pinterest.com",
    "glassdoor.com",
    "indeed.com",
    "upwork.com",
    "yelp.com",
    "alle.com",
    "yellowpages.com",
    "mapquest.com",
    "healthgrades.com",
    "zocdoc.com",
    "realself.com",
    "whatclinic.com",
    "health-tourism.com",
    "bookimed.com",
    "alldentists.org",
    "appointedd.com",
    "primerus.com",
    "juniperpublishers.com",
    "midwestern.edu",
    "botoxcosmetic.com",
    "galdermaaesthetics.com",
    "medicaltourismco.com",
    "medicaltourismex.com",
    "nomadocbrazil.com",
    "digitalsmiledesign.com",
    "bark.com",
    "coachhub.com",
    "kornferry.com",
    "spencerstuart.com",
    "thinkers360.com",
    "heidrick.com",
    "icrossing.com",
    "studocu.com",
    "rhsupplies.org",
    "srol.org",
    "designsocia.com",
    "thatware.co",
    "wrebb.com",
    "propelplay.com",
    "coachbase.io",
    "makingstuffbetter.com",
    "alisonhaill.com",
    "bbb.org",
)

BLOCKED_TITLE_TERMS = (
    "podcast",
    "youtube",
    "reddit",
    "email list",
    "mailing list",
    "database",
    "top 10",
    "top 20",
    "10 best",
    "best online",
    "best ",
    "best agencies",
    "directory",
    "vacancy",
    "certificate program",
    "certification",
    "become a ",
    "course catalog",
    "university",
    "college",
    "job",
    "jobs",
    "careers",
    "career",
    "job location",
    "remote work",
    "vacancy",
    "apply now",
    "hiring",
    "biography",
    "booking info for speaking",
)

GOOD_PATH_TERMS = (
    "",
    "/",
    "about",
    "contact",
    "work-with",
    "work-with-us",
    "services",
    "book",
    "booking",
    "apply",
    "consultation",
    "portfolio",
)

UNSUITABLE_EMAIL_LOCAL_PARTS = {
    "abuse",
    "careers",
    "compliance",
    "consular",
    "digital",
    "hr",
    "humanresources",
    "investorrelations",
    "jobs",
    "legal",
    "media",
    "noreply",
    "postmaster",
    "press",
    "privacy",
    "recruiting",
    "recruitment",
    "talent",
    "talentacquisition",
    "webmaster",
}

UNSUITABLE_EMAIL_SUBSTRINGS = {
    "humanresources",
    "investorrelations",
    "recruiting",
    "recruitment",
    "talentacquisition",
}


def is_rejected_search_result(result: SearchResult) -> tuple[bool, str]:
    url = normalize_url(result.url)
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower().strip("/")
    title_snippet = f"{result.title} {result.snippet}".lower()

    blocked = blocked_domain(domain)
    if blocked:
        return True, f"blocked_domain:{blocked}"

    for term in BLOCKED_TITLE_TERMS:
        if term in title_snippet:
            return True, f"blocked_title:{term}"

    if path.endswith((".pdf", ".xlsx", ".xls", ".doc", ".docx", ".ppt", ".pptx", ".zip")):
        return True, "blocked_filetype"

    if any(part in path for part in ("/careers", "/career", "/jobs", "/job/", "/positions", "/applynow")):
        return True, "blocked_career_path"

    if len(path.split("/")) > 4 and not any(term in path for term in GOOD_PATH_TERMS if term):
        return True, "deep_non_company_page"

    return False, ""


def blocked_domain(url_or_domain: str) -> str:
    domain = urlparse(normalize_url(url_or_domain)).netloc.lower() or url_or_domain.lower()
    domain = domain.removeprefix("www.").split(":", 1)[0]
    for blocked in BLOCKED_DOMAINS:
        if domain == blocked or domain.endswith("." + blocked):
            return blocked
    return ""


def public_sector_domain(url_or_domain: str) -> str:
    domain = urlparse(normalize_url(url_or_domain)).netloc.lower() or url_or_domain.lower()
    domain = domain.removeprefix("www.").split(":", 1)[0]
    labels = domain.split(".")
    government_labels = {"gov", "gob", "gouv"}
    if (
        any(label in government_labels for label in labels)
        or (len(labels) >= 3 and labels[-2] == "go")
        or labels[-1:] == ["mil"]
    ):
        return domain
    return ""


def unsuitable_outreach_email(email: str) -> str:
    if "@" not in email:
        return ""
    local_part = email.lower().split("@", 1)[0]
    normalized = re.sub(r"[^a-z0-9]+", "", local_part)
    for marker in UNSUITABLE_EMAIL_LOCAL_PARTS:
        if normalized == marker:
            return marker
    for marker in UNSUITABLE_EMAIL_SUBSTRINGS:
        if marker in normalized:
            return marker
    return ""
