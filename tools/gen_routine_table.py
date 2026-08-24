#!/usr/bin/env python3
"""Generate the NWScript engine-routine table that Lua calls through.

The game dispatches all engine routines through one runtime array of function
pointers indexed by routine id. To expose "everything NWScript can do" to Lua we
need, for every id: its name, its return type, and its parameter types -- so the
generic bridge knows what to push onto the VM stack and what to pop back.

Source of truth is `nwscript.nss`, the header BioWare and Obsidian shipped. It
declares every routine in id order, each preceded by a `// <id>: description`
comment. That is the authoritative list, it ships with the games, and it needs no
third-party project to interpret.

The recovered `ScriptFunctions` enum from the binaries is used as a cross-check,
not as the source. Where the two disagree we report it rather than pick a winner
silently.

Usage:
    ./gen_routine_table.py --game k1
    ./gen_routine_table.py --all --check-enum
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import kpdiscover  # noqa: E402

OUTDIR = ROOT / "data" / "routines"


def _nss(game: str) -> Path | None:
    """The game's own nwscript.nss.

    Preferred from a copy vendored into this repo, so a checkout regenerates
    without anything else present. Otherwise found wherever it lives on this
    machine, including inside an installed game.
    """
    vendored = ROOT / "data" / "nwscript" / game / "nwscript.nss"
    if vendored.is_file():
        return vendored
    hit = kpdiscover.find_data_file(
        f"bioware_projects/odynsscomp/docs/corpus/nwscript/{game}/nwscript.nss",
        f"odynsscomp/docs/corpus/nwscript/{game}/nwscript.nss",
        env=f"KP_NWSCRIPT_{game.upper()}")
    if hit:
        return hit
    for root in kpdiscover.find_all_games(game):
        for rel in ("nwscript.nss", "Override/nwscript.nss", "override/nwscript.nss"):
            p = root / rel
            if p.is_file():
                return p
    return None

# nwscript's type vocabulary. `action` is a routine returning nothing that also
# queues an action; for marshalling it behaves as void.
TYPES = {
    "void": "void", "int": "int", "float": "float", "string": "string",
    "object": "object", "vector": "vector", "location": "location",
    "effect": "effect", "event": "event", "talent": "talent",
    "itemproperty": "itemproperty", "action": "void", "struct": "struct",
}

# The four engine structures KOTOR's VM knows, by their VM type id. NWN has a
# fifth (itemproperty); KOTOR does not, which matters when marshalling.
ENGINE_STRUCTS = {"effect": 0, "event": 1, "location": 2, "talent": 3}

GAMES = {
    "k1": {"binary_id": 8,  "expect": 772},
    "k2": {"binary_id": 22, "expect": 877},
}

# `// 123: text` or `// 123. text`.
#
# The negative lookahead is load-bearing in both directions. Descriptions contain
# lines like `// 0.0f and 360.0f`, where "0." would otherwise parse as routine id
# 0 and steal the id from the declaration below it, cascading into every later
# routine. But the separator is not always followed by a space either -- id 470
# in the K1 header is `// 470:decrease the blaster deflection rate` -- so
# requiring whitespace drops a real routine. Rejecting only a following digit
# satisfies both.
ID_COMMENT = re.compile(r"^//\s*(\d+)\s*[.:](?!\d)")
# A declaration: `<type> Name(args);` possibly spanning lines.
DECL = re.compile(
    r"^\s*(void|int|float|string|object|vector|location|effect|event|talent"
    r"|itemproperty|action|struct\s+\w+)\s+([A-Za-z_]\w*)\s*\((.*)$"
)


@dataclass
class Param:
    type: str
    name: str
    default: str | None


@dataclass
class Routine:
    id: int
    name: str
    returns: str
    params: list


def split_args(text: str) -> list[str]:
    """Split a parameter list on commas that are not inside brackets."""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([": depth += 1
        elif ch in ")]": depth -= 1
        if ch == "," and depth == 0:
            out.append(cur); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [a.strip() for a in out if a.strip()]


def parse_param(text: str) -> Param | None:
    default = None
    if "=" in text:
        text, default = text.split("=", 1)
        text, default = text.strip(), default.strip()
    parts = text.split()
    if len(parts) < 2:
        return None
    # `struct Foo bar` -> type "struct Foo"
    if parts[0] == "struct" and len(parts) >= 3:
        return Param("struct", parts[2], default)
    return Param(parts[0], parts[1], default)


def parse_nss(path: Path) -> tuple[list[Routine], list[str]]:
    text = path.read_text(encoding="latin-1")
    lines = text.splitlines()
    routines: list[Routine] = []
    problems: list[str] = []

    pending_id: int | None = None
    for i, line in enumerate(lines):
        m = ID_COMMENT.match(line)
        if m:
            pending_id = int(m.group(1))
            continue
        d = DECL.match(line)
        if not d:
            continue
        ret_raw, name, rest = d.group(1), d.group(2), d.group(3)

        # A declaration may wrap; accumulate until the closing paren.
        j = i
        while ")" not in rest and j + 1 < len(lines):
            j += 1
            rest += " " + lines[j].strip()
        if ")" not in rest:
            problems.append(f"{name}: unterminated parameter list")
            continue
        args_text = rest[: rest.rindex(")")]
        tail = rest[rest.rindex(")") :]
        # A definition (has a body) is not an engine routine declaration.
        if "{" in tail:
            continue
        if ";" not in tail:
            continue

        if pending_id is None:
            problems.append(f"{name}: declaration with no preceding id comment")
            continue

        ret = "struct" if ret_raw.startswith("struct") else ret_raw
        params = []
        for a in split_args(args_text):
            p = parse_param(a)
            if p is None:
                problems.append(f"{name}: unparsable parameter {a!r}")
            else:
                params.append(p)
        routines.append(Routine(pending_id, name, TYPES.get(ret, ret), params))
        pending_id = None

    return routines, problems


def enum_names(binary_id: int) -> dict[int, str]:
    """The ScriptFunctions enum recovered from the binary, as a cross-check.

    Optional. Without the corpus the header alone still produces a complete K1
    table; only K2, whose header leaves 71 routines unnumbered, depends on it.
    """
    corpus = kpdiscover.find_corpus()
    if corpus is None:
        return {}
    db = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    row = db.execute(
        "SELECT definition FROM ghidra_type WHERE binary_id=? AND name='ScriptFunctions'",
        (binary_id,)).fetchone()
    db.close()
    if not row:
        return {}
    out = {}
    for m in re.finditer(r"#define\s+(\w+)\s+\(\(ScriptFunctions\)\((\d+)\)\)", row[0]):
        out[int(m.group(2))] = m.group(1)
    return out


def coverage(id_map: dict[int, str]) -> tuple[int, list[int]]:
    """(highest id, missing ids below it). A complete table has no gaps."""
    if not id_map:
        return -1, []
    top = max(id_map)
    return top, [i for i in range(top + 1) if i not in id_map]


def build(game: str, _check_enum: bool) -> int:
    """Join two sources, each used for what it is actually good for.

    Neither source is complete for both games:

      * The K1 header numbers all 772 routines; its recovered ScriptFunctions
        enum holds only 657 entries with 115 gaps, so enum indices drift and
        cannot be trusted for ids.
      * The K2 header leaves ~110 declarations unnumbered; its enum holds all
        877 ids with no gaps at all.

    So the id -> name map comes from whichever source is gap-free, and the
    signature always comes from the header, matched by name. Picking per game
    rather than globally is the whole point.
    """
    spec = GAMES[game]
    nss = _nss(game)
    if nss is None:
        raise SystemExit(
            f"nwscript.nss for {game} not found.\n"
            f"Vendor it at data/nwscript/{game}/nwscript.nss, set "
            f"KP_NWSCRIPT_{game.upper()}, or install the game.")
    routines, problems = parse_nss(nss)

    sig_by_name = {r.name: r for r in routines}
    nss_ids: dict[int, str] = {}
    dupes = []
    for r in routines:
        if r.id in nss_ids and nss_ids[r.id] != r.name:
            dupes.append({"id": r.id, "first": nss_ids[r.id], "second": r.name})
        nss_ids[r.id] = r.name
    enum_ids = enum_names(spec["binary_id"])

    nss_top, nss_gaps = coverage(nss_ids)
    enum_top, enum_gaps = coverage(enum_ids)

    if not nss_gaps and len(nss_ids) == spec["expect"]:
        id_map, chosen = nss_ids, "nwscript.nss"
    elif not enum_gaps and len(enum_ids) == spec["expect"]:
        id_map, chosen = enum_ids, "ScriptFunctions enum (recovered from binary)"
    else:
        id_map, chosen = (nss_ids, "nwscript.nss (incomplete)") if len(nss_ids) >= len(enum_ids) \
            else (enum_ids, "ScriptFunctions enum (incomplete)")

    entries, no_signature, disagree = [], [], []
    for rid in sorted(id_map):
        name = id_map[rid]
        sig = sig_by_name.get(name)
        if sig is None:
            no_signature.append({"id": rid, "name": name})
            entries.append({"id": rid, "name": name, "returns": None, "params": None})
            continue
        entries.append({"id": rid, "name": name, "returns": sig.returns,
                        "params": [asdict(p) for p in sig.params]})
        other = enum_ids if id_map is nss_ids else nss_ids
        if rid in other and other[rid] != name:
            disagree.append({"id": rid, "chosen": name, "other": other[rid]})

    top, gaps = coverage(id_map)
    report = {
        "game": game,
        "id_source": chosen,
        "signature_source": str(nss),
        "count": len(id_map),
        "expected": spec["expect"],
        "max_id": top,
        "gaps": gaps,
        "engine_structs": ENGINE_STRUCTS,
        "source_coverage": {
            "nss": {"entries": len(nss_ids), "max_id": nss_top, "gaps": len(nss_gaps)},
            "enum": {"entries": len(enum_ids), "max_id": enum_top, "gaps": len(enum_gaps)},
        },
        "duplicate_ids": dupes,
        "names_without_signature": no_signature,
        "source_disagreements": disagree,
        "parse_problems": problems,
        "routines": entries,
    }

    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / f"{game}.json").write_text(json.dumps(report, indent=2) + "\n")

    ok = len(id_map) == spec["expect"] and not gaps
    sigs = sum(1 for e in entries if e["returns"] is not None)
    print(f"{game}: {len(id_map)}/{spec['expect']} ids (max {top}, {len(gaps)} gaps) "
          f"from {chosen}; {sigs} with signatures  {'ok' if ok else 'INCOMPLETE'}")
    if no_signature:
        print(f"  no signature for {len(no_signature)}: "
              f"{', '.join(x['name'] for x in no_signature[:4])}")
    if disagree:
        print(f"  sources disagree on {len(disagree)} ids "
              f"(first id {disagree[0]['id']}: {disagree[0]['chosen']} vs {disagree[0]['other']})")
    if dupes:
        print(f"  duplicate ids: {dupes[:3]}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", choices=sorted(GAMES))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check-enum", action="store_true",
                    help="cross-check against the ScriptFunctions enum from the binary")
    args = ap.parse_args()
    games = sorted(GAMES) if args.all else ([args.game] if args.game else [])
    if not games:
        ap.error("pass --game k1|k2 or --all")
    return max(build(g, args.check_enum) for g in games)


if __name__ == "__main__":
    sys.exit(main())
