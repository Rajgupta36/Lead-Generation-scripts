# NexStudio Lead Engine

Apollo-first lead generation, website auditing, qualification, personalised email drafts, and human-reviewed outreach for NexStudio.

## Product strategy

Apollo is the only lead source in the first phase. Apollo CSV exports provide targeted companies, decision makers, domains, and contact emails. The platform audits those websites and creates evidence-based drafts. It does not mass-scrape the web and does not send automatically.

The first target segment is high-value dental, cosmetic, implant, orthodontic, and healthcare practices that can benefit from website redesign, conversion optimisation, performance work, and local SEO.

## Workflow

`Apollo CSV → deduplicate → audit every company → score → generate drafts → human review → approve → send`

Current local dataset: 81 unique companies, 82 contacts, 81 completed audits, 7 drafts, and 0 emails sent.

## Run locally

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d
pnpm install
pnpm --filter @nexstudio/db db:generate
pnpm --filter @nexstudio/web dev
```

Run the worker separately:

```bash
pnpm --filter @nexstudio/worker dev
```

Open:

- Dashboard: http://localhost:3000
- Audit reports: http://localhost:3000/audits
- Draft review: http://localhost:3000/review

## Validation

```bash
pnpm typecheck
pnpm test
pnpm --filter @nexstudio/web build
```

## Deployment

The Next.js app is configured for Vercel with `vercel.json`. The BullMQ worker must run separately on Railway or Fly.io. Production requires managed PostgreSQL and Redis; local Docker URLs must not be used in production.

See [`NEXSTUDIO_OPERATING_GUIDE.md`](NEXSTUDIO_OPERATING_GUIDE.md) for the permanent strategy, scoring rules, safety rules, environment variables, review URLs, and deployment checklist. See [`PRODUCTION_ARCHITECTURE.md`](PRODUCTION_ARCHITECTURE.md) for the detailed system design.
