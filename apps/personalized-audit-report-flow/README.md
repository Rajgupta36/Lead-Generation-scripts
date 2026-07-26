# Personalized Audit Report Flow

Generates meeting-first sales assets from an existing lead output folder. The report is internal enablement; the primary output is a recommended service, specific problem, business impact, meeting email, and call talk track.

Run:

```bash
pnpm generate:audits
```

By default this reads `data/output-website-opportunity-flow` and writes Markdown reports plus `audit_report_summary.csv` into `data/reports/personalized-audit-report-flow`.

The CSV is designed for outreach review. Key columns:

- `recommended_service`
- `specific_problem`
- `business_impact`
- `what_to_show_on_call`
- `email_subject`
- `meeting_email`
- `call_talk_track`

To report on a different flow manually:

```bash
python3 scripts/generate-audit-reports.py \
  --input-dir data/output-google-maps-local-flow \
  --out data/reports/google-maps-local-audits
```
