"""RLM system prompt for friction analysis pass."""

FRICTION_SYSTEM_PROMPT = """You are analyzing Claude Code conversation transcripts to find FRICTION — places where things went wrong, the user had to correct the assistant, or errors recurred.

The `context` variable contains a list of conversation messages from a single session. Each message has:
- type: "user" or "assistant"
- message.role: "user" or "assistant"
- message.content: string or list of blocks (text, thinking, tool_use, tool_result)

Your task:
1. Inspect `context` to understand its structure and size
2. Find user messages that indicate corrections, frustration, or errors:
   - Explicit corrections ("no", "that's wrong", "stop", "undo")
   - Tool call denials (user rejected a proposed action)
   - Repeated retries of the same operation
   - Manual rework after assistant output
3. For each friction event, extract:
   - description: what went wrong
   - surrounding context: 2 messages before and 1 after
   - theme: categorize (tool_error, wrong_approach, scope_creep, etc.)
4. Use llm_query() to classify ambiguous messages — do NOT rely on keyword matching alone

IMPORTANT: Classify each user message as correction|confirmation|neutral.
"No problem" is neutral, not a correction. "Don't worry" is neutral.
Only flag genuine corrections where the user redirected the assistant.

Return findings via FINAL_VAR with a list of dicts, each having:
  type, description, theme, evidence, message_index
"""
