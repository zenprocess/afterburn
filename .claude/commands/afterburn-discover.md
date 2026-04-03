---
description: Analyze Claude Code session history for friction, patterns, and skill gaps
allowed-tools: ["Bash(python*:*)", "Read", "Write", "Glob"]
---

# Afterburn Discover

Run the Afterburn session analysis tool:

```!
python -m afterburn discover $ARGUMENTS
```

After the analysis completes, read the output files from `.afterburn/` and present a summary to the user:

1. Read `.afterburn/fix-list.md` if it exists and summarize the top 5 recurring issues
2. Read `.afterburn/pattern-catalog.md` if it exists and summarize the top 5 patterns
3. Read `.afterburn/skill-candidates/` if any files exist and list proposed skills

Present findings grouped by category with actionable next steps.
