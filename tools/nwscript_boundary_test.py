#!/usr/bin/env python3
"""Reject known access paths through the removed ``kotor`` table.

This is a bounded lexical receipt, not a Lua parser. It scans raw source so
embedded Lua in C++, shell, Python, and TOML strings stays visible. It
rejects both lowercase native helpers and direct routine paths through the
removed root. Native facilities belong below ``kp``:

* dotted members on ``kotor``, parenthesized ``kotor``, or
  ``_G["kotor"]`` / ``_G.kotor``;
* bracket lookup on those receivers, including ``kotor[name]`` helpers;
* single-target local/non-local aliases wherever they occur, plus direct
  receivers in comma-separated assignment lines; and
* ``rawget`` on those receivers.

Whitespace and newlines are accepted inside receivers and member access. This
intentionally does not claim data-flow tracking for arbitrarily computed
aliases, every possible multi-assignment layout, or a complete Lua grammar.

Historical research is excluded because it records the API that existed when
the evidence was gathered.  Active source, scripts, tests, metadata, and user
documentation remain in scope.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {".cpp", ".hpp", ".lua", ".py", ".sh", ".toml", ".md"}
EXCLUDED_DIRS = {
    "adjudication",  # Historical binary research, including non-Lua database names.
    "harness-research",
    "ideation",
    "plans",
    "archive",
}
ACTIVE_ROOTS = ("src", "scripts", "tools", "data", "docs")

KOTOR_BASE = r"(?:\bkotor\b|\b_G\s*(?:\.\s*kotor\b|\[\s*['\"]kotor['\"]\s*\]))"
KOTOR_RECEIVER = rf"(?:{KOTOR_BASE}|(?:\(\s*)+{KOTOR_BASE}(?:\s*\))+)"
IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"

FORBIDDEN = (
    (
        "dotted member on removed host root",
        re.compile(rf"{KOTOR_RECEIVER}\s*\.\s*[A-Za-z_][A-Za-z0-9_]*"),
    ),
    (
        "bracket lookup on kotor table",
        re.compile(rf"{KOTOR_RECEIVER}\s*\["),
    ),
    (
        "direct whole-kotor-table alias",
        re.compile(
            rf"(?<![A-Za-z0-9_.])(?:local\s+)?{IDENTIFIER}"
            rf"\s*=(?!=)\s*{KOTOR_RECEIVER}(?!\s*[.\[])",
        ),
    ),
    (
        "direct whole-kotor-table receiver in comma assignment",
        re.compile(
            rf"(?:^|[;\n])\s*(?:local\s+)?{IDENTIFIER}"
            rf"(?:\s*,\s*{IDENTIFIER})+\s*=(?!=)"
            rf"(?:\s*|[^;\n]*?,\s*){KOTOR_RECEIVER}(?!\s*[.\[])",
            re.MULTILINE,
        ),
    ),
    (
        "dynamic rawget on kotor table",
        re.compile(rf"\brawget\s*\(\s*{KOTOR_RECEIVER}\s*,"),
    ),
)


def active_files() -> list[Path]:
    candidates = [ROOT / "README.md"]
    for root_name in ACTIVE_ROOTS:
        candidates.extend((ROOT / root_name).rglob("*"))

    files: list[Path] = []
    for path in candidates:
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if path == Path(__file__).resolve():
            continue
        if path == ROOT / "docs/nwscript-lua-harness-boundary-plan.md":
            continue  # The accepted plan records the pre-migration collision.
        if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return sorted(files)


def violations(text: str) -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for label, pattern in FORBIDDEN:
        for match in pattern.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            excerpt = " ".join(match.group(0).split())
            found.append((label, line_number, excerpt))
    return sorted(found, key=lambda item: (item[1], item[0], item[2]))


def self_test() -> int:
    forbidden_examples = {
        "dotted": "return kotor.GetFirstPC()",
        "native lowercase": "kotor.log('forbidden')",
        "native memory": "local mem = kotor.mem",
        "parenthesized dotted": "return (( kotor )).GetFirstPC()",
        "multiline dotted": "return kotor\n  .\n  GetFirstPC()",
        "bracket literal": "return kotor['GetFirstPC']()",
        "bracket dynamic helper": "local fn = kotor[name]",
        "global dotted": "return _G['kotor'].GetFirstPC()",
        "global bracket": 'return _G.kotor["GetFirstPC"]()',
        "whole-table dynamic helper": "local api = kotor",
        "non-local table alias": "api = (_G['kotor'])",
        "multiline rawget helper": "local fn = rawget(\n (kotor),\n name)",
        "inline conditional alias": "if ready then api = kotor end",
        "multi-assignment alias": "local keep, api = true, kotor",
        "spaced nested parentheses": "return ( ( kotor ) ).GetFirstPC()",
        "rawget with spaced nested parentheses": "return rawget(( ( kotor ) ), name)",
    }
    allowed_examples = {
        "native helper": "kp.registertimer(100, 'tick')",
        "native namespace alias": "local mem = kp.mem",
        "explicit routine bridge": "return nwscript.call('GetFirstPC')",
    }
    failures: list[str] = []
    for name, text in forbidden_examples.items():
        if not violations(text):
            failures.append(f"missed forbidden {name}: {text!r}")
    for name, text in allowed_examples.items():
        matches = violations(text)
        if matches:
            failures.append(f"rejected allowed {name} as {matches}: {text!r}")
    if failures:
        print("NWScript boundary pattern self-test failures:")
        print("\n".join(failures))
        return 1
    print(
        "NWScript boundary pattern self-test: "
        f"{len(forbidden_examples)} forbidden and {len(allowed_examples)} allowed forms passed"
    )
    return 0


def main() -> int:
    failures: list[str] = []
    checked = 0
    for path in active_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        checked += 1
        for label, line_number, excerpt in violations(text):
            failures.append(
                f"{path.relative_to(ROOT)}:{line_number}: {label}: {excerpt}"
            )

    if failures:
        print("NWScript boundary violations:")
        print("\n".join(failures))
        return 1

    print(
        f"NWScript bounded lexical receipt: checked {checked} active files; "
        "0 covered dotted, bracket, rawget, single-target alias, or "
        "comma-assignment receiver paths on kotor/_G-kotor receivers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test() if "--self-test" in sys.argv else main())
