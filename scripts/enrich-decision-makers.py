from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.config import load_env
from leadgen.decision_makers import DecisionMakerResult, enrich_decision_maker
from leadgen.search import SerperProvider


DECISION_FIELDS = [
    "general_email",
    "decision_maker_name",
    "decision_maker_title",
    "decision_maker_email",
    "decision_maker_email_status",
    "decision_maker_evidence_url",
    "decision_maker_evidence",
    "decision_maker_source",
    "decision_maker_status",
    "recommended_outreach_email",
    "recommended_outreach_name",
    "decision_maker_enriched_at",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Attach publicly evidenced founder/owner/CEO emails to a lead CSV."
    )
    parser.add_argument(
        "--input",
        default="data/output-americas-email-leads-2026-07-26/all_leads.csv",
    )
    parser.add_argument(
        "--out",
        default="data/output-americas-decision-makers-2026-07-26",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=6)
    args = parser.parse_args()

    if args.workers <= 0 or args.timeout <= 0:
        parser.error("--workers and --timeout must be greater than zero")

    load_env(REPO_ROOT / ".env")
    input_path = REPO_ROOT / args.input
    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = read_rows(input_path)
    provider = SerperProvider()
    enriched_at = datetime.now(timezone.utc).isoformat()
    results: dict[int, DecisionMakerResult] = {}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                enrich_decision_maker,
                row,
                provider,
                args.timeout,
            ): index
            for index, row in enumerate(rows)
        }
        completed = 0
        for future in as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except Exception as error:
                results[index] = DecisionMakerResult(
                    status=f"enrichment_failed:{type(error).__name__}"
                )
            completed += 1
            if completed % 10 == 0 or completed == len(rows):
                found = sum(result.status == "decision_maker_email_found" for result in results.values())
                print(f"Processed {completed}/{len(rows)}; person emails found {found}", flush=True)

    augmented = [
        augment_row(row, results.get(index, DecisionMakerResult()), enriched_at)
        for index, row in enumerate(rows)
    ]
    all_path = out_dir / "all_leads_decision_makers.csv"
    mail_path = out_dir / "decision_maker_mail_queue.csv"
    research_path = out_dir / "decision_maker_research_queue.csv"
    fieldnames = list(rows[0].keys()) + DECISION_FIELDS if rows else DECISION_FIELDS
    write_rows(all_path, fieldnames, augmented)
    write_rows(
        mail_path,
        fieldnames,
        [row for row in augmented if row["decision_maker_status"] == "decision_maker_email_found"],
    )
    write_rows(
        research_path,
        fieldnames,
        [row for row in augmented if row["decision_maker_status"] != "decision_maker_email_found"],
    )
    statuses = Counter(row["decision_maker_status"] for row in augmented)
    summary = {
        "generated_at": enriched_at,
        "input_leads": len(rows),
        "decision_maker_emails_found": statuses.get("decision_maker_email_found", 0),
        "research_required": len(rows) - statuses.get("decision_maker_email_found", 0),
        "statuses": dict(sorted(statuses.items())),
        "apollo_people_status": "unavailable_403",
        "email_policy": "published_person_email_only_no_generated_patterns",
        "all_leads_csv": str(all_path.resolve()),
        "mail_queue_csv": str(mail_path.resolve()),
        "research_queue_csv": str(research_path.resolve()),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def augment_row(
    row: dict[str, str],
    result: DecisionMakerResult,
    enriched_at: str,
) -> dict[str, str]:
    augmented = dict(row)
    augmented.update(
        {
            "general_email": row.get("email", ""),
            "decision_maker_name": result.name,
            "decision_maker_title": result.title,
            "decision_maker_email": result.email,
            "decision_maker_email_status": result.email_status,
            "decision_maker_evidence_url": result.evidence_url,
            "decision_maker_evidence": result.evidence,
            "decision_maker_source": result.source,
            "decision_maker_status": result.status,
            "recommended_outreach_email": result.email,
            "recommended_outreach_name": result.name,
            "decision_maker_enriched_at": enriched_at,
        }
    )
    return augmented


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


if __name__ == "__main__":
    raise SystemExit(main())
