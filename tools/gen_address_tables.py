#!/usr/bin/env python3
"""Resolve KotorPhasor's logical hook sites to concrete addresses, per game build.

Addresses are data. Nothing in src/ ever hardcodes a VA; this script reads the
logical site manifest (data/hooksites.toml) and the reverse-engineering corpus,
and emits one JSON table per supported build to data/addresses/.

Two resolution layers, in precedence order:

  1. `func`     - a name recorded directly on that binary. Highest trust.
  2. `identity` - a cross-build binding via the logical_function layer, carrying
                  a confidence and the method that produced it.

Layer 2 is what makes builds nobody has hand-reversed usable. It is also where
bad bindings come from, so every layer-2 hit is emitted with its confidence and
margin so the runtime (and a human) can judge it.

Usage:
    ./gen_address_tables.py --list-builds
    ./gen_address_tables.py --build k1_win_gog_swkotor.exe
    ./gen_address_tables.py --all
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tomllib
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path("/home/brunner56/biodecompwarehouse/kotorxid/db/kotorxid.sqlite")
MANIFEST = ROOT / "data" / "hooksites.toml"
OUTDIR = ROOT / "data" / "addresses"

# Builds we emit tables for. `alias` is the stable id used by the runtime;
# `sha256` is how the runtime recognises the build at load time.
#
# NOTE k1_steam: the corpus has no Steam entry - its .text is DRM ciphertext, so
# nobody analysed it. But we proved the unpacked Steam .text is byte-identical to
# GOG (828/828 pages), so GOG addresses are correct for it once deciphered. That
# is why it borrows GOG's symbol source. See docs/steam-gog-equivalence.md.
BUILDS = {
    "k1_steam_103": {
        "symbol_source": "K1__k1_win_gog_swkotor.exe",
        "sha256": "34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88",
        "game": "K1", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": True,
        "note": "Steam build. .text is ciphertext on disk; identical to GOG once deciphered.",
    },
    "k1_gog_103": {
        "symbol_source": "K1__k1_win_gog_swkotor.exe",
        "md5": "9a44891011437deb6536d992bccdfe4b",
        "game": "K1", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
    },
    "k2_steam_linux": {
        "symbol_source": "TSL__k2_linux_swkotor2.elf",
        "sha256": "ed043d21a4578fd1c6f1557f0f72bde5589ba3572a5b6f1a687ed9feeab49ac3",
        "md5": "b3420a36a4385fec8189f37c5d5eaad1",
        "game": "K2", "platform": "linux", "format": "elf", "image_base": 0x8048000,
        "encrypted": False,
        "note": "Native Aspyr ELF, EXEC (not PIE). VM symbols pending adjudication.",
    },
    "k2_gog_aspyr": {
        "symbol_source": "TSL__k2_win_gog_aspyr_swkotor2.exe",
        "md5": "1ffa92993d8015c9bb93ceac96c508c0",
        "game": "K2", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "note": "Binary not on this machine; table emitted to prove the generator generalises.",
    },
}


@dataclass
class Resolved:
    name: str
    cls: str
    method: str
    kind: str
    required: bool
    addr: int | None
    source: str          # "func" | "identity" | "unresolved"
    confidence: float | None
    method_detail: str | None
    candidates: int      # how many addresses matched; >1 means ambiguous


def load_sites() -> list[dict]:
    with MANIFEST.open("rb") as fh:
        return tomllib.load(fh)["site"]


def binary_id(db: sqlite3.Connection, slug: str) -> int:
    row = db.execute("SELECT id FROM binary WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise SystemExit(f"no binary with slug {slug!r} in the corpus")
    return row[0]


def resolve(db: sqlite3.Connection, bid: int, site: dict) -> Resolved:
    cls, method = site.get("class", "") or "", site["method"]
    name, kind, req = site["name"], site["kind"], site.get("required", False)

    # Layer 1: a name recorded on this binary directly.
    #
    # Order by size DESC, not addr. Several VM entry points ship as a tiny stub
    # immediately followed by the real body (K2 GOG has a 9-byte
    # CVirtualMachineInternal::RunScript at 0x00645540 and the 731-byte one at
    # 0x00645549). Taking the lowest address would hook the stub.
    if cls:
        rows = db.execute(
            "SELECT addr, size FROM func WHERE binary_id=? AND namespace=? AND name=? "
            "AND source='USER_DEFINED' ORDER BY size DESC, addr",
            (bid, cls, method)).fetchall()
    else:
        rows = db.execute(
            "SELECT addr, size FROM func WHERE binary_id=? AND COALESCE(namespace,'')='' "
            "AND name=? AND source='USER_DEFINED' ORDER BY size DESC, addr",
            (bid, method)).fetchall()
    if rows:
        return Resolved(name, cls, method, kind, req,
                        rows[0][0], "func", 1.0, "user_defined", len(rows))

    # Layer 2: cross-build binding through logical_function.
    #
    # Only a fully-qualified Class::method match is trustworthy. On builds where
    # propagation recorded a bare method name, "EventHandler" matches every
    # object type's handler at once and there is no way to tell which is which -
    # picking the highest-confidence one would silently hook the wrong object
    # class. We refuse instead, and the runtime disables that site.
    if cls:
        rows = db.execute(
            "SELECT i.addr, i.confidence, i.method FROM logical_name ln "
            "JOIN identity i ON i.logical_id = ln.logical_id "
            "WHERE i.binary_id = ? AND ln.name = ? ORDER BY i.confidence DESC",
            (bid, f"{cls}::{method}")).fetchall()
        if not rows:
            bare = db.execute(
                "SELECT COUNT(*) FROM logical_name ln JOIN identity i "
                "ON i.logical_id = ln.logical_id WHERE i.binary_id=? AND ln.name=?",
                (bid, method)).fetchone()[0]
            if bare:
                return Resolved(name, cls, method, kind, req, None,
                                "ambiguous", None,
                                f"{bare} bare '{method}' bindings, class unknown", bare)
    else:
        rows = db.execute(
            "SELECT i.addr, i.confidence, i.method FROM logical_name ln "
            "JOIN identity i ON i.logical_id = ln.logical_id "
            "WHERE i.binary_id = ? AND ln.name = ? ORDER BY i.confidence DESC",
            (bid, method)).fetchall()

    if rows:
        addr, conf, meth = rows[0]
        return Resolved(name, cls, method, kind, req,
                        addr, "identity", conf, meth, len(rows))

    return Resolved(name, cls, method, kind, req, None, "unresolved", None, None, 0)


def emit(db: sqlite3.Connection, alias: str, spec: dict, sites: list[dict]) -> dict:
    bid = binary_id(db, spec["symbol_source"])
    resolved = [resolve(db, bid, s) for s in sites]

    table = {
        "build": alias,
        "game": spec["game"],
        "platform": spec["platform"],
        "format": spec["format"],
        "image_base": spec["image_base"],
        "encrypted": spec.get("encrypted", False),
        "symbol_source": spec["symbol_source"],
        "identity": {k: spec[k] for k in ("sha256", "md5") if k in spec},
        "note": spec.get("note"),
        "sites": {},
    }
    for r in resolved:
        d = asdict(r)
        d.pop("name")
        if d["addr"] is not None:
            d["addr_hex"] = f"0x{d['addr']:08X}"
        table["sites"][r.name] = d

    ok = [r for r in resolved if r.addr is not None]
    missing_required = [r for r in resolved if r.required and r.addr is None]
    table["summary"] = {
        "total": len(resolved),
        "resolved": len(ok),
        "by_func": sum(1 for r in ok if r.source == "func"),
        "by_identity": sum(1 for r in ok if r.source == "identity"),
        "refused_ambiguous": [r.name for r in resolved if r.source == "ambiguous"],
        "unresolved": [r.name for r in resolved if r.source == "unresolved"],
        # A resolved site with >1 candidate: we picked one on a stated rule
        # (largest body, or highest confidence). Worth a human look.
        "multi_candidate": [r.name for r in ok if r.candidates > 1],
        "low_confidence": [r.name for r in ok
                           if r.confidence is not None and r.confidence < 0.9],
        "missing_required": [r.name for r in missing_required],
        "installable": not missing_required,
    }
    return table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="append", help="build alias (repeatable)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list-builds", action="store_true")
    args = ap.parse_args()

    if args.list_builds:
        for k, v in BUILDS.items():
            print(f"{k:20s} {v['game']:3s} {v['platform']:6s} <- {v['symbol_source']}")
        return 0

    targets = list(BUILDS) if args.all else (args.build or [])
    if not targets:
        ap.error("pass --all, --build ALIAS, or --list-builds")
    unknown = [t for t in targets if t not in BUILDS]
    if unknown:
        ap.error(f"unknown build(s): {', '.join(unknown)}")

    if not CORPUS.exists():
        raise SystemExit(f"corpus not found: {CORPUS}")

    sites = load_sites()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(f"file:{CORPUS}?mode=ro", uri=True)

    rc = 0
    for alias in targets:
        table = emit(db, alias, BUILDS[alias], sites)
        out = OUTDIR / f"{alias}.json"
        out.write_text(json.dumps(table, indent=2) + "\n")
        s = table["summary"]
        flag = "ok" if s["installable"] else "NOT INSTALLABLE"
        print(f"{alias:20s} {s['resolved']:3d}/{s['total']:3d} resolved "
              f"(func {s['by_func']}, identity {s['by_identity']})  {flag}")
        if s["missing_required"]:
            print(f"  missing required : {', '.join(s['missing_required'])}")
            rc = 1
        for label in ("refused_ambiguous", "multi_candidate", "low_confidence"):
            if s[label]:
                print(f"  {label:17s}: {', '.join(s[label])}")
    db.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
