# Afterburn

**Extract residual intelligence from spent sessions.**

Afterburn mines your [Claude Code](https://docs.anthropic.com/en/docs/claude-code) conversation history to find what keeps going wrong, what works well, and how to make your skills better — automatically.

```
$ afterburn discover

Scanning 120 sessions (1.5GB) from ~/.claude/projects/-home-user-myproject/...
Processing: ████████████████████████████░░░░ 89/120 sessions (156 LLM calls)

✓ Fix list:        .afterburn/fix-list.md         (23 recurring issues found)
✓ Pattern catalog: .afterburn/pattern-catalog.md   (12 successful patterns)
✓ Skill gaps:      .afterburn/skill-candidates/    (4 candidate skills)
```

## What It Does

Every Claude Code session produces a full conversation transcript — your messages, Claude's responses, tool calls, errors, corrections, confirmations. These transcripts pile up in `~/.claude/projects/` and are never read again.

Afterburn reads them. It runs three analysis passes:

| Pass | Finds | Produces |
|------|-------|----------|
| **Friction** | Recurring errors, user corrections, tool denials, failed hooks | `fix-list.md` with verification commands |
| **Patterns** | Approaches that consistently worked, user confirmations | `pattern-catalog.md` with draft CLAUDE.md rules |
| **Gaps** | Manual multi-step workflows repeated across sessions | `skill-candidates/` with draft SKILL.md files |

Then, optionally, it can **evolve** existing skills:

```
$ afterburn evolve --skill dispatch --max-iterations 10

Evolving: dispatch (baseline correction_rate: 0.34)
  #1 keep  → 0.31 (added retry guidance for hook failures)
  #2 keep  → 0.28 (removed ambiguous scope language)
  #3 discard → 0.35 (regressed, reverted)
  ...
  #8 keep  → 0.22 (best)

✓ Experiment branch: afterburn/dispatch-1712179200
  Baseline: 0.34 → Best: 0.22 (35% improvement)
  8 iterations: 5 kept, 2 discarded, 1 crashed
```

## How It Works

### The Scale Problem

Your session files can be enormous — we've seen individual transcripts hit 93MB. No context window can hold that. Afterburn uses **RLM REPL** (Recursive Language Models) to solve this:

1. The session is loaded into a Python REPL as a variable — never into the LLM's context
2. The root LLM writes Python code to inspect, filter, and chunk the data
3. It calls `llm_query()` on each chunk for focused analysis
4. Sub-results are aggregated and synthesized into findings

This means a 93MB file with 45,000 messages gets filtered down to ~200 relevant messages before any expensive LLM calls happen.

### The Evolution Loop

Skill evolution uses **CCAR** (Claude Code AutoResearch) — an autonomous experiment loop:

1. **Baseline**: Compute a benchmark score from historical skill invocations
2. **Mutate**: Claude proposes a change to the SKILL.md based on failure analysis
3. **Benchmark**: Run the mutated skill against test cases from history
4. **Gate**: If improved → git commit. If regressed → git restore.
5. **Repeat**: Until max iterations or convergence

Everything stays on a git branch. Nothing touches your main branch until you review and merge.

## Install

### As a Python CLI

```bash
pip install afterburn
# or
pip install git+https://github.com/zenprocess/afterburn.git
```

### As Claude Code Slash Commands

```bash
afterburn install           # Install to current project's .claude/commands/
afterburn install --global  # Install to ~/.claude/commands/ (all projects)
```

Then in Claude Code:
```
/afterburn-discover              # Run all three passes
/afterburn-discover --pass friction --since 2026-03-01
/afterburn-evolve --skill dispatch --max-iterations 5
/afterburn-status                # Show last run summary
```

## Usage

### Discover

```bash
# All three passes on the current project
afterburn discover

# Single pass
afterburn discover --pass friction
afterburn discover --pass patterns
afterburn discover --pass gaps

# Filter by date
afterburn discover --since 2026-03-01

# Filter by project
afterburn discover --project -home-user-myproject

# Custom session directory (e.g., from another machine)
afterburn discover --sessions-dir /mnt/mac-sessions/.claude/projects/

# JSON output for programmatic use
afterburn discover --format json

# Include worktree sessions (excluded by default)
afterburn discover --include-worktrees

# Limit LLM calls (default: 1000)
afterburn discover --max-calls 500
```

### Evolve

```bash
# Evolve a skill with CCAR experiment loop
afterburn evolve --skill dispatch --max-iterations 10

# Dry run — show what would be benchmarked
afterburn evolve --skill dispatch --dry-run

# Check experiment status
afterburn status
```

### Output

All outputs are written to `.afterburn/` in the current directory:

```
.afterburn/
├── fix-list.md              # Recurring issues with verification commands
├── pattern-catalog.md       # Successful patterns with draft rules
├── skill-candidates/        # Draft SKILL.md files for identified gaps
│   ├── candidate-001.md
│   └── candidate-002.md
├── state.json               # Incremental analysis state
├── errors.log               # Any processing errors
└── provenance.json          # What was analyzed, when, with what model
```

## Configuration

Afterburn needs an LLM endpoint. It supports two model roles:

| Role | Purpose | Default |
|------|---------|---------|
| Root model | Orchestration, strategy, synthesis | Claude API (`ANTHROPIC_API_KEY`) |
| Recursive model | Chunk analysis (high volume, can be cheaper) | Local vLLM auto-discover |

### Environment Variables

```bash
# Model backends
AFTERBURN_ROOT_MODEL=claude           # or "auto" for local vLLM
AFTERBURN_RECURSIVE_MODEL=auto        # vLLM/llama.cpp auto-discover
AFTERBURN_API_URL=http://localhost:8080/v1  # Local model endpoint

# For Claude API as root model
ANTHROPIC_API_KEY=sk-ant-...
```

### Two-Model Architecture

The recommended setup uses Claude for orchestration (strong reasoning) and a local model for chunk analysis (cheap, fast, private):

```bash
# Claude orchestrates, local Qwen handles volume
AFTERBURN_ROOT_MODEL=claude
AFTERBURN_RECURSIVE_MODEL=auto
AFTERBURN_API_URL=http://localhost:8080/v1
```

For fully local operation:

```bash
# Everything local — no API key needed
AFTERBURN_ROOT_MODEL=auto
AFTERBURN_RECURSIVE_MODEL=auto
AFTERBURN_API_URL=http://localhost:8080/v1
```

## Privacy

- **Read-only**: Session files are never modified
- **Redaction**: Outputs sanitize secrets (API keys, tokens, passwords) and truncate tool results to 200 chars
- **Local-first**: Runs against local models (vLLM, llama.cpp) with zero data leaving your machine
- **No telemetry**: Nothing phones home

## Requirements

- Python 3.10+
- `requests` (only pip dependency)
- `jq` (for CCAR experiment scripts)
- An LLM endpoint (Claude API or local vLLM/llama.cpp)
- Linux or macOS

## How It Compares

| Tool | What it does | Difference |
|------|-------------|------------|
| Claude Code `/compact` | Compresses current conversation | Afterburn analyzes *past* conversations |
| Claude Code auto-memory | Saves key facts per session | Afterburn finds patterns *across* sessions |
| DSPy optimizers | Optimize LLM prompts via Python framework | Afterburn is framework-free, uses CCAR loops |
| CCAR standalone | Autonomous experiment loop | Afterburn adds session mining as the input source |

## Acknowledgements

Afterburn vendors and builds on two open-source projects:

- **[CCAR](https://github.com/mitkox/ccar)** by Mitko — Claude Code AutoResearch experiment loop (MIT license)
- **[RLM REPL](https://github.com/fullstackwebdev/rlm_repl)** by fullstackwebdev — Recursive Language Model REPL engine based on the paper by Zhang, Kraska & Khattab (MIT license)

The skill evolution approach was inspired by [DSPy's GEPA optimizer](https://dspy.ai/api/optimizers/GEPA/overview/) (Stanford NLP) and [NousResearch's hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution).

## License

MIT
