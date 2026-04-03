# Vendored: RLM REPL (Recursive Language Model REPL)

Source: https://github.com/fullstackwebdev/rlm_repl
License: MIT
Author: fullstackwebdev (https://github.com/fullstackwebdev)

Vendored for processing session transcripts that exceed LLM context windows.
Based on "Recursive Language Models" by Zhang, Kraska, Khattab (arXiv:2512.24601).

## Files to vendor

From the rlm_repl repo, copy:
- `rlm/rlm.py` → `rlm.py`
- `rlm/rlm_repl.py` → `rlm_repl.py`
- `rlm/repl.py` → `repl.py`
- `rlm/utils/llm.py` → `utils/llm.py`
- `rlm/utils/prompts.py` → `utils/prompts.py`
- `rlm/utils/tracing.py` → `utils/tracing.py`
- `rlm/utils/parsing.py` → `utils/parsing.py`

Session-specific prompts are added in `afterburn/prompts/` (not vendored).
