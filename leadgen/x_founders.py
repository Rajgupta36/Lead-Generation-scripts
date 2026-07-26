from __future__ import annotations

import csv
import html
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .config import load_env
from .export import append_log
from .extract import is_valid_email
from .models import SearchResult
from .search import SearchProvider, create_provider, is_transient_search_error


FOUNDER_PATTERNS = (
    ("co-founder", re.compile(r"\bco[\s-]?founder\b", re.IGNORECASE)),
    ("founder", re.compile(r"\bfounder\b", re.IGNORECASE)),
)

FOLLOWER_PATTERN = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?\s*[KMB]?)\s+followers?\b",
    re.IGNORECASE,
)

RESERVED_X_PATHS = {
    "about",
    "compose",
    "explore",
    "hashtag",
    "home",
    "i",
    "intent",
    "login",
    "messages",
    "notifications",
    "privacy",
    "search",
    "settings",
    "share",
    "signup",
    "tos",
}

PROFILE_SUBPATHS = {"articles", "highlights", "likes", "media", "with_replies"}

CANDIDATE_FIELDS = [
    "handle",
    "display_name",
    "profile_url",
    "bio",
    "founder_evidence",
    "indexed_followers",
    "indexed_follower_status",
    "source_provider",
    "source_queries",
    "source_urls",
    "discovered_at",
    "review_status",
]

GROK_REVIEW_FIELDS = [
    "handle",
    "founder_confirmed",
    "founder_evidence",
    "founder_name",
    "founder_title",
    "blue_check",
    "check_type",
    "live_followers",
    "location",
    "website_url",
    "profile_url",
    "email_owner_confirmed",
    "public_email",
    "email_evidence_url",
    "email_evidence",
    "notes",
]

LEAD_FIELDS = [
    "lead_id",
    "handle",
    "display_name",
    "contact_name",
    "title",
    "profile_url",
    "bio",
    "founder_evidence",
    "premium_status",
    "live_followers",
    "location",
    "website_url",
    "email",
    "email_status",
    "email_evidence_url",
    "email_evidence",
    "source_provider",
    "source_queries",
    "verified_at",
    "review_status",
    "notes",
]

EMAIL_RESEARCH_FIELDS = [
    "handle",
    "contact_name",
    "title",
    "profile_url",
    "website_url",
    "public_email",
    "email_evidence_url",
    "missing_reason",
    "review_status",
]

ACCEPTED_PREMIUM_TYPES = {"premium", "premium+", "premium_plus"}
AFFIRMATIVE_VALUES = {"1", "true", "yes", "y"}
GENERIC_EMAIL_LOCAL_PARTS = {
    "admin",
    "billing",
    "book",
    "booking",
    "bookings",
    "business",
    "careers",
    "contact",
    "customerservice",
    "enquiries",
    "enquiry",
    "help",
    "hello",
    "hi",
    "info",
    "inquiries",
    "inquiry",
    "jobs",
    "legal",
    "mail",
    "marketing",
    "media",
    "office",
    "partnerships",
    "press",
    "privacy",
    "reception",
    "sales",
    "support",
    "team",
}


@dataclass
class XFounderCandidate:
    handle: str
    display_name: str
    profile_url: str
    bio: str
    founder_evidence: str
    indexed_followers: int | None
    source_provider: str
    source_queries: set[str] = field(default_factory=set)
    source_urls: set[str] = field(default_factory=set)

    @property
    def indexed_follower_status(self) -> str:
        if self.indexed_followers is None:
            return "unknown_needs_live_check"
        if self.indexed_followers < 1000:
            return "under_1000_indexed"
        return "1000_or_more_excluded"


def build_x_founder_dorks() -> list[str]:
    titles = ('"Founder"', '"Co-Founder"', '"Cofounder"')
    contexts = (
        "",
        "SaaS",
        "startup",
        "software",
        "AI",
        "app",
        "agency",
        "studio",
        "bootstrapped",
        "ecommerce",
        "entrepreneur",
        "building",
    )
    return [
        " ".join(part for part in ("site:x.com", title, context, '"Followers"') if part)
        for title in titles
        for context in contexts
    ]


def clean_search_text(value: str) -> str:
    unescaped = html.unescape(value or "")
    without_tags = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", without_tags).strip()


def extract_x_profile(url: str) -> tuple[str, str] | None:
    candidate = (url or "").strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = "https://" + candidate.lstrip("/")
    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").lower()
    if host.startswith("www.") or host.startswith("mobile."):
        host = host.split(".", 1)[1]
    if host not in {"x.com", "twitter.com"}:
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    handle = parts[0].lstrip("@")
    if handle.lower() in RESERVED_X_PATHS or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
        return None
    if len(parts) > 1 and parts[1].lower() not in PROFILE_SUBPATHS:
        return None
    return handle, f"https://x.com/{handle}"


def parse_follower_count(value: str) -> int | None:
    match = FOLLOWER_PATTERN.search(clean_search_text(value))
    if not match:
        return None
    raw = match.group(1).replace(" ", "").replace(",", "")
    multiplier = 1
    if raw[-1:].upper() in {"K", "M", "B"}:
        suffix = raw[-1].upper()
        raw = raw[:-1]
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
    try:
        return int(float(raw) * multiplier)
    except ValueError:
        return None


def founder_evidence(value: str) -> str:
    text = clean_search_text(value)
    for label, pattern in FOUNDER_PATTERNS:
        if pattern.search(text):
            return label
    return ""


def parse_display_name(title: str, handle: str) -> str:
    cleaned = clean_search_text(title)
    patterns = (
        rf"\bby\s+(.+?)\s+\(@{re.escape(handle)}\)",
        rf"^(.+?)\s+\(@{re.escape(handle)}\)",
        r"^(.+?)\s+(?:/ X|on X|— X|- X)$",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            name = match.group(1).strip(" -–—|")
            if name:
                return name
    return handle


def candidate_from_search_result(
    result: SearchResult,
    query: str,
    provider_name: str,
) -> XFounderCandidate | None:
    profile = extract_x_profile(result.url)
    if not profile:
        return None
    handle, profile_url = profile
    bio = clean_search_text(result.snippet)
    evidence = founder_evidence(bio)
    if not evidence:
        return None
    return XFounderCandidate(
        handle=handle,
        display_name=parse_display_name(result.title, handle),
        profile_url=profile_url,
        bio=bio,
        founder_evidence=evidence,
        indexed_followers=parse_follower_count(bio),
        source_provider=result.source_provider or provider_name,
        source_queries={query},
        source_urls={result.url},
    )


def merge_candidate(existing: XFounderCandidate, incoming: XFounderCandidate) -> XFounderCandidate:
    existing.source_queries.update(incoming.source_queries)
    existing.source_urls.update(incoming.source_urls)
    if existing.display_name == existing.handle and incoming.display_name != incoming.handle:
        existing.display_name = incoming.display_name
    if len(incoming.bio) > len(existing.bio):
        existing.bio = incoming.bio
        existing.founder_evidence = incoming.founder_evidence
    if existing.indexed_followers is None and incoming.indexed_followers is not None:
        existing.indexed_followers = incoming.indexed_followers
    return existing


def discover_x_founders(
    provider_name: str,
    env_path: Path,
    out_dir: Path,
    target: int = 100,
    results_per_query: int = 20,
    max_search_requests: int = 200,
    batch_size: int = 20,
    search_results_file: str | None = None,
    queries: list[str] | None = None,
    provider: SearchProvider | None = None,
) -> list[XFounderCandidate]:
    load_env(env_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    reset_run_log(out_dir)
    search_provider = provider or create_provider(provider_name, search_results_file)
    candidates_by_handle: dict[str, XFounderCandidate] = {}
    search_queries = queries or build_x_founder_dorks()
    candidate_target = max(target * 5, target)

    for query_number, query in enumerate(search_queries, start=1):
        if query_number > max_search_requests:
            append_log(
                out_dir,
                {
                    "event": "search_budget_reached",
                    "max_search_requests": max_search_requests,
                    "candidates": len(candidates_by_handle),
                },
            )
            break
        try:
            results = search_provider.search(query, results_per_query)
        except Exception as error:
            append_log(
                out_dir,
                {
                    "event": "x_founder_search_failed",
                    "query": query,
                    "error": str(error),
                    "transient": is_transient_search_error(error),
                },
            )
            continue

        for result in results:
            candidate = candidate_from_search_result(result, query, provider_name)
            if candidate is None:
                continue
            key = candidate.handle.lower()
            if key in candidates_by_handle:
                candidates_by_handle[key] = merge_candidate(candidates_by_handle[key], candidate)
            else:
                candidates_by_handle[key] = candidate

        eligible_count = sum(
            candidate.indexed_followers is None or candidate.indexed_followers < 1000
            for candidate in candidates_by_handle.values()
        )
        if eligible_count >= candidate_target:
            break

    review_candidates = [
        candidate
        for candidate in candidates_by_handle.values()
        if candidate.indexed_followers is None or candidate.indexed_followers < 1000
    ]
    review_candidates.sort(
        key=lambda item: (
            item.indexed_followers is None,
            item.indexed_followers if item.indexed_followers is not None else 10**12,
            item.handle.lower(),
        )
    )
    write_candidates(out_dir / "candidates_review.csv", review_candidates)
    write_grok_batches(out_dir, review_candidates, batch_size=batch_size)
    append_log(
        out_dir,
        {
            "event": "x_founder_discovery_completed",
            "target": target,
            "review_candidates": len(review_candidates),
            "all_founder_profiles_seen": len(candidates_by_handle),
        },
    )
    return review_candidates


def write_candidates(path: Path, candidates: list[XFounderCandidate]) -> None:
    discovered_at = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "handle": candidate.handle,
                    "display_name": candidate.display_name,
                    "profile_url": candidate.profile_url,
                    "bio": candidate.bio,
                    "founder_evidence": candidate.founder_evidence,
                    "indexed_followers": (
                        candidate.indexed_followers if candidate.indexed_followers is not None else ""
                    ),
                    "indexed_follower_status": candidate.indexed_follower_status,
                    "source_provider": candidate.source_provider,
                    "source_queries": " | ".join(sorted(candidate.source_queries)),
                    "source_urls": " | ".join(sorted(candidate.source_urls)),
                    "discovered_at": discovered_at,
                    "review_status": "needs_grok_review",
                }
            )


def build_grok_prompt(handles: list[str]) -> str:
    handle_list = ", ".join(f"@{handle}" for handle in handles)
    return f"""Use X Search to inspect the current public X profile for each handle below.

Handles: {handle_list}

Return CSV only, with exactly this header:
{",".join(GROK_REVIEW_FIELDS)}

Rules:
- founder_confirmed=yes only when the current profile bio explicitly says founder, co-founder, or cofounder. Do not accept owner alone and do not treat "founding engineer" as founder.
- founder_evidence must contain the exact short phrase from the current bio.
- founder_name must be the person's public name, and founder_title must be Founder or Co-Founder.
- blue_check=yes only when the profile currently has a blue check.
- check_type=premium only when the blue badge indicates Premium/Premium+ and there is no Verified Organization affiliation. Use affiliate, gold, gray, none, or unknown otherwise.
- live_followers must be the current integer count with no commas or suffix. Leave it blank if unavailable.
- Copy public profile location and website URL when present; otherwise leave them blank.
- Search the public X profile, public posts, and linked public website for an email explicitly published for this same founder.
- email_owner_confirmed=yes only when the evidence explicitly connects the email to this founder. Do not infer or generate an email pattern.
- public_email must be a person-level address. Reject role inboxes such as info@, hello@, contact@, team@, support@, sales@, admin@, office@, marketing@, or founder@.
- email_evidence_url must be the exact public page containing the email, and email_evidence must be a short snippet that includes the exact email. Leave all email fields blank when no direct public email is found.
- Do not guess missing values. Include one row per requested handle."""


def write_grok_batches(out_dir: Path, candidates: list[XFounderCandidate], batch_size: int) -> None:
    normalized_batch_size = max(1, min(batch_size, 20))
    batch_path = out_dir / "grok_review_batches.csv"
    prompt_path = out_dir / "grok_prompts.md"
    prompt_sections = []
    with batch_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["batch_id", "handles", "grok_prompt"])
        writer.writeheader()
        for offset in range(0, len(candidates), normalized_batch_size):
            batch = candidates[offset : offset + normalized_batch_size]
            batch_id = f"B{offset // normalized_batch_size + 1:04d}"
            handles = [candidate.handle for candidate in batch]
            prompt = build_grok_prompt(handles)
            writer.writerow(
                {
                    "batch_id": batch_id,
                    "handles": " ".join(f"@{item}" for item in handles),
                    "grok_prompt": prompt,
                }
            )
            prompt_sections.append(f"## {batch_id}\n\n```text\n{prompt}\n```")
    prompt_path.write_text(
        "# Grok X founder review prompts\n\n" + "\n\n".join(prompt_sections) + "\n",
        encoding="utf-8",
    )


def normalize_boolean(value: str) -> bool:
    return (value or "").strip().lower() in AFFIRMATIVE_VALUES


def normalize_premium_type(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "_").replace("-", "_")


def parse_live_followers(value: str) -> int | None:
    cleaned = (value or "").strip().replace(",", "")
    if not re.fullmatch(r"\d+", cleaned):
        return None
    return int(cleaned)


def qualify_review_row(row: dict[str, str]) -> tuple[bool, str]:
    if not normalize_boolean(row.get("founder_confirmed", "")):
        return False, "founder_not_confirmed"
    if not founder_evidence(row.get("founder_evidence", "")):
        return False, "founder_evidence_missing"
    if not normalize_boolean(row.get("blue_check", "")):
        return False, "blue_check_not_confirmed"
    premium_type = normalize_premium_type(row.get("check_type", ""))
    if premium_type not in ACCEPTED_PREMIUM_TYPES:
        return False, f"premium_type_not_accepted:{premium_type or 'missing'}"
    followers = parse_live_followers(row.get("live_followers", ""))
    if followers is None:
        return False, "live_followers_missing"
    if followers >= 1000:
        return False, "live_followers_1000_or_more"
    email = (row.get("public_email") or "").strip().lower()
    if not normalize_boolean(row.get("email_owner_confirmed", "")):
        return False, "founder_email_owner_not_confirmed"
    if not is_direct_person_email(email):
        return False, "founder_email_missing_or_generic"
    evidence_url = (row.get("email_evidence_url") or "").strip()
    if not is_public_http_url(evidence_url):
        return False, "founder_email_evidence_url_missing"
    evidence = (row.get("email_evidence") or "").strip()
    if email not in evidence.lower():
        return False, "founder_email_not_in_evidence"
    return True, ""


def is_direct_person_email(email: str) -> bool:
    normalized = (email or "").strip().lower()
    if not is_valid_email(normalized):
        return False
    local = normalized.split("@", 1)[0].split("+", 1)[0]
    compact = re.sub(r"[^a-z0-9]", "", local)
    first_token = re.split(r"[._+-]", local, maxsplit=1)[0]
    if compact in GENERIC_EMAIL_LOCAL_PARTS or first_token in GENERIC_EMAIL_LOCAL_PARTS:
        return False
    if compact in {"ceo", "founder", "cofounder", "owner"}:
        return False
    return True


def is_public_http_url(value: str) -> bool:
    parsed = urlsplit((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def finalize_x_founders(
    review_file: Path,
    candidates_file: Path,
    out_dir: Path,
    target: int = 100,
) -> list[dict[str, str]]:
    candidates = read_csv_by_handle(candidates_file, required_fields=CANDIDATE_FIELDS)
    reviews = read_csv_by_handle(review_file, required_fields=GROK_REVIEW_FIELDS)
    out_dir.mkdir(parents=True, exist_ok=True)
    verified_at = datetime.now(timezone.utc).isoformat()
    leads: list[dict[str, str]] = []
    email_research: list[dict[str, str]] = []

    for handle_key, review in reviews.items():
        candidate = candidates.get(handle_key)
        if candidate is None:
            append_log(
                out_dir,
                {
                    "event": "grok_review_rejected",
                    "handle": review.get("handle", ""),
                    "reason": "handle_not_in_candidates",
                },
            )
            continue
        qualified, reason = qualify_review_row(review)
        if not qualified:
            append_log(
                out_dir,
                {
                    "event": "grok_review_rejected",
                    "handle": candidate.get("handle", ""),
                    "reason": reason,
                },
            )
            if reason.startswith("founder_email"):
                email_research.append(
                    {
                        "handle": candidate.get("handle", ""),
                        "contact_name": review.get("founder_name", "").strip()
                        or candidate.get("display_name", ""),
                        "title": review.get("founder_title", "").strip(),
                        "profile_url": candidate.get("profile_url", ""),
                        "website_url": review.get("website_url", "").strip(),
                        "public_email": review.get("public_email", "").strip().lower(),
                        "email_evidence_url": review.get("email_evidence_url", "").strip(),
                        "missing_reason": reason,
                        "review_status": "needs_direct_email_research",
                    }
                )
            continue
        leads.append(
            {
                "handle": candidate.get("handle", ""),
                "display_name": candidate.get("display_name", ""),
                "contact_name": review.get("founder_name", "").strip()
                or candidate.get("display_name", ""),
                "title": review.get("founder_title", "").strip(),
                "profile_url": candidate.get("profile_url", ""),
                "bio": candidate.get("bio", ""),
                "founder_evidence": review.get("founder_evidence", "").strip(),
                "premium_status": normalize_premium_type(review.get("check_type", "")),
                "live_followers": str(parse_live_followers(review.get("live_followers", ""))),
                "location": review.get("location", "").strip(),
                "website_url": review.get("website_url", "").strip(),
                "email": review.get("public_email", "").strip().lower(),
                "email_status": "public_founder_email_needs_human_spot_check",
                "email_evidence_url": review.get("email_evidence_url", "").strip(),
                "email_evidence": review.get("email_evidence", "").strip(),
                "source_provider": candidate.get("source_provider", ""),
                "source_queries": candidate.get("source_queries", ""),
                "verified_at": verified_at,
                "review_status": "qualified_needs_human_spot_check",
                "notes": review.get("notes", "").strip(),
            }
        )

    leads.sort(key=lambda item: (int(item["live_followers"]), item["handle"].lower()))
    leads = leads[:target]
    write_final_leads(out_dir / "leads.csv", leads)
    write_email_research(out_dir / "email_research_queue.csv", email_research)
    append_log(
        out_dir,
        {
            "event": "x_founder_finalization_completed",
            "qualified_leads": len(leads),
            "target": target,
            "review_rows": len(reviews),
        },
    )
    return leads


def read_csv_by_handle(
    path: Path,
    required_fields: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    content = path.read_text(encoding="utf-8-sig").strip()
    lines = content.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    fields = reader.fieldnames or []
    required = required_fields or ["handle"]
    missing = [field for field in required if field not in fields]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
    rows: dict[str, dict[str, str]] = {}
    for row in reader:
        raw_handle = (row.get("handle") or "").strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", raw_handle):
            continue
        rows[raw_handle.lower()] = {key: value or "" for key, value in row.items()}
    return rows


def write_final_leads(path: Path, leads: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEAD_FIELDS)
        writer.writeheader()
        for index, lead in enumerate(leads, start=1):
            writer.writerow({"lead_id": f"XF{index:06d}", **lead})


def write_email_research(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EMAIL_RESEARCH_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def reset_run_log(out_dir: Path) -> None:
    log_path = out_dir / "run_log.jsonl"
    if log_path.exists():
        log_path.unlink()
