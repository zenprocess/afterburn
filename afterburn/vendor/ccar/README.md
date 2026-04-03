# Vendored: CCAR (Claude Code AutoResearch)

Source: https://github.com/mitkox/ccar
License: MIT
Author: Mitko (https://github.com/mitkox)

Vendored for the autonomous experiment loop that drives skill evolution.

## Files to vendor

From the CCAR repo, copy:
- `.claude/scripts/common.sh` → `scripts/common.sh`
- `.claude/scripts/init-experiment.sh` → `scripts/init-experiment.sh`
- `.claude/scripts/run-experiment.sh` → `scripts/run-experiment.sh`
- `.claude/scripts/log-experiment.sh` → `scripts/log-experiment.sh`
- `.claude/scripts/summarize-session.sh` → `scripts/summarize-session.sh`
- `.claude/hooks/stop-hook.sh` → `hooks/stop-hook.sh`
- `.claude/hooks/session-start.sh` → `hooks/session-start.sh`

Paths in scripts need adjustment to reference this vendored location.
