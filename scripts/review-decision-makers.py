from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_FIELDS = [
    "decision_maker_review_status",
    "decision_maker_review_note",
    "decision_maker_reviewed_at",
]
SLIM_FIELDS = [
    "business_name",
    "segment",
    "website",
    "name",
    "title",
    "email",
    "city",
    "country",
    "lead_score",
    "evidence_url",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply human-review decisions to decision-maker enrichment results."
    )
    parser.add_argument(
        "--input",
        default=(
            "data/output-americas-decision-makers-2026-07-26/"
            "all_leads_decision_makers.csv"
        ),
    )
    parser.add_argument(
        "--overrides",
        default="data/decision-maker-review-overrides.csv",
    )
    parser.add_argument(
        "--out",
        default="data/output-americas-decision-makers-2026-07-26",
    )
    args = parser.parse_args()

    input_path = REPO_ROOT / args.input
    override_path = REPO_ROOT / args.overrides
    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_rows(input_path)
    overrides = {
        row["business_name"]: row
        for row in read_rows(override_path)
        if row.get("business_name")
    }
    reviewed_at = datetime.now(timezone.utc).isoformat()
    reviewed = [
        review_row(row, overrides.get(row.get("business_name", "")), reviewed_at)
        for row in rows
    ]
    fields = list(rows[0].keys()) + REVIEW_FIELDS if rows else REVIEW_FIELDS
    approved = [
        row
        for row in reviewed
        if row["decision_maker_review_status"] == "approved_public_person_email"
    ]
    rejected = [
        row
        for row in reviewed
        if row["decision_maker_review_status"] == "rejected_match"
    ]

    all_path = out_dir / "all_leads_decision_makers_reviewed.csv"
    queue_path = out_dir / "decision_maker_mail_queue_reviewed.csv"
    slim_queue_path = out_dir / "decision_maker_leads.csv"
    rejected_path = out_dir / "decision_maker_rejected_matches.csv"
    write_rows(all_path, fields, reviewed)
    write_rows(queue_path, fields, approved)
    write_rows(
        slim_queue_path,
        SLIM_FIELDS,
        [slim_outreach_row(row) for row in approved],
    )
    write_rows(rejected_path, fields, rejected)

    statuses = Counter(row["decision_maker_review_status"] for row in reviewed)
    summary = {
        "generated_at": reviewed_at,
        "input_leads": len(reviewed),
        "approved_public_person_emails": len(approved),
        "rejected_matches": len(rejected),
        "statuses": dict(sorted(statuses.items())),
        "email_policy": "publicly_evidenced_person_email_no_generated_patterns",
        "deliverability_note": "Addresses are not SMTP deliverability verified.",
        "all_leads_csv": str(all_path.resolve()),
        "mail_queue_csv": str(queue_path.resolve()),
        "slim_mail_queue_csv": str(slim_queue_path.resolve()),
        "rejected_matches_csv": str(rejected_path.resolve()),
    }
    (out_dir / "review_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def review_row(
    row: dict[str, str],
    override: dict[str, str] | None,
    reviewed_at: str,
) -> dict[str, str]:
    reviewed = dict(row)
    has_email = row.get("decision_maker_status") == "decision_maker_email_found"
    status = "not_reviewed_no_person_email"
    note = ""

    if has_email:
        status = "approved_public_person_email"
        note = "Name, role, address, and public evidence passed manual spot review."

    if override:
        note = override.get("review_note", "") or note
        if override.get("action") == "reject":
            status = "rejected_match"
            reviewed["decision_maker_email"] = ""
            reviewed["recommended_outreach_email"] = ""
            reviewed["recommended_outreach_name"] = ""
            reviewed["decision_maker_email_status"] = "rejected_during_human_review"
        elif override.get("action") == "approve" and has_email:
            status = "approved_public_person_email"
            reviewed["decision_maker_name"] = override.get("name", "") or reviewed.get(
                "decision_maker_name", ""
            )
            reviewed["decision_maker_title"] = override.get("title", "") or reviewed.get(
                "decision_maker_title", ""
            )
            reviewed["recommended_outreach_name"] = reviewed["decision_maker_name"]
            reviewed["decision_maker_evidence_url"] = override.get(
                "evidence_url", ""
            ) or reviewed.get("decision_maker_evidence_url", "")

    reviewed.update(
        {
            "decision_maker_review_status": status,
            "decision_maker_review_note": note,
            "decision_maker_reviewed_at": reviewed_at,
        }
    )
    return reviewed


def slim_outreach_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "business_name": row.get("business_name", ""),
        "segment": row.get("segment", ""),
        "website": row.get("website", ""),
        "name": row.get("decision_maker_name", ""),
        "title": row.get("decision_maker_title", ""),
        "email": row.get("decision_maker_email", ""),
        "city": row.get("city", ""),
        "country": row.get("country", ""),
        "lead_score": row.get("score", ""),
        "evidence_url": row.get("decision_maker_evidence_url", ""),
    }


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


if __name__ == "__main__":
    raise SystemExit(main())
