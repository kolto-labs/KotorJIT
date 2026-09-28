#!/usr/bin/env python3
"""Offline tests for the pre-launch input commitment; no game, Wine or display."""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts/harness'))
from kpharness import commit_inputs as CI  # noqa: E402

ELF = b'\x7fELF\x02\x01\x01' + b'\0' * 57


class CommitInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runs = self.root / 'runs'; self.runs.mkdir()
        self.log = self.root / 'kp-inputs.log'; self.log.write_text('')
        self.route = self.root / 'route.toml'; self.route.write_text('[[steps]]\nkind = "wait"\n')
        self.ffprobe = self.root / 'ffprobe'; self.ffprobe.write_bytes(ELF); self.ffprobe.chmod(0o755)

    def commit(self, **overrides):
        values = dict(route=self.route, ffprobe=str(self.ffprobe), log=self.log, runs_dir=self.runs)
        values.update(overrides)
        return CI.commit_inputs(**values)

    def lines(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_normal_append_records_both_hashes(self):
        line = self.commit()
        self.assertEqual(line['kind'], 'kpharness.input-commitment.v1')
        self.assertEqual(line['route']['sha256'], hashlib.sha256(self.route.read_bytes()).hexdigest())
        self.assertEqual(line['ffprobe']['sha256'], hashlib.sha256(ELF).hexdigest())
        self.assertEqual(line['ffprobe']['resolved_path'], str(self.ffprobe.resolve()))
        self.assertEqual(self.lines(), [line])

    def test_second_append_keeps_earlier_lines(self):
        self.log.write_text('{"kind":"user-note"}\n')
        first = self.commit()
        second = self.commit()
        self.assertEqual(self.lines(), [{'kind': 'user-note'}, first, second])

    def test_missing_log_is_refused(self):
        self.log.unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.commit()
        self.assertFalse(self.log.exists())

    def test_symlinked_log_is_refused(self):
        real = self.root / 'real.log'; real.write_text('')
        self.log.unlink(); self.log.symlink_to(real)
        with self.assertRaises(ValueError):
            self.commit()
        self.assertEqual(real.read_text(), '')

    def test_hard_linked_log_is_refused(self):
        os.link(self.log, self.root / 'second-name.log')
        with self.assertRaises(ValueError):
            self.commit()
        self.assertEqual(self.log.read_text(), '')

    def test_log_inside_runs_dir_is_refused(self):
        inside = self.runs / 'kp-inputs.log'; inside.write_text('')
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.commit(log=inside)
        self.assertEqual(inside.read_text(), '')

    def test_ffprobe_wrapper_script_is_refused(self):
        self.ffprobe.write_text('#!/bin/sh\nexec ffprobe "$@"\n')
        with self.assertRaisesRegex(ValueError, 'ELF'):
            self.commit()
        self.assertEqual(self.log.read_text(), '')

    def test_ffprobe_found_through_path_is_resolved(self):
        line = self.commit(ffprobe='ffprobe', search_path=str(self.root))
        self.assertEqual(line['ffprobe']['command'], 'ffprobe')
        self.assertEqual(line['ffprobe']['resolved_path'], str(self.ffprobe.resolve()))

    def test_missing_or_linked_route_is_refused(self):
        linked = self.root / 'linked.toml'; linked.symlink_to(self.route)
        for route in (self.root / 'absent.toml', linked, self.runs):
            with self.subTest(route=route), self.assertRaises(ValueError):
                self.commit(route=route)
        self.assertEqual(self.log.read_text(), '')

    def test_m4_route_inside_runs_dir_is_refused(self):
        inside = self.runs / 'old-run' / 'executed-route.toml'
        inside.parent.mkdir(); inside.write_text('[[steps]]\nkind = "wait"\n')
        with self.assertRaisesRegex(ValueError, 'route.*outside'):
            self.commit(route=inside)
        linked_runs = self.root / 'runs-link'; linked_runs.symlink_to(self.runs)
        with self.assertRaisesRegex(ValueError, 'route.*outside'):
            self.commit(route=inside, runs_dir=linked_runs)
        self.assertEqual(self.log.read_text(), '')

    def test_m9_log_refusals_name_the_inputs_log(self):
        cases = {'missing': lambda: self.log.unlink(),
                 'outside': lambda: None}
        for word, prepare in cases.items():
            with self.subTest(word=word):
                prepare()
                log = self.runs / 'in.log' if word == 'outside' else self.log
                if word == 'outside':
                    log.write_text('')
                with self.assertRaises(ValueError) as caught:
                    self.commit(log=log)
                message = str(caught.exception)
                self.assertIn('inputs log', message)
                self.assertIn(word, message)
                self.assertNotIn('cleanup commitment', message)

    def test_main_prints_the_appended_line(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = CI.main(['--route', str(self.route), '--ffprobe', str(self.ffprobe),
                              '--log', str(self.log), '--runs-dir', str(self.runs)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue()), self.lines()[0])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = CI.main(['--route', str(self.route), '--ffprobe', str(self.ffprobe),
                              '--log', str(self.runs / 'nope.log'), '--runs-dir', str(self.runs)])
        self.assertEqual(status, 1)
        self.assertFalse(json.loads(out.getvalue())['ok'])


if __name__ == '__main__':
    unittest.main()
