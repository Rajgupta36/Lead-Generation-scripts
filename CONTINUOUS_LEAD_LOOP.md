# Continuous Lead Loop

Three independent Turbo workflows run in parallel:

1. `continuous-business-leads`: small, medium, and large businesses.
2. `continuous-coach-leads`: business, executive, leadership, and career coaches.
3. `continuous-agency-partner-leads`: PR, paid media, social, email, influencer,
   and video agencies that do not advertise SEO, website design, or website
   development.

Run one parallel cycle:

```bash
pnpm lead-loop:once
```

Run continuously using the interval in `config/lead-loop.json`:

```bash
pnpm lead-loop
```

Install the recurring macOS background schedule:

```bash
pnpm lead-loop:install
```

The default interval is 12 hours. Each workflow rotates Europe,
Australia/New Zealand, North America, and South America, persists its own
cursor, and deduplicates by website domain and email.

Outputs:

```text
data/continuous-leads/businesses/all_leads.csv
data/continuous-leads/coaches/all_leads.csv
data/continuous-leads/agency_partners/all_leads.csv
data/continuous-leads/all_leads.csv
data/continuous-leads/new_leads_latest.csv
data/continuous-leads/analysis/meeting_queue.csv
data/continuous-leads/outreach-drafts/outreach_drafts.csv
```

No email is sent automatically. The loop only discovers, audits, deduplicates,
and refreshes draft data.
