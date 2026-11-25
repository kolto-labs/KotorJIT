#!/usr/bin/env python3
"""Real-image check for hookmanifest/v1 pattern resolution.

Runs `kp_manifesttest image` (which never sees entry_va) against a plaintext
game image, then compares every pattern-bound site with the manifest's
entry_va and with the KP address table. Passes only when:

  * no bound site disagrees with entry_va or with the KP table,
  * every unbound code site is a refusal (missing / ambiguous / no_locator),
  * required sites that refuse are exactly --expect-refused.

    tools/manifest_resolve_check.py --tool build/kp_manifesttest \
        --image swkotor.exe --manifest hookmanifest.k1_win_gog.json \
        --table data/addresses/k1_gog_103.json \
        --expect-refused vm.stack_push_integer
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--expect-refused", action="append", default=[])
    a = ap.parse_args()

    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(a.tool))) as tmp:
        dump = os.path.join(tmp, "resolve.tsv")
        run = subprocess.run([a.tool, "image", a.image, a.manifest, "--overlay", a.table, "--dump", dump],
                             capture_output=True, text=True)
        sys.stdout.write(run.stdout)
        if not os.path.exists(dump):
            sys.stderr.write(run.stderr)
            return 2
        rows = {}
        with open(dump) as f:
            for line in f:
                name, status, addr, kind = line.rstrip("\n").split("\t")
                rows[name] = (status, int(addr, 16), kind)

    manifest = json.load(open(a.manifest))
    table = json.load(open(a.table))["sites"]
    failures = []

    seen = collections.Counter()
    agree = 0
    for fn in manifest["functions"]:
        base = fn.get("kp_site") or fn["id"]
        seen[base] += 1
        name = base if seen[base] == 1 else "%s#%d" % (base, seen[base])
        status, addr, _ = rows[name]
        if status == "bound":
            if addr == int(fn["entry_va"], 16):
                agree += 1
            else:
                failures.append("%s bound 0x%08X, manifest entry_va %s" % (name, addr, fn["entry_va"]))
        elif status not in ("missing", "ambiguous", "no_locator"):
            failures.append("%s unbound without a refusal reason (%s)" % (name, status))

    kp_agree = 0
    refused_required = []
    for name, site in table.items():
        if site.get("kind") == "field" or name not in rows:
            continue
        status, addr, _ = rows[name]
        if status == "bound":
            if addr == site.get("addr"):
                kp_agree += 1
            else:
                failures.append("%s bound 0x%08X, KP table 0x%08X" % (name, addr, site.get("addr", 0)))
        elif site.get("required"):
            refused_required.append("%s(%s)" % (name, status))

    expected = sorted(a.expect_refused)
    got = sorted(r.split("(")[0] for r in refused_required)
    if got != expected:
        failures.append("required refusals %s, expected %s" % (refused_required, expected))

    print("entry_va agreement: %d bound sites match" % agree)
    print("KP table agreement: %d bound" % kp_agree)
    print("required refused: %s" % (", ".join(refused_required) or "none"))
    for f in failures:
        print("FAIL:", f)
    print("OK" if not failures else "FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
