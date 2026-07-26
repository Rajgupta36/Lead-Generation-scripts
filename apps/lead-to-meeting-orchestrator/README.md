# Lead To Meeting Orchestrator

Turns generated lead CSVs into a review queue for small $1K-$2K productized service meetings.

Run:

```bash
pnpm generate:meetings
```

Default input:

```text
data/output-website-opportunity-flow
```

Default output:

```text
data/output-lead-to-meeting-orchestrator/meeting_queue.csv
data/output-lead-to-meeting-orchestrator/meeting_queue.jsonl
data/output-lead-to-meeting-orchestrator/lead_reports/*.md
data/output-lead-to-meeting-orchestrator/research_queue.csv
```

The orchestrator checks the direct homepage, removes directory/profile results, cleans business names, and holds failed or unreachable leads in `research_queue.csv`. It only writes evidence-backed prospects to the meeting queue.

It does not send email automatically. Every qualified row starts with `send_status=needs_review`.
