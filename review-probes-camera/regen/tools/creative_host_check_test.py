#!/usr/bin/env python3
"""Offline tests for the creative host check; `-version` calls are mocked, no tool is launched."""
import contextlib
import io
import json
import os
import subprocess
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
        # Fake ELF bytes cannot run; answer `-version` with the real banner shape.
        runner = mock.patch('subprocess.run', side_effect=self.banner)
        runner.start(); self.addCleanup(runner.stop)

    def banner(self, command, override=None, **kwargs):
        name = Path(command[0]).name.split('-')[0]  # ffprobe-real still prints 'ffprobe version'
        text = (override or {}).get(name, f'{name} version 8.1.2 Copyright (c) the FFmpeg developers\n')
        return subprocess.CompletedProcess(command, 0, stdout=text, stderr='')

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

    def test_m3_elf_that_is_not_the_tool_blocks(self):
        # hc/ probe: a PATH ffmpeg that is really /usr/bin/env reported ok.
        self.all_elf()
        with mock.patch('subprocess.run', side_effect=lambda cmd, **kw: self.banner(
                cmd, override={'ffmpeg': 'env: invalid option -- v\n'})):
            result = self.run_check()
        entry = result['tools']['ffmpeg']
        self.assertEqual(entry['status'], 'not_the_tool')
        self.assertTrue(entry['blocking'])
        self.assertFalse(result['ok'])

    def test_m3_version_banner_is_recorded(self):
        self.all_elf()
        with mock.patch('subprocess.run', side_effect=self.banner):
            result = self.run_check()
        self.assertEqual(result['tools']['ffprobe']['version'], 'ffprobe version 8.1.2')
        self.assertTrue(result['ok'], result)

    def test_m3_only_ffmpeg_and_ffprobe_version_are_run(self):
        self.all_elf()
        calls = []
        with mock.patch('subprocess.run', side_effect=lambda cmd, **kw: calls.append(cmd) or self.banner(cmd)), \
                mock.patch('subprocess.Popen', side_effect=AssertionError('launched')), \
                mock.patch('os.system', side_effect=AssertionError('launched')):
            self.assertTrue(self.run_check()['ok'])
        self.assertEqual(sorted(calls), [[os.path.realpath(self.first / 'ffmpeg'), '-version'],
                                         [os.path.realpath(self.first / 'ffprobe'), '-version']])

    def test_m5_elf_elsewhere_prefers_a_system_folder(self):
        self.all_elf()
        system = self.root / 'system'; system.mkdir()
        self.put(self.first, 'ffprobe', SCRIPT)
        self.put(self.second, 'ffprobe', ELF)
        preferred = self.put(system, 'ffprobe', ELF)
        with mock.patch.object(H, 'SYSTEM_DIRS', (str(system),)), \
                mock.patch('subprocess.run', side_effect=self.banner):
            entry = H.check_host(path=os.pathsep.join(map(str, (self.first, self.second, system))),
                                 dri_dir=self.dri)['tools']['ffprobe']
        self.assertEqual(entry['elf_elsewhere'], str(preferred))

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
