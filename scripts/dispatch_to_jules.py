#!/usr/bin/env python3
"""Dispatch implementation tickets to Google Jules via GitHub Issues.

This script automates cloud delegation for Google Jules:
1. Parses ticket metadata (ID, title, archetype, dependencies).
2. Validates the ticket against ASD-STE100 rules using validate_ste100.py.
3. Checks that declared ticket dependencies are satisfied.
4. Invokes GitHub CLI (gh) to create an issue with label 'jules',
   triggering the Jules GitHub App in Google Cloud at zero additional cost.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def parse_ticket_header(ticket_path: Path) -> tuple[str, str, list[str]]:
    """Extract ticket title, archetype, and dependencies from markdown header.

    Returns:
        (title, archetype, list_of_dependencies)
    """
    lines = ticket_path.read_text(encoding="utf-8").splitlines()
    title = ""
    archetype = "Builder"
    dependencies: list[str] = []

    for line in lines[:25]:
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
        elif "Archetype:" in line:
            # e.g. **Archetype:** Builder · **Depends on:** T1.4
            arch_match = re.search(r"Archetype:\*{0,2}\s*(\w+)", line)
            if arch_match:
                archetype = arch_match.group(1).lower()

            dep_match = re.search(r"Depends on:\*{0,2}\s*([^·\n]+)", line)
            if dep_match:
                raw_deps = dep_match.group(1).strip()
                dependencies = [d.strip() for d in re.split(r"[, ]+", raw_deps) if d.strip()]

    if not title:
        title = ticket_path.stem

    return title, archetype, dependencies


def validate_ste100(ticket_path: Path) -> bool:
    """Run ASD-STE100 validator against the ticket."""
    validator_path = Path(__file__).parent / "validate_ste100.py"
    if not validator_path.is_file():
        print(f"Warning: Validator script not found at {validator_path}")
        return True

    cmd = [sys.executable, str(validator_path), str(ticket_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ASD-STE100 Validation failed:\n{result.stdout}")
        return False

    print(f"ASD-STE100 Check: PASSED ({ticket_path.name} obeys language rules)")
    return True


def check_gh_authenticated() -> bool:
    """Check if GitHub CLI (gh) is installed and logged in."""
    gh_bin = shutil.which("gh")
    if not gh_bin:
        return False

    result = subprocess.run([gh_bin, "auth", "status"], capture_output=True, text=True)
    return result.returncode == 0


def dispatch_ticket(
    ticket_path: Path,
    dry_run: bool = False,
    skip_validation: bool = False,
) -> int:
    """Dispatch the ticket to Google Jules via GitHub CLI."""
    if not ticket_path.is_file():
        print(f"Error: Ticket file not found: {ticket_path}")
        return 1

    title, archetype, dependencies = parse_ticket_header(ticket_path)
    print("\n--- Dispatching to Google Jules ---")
    print(f"Ticket:       {title}")
    print(f"Archetype:    {archetype}")
    print(f"Dependencies: {', '.join(dependencies) if dependencies else 'None'}")

    # Step 1: Validate ASD-STE100 language rules
    if not skip_validation and not validate_ste100(ticket_path):
        print("Aborting: Ticket does not meet ASD-STE100 standard.")
        return 1

    # Step 2: Prepare GitHub Issue payload
    labels = ["jules", archetype]
    issue_title = f"[TICKET] {title}"

    gh_cmd = [
        "gh",
        "issue",
        "create",
        "--title",
        issue_title,
        "--label",
        ",".join(labels),
        "--body-file",
        str(ticket_path),
    ]

    cmd_str = " ".join(gh_cmd)

    if dry_run:
        print("\n[DRY RUN] GitHub CLI command that will be executed:")
        print(f"  {cmd_str}")
        print("\nTicket is ready for Jules. Run without --dry-run to dispatch.")
        return 0

    # Step 3: Check gh auth
    if not check_gh_authenticated():
        print("\nGitHub CLI (gh) is not authenticated or not installed.")
        print("To authenticate and trigger Jules automatically, run:")
        print("  gh auth login")
        print("\nAlternatively, run the command manually once logged in:")
        print(f"  {cmd_str}")
        return 1

    # Step 4: Execute gh issue create
    print(f"\nExecuting: {cmd_str}")
    result = subprocess.run(gh_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        issue_url = result.stdout.strip()
        print(f"\nIssue successfully created: {issue_url}")
        print("Google Jules GitHub App will automatically wake up and start in cloud VM!")
        return 0
    else:
        print(f"\nError creating GitHub issue:\n{result.stderr}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dispatch implementation tickets to Google Jules via GitHub Issues."
    )
    parser.add_argument("ticket_path", type=Path, help="Path to ticket markdown file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show dispatch command without creating the issue",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip ASD-STE100 language check",
    )
    args = parser.parse_args()

    return dispatch_ticket(
        ticket_path=args.ticket_path,
        dry_run=args.dry_run,
        skip_validation=args.skip_validation,
    )


if __name__ == "__main__":
    sys.exit(main())
