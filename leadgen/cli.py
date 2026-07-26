from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_pipeline
from .x_founders import discover_x_founders, finalize_x_founders


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate high-recall web agency leads from dork queries.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run the lead generation pipeline.")
    run.add_argument("--provider", default="serper", choices=["file", "csv", "serpapi", "serpapi_maps", "serper", "brave"])
    run.add_argument("--env", default=".env")
    run.add_argument("--cities", default="config/cities.csv")
    run.add_argument("--dorks", default="config/dorks.yaml")
    run.add_argument("--industries", default="config/industries.txt")
    run.add_argument("--out", default="data/output")
    run.add_argument("--max-queries", type=int, default=20)
    run.add_argument("--max-results-per-query", type=int, default=10)
    run.add_argument("--search-results-file", default=None)
    run.add_argument("--query", default=None, help="Run one exact search dork/query instead of config-generated dorks.")
    run.add_argument("--segment", default="agency_owner")
    run.add_argument("--city", default="")
    run.add_argument("--country", default="")
    run.add_argument("--request-timeout", type=float, default=None)
    run.add_argument("--crawl-delay", type=float, default=None)
    run.add_argument("--max-followup-pages", type=int, default=4)
    run.add_argument("--max-leads", type=int, default=None)
    run.add_argument("--crawl-workers", type=int, default=1)
    run.add_argument("--allow-junk-results", action="store_true")
    run.add_argument("--apollo-enrich", action="store_true", help="Enrich leads with Apollo after discovery/crawling.")
    run.add_argument("--apollo-max-leads", type=int, default=None, help="Limit Apollo enrichment calls to the first N leads.")
    run.add_argument("--apollo-people", action="store_true", help="Also call Apollo People Search/People Enrichment. Requires those API permissions.")
    run.add_argument("--apollo-reveal-personal-emails", action="store_true")
    run.add_argument("--apollo-reveal-phone-number", action="store_true")
    run.add_argument("--apollo-webhook-url", default="")

    x_founders = subparsers.add_parser(
        "x-founders",
        help="Discover X founder profiles with web dorks and finalize manual Grok reviews.",
    )
    x_actions = x_founders.add_subparsers(dest="x_action", required=True)

    discover = x_actions.add_parser("discover", help="Build a Grok review queue from indexed X profiles.")
    discover.add_argument("--provider", default="brave", choices=["brave", "file"])
    discover.add_argument("--env", default=".env")
    discover.add_argument("--out", default="data/output-x-premium-founders")
    discover.add_argument("--target", type=int, default=100)
    discover.add_argument("--results-per-query", type=int, default=20)
    discover.add_argument("--max-search-requests", type=int, default=200)
    discover.add_argument("--batch-size", type=int, default=20)
    discover.add_argument("--search-results-file", default=None)
    discover.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Use a custom dork. Repeat the flag to provide multiple queries.",
    )

    finalize = x_actions.add_parser(
        "finalize",
        help="Validate an imported Grok CSV and export qualified founder leads.",
    )
    finalize.add_argument("--review-file", required=True)
    finalize.add_argument("--candidates-file", default=None)
    finalize.add_argument("--out", default="data/output-x-premium-founders")
    finalize.add_argument("--target", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        leads = run_pipeline(
            provider_name=args.provider,
            env_path=Path(args.env),
            cities_path=Path(args.cities),
            dorks_path=Path(args.dorks),
            industries_path=Path(args.industries),
            out_dir=Path(args.out),
            max_queries=args.max_queries,
            max_results_per_query=args.max_results_per_query,
            search_results_file=args.search_results_file,
            query=args.query,
            segment=args.segment,
            city=args.city,
            country=args.country,
            request_timeout_seconds=args.request_timeout,
            crawl_delay_seconds=args.crawl_delay,
            max_followup_pages=args.max_followup_pages,
            max_leads=args.max_leads,
            crawl_workers=args.crawl_workers,
            reject_junk_results=not args.allow_junk_results,
            apollo_enrich=args.apollo_enrich,
            apollo_max_leads=args.apollo_max_leads,
            apollo_people=args.apollo_people,
            apollo_reveal_personal_emails=args.apollo_reveal_personal_emails,
            apollo_reveal_phone_number=args.apollo_reveal_phone_number,
            apollo_webhook_url=args.apollo_webhook_url,
        )
        high = sum(1 for lead in leads if lead.score >= 70)
        review = sum(1 for lead in leads if lead.score < 70)
        print(f"Generated {high} leads and {review} manual-review candidates in {args.out}")
        return 0
    if args.command == "x-founders" and args.x_action == "discover":
        if args.target < 1:
            parser.error("--target must be at least 1")
        if args.results_per_query < 1:
            parser.error("--results-per-query must be at least 1")
        if args.max_search_requests < 1:
            parser.error("--max-search-requests must be at least 1")
        candidates = discover_x_founders(
            provider_name=args.provider,
            env_path=Path(args.env),
            out_dir=Path(args.out),
            target=args.target,
            results_per_query=args.results_per_query,
            max_search_requests=args.max_search_requests,
            batch_size=args.batch_size,
            search_results_file=args.search_results_file,
            queries=args.queries,
        )
        print(
            f"Generated {len(candidates)} candidates and Grok review batches in {args.out}"
        )
        return 0
    if args.command == "x-founders" and args.x_action == "finalize":
        if args.target < 1:
            parser.error("--target must be at least 1")
        out_dir = Path(args.out)
        candidates_file = (
            Path(args.candidates_file)
            if args.candidates_file
            else out_dir / "candidates_review.csv"
        )
        leads = finalize_x_founders(
            review_file=Path(args.review_file),
            candidates_file=candidates_file,
            out_dir=out_dir,
            target=args.target,
        )
        print(f"Qualified {len(leads)} X Premium founder leads in {out_dir}")
        return 0
    return 2
