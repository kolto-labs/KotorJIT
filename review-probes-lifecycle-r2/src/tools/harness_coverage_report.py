#!/usr/bin/env python3
"""Report signature/absolute coverage for every address table."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    rows = []
    for path in sorted((ROOT / "data" / "addresses").glob("*.json")):
        doc = json.loads(path.read_text())
        sites = doc.get("sites", {})
        sig = sum(bool(v.get("expected_bytes")) for v in sites.values())
        absolute = sum(not bool(v.get("expected_bytes")) and bool(v.get("addr"))
                       for v in sites.values())
        unresolved = sum(not bool(v.get("addr")) for v in sites.values())
        rows.append((doc.get("build", path.stem), len(sites), sig, absolute, unresolved))
    print("build\tsites\tsignature\tabsolute_only\tunresolved")
    for row in rows:
        print("\t".join(map(str, row)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
