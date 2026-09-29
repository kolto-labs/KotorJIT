#!/usr/bin/env python3
"""Offline structural checks on the macOS x86_64 address tables.

Runs without the retail binaries (which never ship): it checks the shape and
internal consistency of data/addresses/k{1,2}_mac_steam_x64.json and their
agreement with src/generated/builds_macho.inc, src/api/abi_layout.hpp and
data/profiles/builds.toml. The full byte-for-byte verification against the
images is `tools/mac/gen_mac_tables.py --check`, which needs the local images.

    python3 tools/mac/mac_tables_test.py
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAIL = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)


REQUIRED = {"vm.run_script", "vm.execute_command", "vm.stack_pop_integer", "vm.stack_push_integer",
            "vm.stack_pop_float", "vm.stack_push_float", "vm.stack_pop_string", "vm.stack_push_string",
            "vm.stack_pop_object", "vm.stack_push_object", "app.server_main_loop", "console.do_console"}
EVENTS = {"event." + e for e in ("creature", "door", "placeable", "trigger", "module", "area",
                                 "encounter", "aoe", "store", "waypoint")}
IMAGE_BASE = 0x100000000


def check_table(alias, game):
    p = os.path.join(ROOT, "data/addresses/%s.json" % alias)
    d = json.load(open(p))
    check(d["game"] == game and d["platform"] == "mac" and d["format"] == "macho", alias + ": header")
    check(d["arch"] == "x86_64" and d["image_base"] == IMAGE_BASE, alias + ": arch/base")
    check(d["encrypted"] is False, alias + ": not encrypted")
    sites = d["sites"]
    # every required and event site present and resolved
    for name in REQUIRED | EVENTS:
        check(name in sites, "%s: missing site %s" % (alias, name))
    for name, s in sites.items():
        kind = s["kind"]
        check(kind in ("detour", "reference", "call", "field"), "%s.%s: bad kind %s" % (alias, name, kind))
        if kind == "field":
            check("offset" in s and "size" in s, "%s.%s: field needs offset/size" % (alias, name))
            # g.app_manager is a global: addr set, offset 0.
            if name == "g.app_manager":
                check(s["addr"] != 0, "%s.%s: global addr" % (alias, name))
            continue
        addr = s["addr"]
        check(IMAGE_BASE <= addr < IMAGE_BASE + 0x600000, "%s.%s: addr 0x%x out of __TEXT" % (alias, name, addr))
        eb = s.get("expected_bytes", "")
        check(len(eb) == 32 and re.fullmatch(r"[0-9a-f]{32}", eb), "%s.%s: expected_bytes must be 16 bytes hex" % (alias, name))
    # required sites all resolved (non-zero addr)
    for name in REQUIRED:
        check(sites[name]["addr"] != 0, "%s: required site %s unresolved" % (alias, name))
    return d


def read_layout_kx64():
    hdr = open(os.path.join(ROOT, "src/api/abi_layout.hpp")).read()
    body = hdr[hdr.index("inline constexpr EngineLayout kX64{"):]
    body = body[:body.index("};")]
    return [int(v, 0) for v in re.findall(r"\*/\s*(0x[0-9A-Fa-f]+|\d+)", body)]


def main():
    k1 = check_table("k1_mac_steam_x64", "K1")
    k2 = check_table("k2_mac_steam_x64", "K2")

    # The two builds share the same site set (they are the same engine).
    check(set(k1["sites"]) == set(k2["sites"]), "K1/K2 site sets differ")

    # builds_macho.inc lists both aliases and a text sha for each.
    inc = open(os.path.join(ROOT, "src/generated/builds_macho.inc")).read()
    for alias in ("k1_mac_steam_x64", "k2_mac_steam_x64"):
        check(("kText_%s" % alias) in inc, "builds_macho.inc missing text table for " + alias)
        check(inc.count('"%s"' % alias) >= 1, "builds_macho.inc missing build record for " + alias)

    # abi_layout.hpp kX64 is readable and has the 17 fields the generator checks.
    check(len(read_layout_kx64()) == 16, "abi_layout.hpp kX64 numeric field count (expected 16 + 1 bool)")

    # profiles registered as supported.
    prof = open(os.path.join(ROOT, "data/profiles/builds.toml")).read()
    for alias in ("k1_mac_steam_x64", "k2_mac_steam_x64"):
        m = re.search(r'id = "%s".*?status = "(\w+)"' % alias, prof, re.S)
        check(m and m.group(1) == "supported", "%s not registered supported in builds.toml" % alias)

    # adjudication evidence: every K1 function binding has >=2 derivations.
    adj = json.load(open(os.path.join(ROOT, "data/adjudication/mac_x64_bindings.json")))
    for site, v in adj["bindings"].items():
        check(len(v["derivations"]) >= 2, "K1 %s has <2 derivations" % site)

    if FAIL:
        print("FAIL (%d):" % len(FAIL))
        for m in FAIL:
            print("  " + m)
        sys.exit(1)
    print("mac_tables_test: OK (k1=%d sites, k2=%d sites)" % (len(k1["sites"]), len(k2["sites"])))


if __name__ == "__main__":
    main()
