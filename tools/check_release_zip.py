#!/usr/bin/env python3
"""Offline check: a release zip has required members and no forbidden payloads."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REQUIRED_SUFFIXES = (
    "/scriptforge.dll",
    "/binkw32.dll",
    "/install_to_game.sh",
    "/data/addresses/k1_gog_103.json",
    "/data/addresses/k2_gog_aspyr.json",
    "/README.md",
    "/docs/user/install.md",
    "/CONTRIBUTING.md",
)

ALLOWED_EXE_SUFFIXES = (
    "/scriptforge-launch.exe",
    "/bin/scriptforge-launch.exe",
)

FORBIDDEN_SUBSTRINGS = (
    "corpus.sqlite",
    "scriptforge.log",
    "scriptforge-proxy.log",
    "/.git/",
    "agentdecompile",
)


def members(zf: zipfile.ZipFile) -> list[str]:
    return [n.replace("\\", "/") for n in zf.namelist()]


def check(path: Path) -> list[str]:
    errs: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = members(zf)
        if not names:
            return ["zip is empty"]
        roots = {n.split("/", 1)[0] for n in names if n}
        if len(roots) != 1:
            errs.append(f"expected one top-level directory, got {sorted(roots)}")
        root = next(iter(roots)) if roots else ""
        for suf in REQUIRED_SUFFIXES:
            want = root + suf
            if want not in names and not any(n.endswith(suf.lstrip("/")) or n.endswith(suf) for n in names):
                # Accept either rooted or exact suffix match under the single root.
                if not any(n == want or n.endswith(suf) for n in names):
                    errs.append(f"missing required member ending with {suf}")
        for n in names:
            low = n.lower()
            for bad in FORBIDDEN_SUBSTRINGS:
                if bad in low:
                    errs.append(f"forbidden member: {n}")
            # Game PE payloads must never ship; our proxy binkw32.dll and launcher are allowed by name.
            exe_allowed = any(low.endswith(s) for s in ALLOWED_EXE_SUFFIXES)
            if (low.endswith(".exe") and not exe_allowed) or low.endswith(".app/") or "/swkotor" in low:
                errs.append(f"forbidden game path: {n}")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zip", type=Path)
    args = ap.parse_args(argv)
    if not args.zip.is_file():
        print(f"missing zip: {args.zip}", file=sys.stderr)
        return 2
    errs = check(args.zip)
    if errs:
        for e in errs:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(f"OK: {args.zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
