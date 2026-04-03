---
description: "Enhanced /insights — narrative report with selectable timeframe and project filter. What you did, what went well, what didn't."
allowed-tools: ["Bash(python*:*)", "Read"]
---

# /enhanced-insights — Narrative Development Report

Like the built-in `/insights` but with selectable timeframes, per-project focus, and actionable suggestions.

## Step 1 — Ask timeframe

If no timeframe is provided in `$ARGUMENTS`, ask the user:

> What timeframe would you like the report to cover?
> - `--today` — just today
> - `--week` — last 7 days
> - `--month` — last 30 days
> - `--since YYYY-MM-DD` — custom start date
>
> Optionally filter by project: `--project <slug>`

## Step 2 — Generate

```!
python -m afterburn narrative $ARGUMENTS
```

## Step 3 — Present

Read `.afterburn/narrative.md` and present the full report to the user. Highlight:
- The satisfaction ratio (confirmations vs corrections)
- The top friction points
- The suggestions section

## Step 4 — Follow-up

Suggest:
- "Run `/afterburn-discover` for deep pattern mining across these sessions"
- "Run `afterburn archive` to clean up old sessions"
- If friction is high: "Consider adding rules to CLAUDE.md to address the top friction points"
