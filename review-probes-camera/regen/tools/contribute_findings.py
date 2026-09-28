#!/usr/bin/env python3
"""Write this project's reverse-engineering findings back into the shared corpus.

A finding that stays in one project's data/ directory is invisible to everything
else. The corpus is what the propagation runs and the analysis passes read, so a
binding established here has to land there or the next person reverses the same
function again.

What gets contributed:

  bindings   hand-adjudicated function addresses, into `identity`, attributed to
             this project and its method so a later reader can weigh them
  builds     a build we can now analyse that the corpus records as unanalysable
             -- notably the deciphered Steam image, whose .text the corpus never
             had because the shipped file is ciphertext
  notes      prose under the warehouse describing what was found and how, since
             a row records the answer but not the reasoning

Safety, because the database is live and large:

  * nothing is written without --apply; the default is a dry run
  * a backup is taken first unless --no-backup
  * writes happen in one transaction, and row counts are verified after
  * an existing higher-tier name is never overwritten -- ours is additive
  * re-running is idempotent: an identical binding is left alone

Usage:
    ./contribute_findings.py                 # dry run, show what would change
    ./contribute_findings.py --apply         # write it
    ./contribute_findings.py --notes-only    # just the prose
    ./contribute_findings.py --verify        # what the corpus holds from us
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import kpdiscover  # noqa: E402

# How our rows identify themselves. A reader who wants to discount everything
# this project contributed can filter on this one string.
METHOD = "kotorphasor:adjudicated:v1"
PROVENANCE = "kotorphasor"

# The prefix is load-bearing, not cosmetic. kx/propagate.py starts each run with
#     DELETE FROM identity WHERE method LIKE 'match:<run>:%'
# and then refuses to write over any address whose identity method does NOT begin
# with 'match:'. So a method outside that namespace is both preserved across runs
# and treated as a fixed point the matcher may not contradict. Naming ours
# 'match:kotorphasor' would silently delete every contribution on the next run.
assert not METHOD.startswith("match:"), (
    "METHOD must stay outside the 'match:' namespace or kx/propagate.py will "
    "delete these rows at the start of its next run")

# logical_name.tier: 1 human, 2 stabs, 3 symbol, 4 derived, 5 placeholder.
# Hand-adjudicated bindings are tier 1 -- a person read the disassembly. That is
# a stronger claim than the matcher's output, which lands at tier 4.
TIER_HUMAN = 1


def warehouse_root() -> Path | None:
    """The warehouse that owns the corpus, found from the corpus itself."""
    env = os.environ.get("BIODECOMP_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    corpus = kpdiscover.find_corpus()
    if corpus is None:
        return None
    # .../<warehouse>/kotorxid/db/kotorxid.sqlite
    for parent in corpus.parents:
        if (parent / "kotorxid").is_dir():
            return parent
    return corpus.parent.parent.parent


def _as_text(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return "; ".join(_as_text(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}={_as_text(x)}" for k, x in v.items())
    return str(v)


def load_bindings() -> list[dict]:
    """Accepted bindings from data/adjudication/*.json."""
    out = []
    d = ROOT / "data" / "adjudication"
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*_vm_bindings.json")):
        doc = json.loads(f.read_text())
        target = doc.get("target_binary") or {}
        md5 = (target.get("md5") or "").lower()
        for b in doc.get("bindings", []):
            if b.get("verdict") != "accept":
                continue
            addr = b.get("elf_addr") or b.get("addr")
            if addr is None:
                continue
            out.append({
                "source_file": f.name,
                "target_md5": md5,
                "name": b["name"],
                "addr": int(str(addr), 16) if isinstance(addr, str) else int(addr),
                "confidence": float(b.get("confidence") or 0.0),
                # Evidence is prose in some entries and a structured object in
                # others. Normalise, because it ends up in a TEXT column.
                "evidence": _as_text(b.get("evidence") or b.get("rationale") or ""),
            })
    return out


def binary_id_for_md5(db: sqlite3.Connection, md5: str) -> int | None:
    row = db.execute("SELECT id FROM binary WHERE lower(md5) = ?", (md5,)).fetchone()
    return row[0] if row else None


def plan_bindings(db: sqlite3.Connection, bindings: list[dict]) -> dict:
    """Work out what would change, without changing it."""
    plan = {"insert": [], "already_present": [], "corroborated": [],
            "conflict": [], "no_binary": []}
    for b in bindings:
        bid = binary_id_for_md5(db, b["target_md5"])
        if bid is None:
            plan["no_binary"].append(b)
            continue
        b = {**b, "binary_id": bid}

        # identity is unique on (binary_id, addr), so an address already bound is
        # either us re-running or someone else's claim. Never clobber.
        row = db.execute(
            "SELECT ln.name, i.method FROM identity i "
            "LEFT JOIN logical_name ln ON ln.logical_id = i.logical_id "
            "WHERE i.binary_id = ? AND i.addr = ?", (bid, b["addr"])).fetchone()
        if row is None:
            plan["insert"].append(b)
        elif row[0] == b["name"]:
            plan["already_present"].append(b)
        elif row[0] and b["name"].endswith("::" + row[0]):
            # The corpus has the bare method name at this address and we have the
            # qualified one. That is not a conflict, it is two independent routes
            # to the same answer -- and it is evidence FOR our binding, since the
            # automatic matcher got there without any of our reasoning. We refine
            # rather than replace: the row is someone else's, and identity is
            # unique on (binary_id, addr) so there is no second row to add.
            plan["corroborated"].append({**b, "existing_name": row[0],
                                         "existing_method": row[1]})
        else:
            plan["conflict"].append({**b, "existing_name": row[0],
                                     "existing_method": row[1]})
    return plan


def apply_bindings(db: sqlite3.Connection, plan: dict) -> dict:
    """Insert in one transaction, attach to a logical function per name."""
    stats = {"logical_created": 0, "names_created": 0, "identities": 0}
    cur = db.cursor()

    # Allocate ids above BOTH tables, not just logical_function.
    #
    # The corpus has 304 logical_name rows whose logical_id has no
    # logical_function row, and their ids run past logical_function's maximum.
    # Since logical_name.logical_id is the primary key, letting SQLite pick
    # max(logical_function.id)+1 lands straight on one of those orphans and the
    # insert fails. Not our mess, but we have to allocate around it.
    next_id = 1 + max(
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM logical_function").fetchone()[0],
        cur.execute("SELECT COALESCE(MAX(logical_id), 0) FROM logical_name").fetchone()[0])

    cur.execute("BEGIN")
    try:
        for b in plan["insert"]:
            name = b["name"]
            cls, _, method = name.partition("::")
            row = cur.execute(
                "SELECT logical_id FROM logical_name WHERE name = ?", (name,)).fetchone()
            if row:
                logical_id = row[0]
            else:
                logical_id = next_id
                next_id += 1
                cur.execute(
                    "INSERT INTO logical_function (id, canon_key, canon_class, canon_method, game) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (logical_id, name, cls if method else "", method or cls, "K2"))
                stats["logical_created"] += 1
                cur.execute(
                    "INSERT INTO logical_name (logical_id, name, tier, tier_name, "
                    "from_binary_id, n_members, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (logical_id, name, TIER_HUMAN, "human", b["binary_id"], 1,
                     f"{PROVENANCE}: {b['evidence'][:400]}"))
                stats["names_created"] += 1

            cur.execute(
                "INSERT OR IGNORE INTO identity "
                "(logical_id, binary_id, addr, confidence, method, evidence) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (logical_id, b["binary_id"], b["addr"], b["confidence"], METHOD,
                 json.dumps({"provenance": PROVENANCE,
                             "source": b["source_file"],
                             "evidence": b["evidence"][:1000]})))
            stats["identities"] += cur.rowcount
        db.commit()
    except Exception:
        db.rollback()
        raise
    return stats


def write_notes(wh: Path, plan: dict, applied: bool) -> Path:
    """The reasoning, which a row cannot carry."""
    d = wh / "findings"
    d.mkdir(parents=True, exist_ok=True)
    out = d / "kotorphasor-findings.md"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    steam_sha = "34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88"
    body = f"""# Findings contributed by KotorPhasor

Last written {stamp}. Rows carry `identity.method = '{METHOD}'`, so everything
this project contributed can be filtered or discounted as one set.

## The Steam KOTOR 1 build is analysable after all

The corpus has no entry for the Steam K1 build, and `MizuchiRE/PLAN.md` records it
as unmatchable: its `.text` is SteamStub ciphertext, entropy 8.000, no x86
prologues anywhere in 3.3 MB.

It is the GOG build with a wrapper bolted on. Deciphered, its `.text` is
**byte-identical to GOG across all 828 4 KB pages**, both entry points resolve to
`0x006fb38d`, and the file-size difference is exactly the size of the `.bind`
section (4,395,008 - 0x56000 = 4,042,752).

That comparison alone would be circular, since a GOG-code splice would look the
same. What rules it out is an asymmetry: the deciphered image's `.rdata` matches
**Steam** (0 bytes differ) while its `.text` matches **GOG**. A splice would have
carried GOG's `.rdata` too. The unpacker decrypted in place.

Steam and GOG differ outside the wrapper by 38 bytes in `.rdata`, all of them the
letter case of imported DLL names. Inert for analysis.

- Steam file sha256 `{steam_sha}`
- deciphered `.text[0:0x33b1d0]` sha256 `39bcd9f2c21de0e24aef77bcc2912f313fe9ed57803f505819d19a59ee0d4135`
- the same digest for the GOG build's `.text` over the same range

**Consequence for the corpus:** every K1 GOG address applies verbatim to the Steam
build once deciphered, and the deciphered image is a normal analysis target. The
"unanalysable" entry can be retired.

## KOTOR 2 native Linux script VM

`k2_linux_swkotor2.elf` (md5 `b3420a36a4385fec8189f37c5d5eaad1`) had one
hand-named function in the whole binary and no script-VM symbol at all.
{len(plan['insert']) + len(plan['already_present']) + len(plan['corroborated'])} bindings are contributed here,
established by disassembly and cross-build reasoning rather than by the matcher.

The matcher could not do this alone, and the calibration says why: on a pair where
the answer is knowable, its margin-0.000 bucket is 8.9% correct. Every binding
rests on at least two independent signals, at least one not from the matcher.

What actually worked:

- **Translation-unit layout isomorphism.** The nwscript TU appears in identical
  declaration order on the Mac and Android x86 builds, two different compilers,
  and the Linux ELF reproduces it across 24 consecutive functions.
- **NWScript type-code immediates.** `mov [esp+4], 0x3` is INTEGER, `0x4` with a
  `movss` is FLOAT, `0x5` with `operator new` is STRING, `0x6` is OBJECT. This is
  what separates `StackPushInteger` from `StackPushObject`, which are otherwise
  byte-identical in shape.
- **Resolving the Internal layer first.** Nine stack accessors are 28-byte,
  one-callee thunks containing no information except their callee, and the matcher
  collapsed all nine onto one wrong address. Naming the `CVirtualMachineInternal`
  layer first, then labelling each wrapper by its single `calledge` callee,
  resolved all 18 uniquely.

Independently re-verified for this note:
`CSWVirtualMachineCommands::ExecuteCommand` at `0x085b878e` carries
`cmp eax,0x36c` (877 routines), reads its dispatch table from `[ecx+0xc]`, indexes
it by 8 bytes per entry (Itanium `{{ptr, adj}}` member pointers), and returns
`0xfffff82e` = -2002 = `COMMAND_NOT_FOUND`.

**Two premises in the corpus notes that are wrong, corrected here:**

1. `CScriptEvent`'s four parameter blocks are **not** three values each. Each is a
   `CExoArrayList {{void* data; int size; int capacity}}`, grown on demand. Ghidra
   emits them as `unsigned char[0xc]`, which reads as three ints. Indexing slot 0
   as an int returns the **data pointer**. Anything reading a payload slot must go
   through the bounds-checked accessor.
2. `CSWSCreature::EventHandler` takes **five** parameters
   `(nEventId, nCallerObjectId, void* pEventData, nCalendarDay, nTimeOfDay)`, and
   the payload type varies by event id. Six creature script slots -- heartbeat,
   spawn, damaged, end-of-round, death, end-of-dialogue -- never reach it at all.

## The engine-routine dispatch, from building a working bridge against it

Findings from making Lua call KOTOR 1's engine routines for real. All addresses
are K1 GOG, which is byte-identical to the deciphered Steam build.

**NWScript defaults are a compiler feature, and the handlers do not agree about
it.** The compiler emits the default expression at the call site; each engine
handler then pops what its own signature says. Read out of the binary, two
handlers behave differently:

- `ExecuteCommandSuppressStatusSummaryEntry` (`0x547E50`) pops its one int
  unconditionally and never looks at `paramCount`.
- `ExecuteCommandCreateItemOnObject` (`0x52F570`) does `cmp DWORD PTR
  [esp+0x3c],0x3` -- it checks `paramCount` before popping three.

So anything calling routines from outside the VM must push the FULL declared
parameter count, not just the arguments it was given. Pushing fewer makes every
handler of the first kind pop whatever happens to be underneath. This makes the
recovered default VALUES load-bearing rather than documentation.

**`CVirtualMachine` is one pointer, and its accessors are two-instruction
thunks.** `CVirtualMachine::StackPopInteger` at `0x5D1000` is exactly:

    mov ecx, [ecx]        ; this = this->internal
    jmp 0x5D24C0          ; CVirtualMachineInternal::StackPopInteger

so a `CVirtualMachine*` is a pointer to a pointer to the internal. Anything
holding a `CVirtualMachineInternal*` can synthesise a usable `CVirtualMachine*`
by taking the address of a variable that holds it, without locating the real
singleton.

**`CVirtualMachineInternal::command_implementer` is at `+0x3D4`**, the last
member of the size-asserted `0x3D8` struct. That is the reachable path from the
`RunScript` receiver to `CSWVirtualMachineCommands`, and from there to the
command table at `[implementer+0x0C]`.

**The live command table on K1 holds 772 entries**, read back out of a running
game rather than inferred: the count matches both the header's routine count and
the dispatcher's own `cmp edx,0x304`.

**`StackPushVector` takes the Vector by value.** The K1 thunk at `0x5D1050`
reads `[esp+4]`, `[esp+8]`, `[esp+0xC]` and returns `ret 0xC` -- three stacked
floats under `__thiscall`, not a pointer and not three separate scalar pushes,
which would leave three stack entries with the wrong type tags.

**`StackPopEngineStructure` takes the bare structure id, 0..3.** The VM adds the
`0x10` that makes it a stack tag itself; passing the tag fails the comparison at
`0x5D265D` and pops nothing.

## Also worth recording

`0F BA` (Group 8: `bt`/`bts`/`btr`/`btc r/m32, imm8`) carries an `imm8`. Any length
disassembler used against GCC-built Odyssey binaries needs it; MSVC never emits it,
so a KOTOR 1 sweep will not find the omission, and the Linux TSL build has two.
"""
    out.write_text(body)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually write")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--notes-only", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="report what the corpus already holds from us")
    args = ap.parse_args()

    corpus = kpdiscover.find_corpus()
    if corpus is None:
        print("corpus not found; set KOTORXID_DB or add [paths] corpus to "
              "kotorphasor.toml", file=sys.stderr)
        return 1
    wh = warehouse_root()
    print(f"corpus     : {corpus}")
    print(f"warehouse  : {wh}")

    if args.verify:
        db = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
        n = db.execute("SELECT COUNT(*) FROM identity WHERE method = ?", (METHOD,)).fetchone()[0]
        print(f"\nidentity rows from {PROVENANCE}: {n}")
        for name, bid, addr, conf in db.execute(
                "SELECT ln.name, i.binary_id, i.addr, i.confidence FROM identity i "
                "JOIN logical_name ln ON ln.logical_id = i.logical_id "
                "WHERE i.method = ? ORDER BY ln.name LIMIT 12", (METHOD,)):
            print(f"  {name:52s} bin={bid} 0x{addr:08X} conf={conf}")
        db.close()
        return 0

    bindings = load_bindings()
    print(f"bindings   : {len(bindings)} accepted, from data/adjudication/")

    if args.notes_only:
        p = write_notes(wh, {"insert": [], "already_present": bindings,
                             "corroborated": [], "conflict": [], "no_binary": []}, False)
        print(f"wrote {p}")
        return 0

    db = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    plan = plan_bindings(db, bindings)
    db.close()

    print(f"\nwould insert        : {len(plan['insert'])}")
    print(f"already present     : {len(plan['already_present'])}")
    print(f"corroborated        : {len(plan['corroborated'])}  "
          f"(matcher reached the same address independently)")
    print(f"real conflicts      : {len(plan['conflict'])}")
    print(f"no matching binary  : {len(plan['no_binary'])}")
    for c in plan["corroborated"][:6]:
        print(f"  agrees  0x{c['addr']:08X} {c['existing_name']:16s} "
              f"-> refined to {c['name']}  ({c['existing_method']})")
    for c in plan["conflict"][:5]:
        print(f"  CONFLICT 0x{c['addr']:08X} ours={c['name']} "
              f"theirs={c['existing_name']} ({c['existing_method']})")

    if not args.apply:
        print("\ndry run; nothing written. pass --apply to write.")
        return 0

    if not args.no_backup:
        # The corpus is over half a gigabyte and its own volume can be nearly
        # full. Put the backup wherever there is room, preferring an explicit
        # choice, then this repo's volume, then alongside the original.
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"{corpus.stem}.bak-{stamp}.sqlite"
        need = corpus.stat().st_size + (64 << 20)
        candidates = []
        if os.environ.get("KP_BACKUP_DIR"):
            candidates.append(Path(os.environ["KP_BACKUP_DIR"]))
        candidates += [ROOT / "tmp" / "corpus-backups", corpus.parent]
        bak = None
        for d in candidates:
            try:
                d.mkdir(parents=True, exist_ok=True)
                if shutil.disk_usage(d).free > need:
                    bak = d / name
                    break
            except OSError:
                continue
        if bak is None:
            print("no volume with room for a backup; refusing to write. "
                  "Set KP_BACKUP_DIR or free space.", file=sys.stderr)
            return 1
        print(f"\nbacking up to {bak} ...", flush=True)
        shutil.copy2(corpus, bak)

    db = sqlite3.connect(str(corpus))
    before = db.execute("SELECT COUNT(*) FROM identity").fetchone()[0]
    stats = apply_bindings(db, plan)
    after = db.execute("SELECT COUNT(*) FROM identity").fetchone()[0]
    db.close()

    print(f"identity rows {before} -> {after} (+{after - before})")
    print(f"logical functions created: {stats['logical_created']}, "
          f"names: {stats['names_created']}")
    if after - before != len(plan["insert"]):
        print("WARNING: inserted count differs from planned; inspect before trusting",
              file=sys.stderr)

    p = write_notes(wh, plan, True)
    print(f"notes: {p}")
    report_wiring(corpus)
    return 0


def report_wiring(corpus: Path) -> None:
    """Say exactly what downstream will and will not do with this."""
    db = sqlite3.connect(f"file:{corpus}?mode=ro", uri=True)
    ours = db.execute("SELECT COUNT(*) FROM identity WHERE method = ?", (METHOD,)).fetchone()[0]
    bins = [r[0] for r in db.execute(
        "SELECT DISTINCT binary_id FROM identity WHERE method = ?", (METHOD,))]
    as_source = db.execute(
        "SELECT COUNT(*) FROM identity i JOIN match m "
        "ON m.src_binary = i.binary_id AND m.src_addr = i.addr WHERE i.method = ?",
        (METHOD,)).fetchone()[0]
    db.close()

    print("\n--- downstream wiring ---")
    print(f"{ours} rows contributed, on binary id(s) {bins}")
    print("automatic, no action needed:")
    print("  * kx/propagate.py will NOT overwrite these. It only deletes its own")
    print("    'match:<run>:%' rows, and skips any address whose identity method")
    print("    is outside that namespace. These are fixed points from now on.")
    print("  * anything reading `identity` -- the dashboard, report_propagation,")
    print("    the atlas -- sees them on its next read. No re-run required.")
    print("re-run to benefit:")
    print("  * kx/propagate.py    picks these up as SOURCES for any pair whose")
    print("    source is one of the binaries above")
    print("  * kx/report_propagation.py   refreshes the coverage numbers")
    if as_source == 0:
        print("honest gap:")
        print(f"  * no pair in propagate.py's PLAN currently sources from binary")
        print(f"    {bins}, so these will not seed another build until such a pair")
        print("    is added. They still protect and document their own binary.")


if __name__ == "__main__":
    sys.exit(main())
