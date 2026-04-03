---
description: Evolve a skill's SKILL.md via metric-gated experiment loop
allowed-tools: ["Bash(python*:*)", "Bash(git*:*)", "Bash(.claude/scripts/*:*)", "Read", "Write", "Edit"]
---

# Afterburn Evolve

Run the Afterburn skill evolution loop:

```!
python -m afterburn evolve $ARGUMENTS
```

Monitor the experiment progress. After completion, summarize:

1. Baseline metric vs. best metric
2. Number of iterations: kept, discarded, crashed
3. Key changes that were kept
4. The experiment branch name for review
