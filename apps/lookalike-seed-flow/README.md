# Lookalike Seed Flow

Starts from a hand-picked list of companies matching the ideal customer profile. Add businesses that look like your best customers, then let the shared crawler and scorer normalize them into lead CSVs.

Run:

```bash
pnpm generate:lookalikes
```

Replace `data/seeds/lookalike-seeds.csv` with real seed companies. Required columns are `title` and `url`.
