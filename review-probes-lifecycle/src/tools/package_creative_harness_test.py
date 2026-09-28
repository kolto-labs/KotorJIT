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
                    'scripts/examples/cursed/tmp/n.lua',
                    'scripts/examples/cursed/runs/n.lua',
                    'scripts/examples/cursed/Saves/n.lua',
                    'scripts/examples/cursed/.worktrees/x/n.lua',
                    'scripts/examples/cursed/kp-live-20260922/n.lua',
                    'scripts/harness/kpharness/tmp/n.py'):
            with self.subTest(rel=rel):
                self.assertIn('private', B.deny_reason(rel) or '')
                write(self.src, rel, '-- nested private\n')
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
                 'ogg.lua': b'OggS --\n', 'pe.lua': b'MZ-- text\n', 'nul.lua': b'-- a\x00b\n'}
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


class RealTreeDryRun(unittest.TestCase):
    def test_real_closure_excludes_unfinished_modules(self):
        selected = B.select_files(ROOT)['selected']
        for name in ('playback.py', 'pioneer.py', 'cli.py'):
            self.assertNotIn('scripts/harness/kpharness/' + name, selected)


if __name__ == '__main__':
    unittest.main()
