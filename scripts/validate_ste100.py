#!/usr/bin/env python3
"""ASD-STE100 Simplified Technical English Checker for Agent Communication.

Checks text/markdown files against core ASD-STE100 rules:
1. Sentence length (max 20 words for instructions, 25 for descriptions).
2. Prohibited ambiguous modal verbs (should, may, might, could, would).
3. Unapproved complex vocabulary with suggested replacements.
4. Passive voice indicators.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Prohibited modal verbs in STE-100
PROHIBITED_MODALS = {
    "should": "must (for obligation) or can (for ability)",
    "may": "can (for capability) or specify condition explicitly",
    "might": "can (for capability) or specify condition explicitly",
    "could": "can (for capability)",
    "would": "will (for future action)",
}

# Common unapproved words in technical documentation and STE-100 replacements
UNAPPROVED_WORDS = {
    "perform": "make or do",
    "execute": "run, make, or do",
    "terminate": "stop or end",
    "initiate": "start",
    "commence": "start",
    "modify": "change",
    "utilize": "use",
    "demonstrate": "show",
    "retain": "keep",
    "alter": "change",
    "abort": "stop",
    "facilitate": "help or make easy",
    "subsequently": "then or after",
    "prior to": "before",
    "in order to": "to",
}

PASSIVE_VOICE_PATTERNS = [
    re.compile(r"\b(is|are|was|were|be|been|being)\s+([a-z]+ed)\s+by\b", re.IGNORECASE),
    re.compile(r"\b(must|can)\s+be\s+([a-z]+ed)\b", re.IGNORECASE),
]


def clean_markdown_line(line: str) -> str:
    """Strip markdown formatting elements and inline code spans."""
    line = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", line)  # links
    line = re.sub(r"`[^`]+`", " ", line)  # inline code spans
    line = re.sub(r"[*_{}[\]()#+\-.!]", " ", line)  # markdown syntax
    return line.strip()


def check_file(path: Path) -> tuple[int, list[str]]:
    """Check a file for ASD-STE100 compliance.

    Returns:
        (violation_count, list_of_error_messages)
    """
    if not path.is_file():
        return 1, [f"File not found: {path}"]

    lines = path.read_text(encoding="utf-8").splitlines()
    violations: list[str] = []

    in_code_block = False
    in_frontmatter = False

    for line_idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Handle frontmatter
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue

        # Handle code blocks
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Skip headers, empty lines, and table rows
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("|")
            or stripped.startswith("<!--")
        ):
            continue

        clean_text = clean_markdown_line(line)
        if not clean_text:
            continue

        # Split into sentences (by period, exclamation, question mark)
        sentences = [s.strip() for s in re.split(r"[.!?]+", clean_text) if s.strip()]

        for sent in sentences:
            words = sent.split()
            word_count = len(words)

            # Rule: Sentence length (max 25 words for descriptions)
            if word_count > 25:
                violations.append(
                    f"Line {line_idx}: Sentence exceeds 25 words "
                    f'({word_count} words): "{sent[:50]}..."'
                )

            # Rule: Prohibited modal verbs
            lower_words = [w.lower() for w in words]
            for modal, suggestion in PROHIBITED_MODALS.items():
                if modal in lower_words:
                    violations.append(
                        f"Line {line_idx}: Prohibited modal '{modal}'. Use '{suggestion}'."
                    )

            # Rule: Unapproved vocabulary
            for unapproved, replacement in UNAPPROVED_WORDS.items():
                pattern = rf"\b{re.escape(unapproved)}\b"
                if re.search(pattern, sent, re.IGNORECASE):
                    violations.append(
                        f"Line {line_idx}: Unapproved word '{unapproved}'. "
                        f"Recommended: '{replacement}'."
                    )

            # Rule: Passive voice
            for p_pat in PASSIVE_VOICE_PATTERNS:
                match = p_pat.search(sent)
                if match:
                    violations.append(
                        f"Line {line_idx}: Possible passive voice detected "
                        f"('{match.group(0)}'). Use active voice."
                    )

    return len(violations), violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ASD-STE100 compliance for agent files.")
    parser.add_argument("paths", nargs="+", type=Path, help="Files to check")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 on any violation")
    args = parser.parse_args()

    total_violations = 0

    for path in args.paths:
        count, errors = check_file(path)
        total_violations += count
        if errors:
            print(f"\n[{path}] - {count} STE-100 warnings/violations:")
            for err in errors:
                print(f"  * {err}")
        else:
            print(f"[{path}] - ASD-STE100 Compliant (0 issues)")

    if total_violations > 0 and args.strict:
        print(f"\nTotal violations: {total_violations}. Exiting with error.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
