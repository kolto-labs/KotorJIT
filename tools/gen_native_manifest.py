#!/usr/bin/env python3
"""Emit data/signatures/native_manifest.json for kp.native discovery and testing."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKSITES = ROOT / "data" / "hooksites.toml"
UNIFIED = ROOT / "data" / "signatures" / "unified_kotor.json"
ADDR_DIR = ROOT / "data" / "addresses"
OUT = ROOT / "data" / "signatures" / "native_manifest.json"


def main() -> int:
    hooksites = tomllib.loads(HOOKSITES.read_text(encoding="utf-8"))
    unified = json.loads(UNIFIED.read_text(encoding="utf-8"))

    # Collect per-build address tables to summarize resolution status per function.
    builds: dict[str, dict] = {}
    for p in sorted(ADDR_DIR.glob("*.json")):
        builds[p.stem] = json.loads(p.read_text(encoding="utf-8"))

    entries = []
    sites_raw = hooksites.get("site", [])
    if isinstance(sites_raw, dict):
        site_items = sorted(sites_raw.items())
    else:
        site_items = sorted((s.get("name", ""), s) for s in sites_raw)
    for name, spec in site_items:
        kind = spec.get("kind", "unknown")
        if kind == "field":
            continue
        cls = spec.get("class", "")
        method = spec.get("method", "")
        convention = spec.get("convention", "thiscall" if cls else "cdecl")

        per_game_locators = {}
        for game in ("k1", "k2"):
            g_site = unified.get("games", {}).get(game, {}).get(name, {})
            if g_site.get("locators"):
                per_game_locators[game] = g_site["locators"]

        resolved_builds = []
        for bname, bdata in builds.items():
            s = bdata.get("sites", {}).get(name)
            if s and s.get("resolved") and s.get("addr"):
                resolved_builds.append(bname)

        entries.append({
            "name": name,
            "kind": kind,
            "class": cls,
            "method": method,
            "convention": convention,
            "required": bool(spec.get("required", False)),
            "resolved_builds": resolved_builds,
            "locators": per_game_locators,
        })

    manifest = {
        "format": "kotorjit.native-manifest/v1",
        "site_count": len(entries),
        "entries": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(entries)} callable/code sites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
