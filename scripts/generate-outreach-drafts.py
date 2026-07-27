from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.outreach_drafts import generate_drafts


CSV_FIELDS = [
    "business_name",
    "segment",
    "website",
    "name",
    "title",
    "email",
    "city",
    "country",
    "lead_score",
    "recipient_type",
    "audit_status",
    "recommended_offer",
    "price_range",
    "specific_observation",
    "evidence_page",
    "page_findings",
    "funnel_sequence",
    "draft_number",
    "draft_key",
    "draft_label",
    "subject",
    "body",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate five meeting-focused NexStudio emails per reviewed lead."
    )
    parser.add_argument(
        "--leads",
        default="data/output-americas-email-leads-2026-07-26/all_leads.csv",
    )
    parser.add_argument(
        "--reviewed",
        default=(
            "data/output-americas-decision-makers-2026-07-26/"
            "all_leads_decision_makers_reviewed.csv"
        ),
    )
    parser.add_argument(
        "--audits",
        default="data/output-americas-email-analysis-2026-07-26/meeting_queue.csv",
    )
    parser.add_argument(
        "--out",
        default="data/output-americas-outreach-drafts-2026-07-26",
    )
    parser.add_argument(
        "--frontend-data",
        default="apps/outreach-draft-review/data.js",
    )
    args = parser.parse_args()

    leads = read_rows(REPO_ROOT / args.leads)
    reviewed = read_rows(REPO_ROOT / args.reviewed)
    audits = read_rows(REPO_ROOT / args.audits)
    reviewed_by_domain = {
        domain_key(row.get("website", "")): row for row in reviewed
    }
    audits_by_domain = {domain_key(row.get("website", "")): row for row in audits}
    records: list[dict] = []
    flat_rows: list[dict[str, str]] = []

    for source_lead in leads:
        domain = domain_key(source_lead.get("website", ""))
        review = reviewed_by_domain.get(domain, {})
        source_audit = audits_by_domain.get(domain)
        lead = outreach_lead(source_lead, review)
        if source_audit and source_audit.get("business_name"):
            lead["business_name"] = source_audit["business_name"]
        audit = source_audit or fallback_audit(lead)
        drafts = generate_drafts(lead, audit)
        audit_status = audit.get("audit_status", "audited")
        if not drafts:
            audit_status = "research_required"
        record = {
            **lead,
            "audit_status": audit_status,
            "recommended_offer": audit.get("recommended_offer", ""),
            "price_range": audit.get("price_range", ""),
            "specific_observation": audit.get("specific_observation", ""),
            "evidence_page": audit.get("evidence_page", ""),
            "page_findings": audit.get("page_findings", ""),
            "funnel_sequence": audit.get("funnel_sequence", ""),
            "business_reason": audit.get("business_reason", ""),
            "evidence_url": audit.get("evidence_url", lead.get("website", "")),
            "evidence_summary": audit.get("evidence_summary", ""),
            "what_to_show_on_call": audit.get("what_to_show_on_call", ""),
            "drafts": [
                {
                    "number": index,
                    "key": draft.key,
                    "label": draft.label,
                    "subject": draft.subject,
                    "body": draft.body,
                }
                for index, draft in enumerate(drafts, start=1)
            ],
        }
        records.append(record)
        for draft in record["drafts"]:
            flat_rows.append(
                {
                    **{field: record.get(field, "") for field in CSV_FIELDS},
                    "draft_number": str(draft["number"]),
                    "draft_key": draft["key"],
                    "draft_label": draft["label"],
                    "subject": draft["subject"],
                    "body": draft["body"],
                }
            )

    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "outreach_drafts.csv"
    json_path = out_dir / "outreach_drafts.json"
    write_csv(csv_path, flat_rows)
    json_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    frontend_path = REPO_ROOT / args.frontend_data
    frontend_path.parent.mkdir(parents=True, exist_ok=True)
    frontend_path.write_text(
        "window.OUTREACH_DATA = "
        + json.dumps(records, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Generated {len(flat_rows)} drafts for {len(records)} companies")
    print(f"CSV: {csv_path.resolve()}")
    print(f"JSON: {json_path.resolve()}")
    print(f"Frontend data: {frontend_path.resolve()}")
    return 0


def outreach_lead(
    source: dict[str, str],
    review: dict[str, str],
) -> dict[str, str]:
    direct = review.get("decision_maker_review_status") == "approved_public_person_email"
    return {
        "business_name": source.get("business_name", ""),
        "segment": source.get("segment", ""),
        "website": source.get("website", ""),
        "name": review.get("decision_maker_name", "") if direct else "",
        "title": review.get("decision_maker_title", "") if direct else "",
        "email": (
            review.get("decision_maker_email", "")
            if direct
            else source.get("email", "")
        ),
        "city": source.get("city", ""),
        "country": source.get("country", ""),
        "lead_score": source.get("score", ""),
        "workflow": source.get("workflow", ""),
        "recipient_type": "decision_maker" if direct else "business_inbox",
    }


def fallback_audit(lead: dict[str, str]) -> dict[str, str]:
    company = lead.get("business_name", "The business")
    return {
        "audit_status": "research_required",
        "recommended_offer": "",
        "price_range": "",
        "specific_observation": (
            f"{company} needs a fresh visible-page review before an outbound claim is used."
        ),
        "business_reason": (
            "No outreach should be drafted until the observation is verified on the live site."
        ),
        "evidence_url": lead.get("website", ""),
        "evidence_summary": "",
        "what_to_show_on_call": "",
    }


def domain_key(value: str) -> str:
    domain = urlparse(value).netloc.lower().split(":", 1)[0]
    return domain[4:] if domain.startswith("www.") else domain


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in CSV_FIELDS} for row in rows)


if __name__ == "__main__":
    raise SystemExit(main())
