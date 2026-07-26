from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source_query: str = ""
    source_provider: str = ""
    segment: str = ""
    city: str = ""
    country: str = ""
    address: str = ""
    category: str = ""
    phone: str = ""
    rating: str = ""
    reviews: str = ""
    place_id: str = ""


@dataclass
class ExtractedContact:
    url: str
    title: str = ""
    description: str = ""
    emails: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    links: set[str] = field(default_factory=set)
    contact_pages: set[str] = field(default_factory=set)
    social_links: dict[str, set[str]] = field(default_factory=dict)
    booking_urls: set[str] = field(default_factory=set)
    text_sample: str = ""


@dataclass
class Lead:
    segment: str
    business_name: str
    website: str
    city: str
    country: str
    source_queries: set[str] = field(default_factory=set)
    source_urls: set[str] = field(default_factory=set)
    contact_name: str = ""
    title: str = ""
    contact_page: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    instagram: str = ""
    youtube: str = ""
    booking_url: str = ""
    address: str = ""
    category: str = ""
    maps_rating: str = ""
    maps_reviews: str = ""
    maps_place_id: str = ""
    source_provider: str = ""
    enrichment_provider: str = ""
    enrichment_status: str = "not_configured"
    email_validation_status: str = "not_configured"
    apollo_person_id: str = ""
    apollo_organization_id: str = ""
    apollo_email_status: str = ""
    apollo_employee_count: str = ""
    apollo_industry: str = ""
    apollo_revenue: str = ""
    apollo_company_phone: str = ""
    website_score: int = 0
    score: int = 0
    confidence: str = "low"
    score_reasons: list[str] = field(default_factory=list)
    status: str = "new"
    notes: str = ""
    missing_reason: str = ""
