# Afterburn: Extract Residual Intelligence from Spent Sessions

**A White Paper on Closed-Loop Learning from Claude Code Conversation History**

*April 2026*

---

## Abstract

Every Claude Code session produces a full conversation transcript — user messages, assistant responses, tool calls, results, errors, corrections, and confirmations. These transcripts are stored as JSONL files in `~/.claude/projects/` and are typically never read again. Afterburn is a Claude Code native tool that mines these transcripts to close three feedback loops that are currently open: (1) identifying recurring issues and verifying whether they've been fixed, (2) extracting successful patterns into codified rules and skills, and (3) iteratively improving existing skills through metric-gated experiment loops. It combines two recent open-source innovations — Recursive Language Models (RLM REPL) for processing transcripts that far exceed any context window, and Claude Code AutoResearch (CCAR) for autonomous experiment loops — into a single, dependency-free Python + bash toolkit.

## 1. The Problem: Open Feedback Loops

Software teams using AI coding assistants accumulate thousands of hours of interaction data. A single active project can generate 1.5GB+ of conversation transcripts across 120+ sessions. This data contains three types of signal that are currently lost:

### 1.1 Friction Signal
When a user corrects the assistant ("no, not that way", "stop", "that's wrong"), rejects a tool call, or manually redoes work the assistant attempted, this is a signal that something is broken or suboptimal. These corrections are scattered across sessions and forgotten. The same friction recurs session after session.

### 1.2 Success Signal
When a user confirms an approach ("yes exactly", "perfect"), accepts work without correction, or a multi-step workflow completes without intervention, this is a signal that a pattern works. But these successful patterns live only in the conversation — they are not promoted to project rules (CLAUDE.md), skills (SKILL.md), or hooks.

### 1.3 Evolution Signal
When a skill is invoked repeatedly across sessions, each invocation produces an outcome — success, partial success, or failure. This sequence of outcomes contains the gradient for improving the skill's prompt. But no mechanism exists to close the loop: the skill's SKILL.md stays static regardless of how well or poorly it performs.

## 2. The Solution: Three Closed Loops

Afterburn closes all three loops with machine-in-the-loop processing and human-as-gate review.

### 2.1 Loop 1: Friction Discovery

```
Sessions → [RLM REPL analysis] → Fix List → [Human verifies] → Issues resolved
```

The friction pass uses LLM classification (not keyword matching) to identify user corrections, tool denials, error patterns, and retries across all sessions. Each finding includes:
- What went wrong
- How often it occurred
- When it was last seen
- A verification command to check if it's been fixed

This transforms a 1.5GB haystack of conversation data into a concise, actionable checklist.

### 2.2 Loop 2: Pattern Extraction

```
Sessions → [RLM REPL analysis] → Pattern Catalog → [Human reviews] → CLAUDE.md / SKILL.md
```

The patterns pass identifies approaches that consistently succeeded across multiple sessions. Patterns that appear in 3+ sessions with user confirmation are flagged as "high confidence" and a draft codification is generated — either a CLAUDE.md rule or a SKILL.md skeleton. This is how implicit knowledge becomes explicit configuration.

### 2.3 Loop 3: Skill Evolution

```
Sessions → [Extract training data] → CCAR experiment loop → [Human reviews PR] → Better skill
```

For each existing skill, Afterburn extracts historical invocations from session transcripts as training examples. It then runs the CCAR (Claude Code AutoResearch) experiment loop: Claude proposes a mutation to the skill's SKILL.md, the mutation is benchmarked against historical outcomes, and the result is either committed (if improved) or reverted (if regressed). After N iterations, the best-performing variant is offered as a pull request.

## 3. Technical Architecture

### 3.1 RLM REPL: Processing Beyond Context Windows

The central technical challenge is scale. A single session transcript can be 93MB — far beyond any model's context window. Afterburn uses the Recursive Language Model REPL pattern (Zhang, Kraska, Khattab 2025; arXiv:2512.24601) to solve this.

In RLM REPL, the context is stored in a Python REPL environment as a variable. The root LLM receives metadata about the context (type, size, structure) and writes Python code to inspect and decompose it. It can call `llm_query()` to make recursive sub-LLM calls on chunks. The key insight: the root LLM can use Python to filter and transform data *before* spending tokens on sub-calls.

For a 93MB session file:

```python
# Root LLM writes this in the REPL
corrections = [msg for msg in context if msg['type'] == 'user'
               and any(kw in msg.get('message',{}).get('content','').lower()
                       for kw in ['no ', 'stop', 'wrong', "don't"])]
# 45,000 messages → ~200 candidates → llm_query() on each
```

The root model orchestrates (needs strong reasoning). The recursive model handles chunk analysis (can be smaller, cheaper, local). This two-model architecture means the expensive model does strategy while the cheap model does volume.

### 3.2 CCAR: Metric-Gated Experiment Loops

CCAR (Claude Code AutoResearch, mitkox 2026) provides the experiment infrastructure for skill evolution. Its design is elegant in its simplicity:

1. **Init**: Declare a metric name, unit, and direction (lower/higher is better)
2. **Run**: Execute a benchmark script that emits `METRIC name=value` lines
3. **Judge**: Claude evaluates: keep (improved), discard (regressed), or crash (failed)
4. **Log**: Append result to `autoresearch.jsonl`, commit or revert
5. **Loop**: A Stop hook re-injects the experiment prompt, preventing Claude from stopping

The entire state machine is bash + jq. No frameworks, no databases, no orchestrators. Git is the persistence layer — kept experiments are committed, discarded experiments are reverted.

### 3.3 Why Not DSPy?

DSPy's GEPA optimizer could theoretically optimize skill prompts. But Afterburn deliberately avoids framework dependencies:

- **Portability**: Python + bash + requests. No pip install nightmares.
- **Transparency**: Every step is a readable script. No magic.
- **Claude Code native**: Slash commands, hooks, and shell scripts — the same primitives Claude Code itself uses.
- **Local-first**: Works with vLLM/llama.cpp. No cloud dependency required.

The CCAR experiment loop achieves the same feedback-driven optimization that DSPy's optimizers provide, but using Claude itself as the optimizer rather than a Python framework.

## 4. Data Source

Claude Code stores conversation transcripts as JSONL files in `~/.claude/projects/<project-slug>/`. Each line is a JSON object with:

| Field | Description |
|-------|-------------|
| `type` | `user`, `assistant`, or `file-history-snapshot` |
| `message.role` | `user` or `assistant` |
| `message.content` | String or array of blocks: `text`, `thinking`, `tool_use`, `tool_result` |
| `sessionId` | UUID identifying the conversation |
| `cwd` | Working directory at time of message |
| `version` | Claude Code version |
| `gitBranch` | Active git branch |

A typical active project accumulates 100+ session files totaling 1-2GB over several weeks.

## 5. Privacy and Security

Session transcripts contain everything — code, credentials, API responses, file contents. Afterburn addresses this:

1. **Read-only**: Session files are never modified
2. **Redaction**: All outputs are sanitized — secret patterns stripped, tool results truncated to 200 chars, no verbatim JSONL copying
3. **Local processing**: RLM REPL and CCAR run locally. Model backends can be fully local (vLLM/llama.cpp)
4. **No telemetry**: Zero data leaves the machine unless the user explicitly configures a cloud model endpoint

## 6. Related Work

| Project | Relationship |
|---------|-------------|
| **RLM REPL** (fullstackwebdev) | Vendored. Provides the recursive decomposition engine for large context processing. MIT licensed. |
| **CCAR** (mitkox) | Vendored. Provides the experiment loop infrastructure for skill evolution. MIT licensed. |
| **DSPy GEPA** (Stanford NLP) | Intellectual ancestor. GEPA's reflective evolutionary optimization inspired the skill evolution loop, but Afterburn uses Claude directly instead of DSPy's Python framework. |
| **Claude Code source analysis** | Prior art. One-off analysis of Claude Code's own source to extract "borrowable patterns." Afterburn generalizes this from a one-time source analysis to a continuous conversation analysis. |
| **megacode** (mitkox) | Sibling project using DSPy RLM for security auditing of .NET repos. Demonstrated the RLM tool pattern for codebase analysis. |

## 7. Limitations and Future Work

**Current limitations**:
- Correction detection depends on LLM classification quality — false positives are possible
- Skill evolution benchmarks are non-deterministic when using live LLM calls
- Cross-machine session aggregation requires manual file transfer
- The RLM REPL sandbox is permissive (uses Python `exec()`)

**Future directions**:
- Continuous mode: watch for new sessions and analyze incrementally
- Team aggregation: merge findings across multiple developers
- Feedback integration: pipe findings directly into CLAUDE.md and SKILL.md with one-click accept
- Pattern similarity: detect when two different users independently discover the same pattern

## 8. Conclusion

The richest dataset about how AI coding assistants succeed and fail is sitting unused on every developer's machine. Afterburn extracts that signal — not by reading every message (impossible at 1.5GB), but by using recursive LLM decomposition to intelligently sample, classify, and synthesize findings. The result is a tool that makes Claude Code better at helping you, based on evidence from how it actually helped you before.

---

*Afterburn is open source under the MIT license. Repository: github.com/zenprocess/afterburn*

*Vendored components: RLM REPL (fullstackwebdev, MIT), CCAR (mitkox, MIT)*

*Part of [standra.ai](https://standra.ai) — Open Standards for the AI-Ready Enterprise*
