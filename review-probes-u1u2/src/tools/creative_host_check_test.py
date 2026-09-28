#!/usr/bin/env python3
"""Offline tests for the creative host check; no tool is launched."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import creative_host_check as H  # noqa: E402

ELF = b'\x7fELF\x02\x01\x01' + b'\0' * 57
SCRIPT = b'#!/bin/sh\nexec /usr/bin/true "$@"\n'


class HostCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = self.root / 'first'; self.first.mkdir()
        self.second = self.root / 'second'; self.second.mkdir()
        self.dri = self.root / 'dri'; self.dri.mkdir()
        (self.dri / 'renderD128').write_bytes(b'')

    def put(self, directory: Path, name: str, data: bytes) -> Path:
        path = directory / name
        path.write_bytes(data)
        path.chmod(0o755)
        return path

    def all_elf(self):
        for name in H.TOOLS:
            self.put(self.first, name, ELF)

    def run_check(self, path=None):
        return H.check_host(path=path or f'{self.first}{os.pathsep}{self.second}', dri_dir=self.dri)

    def test_elf_script_and_missing_are_classified(self):
        self.put(self.first, 'ffmpeg', ELF)
        self.put(self.first, 'ffprobe', SCRIPT)
        result = self.run_check()
        self.assertEqual(result['tools']['ffmpeg']['status'], 'ok')
        self.assertEqual(result['tools']['ffprobe']['status'], 'wrapper')
        self.assertEqual(result['tools']['mpv']['status'], 'missing')
        self.assertFalse(result['ok'])

    def test_all_elf_with_render_node_passes(self):
        self.all_elf()
        result = self.run_check()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['render_nodes'], [str(self.dri / 'renderD128')])
        self.assertEqual(result['kind'], 'kpharness.creative-host-check.v1')

    def test_ffmpeg_wrapper_blocks_and_names_a_later_elf(self):
        self.all_elf()
        self.put(self.first, 'ffmpeg', SCRIPT)
        later = self.put(self.second, 'ffmpeg', ELF)
        result = self.run_check()
        entry = result['tools']['ffmpeg']
        self.assertEqual(entry['status'], 'wrapper')
        self.assertTrue(entry['blocking'])
        self.assertEqual(entry['elf_elsewhere'], str(later))
        self.assertFalse(result['ok'])

    def test_script_for_tools_that_may_be_scripts_is_information_only(self):
        self.all_elf()
        self.put(self.first, 'wine', SCRIPT)
        result = self.run_check()
        self.assertEqual(result['tools']['wine']['status'], 'wrapper')
        self.assertFalse(result['tools']['wine']['blocking'])
        self.assertTrue(result['ok'], result)

    def test_missing_render_node_fails(self):
        self.all_elf()
        (self.dri / 'renderD128').unlink()
        result = self.run_check()
        self.assertEqual(result['render_nodes'], [])
        self.assertFalse(result['ok'])

    def test_symlink_resolves_to_target(self):
        self.all_elf()
        target = self.put(self.second, 'ffprobe-real', ELF)
        (self.first / 'ffprobe').unlink()
        (self.first / 'ffprobe').symlink_to(target)
        entry = self.run_check()['tools']['ffprobe']
        self.assertEqual(entry['status'], 'ok')
        self.assertEqual(entry['resolved'], str(target))

    def test_non_executable_file_is_skipped(self):
        self.all_elf()
        (self.first / 'mpv').chmod(0o644)
        self.assertEqual(self.run_check()['tools']['mpv']['status'], 'missing')

    def test_old_python_fails(self):
        self.all_elf()
        with mock.patch.object(H.sys, 'version_info', (3, 11, 9)):
            result = self.run_check()
        self.assertFalse(result['python']['ok'])
        self.assertFalse(result['ok'])

    def test_never_launches_a_process(self):
        self.all_elf()
        with mock.patch('subprocess.run', side_effect=AssertionError('launched')), \
                mock.patch('subprocess.Popen', side_effect=AssertionError('launched')), \
                mock.patch('os.system', side_effect=AssertionError('launched')):
            self.assertTrue(self.run_check()['ok'])

    def test_main_prints_one_json_line_and_sets_exit_code(self):
        self.all_elf()
        for broken, code in ((False, 0), (True, 1)):
            with self.subTest(broken=broken):
                if broken:
                    self.put(self.first, 'ffprobe', SCRIPT)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    status = H.main(['--path', str(self.first), '--dri-dir', str(self.dri)])
                lines = out.getvalue().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertEqual(json.loads(lines[0])['ok'], not broken)
                self.assertEqual(status, code)


if __name__ == '__main__':
    unittest.main()
