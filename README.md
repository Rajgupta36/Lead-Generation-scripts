# Lead Generator

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete lead-to-meeting workflow,
project boundaries, data contracts, and planned delivery loop.

A local Python CLI that turns Google-dork style query templates into reviewed lead CSVs for a web/freelancing agency.

The workflow is intentionally high-recall: it keeps possible prospects in `candidates_review.csv` instead of dropping them early when email or phone is missing.

## Setup

Python 3.10+ is enough. No third-party packages are required.

Copy the environment example and add at least one search API key:

```bash
cp .env.example .env
```

Supported live providers:

- `serper` with `SERPER_API_KEY` for Google-style dork discovery
- `serpapi` with `SERPAPI_API_KEY` for Google organic/dork discovery
- `serpapi_maps` with `SERPAPI_API_KEY` for Google Maps/local business discovery
- `brave` with `BRAVE_API_KEY`
- `file` with `SEARCH_RESULTS_FILE` for testing/importing saved search results
- `csv` with `SEARCH_RESULTS_FILE` or `--search-results-file` for seed lists exported from directories, CRMs, or lookalike research

## Turbo flows

This repo is also organized as a small Turborepo workspace. The lead and outreach flows live under `apps/` and all reuse the shared Python engine in `leadgen/`.

```bash
pnpm install
pnpm generate:maps          # Google Maps/local businesses
pnpm generate:apollo        # Dork discovery + Apollo organization enrichment
pnpm generate:directories   # CSV seeds from niche directories
pnpm generate:opportunities # Website improvement signal discovery
pnpm generate:lookalikes    # CSV seeds matching your ideal customer profile
pnpm generate:x-founders    # Free dork discovery + manual Grok verification
pnpm generate:audits        # Meeting-first sales assets from generated leads
pnpm generate:meetings      # $1K-$2K offer-matched meeting queue
pnpm generate:nexstudio     # Complete discovery-to-meeting NexStudio pipeline
pnpm generate:americas      # 100 review-only North/South America leads and drafts
pnpm generate:americas-email # 100 Americas leads requiring website + matched email
pnpm enrich:decision-makers # Add public founder/owner/CEO emails with evidence
pnpm review:decision-makers # Apply reviewed corrections and create the sendable queue
pnpm generate:drafts        # Generate five emails per reviewed lead and refresh the review UI
```

Each app has a `flow.json` file with its provider, query or seed file, crawler settings, and output directory.

The X Premium founder flow is intentionally semi-automated. Brave Search dorks
discover profiles with explicit founder/co-founder titles and screen indexed
follower counts. It then creates copy/paste prompts for Grok to verify the live
blue Premium badge, current follower count, and a publicly evidenced direct
founder email. Generic role inboxes are excluded. It never scrapes or automates
X, and only imports email-qualified profiles below 1,000 followers after review. See
[`apps/x-premium-founder-flow/README.md`](apps/x-premium-founder-flow/README.md).

The audit workflow creates internal Markdown reports and a CSV summary for outreach review. Its goal is to lead prospects to a meeting: each row includes a recommended service, specific problem, business impact, what to show on a 10-minute call, meeting email, and call talk track.

The meeting orchestrator qualifies direct business sites before generating outreach. It rejects directories and failed audits, preserves verified evidence, and matches qualified leads to one of three offers: High-Intent Service Page Pack, Website Conversion Sprint, or Lead Response Automation Setup. Sendable rows go to `meeting_queue.csv`; held and rejected rows go to `research_queue.csv`.

The end-to-end NexStudio flow defaults to med spas in Miami and supports `med_spa`, `dentist`, `roofing`, `hvac`, and `immigration_law` presets. Every generated email starts from a visible website observation and asks for a 15-minute walkthrough. Nothing is sent automatically.

## Run

```bash
python3 -m leadgen run \
  --provider file \
  --search-results-file tests/fixtures_search_results.json \
  --max-results-per-query 10 \
  --out data/output
```

For cleaner manual research, use [LEAD_RESEARCH_PLAYBOOK.md](LEAD_RESEARCH_PLAYBOOK.md).

For live search:

```bash
python3 -m leadgen run --provider serper --max-queries 50 --max-results-per-query 10
```

Run one exact dork/query:

```bash
python3 -m leadgen run \
  --provider serper \
  --query '("agency owner" OR "founder") ("marketing agency" OR "branding agency" OR "creative agency") ("contact" OR "email") ("United States" OR "United Kingdom" OR "Canada" OR "Germany")' \
  --segment agency_owner \
  --max-results-per-query 100 \
  --request-timeout 5 \
  --crawl-delay 0 \
  --max-followup-pages 0 \
  --out data/output-custom-dork
```

For higher-quality local business discovery:

```bash
python3 -m leadgen run --provider serpapi_maps --max-queries 50 --max-results-per-query 20
```

## Outputs

- `data/output/leads.csv`: review-ready leads with score >= 70.
- `data/output/candidates_review.csv`: possible leads with score 40-69, or target-matching reachable prospects that need manual research.
- `data/output/run_log.jsonl`: crawl/search errors and skipped URLs.

Lead CSVs include discovery-ready columns such as `source_provider`, `address`,
`category`, `maps_rating`, `maps_reviews`, `maps_place_id`, `website_score`,
`enrichment_provider`, `enrichment_status`, and `email_validation_status`.

## Environment

Required for your live discovery setup:

```env
SERPER_API_KEY=your_serper_key
```

Required only if you enable Apollo enrichment:

```env
APOLLO_API_KEY=your_apollo_api_key
APOLLO_WEBHOOK_URL=https://your-webhook.example/path
```

Apollo keys are sent with the `x-api-key` header.

Apollo enrichment is optional and runs after Serper/crawling:

```bash
python3 -m leadgen run \
  --provider serper \
  --query '("agency owner" OR "founder") ("marketing agency" OR "branding agency" OR "creative agency") ("contact" OR "email") ("United States" OR "United Kingdom" OR "Canada" OR "Germany")' \
  --segment agency_owner \
  --max-results-per-query 100 \
  --apollo-enrich \
  --apollo-max-leads 25 \
  --out data/output-apollo-test
```

By default, `--apollo-enrich` uses only Apollo Organization Enrichment. It does
not call People Search or People Enrichment.

Only add `--apollo-people` if your Apollo key has People Search and People
Enrichment permissions. Use `--apollo-reveal-personal-emails` only when you want
Apollo to spend credits to reveal personal emails. Use
`--apollo-reveal-phone-number` only with `APOLLO_WEBHOOK_URL` or
`--apollo-webhook-url`, because Apollo sends phone results asynchronously to a
webhook.

Optional providers:

```env
SERPAPI_API_KEY=your_serpapi_key
BRAVE_API_KEY=your_brave_key
SEARCH_RESULTS_FILE=tests/fixtures_search_results.json
```

## Notes

- The crawler reads `robots.txt` and skips pages it is not allowed to fetch.
- Do not scrape Google result pages directly. Use a search/SERP API or saved result file.
- The CLI collects public business/contact information only.
