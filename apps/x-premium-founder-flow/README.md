# X Premium Founder Flow

Discovers public X profiles through Brave Search dorks, keeps profiles whose
indexed bio explicitly says founder, co-founder, or cofounder, and creates review
prompts for Grok. It does not scrape or automate the X website.

## 1. Discover candidates

Set `BRAVE_API_KEY` in the repository `.env`, then run:

```bash
pnpm generate:x-founders
```

The flow uses Brave's web-search API and writes:

- `data/output-x-premium-founder-flow/candidates_review.csv`
- `data/output-x-premium-founder-flow/grok_review_batches.csv`
- `data/output-x-premium-founder-flow/grok_prompts.md`
- `data/output-x-premium-founder-flow/run_log.jsonl`

Indexed follower counts are only screening hints. Profiles with an indexed
count of 1,000 or more are omitted from the Grok queue; profiles with a missing
count remain in the queue for a live check.

## 2. Review with Grok

Open `grok_prompts.md`, paste each prompt into Grok, and combine Grok's CSV rows
into one file such as:

```text
data/output-x-premium-founder-flow/grok_reviews.csv
```

Keep the exact CSV header requested by the prompt. Review any ambiguous Grok
answer manually on X. A blue badge must represent Premium or Premium+, not a
Verified Organization affiliate. Grok must also find a direct person-level email
that is explicitly published for the founder and return its public evidence URL.
The workflow never guesses an email pattern.

## 3. Finalize qualified leads

```bash
python3 -m leadgen x-founders finalize \
  --review-file data/output-x-premium-founder-flow/grok_reviews.csv \
  --out data/output-x-premium-founder-flow \
  --target 100
```

`leads.csv` only includes rows where Grok confirmed an explicit founder or
co-founder title, a non-affiliate blue Premium check, a live follower count below
1,000, and a publicly evidenced direct email for that same person. Generic role
inboxes such as `info@`, `hello@`, `contact@`, `support@`, `sales@`, `team@`, and
`admin@` are rejected.

Otherwise-qualified profiles without a direct email are written to
`email_research_queue.csv`. The final lead status remains
`qualified_needs_human_spot_check`; verify the email evidence before outreach.
No outreach is sent automatically.

## Custom discovery

Use one or more exact dorks:

```bash
python3 -m leadgen x-founders discover \
  --query 'site:x.com "Founder" "Followers" SaaS' \
  --query 'site:x.com "Co-Founder" "Followers" AI' \
  --out data/output-x-premium-founder-flow
```

Use `--max-search-requests` to cap Brave requests. The default built-in dork set
currently contains fewer queries than the 200-request cap.
