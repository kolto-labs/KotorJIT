#!/usr/bin/env python3
"""Dry-run tests for the creative harness package builder.

Every package is built inside a temporary directory and deleted afterwards.
Nothing is published. No game, Wine, display, FFmpeg or lock file is used.
"""
import contextlib
import hashlib
import io
import json
import os
import struct
import sys
import tarfile
import tempfile
import unittest
import zipfile
import zlib
from unittest import mock
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


class TreeCase(unittest.TestCase):
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


class BuilderTests(TreeCase):
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

    def test_files_equal_to_git_base_are_bound_without_overlay(self):
        import subprocess
        git = ['git', '-C', str(self.src), '-c', 'user.name=t', '-c', 'user.email=t@t']
        subprocess.run(['git', 'init', '-q', str(self.src)], check=True)
        subprocess.run(git + ['add', '-A'], check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'base'], check=True)
        prov = self.tmp / 'base.json'
        prov.write_text(json.dumps({'base_commit': 'HEAD', 'overlay_sha256': {}}))
        report = B.build(self.src, None, provenance=prov, dry_run=True)
        self.assertEqual(report['provenance']['unbound'], [])
        self.assertEqual(report['provenance']['bound_by_base'], report['selected'])
        result = self.build(provenance=prov)
        self.assertEqual(result['manifest_hashes'], 'PASS')
        rel = 'scripts/harness/kpharness/shared.py'
        write(self.src, rel, 'def helper():\n    return 3\n')
        report = B.build(self.src, None, provenance=prov, dry_run=True)
        self.assertEqual(report['provenance']['unbound'], [rel])
        with self.assertRaisesRegex(ValueError, 'unbound.*shared.py'):
            self.build(out_name='out2', provenance=prov)

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


class AdversarialTests(TreeCase):
    """Red tests from the review probes (adversarial.py and race.py). Each must refuse or exclude."""

    CURSED = 'scripts/examples/cursed/'

    def refuse(self, pattern, **kwargs):
        with self.assertRaisesRegex(ValueError, pattern):
            self.build(**kwargs)
        self.assertFalse((self.tmp / 'out').exists())

    def outside(self) -> Path:
        path = self.tmp / 'outside'
        path.mkdir(exist_ok=True)
        return path

    def test_i1_symlinked_parent_of_a_fixed_file_refuses(self):
        user = self.outside() / 'user'
        user.mkdir()
        (user / 'creative-harness.md').write_text('# Secret outside doc\n')
        import shutil
        shutil.rmtree(self.src / 'docs/user')
        (self.src / 'docs/user').symlink_to(user)
        self.refuse('symlink.*docs/user')

    def test_i1_symlinked_parent_of_a_walked_folder_refuses(self):
        import shutil
        moved = self.outside() / 'examples'
        shutil.move(str(self.src / 'scripts/examples'), str(moved))
        (moved / 'cursed/outside_secret.lua').write_text('-- outside tree\n')
        (self.src / 'scripts/examples').symlink_to(moved)
        self.refuse('symlink.*scripts/examples')

    def test_i1_symlinked_data_folder_refuses(self):
        import shutil
        moved = self.outside() / 'data'
        shutil.move(str(self.src / 'data'), str(moved))
        (self.src / 'data').symlink_to(moved)
        self.refuse('symlink.*data')

    def test_m1_hard_link_to_an_outside_file_refuses(self):
        private = self.outside() / 'private.txt'
        private.write_text('-- PRIVATE hardlinked bytes\n')
        os.link(private, self.src / (self.CURSED + 'hl.lua'))
        self.prov = provenance_for(self.src, self.tmp / 'p2.json')
        self.refuse('hard link.*hl.lua')

    def test_i2_private_folder_names_are_denied_at_any_depth(self):
        for rel in ('scripts/examples/cursed/.superpowers/sdd/n.lua',
                    'scripts/examples/cursed/data/adjudication/n.lua',
                    'scripts/examples/cursed/data/research/n.lua',
                    'scripts/examples/cursed/Saves/n.lua',
                    'scripts/examples/cursed/.worktrees/x/n.lua',
                    'scripts/examples/cursed/kp-live-20260922/n.lua'):
            with self.subTest(rel=rel):
                self.assertIn('private', B.deny_reason(rel) or '')
                write(self.src, rel, '-- nested private\n')
        # Ruling (2): tmp/ and runs/ are private at the repository root only. Nested ones are still
        # left out, by the flat-folder and closure rules.
        for rel in ('tmp/n.lua', 'runs/20260926-234927/n.lua', 'TMP/n.lua'):
            with self.subTest(rel=rel):
                self.assertIn('private', B.deny_reason(rel) or '')
        for rel in ('scripts/examples/cursed/tmp/n.lua', 'scripts/examples/cursed/runs/n.lua',
                    'scripts/harness/kpharness/tmp/n.py'):
            write(self.src, rel, '-- nested\n')
        result = self.build()
        leaked = [name for name in self.names(result)
                  if any(part in name for part in ('.superpowers', 'adjudication', 'research', '/tmp/',
                                                   '/runs/', 'Saves', '.worktrees', 'kp-live'))]
        self.assertEqual(leaked, [])

    def test_i2_receipt_does_not_name_private_folders(self):
        write(self.src, 'scripts/examples/cursed/.superpowers/sdd/n.lua', '-- nested private\n')
        write(self.src, 'scripts/examples/cursed/kp-live-20260922/n.lua', '-- nested private\n')
        result = self.build()
        with zipfile.ZipFile(result['zip']) as archive:
            for name in archive.namelist():
                data = archive.read(name)
                for word in (b'.superpowers', b'kp-live'):
                    self.assertNotIn(word, data, name)

    def test_i2_example_and_scenario_folders_must_be_flat(self):
        write(self.src, self.CURSED + 'sub/x.lua', '-- nested\n')
        write(self.src, 'scripts/harness/scenarios/cursed/sub/10_rancor.toml', 'name = "x"\n')
        result = self.build()
        names = self.names(result)
        self.assertNotIn(TOP + self.CURSED + 'sub/x.lua', names)
        self.assertNotIn(TOP + 'scripts/harness/scenarios/cursed/sub/10_rancor.toml', names)

    def test_i3_png_bytes_under_a_lua_name_refuse(self):
        write(self.src, self.CURSED + 'evil.lua',
              b'\x89PNG\r\n\x1a\n' + b'\0' * 20 + b'/home/secretuser/ ' + b'\xff\xfe')
        self.prov = provenance_for(self.src, self.tmp / 'p2.json')
        self.refuse('evil.lua')

    def test_i3_utf16_text_refuses(self):
        write(self.src, self.CURSED + 'u16.lua', '-- /home/secretuser/x\n'.encode('utf-16'))
        self.prov = provenance_for(self.src, self.tmp / 'p2.json')
        self.refuse('UTF-8.*u16.lua')

    def test_i3_magic_bytes_refuse_even_when_valid_utf8(self):
        cases = {'gif.lua': b'GIF89a-- looks like text\n', 'elf.lua': b'\x7fELF\n-- text\n',
                 'gff.lua': b'UTC V3.2 -- text\n', 'erf.toml': b'ERF V1.0\n', 'zip.lua': b'PK\x03\x04--\n',
                 'ogg.lua': b'OggS --\n', 'pe.lua': b'MZ\x90\x00\x03\x00' + b'\x00' * 58,
                 'bom_png.lua': b'\xef\xbb\xbf\x89PNG\r\n\x1a\n', 'nul.lua': b'-- a\x00b\n'}
        for name, data in cases.items():
            with self.subTest(name=name):
                self.assertTrue(B.content_problems(self.CURSED + name, data), name)
        write(self.src, self.CURSED + 'gif.lua', cases['gif.lua'])
        self.prov = provenance_for(self.src, self.tmp / 'p2.json')
        self.refuse('gif.lua')

    def test_i3_privacy_markers_refuse(self):
        lines = {'user.lua': '-- by zqxtester\n', 'live.lua': '-- see kp-live-20260922\n',
                 'sdd.lua': '-- .superpowers/sdd/plan\n', 'book.lua': '-- MyBook drive\n',
                 'wt.lua': '-- .worktrees/x\n', 'win.lua': '-- C:\\Users\\bob\n',
                 'root.lua': '-- /root/x\n', 'runid.lua': '-- 20260922-141500-0a1b2c3d\n',
                 'mac.lua': '-- /Users/bob\n'}
        env = {'USER': 'zqxtester', 'HOME': '/home/zqxtester', 'PATH': os.environ.get('PATH', '')}
        markers = B.privacy_markers(env)
        for name, text in lines.items():
            with self.subTest(name=name):
                self.assertTrue(B.path_scan(self.CURSED + name, text.encode(), markers), name)
        self.assertTrue(B.path_scan(self.CURSED + 'r.lua', b'-- runs/20260926-234927\n', markers))
        self.assertEqual(B.path_scan(self.CURSED + 'ok.lua', b'-- ~/kp-runs and creative-runner.md\n',
                                     markers), [])
        write(self.src, self.CURSED + 'user.lua', lines['user.lua'])
        self.prov = provenance_for(self.src, self.tmp / 'p2.json')
        from unittest import mock
        with mock.patch.dict(os.environ, env):
            self.refuse('user.lua:1')

    def test_i3_common_or_short_usernames_are_not_markers(self):
        for user in ('root', 'runner', 'ubuntu', 'me'):
            markers = B.privacy_markers({'USER': user, 'HOME': '/home/' + user})
            self.assertEqual(B.path_scan('x.lua', b'-- creative-runner root ubuntu me\n', markers), [], user)

    def test_m2_backslash_in_a_name_refuses(self):
        write(self.src, self.CURSED + '..\\..\\..\\..\\evil.lua', '-- slip\n')
        self.prov = provenance_for(self.src, self.tmp / 'p2.json')
        self.refuse('unsafe name')

    def test_i4_edit_reverted_inside_the_window_refuses(self):
        # race.py: overlay binds the original; staging sees a tampered file; the file is
        # restored before any second read. The staged bytes must be what gets bound.
        from unittest import mock
        target = self.CURSED + '10_rancor.lua'
        original = (self.src / target).read_bytes()
        (self.src / target).write_bytes(b'-- TAMPERED in window\n')
        real = B.clean_bytes

        def restore(rel, data):
            if rel == target:
                (self.src / target).write_bytes(original)
            return real(rel, data)
        with mock.patch.object(B, 'clean_bytes', side_effect=restore):
            self.refuse('provenance mismatch.*10_rancor.lua')

    def test_i4_source_changed_after_staging_refuses(self):
        from unittest import mock
        target = self.CURSED + '10_rancor.lua'
        real = B.clean_bytes

        def change(rel, data):
            if rel == target:
                (self.src / target).write_bytes(b'-- changed after staging\n')
            return real(rel, data)
        with mock.patch.object(B, 'clean_bytes', side_effect=change):
            self.refuse('changed during the build.*10_rancor.lua')

    def test_i4_zip_holds_exactly_the_bound_bytes(self):
        result = self.build()
        overlay = json.loads(self.prov.read_text())['overlay_sha256']
        with zipfile.ZipFile(result['zip']) as archive:
            for rel, digest in overlay.items():
                if rel.endswith('.json'):
                    continue  # sanitized JSON is bound before cleaning
                self.assertEqual(hashlib.sha256(archive.read(TOP + rel)).hexdigest(), digest, rel)
        self.assertEqual(hashlib.sha256(Path(result['zip']).read_bytes()).hexdigest(), result['zip_sha256'])

    def test_existing_out_refuses_before_any_work(self):
        (self.tmp / 'out').mkdir()
        from unittest import mock
        with mock.patch.object(B, 'select_files', side_effect=AssertionError('did work')):
            with self.assertRaisesRegex(ValueError, 'exists'):
                self.build()


class ReleaseZipScanTests(unittest.TestCase):
    """Tests for the read-only release ZIP scanner (tools/scan_release_zip.py)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        import scan_release_zip
        self.Z = scan_release_zip

    def make(self, entries, name='t.zip'):
        path = self.tmp / name
        with zipfile.ZipFile(path, 'w') as archive:
            for entry, data, mode in entries:
                info = zipfile.ZipInfo(entry)
                info.external_attr = mode << 16
                archive.writestr(info, data)
        return path

    def kinds(self, report):
        return {(item['entry'], item['kind']) for item in report['findings']}

    def test_clean_zip_has_no_findings_and_is_not_changed(self):
        path = self.make([('top/a.lua', b'-- ok\n', 0o100644), ('top/README.md', b'# ok\n', 0o100644)])
        before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        report = self.Z.scan(path, markers=('zqxtester',))
        self.assertEqual(report['findings'], [])
        self.assertTrue(report['ok'])
        self.assertEqual((hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns), before)

    def test_each_problem_is_reported(self):
        import io as _io
        import tarfile
        buffer = _io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
            link = tarfile.TarInfo('src/link.lua'); link.type = tarfile.SYMTYPE; link.linkname = '/etc/passwd'
            tar.addfile(link)
            data = b'-- zqxtester\n'
            member = tarfile.TarInfo('src/.superpowers/n.lua'); member.size = len(data)
            tar.addfile(member, _io.BytesIO(data))
        path = self.make([
            ('top/ln', b'/etc/passwd', 0o120777),
            ('top/..\\evil.lua', b'--\n', 0o100644),
            ('top/data/adjudication/x.json', b'{}', 0o100644),
            ('top/pic.lua', b'\x89PNG\r\n\x1a\n\0', 0o100644),
            ('top/u.lua', '-- x\n'.encode('utf-16'), 0o100644),
            ('top/m.md', b'see /home/zqxtester/x\n', 0o100644),
            ('top/source.tar.gz', buffer.getvalue(), 0o100644),
        ])
        kinds = self.kinds(self.Z.scan(path, markers=('zqxtester',)))
        for expected in (('top/ln', 'symlink'), ('top/..\\evil.lua', 'unsafe name'),
                         ('top/data/adjudication/x.json', 'private folder'),
                         ('top/pic.lua', 'magic'), ('top/u.lua', 'not UTF-8'), ('top/m.md', 'marker'),
                         ('top/source.tar.gz!src/link.lua', 'symlink'),
                         ('top/source.tar.gz!src/.superpowers/n.lua', 'private folder'),
                         ('top/source.tar.gz!src/.superpowers/n.lua', 'marker')):
            self.assertIn(expected, kinds)

    def test_allow_list_marks_expected_binaries(self):
        path = self.make([('top/k.dll', b'MZ\x90\x00' + b'\0' * 60, 0o100755)])
        report = self.Z.scan(path, markers=(), allow=('*.dll',))
        self.assertTrue(report['ok'])
        self.assertEqual([item['kind'] for item in report['expected']], ['magic'])


class HardeningScanTests(unittest.TestCase):
    """Red tests for the release scanner hardening (triage M1, M4; re-review R-1, R-3, R-6, scanner list)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        import scan_release_zip
        self.Z = scan_release_zip

    def make(self, entries, name='t.zip', comment=b'', prefix=b''):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.comment = comment
            for entry in entries:
                info = zipfile.ZipInfo(entry[0])
                info.external_attr = 0o100644 << 16
                if len(entry) > 2:
                    info.comment = entry[2].get('comment', b'')
                    info.extra = entry[2].get('extra', b'')
                archive.writestr(info, entry[1])
        path = self.tmp / name
        path.write_bytes(prefix + buffer.getvalue())
        return path

    def kinds(self, report, key='findings'):
        return {(item['entry'], item['kind']) for item in report[key]}

    def tar(self, members):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for name, data, owner in members:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.uname, info.gname, info.uid, info.gid = owner
                archive.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    def test_m1_tar_owner_names_and_ids_are_findings(self):
        data = self.tar([('source/a.lua', b'-- a\n', ('zqxtester', 'ZqxTester', 1000, 1000)),
                         ('source/b.lua', b'-- b\n', ('', '', 0, 0)),
                         ('source/c.lua', b'-- c\n', ('', '', 1000, 0))])
        report = self.Z.scan(self.make([('top/source.tar.gz', data)]), markers=('zqxtester',))
        owners = {item['entry']: item['detail'] for item in report['findings'] if item['kind'] == 'tar owner'}
        self.assertEqual(set(owners), {'top/source.tar.gz!source/a.lua', 'top/source.tar.gz!source/c.lua'})
        self.assertIn('build user', owners['top/source.tar.gz!source/a.lua'])
        self.assertNotIn('zqxtester', json.dumps(report).lower())  # the name is never repeated
        self.assertFalse(report['ok'])

    def test_entry_names_are_scanned_for_markers(self):
        path = self.make([('top/zqxtester-notes.md', b'ok\n'), ('top/20260927-102706-0523fa70/report.md', b'ok\n'),
                          ('top/kp-live-20260922.md', b'ok\n'), ('top/home/zqxtester/x.md', b'ok\n'),
                          ('top/fine.md', b'ok\n')])
        markers = self.Z.privacy_markers({'USER': 'zqxtester', 'HOME': '/home/zqxtester'})
        kinds = self.kinds(self.Z.scan(path, markers=markers))
        for entry in ('top/zqxtester-notes.md', 'top/20260927-102706-0523fa70/report.md',
                      'top/kp-live-20260922.md', 'top/home/zqxtester/x.md'):
            self.assertIn((entry, 'marker in name'), kinds)
        self.assertNotIn(('top/fine.md', 'marker in name'), kinds)

    def test_zip_comment_entry_comment_extra_field_and_prefix_are_scanned(self):
        extra = struct.pack('<HH', 0xCAFE, 17) + b'/home/zqxtester/x'
        path = self.make([('top/a.md', b'ok\n', {'comment': b'/home/zqxtester/c', 'extra': extra})],
                         comment=b'built in /home/zqxtester', prefix=b'/home/zqxtester/prefix\n')
        report = self.Z.scan(path, markers=('zqxtester',))
        kinds = {item['kind'] for item in report['findings']}
        for kind in ('zip comment', 'entry comment', 'extra field', 'prefix bytes'):
            self.assertIn(kind, kinds)

    def test_zip_unix_owner_extra_field_is_a_finding(self):
        extra = struct.pack('<HHBB', 0x7875, 11, 1, 4) + struct.pack('<I', 1000) + b'\x04' + struct.pack('<I', 1000)
        report = self.Z.scan(self.make([('top/a.md', b'ok\n', {'extra': extra})]), markers=())
        self.assertIn(('top/a.md', 'zip owner'), self.kinds(report))

    def test_r1_markers_ignore_case_and_treat_underscore_as_a_boundary(self):
        markers = self.Z.privacy_markers({'USER': 'zqxtester', 'HOME': '/home/zqxtester'})
        for text in (b'-- ZQXTESTER\n', b'-- ZqxTester\n', b'-- prefix_zqxtester_suffix\n', b'-- KP-LIVE x\n',
                     b'-- /Volumes/disk\n', b'-- /media/bob/disk\n', b'-- .SuperPowers/x\n', b'-- mybook\n'):
            with self.subTest(text=text):
                self.assertTrue(self.Z.path_scan('x.lua', text, markers), text)
        self.assertEqual(self.Z.path_scan('x.lua', b'-- zqxtesters and azqxtester\n', markers), [])
        # Linux paths are case-sensitive: ImGui's "PageDown/Home/End" comment is not a home folder.
        self.assertEqual(self.Z.path_scan('imgui.cpp', b'// Handle PageUp/PageDown/Home/End keys\n', markers), [])
        self.assertTrue(self.Z.path_scan('x.md', b'see /users/bob and c:\\users\\bob\n', markers))

    def test_r1_git_identities_are_markers_at_scan_time(self):
        config = {'user.name': 'Qwv Plonk', 'user.email': 'qwvplonk@example.org', 'github.user': 'plonkqwv'}
        with mock.patch.object(self.Z, '_git_config', side_effect=lambda key: config.get(key, '')):
            markers = self.Z.privacy_markers()
        for text in (b'by qwv plonk\n', b'mail QWVPLONK@example.org\n', b'-- qwvplonk\n', b'github.com/PlonkQwv\n'):
            with self.subTest(text=text):
                self.assertTrue(self.Z.path_scan('x.md', text, markers), text)

    def test_run_id_is_narrowed_to_runs_folder_and_hex_suffix(self):
        self.assertEqual(self.Z.path_scan('x.py', b'# exact 20260910-095338 failure mode.\n', ()), [])
        self.assertEqual(self.Z.path_scan('x.md', b'Built 20260927-102706 on CI\n', ()), [])
        self.assertTrue(self.Z.path_scan('x.toml', b'# tmp/k1_harness/runs/20260915-071620\n', ()))
        self.assertTrue(self.Z.path_scan('x.md', b'see 20260927-102706-0523fa70\n', ()))

    def test_ruling_private_parts(self):
        P = self.Z.private_part
        self.assertIsNone(P('docs/research/native-animation-sites.md'))
        self.assertEqual(P('data/research/phasor_structs.json'), 'research')
        self.assertEqual(P('Data/Research/x.json'), 'Research')
        self.assertIsNone(P('scripts/tmp/x.lua'))
        self.assertEqual(P('tmp/x.lua'), 'tmp')
        self.assertEqual(P('runs/x/y.json'), 'runs')
        self.assertEqual(P('top/tmp/x', root_depth=1), 'tmp')
        self.assertIsNone(P('top/docs/research/x.md', root_depth=1))
        self.assertEqual(P('a/.SuperPowers/x'), '.SuperPowers')
        self.assertEqual(P('a/KP-Live-x/y'), 'KP-Live-x')

    def test_ruling_codecaves_and_events_draft_are_findings(self):
        report = self.Z.scan(self.make([('top/data/codecaves.toml', b'x = 1\n'),
                                        ('top/data/events.draft.toml', b'x = 1\n'),
                                        ('top/docs/research/ok.md', b'ok\n')]), markers=())
        kinds = self.kinds(report)
        self.assertIn(('top/data/codecaves.toml', 'excluded file'), kinds)
        self.assertIn(('top/data/events.draft.toml', 'excluded file'), kinds)
        self.assertEqual([item for item in report['findings'] if 'research' in item['entry']], [])

    def test_encrypted_entry_is_reported_not_raised(self):
        path = self.make([('top/secret.md', b'hidden /home/zqxtester\n')])
        raw = bytearray(path.read_bytes())
        for signature, offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
            at = raw.index(signature)
            raw[at + offset] |= 0x01
        path.write_bytes(bytes(raw))
        report = self.Z.scan(path, markers=('zqxtester',))
        self.assertIn(('top/secret.md', 'encrypted'), self.kinds(report))
        self.assertFalse(report['ok'])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = self.Z.main([str(path)])
        self.assertEqual(status, 1)
        self.assertFalse(json.loads(out.getvalue())['ok'])

    def test_unknown_compressed_type_under_allow_is_unscanned_not_trusted(self):
        seven = b'7z\xbc\xaf\x27\x1c\x00\x04' + b'\x00' * 24
        report = self.Z.scan(self.make([('top/x.7z', seven), ('top/y.rar', b'Rar!\x1a\x07\x00' + b'\x00' * 8)]),
                             markers=(), allow=('*.7z', '*.rar'))
        kinds = self.kinds(report)
        self.assertIn(('top/x.7z', 'unscanned archive'), kinds)
        self.assertIn(('top/y.rar', 'unscanned archive'), kinds)
        self.assertFalse(report['ok'])

    def test_xz_and_single_gzip_streams_are_opened_and_scanned(self):
        import gzip
        import lzma
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:xz') as archive:
            info = tarfile.TarInfo('src/n.md'); data = b'/home/zqxtester/x\n'; info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        report = self.Z.scan(self.make([('top/s.tar.xz', buffer.getvalue()),
                                        ('top/n.md.gz', gzip.compress(b'see /home/zqxtester\n')),
                                        ('top/n.txt.xz', lzma.compress(b'see /home/zqxtester\n'))]),
                             markers=('zqxtester',), allow=('*.xz', '*.gz'))
        markers = {item['entry'] for item in report['findings'] if item['kind'] == 'marker'}
        self.assertEqual(markers, {'top/s.tar.xz!src/n.md', 'top/n.md.gz!n.md', 'top/n.txt.xz!n.txt'})

    def test_nested_archive_matching_its_suffix_is_not_a_magic_finding(self):
        data = self.tar([('source/a.lua', b'-- a\n', ('', '', 0, 0))])
        report = self.Z.scan(self.make([('top/source.tar.gz', data)]), markers=())
        self.assertEqual(report['findings'], [])
        report = self.Z.scan(self.make([('top/source.lua', data)]), markers=())
        self.assertIn(('top/source.lua', 'magic'), self.kinds(report))

    def test_r6_magic_skips_a_bom_and_needs_a_full_signature(self):
        K = self.Z.magic_kind
        pe = b'MZ\x90\x00' + b'\x00' * 56 + struct.pack('<I', 64) + b'PE\x00\x00' + b'\x00' * 20
        self.assertEqual(K(pe), 'pe/dos')
        self.assertEqual(K(b'\xef\xbb\xbf' + pe), 'pe/dos')
        self.assertEqual(K(b'\xef\xbb\xbf\x89PNG\r\n\x1a\n'), 'png')
        self.assertEqual(K(b'BIKi' + b'\x00' * 8), 'bink')
        self.assertEqual(K(b'KB2g' + b'\x00' * 8), 'bink2')
        for text in (b'MZ = 1\n', b'KB2267602 fix\n', b'BIKE ride\n', b'ID3 tags\n', b'BZh is bzip\n',
                     b'\xef\xbb\xbfMZ = 1\n', b'MZ', b'RIFF'):
            with self.subTest(text=text):
                self.assertIsNone(K(text), text)

    def test_r3_unportable_names_and_twins_are_findings(self):
        nfc, nfd = 'top/caf\u00e9.lua', 'top/cafe\u0301.lua'
        path = self.make([(nfc, b'--\n'), (nfd, b'--\n'), ('top/Twin.lua', b'--\n'), ('top/twin.lua', b'--\n'),
                          ('top/CON.lua', b'--\n'), ('top/q?.lua', b'--\n'), ('top/x\u202eaul.txt.lua', b'--\n'),
                          ('top/trail./a.lua', b'--\n'), ('top/ok.lua', b'--\n')])
        kinds = self.kinds(self.Z.scan(path, markers=()))
        for entry in (nfc, nfd, 'top/Twin.lua', 'top/twin.lua'):
            self.assertIn((entry, 'name collision'), kinds)
        for entry in ('top/CON.lua', 'top/q?.lua', 'top/x\u202eaul.txt.lua', 'top/trail./a.lua'):
            self.assertIn((entry, 'unportable name'), kinds)
        self.assertFalse({kind for entry, kind in kinds if entry == 'top/ok.lua'})

    def test_wide_strings_in_binaries_are_scanned(self):
        dll = b'MZ\x90\x00' + b'\x00' * 60 + 'C:\\Users\\zqxtester\\x.pdb'.encode('utf-16-le') + b'\x00\x00'
        report = self.Z.scan(self.make([('top/k.dll', dll)]), markers=('zqxtester',), allow=('*.dll',))
        self.assertIn(('top/k.dll', 'marker'), self.kinds(report))


def hand_zip(entries, *, gap=b'', trailing=b''):
    """A ZIP built byte by byte. Each entry: dict(name=bytes, data=bytes, deflate=bool, slack=bytes,
    local_extra=bytes, central_extra=bytes). `gap` sits between the last entry and the central directory."""
    out, central = bytearray(), bytearray()
    for entry in entries:
        name, data = entry['name'], entry.get('data', b'')
        method = 8 if entry.get('deflate') else 0
        if method:
            packer = zlib.compressobj(wbits=-15)
            body = packer.compress(data) + packer.flush()
        else:
            body = data
        body += entry.get('slack', b'')
        crc = zlib.crc32(data)
        local_extra, central_extra = entry.get('local_extra', b''), entry.get('central_extra', b'')
        offset = len(out)
        out += struct.pack('<4sHHHHHIIIHH', b'PK\x03\x04', 20, 0, method, 0, 0x21, crc, len(body), len(data),
                           len(name), len(local_extra)) + name + local_extra + body
        central += struct.pack('<4sHHHHHHIIIHHHHHII', b'PK\x01\x02', 20, 20, 0, method, 0, 0x21, crc, len(body),
                               len(data), len(name), len(central_extra), 0, 0, 0, 0o100644 << 16,
                               offset) + name + central_extra
    out += gap
    start = len(out)
    out += central
    out += struct.pack('<4sHHHHIIH', b'PK\x05\x06', 0, 0, len(entries), len(entries), len(central), start, 0)
    return bytes(out + trailing)


class FollowupScanTests(unittest.TestCase):
    """Red tests for the publication-boundary follow-up: /tmp markers and review items S-1 to S-7."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        import scan_release_zip
        self.Z = scan_release_zip

    def scan_raw(self, raw, markers=('zqxtester',), **kwargs):
        return self.Z.scan_bytes(raw, name='t.zip', markers=markers, **kwargs)

    def zip_of(self, entries):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name, data in entries:
                archive.writestr(name, data)
        return buffer.getvalue()

    def kinds(self, report):
        return {(item['entry'], item['kind']) for item in report['findings']}

    # /tmp and /var/tmp ---------------------------------------------------------------------------
    def test_tmp_and_var_tmp_are_markers(self):
        markers = self.Z.privacy_markers({})
        for text, label in ((b'// /tmp/kp-rebuild-verify/src/x.cpp\n', '/tmp/'),
                            (b'"/tmp/k1_harness"\n', '/tmp/'),
                            (b'see file:///tmp/x\n', '/tmp/'),
                            (b'@/tmp/.hidden-private/x\n', '/tmp/'),
                            (b'/tmp/.X11-unix/X0 then /tmp/scratch/y\n', '/tmp/'),
                            (b'/var/tmp/build/x.o\n', '/var/tmp/'),
                            (b'R="${K1_ROOT:-/tmp/k1_harness}"\n', '/tmp/'),
                            (b'W="${WINEPREFIX:-/var/tmp/wineprefix}"\n', '/var/tmp/')):
            with self.subTest(text=text):
                hits = self.Z.path_scan('x.cpp', text, markers)
                self.assertEqual([hit['marker'] for hit in hits], [label], text)

    def test_tmp_marker_spares_relative_folders_and_fixed_system_names(self):
        # Criterion: a /tmp name passes only when it is fixed, the same on every machine and run, and holds
        # no build tree or run output: X11/ICE sockets and locks, and the harness's own write-probe file.
        markers = self.Z.privacy_markers({})
        for text in (b'scripts/tmp/x.lua\n', b'lib/tmp/y\n', b"names = ('/tmp/.X11-unix/X' + number,\n",
                     b"'@/tmp/.X11-unix/X' + number\n", b'Xvfb writes /tmp/.X<n>-lock first\n',
                     b'/tmp/.X0-lock and /tmp/.tX12-lock\n', b'/tmp/.ICE-unix/42\n',
                     b'probe = Path(f"/tmp/.kp_harness_write_probe.{os.getpid()}")\n',
                     b'touch /tmp/.kp_harness_write_probe.$$\n'):
            with self.subTest(text=text):
                self.assertEqual(self.Z.path_scan('x.py', text, markers), [], text)
        # The exemption covers the fixed file only, not a folder or a longer name that starts the same way.
        for text in (b'/tmp/.kp_harness_write_probe/run/x\n', b'/tmp/.X11-unixfoo/x\n', b'/tmp/.X0-lock/x\n'):
            with self.subTest(text=text):
                self.assertTrue(self.Z.path_scan('x.py', text, markers), text)

    def test_tmp_markers_are_fixed_markers_not_identities(self):
        markers = self.Z.privacy_markers({})
        self.assertIn('/tmp/', markers)
        self.assertIn('/var/tmp/', markers)
        self.assertNotIn('/tmp/', self.Z.identity_markers(markers))

    # S-1 ---------------------------------------------------------------------------------------------
    def test_s1_utf16_is_scanned_whenever_nul_bytes_are_present(self):
        for name, data in (('top/log.dat', '/home/zqxtester/x'.encode('utf-16-le')),
                           ('top/cfg.bin', 'C:\\Users\\zqxtester\\x'.encode('utf-16-be')),
                           ('top/k.dll', b'MZ' + b'\x00' * 62 + 'C:\\Users\\zqxtester\\x.pdb'.encode('utf-16-le'))):
            with self.subTest(name=name):
                data.decode('utf-8')  # valid UTF-8: the old rule skipped the UTF-16 scan
                report = self.scan_raw(self.zip_of([(name, data)]), allow=('*.dll',))
                self.assertIn((name, 'marker'), self.kinds(report))

    # S-2 ---------------------------------------------------------------------------------------------
    def test_s2_all_git_scopes_and_the_origin_owner_are_identities(self):
        config = {'user.name': 'Copilot\nQwv Plonk', 'user.email': 'bot4321@users.noreply.github.com\nqwvplonk@example.org'}
        with mock.patch.object(self.Z, '_git_config', side_effect=lambda key: config.get(key, '')), \
                mock.patch.object(self.Z, '_origin_url', return_value='https://github.com/qwvowner/KotorPhasor.git'):
            identities = self.Z.git_identities()
            markers = self.Z.privacy_markers()
        for value in ('Qwv Plonk', 'qwvplonk', 'qwvplonk@example.org', 'bot4321', 'qwvowner'):
            self.assertIn(value, identities)
        self.assertNotIn('Copilot', identities)  # generic name on the allow-list
        for text in (b'by bot4321\n', b'github.com/QwvOwner/KotorPhasor\n', b'Qwv Plonk wrote this\n'):
            with self.subTest(text=text):
                self.assertTrue(self.Z.path_scan('x.md', text, markers), text)
        self.assertEqual(self.Z.path_scan('x.md', b'Suggested by GitHub Copilot.\n', markers), [])

    def test_s2_generic_identity_allow_list(self):
        for name in ('Copilot', 'copilot', 'GitHub', 'github-actions[bot]', 'dependabot[bot]', 'noreply'):
            with self.subTest(name=name):
                self.assertFalse(self.Z._identity_ok(name), name)
        self.assertTrue(self.Z._identity_ok('qwvplonk'))

    def test_s2_origin_owner_is_parsed_from_common_url_forms(self):
        O = self.Z.owner_from_url
        for url in ('https://github.com/qwvowner/Repo.git', 'https://github.com/qwvowner/Repo',
                    'git@github.com:qwvowner/Repo.git', 'ssh://git@github.com/qwvowner/Repo.git',
                    'https://token@github.com/qwvowner/Repo.git'):
            with self.subTest(url=url):
                self.assertEqual(O(url), 'qwvowner')
        self.assertEqual(O(''), '')
        self.assertEqual(O('/srv/git/repo.git'), '')

    # S-3 ---------------------------------------------------------------------------------------------
    def test_s3_bytes_no_entry_covers_are_findings(self):
        secret = b'/home/zqxtester/hidden\n'
        base = [dict(name=b'top/a.lua', data=b'-- a\n' * 40, deflate=True)]
        for label, raw in (('gap', hand_zip(base, gap=secret)),
                           ('trailing', hand_zip(base, trailing=secret)),
                           ('slack', hand_zip([dict(base[0], slack=secret)]))):
            with self.subTest(label=label):
                report = self.scan_raw(raw)
                kinds = {item['kind'] for item in report['findings']}
                self.assertIn('uncovered bytes', kinds, report['findings'])
                self.assertTrue(any(item['detail'].startswith('line ') for item in report['findings']
                                    if item['kind'] == 'uncovered bytes'), report['findings'])  # marker hit
        self.assertTrue(self.scan_raw(hand_zip(base))['ok'])

    def test_s3_data_descriptors_are_covered_not_flagged(self):
        class Unseekable(io.RawIOBase):
            def __init__(self):
                self.buffer = bytearray()

            def writable(self):
                return True

            def write(self, data):
                self.buffer += data
                return len(data)
        for zip64 in (False, True):
            with self.subTest(zip64=zip64):
                sink = Unseekable()
                with zipfile.ZipFile(sink, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    for name in ('top/a.lua', 'top/b.lua'):
                        with archive.open(name, 'w', force_zip64=zip64) as stream:
                            stream.write(b'-- ok\n' * 30)
                raw = bytes(sink.buffer)
                self.assertTrue(zipfile.ZipFile(io.BytesIO(raw)).infolist()[0].flag_bits & 0x08)
                report = self.scan_raw(raw)
                self.assertEqual(report['findings'], [])

    def test_s3_nonzero_bytes_after_the_tar_end_are_findings(self):
        def tgz(tail):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w') as archive:
                info = tarfile.TarInfo('source/a.lua'); info.size = 5
                archive.addfile(info, io.BytesIO(b'-- a\n'))
            return gzip_compress(buffer.getvalue() + tail)
        hidden = io.BytesIO()
        with tarfile.open(fileobj=hidden, mode='w') as archive:
            info = tarfile.TarInfo('source/b.lua'); data = b'-- /home/zqxtester/b\n'; info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        report = self.scan_raw(self.zip_of([('top/source.tar.gz', tgz(hidden.getvalue()))]))
        self.assertIn(('top/source.tar.gz', 'uncovered bytes'), self.kinds(report))
        clean = self.scan_raw(self.zip_of([('top/source.tar.gz', tgz(b'\0' * 4096))]))
        self.assertEqual(clean['findings'], [])

    # S-4 ---------------------------------------------------------------------------------------------
    def test_s4_nul_in_a_zip_name_is_reported_and_its_tail_scanned(self):
        raw = hand_zip([dict(name=b'top/a.lua\x00/home/zqxtester/x', data=b'-- a\n'),
                        dict(name=b'top/b.lua', data=b'-- b\n')])
        kinds = self.kinds(self.scan_raw(raw))
        self.assertIn(('top/a.lua', 'unsafe name'), kinds)
        self.assertIn(('top/a.lua', 'marker in name'), kinds)

    # S-5 ---------------------------------------------------------------------------------------------
    def test_s5_a_lone_data_tmp_or_runs_folder_is_not_a_wrapper(self):
        for names, kind in ((['data/codecaves.toml'], 'excluded file'),
                            (['data/codecaves.toml', 'data/events.draft.toml', 'data/hooksites.toml'], 'excluded file'),
                            (['tmp/a.lua', 'tmp/b.lua'], 'private folder'),
                            (['runs/x/report.md'], 'private folder')):
            with self.subTest(names=names):
                report = self.scan_raw(self.zip_of([(name, b'x = 1\n') for name in names]), markers=())
                self.assertIn((names[0], kind), self.kinds(report))
        wrapped = self.scan_raw(self.zip_of([('kotorphasor-preview/data/codecaves.toml', b'x = 1\n')]), markers=())
        self.assertIn(('kotorphasor-preview/data/codecaves.toml', 'excluded file'), self.kinds(wrapped))
        public = self.scan_raw(self.zip_of([('top/scripts/tmp/a.lua', b'-- a\n')]), markers=())
        self.assertEqual(public['findings'], [])

    # Queued follow-up: the wrapper-folder list only knew about data/tmp/runs. A ZIP whose sole top
    # folder is one of the repo's other real top-level directories (docs, scripts, src, third_party,
    # tools) was mistaken for a synthetic wrapper, shifting root_depth by one and flagging an ordinary
    # nested `tmp`/`runs` subfolder as the private repository-root one.
    def test_lone_scripts_src_docs_tools_third_party_folder_is_not_a_wrapper(self):
        for top in ('docs', 'scripts', 'src', 'third_party', 'tools'):
            with self.subTest(top=top):
                report = self.scan_raw(self.zip_of([(f'{top}/tmp/a.lua', b'-- a\n')]), markers=())
                self.assertEqual(report['findings'], [],
                                  f"a nested tmp/ under a lone '{top}/' top folder must not read as the "
                                  "private repository-root tmp/")
        # A real wrapper (a name that is not itself a repo top-level folder) still shifts root_depth,
        # so the same nested tmp/ under it is still the private repository root.
        wrapped = self.scan_raw(self.zip_of([('kotorphasor-preview/tmp/a.lua', b'-- a\n')]), markers=())
        self.assertIn(('kotorphasor-preview/tmp/a.lua', 'private folder'), self.kinds(wrapped))

    # S-6 ---------------------------------------------------------------------------------------------
    def test_s6_unix_owner_in_5855_000d_and_7855_extra_fields(self):
        times = struct.pack('<II', 0, 0)
        for label, extra in (('5855', struct.pack('<HH', 0x5855, 12) + times + struct.pack('<HH', 1000, 1000)),
                             ('000d', struct.pack('<HH', 0x000D, 12) + times + struct.pack('<HH', 1000, 100)),
                             ('7855', struct.pack('<HH', 0x7855, 4) + struct.pack('<HH', 1000, 1000))):
            with self.subTest(label=label):
                raw = hand_zip([dict(name=b'top/a.lua', data=b'-- a\n', local_extra=extra)])
                self.assertIn(('top/a.lua', 'zip owner'), self.kinds(self.scan_raw(raw, markers=())))
        for label, extra in (('5855 zero', struct.pack('<HH', 0x5855, 12) + times + struct.pack('<HH', 0, 0)),
                             ('5855 central, times only', struct.pack('<HH', 0x5855, 8) + times),
                             ('7855 central, empty', struct.pack('<HH', 0x7855, 0))):
            with self.subTest(label=label):
                raw = hand_zip([dict(name=b'top/a.lua', data=b'-- a\n', local_extra=extra, central_extra=extra)])
                self.assertEqual(self.scan_raw(raw, markers=())['findings'], [])

    # S-7 ---------------------------------------------------------------------------------------------
    def test_s7_duplicates_and_file_folder_clashes_are_collisions(self):
        raw = hand_zip([dict(name=b'p/dup.lua', data=b'-- 1\n'), dict(name=b'p/dup.lua', data=b'-- 2\n'),
                        dict(name=b'p/x', data=b'x\n'), dict(name=b'p/x/y.lua', data=b'-- y\n'),
                        dict(name=b'p/A', data=b'a\n'), dict(name=b'p/a/z.lua', data=b'-- z\n'),
                        dict(name=b'p/d/', data=b''), dict(name=b'p/d/w.lua', data=b'-- w\n')])
        kinds = self.kinds(self.scan_raw(raw, markers=()))
        for entry in ('p/dup.lua', 'p/x', 'p/A'):
            self.assertIn((entry, 'name collision'), kinds)
        for entry in ('p/d/', 'p/d/w.lua', 'p/x/y.lua', 'p/a/z.lua'):
            self.assertNotIn((entry, 'name collision'), kinds)
        self.assertEqual(self.Z.name_collisions(['a/b.lua', 'a/c.lua']), {})
        self.assertIn('a/b', self.Z.name_collisions(['a/b', 'a/b/c.lua']))

    def test_s7_duplicate_tar_members_are_collisions(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for body in (b'-- 1\n', b'-- 2\n'):
                info = tarfile.TarInfo('source/a.lua'); info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
        report = self.scan_raw(self.zip_of([('top/source.tar.gz', buffer.getvalue())]), markers=())
        self.assertIn(('top/source.tar.gz!source/a.lua', 'name collision'), self.kinds(report))


def gzip_compress(data: bytes) -> bytes:
    import gzip
    return gzip.compress(data, mtime=0)


class HardeningBuilderTests(TreeCase):
    """Red tests for the packager (ruling 3, release gate, R-2 to R-5)."""

    def refuse(self, pattern, **kwargs):
        with self.assertRaisesRegex(ValueError, pattern):
            self.build(**kwargs)
        self.assertFalse((self.tmp / 'out').exists())

    def test_ruling_codecaves_and_events_draft_are_denied(self):
        for rel in ('data/codecaves.toml', 'data/events.draft.toml'):
            self.assertIn('owner decision', B.deny_reason(rel) or '')
        with mock.patch.object(B, 'FIXED', B.FIXED + ('data/codecaves.toml',)):
            write(self.src, 'data/codecaves.toml', 'x = 1\n')
            with self.assertRaisesRegex(ValueError, 'denylist.*codecaves'):
                B.select_files(self.src)

    def test_release_scan_is_a_mandatory_final_gate(self):
        result = self.build()
        verification = json.loads((self.tmp / 'out/verification.json').read_text())
        self.assertEqual(verification['release_scan'], 'PASS')
        self.assertEqual(result['release_scan'], 'PASS')
        failing = {'ok': False, 'findings': [{'entry': 'x', 'kind': 'marker', 'detail': 'line 1: /home/'}]}
        with mock.patch.object(B._scanner, 'scan_bytes', return_value=failing) as gate:
            with self.assertRaisesRegex(ValueError, 'release scan'):
                self.build(out_name='out2')
        self.assertTrue(gate.called)
        self.assertFalse((self.tmp / 'out2').exists())

    def test_r2_case_variant_private_folders_are_withheld_from_the_receipt(self):
        for part in ('.SuperPowers', 'KP-LIVE-x', 'Adjudication', 'SAVES'):
            write(self.src, f'scripts/examples/cursed/{part}/n.lua', '-- nested private\n')
        result = self.build()
        with zipfile.ZipFile(result['zip']) as archive:
            receipt = archive.read(TOP + 'packaging-receipt.json').lower()
        for word in (b'superpowers/', b'kp-live-x/', b'adjudication/', b'saves/'):
            self.assertNotIn(word, receipt)

    def test_r3_unportable_or_twin_names_refuse(self):
        self.assertTrue(B.name_problems(['a/CON.lua']))
        self.assertTrue(B.name_problems(['a/x\u202eaul.txt.lua']))
        self.assertTrue(B.name_problems(['a/Twin.lua', 'a/twin.lua']))
        self.assertTrue(B.name_problems(['a/caf\u00e9.lua', 'a/cafe\u0301.lua']))
        self.assertEqual(B.name_problems(['a/ok.lua', 'a/b.lua']), [])
        write(self.src, 'scripts/examples/cursed/Twin.lua', '-- a\n')
        write(self.src, 'scripts/examples/cursed/twin.lua', '-- b\n')
        with self.assertRaisesRegex(ValueError, 'name'):
            B.select_files(self.src)

    def test_r4_replaced_file_names_the_right_cause(self):
        rel = 'scripts/examples/cursed/10_rancor.lua'
        real = os.fstat

        def unlinked(descriptor):
            info = real(descriptor)
            return os.stat_result((info.st_mode, info.st_ino, info.st_dev, 0) + tuple(info)[4:])
        with mock.patch.object(B.os, 'fstat', side_effect=unlinked):
            with self.assertRaisesRegex(ValueError, 'replaced while reading'):
                B.read_source(self.src, rel)

    def test_r5_symlinked_harness_package_refuses_before_parsing(self):
        import shutil
        moved = self.tmp / 'outside-kpharness'
        shutil.move(str(self.src / 'scripts/harness/kpharness'), str(moved))
        (self.src / 'scripts/harness/kpharness').symlink_to(moved)
        with mock.patch.object(B, 'runtime_module_paths', side_effect=AssertionError('parsed')):
            with self.assertRaisesRegex(ValueError, 'symlink.*kpharness'):
                B.select_files(self.src)

    def test_r5_syntax_error_prints_json(self):
        write(self.src, 'scripts/harness/kpharness/shared.py', 'def broken(:\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = B.main(['--source-root', str(self.src), '--dry-run'])
        self.assertEqual(status, 1)
        report = json.loads(out.getvalue())
        self.assertFalse(report['ok'])
        self.assertIn('shared.py', report['error'])


class RealTreeDryRun(unittest.TestCase):
    def test_real_closure_excludes_unfinished_modules(self):
        selected = B.select_files(ROOT)['selected']
        for name in ('playback.py', 'pioneer.py', 'cli.py'):
            self.assertNotIn('scripts/harness/kpharness/' + name, selected)


if __name__ == '__main__':
    unittest.main()
