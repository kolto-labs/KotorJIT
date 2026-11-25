#!/usr/bin/env python3
"""Offline cross-check of every place a build identity is written down.

A build is named in five places that no compiler checks against each other:

  src/generated/builds.inc           BuildRecord alias, file sha, base, format,
                                     encrypted flag, known-text digests, note
  data/addresses/<alias>.json        the per-build address table's identity
  tools/gen_address_tables.py        BUILDS (the generator's source of truth),
                                     including static_only rows it never emits
  src/api/model_profiles.cpp,        exact-image sha literals the model,
  src/api/animation_profiles.cpp,    animation and projectile backends bind by
  src/api/projectiles_profile.cpp
  src/runtime/runtime.cpp            build alias strings in the multiplayer
                                     ABI receipt gate

This test text-parses all of them (no import of the generator, no compile, no
game bytes) and fails when they disagree. Every profile sha must be a
BuildRecord or an explicit static_only Mac entry in the generator.

Drift that is real today and owned by a later stage is pinned in KNOWN_DRIFT
with the stage that clears it. A pin names the kind, the subject and the exact
offending value, so the same subject drifting to a different value fails as
new drift, and a pinned one that has gone away fails too (the ledger cannot
rot).

    python3 tools/platform_profile_consistency_test.py            # run tests
    python3 tools/platform_profile_consistency_test.py --report   # list findings
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# (kind, subject, exact detail) -> stage that clears it. The detail carries the
# offending value, so a pin cannot absorb a different drift on the same
# subject. Every entry is also reported as drift found, never as a pass.
_UNREG = " is neither a BuildRecord nor a static_only Mac entry"
KNOWN_DRIFT = {
    # The Mac model profiles bind exact slice shas, but the generator's k1_mac
    # and k2_mac rows carry md5 only and there is no k2_mac_x86_64 row at all.
    ("profile-sha-unregistered", "model:macos-k1-i386",
     "aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032" + _UNREG):
        "M0 static-only Mac generator entries",
    ("profile-sha-unregistered", "model:macos-k2-i386",
     "f14f285b1b6ed7e4bf000fe19ebcd0d6528d1d3e86d2832be6092761557c130d" + _UNREG):
        "M0 static-only Mac generator entries",
    ("profile-sha-unregistered", "model:macos-k2-x86_64",
     "469067c416f1a3ff391df73c7ace2d44a8d0a246253e8ad5752f6413ea033be4" + _UNREG):
        "M0 static-only k2_mac_x86_64 generator entry",
}


# --------------------------------------------------------------------------
# parsers


def parse_builds_inc(text: str) -> dict[str, dict]:
    texts: dict[str, list[tuple[str, str]]] = {}
    for m in re.finditer(r"static const KnownText kText_(\w+)\[\] = \{(.*?)\};", text, re.S):
        texts[m.group(1)] = re.findall(r'\{"([^"]+)", "([0-9a-f]{64})"\}', m.group(2))
    body = re.search(r"static const BuildRecord kBuilds\[\] = \{(.*)\};", text, re.S)
    records: dict[str, dict] = {}
    if not body:
        return records
    rec_re = re.compile(
        r'\{\s*"(?P<alias>\w+)",\s*"(?P<sha>[0-9a-f]*)",\s*'
        r"Format::(?P<fmt>\w+),\s*0x(?P<base>[0-9A-Fa-f]+),\s*(?P<enc>true|false),\s*"
        r'(?P<sva>0x[0-9A-Fa-f]+|0),\s*"(?P<sbytes>[0-9a-f]*)",\s*"(?P<sdesc>[^"]*)",\s*'
        r"kText_(?P<ktext>\w+),[^\n]*\n\s*\"(?P<note>(?:[^\"\\]|\\.)*)\",\s*\}",
        re.S)
    for m in rec_re.finditer(body.group(1)):
        a = m.group("alias")
        records[a] = {
            "sha256": m.group("sha"),
            "format": m.group("fmt"),
            "image_base": int(m.group("base"), 16),
            "encrypted": m.group("enc") == "true",
            "known_text": texts.get(m.group("ktext"), []),
            "ktext_name": m.group("ktext"),
            "note": m.group("note").replace('\\"', '"'),
        }
    # A record the regex could not read is itself a failure, not a skip.
    records["__raw_count__"] = body.group(1).count("\n    {\n")  # type: ignore[assignment]
    return records


def parse_generator_builds(text: str) -> dict[str, dict]:
    """BUILDS from gen_address_tables.py by AST, literals only.

    Importing the module would run its filesystem probes (_ref/_game_file) at
    import time; the AST walk reads the same dict without executing anything.
    """
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "BUILDS" for t in node.targets):
            if not isinstance(node.value, ast.Dict):
                break
            out: dict[str, dict] = {}
            for k, v in zip(node.value.keys, node.value.values):
                if not isinstance(k, ast.Constant) or not isinstance(v, ast.Dict):
                    continue
                entry: dict = {}
                for fk, fv in zip(v.keys, v.values):
                    if not isinstance(fk, ast.Constant):
                        continue
                    try:
                        entry[fk.value] = ast.literal_eval(fv)
                    except ValueError:
                        entry[fk.value] = "<expr>"
                out[k.value] = entry
            return out
    raise AssertionError("BUILDS = {...} not found in gen_address_tables.py")


def parse_profile_array(text: str, fn: str) -> tuple[int | None, list[str]]:
    """Declared std::array size and the profile ids in initializer order."""
    size = re.search(r"std::array<Profile,\s*(\d+)>\s*&\s*" + fn, text)
    ids = re.findall(r'\{\s*"((?:macos|windows|linux)-[\w-]+)"', text)
    return (int(size.group(1)) if size else None), ids


def parse_model_profiles(text: str) -> tuple[int | None, dict[str, str]]:
    size = re.search(r"std::array<Profile,\s*(\d+)>\s*&\s*profiles", text)
    pairs = re.findall(r'\{\s*"([\w-]+)",\s*"([0-9a-f]{64})"', text)
    return (int(size.group(1)) if size else None), dict(pairs)


_PROFILE_ID = r'"((?:macos|windows|linux)-[\w-]+)"'
_SHA_LIT = r'"([0-9a-f]{64})"'


def parse_projectiles_profile(text: str) -> dict[str, str]:
    """Every projectile profile in the file, however it is declared.

    Any adjacent sha/id string pair counts, in either order, so a second
    Profile, a Profile array or a renamed variable cannot hide a sha.
    """
    out = {pid: sha for sha, pid in re.findall(_SHA_LIT + r",\s*" + _PROFILE_ID, text)}
    out.update(re.findall(_PROFILE_ID + r",\s*" + _SHA_LIT, text))
    return out


def parse_runtime_aliases(text: str) -> set[str]:
    """Build aliases compared against build_ or build(), either side, == or !=."""
    build = r"build(?:_|\(\))"
    return (set(re.findall(build + r'\s*[!=]=\s*"(\w+)"', text))
            | set(re.findall(r'"(\w+)"\s*[!=]=\s*' + build, text)))


# --------------------------------------------------------------------------
# checker


def check(root: Path) -> list[tuple[str, str, str]]:
    """Every disagreement as (kind, subject, detail)."""
    f: list[tuple[str, str, str]] = []
    add = lambda kind, subj, detail: f.append((kind, subj, detail))

    inc = parse_builds_inc((root / "src/generated/builds.inc").read_text())
    raw_count = inc.pop("__raw_count__", 0)
    if raw_count != len(inc):
        add("builds-inc-unparsed", "builds.inc",
            f"{raw_count} record blocks, {len(inc)} parsed")
    gen = parse_generator_builds((root / "tools/gen_address_tables.py").read_text())
    record_shas = {r["sha256"]: a for a, r in inc.items()}

    fmt_map = {"Pe32": "pe", "Elf32": "elf"}
    for alias, rec in inc.items():
        if not HEX64.match(rec["sha256"]):
            add("bad-sha", alias, f"builds.inc sha {rec['sha256']!r}")
        g = gen.get(alias)
        if g is None:
            add("record-not-in-generator", alias, "BuildRecord alias missing from BUILDS")
        elif g.get("static_only"):
            add("static-only-emitted", alias, "static_only BUILDS entry has a BuildRecord")
        jpath = root / "data/addresses" / f"{alias}.json"
        if not jpath.exists():
            add("record-without-table", alias, f"{jpath.relative_to(root)} missing")
            continue
        j = json.loads(jpath.read_text())
        # The generator's own rule (gen_address_tables.py emit): identity.sha256
        # or derived_sha256. reference_sha256 is the plaintext twin for an
        # encrypted build and is deliberately not the file hash.
        jsha = (j.get("identity") or {}).get("sha256") or j.get("derived_sha256")
        checks = [
            ("build", j.get("build"), alias),
            ("sha256", jsha, rec["sha256"]),
            ("image_base", j.get("image_base"), rec["image_base"]),
            ("encrypted", bool(j.get("encrypted")), rec["encrypted"]),
            ("format", j.get("format"), fmt_map.get(rec["format"], rec["format"])),
            ("known_text", [(k["section"], k["sha256"]) for k in j.get("known_text") or []],
             [tuple(x) for x in rec["known_text"]]),
        ]
        for field, got, want in checks:
            if got != want:
                add(f"{field}-mismatch", alias, f"json={got!r} builds.inc={want!r}")
        if (j.get("note") or "") != rec["note"]:
            h = lambda t: hashlib.sha256(t.encode()).hexdigest()[:16]
            add("note-mismatch", alias, "json-note-sha256=%s builds.inc-note-sha256=%s"
                % (h(j.get("note") or ""), h(rec["note"])))
        if g is not None:
            gsha = g.get("sha256")
            if gsha and gsha != rec["sha256"]:
                add("generator-sha-mismatch", alias, f"BUILDS={gsha} builds.inc={rec['sha256']}")
            for field in ("image_base", "encrypted", "format", "game", "platform"):
                if field in g and field in j and g[field] != j[field]:
                    add(f"generator-{field}-mismatch", alias, f"BUILDS={g[field]!r} json={j[field]!r}")

    for alias, g in gen.items():
        if g.get("static_only") and alias in inc:
            continue  # reported above
        if (root / "data/addresses" / f"{alias}.json").exists() and alias not in inc \
                and not g.get("static_only"):
            add("table-without-record", alias, "address JSON present, no BuildRecord")

    # Static-only Mac shas the generator vouches for. Any sha-shaped literal in
    # a static_only platform=mac row counts (sha256, slice shas, lists).
    mac_static: set[str] = set()
    for g in gen.values():
        if g.get("static_only") and g.get("platform") == "mac":
            for v in g.values():
                vals = v if isinstance(v, (list, tuple)) else (v.values() if isinstance(v, dict) else [v])
                for x in vals:
                    if isinstance(x, str) and HEX64.match(x):
                        mac_static.add(x)

    def profile_sha(kind: str, pid: str, sha: str) -> None:
        if sha in record_shas:
            return
        if pid.startswith("macos-") and sha in mac_static:
            return
        add("profile-sha-unregistered", f"{kind}:{pid}",
            f"{sha} is neither a BuildRecord nor a static_only Mac entry")

    msize, model = parse_model_profiles((root / "src/api/model_profiles.cpp").read_text())
    if msize is not None and msize != len(model):
        add("profile-count-mismatch", "model", f"std::array<Profile,{msize}> has {len(model)} entries")
    for pid, sha in model.items():
        profile_sha("model", pid, sha)
    for pid, sha in parse_projectiles_profile(
            (root / "src/api/projectiles_profile.cpp").read_text()).items():
        profile_sha("projectiles", pid, sha)
    asize, anim_ids = parse_profile_array(
        (root / "src/api/animation_profiles.cpp").read_text(), "profiles")
    if asize is not None and asize != len(anim_ids):
        add("profile-count-mismatch", "animation", f"std::array<Profile,{asize}> has {len(anim_ids)} entries")
    # animation.cpp binds by sha through model::profile_for, then by id: an
    # animation id with no model twin can never be selected, and a model id
    # without one silently has no animation.
    if set(anim_ids) != set(model):
        add("animation-model-id-mismatch", "animation",
            f"animation-only={sorted(set(anim_ids) - set(model))} "
            f"model-only={sorted(set(model) - set(anim_ids))}")

    for alias in sorted(parse_runtime_aliases((root / "src/runtime/runtime.cpp").read_text())):
        if alias not in inc:
            add("runtime-alias-unknown", alias, "runtime.cpp names a build with no BuildRecord")
    return f


def informational(root: Path) -> list[str]:
    """Not drift: generator rows that emit nothing because no table exists."""
    gen = parse_generator_builds((root / "tools/gen_address_tables.py").read_text())
    return sorted(a for a, g in gen.items() if not g.get("static_only")
                  and not (root / "data/addresses" / f"{a}.json").exists())


# --------------------------------------------------------------------------
# tests


def _copy_tree(dst: Path) -> None:
    for rel in ("src/generated/builds.inc", "tools/gen_address_tables.py",
                "src/api/model_profiles.cpp", "src/api/animation_profiles.cpp",
                "src/api/projectiles_profile.cpp", "src/runtime/runtime.cpp"):
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        (dst / rel).write_text((ROOT / rel).read_text())
    (dst / "data/addresses").mkdir(parents=True, exist_ok=True)
    for p in (ROOT / "data/addresses").glob("*.json"):
        (dst / "data/addresses" / p.name).write_text(p.read_text())


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"fixture anchor {old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1))


class RealTree(unittest.TestCase):
    def test_parsers_see_the_whole_tree(self):
        inc = parse_builds_inc((ROOT / "src/generated/builds.inc").read_text())
        raw = inc.pop("__raw_count__")
        self.assertGreaterEqual(len(inc), 1)
        self.assertEqual(raw, len(inc), "a BuildRecord block did not parse")
        _, model = parse_model_profiles((ROOT / "src/api/model_profiles.cpp").read_text())
        self.assertGreaterEqual(len(model), 1)
        self.assertTrue(parse_runtime_aliases((ROOT / "src/runtime/runtime.cpp").read_text()))

    def test_no_unexpected_drift(self):
        found = check(ROOT)
        unexpected = [x for x in found if x not in KNOWN_DRIFT]
        self.assertEqual(unexpected, [], "new identity drift:\n" +
                         "\n".join(f"  {k} {s}: {d}" for k, s, d in unexpected))

    def test_known_drift_ledger_is_not_stale(self):
        present = set(check(ROOT))
        stale = sorted(set(KNOWN_DRIFT) - present)
        self.assertEqual(stale, [], "drift pinned in KNOWN_DRIFT is gone; remove it")


class SyntheticDrift(unittest.TestCase):
    """Each drift class, injected into a copy of the tree, must be flagged."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _copy_tree(self.root)
        self.baseline = {(k, s) for k, s, _ in check(self.root)}

    def tearDown(self):
        self._tmp.cleanup()

    def new(self) -> set[tuple[str, str]]:
        return {(k, s) for k, s, _ in check(self.root)} - self.baseline

    def test_copy_matches_real_tree(self):
        self.assertEqual(self.baseline, {(k, s) for k, s, _ in check(ROOT)})

    def test_pinned_subject_with_new_value_is_new_drift(self):
        _edit(self.root / "src/api/model_profiles.cpp",
              '"macos-k1-i386", "aa6283', '"macos-k1-i386", "bb6283')
        found = check(self.root)
        self.assertTrue(any(x[1] == "model:macos-k1-i386" and x not in KNOWN_DRIFT for x in found))

    def test_model_profile_sha_not_a_build(self):
        _edit(self.root / "src/api/model_profiles.cpp",
              '"windows-k1-gog", "9c10e045', '"windows-k1-gog", "0c10e045')
        self.assertIn(("profile-sha-unregistered", "model:windows-k1-gog"), self.new())

    def test_projectile_profile_sha_not_a_build(self):
        _edit(self.root / "src/api/projectiles_profile.cpp", '"9c10e045', '"1c10e045')
        self.assertIn(("profile-sha-unregistered", "projectiles:windows-k1-gog-i386"), self.new())

    def test_static_only_mac_sha_clears_profile(self):
        _edit(self.root / "tools/gen_address_tables.py",
              '"symbol_source": "K1__k1_mac_swkotor.app",',
              '"symbol_source": "K1__k1_mac_swkotor.app", "sha256": '
              '"aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032",')
        gone = self.baseline - {(k, s) for k, s, _ in check(self.root)}
        self.assertIn(("profile-sha-unregistered", "model:macos-k1-i386"), gone)

    def test_mac_sha_on_non_static_row_does_not_clear(self):
        _edit(self.root / "tools/gen_address_tables.py",
              '"code_sections": ["__text"], "static_only": True, "reject_cross_placed": True,\n'
              '        "note": "32-bit K1 Mac',
              '"code_sections": ["__text"], "reject_cross_placed": True, "sha256": '
              '"aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032",\n'
              '        "note": "32-bit K1 Mac')
        self.assertIn(("profile-sha-unregistered", "model:macos-k1-i386"),
                      {(k, s) for k, s, _ in check(self.root)})

    def test_json_sha_drift(self):
        p = self.root / "data/addresses/k1_steam_103.json"
        j = json.loads(p.read_text()); j["identity"]["sha256"] = "0" * 64
        p.write_text(json.dumps(j))
        self.assertIn(("sha256-mismatch", "k1_steam_103"), self.new())

    def test_reference_sha_is_not_the_identity(self):
        # k1_steam_103's reference_sha256 is its unpacked twin by design.
        j = json.loads((self.root / "data/addresses/k1_steam_103.json").read_text())
        self.assertNotEqual(j["reference_sha256"], j["identity"]["sha256"])
        self.assertNotIn("sha256-mismatch", {k for k, s in self.baseline if s == "k1_steam_103"})

    def test_known_text_drift(self):
        p = self.root / "data/addresses/k1_gog_103.json"
        j = json.loads(p.read_text()); j["known_text"][0]["sha256"] = "1" * 64
        p.write_text(json.dumps(j))
        self.assertIn(("known_text-mismatch", "k1_gog_103"), self.new())

    def test_image_base_drift(self):
        p = self.root / "data/addresses/k2_gog_aspyr.json"
        j = json.loads(p.read_text()); j["image_base"] = 0x10000
        p.write_text(json.dumps(j))
        self.assertIn(("image_base-mismatch", "k2_gog_aspyr"), self.new())

    def test_missing_table(self):
        (self.root / "data/addresses/k1_gog_103.json").unlink()
        self.assertIn(("record-without-table", "k1_gog_103"), self.new())

    def test_runtime_alias_unknown(self):
        _edit(self.root / "src/runtime/runtime.cpp",
              'build_ == "k2_steam_aspyr"', 'build_ == "k2_steam_aspyr_v2"')
        self.assertIn(("runtime-alias-unknown", "k2_steam_aspyr_v2"), self.new())

    def test_runtime_alias_other_forms(self):
        # Reversed operands, !=, and the build() accessor are the same gate.
        for i, form in enumerate(('"k9_rev_%d" == build_', 'build_ != "k9_ne_%d"',
                                  'build() == "k9_acc_%d"', '"k9_racc_%d" != build()')):
            alias = re.search(r'"(\w+)"', form % i).group(1)
            with self.subTest(form):
                _edit(self.root / "src/runtime/runtime.cpp",
                      'const bool k1_receipt = build_ == "k1_gog_103" &&',
                      'const bool k1_receipt = build_ == "k1_gog_103" && (%s) &&' % (form % i))
                self.assertIn(("runtime-alias-unknown", alias), self.new())

    def test_every_projectile_profile_is_read(self):
        # A second profile, declared a different way, is still checked.
        _edit(self.root / "src/api/projectiles_profile.cpp",
              "const Profile &profile() {",
              'static const Profile q = {\n    "%s", "windows-k9-extra-i386", 0x400000};\n'
              "const Profile &profile() {" % ("5" * 63 + "4"))
        self.assertIn(("profile-sha-unregistered", "projectiles:windows-k9-extra-i386"), self.new())
        self.assertIn("windows-k1-gog-i386", parse_projectiles_profile(
            (self.root / "src/api/projectiles_profile.cpp").read_text()))

    def test_projectile_profile_array_form(self):
        _edit(self.root / "src/api/projectiles_profile.cpp",
              "const Profile &profile() {",
              'static const std::array<Profile, 1> more{{\n  {"windows-k9-arr-i386", "%s"}}};\n'
              "const Profile &profile() {" % ("6" * 63 + "4"))
        self.assertIn(("profile-sha-unregistered", "projectiles:windows-k9-arr-i386"), self.new())

    def test_static_only_emitted(self):
        _edit(self.root / "tools/gen_address_tables.py",
              '"code_sections": [".text"],\n    },\n    "k2_steam_linux"',
              '"code_sections": [".text"], "static_only": True,\n    },\n    "k2_steam_linux"')
        self.assertIn(("static-only-emitted", "k1_gog_103"), self.new())

    def test_record_missing_from_generator(self):
        _edit(self.root / "tools/gen_address_tables.py", '"k2_gog_aspyr": {', '"k2_gog_aspyr_old": {')
        self.assertIn(("record-not-in-generator", "k2_gog_aspyr"), self.new())

    def test_animation_profile_without_model_twin(self):
        _edit(self.root / "src/api/animation_profiles.cpp", '{"windows-k1-gog",', '{"windows-k2-gog",')
        self.assertIn(("animation-model-id-mismatch", "animation"), self.new())

    def test_profile_array_count(self):
        _edit(self.root / "src/api/model_profiles.cpp",
              "const std::array<Profile,4>& profiles() {", "const std::array<Profile,5>& profiles() {")
        self.assertIn(("profile-count-mismatch", "model"), self.new())

    def test_unparsed_build_record(self):
        _edit(self.root / "src/generated/builds.inc", "Format::Pe32, 0x00400000, false,\n        0, \"\", \"\",\n        kText_k1_gog_103",
              "Format::Pe32, 0x00400000, maybe,\n        0, \"\", \"\",\n        kText_k1_gog_103")
        self.assertIn(("builds-inc-unparsed", "builds.inc"), self.new())


def report() -> int:
    found = check(ROOT)
    for k, s, d in found:
        tag = f"KNOWN ({KNOWN_DRIFT[(k, s, d)]})" if (k, s, d) in KNOWN_DRIFT else "NEW"
        print(f"{tag:>8} {k} {s}: {d}")
    for a in informational(ROOT):
        print(f"    INFO generator row {a}: no address JSON, emits no BuildRecord")
    return 1 if any(x not in KNOWN_DRIFT for x in found) else 0


if __name__ == "__main__":
    if "--report" in sys.argv:
        sys.exit(report())
    unittest.main()
