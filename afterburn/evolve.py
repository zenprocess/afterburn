"""CCAR experiment loop integration for skill evolution."""

import sys


def run_evolve(args) -> None:
    """Evolve a skill via CCAR experiment loop."""
    # TODO: Integrate vendored CCAR scripts
    print(f"Evolving skill: {args.skill}")
    print(f"Max iterations: {args.max_iterations}")
    if args.dry_run:
        print("[dry-run] Would benchmark and evolve — no changes made")
        return
    print("[stub] Evolve not yet implemented — requires CCAR script integration")
    sys.exit(1)
