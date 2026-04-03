"""Afterburn CLI entry point."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="afterburn",
        description="Extract residual intelligence from spent Claude Code sessions",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # discover
    discover_parser = subparsers.add_parser("discover", help="Analyze session history")
    discover_parser.add_argument(
        "--pass",
        dest="analysis_pass",
        choices=["friction", "patterns", "gaps"],
        help="Run a single analysis pass (default: all three)",
    )
    discover_parser.add_argument("--since", help="Only analyze sessions after this date (YYYY-MM-DD)")
    discover_parser.add_argument("--project", help="Filter to a specific project slug")
    discover_parser.add_argument(
        "--sessions-dir",
        help="Custom session directory (default: ~/.claude/projects/)",
    )
    discover_parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    discover_parser.add_argument(
        "--include-worktrees",
        action="store_true",
        help="Include worktree sessions (excluded by default)",
    )
    discover_parser.add_argument(
        "--max-calls",
        type=int,
        default=1000,
        help="Maximum LLM calls (default: 1000)",
    )
    discover_parser.add_argument(
        "--max-tokens",
        type=int,
        help="Maximum total tokens budget",
    )

    # evolve
    evolve_parser = subparsers.add_parser("evolve", help="Evolve a skill via experiment loop")
    evolve_parser.add_argument("--skill", required=True, help="Skill name to evolve")
    evolve_parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum experiment iterations (default: 10)",
    )
    evolve_parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")

    # status
    subparsers.add_parser("status", help="Show last run summary")

    # install
    install_parser = subparsers.add_parser("install", help="Install Claude Code slash commands")
    install_parser.add_argument(
        "--global",
        dest="global_install",
        action="store_true",
        help="Install to ~/.claude/commands/ (all projects)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "discover":
        from afterburn.discover import run_discover

        run_discover(args)
    elif args.command == "evolve":
        from afterburn.evolve import run_evolve

        run_evolve(args)
    elif args.command == "status":
        from afterburn.discover import show_status

        show_status()
    elif args.command == "install":
        from afterburn.install import run_install

        run_install(args)


if __name__ == "__main__":
    main()
