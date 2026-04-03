"""Install Claude Code slash commands."""

import shutil
from pathlib import Path


COMMANDS_DIR = Path(__file__).parent.parent / ".claude" / "commands"


def run_install(args) -> None:
    """Install slash commands to project or global directory."""
    if args.global_install:
        target = Path.home() / ".claude" / "commands"
    else:
        target = Path.cwd() / ".claude" / "commands"

    target.mkdir(parents=True, exist_ok=True)

    if not COMMANDS_DIR.exists():
        print(f"Error: command templates not found at {COMMANDS_DIR}")
        return

    installed = 0
    for cmd_file in COMMANDS_DIR.glob("*.md"):
        dest = target / cmd_file.name
        shutil.copy2(cmd_file, dest)
        print(f"  Installed: {dest}")
        installed += 1

    scope = "globally" if args.global_install else f"to {target}"
    print(f"\n{installed} commands installed {scope}")
