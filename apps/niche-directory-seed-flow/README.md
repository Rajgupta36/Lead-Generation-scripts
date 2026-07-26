# Niche Directory Seed Flow

Starts from a CSV export of businesses found in niche directories, then crawls the actual company websites. This avoids broad search noise while keeping the existing extraction and scoring engine.

Run:

```bash
pnpm generate:directories
```

Replace `data/seeds/niche-directory-seeds.csv` with real directory exports. Required columns are `title` and `url`; optional columns include `snippet`, `category`, `address`, `phone`, `rating`, and `reviews`.
