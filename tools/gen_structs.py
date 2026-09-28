#!/usr/bin/env python3
"""Generate the engine struct layout table that typed field access reads.

Turns `data/research/phasor_structs.json` into `src/generated/structs_<game>.inc`
so a script says `creature.object.current_hp` instead of `readfloat(base+0xDC)`,
and a wrong offset stops the build instead of returning a wrong number.

WHY THIS IS A GENERATOR AND NOT A HAND-WRITTEN HEADER

There are 1690 fields across 25 layouts. Typed by hand, the first typo is silent
and permanent. Generated, the offsets are copied mechanically from the artifact
that was verified against the binary, and everything below can be re-asserted on
every regeneration.

WHAT IS CHECKED, AND WHY EACH CHECK EXISTS

The research notes are explicit that a size total alone proves nothing: two
compensating width errors cancel and leave every offset between them wrong. So
this tool re-derives the same evidence rather than trusting the file:

  1. Contiguity walk. Fields are packed sequentially from 0; a declared offset
     that disagrees with the running offset is fatal. This is what catches a
     wrong width, because a wrong width moves every later field.
  2. Name-offset assertions. Ghidra names unrecovered fields after their own hex
     offset, so `field_1a4` at offset 0x1a4 is a free assertion the file cannot
     fake. About a thousand of them.
  3. Size totals. The walk must end exactly at the declared struct size.
  4. The CExoArrayList census. The prose census in `access_notes` is parsed
     independently of the typed `fields` and the two must agree exactly, in both
     directions. This is the check the task asked for: verify the flag rather
     than trust it. A field the prose calls a list but the table calls a u32, or
     the reverse, is fatal.
  5. Twelve-byte accounting. The notes enumerate 34 twelve-byte blobs across the
     25 layouts and classify every one. 21 lists + 10 Vectors + 3 embedded
     CGameObjects must equal 34, and no opaque `u8[0xc]` may survive anywhere.
     An opaque 12-byte blob is the exact shape of the bug this file exists to
     prevent, so one appearing is fatal rather than a warning.

THE SPLIT-FORM LIST

Ghidra sometimes emits a CExoArrayList as three separate scalars instead of one
blob, so it does not look like a list at all. Where the research file annotates
that (`ptr` at N, size at N+4, capacity at N+8, with CExoArrayList named in the
meaning), the three fields are folded into one list field covering all 12 bytes.
The fold asserts it covers exactly those three and nothing else.

Shape-alike triples that carry no annotation are REPORTED, not folded. The notes
say that census is incomplete and that confirming one needs disassembly.
Promoting a guess is the same class of error as missing a real list, just
pointing the other way.

Usage:
    ./gen_structs.py --game k1
    ./gen_structs.py --game k1 --check      # verify only, write nothing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "data" / "research" / "phasor_structs.json"
OUTDIR = ROOT / "src" / "generated"

# Sizes for the named types the research file uses as field types but does not
# define a layout for. Each is a claim, and each is checked: a wrong size here
# breaks the contiguity walk of every struct that embeds one, which is why these
# are guesses that cannot survive being wrong.
#
#   Vector           3 floats, per the notes' flds base/base+4/base+8 test
#   CResRef          16-byte NUL-padded resource name
#   CScriptVarTable  the notes' name for the recurring 20-byte script-variable
#                    blob; there is no type by that name in the corpus
#   CExoLocString    {void*, i32 strref}, same 8 bytes as CExoString
EXTERNAL_SIZES = {
    "Vector": 12,
    "CResRef": 16,
    "CScriptVarTable": 20,
    "CExoLocString": 8,
}

SCALARS = {
    "u8": ("U8", 1), "i8": ("I8", 1),
    "u16": ("U16", 2), "i16": ("I16", 2),
    "u32": ("U32", 4), "i32": ("I32", 4),
    "u64": ("U64", 8),
    "f32": ("F32", 4),
    "ptr": ("Ptr", 4),
}

# Field types that are not scalars and not a named layout.
AGGREGATE_KIND = {
    "Vector": "Vector",
    "CExoString": "ExoString",
    "CExoLocString": "LocString",
    "CResRef": "ResRef",
    "CExoArrayList": "List",
    "CScriptVarTable": "Blob",
}

ARRAY = re.compile(r"^(.+?)\[(0x[0-9a-fA-F]+|\d+)\]$")
PLACEHOLDER = re.compile(r"^(?:field|_pad)_?([0-9a-fA-F]+)$")

CONFIDENCE = {"high": "High", "med": "Med", "low": "Low"}

# The kinds src/api/structs.cpp will attempt a store on: integer_range() plus
# F32. Every other kind is refused as an aggregate before confidence is
# consulted, so these are the only fields the confidence gate can decide.
# Duplicated from the runtime on purpose, and only to report on it -- nothing
# here changes what the runtime accepts.
WRITABLE_KINDS = {"U8", "I8", "U16", "I16", "U32", "I32", "U64", "F32", "Ptr"}

# Element types for a CExoArrayList, read out of the field's `meaning` prose.
#
# The type of a list's elements is not a column in the research file -- it is
# stated in English where it was recovered and absent where it was not. Parsing
# the prose keeps this a data change rather than a per-field table in this tool,
# and every list that matches nothing is reported instead of being guessed at.
#
# An unresolved element type is not fatal. The list still reads back as a list
# with a size, a capacity and an address; only element indexing is refused, with
# a message saying so. Guessing a stride would reintroduce the silent-wrong-value
# failure this whole module exists to remove.
ELEMENT_PATTERNS = [
    (re.compile(r"elements are \d+ \(0x([0-9a-fA-F]+)\) bytes each"), "blob-hex"),
    (re.compile(r"\bElements are (u8|i8|u16|i16|u32|i32|f32|u64)\b", re.I), "scalar"),
    (re.compile(r"\b(u8|i8|u16|i16|u32|i32|f32|u64)\s+(?:elements|object ids)\b"), "scalar"),
    (re.compile(r"\(to (CExoString) elements\)"), "named"),
    (re.compile(r"\bC[A-Za-z]\w*\*\s+list\b"), "pointer"),
    (re.compile(r"\*\(int\*\*\)"), "int-deref"),
]


class Fatal(Exception):
    pass


def size_of(type_text: str, layouts: dict[str, int]) -> int:
    """Bytes one field of this type occupies. Raises on a type we cannot size."""
    m = ARRAY.match(type_text)
    if m:
        return size_of(m.group(1), layouts) * int(m.group(2), 0)
    if type_text in SCALARS:
        return SCALARS[type_text][1]
    if type_text in EXTERNAL_SIZES:
        return EXTERNAL_SIZES[type_text]
    if type_text in layouts:
        return layouts[type_text]
    raise Fatal(f"no size known for type {type_text!r}")


def element_kind(meaning: str) -> tuple[str, str | None, int]:
    """(kind, layout name, stride) for a list's elements, or ('Unknown', None, 0)."""
    for rx, how in ELEMENT_PATTERNS:
        m = rx.search(meaning or "")
        if not m:
            continue
        if how == "blob-hex":
            return "Blob", None, int(m.group(1), 16)
        if how == "scalar":
            kind, width = SCALARS[m.group(1).lower()]
            return kind, None, width
        if how == "named":
            return "ExoString", None, 8
        if how == "pointer":
            return "Ptr", None, 4
        if how == "int-deref":
            return "I32", None, 4
    return "Unknown", None, 0


# --------------------------------------------------------------- verification

def parse_list_census(notes: str) -> set[tuple[str, str, int]]:
    """The CExoArrayList census, read out of the prose rather than the table.

    Independent of the `type` column, which is the point: the task is to verify
    the flag, not to trust it. Returns {(struct, field, offset)}.
    """
    try:
        body = notes.split("The ones that ARE CExoArrayList:")[1]
        body = body.split("The twelve-byte blobs that are NOT lists:")[0]
    except IndexError as exc:
        raise Fatal("access_notes no longer contains the CExoArrayList census; "
                    "the verification this generator depends on is gone") from exc

    out: set[tuple[str, str, int]] = set()
    for line in body.strip().splitlines():
        line = line.strip().lstrip("- ")
        if ":" not in line:
            continue
        struct, rest = line.split(":", 1)
        struct = struct.strip()
        rest = rest.split("<--")[0]
        for item in rest.split(","):
            m = re.match(r"^([\w.]+)\s+0x([0-9a-fA-F]+)$", item.strip())
            if m:
                out.add((struct, m.group(1), int(m.group(2), 16)))
    if not out:
        raise Fatal("parsed an empty CExoArrayList census out of access_notes")
    return out


def verify(doc: dict, layouts: dict[str, int]) -> list[str]:
    """Every check that must pass before a line is written. Raises Fatal."""
    problems: list[str] = []
    notes: list[str] = []
    structs = doc["structs"]

    # 1-3: the walk, the name-offset assertions, and the size totals.
    for s in structs:
        run = 0
        for f in s["fields"]:
            where = f"{s['name']}.{f['name']}"
            if f["offset"] != run:
                problems.append(
                    f"{where}: declared offset {f['offset']} (0x{f['offset']:x}) but the "
                    f"walk is at {run} (0x{run:x}); a field before it has the wrong width")
            run = f["offset"] + size_of(f["type"], layouts)
            m = PLACEHOLDER.match(f["name"])
            if m and int(m.group(1), 16) != f["offset"]:
                problems.append(
                    f"{where}: Ghidra named it for offset 0x{int(m.group(1), 16):x} "
                    f"but the table says 0x{f['offset']:x}")
        if run != s["size"]:
            problems.append(f"{s['name']}: walk ends at {run}, declared size {s['size']}")

    # 4: the census, both directions.
    census = parse_list_census(doc["access_notes"])
    declared = {(s["name"], f["name"], f["offset"])
                for s in structs for f in s["fields"] if f["type"] == "CExoArrayList"}
    for miss in sorted(census - declared):
        problems.append(f"{miss[0]}.{miss[1]} @0x{miss[2]:x}: the prose census calls this a "
                        f"CExoArrayList but the field table does not. Reading it as a scalar "
                        f"returns the DATA POINTER, not a value")
    for extra in sorted(declared - census):
        problems.append(f"{extra[0]}.{extra[1]} @0x{extra[2]:x}: typed as CExoArrayList but "
                        f"absent from the prose census; one of the two is wrong")
    notes.append(f"CExoArrayList census: {len(census)} in prose, {len(declared)} in the field "
                 f"table, agreeing in both directions")

    # 5: twelve-byte accounting, and no opaque blob of that width anywhere.
    tally = {"CExoArrayList": 0, "Vector": 0, "CGameObject": 0}
    for s in structs:
        for f in s["fields"]:
            if f["type"] in tally:
                tally[f["type"]] += 1
            if size_of(f["type"], layouts) == 12 and f["type"] not in tally:
                problems.append(
                    f"{s['name']}.{f['name']} @0x{f['offset']:x}: an unclassified 12-byte field "
                    f"of type {f['type']!r}. Twelve opaque bytes is the shape of a CExoArrayList; "
                    f"classify it before this generator will emit it")
    total = sum(tally.values())
    if total != 34:
        problems.append(f"twelve-byte accounting: {tally} sums to {total}, the notes enumerate 34")
    notes.append(f"twelve-byte fields: {tally['CExoArrayList']} lists + {tally['Vector']} Vectors "
                 f"+ {tally['CGameObject']} embedded CGameObject = {total}")

    if problems:
        raise Fatal("\n  ".join(["layout verification failed:"] + problems))
    return notes


# ------------------------------------------------------------------- folding

def fold_split_lists(struct: dict, layouts: dict[str, int]) -> tuple[list[dict], list[str], list[str]]:
    """Fold annotated three-scalar CExoArrayLists into one list field.

    Returns (fields, folded, candidates). `candidates` are triples with the right
    shape and no annotation; they are reported and left alone.
    """
    fields = struct["fields"]
    # The CExoArrayList layout itself is three scalars by definition, not a
    # struct that happens to contain a list.
    if struct["name"] == "CExoArrayList":
        return list(fields), [], []

    out: list[dict] = []
    folded: list[str] = []
    candidates: list[str] = []
    i = 0
    while i < len(fields):
        a = fields[i]
        trio = fields[i:i + 3]
        shaped = (len(trio) == 3
                  and a["type"] == "ptr"
                  and trio[1]["type"] in ("i32", "u32")
                  and trio[2]["type"] in ("i32", "u32")
                  and trio[1]["offset"] == a["offset"] + 4
                  and trio[2]["offset"] == a["offset"] + 8)
        if shaped:
            annotated = any("CExoArrayList" in (f.get("meaning") or "") for f in trio)
            if annotated:
                # The fold must cover exactly these three fields and nothing
                # else, or it would swallow a neighbour and shift the layout.
                span = sum(size_of(f["type"], layouts) for f in trio)
                if span != 12:
                    raise Fatal(f"{struct['name']}.{a['name']}: split-list fold would cover "
                                f"{span} bytes, not 12")
                merged = dict(a)
                merged["type"] = "CExoArrayList"
                merged["meaning"] = (a.get("meaning")
                                     or trio[1].get("meaning")
                                     or "split-form CExoArrayList")
                merged["_folded"] = [f["name"] for f in trio]
                out.append(merged)
                folded.append(f"{struct['name']}.{a['name']} @0x{a['offset']:x} "
                              f"({', '.join(f['name'] for f in trio)})")
                i += 3
                continue
            # Left as a plain pointer, but the suspicion travels with the field
            # rather than staying in a comment nobody reads. kp.struct.fields()
            # reports it, so an author who reads this field as a number is told
            # it may be a list head without this tool guessing that it is one.
            candidates.append(f"{struct['name']}.{a['name']} @0x{a['offset']:x}")
            a = dict(a)
            a["_list_shape_unconfirmed"] = True
        out.append(a)
        i += 1
    return out, folded, candidates


# -------------------------------------------------------------------- emitting

def c_string(text: str | None) -> str:
    if text is None:
        return "nullptr"
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", " ").replace("\t", " ")
    return f'"{escaped}"'


def classify(field: dict, layouts: dict[str, int]) -> dict:
    """One field, resolved into what the C++ table needs."""
    type_text = field["type"]
    size = size_of(type_text, layouts)
    kind = elem = "Unknown"
    struct_name = None
    elem_size = count = 0

    m = ARRAY.match(type_text)
    if m:
        base, n = m.group(1), int(m.group(2), 0)
        stride = size_of(base, layouts)
        if base == "u8":
            # A byte array is bytes. Handing it back as a sequence of one-byte
            # numbers is less useful than handing back the bytes.
            kind = "Blob"
        else:
            kind, count, elem_size = "Array", n, stride
            if base in SCALARS:
                elem = SCALARS[base][0]
            elif base in AGGREGATE_KIND:
                elem = AGGREGATE_KIND[base]
            elif base in layouts:
                elem, struct_name = "Struct", base
            else:
                raise Fatal(f"array of unhandled element type {base!r}")
    elif type_text in SCALARS:
        kind = SCALARS[type_text][0]
    elif type_text == "CExoArrayList":
        kind = "List"
        elem, struct_name, elem_size = element_kind(field.get("meaning") or "")
    elif type_text in AGGREGATE_KIND:
        kind = AGGREGATE_KIND[type_text]
    elif type_text in layouts:
        kind, struct_name = "Struct", type_text
    else:
        raise Fatal(f"unhandled field type {type_text!r}")

    shape_unconfirmed = bool(field.get("_list_shape_unconfirmed"))
    confidence = CONFIDENCE[field.get("confidence", "high")]

    # A pointer that may be a list head is not a pointer to write a number into.
    #
    # The research file marks confidence per field and never marks a plain scalar
    # below high, so before this demotion the runtime's confidence gate could not
    # fire on any field a write is even attempted on: every med and low field in
    # the corpus is an aggregate, and aggregates are refused by an earlier check.
    # The gate was unreachable, and opting in could not change the outcome of any
    # write.
    #
    # This is a derivation, not new data. The shape-alike census is something the
    # generator already computes out of the fields themselves, and what it says
    # about these pointers is exactly what "the corpus did not confirm this
    # offset" means: either the offset holds a pointer, or it holds the first
    # four bytes of a CExoArrayList and a write there replaces a live data
    # pointer with a number. Reading is unaffected. Writing takes
    # allow_unverified_writes, which is the whole point of the opt-in.
    #
    # Demotion only: a field the research file already marks med or low keeps its
    # own marking.
    demoted = shape_unconfirmed and confidence == "High"
    if demoted:
        confidence = "Med"

    return {
        "demoted": demoted,
        "name": field["name"],
        "type_text": type_text,
        "meaning": field.get("meaning"),
        "struct_name": struct_name,
        "offset": field["offset"],
        "size": size,
        "elem_size": elem_size,
        "count": count,
        "kind": kind,
        "elem": elem,
        "confidence": confidence,
        "list_shape_unconfirmed": shape_unconfirmed,
    }


def emit(game: str, doc: dict, tables: list[tuple[dict, list[dict]]], report: list[str]) -> str:
    lines = [
        f"// Generated by tools/gen_structs.py from data/research/phasor_structs.json.",
        f"// Do not edit; regenerate.",
        f"//",
        f"// {len(tables)} layouts, {sum(len(f) for _, f in tables)} fields, game {game}.",
        f"//",
        f"// Every offset below survived a contiguity walk, the ~1000 free assertions",
        f"// Ghidra's field_<hex> names give, and an exact size total. The static_asserts",
        f"// that follow each table repeat the walk in constexpr, so a hand edit to this",
        f"// file is a compile error and not a wrong number at runtime.",
        "",
        "// clang-format off",
        "",
        'static_assert(sizeof(void*) == 4, "32-bit only: these offsets describe a 32-bit process");',
        "",
    ]
    for struct, fields in tables:
        sym = f"kFields_{struct['name']}"
        lines.append(f"// {struct['name']}, {struct['size']} bytes, {len(fields)} fields.")
        lines.append(f"static constexpr Field {sym}[] = {{")
        for f in fields:
            lines.append(
                "    {" + ", ".join([
                    c_string(f["name"]),
                    c_string(f["type_text"]),
                    c_string(f["meaning"]),
                    c_string(f["struct_name"]),
                    f'{f["offset"]}u',
                    f'{f["size"]}u',
                    f'{f["elem_size"]}u',
                    f'{f["count"]}u',
                    f'Kind::{f["kind"]}',
                    f'Kind::{f["elem"]}',
                    f'Confidence::{f["confidence"]}',
                    "true" if f["list_shape_unconfirmed"] else "false",
                ]) + "},")
        lines.append("};")
        lines.append(
            f"static_assert(layout_is_packed({sym}, {len(fields)}, {struct['size']}u),\n"
            f'              "{struct["name"]}: fields are not packed from 0 to its asserted size");')
        lines.append("")

    lines.append("static constexpr Layout kLayouts[] = {")
    for struct, fields in tables:
        lines.append("    {" + ", ".join([
            c_string(struct["name"]),
            f'{struct["size"]}u',
            f"kFields_{struct['name']}",
            f"{len(fields)}u",
            c_string(struct.get("how_to_obtain")),
        ]) + "},")
    lines.append("};")
    lines.append("")
    lines.append("// What the generator could not resolve, recorded here rather than guessed at.")
    for line in report:
        lines.append(f"// {line}")
    lines.append("")
    return "\n".join(lines)


def build(game: str, check_only: bool) -> int:
    doc = json.loads(RESEARCH.read_text())
    layouts = {s["name"]: s["size"] for s in doc["structs"]}

    notes = verify(doc, layouts)

    tables: list[tuple[dict, list[dict]]] = []
    folded_all: list[str] = []
    candidates_all: list[str] = []
    unresolved: list[str] = []

    for struct in doc["structs"]:
        fields, folded, candidates = fold_split_lists(struct, layouts)
        folded_all += folded
        candidates_all += candidates

        # The fold must not disturb the layout: re-walk what we are about to emit.
        run = 0
        resolved = []
        for f in fields:
            c = classify(f, layouts)
            if c["offset"] != run:
                raise Fatal(f"{struct['name']}.{c['name']}: folding broke the walk at "
                            f"0x{c['offset']:x} (expected 0x{run:x})")
            run = c["offset"] + c["size"]
            if c["kind"] == "List" and c["elem"] == "Unknown":
                unresolved.append(f"{struct['name']}.{c['name']}")
            resolved.append(c)
        if run != struct["size"]:
            raise Fatal(f"{struct['name']}: emitted walk ends at {run}, size is {struct['size']}")
        tables.append((struct, resolved))

    report = list(notes)
    report.append(f"split-form lists folded into one field: {len(folded_all)}")
    for f in folded_all:
        report.append(f"  folded {f}")
    report.append(f"unannotated ptr+size+capacity shape-alikes left as ptr: {len(candidates_all)}")
    for c in candidates_all:
        report.append(f"  candidate {c}")
    report.append(f"lists whose element type the research prose does not state: {len(unresolved)}")
    for u in unresolved:
        report.append(f"  unresolved elements {u}")

    # Is the runtime's confidence gate reachable?
    #
    # The gate refuses a write when the field is below high confidence, and the
    # write path only ever attempts a store on a scalar or an f32 -- everything
    # else is refused as an aggregate before the gate is consulted. So the two
    # sets have to overlap or the gate is dead code that reads like a safety
    # feature. This counts the overlap on every run rather than leaving it to be
    # discovered by someone auditing the shipped module.
    demoted_all = [f"{s['name']}.{f['name']}"
                   for s, fields in tables for f in fields if f["demoted"]]
    gated = [f"{s['name']}.{f['name']}"
             for s, fields in tables for f in fields
             if f["kind"] in WRITABLE_KINDS and f["confidence"] != "High"]
    attempted = sum(1 for _, fields in tables for f in fields
                    if f["kind"] in WRITABLE_KINDS)
    report.append(f"shape-unconfirmed pointers demoted to med confidence: {len(demoted_all)}")
    for d in demoted_all:
        report.append(f"  demoted {d}")
    report.append(f"fields a write attempts a store on: {attempted}")
    report.append(f"of those, below high confidence, so allow_unverified_writes "
                  f"decides the outcome: {len(gated)}")

    text = emit(game, doc, tables, report)
    out = OUTDIR / f"structs_{game}.inc"
    if not check_only:
        OUTDIR.mkdir(parents=True, exist_ok=True)
        out.write_text(text)

    print(f"{game}: {len(tables)} layouts, {sum(len(f) for _, f in tables)} fields")
    for line in notes:
        print(f"  ok: {line}")
    print(f"  folded {len(folded_all)} split-form list(s): "
          + (", ".join(folded_all) if folded_all else "none"))
    print(f"  {len(candidates_all)} unannotated shape-alike triple(s) left as ptr "
          f"(reported, not promoted)")
    print(f"  {len(unresolved)} list(s) with no element type in the prose: "
          + (", ".join(unresolved) if unresolved else "none"))
    print(f"  {len(demoted_all)} shape-unconfirmed pointer(s) demoted to med confidence")
    print(f"  the confidence gate can decide {len(gated)} of the {attempted} field(s) "
          f"a write attempts a store on"
          + ("  <-- UNREACHABLE GATE" if not gated else ""))
    print(f"  {'checked, wrote nothing' if check_only else 'wrote ' + str(out.relative_to(ROOT))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", default="k1", choices=["k1"],
                    help="the research file covers K1 only; K2 layouts are not recovered yet")
    ap.add_argument("--check", action="store_true", help="verify and write nothing")
    args = ap.parse_args()
    try:
        return build(args.game, args.check)
    except Fatal as exc:
        print(f"gen_structs: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
