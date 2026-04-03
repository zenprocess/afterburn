---
description: Archive old Claude Code sessions (>7 days) to .tgz and clean history
allowed-tools: ["Bash(python*:*)", "Read", "Glob"]
---

# Afterburn Archive

Archive stale session data and clean history for the current project.

## Step 1 — Ask about analysis first

Before archiving, ask the user:

> These sessions will be archived and removed. Would you like me to run `/afterburn-discover` first to extract insights before they're compressed?
> (The .tgz archive preserves the raw data, but analysis is faster on uncompressed files.)

If the user says yes, run `/afterburn-discover` first and wait for it to complete before proceeding.

If the user says no or wants to skip, proceed directly to Step 2.

## Step 2 — Run the archive

```!
python -m afterburn archive $ARGUMENTS
```

## Step 3 — Report results

After archiving, report:
- How many sessions were archived
- Total size before vs. after (uncompressed → compressed)
- Archive file location
- How many history entries were cleaned
