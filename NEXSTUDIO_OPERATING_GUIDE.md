# NexStudio Lead Engine

This is the permanent operating guide for the Apollo-first lead generation platform. It records the strategy, workflow, scoring model, review rules, and deployment requirements so the process does not need to be researched again.

## Strategy

NexStudio uses Apollo as the lead source and does not mass-scrape the web. Apollo supplies a targeted company, decision maker, title, domain, and email. The platform then audits the company website and creates a human-reviewed outreach draft.

Primary target: dental, cosmetic, implant, orthodontic, and other high-value healthcare practices that can benefit from website redesign, conversion optimisation, local SEO, and performance work.

Excluded from the first phase: Product Hunt, Clutch, Crunchbase, Google Maps, LinkedIn scraping, and broad web crawling as lead sources. Website crawling is used only to audit Apollo-selected companies.

## Pipeline

1. Export targeted people and companies from Apollo as CSV.
2. Import the CSV through the Apollo import flow.
3. Deduplicate companies by normalized domain.
4. Keep every imported record; do not pre-filter before auditing.
5. Audit each website asynchronously with the worker.
6. Score the company using the latest audit and contact status.
7. Generate a personalised draft only for companies scoring 40 or higher.
8. Review the draft manually.
9. Approve only relevant, verified, non-generic contact emails.
10. Send only after explicit approval; follow-ups remain controlled by the worker.

## Current local dataset

- 81 unique companies
- 82 contacts
- 81 companies audited
- 7 drafts in the review queue
- 0 emails sent

The duplicate company count is expected when multiple Apollo contacts belong to the same domain.

## Audit evidence

The website audit records response time, mobile rendering, missing metadata, forms, blog presence, cookie banner, broken links, screenshots/raw audit data, and technology signals where available. Drafts must reference concrete evidence from the audit; generic statements and invented observations are not acceptable.

## Lead scoring

The current production slice scores these signals:

- Outdated or incomplete website metadata: 25 points
- Slow initial response: 20 points
- Active blog: 15 points
- Verified founder/CEO decision-maker email: 30 points

The review threshold is 40. A score is a prioritisation signal, not automatic permission to send.

## Review URLs

With the local web server running:

- Dashboard: http://localhost:3000
- Website audit reports: http://localhost:3000/audits
- Draft messages: http://localhost:3000/review
- Health check: http://localhost:3000/api/health

## Production architecture

- Vercel: Next.js dashboard and route handlers
- Managed PostgreSQL: production data and audit history
- Redis: BullMQ queues
- Railway/Fly.io worker: website audits, scoring, AI generation, sending, and follow-ups
- Apollo CSV: no-cost lead acquisition mode
- OpenAI: optional AI analysis and copy generation; deterministic fallback remains available
- Resend: optional sending provider, disabled until configured

## Deployment environment

Required for the dashboard and workers:

```text
DATABASE_URL=managed PostgreSQL connection string
REDIS_URL=managed Redis connection string
NEXTAUTH_SECRET=random value of at least 32 characters
NEXTAUTH_URL=production dashboard URL
```

Optional:

```text
OPENAI_API_KEY=AI analysis and copy generation
RESEND_API_KEY=email delivery
OUTREACH_FROM_EMAIL=verified sender address
APOLLO_API_KEY=live Apollo API mode; not needed for CSV mode
```

Do not use local Docker PostgreSQL or Redis URLs in Vercel. Vercel cannot run the persistent worker; deploy the worker separately and point both services at the same managed PostgreSQL and Redis instances.

## Safety rules

- Never send automatically from a newly imported CSV.
- Never send to `info@`, `support@`, `sales@`, `contact@`, or `hello@` without explicit approval.
- Keep all drafts in `DRAFT` until a human approves them.
- Do not add another lead source unless it improves targeting quality.
- Do not delete audit history when rerunning an audit; use the latest audit for current scoring.

## Useful commands

```bash
pnpm install
pnpm --filter @nexstudio/db db:generate
pnpm typecheck
pnpm test
pnpm --filter @nexstudio/web build
```

Vercel deploys from the repository root using `vercel.json`; the root package includes Next.js so Vercel can detect the framework. The BullMQ worker must run separately on Railway or Fly.io.
