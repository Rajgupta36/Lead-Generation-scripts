from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Lead


LEAD_FIELDS = [
    "lead_id",
    "segment",
    "business_name",
    "contact_name",
    "title",
    "website",
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
    "city",
    "country",
    "source_provider",
    "source_query",
    "source_url",
    "website_score",
    "score",
    "confidence",
    "score_reasons",
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
    "status",
    "notes",
    "created_at",
]

CANDIDATE_FIELDS = LEAD_FIELDS + ["missing_reason"]


def export_csv(leads: list[Lead], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    lead_path = out_dir / "leads.csv"
    candidate_path = out_dir / "candidates_review.csv"
    all_path = out_dir / "all_leads.csv"
    now = datetime.now(timezone.utc).isoformat()
    lead_rows = [lead for lead in leads if lead.score >= 70]
    candidate_rows = [lead for lead in leads if lead.score < 70]
    write_rows(lead_path, LEAD_FIELDS, lead_rows, now)
    write_rows(candidate_path, CANDIDATE_FIELDS, candidate_rows, now)
    write_rows(all_path, CANDIDATE_FIELDS, leads, now)
    return lead_path, candidate_path


def write_rows(path: Path, fields: list[str], leads: list[Lead], created_at: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, lead in enumerate(sorted(leads, key=lambda item: (-item.score, item.website)), start=1):
            row = lead_to_row(index, lead, created_at)
            writer.writerow({field: row.get(field, "") for field in fields})


def lead_to_row(index: int, lead: Lead, created_at: str) -> dict[str, str | int]:
    return {
        "lead_id": f"L{index:06d}",
        "segment": lead.segment,
        "business_name": lead.business_name,
        "contact_name": lead.contact_name,
        "title": lead.title,
        "website": lead.website,
        "contact_page": lead.contact_page,
        "email": lead.email,
        "phone": lead.phone,
        "linkedin": lead.linkedin,
        "instagram": lead.instagram,
        "youtube": lead.youtube,
        "booking_url": lead.booking_url,
        "address": lead.address,
        "category": lead.category,
        "maps_rating": lead.maps_rating,
        "maps_reviews": lead.maps_reviews,
        "maps_place_id": lead.maps_place_id,
        "city": lead.city,
        "country": lead.country,
        "source_provider": lead.source_provider,
        "source_query": " | ".join(sorted(lead.source_queries)),
        "source_url": " | ".join(sorted(lead.source_urls)),
        "website_score": lead.website_score,
        "score": lead.score,
        "confidence": lead.confidence,
        "score_reasons": " | ".join(lead.score_reasons),
        "enrichment_provider": lead.enrichment_provider,
        "enrichment_status": lead.enrichment_status,
        "email_validation_status": lead.email_validation_status,
        "apollo_person_id": lead.apollo_person_id,
        "apollo_organization_id": lead.apollo_organization_id,
        "apollo_email_status": lead.apollo_email_status,
        "apollo_employee_count": lead.apollo_employee_count,
        "apollo_industry": lead.apollo_industry,
        "apollo_revenue": lead.apollo_revenue,
        "apollo_company_phone": lead.apollo_company_phone,
        "status": lead.status,
        "notes": lead.notes,
        "missing_reason": lead.missing_reason,
        "created_at": created_at,
    }


def append_log(out_dir: Path, event: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "run_log.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
