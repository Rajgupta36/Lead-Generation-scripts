from __future__ import annotations

import csv
import json
import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.continuous import (
    MASTER_FIELDS,
    merge_leads,
    read_rows,
    save_json_atomic,
    workflow_row_relevant,
    write_master_csv,
)
from leadgen.filters import public_sector_domain, unsuitable_outreach_email
from leadgen.meeting_orchestrator import run_meeting_orchestrator
from leadgen.urltools import domain_key


CONTINUOUS_DIR = REPO_ROOT / "data/continuous-leads"
INITIAL_LEADS = (
    REPO_ROOT / "data/output-americas-email-leads-2026-07-26/all_leads.csv"
)
INITIAL_AUDITS = (
    REPO_ROOT / "data/output-americas-email-analysis-2026-07-26/meeting_queue.csv"
)
INITIAL_RESEARCH = (
    REPO_ROOT / "data/output-americas-email-analysis-2026-07-26/research_queue.csv"
)
INITIAL_CONTACTS = (
    REPO_ROOT
    / "data/output-americas-decision-makers-2026-07-26/all_leads_decision_makers_reviewed.csv"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh-audits",
        action="store_true",
        help="Re-crawl every lead instead of honoring the audit TTL.",
    )
    args = parser.parse_args()
    config = json.loads(
        (REPO_ROOT / "config/lead-loop.json").read_text(encoding="utf-8")
    )
    now = datetime.now(timezone.utc)
    audit_ttl = timedelta(days=int(config.get("audit_ttl_days", 7)))
    CONTINUOUS_DIR.mkdir(parents=True, exist_ok=True)
    master_path = CONTINUOUS_DIR / "all_leads.csv"
    previous = read_rows(master_path)
    existing = previous or seed_initial_leads()
    workflow_rows = []
    latest_workflow_domains = set()
    for workflow in ("businesses", "coaches", "agency_partners"):
        workflow_path = CONTINUOUS_DIR / workflow / "all_leads.csv"
        relevant_rows = [
            row
            for row in read_rows(workflow_path)
            if workflow_row_relevant(row, workflow)
        ]
        write_master_csv(workflow_path, relevant_rows)
        workflow_rows.extend(relevant_rows)
        latest_path = CONTINUOUS_DIR / workflow / "new_leads_latest.csv"
        relevant_latest_rows = [
            row
            for row in read_rows(latest_path)
            if workflow_row_relevant(row, workflow)
        ]
        write_master_csv(latest_path, relevant_latest_rows)
        latest_workflow_domains.update(
            domain_key(row.get("website", ""))
            for row in relevant_latest_rows
            if domain_key(row.get("website", ""))
        )
        sync_workflow_counts(workflow, relevant_rows, relevant_latest_rows)
    combined, _ = merge_leads(existing, workflow_rows)
    combined = [
        row
        for row in combined
        if not public_sector_domain(row.get("website", ""))
        and not unsuitable_outreach_email(row.get("email", ""))
        and (
            row.get("workflow") not in {"businesses", "coaches", "agency_partners"}
            or workflow_row_relevant(row, row["workflow"])
        )
    ]
    audit_dir = CONTINUOUS_DIR / "analysis"
    audit_dir.mkdir(parents=True, exist_ok=True)
    seed_audit_file(INITIAL_AUDITS, audit_dir / "meeting_queue.csv")
    seed_audit_file(INITIAL_RESEARCH, audit_dir / "research_queue.csv")
    combined_domains = {
        domain_key(row.get("website", ""))
        for row in combined
        if domain_key(row.get("website", ""))
    }
    retain_csv_domains(audit_dir / "meeting_queue.csv", combined_domains)
    retain_csv_domains(audit_dir / "research_queue.csv", combined_domains)
    audited_domains = set() if args.refresh_audits else {
        domain_key(row.get("website", ""))
        for row in (
            read_rows(audit_dir / "meeting_queue.csv")
            + read_rows(audit_dir / "research_queue.csv")
        )
        if domain_key(row.get("website", "")) and audit_is_fresh(row, now, audit_ttl)
    }
    audit_rows = [
        row
        for row in combined
        if domain_key(row.get("website", "")) not in audited_domains
    ]
    previous_domains = {
        domain_key(row.get("website", ""))
        for row in previous
        if domain_key(row.get("website", ""))
    }
    new_rows = [
        row
        for row in combined
        if (
            domain_key(row.get("website", "")) not in previous_domains
            or domain_key(row.get("website", "")) in latest_workflow_domains
        )
    ]
    write_master_csv(master_path, combined)
    write_master_csv(CONTINUOUS_DIR / "new_leads_latest.csv", new_rows)

    if audit_rows:
        new_audits_dir = CONTINUOUS_DIR / "_latest_audit_input"
        write_rows(new_audits_dir / "leads.csv", MASTER_FIELDS, audit_rows)
        latest_analysis = CONTINUOUS_DIR / "_latest_analysis"
        run_meeting_orchestrator(
            input_dir=new_audits_dir,
            out_dir=latest_analysis,
            max_leads=len(audit_rows),
        )
        refreshed_domains = {
            domain_key(row.get("website", ""))
            for row in audit_rows
            if domain_key(row.get("website", ""))
        }
        remove_csv_domains(audit_dir / "meeting_queue.csv", refreshed_domains)
        remove_csv_domains(audit_dir / "research_queue.csv", refreshed_domains)
        merge_csv_by_domain(
            audit_dir / "meeting_queue.csv",
            latest_analysis / "meeting_queue.csv",
        )
        merge_csv_by_domain(
            audit_dir / "research_queue.csv",
            latest_analysis / "research_queue.csv",
        )

    drafts_dir = CONTINUOUS_DIR / "outreach-drafts"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/generate-outreach-drafts.py"),
            "--leads",
            str(master_path),
            "--reviewed",
            str(INITIAL_CONTACTS),
            "--audits",
            str(audit_dir / "meeting_queue.csv"),
            "--out",
            str(drafts_dir),
            "--frontend-data",
            str(REPO_ROOT / "apps/outreach-draft-review/data.js"),
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_leads": len(combined),
        "new_leads": len(new_rows),
        "workflow_totals": {
            workflow: len(
                read_rows(CONTINUOUS_DIR / workflow / "all_leads.csv")
            )
            for workflow in ("businesses", "coaches", "agency_partners")
        },
        "master_csv": str(master_path.resolve()),
        "frontend_data": str(
            (REPO_ROOT / "apps/outreach-draft-review/data.js").resolve()
        ),
    }
    save_json_atomic(CONTINUOUS_DIR / "latest_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


def seed_initial_leads() -> list[dict[str, str]]:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for row in read_rows(INITIAL_LEADS):
        seeded = dict(row)
        seeded.update(
            {
                "workflow": "legacy_seed",
                "business_size_tier": (
                    "small" if row.get("segment") == "small_business" else ""
                ),
                "region": "americas_seed",
                "first_seen_at": row.get("created_at") or now,
                "last_seen_at": now,
                "loop_cycle": "seed",
            }
        )
        rows.append(seeded)
    return rows


def sync_workflow_counts(
    workflow: str,
    rows: list[dict[str, str]],
    latest_rows: list[dict[str, str]],
) -> None:
    workflow_dir = CONTINUOUS_DIR / workflow
    for name in ("state.json", "latest_summary.json"):
        path = workflow_dir / name
        if not path.exists():
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        value["total_leads"] = len(rows)
        if name == "state.json":
            value["last_new_leads"] = len(latest_rows)
        else:
            value["new_leads"] = len(latest_rows)
        save_json_atomic(path, value)


def seed_audit_file(source: Path, target: Path) -> None:
    if target.exists() or not source.exists():
        return
    rows = read_rows(source)
    fields = list(rows[0]) if rows else []
    write_rows(target, fields, rows)


def merge_csv_by_domain(master_path: Path, new_path: Path) -> None:
    existing = read_rows(master_path)
    new_rows = read_rows(new_path)
    if not existing and not new_rows:
        return
    by_domain = {
        domain_key(row.get("website", "")): row
        for row in existing
        if domain_key(row.get("website", ""))
    }
    for row in new_rows:
        key = domain_key(row.get("website", ""))
        if key:
            by_domain[key] = row
    fields = union_fields(existing + new_rows)
    write_rows(master_path, fields, list(by_domain.values()))


def remove_csv_domains(path: Path, domains: set[str]) -> None:
    rows = read_rows(path)
    if not rows:
        return
    kept = [
        row
        for row in rows
        if domain_key(row.get("website", "")) not in domains
    ]
    write_rows(path, list(rows[0]), kept)


def retain_csv_domains(path: Path, domains: set[str]) -> None:
    rows = read_rows(path)
    if not rows:
        return
    kept = [
        row
        for row in rows
        if domain_key(row.get("website", "")) in domains
    ]
    write_rows(path, list(rows[0]), kept)


def audit_is_fresh(
    row: dict[str, str],
    now: datetime,
    ttl: timedelta,
) -> bool:
    raw = row.get("audited_at", "").strip()
    if not raw:
        return False
    try:
        audited_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if audited_at.tzinfo is None:
        audited_at = audited_at.replace(tzinfo=timezone.utc)
    return now - audited_at <= ttl


def union_fields(rows: list[dict[str, str]]) -> list[str]:
    fields = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    return fields


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


if __name__ == "__main__":
    raise SystemExit(main())
