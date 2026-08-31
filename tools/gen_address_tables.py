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
sys.path.insert(0, str(ROOT / "tools"))
import kpdiscover  # noqa: E402

MANIFEST = ROOT / "data" / "hooksites.toml"
OUTDIR = ROOT / "data" / "addresses"

# Builds we emit tables for. `alias` is the stable id used by the runtime;
# `sha256` is how the runtime recognises the build at load time.
#
# NOTE k1_steam: the corpus has no Steam entry - its .text is DRM ciphertext, so
# nobody analysed it. But we proved the unpacked Steam .text is byte-identical to
# GOG (828/828 pages), so GOG addresses are correct for it once deciphered. That
# is why it borrows GOG's symbol source. See docs/steam-gog-equivalence.md.
def _game_file(game: str, *names: str, env: str | None = None):
    """A file inside an installed game, found by locating the install first."""
    import os
    if env and os.environ.get(env) and Path(os.environ[env]).exists():
        return Path(os.environ[env])
    for root in kpdiscover.find_all_games(game):
        for cand in (root, root.parent):
            for n in names:
                p = cand / n
                if p.is_file():
                    return p
    return None


def _ref(*rel: str, env: str | None = None):
    """A plaintext reference image, wherever it happens to live on this machine.

    Returns None when it is absent, which is not fatal: the sentinel and the
    known-good digest for that build simply cannot be derived, and the generator
    says so instead of writing a wrong one.
    """
    return kpdiscover.find_data_file(*rel, env=env)

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
        "reference_image": _ref("biodecompwarehouse/agentdecompile/target/swkotor-unpack/swkotor.exe.unpacked.exe",
                                "agentdecompile/target/swkotor-unpack/swkotor.exe.unpacked.exe",
                                env="KP_K1_UNPACKED"),
        "code_sections": [".text", ".textU"],
        "note": "Steam build. .text is ciphertext on disk; identical to GOG once deciphered.",
    },
    "k1_steam_103_unpacked": {
        "symbol_source": "K1__k1_win_gog_swkotor.exe",
        "sha256": "2719ed2cb678e2c1ff5b2a787f9804d8e5f8dd52a02c2279080f031636e03a05",
        "game": "K1", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "reference_image": _ref("biodecompwarehouse/agentdecompile/target/swkotor-unpack/swkotor.exe.unpacked.exe",
                                "agentdecompile/target/swkotor-unpack/swkotor.exe.unpacked.exe",
                                env="KP_K1_UNPACKED"),
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
        "reference_image": _ref("biodecompwarehouse/agentdecompile/target/swkotor-gog/swkotor.exe.gog",
                                "agentdecompile/target/swkotor-gog/swkotor.exe.gog",
                                env="KP_K1_GOG_EXE"),
        "code_sections": [".text"],
    },
    "k2_steam_linux": {
        "symbol_source": "TSL__k2_linux_swkotor2.elf",
        "sha256": "ed043d21a4578fd1c6f1557f0f72bde5589ba3572a5b6f1a687ed9feeab49ac3",
        "md5": "b3420a36a4385fec8189f37c5d5eaad1",
        "game": "K2", "platform": "linux", "format": "elf", "image_base": 0x8048000,
        "encrypted": False,
        # The TSL Linux build is its own reference: it ships unencrypted.
        "reference_image": _game_file("k2", "kotor2", env="KP_K2_ELF"),
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
        "reference_image": _ref(
            "biodecompwarehouse/agentdecompile/vendor/MizuchiRE/binaries/"
            "k2_win_gog_aspyr_swkotor2.exe/k2_win_gog_aspyr_swkotor2.exe",
            env="KP_K2_GOG_ASPYR_EXE"),
        "code_sections": [".text"],
        "note": "Native Aspyr PE. Sites resolved from the func table's own "
                "namespace-qualified symbols (name_origin='namespace'), not "
                "hand-adjudicated: this build was never stripped.",
    },
    "k1_amazongames": {
        "symbol_source": "K1__k1_win_amazongames_swkotor.exe",
        "md5": "a2620900440a958019a401a5ad2351cf",
        "game": "K1", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "reference_image": _ref(
            "biodecompwarehouse/agentdecompile/vendor/MizuchiRE/binaries/"
            "k1_win_amazongames_swkotor.exe/k1_win_amazongames_swkotor.exe",
            env="KP_K1_AMAZONGAMES_EXE"),
        "code_sections": [".text"],
        "note": "Registered for build identification only. Only 47% of this "
                "binary's functions carry a native symbol (corpus func_count "
                "30101, named_count 14211) -- far short of k2_gog_aspyr's 95% "
                "-- so almost every site needs the identity/adjudication layer "
                "this build has none of yet, same as k2_steam_linux's original "
                "55-binding pass. Checked: the run v1 match from the "
                "k1_gog_103 donor has ZERO candidates at all for vm.run_script "
                "on this binary, unlike k2_steam_aspyr where the same "
                "technique found real evidence -- this build needs its own "
                "from-scratch RE pass, not a donor-matching shortcut. Not "
                "installable until that work is done.",
    },
    "k2_win_cd_10": {
        "symbol_source": "TSL__k2_win_CD_1.0_swkotor2.exe",
        "md5": "4a318b515e0e35ba7f289b7764ac1aad",
        "game": "K2", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "reference_image": _ref(
            "biodecompwarehouse/agentdecompile/vendor/MizuchiRE/binaries/"
            "k2_win_CD_1.0_swkotor2.exe/k2_win_CD_1.0_swkotor2.exe",
            env="KP_K2_CD10_EXE"),
        "code_sections": [".text"],
        "note": "Pre-Aspyr retail CD release, before the 1.0b patch. Registered "
                "for build identification only -- 61% named (func_count 22502, "
                "named_count 13740), so this needs the identity/adjudication "
                "layer, same as k2_steam_linux's original pass. Checked: the "
                "run v1 match from the k2_gog_aspyr donor has ZERO candidates "
                "for vm.run_script on this binary -- this build's own 15 "
                "natively-named functions are all Windows DLL import-table "
                "entries (GetTickCount, DirectInput8Create, ...), none of them "
                "engine classes, so there is no local ground truth to "
                "calibrate a matcher against here at all. Not installable "
                "until that work is done.",
    },
    "k2_win_cd_10b": {
        "symbol_source": "TSL__k2_win_CD_1.0b_swkotor2.exe",
        "md5": "e0fdc77e3f248d621f24d538df687d92",
        "game": "K2", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "reference_image": _ref(
            "biodecompwarehouse/agentdecompile/vendor/MizuchiRE/binaries/"
            "k2_win_CD_1.0b_swkotor2.exe/k2_win_CD_1.0b_swkotor2.exe",
            env="KP_K2_CD10B_EXE"),
        "code_sections": [".text"],
        "note": "Pre-Aspyr retail CD release, the 1.0b patch. Same func/named "
                "counts as 1.0 in the corpus -- a small patch, not a rebuild. "
                "Registered for build identification only; not installable "
                "until it has the same identity/adjudication work 1.0 needs.",
    },
    "k2_steam_aspyr": {
        "symbol_source": "TSL__k2_win_steam_aspyr_swkotor2.exe",
        "md5": "2f2d31e21acc6b3d9c5f28c79a28a202",
        "game": "K2", "platform": "win", "format": "pe", "image_base": 0x400000,
        "encrypted": False,
        "reference_image": _ref(
            "biodecompwarehouse/agentdecompile/vendor/MizuchiRE/binaries/"
            "k2_win_steam_aspyr_swkotor2.exe/k2_win_steam_aspyr_swkotor2.exe",
            env="KP_K2_STEAM_ASPYR_EXE"),
        "code_sections": [".text"],
        "note": "7 of 12 required VM/stack sites hand-adjudicated against the "
                "gog_aspyr donor (see data/adjudication/k2_steam_aspyr_vm_"
                "bindings.json): vm.run_script, vm.execute_command, "
                "app.server_main_loop, console.do_console, "
                "vm.stack_push_float, vm.stack_pop_string, "
                "vm.stack_push_string. Still not installable: the other 5 "
                "required stack accessors (int/float-pop/object) are a "
                "genuine degenerate cluster of 12 near-identical thunks that "
                "run v1 cannot discriminate and this pass could not "
                "disambiguate by instruction pattern in the time available.",
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


def elf_exec_segments(path: Path):
    """Executable PT_LOAD segments, as (vaddr, filesz, offset).

    A running process cannot always reach the section headers -- in this ELF
    e_shoff sits past the last PT_LOAD -- so the runtime identifies code by the
    r-x segment instead. Both digests are recorded so either view verifies.
    """
    import struct
    d = path.read_bytes()
    if d[:4] != b"\x7fELF":
        return []
    phoff, = struct.unpack_from("<I", d, 0x1C)
    phentsize, phnum = struct.unpack_from("<HH", d, 0x2A)
    out = []
    for i in range(phnum):
        o = phoff + i * phentsize
        p_type, p_offset, p_vaddr, _pa, p_filesz, _mem, p_flags, _al = \
            struct.unpack_from("<IIIIIIII", d, o)
        if p_type == 1 and (p_flags & 0x1):        # PT_LOAD, executable
            out.append((p_vaddr, p_filesz, p_offset))
    return out


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

    # A plaintext build is its own reference, so the file we just hashed is the
    # file the runtime will meet. An encrypted build's reference is its
    # deciphered twin, which has a different hash -- using it would make the
    # runtime fail to recognise the build it actually loads.
    if not spec.get("encrypted") and "sha256" not in spec:
        out["derived_sha256"] = out["reference_sha256"]

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

    if spec.get("format") == "elf":
        for n, (vaddr, filesz, off) in enumerate(elf_exec_segments(ref)):
            out.setdefault("known_text", []).append({
                "section": f"seg{n}",
                "sha256": hashlib.sha256(d[off:off + filesz]).hexdigest(),
                "note": "runtime view: what a live process sees when section "
                        "headers are not mapped",
            })
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
        "format_kind": spec["format"],
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


def emit_builds_inc(tables: dict[str, dict]) -> str:
    """The C++ build table, generated from the same JSON the runtime reads.

    Without this the image module keeps its own copy of every sentinel and
    digest, which is a second source of truth for facts that already have one --
    they agree until the day they quietly do not.
    """
    fmt = {"pe": "Format::Pe32", "elf": "Format::Elf32"}
    out = ["// Generated by tools/gen_address_tables.py. Do not edit; regenerate.",
           "// clang-format off"]

    for alias, t in tables.items():
        known = t.get("known_text") or []
        if not known:
            continue
        out.append(f"static const KnownText kText_{alias}[] = {{")
        for k in known:
            out.append(f'    {{"{k["section"]}", "{k["sha256"]}"}},')
        out.append("};")
    out.append("")

    out.append("static const BuildRecord kBuilds[] = {")
    for alias, t in tables.items():
        ident = t.get("identity") or {}
        sha = ident.get("sha256") or t.get("derived_sha256")
        known = t.get("known_text") or []
        if not sha or not known:
            # Without a file hash we cannot recognise the build, and without a
            # digest we could not verify it if we did. Emitting a half record
            # would be a build we accept and cannot check.
            continue
        sent = t.get("sentinel")
        if sent and t.get("encrypted"):
            sva = f'0x{sent["va"]:08X}'
            sbytes, sdesc = sent["bytes"], sent["describes"]
        else:
            # Nothing to wait for on a plaintext build.
            sva, sbytes, sdesc = "0", "", ""
        note = (t.get("note") or "").replace('"', '\"')
        out.append("    {")
        out.append(f'        "{alias}",')
        out.append(f'        "{sha}",')
        out.append(f'        {fmt[t["format"]]}, 0x{t["image_base"]:08X}, '
                   f'{"true" if t.get("encrypted") else "false"},')
        out.append(f'        {sva}, "{sbytes}", "{sdesc}",')
        out.append(f'        kText_{alias}, sizeof kText_{alias} / sizeof kText_{alias}[0],')
        out.append(f'        "{note}",')
        out.append("    },")
    out.append("};")
    out.append("// clang-format on")
    return "\n".join(out) + "\n"


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

    corpus = kpdiscover.find_corpus()
    if corpus is None:
        raise SystemExit(
            "reverse-engineering corpus not found.\n"
            "Set KOTORXID_DB, or add [paths] corpus = \"...\" to kotorphasor.toml.\n"
            "It is only needed to REGENERATE these tables; a checkout with\n"
            "data/addresses/ committed builds and runs without it.")

    sites = load_sites()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)

    rc = 0
    emitted: dict[str, dict] = {}
    for alias in targets:
        table = emit(db, alias, BUILDS[alias], sites)
        emitted[alias] = table
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

    # Only rewrite the C++ table when every build was regenerated; a partial run
    # would silently drop the builds it did not touch.
    if set(targets) == set(BUILDS):
        gen = ROOT / "src" / "generated"
        gen.mkdir(parents=True, exist_ok=True)
        (gen / "builds.inc").write_text(emit_builds_inc(emitted))
        usable = sum(1 for t in emitted.values()
                     if ((t.get("identity") or {}).get("sha256") or t.get("derived_sha256"))
                     and t.get("known_text"))
        print(f"builds.inc: {usable} recognisable build(s) "
              f"of {len(emitted)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
