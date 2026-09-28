#!/usr/bin/env python3
"""Dry-run tests for the creative harness package builder.

Every package is built inside a temporary directory and deleted afterwards.
Nothing is published. No game, Wine, display, FFmpeg or lock file is used.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'scripts/harness'))
import package_creative_harness as B  # noqa: E402
from kpharness import gamescope_snapshot as S  # noqa: E402

TOP = 'kotorphasor-creative-harness/'
MODULES = {
    '__init__.py': '',
    'creative.py': 'from .creative_accept import accept\nfrom . import shared\n',
    'gamescope_snapshot.py': 'import json\n',
    'creative_accept.py': 'from .shared import helper\n',
    'creative_export.py': 'from .creative_accept import accept\n',
    'capture_diagnostic.py': 'from .creative import run\n',
    'shared.py': 'def helper():\n    return 1\n',
    'commit_inputs.py': 'from .creative_accept import accept\n',
    'export_verify.py': 'from .commit_inputs import x\nfrom .creative_accept import accept\n',
    'playback.py': 'UNFINISHED = True\n',
    'pioneer.py': 'UNFINISHED = True\n',
}
ADDRESS = {'build': 'k1_gog_103', 'reference_image': {'sha256': '9c10'},
           'functions': {'GetFirstPC': {'va': '0x1', 'source_path': '/home/someone/corpus/x.txt'}}}


def write(root: Path, rel: str, data) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)
    return path


def fake_tree(root: Path) -> Path:
    for name, text in MODULES.items():
        write(root, 'scripts/harness/kpharness/' + name, text)
    write(root, 'scripts/harness/kpharness/__pycache__/creative.cpython-312.pyc', b'\0cache')
    write(root, 'tools/kpdiscover.py', 'import os\n')
    write(root, 'tools/creative_host_check.py', 'import os\n')
    write(root, 'tools/tests/examples/manifest.json', json.dumps({'schema': 2, 'examples': []}))
    write(root, 'data/app_signatures.toml', '[k1]\n')
    write(root, 'data/addresses/k1_gog_103.json', json.dumps(ADDRESS))
    write(root, 'data/addresses/k2_gog_aspyr.json', json.dumps({'build': 'k2'}))
    write(root, 'data/adjudication/x.json', '{}')
    write(root, 'LICENSE', 'license text\n')
    write(root, 'ATTRIBUTION.md', 'attribution\n')
    write(root, 'docs/user/creative-harness.md', '# Run the creative harness\n')
    write(root, 'docs/creative-runner.md', '# Creative route runner\n')
    write(root, 'scripts/examples/cursed/10_rancor.lua', '-- example\n')
    write(root, 'scripts/examples/cursed/README.md', 'Cursed pack\n')
    write(root, 'scripts/examples/probe/00_probe.lua', '-- probe\n')
    write(root, 'scripts/harness/scenarios/cursed/10_rancor.toml', 'name = "rancor"\n')
    write(root, 'scripts/harness/scenarios/cursed/50_retired.toml', 'name = "retired"\n')
    # Planted items inside walked folders: each must be excluded with a deny reason.
    write(root, 'scripts/examples/cursed/party.sav', b'SAV')
    write(root, 'scripts/examples/cursed/clip.gif', b'GIF89a')
    write(root, 'scripts/examples/cursed/continuous.mp4', b'mp4')
    write(root, 'scripts/examples/cursed/accepted-media-x/export.json', '{}')
    write(root, 'scripts/examples/probe/creative-run.json', '{}')
    return root


PLANTED = {
    'scripts/examples/cursed/party.sav': 'retail',
    'scripts/examples/cursed/clip.gif': 'media',
    'scripts/examples/cursed/continuous.mp4': 'run evidence',
    'scripts/examples/cursed/accepted-media-x/export.json': 'run evidence',
    'scripts/examples/probe/creative-run.json': 'run evidence',
    'scripts/harness/kpharness/__pycache__/creative.cpython-312.pyc': 'cache',
}


def provenance_for(root: Path, path: Path, *, drop: str | None = None) -> Path:
    selected = B.select_files(root)['selected']
    overlay = {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
               for rel in selected if rel != drop}
    path.write_text(json.dumps({'base_commit': None, 'overlay_sha256': overlay}))
    return path


class BuilderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.src = fake_tree(self.tmp / 'src')
        self.prov = provenance_for(self.src, self.tmp / 'source-provenance.json')

    def build(self, out_name='out', **kwargs):
        kwargs.setdefault('provenance', self.prov)
        return B.build(self.src, self.tmp / out_name, **kwargs)

    def names(self, result):
        with zipfile.ZipFile(result['zip']) as archive:
            return set(archive.namelist())

    def test_zip_excludes_every_planted_item_with_a_deny_reason(self):
        result = self.build()
        names = self.names(result)
        receipt = json.loads((self.tmp / 'out/package/packaging-receipt.json').read_text())
        reasons = {item['path']: item['reason'] for item in receipt['exclusions']}
        for rel, reason in PLANTED.items():
            with self.subTest(rel=rel):
                self.assertNotIn(TOP + rel, names)
                self.assertIn(reason, reasons.get(rel, ''))
        for rel in ('data/adjudication/x.json', 'data/addresses/k2_gog_aspyr.json',
                    'scripts/harness/scenarios/cursed/50_retired.toml'):
            self.assertNotIn(TOP + rel, names)
        self.assertIn(TOP + 'scripts/harness/scenarios/cursed/10_rancor.toml', names)
        self.assertEqual(reasons['scripts/harness/scenarios/cursed/50_retired.toml'],
                         'retired: no matching public example')
        self.assertTrue(B.deny_reason('data/adjudication/x.json'))
        self.assertTrue(B.deny_reason('Saves/000001 - Quick/savegame.sav'))

    def test_symlink_in_source_refuses_build(self):
        (self.src / 'scripts/examples/cursed/linked.lua').symlink_to(self.src / 'scripts/examples/cursed/10_rancor.lua')
        with self.assertRaisesRegex(ValueError, 'symlink.*linked.lua'):
            self.build()
        self.assertFalse((self.tmp / 'out').exists())

    def test_absolute_path_in_packaged_text_fails_naming_the_file(self):
        write(self.src, 'scripts/harness/kpharness/shared.py',
              "DEFAULT = '/home/someone/bin/ffprobe'\n")
        self.prov = provenance_for(self.src, self.tmp / 'p2.json')
        with self.assertRaisesRegex(ValueError, r'scripts/harness/kpharness/shared\.py:1'):
            self.build()
        self.assertFalse((self.tmp / 'out').exists())
        report = B.build(self.src, None, dry_run=True)
        self.assertEqual([hit['path'] for hit in report['path_scan']], ['scripts/harness/kpharness/shared.py'])

    def test_manifest_rehashes_from_zip_and_crc_passes(self):
        result = self.build()
        manifest = json.loads((self.tmp / 'out/package/manifest.json').read_text())
        with zipfile.ZipFile(result['zip']) as archive:
            self.assertIsNone(archive.testzip())
            for rel, digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(TOP + rel)).hexdigest(), digest, rel)
            self.assertEqual({name[len(TOP):] for name in archive.namelist()},
                             set(manifest['files']) | {'manifest.json'})
        verification = json.loads((self.tmp / 'out/verification.json').read_text())
        self.assertEqual(verification['zip_crc'], 'PASS')
        self.assertEqual(verification['manifest_hashes'], 'PASS')
        zip_sha = hashlib.sha256(Path(result['zip']).read_bytes()).hexdigest()
        self.assertEqual((self.tmp / 'out/zip-sha256.txt').read_text().split()[0], zip_sha)

    def test_existing_out_refuses(self):
        self.build()
        before = sorted(p.relative_to(self.tmp) for p in (self.tmp / 'out').rglob('*'))
        with self.assertRaisesRegex(ValueError, 'exists'):
            self.build()
        self.assertEqual(sorted(p.relative_to(self.tmp) for p in (self.tmp / 'out').rglob('*')), before)

    def test_module_set_equals_runtime_closure(self):
        expected = {p.relative_to(self.src).as_posix()
                    for p in S.runtime_module_paths(self.src / 'scripts/harness', B.ENTRIES)}
        selected = {rel for rel in B.select_files(self.src)['selected']
                    if rel.startswith('scripts/harness/kpharness/')}
        self.assertEqual(selected, expected)
        self.assertNotIn('scripts/harness/kpharness/playback.py', selected)
        self.assertNotIn('scripts/harness/kpharness/pioneer.py', selected)

    def test_closure_that_reaches_unfinished_modules_stops(self):
        write(self.src, 'scripts/harness/kpharness/shared.py', 'from . import playback\n')
        with self.assertRaisesRegex(ValueError, 'playback'):
            B.select_files(self.src)

    def test_extracted_package_has_no_git_and_lock_falls_back_to_tree(self):
        result = self.build()
        extracted = self.tmp / 'extracted'
        with zipfile.ZipFile(result['zip']) as archive:
            archive.extractall(extracted)
        tree = extracted / TOP.rstrip('/')
        self.assertFalse((tree / '.git').exists())
        from kpharness import creative as C  # read-only import; creates no lock
        self.assertEqual(C.shared_lock_path(tree), tree / 'tmp/harness-locks/live-game.lock')
        self.assertFalse((tree / 'tmp').exists())

    def test_extracted_package_snapshots_and_matches_recorded_closure(self):
        result = self.build()
        extracted = self.tmp / 'extracted'
        with zipfile.ZipFile(result['zip']) as archive:
            archive.extractall(extracted)
        # Default entries: exactly what `gamescope_snapshot create` freezes for a user run.
        snapshot = S.create_snapshot(extracted / TOP / 'scripts/harness', self.tmp / 'snap')
        manifest = json.loads((snapshot / S.MANIFEST).read_text())
        receipt = json.loads((self.tmp / 'out/package/packaging-receipt.json').read_text())
        self.assertEqual(B.closure_files_sha256(manifest['files']), receipt['snapshot_files_sha256'])
        self.assertEqual(manifest['files'], receipt['snapshot_files'])

    def test_sanitization_removes_private_keys_and_records_it(self):
        self.build()
        packaged = json.loads((self.tmp / 'out/package/data/addresses/k1_gog_103.json').read_text())
        self.assertNotIn('reference_image', packaged)
        self.assertNotIn('source_path', packaged['functions']['GetFirstPC'])
        receipt = json.loads((self.tmp / 'out/package/packaging-receipt.json').read_text())
        self.assertIn({'path': 'data/addresses/k1_gog_103.json',
                       'removed_metadata_keys': ['reference_image', 'source_path']}, receipt['sanitizations'])

    def test_provenance_must_cover_every_file(self):
        rel = 'scripts/harness/kpharness/shared.py'
        with self.subTest('uncovered file without git'):
            prov = provenance_for(self.src, self.tmp / 'short.json', drop=rel)
            with self.assertRaisesRegex(ValueError, 'unbound.*shared.py'):
                self.build(provenance=prov)
        with self.subTest('changed file'):
            write(self.src, rel, 'def helper():\n    return 2\n')
            with self.assertRaisesRegex(ValueError, 'provenance mismatch.*shared.py'):
                self.build(out_name='out2')
        with self.subTest('no provenance'):
            with self.assertRaisesRegex(ValueError, 'provenance'):
                self.build(out_name='out3', provenance=None)
        self.assertFalse(any((self.tmp / name).exists() for name in ('out', 'out2', 'out3')))

    def test_receipt_holds_no_absolute_source_path(self):
        self.build()
        for name in ('packaging-receipt.json', 'manifest.json', 'source-provenance.json'):
            text = (self.tmp / 'out/package' / name).read_text()
            self.assertNotIn(str(self.tmp), text, name)
        self.assertNotIn(str(self.tmp), (self.tmp / 'out/verification.json').read_text())

    def test_dry_run_writes_nothing(self):
        before = sorted(self.tmp.rglob('*'))
        report = B.build(self.src, self.tmp / 'dry', dry_run=True)
        self.assertEqual(sorted(self.tmp.rglob('*')), before)
        self.assertTrue(report['dry_run'])
        self.assertIn('scripts/harness/kpharness/creative.py', report['selected'])


class RealTreeDryRun(unittest.TestCase):
    def test_real_closure_excludes_unfinished_modules(self):
        selected = B.select_files(ROOT)['selected']
        for name in ('playback.py', 'pioneer.py', 'cli.py'):
            self.assertNotIn('scripts/harness/kpharness/' + name, selected)


if __name__ == '__main__':
    unittest.main()
