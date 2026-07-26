# Outreach Draft Review

Review five meeting-focused NexStudio email drafts for every approved
decision-maker lead.

Generate the latest data:

```bash
pnpm generate:drafts
```

Open `index.html` directly in a browser. The interface is static and does not
send email.

Open `workflow-control.html` for the static workflow control panel. It lists
every discovery, enrichment, audit, meeting, continuous-loop, and draft command
with a copy button. Run copied commands from the repository root; the page does
not execute commands itself.
