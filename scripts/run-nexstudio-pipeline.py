from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.meeting_orchestrator import run_meeting_orchestrator
from leadgen.pipeline import run_pipeline


TARGET_PRESETS = {
    "med_spa": {
        "businesses": ("med spa", "medical spa", "aesthetic clinic"),
        "services": ("botox", "dermal fillers", "laser hair removal"),
    },
    "dentist": {
        "businesses": ("dentist", "dental clinic", "cosmetic dentist"),
        "services": ("dental implants", "invisalign", "cosmetic dentistry"),
    },
    "roofing": {
        "businesses": ("roofing company", "roofer", "roof contractor"),
        "services": ("roof repair", "roof replacement", "emergency roofing"),
    },
    "hvac": {
        "businesses": ("HVAC company", "air conditioning contractor", "heating contractor"),
        "services": ("AC repair", "HVAC installation", "emergency HVAC"),
    },
    "immigration_law": {
        "businesses": ("immigration lawyer", "immigration law firm", "visa attorney"),
        "services": ("green card", "work visa", "citizenship"),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run NexStudio lead discovery through the meeting-ready outreach queue."
    )
    parser.add_argument("--niche", choices=sorted(TARGET_PRESETS), default="med_spa")
    parser.add_argument("--city", default="Miami")
    parser.add_argument("--country", default="USA")
    parser.add_argument("--max-results", type=int, default=30)
    parser.add_argument("--max-leads", type=int, default=30)
    parser.add_argument("--leads-out", default="data/output-nexstudio-leads")
    parser.add_argument("--meetings-out", default="data/output-nexstudio-meetings")
    args = parser.parse_args()

    query = build_query(args.niche, args.city)
    leads = run_pipeline(
        provider_name="serper",
        env_path=REPO_ROOT / ".env",
        cities_path=REPO_ROOT / "config/cities.csv",
        dorks_path=REPO_ROOT / "config/dorks.yaml",
        industries_path=REPO_ROOT / "config/industries.txt",
        out_dir=REPO_ROOT / args.leads_out,
        max_queries=1,
        max_results_per_query=args.max_results,
        query=query,
        segment="small_business",
        city=args.city,
        country=args.country,
        request_timeout_seconds=8,
        crawl_delay_seconds=0,
        max_followup_pages=2,
        max_leads=args.max_leads,
        crawl_workers=4,
        reject_junk_results=True,
    )
    queued, queue_path = run_meeting_orchestrator(
        input_dir=REPO_ROOT / args.leads_out,
        out_dir=REPO_ROOT / args.meetings_out,
        max_leads=args.max_leads,
    )
    print(f"Discovered {len(leads)} direct-site candidates")
    print(f"Qualified {queued} meeting-ready prospects")
    print(f"Meeting queue: {queue_path}")
    print(f"Research queue: {REPO_ROOT / args.meetings_out / 'research_queue.csv'}")
    return 0


def build_query(niche: str, city: str) -> str:
    preset = TARGET_PRESETS[niche]
    businesses = quoted_or_group(preset["businesses"])
    services = quoted_or_group(preset["services"])
    return (
        f"({businesses}) \"{city}\" ({services}) "
        '("contact us" OR "book appointment" OR "request a quote" OR "schedule consultation")'
    )


def quoted_or_group(values: tuple[str, ...]) -> str:
    return " OR ".join(f'"{value}"' for value in values)


if __name__ == "__main__":
    raise SystemExit(main())
