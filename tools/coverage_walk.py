#!/usr/bin/env python3
"""Turn a coverage JSON report into an API-director itinerary.

Each dialog becomes: unlock start actives (best-effort), talk to a speaker,
then pick every reply index. The live harness feeds these as `cover …` lines.
No keystrokes except the digit fallback inside `cover pick` when the
conversation-manager cave is not installed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def itinerary(report: dict) -> list[str]:
    lines = ["cover haste 4", "cover fade0"]
    # Plot-flag suspects from the scan, not script resrefs (those are NCS names).
    for row in report.get("conditional_only_strings") or []:
        s = row.get("string") or ""
        if s and s[0] != "_" and "false" not in s.lower():
            lines.append(f"cover setb {s} 1")
    for d in report.get("dialogs") or []:
        resref = d.get("resref") or ""
        speakers = d.get("speakers") or []
        tag = speakers[0] if speakers else ""
        if tag:
            lines.append(f"cover talk {tag} {resref}")
        else:
            lines.append(f"# no speaker tag in {resref}")
        n = max(int(d.get("replies") or 0), 1)
        for i in range(1, min(n, 9) + 1):
            lines.append(f"cover pick {i}")
        lines.append("cover convo")
    lines.append("cover haste 1")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", nargs="?", default="")
    ap.add_argument("-m", "--module", default="end_m01aa")
    ap.add_argument("-o", "--out", default="")
    args = ap.parse_args()
    path = Path(args.report) if args.report else Path(f"tmp/coverage/{args.module}.json")
    report = json.loads(path.read_text())
    lines = itinerary(report)
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
