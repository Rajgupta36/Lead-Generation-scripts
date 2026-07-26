# NexStudio Outreach Pipeline

Runs the complete local-service agency workflow:

1. Find direct business websites with Serper.
2. Crawl the homepage and useful contact/service pages.
3. Remove directories, duplicates, failed sites, and unreachable leads.
4. Match each qualified lead to a $1K-$2K NexStudio offer.
5. Generate a verified meeting angle, email, and call brief.

Default run:

```bash
pnpm generate:nexstudio
```

Custom target:

```bash
python3 scripts/run-nexstudio-pipeline.py \
  --niche dentist \
  --city Austin \
  --country USA \
  --max-results 30
```

Supported presets: `med_spa`, `dentist`, `roofing`, `hvac`, and `immigration_law`.

The workflow never sends automatically. Review `meeting_queue.csv`; leads that need more work are placed in `research_queue.csv`.
