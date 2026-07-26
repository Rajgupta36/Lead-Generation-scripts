from __future__ import annotations

import re

from .models import ExtractedContact, Lead, SearchResult
from .urltools import normalize_url, site_root_url


SEGMENT_TERMS = {
    "agency_owner": ("agency", "studio", "marketing", "branding", "design", "seo", "founder", "owner"),
    "coach": ("coach", "mentor", "speaker", "consultant", "strategy", "book a call"),
    "creator": ("creator", "youtube", "podcast", "newsletter", "sponsorship", "business inquiries"),
    "small_business": ("services", "book now", "appointment", "free consultation", "local"),
    "shop_owner": ("shop", "store", "boutique", "shopify", "owner", "contact", "instagram"),
    "tutor": ("tutor", "tutoring", "lesson", "test prep", "sat", "gcse", "ielts", "book"),
}

WEBSITE_OPPORTUNITY_TERMS = (
    "copyright 201",
    "under construction",
    "coming soon",
    "wixsite",
    "weebly",
    "godaddy",
    "wordpress.com",
)


def build_lead(result: SearchResult, contact: ExtractedContact | None) -> Lead:
    website = site_root_url(contact.url if contact else result.url)
    business_name = choose_business_name(
        contact.title if contact else "",
        result.title,
        website,
    )

    lead = Lead(
        segment=result.segment,
        business_name=business_name,
        website=website,
        city=result.city,
        country=result.country,
        source_queries={result.source_query} if result.source_query else set(),
        source_urls={result.url},
        address=result.address,
        category=result.category,
        maps_rating=result.rating,
        maps_reviews=result.reviews,
        maps_place_id=result.place_id,
        source_provider=result.source_provider,
    )
    if contact:
        lead.contact_page = first_sorted(contact.contact_pages)
        lead.email = first_sorted(contact.emails)
        lead.phone = first_sorted(contact.phones)
        lead.linkedin = first_sorted(contact.social_links.get("linkedin", set()))
        lead.instagram = first_sorted(contact.social_links.get("instagram", set()))
        lead.youtube = first_sorted(contact.social_links.get("youtube", set()))
        lead.booking_url = first_sorted(contact.booking_urls)
        lead.title = contact.title
    if not lead.phone and result.phone:
        lead.phone = result.phone
    lead.score, lead.confidence, lead.score_reasons = score_lead(result, contact)
    lead.website_score = website_opportunity_score(result, contact)
    if lead.score < 70:
        lead.status = "needs_manual_research"
        lead.missing_reason = missing_reason(lead)
    return lead


def score_lead(result: SearchResult, contact: ExtractedContact | None) -> tuple[int, str, list[str]]:
    score = 0
    reasons: list[str] = []
    haystack = " ".join(
        [
            result.title,
            result.snippet,
            result.url,
            contact.title if contact else "",
            contact.description if contact else "",
            contact.text_sample if contact else "",
            result.address,
            result.category,
        ]
    ).lower()

    segment_terms = SEGMENT_TERMS.get(result.segment, ())
    matched_terms = [term for term in segment_terms if term in haystack]
    if matched_terms:
        score += min(35, 15 + len(matched_terms) * 5)
        reasons.append(f"segment_match:{','.join(matched_terms[:5])}")

    if result.city.lower() in haystack or result.country.lower() in haystack:
        score += 10
        reasons.append("location_match")

    if contact:
        score += 10
        reasons.append("reachable_website")
        if contact.emails:
            score += 18
            reasons.append("email_found")
        if contact.phones:
            score += 12
            reasons.append("phone_found")
        if contact.contact_pages:
            score += 12
            reasons.append("contact_page_found")
        if contact.booking_urls:
            score += 15
            reasons.append("booking_link_found")
        if any(contact.social_links.values()):
            score += 10
            reasons.append("social_link_found")
        opportunity_terms = [term for term in WEBSITE_OPPORTUNITY_TERMS if term in haystack]
        if opportunity_terms:
            score += 10
            reasons.append(f"website_opportunity:{','.join(opportunity_terms[:3])}")

    if result.source_provider == "serpapi_maps":
        score += 12
        reasons.append("google_maps_result")
        if result.phone:
            score += 10
            reasons.append("maps_phone_found")
        if result.rating or result.reviews:
            score += 5
            reasons.append("maps_business_signals")

    if result.source_query:
        score += 5
        reasons.append("source_query_kept")

    score = min(score, 100)
    confidence = "high" if score >= 70 else "medium" if score >= 40 else "low"
    return score, confidence, reasons


def website_opportunity_score(result: SearchResult, contact: ExtractedContact | None) -> int:
    haystack = " ".join(
        [
            result.url,
            result.snippet,
            contact.title if contact else "",
            contact.description if contact else "",
            contact.text_sample if contact else "",
        ]
    ).lower()
    score = 0
    if any(term in haystack for term in WEBSITE_OPPORTUNITY_TERMS):
        score += 35
    if contact and not contact.booking_urls:
        score += 15
    if contact and not contact.contact_pages:
        score += 15
    if contact and not contact.emails:
        score += 10
    if "http://" in result.url:
        score += 10
    return min(score, 100)


def merge_leads(existing: Lead, new: Lead) -> Lead:
    existing.source_queries.update(new.source_queries)
    existing.source_urls.update(new.source_urls)
    existing.score = max(existing.score, new.score)
    existing.confidence = "high" if existing.score >= 70 else "medium" if existing.score >= 40 else "low"
    existing.score_reasons = sorted(set(existing.score_reasons + new.score_reasons))
    for field in (
        "business_name",
        "contact_name",
        "title",
        "contact_page",
        "email",
        "phone",
        "linkedin",
        "instagram",
        "youtube",
        "booking_url",
        "address",
        "category",
        "maps_rating",
        "maps_reviews",
        "maps_place_id",
        "source_provider",
        "enrichment_provider",
        "enrichment_status",
        "email_validation_status",
        "apollo_person_id",
        "apollo_organization_id",
        "apollo_email_status",
        "apollo_employee_count",
        "apollo_industry",
        "apollo_revenue",
        "apollo_company_phone",
    ):
        if not getattr(existing, field) and getattr(new, field):
            setattr(existing, field, getattr(new, field))
    existing.website_score = max(existing.website_score, new.website_score)
    if len(existing.source_queries) > 1 and "discovered_multiple_times" not in existing.score_reasons:
        existing.score = min(100, existing.score + 8)
        existing.score_reasons.append("discovered_multiple_times")
    if existing.score >= 70:
        existing.status = "new"
        existing.missing_reason = ""
    return existing


GENERIC_PAGE_TITLES = {
    "about",
    "appointment",
    "book",
    "booking",
    "contact",
    "contact us",
    "home",
    "services",
}


def choose_business_name(primary_title: str, result_title: str, website: str) -> str:
    domain = website.split("//", 1)[-1].split("/", 1)[0].split(".", 1)[0]
    domain_key = re.sub(r"[^a-z0-9]", "", domain.lower())
    candidates: list[tuple[int, str]] = []
    for title_index, title in enumerate((primary_title, result_title)):
        for candidate in title_candidates(title):
            cleaned = clean_business_candidate(candidate)
            if not cleaned or cleaned.lower() in GENERIC_PAGE_TITLES:
                continue
            compact = re.sub(r"[^a-z0-9]", "", cleaned.lower())
            if compact == domain_key and cleaned == cleaned.lower():
                cleaned = humanize_domain(domain)
                compact = re.sub(r"[^a-z0-9]", "", cleaned.lower())
            score = 5 - title_index
            if compact == domain_key:
                score += 50
            elif compact in domain_key or domain_key in compact:
                score += 25
            if len(cleaned) > 65:
                score -= 15
            if contains_seo_title_language(cleaned):
                score -= 10
            candidates.append((score, cleaned))

    domain_name = humanize_domain(domain)
    if domain_name:
        candidates.append((50, domain_name))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return domain_name


def cleanup_title(title: str) -> str:
    candidates = title_candidates(title)
    for candidate in candidates:
        candidate = clean_business_candidate(candidate)
        if candidate.lower() not in GENERIC_PAGE_TITLES and len(candidate) <= 90:
            return candidate
    return clean_business_candidate(candidates[0]) if candidates else ""


def title_candidates(title: str) -> list[str]:
    candidates = [title.strip()] if title.strip() else []
    for separator in ("|", " - ", " – ", " — "):
        if separator in title:
            candidates = [part.strip() for part in title.split(separator) if part.strip()]
            break
    return candidates


def clean_business_candidate(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -|,")
    value = re.sub(r"\s*\([^)]*\.(?:com|net|org|co|io)\)\s*$", "", value, flags=re.I)
    value = re.sub(r"\s+['’]\s*s\s+(?:miami|new york|los angeles|the best|best).*", "", value, flags=re.I)
    return value.strip(" -|,")


def contains_seo_title_language(value: str) -> bool:
    lower = value.lower()
    return any(term in lower for term in ("best cosmetic", "near me", "top rated", "revitalize your", "spa services"))


def humanize_domain(domain: str) -> str:
    value = re.sub(r"[-_]+", " ", domain.lower())
    for term, replacement in DOMAIN_WORDS:
        value = value.replace(term, f" {replacement} ")
    value = re.sub(r"\s+", " ", value).strip()
    if value.startswith("the") and not value.startswith("the ") and len(value) > 5:
        value = "the " + value[3:]
    return value.title()


DOMAIN_WORDS = (
    ("medicalspa", "medical spa"),
    ("medspa", "med spa"),
    ("interiordesign", "interior design"),
    ("realestate", "real estate"),
    ("institute", "institute"),
    ("dentistry", "dentistry"),
    ("marketing", "marketing"),
    ("clinic", "clinic"),
    ("dental", "dental"),
    ("studio", "studio"),
    ("agency", "agency"),
    ("fitness", "fitness"),
    ("design", "design"),
    ("salon", "salon"),
    ("center", "center"),
    ("centre", "centre"),
    ("group", "group"),
    ("care", "care"),
    ("spa", "spa"),
)


def first_sorted(values: set[str] | None) -> str:
    if not values:
        return ""
    return sorted(values)[0]


def missing_reason(lead: Lead) -> str:
    missing = []
    if not any([lead.email, lead.phone, lead.contact_page, lead.booking_url, lead.linkedin, lead.instagram, lead.youtube]):
        missing.append("no_contact_channel")
    if lead.score < 70:
        missing.append("score_below_lead_threshold")
    return ",".join(missing)
