---
description: Analyze Claude Code session history — extract friction, patterns, and skill gaps
allowed-tools: ["Bash(python*:*)", "Read", "Write", "Glob"]
---

# /insights — Session Intelligence Analysis

Analyze your Claude Code conversation history to find what keeps going wrong, what works well, and what's missing.

Powered by [Afterburn](https://github.com/zenprocess/afterburn).

## Step 1 — Check Afterburn

```!
python -m afterburn --help 2>/dev/null || echo "AFTERBURN_NOT_INSTALLED"
```

If not installed, tell the user:
```
Afterburn is not installed. Install with:
  pip install git+https://github.com/zenprocess/afterburn.git
```
Then stop.

## Step 2 — Run discovery

```!
python -m afterburn discover $ARGUMENTS
```

## Step 3 — Present results

Read output files from `.afterburn/` and present a structured summary:

1. **Friction** (`.afterburn/fix-list.md`): Top recurring issues with verification commands
2. **Patterns** (`.afterburn/pattern-catalog.md`): Successful approaches with confidence scores
3. **Gaps** (`.afterburn/skill-candidates/`): Proposed new skills

For patterns with confidence >= 0.7, show the draft CLAUDE.md rule and ask:
> "Would you like me to add any of these to your CLAUDE.md?"

For skill gaps, show the draft and ask:
> "Would you like me to create any of these as skills?"
