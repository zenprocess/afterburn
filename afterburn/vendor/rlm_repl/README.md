# RLM REPL — Recursive Language Model with REPL Sandbox

Reimplemented from the concepts in arXiv:2512.24601.

## Provenance

- **Paper**: "Recursive Language Models" by Alex L. Zhang, Tim Kraska, Omar Khattab
- **Reference implementation**: [alexzhang13/rlm-minimal](https://github.com/alexzhang13/rlm-minimal) (MIT)
- **This code**: Clean reimplementation using only `requests` (no openai/dotenv/rich deps)

## What changed from the reference

| Reference (rlm-minimal) | This reimplementation |
|---|---|
| Uses `openai` Python SDK | Uses raw `requests` to OpenAI-compatible endpoints |
| Uses `python-dotenv` | Reads env vars directly |
| Uses `rich` for logging | Prints to stderr |
| Single model client | Two-model architecture (root + recursive) |
| Generic prompts | Session analysis prompts in `afterburn/prompts/` |

The core algorithm is the same: load context into a Python REPL, let the LLM
write code to inspect and chunk it, provide `llm_query()` for recursive sub-calls,
loop until `FINAL()`.
