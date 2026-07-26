from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from leadgen.export import export_csv
from leadgen.meeting_orchestrator import run_meeting_orchestrator
from leadgen.models import Lead
from leadgen.pipeline import run_pipeline
from leadgen.score import merge_leads
from leadgen.urltools import domain_key


@dataclass(frozen=True)
class Market:
    continent: str
    niche: str
    city: str
    country: str


# Interleaving continents prevents an early target from filling with one region.
AMERICAS_MARKETS = (
    Market("North America", "med_spa", "Miami", "USA"),
    Market("South America", "dentist", "Bogota", "Colombia"),
    Market("North America", "dentist", "Austin", "USA"),
    Market("South America", "med_spa", "Medellin", "Colombia"),
    Market("North America", "roofing", "Dallas", "USA"),
    Market("South America", "dentist", "Lima", "Peru"),
    Market("North America", "hvac", "Phoenix", "USA"),
    Market("South America", "med_spa", "Santiago", "Chile"),
    Market("North America", "dentist", "Toronto", "Canada"),
    Market("South America", "dentist", "Buenos Aires", "Argentina"),
    Market("North America", "med_spa", "Vancouver", "Canada"),
    Market("South America", "med_spa", "Cordoba", "Argentina"),
    Market("North America", "dentist", "Mexico City", "Mexico"),
    Market("South America", "dentist", "Sao Paulo", "Brazil"),
    Market("North America", "med_spa", "Monterrey", "Mexico"),
    Market("South America", "med_spa", "Rio de Janeiro", "Brazil"),
    Market("North America", "immigration_law", "Panama City", "Panama"),
    Market("South America", "dentist", "Belo Horizonte", "Brazil"),
    Market("North America", "dentist", "San Jose", "Costa Rica"),
    Market("South America", "med_spa", "Quito", "Ecuador"),
    Market("North America", "med_spa", "Guadalajara", "Mexico"),
    Market("South America", "dentist", "Montevideo", "Uruguay"),
    Market("North America", "dentist", "Montreal", "Canada"),
    Market("South America", "med_spa", "Guayaquil", "Ecuador"),
    Market("North America", "roofing", "Atlanta", "USA"),
    Market("South America", "dentist", "Curitiba", "Brazil"),
    Market("North America", "hvac", "Orlando", "USA"),
    Market("South America", "med_spa", "Barranquilla", "Colombia"),
)


TARGET_PRESETS = {
    "med_spa": {
        "businesses": ("med spa", "medical spa", "aesthetic clinic", "clinica estetica"),
        "services": ("botox", "dermal fillers", "laser hair removal", "depilacion laser"),
    },
    "dentist": {
        "businesses": ("dentist", "dental clinic", "dentista", "clinica dental"),
        "services": ("dental implants", "invisalign", "cosmetic dentistry", "implantes dentales"),
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
        "businesses": ("immigration lawyer", "immigration law firm", "abogado de inmigracion"),
        "services": ("work visa", "citizenship", "visa de trabajo", "residencia"),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a review-only NexStudio lead and outreach campaign across the Americas."
    )
    parser.add_argument("--target-leads", type=int, default=100)
    parser.add_argument("--discovery-buffer", type=int, default=25)
    parser.add_argument("--results-per-market", type=int, default=10)
    parser.add_argument("--leads-out", default="data/output-americas-100-leads")
    parser.add_argument("--meetings-out", default="data/output-americas-100-analysis")
    args = parser.parse_args()

    if args.target_leads <= 0:
        parser.error("--target-leads must be greater than zero")
    if args.results_per_market <= 0:
        parser.error("--results-per-market must be greater than zero")

    leads_out = REPO_ROOT / args.leads_out
    meetings_out = REPO_ROOT / args.meetings_out
    staging_out = leads_out / "market_runs"
    discovery_target = args.target_leads + max(0, args.discovery_buffer)
    leads_by_domain: dict[str, Lead] = {}
    market_by_domain: dict[str, Market] = {}
    markets_run: list[Market] = []

    for index, market in enumerate(AMERICAS_MARKETS, start=1):
        if len(leads_by_domain) >= discovery_target:
            break
        market_out = staging_out / f"{index:02d}-{slug(market.city)}-{market.niche}"
        query = build_query(market)
        print(
            f"[{index}/{len(AMERICAS_MARKETS)}] {market.continent}: "
            f"{market.niche} in {market.city}, {market.country}"
        )
        market_leads = run_pipeline(
            provider_name="serper",
            env_path=REPO_ROOT / ".env",
            cities_path=REPO_ROOT / "config/cities.csv",
            dorks_path=REPO_ROOT / "config/dorks.yaml",
            industries_path=REPO_ROOT / "config/industries.txt",
            out_dir=market_out,
            max_queries=1,
            max_results_per_query=args.results_per_market,
            query=query,
            segment="small_business",
            city=market.city,
            country=market.country,
            request_timeout_seconds=8,
            crawl_delay_seconds=0,
            max_followup_pages=2,
            max_leads=args.results_per_market,
            crawl_workers=4,
            reject_junk_results=True,
        )
        markets_run.append(market)
        for lead in market_leads:
            key = domain_key(lead.website)
            if not key:
                continue
            if key in leads_by_domain:
                leads_by_domain[key] = merge_leads(leads_by_domain[key], lead)
            else:
                leads_by_domain[key] = lead
                market_by_domain[key] = market
        print(f"  retained {len(market_leads)}; campaign unique total {len(leads_by_domain)}")

    ranked = sorted(leads_by_domain.values(), key=lead_rank, reverse=True)
    selected = ranked[: args.target_leads]
    export_csv(selected, leads_out)

    queued, queue_path = run_meeting_orchestrator(
        input_dir=leads_out,
        out_dir=meetings_out,
        max_leads=len(selected),
    )
    write_summary(
        leads_out=leads_out,
        meetings_out=meetings_out,
        selected=selected,
        market_by_domain=market_by_domain,
        markets_run=markets_run,
        requested=args.target_leads,
        discovered=len(leads_by_domain),
        queued=queued,
    )

    print(f"Selected {len(selected)} unique Americas leads")
    print(f"Generated {queued} evidence-backed outreach drafts")
    print(f"Lead file: {leads_out / 'all_leads.csv'}")
    print(f"Meeting queue: {queue_path}")
    print(f"Research queue: {meetings_out / 'research_queue.csv'}")
    print("No messages were sent; every draft remains needs_review.")
    return 0 if len(selected) >= args.target_leads else 2


def build_query(market: Market) -> str:
    preset = TARGET_PRESETS[market.niche]
    businesses = quoted_or_group(preset["businesses"])
    services = quoted_or_group(preset["services"])
    actions = quoted_or_group(
        ("contact us", "book appointment", "request a quote", "contacto", "agendar cita")
    )
    return f'({businesses}) "{market.city}" ({services}) ({actions})'


def quoted_or_group(values: tuple[str, ...]) -> str:
    return " OR ".join(f'"{value}"' for value in values)


def lead_rank(lead: Lead) -> tuple[int, int, int, int]:
    outreach_rank = 3 if lead.email else 2 if lead.contact_page else 1 if lead.phone else 0
    return outreach_rank, lead.score, lead.website_score, len(lead.source_urls)


def write_summary(
    *,
    leads_out: Path,
    meetings_out: Path,
    selected: list[Lead],
    market_by_domain: dict[str, Market],
    markets_run: list[Market],
    requested: int,
    discovered: int,
    queued: int,
) -> None:
    continent_counts: Counter[str] = Counter()
    country_counts: Counter[str] = Counter()
    niche_counts: Counter[str] = Counter()
    for lead in selected:
        market = market_by_domain.get(domain_key(lead.website))
        if not market:
            continue
        continent_counts[market.continent] += 1
        country_counts[market.country] += 1
        niche_counts[market.niche] += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "send_mode": "review_only",
        "requested_leads": requested,
        "unique_leads_discovered": discovered,
        "selected_leads": len(selected),
        "meeting_ready_drafts": queued,
        "research_required": max(0, len(selected) - queued),
        "markets_run": len(markets_run),
        "continents": dict(sorted(continent_counts.items())),
        "countries": dict(sorted(country_counts.items())),
        "niches": dict(sorted(niche_counts.items())),
        "lead_file": str(leads_out / "all_leads.csv"),
        "meeting_queue": str(meetings_out / "meeting_queue.csv"),
        "research_queue": str(meetings_out / "research_queue.csv"),
    }
    (meetings_out / "campaign_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def slug(value: str) -> str:
    return "-".join(value.lower().split())


if __name__ == "__main__":
    raise SystemExit(main())
