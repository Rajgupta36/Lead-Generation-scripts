from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .export import CANDIDATE_FIELDS
from .extract import is_valid_email
from .filters import blocked_domain, public_sector_domain, unsuitable_outreach_email
from .urltools import domain_key


SEGMENTS = ("agency_owner", "coach", "small_business")

MARKETS = {
    "europe": (
        ("London", "United Kingdom"),
        ("Dublin", "Ireland"),
        ("Berlin", "Germany"),
        ("Paris", "France"),
        ("Amsterdam", "Netherlands"),
        ("Madrid", "Spain"),
        ("Barcelona", "Spain"),
        ("Lisbon", "Portugal"),
        ("Stockholm", "Sweden"),
        ("Copenhagen", "Denmark"),
        ("Zurich", "Switzerland"),
        ("Vienna", "Austria"),
        ("Milan", "Italy"),
        ("Warsaw", "Poland"),
        ("Prague", "Czechia"),
    ),
    "australia_nz": (
        ("Sydney", "Australia"),
        ("Melbourne", "Australia"),
        ("Brisbane", "Australia"),
        ("Perth", "Australia"),
        ("Adelaide", "Australia"),
        ("Gold Coast", "Australia"),
        ("Canberra", "Australia"),
        ("Auckland", "New Zealand"),
        ("Wellington", "New Zealand"),
        ("Christchurch", "New Zealand"),
    ),
    "north_america": (
        ("New York", "USA"),
        ("Toronto", "Canada"),
        ("Los Angeles", "USA"),
        ("Vancouver", "Canada"),
        ("Austin", "USA"),
        ("Montreal", "Canada"),
        ("Miami", "USA"),
        ("Calgary", "Canada"),
        ("Mexico City", "Mexico"),
    ),
    "south_america": (
        ("Sao Paulo", "Brazil"),
        ("Buenos Aires", "Argentina"),
        ("Bogota", "Colombia"),
        ("Santiago", "Chile"),
        ("Lima", "Peru"),
        ("Medellin", "Colombia"),
        ("Montevideo", "Uruguay"),
        ("Quito", "Ecuador"),
        ("Rio de Janeiro", "Brazil"),
    ),
}

PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}

REJECTED_EMAIL_LOCAL_PARTS = {
    "abuse",
    "example",
    "legal",
    "myprivacy",
    "no-reply",
    "noreply",
    "privacy",
}

AGENCY_TERMS = (
    "agency",
    "agencia",
    "agence",
    "advertising",
    "branding",
    "creative",
    "digital",
    "marketing",
    "seo",
    "studio",
    "web design",
)

COACH_TERMS = (
    "business coach",
    "career coach",
    "coach",
    "coaching",
    "consultant",
    "consulting",
    "executive coach",
    "leadership",
    "mentor",
)

MASTER_FIELDS = CANDIDATE_FIELDS + [
    "workflow",
    "business_size_tier",
    "region",
    "first_seen_at",
    "last_seen_at",
    "loop_cycle",
]

WORKFLOWS = ("businesses", "coaches", "agency_partners")
BUSINESS_SIZE_TIERS = ("small", "medium", "large")
AGENCY_PARTNER_TERMS = (
    "advertising agency",
    "email marketing agency",
    "influencer agency",
    "media buying agency",
    "paid media agency",
    "performance marketing agency",
    "pr agency",
    "public relations agency",
    "social media agency",
    "video production agency",
)
FORBIDDEN_AGENCY_SERVICE_PATTERNS = (
    r"\bseo\b",
    r"search engine optimi[sz]ation",
    r"web(?:site)?\s+design",
    r"web(?:site)?\s+development",
    r"wordpress\s+development",
    r"shopify\s+development",
)
WORKFLOW_BLOCKED_DOMAINS = {
    "coachlinks.com",
    "noomii.com",
}


def load_loop_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def default_state() -> dict:
    return {
        "cycle": 0,
        "region_cursor": 0,
        "market_cursors": {region: 0 for region in MARKETS},
        "last_started_at": "",
        "last_completed_at": "",
        "last_status": "never_run",
        "total_leads": 0,
    }


def load_state(path: Path) -> dict:
    if not path.exists():
        return default_state()
    state = default_state()
    state.update(json.loads(path.read_text(encoding="utf-8")))
    state["market_cursors"] = {
        **default_state()["market_cursors"],
        **state.get("market_cursors", {}),
    }
    return state


def save_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def select_cycle_tasks(config: dict, state: dict) -> list[dict[str, str | int]]:
    region_order = config.get("regions") or list(MARKETS)
    regions_per_cycle = int(config.get("regions_per_cycle", 2))
    markets_per_region = int(config.get("markets_per_region", 3))
    region_cursor = int(state.get("region_cursor", 0))
    cycle = int(state.get("cycle", 0))
    tasks = []

    for region_offset in range(regions_per_cycle):
        region = region_order[(region_cursor + region_offset) % len(region_order)]
        markets = MARKETS[region]
        market_cursor = int(state["market_cursors"].get(region, 0))
        for market_offset in range(markets_per_region):
            city, country = markets[(market_cursor + market_offset) % len(markets)]
            segment = SEGMENTS[(cycle + market_offset) % len(SEGMENTS)]
            tasks.append(
                {
                    "region": region,
                    "city": city,
                    "country": country,
                    "segment": segment,
                    "market_index": (market_cursor + market_offset) % len(markets),
                }
            )
    return tasks


def select_workflow_tasks(
    workflow: str,
    config: dict,
    state: dict,
) -> list[dict[str, str | int]]:
    if workflow not in WORKFLOWS:
        raise ValueError(f"Unknown workflow: {workflow}")
    region_order = config.get("regions") or list(MARKETS)
    regions_per_cycle = int(config.get("regions_per_cycle", 2))
    region_cursor = int(state.get("region_cursor", 0))
    tasks = []
    for region_offset in range(regions_per_cycle):
        region = region_order[(region_cursor + region_offset) % len(region_order)]
        markets = MARKETS[region]
        market_cursor = int(state["market_cursors"].get(region, 0))
        if workflow == "businesses":
            for tier_offset, tier in enumerate(BUSINESS_SIZE_TIERS):
                city, country = markets[(market_cursor + tier_offset) % len(markets)]
                tasks.append(
                    {
                        "workflow": workflow,
                        "region": region,
                        "city": city,
                        "country": country,
                        "segment": "small_business",
                        "business_size_tier": tier,
                    }
                )
        else:
            city, country = markets[market_cursor % len(markets)]
            tasks.append(
                {
                    "workflow": workflow,
                    "region": region,
                    "city": city,
                    "country": country,
                    "segment": "coach" if workflow == "coaches" else "agency_owner",
                    "business_size_tier": "",
                }
            )
    return tasks


def advance_state(config: dict, state: dict) -> dict:
    updated = json.loads(json.dumps(state))
    region_order = config.get("regions") or list(MARKETS)
    regions_per_cycle = int(config.get("regions_per_cycle", 2))
    markets_per_region = int(config.get("markets_per_region", 3))
    region_cursor = int(state.get("region_cursor", 0))
    for offset in range(regions_per_cycle):
        region = region_order[(region_cursor + offset) % len(region_order)]
        updated["market_cursors"][region] = (
            int(updated["market_cursors"].get(region, 0)) + markets_per_region
        ) % len(MARKETS[region])
    updated["region_cursor"] = (region_cursor + regions_per_cycle) % len(region_order)
    updated["cycle"] = int(state.get("cycle", 0)) + 1
    return updated


def advance_workflow_state(workflow: str, config: dict, state: dict) -> dict:
    updated = json.loads(json.dumps(state))
    region_order = config.get("regions") or list(MARKETS)
    regions_per_cycle = int(config.get("regions_per_cycle", 2))
    region_cursor = int(state.get("region_cursor", 0))
    market_step = len(BUSINESS_SIZE_TIERS) if workflow == "businesses" else 1
    for offset in range(regions_per_cycle):
        region = region_order[(region_cursor + offset) % len(region_order)]
        updated["market_cursors"][region] = (
            int(updated["market_cursors"].get(region, 0)) + market_step
        ) % len(MARKETS[region])
    updated["region_cursor"] = (region_cursor + regions_per_cycle) % len(region_order)
    updated["cycle"] = int(state.get("cycle", 0)) + 1
    return updated


def finish_workflow_state(
    workflow: str,
    config: dict,
    state: dict,
    failures: list[dict],
) -> dict:
    if failures:
        return json.loads(json.dumps(state))
    return advance_workflow_state(workflow, config, state)


def read_run_events(path: Path, event_name: str) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == event_name:
            events.append(event)
    return events


def build_query(segment: str, city: str, country: str) -> str:
    location = f'"{city}" "{country}"'
    if segment == "agency_owner":
        return (
            '("marketing agency" OR "web design agency" OR "SEO agency" OR '
            f'"branding agency") {location} ("contact us" OR "email us" OR "get in touch")'
        )
    if segment == "coach":
        return (
            '("business coach" OR "executive coach" OR "leadership coach" OR '
            f'"career coach") {location} ("contact" OR "email" OR "book a call")'
        )
    return (
        '("dentist" OR "med spa" OR "roofing company" OR "HVAC company") '
        f'{location} ("contact us" OR "book appointment" OR "request a quote")'
    )


def build_workflow_query(task: dict[str, str | int]) -> str:
    workflow = str(task["workflow"])
    city = str(task["city"])
    country = str(task["country"])
    location = f'"{city}" "{country}"'
    contact = '("contact us" OR "email us" OR "get in touch")'
    if workflow == "coaches":
        return (
            '("business coach" OR "executive coach" OR "leadership coach" OR '
            f'"career coach") {location} ("contact" OR "email" OR "book a call")'
        )
    if workflow == "agency_partners":
        return (
            '("PR agency" OR "public relations agency" OR "paid media agency" OR '
            '"social media agency" OR "email marketing agency" OR "influencer agency" OR '
            f'"video production agency") {location} {contact} '
            '-"web design" -"web development" -"website design" -SEO'
        )

    tier = str(task.get("business_size_tier", "small"))
    if tier == "medium":
        businesses = (
            '("manufacturing company" OR "logistics company" OR "accounting firm" OR '
            '"commercial construction company" OR "staffing company")'
        )
    elif tier == "large":
        businesses = (
            '("regional company" OR "enterprise services company" OR "multi-location company" '
            'OR "industrial company" OR "corporate services")'
        )
    else:
        businesses = (
            '("dentist" OR "medical clinic" OR "law firm" OR "roofing company" OR '
            '"HVAC company" OR "accounting firm")'
        )
    return f"{businesses} {location} {contact}"


def workflow_row_relevant(row: dict[str, str], workflow: str) -> bool:
    if domain_key(row.get("website", "")) in WORKFLOW_BLOCKED_DOMAINS:
        return False
    if public_sector_domain(row.get("website", "")):
        return False
    if unsuitable_outreach_email(row.get("email", "")):
        return False
    haystack = " ".join(
        (
            row.get("business_name", ""),
            row.get("title", ""),
            row.get("category", ""),
            row.get("website", ""),
        )
    ).lower()
    if workflow == "coaches":
        return any(term in haystack for term in COACH_TERMS)
    if workflow == "agency_partners":
        return any(term in haystack for term in AGENCY_PARTNER_TERMS)
    return not any(term in haystack for term in AGENCY_TERMS + COACH_TERMS)


def agency_has_forbidden_service(text: str) -> bool:
    normalized = " ".join((text or "").lower().split())
    return any(
        re.search(pattern, normalized, re.IGNORECASE)
        for pattern in FORBIDDEN_AGENCY_SERVICE_PATTERNS
    )


def qualify_rows(
    rows: list[dict[str, str]],
    *,
    segment: str,
    region: str,
    cycle: int,
) -> list[dict[str, str]]:
    now = datetime.now(timezone.utc).isoformat()
    accepted = []
    for row in sorted(rows, key=row_rank, reverse=True):
        website = row.get("website", "").strip()
        email = row.get("email", "").strip().lower()
        if (
            not domain_key(website)
            or blocked_domain(website)
            or not is_valid_email(email)
            or not outreach_email(email)
            or not email_matches_website(email, website)
            or not segment_relevant(row, segment)
            or parse_int(row.get("score")) < 70
        ):
            continue
        candidate = dict(row)
        candidate.update(
            {
                "segment": segment,
                "email": email,
                "region": region,
                "first_seen_at": row.get("first_seen_at") or now,
                "last_seen_at": now,
                "loop_cycle": str(cycle),
            }
        )
        accepted.append(candidate)
    return accepted


def merge_leads(
    existing: list[dict[str, str]],
    candidates: list[dict[str, str]],
    limit: int | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    by_domain = {
        domain_key(row.get("website", "")): dict(row)
        for row in existing
        if domain_key(row.get("website", ""))
    }
    used_emails = {
        row.get("email", "").strip().lower()
        for row in existing
        if row.get("email", "").strip()
    }
    added = []
    for candidate in sorted(candidates, key=row_rank, reverse=True):
        if limit is not None and len(added) >= limit:
            break
        domain = domain_key(candidate.get("website", ""))
        email = candidate.get("email", "").strip().lower()
        if not domain or domain in by_domain or not email or email in used_emails:
            continue
        by_domain[domain] = dict(candidate)
        used_emails.add(email)
        added.append(dict(candidate))
    return list(by_domain.values()), added


def write_master_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: (row.get("region", ""), row.get("country", ""), row.get("business_name", "")))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MASTER_FIELDS)
        writer.writeheader()
        for index, row in enumerate(ordered, start=1):
            output = dict(row)
            output["lead_id"] = f"L{index:06d}"
            writer.writerow({field: output.get(field, "") for field in MASTER_FIELDS})


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def email_matches_website(email: str, website: str) -> bool:
    email_domain = email.rsplit("@", 1)[-1].lower().removeprefix("www.")
    if email_domain in PUBLIC_EMAIL_DOMAINS:
        return True
    website_domain = domain_key(website)
    return bool(
        website_domain
        and (email_domain == website_domain or email_domain.endswith("." + website_domain))
    )


def outreach_email(email: str) -> bool:
    if "@" not in email:
        return False
    local_part, email_domain = email.lower().split("@", 1)
    return bool(
        local_part
        and not local_part[0].isdigit()
        and local_part not in REJECTED_EMAIL_LOCAL_PARTS
        and not unsuitable_outreach_email(email)
        and not re.fullmatch(r"[0-9a-f]{20,}", local_part)
        and not (email_domain in PUBLIC_EMAIL_DOMAINS and local_part in {"info", "support"})
    )


def segment_relevant(row: dict[str, str], segment: str) -> bool:
    haystack = " ".join(
        (
            row.get("business_name", ""),
            row.get("title", ""),
            row.get("category", ""),
            row.get("website", ""),
        )
    ).lower()
    if segment == "agency_owner":
        return any(term in haystack for term in AGENCY_TERMS)
    if segment == "coach":
        return any(term in haystack for term in COACH_TERMS)
    return True


def row_rank(row: dict[str, str]) -> tuple[int, int]:
    return parse_int(row.get("score")), parse_int(row.get("website_score"))


def parse_int(value: str | None) -> int:
    try:
        return int(float((value or "0").replace(",", "")))
    except ValueError:
        return 0
