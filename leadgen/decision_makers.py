from __future__ import annotations

import re
import unicodedata
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlparse

from .extract import EMAIL_RE, LeadHTMLParser, is_valid_email
from .search import SearchProvider
from .urltools import domain_key, normalize_url, same_site, site_root_url
from .x_founders import is_direct_person_email


ROLE_PATTERN = (
    r"co[\s-]?founder|founder(?:\s+(?:and|&)\s+ceo)?|owner|"
    r"chief executive officer|ceo|managing partner|managing director|"
    r"principal consultant|principal|president|creative director|"
    r"executive coach|business coach|leadership coach|career coach|life coach|coach"
)
ROLE_MATCH = rf"(?i:{ROLE_PATTERN})"
NAME_WORD = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’-]*[A-Za-zÀ-ÖØ-öø-ÿ]"
NAME_INITIAL = r"[A-ZÀ-ÖØ-Þ]\."
NAME_TOKEN = rf"(?:{NAME_WORD}|{NAME_INITIAL})"
PERSON_NAME = rf"({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{1,3}})"

PERSON_PATTERNS = (
    re.compile(
        rf"{PERSON_NAME}\s*(?:,|[-–—|])\s*(?i:(?:is\s+)?(?:the\s+)?)({ROLE_MATCH})\b",
    ),
    re.compile(
        rf"\b({ROLE_MATCH})\s*(?:,|:|[-–—|])?\s*{PERSON_NAME}",
    ),
    re.compile(
        rf"\b{PERSON_NAME}\s+(?i:(?:is|serves\s+as)\s+(?:the\s+)?)({ROLE_MATCH})\b",
    ),
    re.compile(rf"\b(?i:(?:founded|led|owned)\s+by)\s+{PERSON_NAME}"),
)
IDENTITY_PATTERNS = (
    re.compile(rf"\b(?i:meet|about|contact)\s+{PERSON_NAME}"),
    re.compile(rf"\b(?i:work(?:ing)?\s+with)\s+{PERSON_NAME}"),
    re.compile(rf"\b(?i:book(?:\s+\w+){{0,3}}\s+with)\s+{PERSON_NAME}"),
)

PAGE_HINTS = (
    "about",
    "team",
    "leadership",
    "founder",
    "owner",
    "company",
    "people",
    "who-we-are",
)

EXTRA_GENERIC_EMAIL_PARTS = {
    "care",
    "dentalcare",
    "escape",
    "general",
    "hr",
    "manager",
    "operations",
    "service",
    "studio",
}

BAD_NAME_WORDS = {
    "about",
    "agency",
    "business",
    "company",
    "contact",
    "digital",
    "executive",
    "founder",
    "leadership",
    "marketing",
    "medical",
    "owner",
    "services",
    "team",
    "with",
}

LOW_VALUE_PATH_HINTS = (
    "blog",
    "case-study",
    "case_study",
    "collection",
    "news",
    "post",
    "praise",
    "resources",
    "tag",
    "testimonial",
    ".pdf",
)


@dataclass(frozen=True)
class PersonCandidate:
    name: str
    title: str
    evidence: str
    evidence_url: str
    score: int


@dataclass(frozen=True)
class PublishedEmail:
    email: str
    evidence_url: str
    evidence: str


@dataclass(frozen=True)
class DecisionMakerResult:
    name: str = ""
    title: str = ""
    email: str = ""
    email_status: str = ""
    evidence_url: str = ""
    evidence: str = ""
    source: str = ""
    status: str = "decision_maker_not_found"


@dataclass(frozen=True)
class PageDocument:
    url: str
    text: str
    links: tuple[str, ...]
    emails: tuple[str, ...]


def enrich_decision_maker(
    row: dict[str, str],
    search_provider: SearchProvider,
    timeout_seconds: float = 6,
) -> DecisionMakerResult:
    website = row.get("website", "")
    domain = domain_key(website)
    if not domain:
        return DecisionMakerResult(status="missing_website_domain")

    extra_roles = ""
    if row.get("segment") == "coach":
        extra_roles = (
            ' OR "executive coach" OR "business coach" OR "leadership coach" '
            'OR "career coach" OR "life coach"'
        )
    role_query = (
        f'site:{domain} ("founder" OR "co-founder" OR "owner" OR "CEO" '
        f'OR "managing partner" OR "principal" OR "president"{extra_roles})'
    )
    search_results = search_provider.search(role_query, 8)
    candidates: list[PersonCandidate] = []
    published_emails: list[PublishedEmail] = []
    search_urls: list[str] = []

    for result in search_results:
        text = clean_text(f"{result.title}. {result.snippet}")
        candidates.extend(extract_person_candidates(text, result.url))
        published_emails.extend(extract_published_emails(text, result.url))
        if same_site(website, result.url):
            search_urls.append(result.url)

    documents = crawl_decision_pages(
        website,
        seed_urls=search_urls,
        timeout_seconds=timeout_seconds,
    )
    for document in documents:
        candidates.extend(extract_person_candidates(document.text, document.url))
        for email in document.emails:
            published_emails.append(
                PublishedEmail(
                    email=email,
                    evidence_url=document.url,
                    evidence=evidence_window(document.text, email),
                )
            )

    general_email = row.get("email", "").strip().lower()
    if is_valid_email(general_email):
        published_emails.append(
            PublishedEmail(
                email=general_email,
                evidence_url=website,
                evidence=f"Published business-site email: {general_email}",
            )
        )

    candidates = dedupe_candidates(candidates)
    published_emails = dedupe_emails(published_emails)
    match = match_person_email(candidates, published_emails)
    if match:
        candidate, email = match
        return DecisionMakerResult(
            name=candidate.name,
            title=candidate.title,
            email=email.email,
            email_status="public_person_email_needs_human_spot_check",
            evidence_url=email.evidence_url or candidate.evidence_url,
            evidence=f"{candidate.evidence} | {email.evidence}"[:1000],
            source="public_web",
            status="decision_maker_email_found",
        )

    if candidates:
        candidate = candidates[0]
        extra_emails = search_person_email(
            row,
            candidate,
            domain,
            search_provider,
        )
        match = match_person_email([candidate], extra_emails)
        if match:
            matched_candidate, email = match
            return DecisionMakerResult(
                name=matched_candidate.name,
                title=matched_candidate.title,
                email=email.email,
                email_status="public_person_email_needs_human_spot_check",
                evidence_url=email.evidence_url,
                evidence=f"{matched_candidate.evidence} | {email.evidence}"[:1000],
                source="public_search",
                status="decision_maker_email_found",
            )
        return DecisionMakerResult(
            name=candidate.name,
            title=candidate.title,
            evidence_url=candidate.evidence_url,
            evidence=candidate.evidence,
            source="public_web",
            status="decision_maker_found_email_missing",
        )
    return DecisionMakerResult(status="decision_maker_not_found")


def search_person_email(
    row: dict[str, str],
    candidate: PersonCandidate,
    domain: str,
    search_provider: SearchProvider,
) -> list[PublishedEmail]:
    business = row.get("business_name", "")
    query = (
        f'"{candidate.name}" "{business}" '
        f'("email" OR "@{domain}") ("founder" OR "owner" OR "CEO")'
    )
    results = search_provider.search(query, 6)
    emails: list[PublishedEmail] = []
    for result in results:
        text = clean_text(f"{result.title}. {result.snippet}")
        emails.extend(extract_published_emails(text, result.url))
    return dedupe_emails(emails)


def crawl_decision_pages(
    website: str,
    seed_urls: list[str],
    timeout_seconds: float,
    max_pages: int = 6,
) -> list[PageDocument]:
    root = site_root_url(website)
    robots = load_robots(root, timeout_seconds)
    queue = [root]
    queue.extend(url for url in seed_urls if same_site(root, url))
    documents: list[PageDocument] = []
    seen: set[str] = set()

    while queue and len(documents) < max_pages:
        url = normalize_url(queue.pop(0))
        if url in seen or not same_site(root, url):
            continue
        seen.add(url)
        if robots is not None and not robots.can_fetch("NexStudioResearchBot/1.0", url):
            continue
        html = fetch_html(url, timeout_seconds)
        if not html:
            continue
        parser = LeadHTMLParser(url)
        parser.feed(html)
        text = clean_text(" ".join(parser.text_parts))[:50_000]
        emails = tuple(
            sorted(
                {
                    email.lower()
                    for email in EMAIL_RE.findall(html)
                    if is_valid_email(email)
                }
            )
        )
        links = tuple(sorted(parser.links))
        documents.append(PageDocument(url=url, text=text, links=links, emails=emails))
        for link in links:
            lower = link.lower()
            if same_site(root, link) and any(hint in lower for hint in PAGE_HINTS):
                queue.append(link)
    return documents


def load_robots(root_url: str, timeout_seconds: float) -> urllib.robotparser.RobotFileParser | None:
    parsed = urlparse(root_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        request = urllib.request.Request(
            robots_url,
            headers={"User-Agent": "NexStudioResearchBot/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read(500_000).decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(text.splitlines())
    return parser


def fetch_html(url: str, timeout_seconds: float) -> str:
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "NexStudioResearchBot/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return ""
            return response.read(1_500_000).decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return ""


def extract_person_candidates(text: str, evidence_url: str) -> list[PersonCandidate]:
    cleaned = clean_text(text)
    candidates: list[PersonCandidate] = []
    source_score = evidence_source_score(evidence_url)
    for index, pattern in enumerate(PERSON_PATTERNS):
        for match in pattern.finditer(cleaned):
            groups = [value for value in match.groups() if value]
            role = next((value for value in groups if re.fullmatch(ROLE_PATTERN, value, re.I)), "")
            name = next((value for value in groups if value != role), "")
            name = clean_person_name(name)
            if not plausible_person_name(name):
                continue
            evidence = evidence_window(cleaned, match.group(0))
            candidates.append(
                PersonCandidate(
                    name=name,
                    title=normalize_role(role or "Founder"),
                    evidence=evidence,
                    evidence_url=evidence_url,
                    score=role_score(role) - index + source_score,
                )
            )
    for pattern in IDENTITY_PATTERNS:
        for match in pattern.finditer(cleaned):
            name = clean_person_name(match.group(1))
            if not plausible_person_name(name):
                continue
            candidates.append(
                PersonCandidate(
                    name=name,
                    title="Main Contact",
                    evidence=evidence_window(cleaned, match.group(0)),
                    evidence_url=evidence_url,
                    score=55 + source_score,
                )
            )
    return candidates


def extract_published_emails(text: str, evidence_url: str) -> list[PublishedEmail]:
    cleaned = clean_text(text)
    return [
        PublishedEmail(
            email=email.lower(),
            evidence_url=evidence_url,
            evidence=evidence_window(cleaned, email),
        )
        for email in EMAIL_RE.findall(cleaned)
        if is_person_level_email(email)
    ]


def match_person_email(
    candidates: list[PersonCandidate],
    emails: list[PublishedEmail],
) -> tuple[PersonCandidate, PublishedEmail] | None:
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        for email in emails:
            if is_person_level_email(email.email) and email_matches_name(email.email, candidate.name):
                return candidate, email
    return None


def email_matches_name(email: str, name: str) -> bool:
    local = email.lower().split("@", 1)[0].split("+", 1)[0]
    local_compact = normalize_ascii(local)
    tokens = [
        normalize_ascii(token)
        for token in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’.-]+", name)
    ]
    tokens = [token for token in tokens if len(token) >= 2]
    if len(tokens) < 2:
        return False
    first, last = tokens[0], tokens[-1]
    accepted = {
        first,
        last,
        first + last,
        last + first,
        first[:1] + last,
        first + last[:1],
    }
    return local_compact in accepted or (
        len(last) >= 4
        and last in local_compact
        and first[:1] in local_compact
    )


def is_person_level_email(email: str) -> bool:
    normalized = (email or "").strip().lower()
    if not is_direct_person_email(normalized):
        return False
    local = normalized.split("@", 1)[0].split("+", 1)[0]
    compact = re.sub(r"[^a-z0-9]", "", local)
    return compact not in EXTRA_GENERIC_EMAIL_PARTS and not re.fullmatch(r"[0-9a-f]{20,}", compact)


def dedupe_candidates(candidates: list[PersonCandidate]) -> list[PersonCandidate]:
    by_name: dict[str, PersonCandidate] = {}
    for candidate in candidates:
        key = normalize_name(candidate.name)
        existing = by_name.get(key)
        if existing is None or candidate.score > existing.score:
            by_name[key] = candidate
    return sorted(by_name.values(), key=lambda item: (-item.score, item.name.lower()))


def dedupe_emails(emails: list[PublishedEmail]) -> list[PublishedEmail]:
    by_email: dict[str, PublishedEmail] = {}
    for email in emails:
        by_email.setdefault(email.email.lower(), email)
    return list(by_email.values())


def plausible_person_name(name: str) -> bool:
    tokens = [token for token in name.split() if token]
    if not (2 <= len(tokens) <= 4) or len(name) > 70:
        return False
    lower_tokens = {re.sub(r"[^a-z]", "", token.lower()) for token in tokens}
    return not lower_tokens.intersection(BAD_NAME_WORDS)


def clean_person_name(value: str) -> str:
    return " ".join(clean_text(value).strip(" ,:;|-–—").split())


def normalize_name(value: str) -> str:
    return normalize_ascii(value)


def normalize_ascii(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return re.sub(r"[^a-z0-9]", "", decomposed.encode("ascii", "ignore").decode("ascii"))


def normalize_role(value: str) -> str:
    lowered = clean_text(value).lower()
    if "co-founder" in lowered or "cofounder" in lowered:
        return "Co-Founder"
    if "founder" in lowered:
        return "Founder"
    if "chief executive" in lowered or lowered == "ceo":
        return "CEO"
    if "managing partner" in lowered:
        return "Managing Partner"
    if "managing director" in lowered:
        return "Managing Director"
    if "principal consultant" in lowered:
        return "Principal Consultant"
    if "principal" in lowered:
        return "Principal"
    if "president" in lowered:
        return "President"
    if "owner" in lowered:
        return "Owner"
    if "creative director" in lowered:
        return "Creative Director"
    if "executive coach" in lowered:
        return "Executive Coach"
    if "business coach" in lowered:
        return "Business Coach"
    if "leadership coach" in lowered:
        return "Leadership Coach"
    if "career coach" in lowered:
        return "Career Coach"
    if "life coach" in lowered:
        return "Life Coach"
    if lowered == "coach":
        return "Coach"
    return value.title()


def role_score(value: str) -> int:
    role = normalize_role(value)
    return {
        "Co-Founder": 100,
        "Founder": 95,
        "Owner": 90,
        "CEO": 85,
        "Managing Partner": 80,
        "Managing Director": 75,
        "Principal Consultant": 74,
        "Principal": 70,
        "President": 65,
        "Creative Director": 62,
        "Executive Coach": 60,
        "Business Coach": 59,
        "Leadership Coach": 58,
        "Career Coach": 57,
        "Life Coach": 56,
        "Coach": 50,
    }.get(role, 50)


def evidence_source_score(value: str) -> int:
    parsed = urlparse(value)
    path = parsed.path.lower().strip("/")
    if not path:
        return 20
    score = 0
    if any(hint in path for hint in ("about", "team", "leadership", "who-we-are", "people")):
        score += 15
    if any(hint in path for hint in LOW_VALUE_PATH_HINTS):
        score -= 35
    return score


def evidence_window(text: str, needle: str, radius: int = 180) -> str:
    lower = text.lower()
    index = lower.find(needle.lower())
    if index < 0:
        return clean_text(text)[: radius * 2]
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return clean_text(text[start:end])


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()
