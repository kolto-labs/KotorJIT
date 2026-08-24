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
UNPACK = Path("/home/brunner56/biodecompwarehouse/agentdecompile/target")

# `reference_image` is a PLAINTEXT copy of the build's code. It is what the
# sentinel bytes and the known-good code digest are read from, so neither has to
# be written down by hand. For an encrypted build that is the deciphered twin;
# for a plaintext build it is the build itself.
#
# `sentinel_site` names the logical hook site whose first bytes act as the
# "has the wrapper finished deciphering?" gate. It is a logical name, so the VA
# is resolved from the corpus like every other address rather than hardcoded.
BUILDS = {
    "k1_steam_103": {
        "symbol_source": "K1__k1_win_gog_swkotor.exe",
        "sha256": "34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88",
        "game": "K1", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": True,
        "reference_image": UNPACK / "swkotor-unpack" / "swkotor.exe.unpacked.exe",
        "code_sections": [".text", ".textU"],
        "note": "Steam build. .text is ciphertext on disk; identical to GOG once deciphered.",
    },
    "k1_steam_103_unpacked": {
        "symbol_source": "K1__k1_win_gog_swkotor.exe",
        "sha256": "2719ed2cb678e2c1ff5b2a787f9804d8e5f8dd52a02c2279080f031636e03a05",
        "game": "K1", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "reference_image": UNPACK / "swkotor-unpack" / "swkotor.exe.unpacked.exe",
        "code_sections": [".textU", ".text"],
        "note": ("The deciphered Steam image. The headless harness runs this, because "
                 "the shipped executable will not start without Steam, so the runtime "
                 "meets it and must recognise it."),
    },
    "k1_gog_103": {
        "symbol_source": "K1__k1_win_gog_swkotor.exe",
        "md5": "9a44891011437deb6536d992bccdfe4b",
        "game": "K1", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "reference_image": UNPACK / "swkotor-gog" / "swkotor.exe.gog",
        "code_sections": [".text"],
    },
    "k2_steam_linux": {
        "symbol_source": "TSL__k2_linux_swkotor2.elf",
        "sha256": "ed043d21a4578fd1c6f1557f0f72bde5589ba3572a5b6f1a687ed9feeab49ac3",
        "md5": "b3420a36a4385fec8189f37c5d5eaad1",
        "game": "K2", "platform": "linux", "format": "elf", "image_base": 0x8048000,
        "encrypted": False,
        "reference_image": Path("/run/media/brunner56/MyBook/SteamLibrary/steamapps"
                                "/common/Knights of the Old Republic II/kotor2"),
        "code_sections": [".text"],
        # DoConsole is a KOTOR 1 symbol. TSL reaches its console through a
        # different function that has not been adjudicated, so the site is
        # optional here: the runtime loses the in-game `lua` command on this
        # build and keeps everything else, rather than refusing to install.
        "optional_sites": ["console.do_console"],
        "note": "Native Aspyr ELF, EXEC (not PIE). VM entry points hand-adjudicated.",
    },
    "k2_gog_aspyr": {
        "symbol_source": "TSL__k2_win_gog_aspyr_swkotor2.exe",
        "md5": "1ffa92993d8015c9bb93ceac96c508c0",
        "game": "K2", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "note": "Binary not on this machine; table emitted to prove the generator generalises.",
    },
}


# Bytes read at the sentinel site. Ten is enough to be unique here: the K1 gate
# is `mov edx,[esp+4]; cmp edx,0x304`, and the 0x304 bounds check against the
# 772-entry routine table is a shape that appears nowhere else in the image.
SENTINEL_LEN = 10
SENTINEL_SITE = "vm.execute_command"

# Bytes recorded per site so the hook engine can verify what it is about to
# patch. Sixteen covers any prologue a 5-byte detour will displace, with room to
# spare: verification is only as wide as the pattern, and a short one leaves the
# relocated bytes unchecked.
EXPECT_LEN = 16


def read_image(path: Path):
    """Return (bytes, image_base, [(name, vsize, vaddr, rawsize, rawoff)])."""
    import struct
    d = path.read_bytes()
    if d[:2] == b"MZ":
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        optsz = struct.unpack_from("<H", d, pe + 20)[0]
        base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
        so = pe + 24 + optsz
        secs = []
        for i in range(nsec):
            o = so + i * 40
            nm = d[o:o + 8].rstrip(b"\0").decode("latin-1")
            vs, va, rs, ro = struct.unpack_from("<IIII", d, o + 8)
            secs.append((nm, vs, base + va, rs, ro))
        return d, base, secs
    if d[:4] == b"\x7fELF":
        shoff, = struct.unpack_from("<I", d, 0x20)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", d, 0x2E)
        so = shoff + shstrndx * shentsize
        stroff = struct.unpack_from("<I", d, so + 0x10)[0]
        secs = []
        for i in range(shnum):
            o = shoff + i * shentsize
            nameoff, = struct.unpack_from("<I", d, o)
            addr, off, size = struct.unpack_from("<III", d, o + 0x0C)
            end = d.index(b"\0", stroff + nameoff)
            nm = d[stroff + nameoff:end].decode("latin-1")
            secs.append((nm, size, addr, size, off))
        base = min((s[2] for s in secs if s[2]), default=0)
        return d, base, secs
    raise SystemExit(f"unrecognised image format: {path}")


def va_to_offset(secs, va: int) -> int | None:
    for _nm, vs, vaddr, rs, ro in secs:
        if vaddr <= va < vaddr + max(vs, rs):
            return ro + (va - vaddr)
    return None


def image_facts(spec: dict, sentinel_va: int | None) -> dict:
    """Sentinel bytes and code-section digest, read from the plaintext reference.

    Deriving both from the reference image is what keeps invariant 2 intact:
    neither the gate bytes nor the expected digest is written down by hand, so
    there is nothing to drift from the binary it describes.
    """
    import hashlib
    ref = spec.get("reference_image")
    out: dict = {"reference_image": str(ref) if ref else None}
    if not ref or not Path(ref).exists():
        out["error"] = "reference image not available"
        return out

    ref = Path(ref)
    d, _base, secs = read_image(ref)
    out["reference_sha256"] = hashlib.sha256(d).hexdigest()

    if sentinel_va is not None:
        off = va_to_offset(secs, sentinel_va)
        if off is None:
            out["sentinel_error"] = f"VA {sentinel_va:#x} outside every section"
        else:
            out["sentinel"] = {
                "va": sentinel_va,
                "va_hex": f"0x{sentinel_va:08X}",
                "bytes": d[off:off + SENTINEL_LEN].hex(),
                "describes": SENTINEL_SITE,
            }

    out["_secs"] = secs
    out["_data"] = d

    # The digest covers the first VirtualSize bytes of the code section, which is
    # what the loader makes resident. Several names are accepted because an
    # unpacker renames what it rewrites: the artifact on disk carries .textU
    # where the running image carries .text.
    known = []
    for want in spec.get("code_sections", []):
        for nm, vs, _va, rs, ro in secs:
            if nm != want:
                continue
            body = d[ro:ro + min(rs, vs)]
            if len(body) < vs:
                body += b"\0" * (vs - len(body))
            known.append({"section": want,
                          "sha256": hashlib.sha256(body[:vs]).hexdigest()})
            break
    if known:
        # Every accepted name describes the same bytes, so one digest serves all.
        digest = known[0]["sha256"]
        out["known_text"] = [{"section": s, "sha256": digest}
                             for s in spec["code_sections"]]
    return out


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


def load_overlay(alias: str) -> dict[str, dict]:
    """Hand-adjudicated bindings for one build, keyed by "Class::method".

    This is resolution layer 0 -- it outranks the corpus. It exists because a
    stripped build can have no symbol at all where a human has nonetheless
    established the address from disassembly, and that evidence is stronger than
    anything the automatic matcher produces. Calibration on a build where the
    answer is knowable put the matcher at 8.9% correct in the margin-0.000 bucket,
    so nothing here rests on similarity score alone.
    """
    path = ROOT / "data" / "adjudication" / f"{alias.replace('k2_steam_linux', 'k2_linux')}_vm_bindings.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text())
    out = {}
    for b in doc.get("bindings", []):
        if b.get("verdict") != "accept":
            continue
        addr = b.get("elf_addr") or b.get("addr")
        if addr is None:
            continue
        out[b["name"]] = {
            "addr": int(str(addr), 16) if isinstance(addr, str) else int(addr),
            "confidence": b.get("confidence"),
            "evidence": b.get("evidence") or b.get("rationale"),
        }
    return out


def resolve(db: sqlite3.Connection, bid: int, site: dict,
            overlay: dict[str, dict] | None = None) -> Resolved:
    cls, method = site.get("class", "") or "", site["method"]
    name, kind, req = site["name"], site["kind"], site.get("required", False)

    # Layer 0: a hand-adjudicated binding, which outranks everything automatic.
    if overlay:
        hit = overlay.get(f"{cls}::{method}" if cls else method)
        if hit:
            return Resolved(name, cls, method, kind, req, hit["addr"], "adjudicated",
                            hit.get("confidence"), "hand-adjudicated", 1)

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
    overlay = load_overlay(alias)
    relaxed = set(spec.get("optional_sites", []))
    resolved = []
    for site in sites:
        if site["name"] in relaxed:
            site = {**site, "required": False}
        resolved.append(resolve(db, bid, site, overlay))

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
        "adjudicated_bindings": len(overlay),
        "sites": {},
    }
    sentinel_va = next((r.addr for r in resolved if r.name == SENTINEL_SITE), None)
    facts = image_facts(spec, sentinel_va)
    secs = facts.pop("_secs", None)
    data = facts.pop("_data", None)
    table.update(facts)

    # Expected bytes per site, read from the plaintext reference. The hook engine
    # refuses to patch when what it finds does not match, so a stale table or a
    # mismatched build fails loudly at the site rather than corrupting it.
    expect: dict[str, str] = {}
    if secs is not None and data is not None:
        for r in resolved:
            if r.addr is None:
                continue
            off = va_to_offset(secs, r.addr)
            if off is not None:
                expect[r.name] = data[off:off + EXPECT_LEN].hex()

    for r in resolved:
        d = asdict(r)
        d.pop("name")
        if d["addr"] is not None:
            d["addr_hex"] = f"0x{d['addr']:08X}"
        if r.name in expect:
            d["expected_bytes"] = expect[r.name]
        table["sites"][r.name] = d

    ok = [r for r in resolved if r.addr is not None]
    missing_required = [r for r in resolved if r.required and r.addr is None]
    table["summary"] = {
        "total": len(resolved),
        "resolved": len(ok),
        "by_func": sum(1 for r in ok if r.source == "func"),
        "by_identity": sum(1 for r in ok if r.source == "identity"),
        "by_adjudication": sum(1 for r in ok if r.source == "adjudicated"),
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
        print(f"{alias:22s} {s['resolved']:3d}/{s['total']:3d} resolved "
              f"(func {s['by_func']}, identity {s['by_identity']}, "
              f"adjudicated {s['by_adjudication']})  {flag}")
        if table.get("sentinel"):
            print(f"  sentinel         : {table['sentinel']['va_hex']} "
                  f"{table['sentinel']['bytes']}")
        elif table.get("sentinel_error") or table.get("error"):
            print(f"  sentinel         : unavailable "
                  f"({table.get('sentinel_error') or table.get('error')})")
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
