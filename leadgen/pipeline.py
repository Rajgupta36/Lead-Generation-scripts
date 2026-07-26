from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .apollo import ApolloClient
from .config import load_cities, load_dorks, load_env, load_industries
from .crawl import Crawler
from .dorks import SearchQuery, generate_queries
from .export import append_log, export_csv
from .filters import is_rejected_search_result
from .models import Lead, SearchResult
from .score import build_lead, merge_leads
from .search import SearchProvider, create_provider, is_transient_search_error
from .urltools import domain_key


def run_pipeline(
    provider_name: str,
    env_path: Path,
    cities_path: Path,
    dorks_path: Path,
    industries_path: Path,
    out_dir: Path,
    max_queries: int | None,
    max_results_per_query: int,
    search_results_file: str | None = None,
    query: str | None = None,
    segment: str = "agency_owner",
    city: str = "",
    country: str = "",
    request_timeout_seconds: float | None = None,
    crawl_delay_seconds: float | None = None,
    max_followup_pages: int = 4,
    max_leads: int | None = None,
    crawl_workers: int = 1,
    reject_junk_results: bool = True,
    apollo_enrich: bool = False,
    apollo_max_leads: int | None = None,
    apollo_people: bool = False,
    apollo_reveal_personal_emails: bool = False,
    apollo_reveal_phone_number: bool = False,
    apollo_webhook_url: str = "",
    provider: SearchProvider | None = None,
    crawler: Crawler | None = None,
) -> list[Lead]:
    load_env(env_path)
    reset_run_log(out_dir)
    if query:
        queries = [
            SearchQuery(
                segment=segment,
                query=query,
                city=city,
                country=country,
            )
        ]
    else:
        cities = load_cities(cities_path)
        dorks = load_dorks(dorks_path)
        industries = load_industries(industries_path)
        queries = generate_queries(dorks, cities, industries, limit=max_queries)
    search_provider = provider or create_provider(provider_name, search_results_file)
    crawler = crawler or Crawler(
        timeout_seconds=request_timeout_seconds,
        delay_seconds=crawl_delay_seconds,
        max_followup_pages=max_followup_pages,
    )
    leads_by_domain: dict[str, Lead] = {}
    pending_results: list[SearchResult] = []

    for search_query in queries:
        try:
            results = search_provider.search(search_query.query, max_results_per_query)
        except Exception as error:
            append_log(
                out_dir,
                {
                    "event": "search_failed",
                    "query": search_query.query,
                    "error": str(error),
                    "transient": is_transient_search_error(error),
                },
            )
            continue

        for result in hydrate_results(results, search_query):
            if reject_junk_results:
                rejected, reason = is_rejected_search_result(result)
                if rejected:
                    append_log(
                        out_dir,
                        {
                            "event": "search_result_rejected",
                            "url": result.url,
                            "title": result.title,
                            "reason": reason,
                        },
                    )
                    continue
            key = domain_key(result.url)
            if key in leads_by_domain:
                stub = build_lead(result, None)
                leads_by_domain[key] = merge_leads(leads_by_domain[key], stub)
                continue
            if any(domain_key(existing.url) == key for existing in pending_results):
                continue
            pending_results.append(result)
            if max_leads and len(leads_by_domain) + len(pending_results) >= max_leads:
                break

        if max_leads and len(leads_by_domain) + len(pending_results) >= max_leads:
            break

    if crawl_workers <= 1:
        for result in pending_results:
            crawl_result = crawler.crawl(result.url)
            add_crawled_lead(result, crawl_result, leads_by_domain, out_dir)
    else:
        with ThreadPoolExecutor(max_workers=crawl_workers) as executor:
            future_to_result = {
                executor.submit(
                    Crawler(
                        timeout_seconds=request_timeout_seconds,
                        delay_seconds=crawl_delay_seconds,
                        max_followup_pages=max_followup_pages,
                    ).crawl,
                    result.url,
                ): result
                for result in pending_results
            }
            for future in as_completed(future_to_result):
                result = future_to_result[future]
                try:
                    crawl_result = future.result()
                except Exception as error:
                    append_log(
                        out_dir,
                        {
                            "event": "crawl_issue",
                            "url": result.url,
                            "detail": f"crawl_exception:{error}",
                        },
                    )
                    lead = build_lead(result, None)
                    leads_by_domain[domain_key(result.url)] = lead
                    continue
                add_crawled_lead(result, crawl_result, leads_by_domain, out_dir)

    leads = list(leads_by_domain.values())
    if apollo_enrich:
        enrich_leads_with_apollo(
            leads,
            out_dir=out_dir,
            max_leads=apollo_max_leads,
            include_people=apollo_people,
            reveal_personal_emails=apollo_reveal_personal_emails,
            reveal_phone_number=apollo_reveal_phone_number,
            webhook_url=apollo_webhook_url,
        )
    export_csv(leads, out_dir)
    return leads


def hydrate_results(results: list[SearchResult], query) -> list[SearchResult]:
    hydrated: list[SearchResult] = []
    for result in results:
        result.source_query = query.query
        result.segment = query.segment
        result.city = query.city
        result.country = query.country
        hydrated.append(result)
    return hydrated


def should_retain_candidate(lead: Lead) -> bool:
    if lead.score >= 40:
        return True
    if lead.website and lead.segment in {"agency_owner", "coach", "creator", "small_business", "shop_owner", "tutor"}:
        return True
    return False


def add_crawled_lead(result, crawl_result, leads_by_domain: dict[str, Lead], out_dir: Path) -> None:
    key = domain_key(result.url)
    for error in crawl_result.errors:
        append_log(out_dir, {"event": "crawl_issue", "url": result.url, "detail": error})
    lead = build_lead(result, crawl_result.contact)
    if should_retain_candidate(lead):
        leads_by_domain[key] = lead
    else:
        append_log(
            out_dir,
            {
                "event": "candidate_dropped_low_score",
                "url": result.url,
                "score": lead.score,
                "segment": result.segment,
            },
        )


def reset_run_log(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "run_log.jsonl"
    if log_path.exists():
        log_path.unlink()


def enrich_leads_with_apollo(
    leads: list[Lead],
    out_dir: Path,
    max_leads: int | None,
    include_people: bool,
    reveal_personal_emails: bool,
    reveal_phone_number: bool,
    webhook_url: str,
) -> None:
    client = ApolloClient()
    selected = leads if max_leads is None else leads[:max_leads]
    for lead in selected:
        try:
            client.enrich_lead(
                lead,
                include_people=include_people,
                reveal_personal_emails=reveal_personal_emails,
                reveal_phone_number=reveal_phone_number,
                webhook_url=webhook_url,
            )
        except Exception as error:
            lead.enrichment_provider = "apollo"
            lead.enrichment_status = "failed"
            append_log(
                out_dir,
                {
                    "event": "apollo_enrichment_failed",
                    "website": lead.website,
                    "error": str(error),
                },
            )
