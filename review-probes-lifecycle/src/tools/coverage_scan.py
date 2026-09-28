#!/usr/bin/env python3
"""Static soft-lock scan: dialog graph + NCS strings, no running game.

Walks the copies kq says the game would load (--winners). Reports missing
Active/Script NCS, unreachable nodes, and strings that appear only in
conditional scripts (likely Get* with no in-module Set*).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KQ = ROOT / "scripts" / "harness" / "kq.sh"

# CONSTS in Odyssey NCS: 04 05 + uint16 BE length + bytes. Seen on k_end_plot2.


def kq(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("TMPDIR", str(ROOT / "tmp" / "scratch"))
    return subprocess.run(
        [str(KQ), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def kq_json_lines(*args: str) -> list[dict]:
    p = kq(*args)
    if p.returncode != 0:
        print(p.stderr or p.stdout, file=sys.stderr)
        raise SystemExit(p.returncode or 1)
    out = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            out.append(json.loads(line))
    return out


def kq_json(*args: str) -> dict:
    p = kq(*args)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[:400])
    return json.loads(p.stdout)


def ncs_strings(data: bytes) -> list[str]:
    found: list[str] = []
    i = 0
    n = len(data)
    while i < n - 4:
        if data[i] == 0x04 and data[i + 1] == 0x05:
            ln = int.from_bytes(data[i + 2 : i + 4], "big")
            if 1 <= ln <= 64 and i + 4 + ln <= n:
                raw = data[i + 4 : i + 4 + ln]
                if all(32 <= b < 127 for b in raw):
                    found.append(raw.decode("ascii"))
                    i += 4 + ln
                    continue
        i += 1
    return found


def ncs_raw(resref: str, container: str | None) -> bytes | None:
    args = ["cat", resref, "-t", "ncs", "--raw"]
    if container:
        args += ["--from", container]
    env = os.environ.copy()
    env.setdefault("TMPDIR", str(ROOT / "tmp" / "scratch"))
    b = subprocess.run([str(KQ), *args], check=False, capture_output=True, env=env)
    if b.returncode != 0 or not b.stdout.startswith(b"NCS"):
        return None
    return b.stdout


def walk_dlg(content: dict) -> dict:
    starts = content.get("StartingList") or []
    entries = content.get("EntryList") or []
    replies = content.get("ReplyList") or []

    scripts: set[str] = set()
    conditionals: set[str] = set()
    actions: set[str] = set()

    def add_script(slot: str, name: str, cond: bool) -> None:
        name = (name or "").strip()
        if not name:
            return
        scripts.add(name)
        (conditionals if cond else actions).add(name)

    entry_linked = set()
    reply_linked = set()
    for s in starts:
        add_script("start", s.get("Active") or "", True)
        if "Index" in s:
            entry_linked.add(int(s["Index"]))

    for e in entries:
        add_script("entry", e.get("Script") or "", False)
        for link in e.get("RepliesList") or []:
            add_script("reply-active", link.get("Active") or "", True)
            if "Index" in link:
                reply_linked.add(int(link["Index"]))

    for r in replies:
        add_script("reply", r.get("Script") or "", False)
        for link in r.get("EntriesList") or []:
            add_script("entry-active", link.get("Active") or "", True)
            if "Index" in link:
                entry_linked.add(int(link["Index"]))

    orphan_entries = [i for i in range(len(entries)) if i not in entry_linked]
    orphan_replies = [i for i in range(len(replies)) if i not in reply_linked]
    return {
        "entries": len(entries),
        "replies": len(replies),
        "starts": len(starts),
        "scripts": sorted(scripts),
        "conditionals": sorted(conditionals),
        "actions": sorted(actions),
        "orphan_entries": orphan_entries,
        "orphan_replies": orphan_replies,
        "end_conversation": (content.get("EndConversation") or "").strip(),
        "end_abort": (content.get("EndConverAbort") or "").strip(),
        "speakers": sorted({
            (e.get("Speaker") or "").strip()
            for e in entries
            if (e.get("Speaker") or "").strip()
        }),
        "start_actives": [
            (s.get("Active") or "").strip()
            for s in starts
            if (s.get("Active") or "").strip()
        ],
    }


def scan_module(module: str, all_ncs: bool = False) -> dict:
    dlgs = kq_json_lines("ls", "-t", "dlg", "-m", module, "--winners")
    report = {
        "module": module,
        "dialogs": [],
        "missing_ncs": [],
        "orphan_nodes": [],
        "conditional_only_strings": [],
        "ncs_errors": [],
    }
    cond_scripts: set[str] = set()
    action_scripts: set[str] = set()
    script_container: dict[str, str] = {}

    ncs_hits = kq_json_lines("ls", "-t", "ncs", "-m", module, "--winners")
    ncs_index = {h["resref"].lower(): h for h in ncs_hits}

    for d in dlgs:
        container = d.get("container") or ""
        try:
            blob = kq_json("cat", d["resref"], "-t", "dlg", "--from", container, "-f", "json")
        except (RuntimeError, json.JSONDecodeError) as e:
            report["ncs_errors"].append(f"dlg {d['resref']}: {e}")
            continue
        info = walk_dlg(blob.get("content") or {})
        info["resref"] = d["resref"]
        info["container"] = container
        report["dialogs"].append(info)
        cond_scripts.update(info["conditionals"])
        action_scripts.update(info["actions"])
        for name in info["scripts"]:
            script_container.setdefault(name.lower(), container)
        if info["orphan_entries"] or info["orphan_replies"]:
            report["orphan_nodes"].append(
                {
                    "dlg": d["resref"],
                    "entries": info["orphan_entries"],
                    "replies": info["orphan_replies"],
                }
            )

    all_scripts = cond_scripts | action_scripts
    for name in sorted(all_scripts):
        if name.lower() not in ncs_index:
            # May live in templates.bif / override, not this module.
            which = kq("which", name, "-t", "ncs")
            if which.returncode != 0 or '"matches": 0' in which.stdout:
                report["missing_ncs"].append(name)

    cond_strings: dict[str, set[str]] = defaultdict(set)
    action_strings: dict[str, set[str]] = defaultdict(set)
    for name in sorted(all_scripts):
        hit = ncs_index.get(name.lower())
        container = hit["container"] if hit else None
        raw = ncs_raw(name, container)
        if raw is None:
            continue
        strings = ncs_strings(raw)
        target = cond_strings if name in cond_scripts else action_strings
        for s in strings:
            target[s].add(name)

    # Placeable/trigger scripts write flags dialogs only read. Off by default:
    # a late module has hundreds of NCS and each kq cat is a process.
    if all_ncs:
        for hit in ncs_hits:
            name = hit.get("resref") or ""
            if not name or name.lower() in {s.lower() for s in all_scripts}:
                continue
            raw = ncs_raw(name, hit.get("container"))
            if raw is None:
                continue
            for s in ncs_strings(raw):
                action_strings[s].add(name)

    action_set = set(action_strings)
    for s, readers in sorted(cond_strings.items()):
        if s not in action_set and not s.startswith("k_") and "_" in s:
            # Heuristic: plot-flag style names, not speaker tags like end_trask.
            report["conditional_only_strings"].append(
                {"string": s, "read_by": sorted(readers)}
            )

    report["dialog_count"] = len(report["dialogs"])
    report["script_count"] = len(all_scripts)
    return report


def print_text(report: dict) -> None:
    print(f"module {report['module']}: {report['dialog_count']} dialogs, "
          f"{report['script_count']} referenced scripts")
    if report["missing_ncs"]:
        print("missing NCS (Active/Script resref has no winning .ncs):")
        for n in report["missing_ncs"]:
            print(f"  - {n}")
    else:
        print("missing NCS: none")
    orphans = [o for o in report["orphan_nodes"] if o["entries"] or o["replies"]]
    print(f"dialogs with unlinked nodes: {len(orphans)}")
    for o in orphans[:20]:
        print(f"  - {o['dlg']} entries={o['entries']} replies={o['replies']}")
    print("conditional-only strings (in Active NCS, never in Script NCS this module):")
    if not report["conditional_only_strings"]:
        print("  (none matched the plot-flag heuristic)")
    for row in report["conditional_only_strings"][:40]:
        print(f"  - {row['string']}  read_by={','.join(row['read_by'])}")
    if len(report["conditional_only_strings"]) > 40:
        print(f"  … {len(report['conditional_only_strings']) - 40} more")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-m", "--module", default="end_m01aa")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--all-ncs", action="store_true",
                    help="also scan non-dialog NCS for writers (slow on large modules)")
    ap.add_argument("-o", "--out", default="")
    args = ap.parse_args()
    if not KQ.is_file():
        print("kq wrapper missing", file=sys.stderr)
        return 2
    report = scan_module(args.module, all_ncs=args.all_ncs)
    text = json.dumps(report, indent=2) if args.json else None
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    if args.json:
        print(text)
    else:
        print_text(report)
        if args.out:
            print(f"json -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
