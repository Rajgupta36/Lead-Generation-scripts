from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.export import CANDIDATE_FIELDS, LEAD_FIELDS
from leadgen.extract import is_valid_email
from leadgen.filters import blocked_domain
from leadgen.meeting_orchestrator import run_meeting_orchestrator
from leadgen.pipeline import run_pipeline
from leadgen.urltools import domain_key


SEGMENT_QUOTAS = {
    "small_business": 34,
    "agency_owner": 33,
    "coach": 33,
}

AMERICAS_COUNTRIES = {
    "Argentina",
    "Brazil",
    "Canada",
    "Chile",
    "Colombia",
    "Costa Rica",
    "Ecuador",
    "Mexico",
    "Panama",
    "Peru",
    "USA",
    "Uruguay",
}

NORTH_AMERICA = {"Canada", "Costa Rica", "Mexico", "Panama", "USA"}

MARKETS = (
    ("Miami", "USA"),
    ("Bogota", "Colombia"),
    ("Austin", "USA"),
    ("Sao Paulo", "Brazil"),
    ("Toronto", "Canada"),
    ("Buenos Aires", "Argentina"),
    ("Mexico City", "Mexico"),
    ("Santiago", "Chile"),
    ("Vancouver", "Canada"),
    ("Lima", "Peru"),
    ("Dallas", "USA"),
    ("Medellin", "Colombia"),
    ("Montreal", "Canada"),
    ("Rio de Janeiro", "Brazil"),
    ("Panama City", "Panama"),
    ("Quito", "Ecuador"),
    ("San Jose", "Costa Rica"),
    ("Montevideo", "Uruguay"),
    ("Los Angeles", "USA"),
    ("Curitiba", "Brazil"),
    ("New York", "USA"),
    ("Cordoba", "Argentina"),
    ("Guadalajara", "Mexico"),
    ("Cali", "Colombia"),
    ("Chicago", "USA"),
    ("Belo Horizonte", "Brazil"),
    ("Calgary", "Canada"),
    ("Guayaquil", "Ecuador"),
    ("Seattle", "USA"),
    ("Brasilia", "Brazil"),
    ("Denver", "USA"),
    ("Porto Alegre", "Brazil"),
    ("Boston", "USA"),
    ("Rosario", "Argentina"),
    ("Ottawa", "Canada"),
    ("Valparaiso", "Chile"),
)

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
    "ejemplo",
    "legal",
    "myprivacy",
    "no-reply",
    "noreply",
    "privacy",
    "secretariat",
}

PUBLIC_ROLE_LOCAL_PARTS = {
    "admin",
    "contact",
    "hello",
    "info",
    "sales",
    "support",
    "team",
}

AGENCY_TERMS = (
    "agency",
    "agencia",
    "agence",
    "advertising",
    "branding",
    "creative",
    "créative",
    "diseño web",
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

OUTSIDE_AMERICAS_TERMS = (
    "australia",
    "bangalore",
    "berlin",
    "germany",
    "india",
    "london",
    "mumbai",
    "new delhi",
    "singapore",
    "sydney",
    "united kingdom",
)

OUTSIDE_AMERICAS_TLDS = (".au", ".de", ".fr", ".hu", ".in", ".nz", ".sg", ".uk")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate 100 Americas leads with both a website and a matching public email."
    )
    parser.add_argument("--target-leads", type=int, default=100)
    parser.add_argument("--results-per-query", type=int, default=20)
    parser.add_argument("--market-workers", type=int, default=4)
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--small-business-seed",
        default="data/output-americas-100-leads-2026-07-26/all_leads.csv",
    )
    parser.add_argument("--leads-out", default="data/output-americas-email-leads")
    parser.add_argument("--analysis-out", default="data/output-americas-email-analysis")
    args = parser.parse_args()

    if args.target_leads != sum(SEGMENT_QUOTAS.values()):
        parser.error(f"--target-leads must be {sum(SEGMENT_QUOTAS.values())} for the balanced campaign")
    if args.results_per_query <= 0 or args.market_workers <= 0:
        parser.error("--results-per-query and --market-workers must be greater than zero")

    leads_out = REPO_ROOT / args.leads_out
    analysis_out = REPO_ROOT / args.analysis_out
    staging_out = leads_out / "market_runs"
    rows_by_domain: dict[str, dict[str, str]] = {}
    used_emails: set[str] = set()
    searches_run = 0

    seed_path = REPO_ROOT / args.small_business_seed
    if seed_path.exists():
        add_rows(
            read_rows(seed_path),
            rows_by_domain,
            used_emails,
            segment="small_business",
            quota=SEGMENT_QUOTAS["small_business"],
        )
    print(f"small_business email leads: {segment_count(rows_by_domain, 'small_business')}", flush=True)

    completed_market_dirs: set[str] = set()
    if args.finalize_only or args.resume:
        for path in sorted(staging_out.glob("*/all_leads.csv")):
            staged_rows = read_rows(path)
            if not staged_rows:
                continue
            completed_market_dirs.add(path.parent.name)
            segment = staged_rows[0].get("segment", "")
            if segment not in SEGMENT_QUOTAS:
                continue
            searches_run += 1
            add_rows(
                staged_rows,
                rows_by_domain,
                used_emails,
                segment=segment,
                quota=SEGMENT_QUOTAS[segment],
            )
    if args.finalize_only:
        tasks: list[tuple[int, str, str, str]] = []
    else:
        tasks = [
            (market_index, segment, city, country)
            for market_index, (city, country) in enumerate(MARKETS, start=1)
            for segment in ("agency_owner", "coach", "small_business")
            if f"{market_index:02d}-{slug(city)}-{segment}" not in completed_market_dirs
        ]

    task_index = 0
    discovery_complete = not tasks
    with ThreadPoolExecutor(max_workers=max(1, args.market_workers)) as executor:
        pending = {}
        while pending or (not discovery_complete and task_index < len(tasks)):
            while (
                not discovery_complete
                and len(pending) < args.market_workers
                and task_index < len(tasks)
            ):
                task = tasks[task_index]
                task_index += 1
                _, segment, city, country = task
                if segment_count(rows_by_domain, segment) >= SEGMENT_QUOTAS[segment]:
                    continue
                searches_run += 1
                print(
                    f"[{task[0]}/{len(MARKETS)}] {segment}: {city}, {country}",
                    flush=True,
                )
                future = executor.submit(
                    run_market_task,
                    task,
                    staging_out,
                    args.results_per_query,
                )
                pending[future] = task

            if not pending:
                break
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                _, segment, city, country = pending.pop(future)
                try:
                    market_rows = future.result()
                except Exception as error:
                    print(f"  failed {segment} in {city}, {country}: {error}", flush=True)
                    continue
                add_rows(
                    market_rows,
                    rows_by_domain,
                    used_emails,
                    segment=segment,
                    quota=SEGMENT_QUOTAS[segment],
                )
                print(
                    f"  {segment} website+email total: "
                    f"{segment_count(rows_by_domain, segment)}/{SEGMENT_QUOTAS[segment]}",
                    flush=True,
                )

            if all(
                segment_count(rows_by_domain, segment) >= quota
                for segment, quota in SEGMENT_QUOTAS.items()
            ):
                discovery_complete = True

    selected = balanced_rows(rows_by_domain)
    write_lead_outputs(selected, leads_out)
    if len(selected) != args.target_leads:
        counts = Counter(row["segment"] for row in selected)
        print(
            f"Campaign incomplete: selected {len(selected)}/{args.target_leads} "
            f"website+email leads: {dict(counts)}",
            flush=True,
        )
        print("Analysis was not run for the incomplete campaign.", flush=True)
        return 2

    queued, queue_path = run_meeting_orchestrator(
        input_dir=leads_out,
        out_dir=analysis_out,
        max_leads=len(selected),
    )
    write_summary(selected, queued, searches_run, leads_out, analysis_out)

    counts = Counter(row["segment"] for row in selected)
    print(f"Selected {len(selected)} website+email leads: {dict(counts)}", flush=True)
    print(f"Generated {queued} evidence-backed email drafts", flush=True)
    print(f"Lead file: {leads_out / 'all_leads.csv'}", flush=True)
    print(f"Mail queue: {queue_path}", flush=True)
    print("No messages were sent; every draft remains needs_review.", flush=True)
    return 0 if len(selected) == args.target_leads else 2


def build_query(segment: str, city: str) -> str:
    if segment == "agency_owner":
        return (
            '("marketing agency" OR "web design agency" OR "SEO agency" OR "branding agency") '
            f'"{city}" ("contact us" OR "email us" OR "get in touch")'
        )
    if segment == "coach":
        return (
            '("business coach" OR "executive coach" OR "leadership coach" OR "career coach") '
            f'"{city}" ("contact" OR "email" OR "book a call")'
        )
    return (
        '("dentist" OR "med spa" OR "roofing company" OR "HVAC company") '
        f'"{city}" ("contact us" OR "book appointment" OR "request a quote")'
    )


def run_market_task(
    task: tuple[int, str, str, str],
    staging_out: Path,
    results_per_query: int,
) -> list[dict[str, str]]:
    market_index, segment, city, country = task
    market_out = staging_out / f"{market_index:02d}-{slug(city)}-{segment}"
    run_pipeline(
        provider_name="serper",
        env_path=REPO_ROOT / ".env",
        cities_path=REPO_ROOT / "config/cities.csv",
        dorks_path=REPO_ROOT / "config/dorks.yaml",
        industries_path=REPO_ROOT / "config/industries.txt",
        out_dir=market_out,
        max_queries=1,
        max_results_per_query=results_per_query,
        query=build_query(segment, city),
        segment=segment,
        city=city,
        country=country,
        request_timeout_seconds=5,
        crawl_delay_seconds=0,
        max_followup_pages=1,
        max_leads=results_per_query,
        crawl_workers=6,
        reject_junk_results=True,
    )
    return read_rows(market_out / "all_leads.csv")


def add_rows(
    rows: list[dict[str, str]],
    rows_by_domain: dict[str, dict[str, str]],
    used_emails: set[str],
    *,
    segment: str,
    quota: int,
) -> None:
    for row in sorted(rows, key=row_rank, reverse=True):
        if segment_count(rows_by_domain, segment) >= quota:
            return
        website = row.get("website", "").strip()
        email = row.get("email", "").strip().lower()
        country = row.get("country", "").strip()
        key = domain_key(website)
        if (
            not key
            or blocked_domain(website)
            or country not in AMERICAS_COUNTRIES
            or not is_valid_email(email)
            or not outreach_email(email)
            or not email_matches_website(email, website)
            or not segment_relevant(row, segment)
            or email in used_emails
            or key in rows_by_domain
        ):
            continue
        accepted = dict(row)
        accepted["segment"] = segment
        accepted["email"] = email
        rows_by_domain[key] = accepted
        used_emails.add(email)


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
    local_part, email_domain = email.split("@", 1)
    local_part = local_part.lower()
    email_domain = email_domain.lower()
    return bool(
        local_part
        and not local_part[0].isdigit()
        and local_part not in REJECTED_EMAIL_LOCAL_PARTS
        and not (
            email_domain in PUBLIC_EMAIL_DOMAINS
            and local_part in PUBLIC_ROLE_LOCAL_PARTS
        )
        and not re.fullmatch(r"[0-9a-f]{20,}", local_part)
    )


def segment_relevant(row: dict[str, str], segment: str) -> bool:
    website_domain = domain_key(row.get("website", ""))
    if website_domain.endswith(OUTSIDE_AMERICAS_TLDS):
        return False
    haystack = " ".join(
        (
            row.get("business_name", ""),
            row.get("title", ""),
            row.get("category", ""),
        )
    ).lower()
    if any(term in haystack for term in OUTSIDE_AMERICAS_TERMS):
        return False
    if segment == "agency_owner":
        return any(term in haystack for term in AGENCY_TERMS)
    if segment == "coach":
        return any(term in haystack for term in COACH_TERMS)
    return True


def balanced_rows(rows_by_domain: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for segment, quota in SEGMENT_QUOTAS.items():
        segment_rows = [row for row in rows_by_domain.values() if row.get("segment") == segment]
        selected.extend(sorted(segment_rows, key=row_rank, reverse=True)[:quota])
    return selected


def write_lead_outputs(rows: list[dict[str, str]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    for index, row in enumerate(rows, start=1):
        row["lead_id"] = f"L{index:06d}"
        row["created_at"] = created_at
    write_csv(out_dir / "all_leads.csv", CANDIDATE_FIELDS, rows)
    write_csv(out_dir / "leads.csv", LEAD_FIELDS, [row for row in rows if parse_int(row.get("score")) >= 70])
    write_csv(
        out_dir / "candidates_review.csv",
        CANDIDATE_FIELDS,
        [row for row in rows if parse_int(row.get("score")) < 70],
    )


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_summary(
    rows: list[dict[str, str]],
    queued: int,
    searches_run: int,
    leads_out: Path,
    analysis_out: Path,
) -> None:
    countries = Counter(row.get("country", "") for row in rows)
    continents = Counter(
        "North America" if row.get("country", "") in NORTH_AMERICA else "South America"
        for row in rows
    )
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "send_mode": "review_only",
        "requirements": ["website_required", "valid_public_email_required", "email_domain_matched"],
        "selected_leads": len(rows),
        "meeting_ready_email_drafts": queued,
        "research_required": len(rows) - queued,
        "segments": dict(sorted(Counter(row.get("segment", "") for row in rows).items())),
        "continents": dict(sorted(continents.items())),
        "countries": dict(sorted(countries.items())),
        "searches_run": searches_run,
        "lead_file": str((leads_out / "all_leads.csv").resolve()),
        "mail_queue": str((analysis_out / "meeting_queue.csv").resolve()),
        "research_queue": str((analysis_out / "research_queue.csv").resolve()),
    }
    analysis_out.mkdir(parents=True, exist_ok=True)
    (analysis_out / "campaign_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def segment_count(rows_by_domain: dict[str, dict[str, str]], segment: str) -> int:
    return sum(row.get("segment") == segment for row in rows_by_domain.values())


def row_rank(row: dict[str, str]) -> tuple[int, int]:
    return parse_int(row.get("score")), parse_int(row.get("website_score"))


def parse_int(value: str | None) -> int:
    try:
        return int(float((value or "0").replace(",", "")))
    except ValueError:
        return 0


def slug(value: str) -> str:
    return "-".join(value.lower().split())


if __name__ == "__main__":
    raise SystemExit(main())
