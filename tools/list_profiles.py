#!/usr/bin/env python3
"""Print KotorPhasor build profiles from data/profiles/builds.toml."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "data" / "profiles" / "builds.toml"


def load() -> list[dict]:
    data = tomllib.loads(PROFILES.read_text(encoding="utf-8"))
    return list(data.get("profile", []))


def main() -> int:
    rows = load()
    if not rows:
        print("no profiles", file=sys.stderr)
        return 1
    required = {"k1_gog_103", "k2_gog_aspyr", "k1_mac", "k2_mac"}
    have = {r["id"] for r in rows}
    missing = required - have
    if missing:
        print(f"missing required profiles: {sorted(missing)}", file=sys.stderr)
        return 1
    width = max(len(r["id"]) for r in rows)
    for r in rows:
        print(f"{r['id']:<{width}}  {r['game']:<3}  {r['platform']:<6}  "
              f"{r['format']:<6}  {r['status']:<12}  {r.get('note', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
