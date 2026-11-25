#!/usr/bin/env python3
"""Generate signature-enriched address tables, unified_kotor.json, builds.inc, and coverage docs.

Reuses tools/sigforge to:
  1. Sync newly defined VM/dialog sites across K1 builds while preserving packed identities.
  2. Transfer missing sites from K2 GOG -> K2 Steam via unique masked patterns / xref_thunks.
  3. Attach `pattern`+`mask`, `xref_thunk`, or explicit `signature_reason` to every site
     in every shipped `data/addresses/*.json`.
  4. Emit `data/signatures/unified_kotor.json` for cross-version / modded / spinoff fallback.
  5. Sync `src/generated/builds.inc` for all non-static builds and emit `docs/signature-coverage.md`.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
ADDR_DIR = ROOT / "data" / "addresses"
SIG_DIR = ROOT / "data" / "signatures"
DOCS_OUT = ROOT / "docs" / "signature-coverage.md"
BUILDS_INC = ROOT / "src" / "generated" / "builds.inc"

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import gen_address_tables as gat  # noqa: E402
from sigforge.binary_view import BinaryView  # noqa: E402
from sigforge.synthesizer import SignatureResult, _find_unique_thunk_to, synthesize_unique  # noqa: E402

BIN_ROOT = Path("/home/brunner56/biodecompwarehouse/kotorxid/output/binaries")

RAW_IMAGE_MAP: dict[str, Path] = {
    "k1_gog_103": BIN_ROOT / "K1__k1_win_gog_swkotor.exe/artifacts/raw_image",
    "k1_steam_103": BIN_ROOT / "K1__k1_win_steam_swkotor.exe/artifacts/raw_image",
    "k1_steam_103_unpacked": BIN_ROOT / "K1__k1_win_gog_swkotor.exe/artifacts/raw_image",
    "k2_gog_aspyr": BIN_ROOT / "TSL__k2_win_gog_aspyr_swkotor2.exe/artifacts/raw_image",
    "k2_steam_aspyr": BIN_ROOT / "TSL__k2_win_steam_aspyr_swkotor2.exe/artifacts/raw_image",
    "k2_steam_linux": BIN_ROOT / "TSL__k2_linux_swkotor2.elf/artifacts/raw_image",
    "k1_mac_steam_x64": BIN_ROOT / "K1__k1_mac_swkotor.app/artifacts/raw_image",
    "k2_mac_steam_x64": BIN_ROOT / "TSL__k2_mac_swkotor2.app/artifacts/raw_image",
}


def _va_int(entry: dict) -> int | None:
    a = entry.get("addr")
    if a is None:
        return None
    val = int(str(a), 16) if isinstance(a, str) else int(a)
    return val if val != 0 else None


def _is_in_exec(bv: BinaryView, va: int) -> bool:
    for sec in bv.sections:
        if sec.executable and sec.va <= va < sec.va + sec.vsize:
            return True
    return False


def _detect_unresolved_reason(bv: BinaryView, va: int, base_reason: str, hit_count: int) -> str:
    raw = bv.read_va(va, 16)
    if not raw:
        return "unreadable_va_in_image"
    # Check 1-hop E9 -> E9 double thunk pattern (e.g. `mov ecx, [ecx+4]; jmp -> jmp`)
    for off in range(min(6, len(raw) - 5)):
        if raw[off] in (0xE9, 0xE8):
            rel = struct.unpack_from("<i", raw, off + 1)[0]
            hop1 = (va + off + 5 + rel) & ((1 << bv.bits) - 1)
            hop1_raw = bv.read_va(hop1, 24)
            if hop1_raw and (b"\xE9" in hop1_raw[:16] or b"\xEB" in hop1_raw[:16]):
                return "double_hop_thunk_or_shared_wrapper (nested jmp relay too short for direct 1-level unique pattern)"
    if base_reason == "ambiguous_pattern":
        return f"comdat_identical_code_folding ({hit_count} byte-identical executable functions share entire body)"
    if base_reason == "short_stub_non_unique":
        return "short_stub_non_unique (function body terminates before unique byte length)"
    return base_reason


def _res_to_entry_fields(bv: BinaryView, va: int, entry: dict, res: SignatureResult) -> None:
    for k in ("pattern", "mask", "xref_thunk", "signature_kind", "signature_reason"):
        entry.pop(k, None)

    if res.kind == "pattern":
        entry["signature_kind"] = "pattern"
        entry["pattern"] = res.pattern
        entry["mask"] = res.mask
    elif res.kind == "xref_thunk":
        entry["signature_kind"] = "xref_thunk"
        entry["xref_thunk"] = {
            "opcode": res.thunk_opcode,
            "prefix": res.thunk_prefix,
            "suffix": res.thunk_suffix,
            "target_pattern": res.target_pattern,
            "target_mask": res.target_mask,
            "kind_detail": res.reason,
        }
    else:
        entry["signature_kind"] = "unresolved_code"
        entry["signature_reason"] = _detect_unresolved_reason(bv, va, res.reason, res.hit_count)


def _locate_xref_thunk_in_target(bv: BinaryView, xt: dict) -> int | None:
    tpat = bytes.fromhex(xt["target_pattern"])
    tmsk = bytes.fromhex(xt["target_mask"])
    hits = bv.scan_masked(tpat, tmsk, max_hits=3)
    if len(hits) != 1:
        return None
    target_va = hits[0]
    opcode = int(xt.get("opcode", "e9"), 16)
    prefix = bytes.fromhex(xt.get("prefix", ""))
    suffix = bytes.fromhex(xt.get("suffix", ""))
    return _find_unique_thunk_to(bv, opcode, prefix, suffix, target_va)


def _sync_k1_steam_tables(gog: dict, bv_steam: BinaryView | None) -> None:
    gog_sites = gog["sites"]
    for alias in ("k1_steam_103", "k1_steam_103_unpacked"):
        p = ADDR_DIR / f"{alias}.json"
        if not p.exists():
            continue
        doc = json.loads(p.read_text())
        sites = doc["sites"]
        for name in (
            "vm.stack_pointer",
            "vmcmd.destroy_game_defined_structure",
            "exo.string_dtor",
            "dialog.check_script",
        ):
            src = gog_sites.get(name)
            if not src:
                continue
            dst = dict(src)
            if bv_steam is not None and dst.get("kind") not in ("field", "reference"):
                va = _va_int(dst)
                if va is not None and _is_in_exec(bv_steam, va):
                    exp_hex = dst.get("expected_bytes", "")
                    if exp_hex:
                        live = bv_steam.read_va(va, len(exp_hex) // 2)
                        if live != bytes.fromhex(exp_hex):
                            continue
            sites[name] = dst
        _recompute_summary(doc)
        p.write_text(json.dumps(doc, indent=2) + "\n")


def _transfer_k2_gog_to_steam(k2_gog: dict, bv_gog: BinaryView, bv_steam: BinaryView) -> tuple[int, int]:
    steam_path = ADDR_DIR / "k2_steam_aspyr.json"
    doc = json.loads(steam_path.read_text())
    sites = doc["sites"]
    transferred_pat = 0
    transferred_xref = 0

    for name, src in k2_gog["sites"].items():
        cur = sites.get(name)
        cur_va = _va_int(cur) if cur else None
        if cur and (cur_va is not None or (cur.get("kind") == "field" and (cur.get("size") or 0) > 0)):
            # Sync kind upgrades (e.g., dialog.check_script -> detour) cleanly
            if cur.get("kind") != src.get("kind") and src.get("kind") == "detour":
                cur["kind"] = "detour"
            continue

        if src.get("kind") in ("field", "reference"):
            continue
        va = _va_int(src)
        if va is None or not _is_in_exec(bv_gog, va):
            continue
        sig = synthesize_unique(bv_gog, va, max_bytes=512)
        new_va: int | None = None
        how = ""
        if sig.kind == "pattern":
            hits = bv_steam.scan_masked(bytes.fromhex(sig.pattern), bytes.fromhex(sig.mask), max_hits=3)
            if len(hits) == 1:
                new_va = hits[0]
                how = "sigforge_pattern_transfer"
                transferred_pat += 1
        elif sig.kind == "xref_thunk":
            xt = {
                "opcode": sig.thunk_opcode,
                "prefix": sig.thunk_prefix,
                "suffix": sig.thunk_suffix,
                "target_pattern": sig.target_pattern,
                "target_mask": sig.target_mask,
            }
            new_va = _locate_xref_thunk_in_target(bv_steam, xt)
            if new_va is not None:
                how = "sigforge_xref_thunk_transfer"
                transferred_xref += 1

        if new_va is not None:
            exp = bv_steam.read_va(new_va, 16)
            sites[name] = {
                "cls": src.get("cls", ""),
                "method": src.get("method", ""),
                "kind": src.get("kind", "call"),
                "required": src.get("required", False),
                "addr": new_va,
                "source": "adjudicated",
                "confidence": 0.99,
                "method_detail": how,
                "candidates": 1,
                "addr_hex": f"0x{new_va:08X}",
                "expected_bytes": exp.hex(),
            }

    _recompute_summary(doc)
    steam_path.write_text(json.dumps(doc, indent=2) + "\n")
    return transferred_pat, transferred_xref


def _recompute_summary(doc: dict) -> None:
    sites = doc.get("sites", {})
    total = len(sites)
    resolved_entries = []
    missing_req = []
    fields = 0
    for name, s in sites.items():
        if not isinstance(s, dict):
            continue
        kind = s.get("kind")
        is_field = kind == "field"
        ok = ((s.get("size") or 0) > 0) if is_field else (bool(s.get("addr")) or bool(s.get("resolved")))
        if is_field and ok:
            fields += 1
        if ok:
            resolved_entries.append((name, s))
        elif s.get("required"):
            missing_req.append(name)

    if "summary" in doc:
        doc["summary"].update({
            "total": total,
            "resolved": len(resolved_entries),
            "by_func": sum(1 for _, s in resolved_entries if s.get("source") == "func"),
            "by_identity": sum(1 for _, s in resolved_entries if s.get("source") == "identity"),
            "by_adjudication": sum(1 for _, s in resolved_entries if s.get("source") == "adjudicated"),
            "by_field": fields,
            "missing_required": missing_req,
            "installable": not missing_req,
        })


def enrich_table(alias: str, path: Path, bv: BinaryView | None) -> dict:
    doc = json.loads(path.read_text())
    stats = {
        "alias": alias,
        "game": doc.get("game", "?"),
        "platform": doc.get("platform", "?"),
        "arch": doc.get("arch", "x86"),
        "total": 0,
        "resolved": 0,
        "pattern": 0,
        "xref_thunk": 0,
        "field": 0,
        "data_ref": 0,
        "unresolved_code": 0,
        "unmapped_site": 0,
        "non_pattern_reasons": [],
    }
    for name, s in sorted(doc.get("sites", {}).items()):
        if not isinstance(s, dict):
            continue
        stats["total"] += 1
        kind = s.get("kind")
        if kind == "field":
            s["signature_kind"] = "field"
            s["signature_reason"] = "struct_field_or_global_offset (not executable code; ABI layout binding)"
            if (s.get("size") or 0) > 0:
                stats["resolved"] += 1
                stats["field"] += 1
            else:
                stats["unmapped_site"] += 1
            continue

        va = _va_int(s)
        if va is None:
            s["signature_kind"] = "unmapped"
            s["signature_reason"] = "site_not_yet_resolved_in_build_corpus"
            stats["unmapped_site"] += 1
            continue

        stats["resolved"] += 1
        if kind == "reference" or (bv is not None and not _is_in_exec(bv, va)):
            s["signature_kind"] = "data_ref"
            s["signature_reason"] = (
                "rdata_vtable_or_data_pointer (not executable code; locate via code xref)"
                if (bv is None or not _is_in_exec(bv, va))
                else "reference_only_site"
            )
            stats["data_ref"] += 1
            stats["non_pattern_reasons"].append((name, s["signature_kind"], s["signature_reason"]))
            continue

        if bv is None:
            s["signature_kind"] = "no_local_reference_image"
            s["signature_reason"] = "reference_image_not_present_in_environment"
            stats["unresolved_code"] += 1
            stats["non_pattern_reasons"].append((name, s["signature_kind"], s["signature_reason"]))
            continue

        res = synthesize_unique(bv, va, max_bytes=512)
        _res_to_entry_fields(bv, va, s, res)
        sk = s["signature_kind"]
        stats[sk] += 1
        if sk != "pattern":
            reason = s.get("signature_reason") or (s.get("xref_thunk") or {}).get("kind_detail", "xref_thunk")
            stats["non_pattern_reasons"].append((name, sk, reason))

    path.write_text(json.dumps(doc, indent=2) + "\n")
    return stats


def build_unified_catalog(docs: dict[str, dict]) -> dict:
    games: dict[str, dict[str, dict]] = {"K1": {}, "K2": {}}
    # Prefer GOG first (cleanest primary symbols), then Linux/Steam/Mac
    priority = [
        "k1_gog_103", "k1_steam_103_unpacked", "k1_steam_103", "k1_mac_steam_x64",
        "k2_gog_aspyr", "k2_steam_aspyr", "k2_steam_linux", "k2_mac_steam_x64",
    ]
    for alias in priority:
        doc = docs.get(alias)
        if not doc:
            continue
        game = doc.get("game", "").upper()
        if game not in games:
            continue
        arch = doc.get("arch", "x86")
        fmt = doc.get("format", "pe")
        plat = doc.get("platform", "win")
        for name, s in doc.get("sites", {}).items():
            if not isinstance(s, dict):
                continue
            sk = s.get("signature_kind")
            if sk not in ("pattern", "xref_thunk", "field"):
                continue
            if sk == "field" and not s.get("size"):
                continue
            slot = games[game].setdefault(name, {
                "kind": s.get("kind", "call"),
                "required": bool(s.get("required", False)),
                "cls": s.get("cls", ""),
                "method": s.get("method", ""),
                "locators": [],
            })
            if s.get("required"):
                slot["required"] = True

            if sk == "pattern":
                loc = {
                    "type": "pattern",
                    "arch": arch,
                    "format": fmt,
                    "platform": plat,
                    "pattern": s["pattern"],
                    "mask": s["mask"],
                    "expected_bytes": s.get("expected_bytes", ""),
                }
            elif sk == "xref_thunk":
                loc = {
                    "type": "xref_thunk",
                    "arch": arch,
                    "format": fmt,
                    "platform": plat,
                    "xref_thunk": s["xref_thunk"],
                    "expected_bytes": s.get("expected_bytes", ""),
                }
            else:
                loc = {
                    "type": "field",
                    "arch": arch,
                    "format": fmt,
                    "platform": plat,
                    "owner": s.get("owner", ""),
                    "offset": s.get("offset", 0),
                    "size": s.get("size", 0),
                }
            # Deduplicate identical locators across e.g. GOG vs Steam x86 Windows
            key_blob = json.dumps({k: v for k, v in loc.items() if k != "platform"}, sort_keys=True)
            existing_keys = {
                json.dumps({k: v for k, v in e.items() if k not in ("platform", "platforms")}, sort_keys=True): e
                for e in slot["locators"]
            }
            if key_blob in existing_keys:
                plats = existing_keys[key_blob].setdefault("platforms", [existing_keys[key_blob]["platform"]])
                if plat not in plats:
                    plats.append(plat)
            else:
                loc["platforms"] = [plat]
                slot["locators"].append(loc)

    return {
        "format": "kotorjit.unified-signatures/v1",
        "games": {g.lower(): dict(sorted(sites.items())) for g, sites in games.items()},
    }


def write_coverage_doc(all_stats: list[dict], transferred: tuple[int, int]) -> None:
    lines = [
        "# Signature Coverage Report",
        "",
        "Generated by `tools/gen_signatures.py` via the project-agnostic `tools/sigforge` engine.",
        "",
        f"K2 GOG -> K2 Steam automated signature transfer recovered **{transferred[0]} patterns + {transferred[1]} xref_thunks ({transferred[0] + transferred[1]} total new bindings)**.",
        "",
        "## Per-Build Coverage",
        "",
        "| Build | Game | Platform | Resolved / Total | Direct Pattern | Xref Thunk | Field Offset | Data Ref | Unresolved Code |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for st in all_stats:
        lines.append(
            f"| `{st['alias']}` | {st['game']} | {st['platform']} ({st['arch']}) | "
            f"{st['resolved']}/{st['total']} | {st['pattern']} | {st['xref_thunk']} | "
            f"{st['field']} | {st['data_ref']} | {st['unresolved_code']} |"
        )
    lines.extend([
        "",
        "## Why Specific Resolved Sites Do Not Use a Direct Pattern",
        "",
        "Every code site is tested for a unique masked byte pattern (`pattern`+`mask`), then a unique caller/callee thunk xref (`xref_thunk`), and any remaining site records its exact technical reason below.",
        "",
    ])
    for st in all_stats:
        items = [x for x in st["non_pattern_reasons"] if x[1] != "field"]
        lines.append(f"### `{st['alias']}`")
        if not items:
            lines.append("All resolved code sites use unique direct patterns.")
        else:
            lines.append("")
            lines.append("| Site | Signature Kind | Exact Technical Reason |")
            lines.append("|---|---|---|")
            for name, kind, reason in items:
                lines.append(f"| `{name}` | `{kind}` | {reason} |")
        lines.append("")
    DOCS_OUT.write_text("\n".join(lines), encoding="utf-8")


def sync_builds_inc(docs: dict[str, dict]) -> None:
    # Include every non-static build emitted into data/addresses/*.json in deterministic BUILDS order
    ordered: dict[str, dict] = {}
    for alias in gat.BUILDS:
        if gat.BUILDS[alias].get("static_only"):
            continue
        if alias in docs:
            ordered[alias] = docs[alias]
    if ordered:
        BUILDS_INC.write_text(gat.emit_builds_inc(ordered), encoding="utf-8")


def main() -> int:
    bvs: dict[str, BinaryView] = {}
    for alias, p in RAW_IMAGE_MAP.items():
        if p.exists():
            # Skip thin/fat mismatch gently for Mac if MachO arch doesn't parse cleanly
            try:
                bvs[alias] = BinaryView.from_file(p)
            except Exception as exc:
                print(f"warning: skipping BinaryView for {alias} ({p}): {exc}")

    k1_gog = json.loads((ADDR_DIR / "k1_gog_103.json").read_text())
    _sync_k1_steam_tables(k1_gog, bvs.get("k1_steam_103"))

    transferred = (0, 0)
    if "k2_gog_aspyr" in bvs and "k2_steam_aspyr" in bvs:
        k2_gog = json.loads((ADDR_DIR / "k2_gog_aspyr.json").read_text())
        transferred = _transfer_k2_gog_to_steam(k2_gog, bvs["k2_gog_aspyr"], bvs["k2_steam_aspyr"])
        print(f"K2 GOG -> K2 Steam transfer: +{transferred[0]} patterns, +{transferred[1]} xref_thunks")

    all_stats = []
    docs: dict[str, dict] = {}
    for p in sorted(ADDR_DIR.glob("*.json")):
        alias = p.stem
        st = enrich_table(alias, p, bvs.get(alias))
        all_stats.append(st)
        docs[alias] = json.loads(p.read_text())
        print(
            f"{alias:22s}: resolved={st['resolved']:3d}/{st['total']} "
            f"pattern={st['pattern']:3d} xref={st['xref_thunk']:2d} "
            f"field={st['field']:3d} ref={st['data_ref']:2d} unres_code={st['unresolved_code']}"
        )

    SIG_DIR.mkdir(parents=True, exist_ok=True)
    unified = build_unified_catalog(docs)
    (SIG_DIR / "unified_kotor.json").write_text(json.dumps(unified, indent=2) + "\n")
    write_coverage_doc(all_stats, transferred)
    sync_builds_inc(docs)
    print(f"wrote {SIG_DIR / 'unified_kotor.json'}, {DOCS_OUT}, and {BUILDS_INC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
