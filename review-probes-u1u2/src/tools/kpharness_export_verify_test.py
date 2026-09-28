#!/usr/bin/env python3
"""Offline tests for the export sidecar verifier; no game, Wine, display or FFmpeg.

Pinned to export sidecar schema 1. Rerun after round 11 lands, because the
verifier imports creative_accept and recording, which round 11 is editing.
"""
import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts/harness'))
from kpharness import export_verify as V  # noqa: E402

ELF = b'\x7fELF\x02\x01\x01' + b'\0' * 57
ROUTE, FFPROBE_SHA, LEDGER = 'a' * 64, 'b' * 64, 'c' * 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ExportVerifyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.run = self.root / 'run'; self.run.mkdir()
        self.ffprobe = self.root / 'ffprobe'; self.ffprobe.write_bytes(ELF); self.ffprobe.chmod(0o755)
        self.master = self.run / 'continuous.mp4'; self.master.write_bytes(b'accepted master frames')
        self.receipt = {
            'schema': 2, 'ok': True, 'run_dir': str(self.run),
            'media': {'continuous': {'path': str(self.master), 'sha256': sha(self.master.read_bytes())}},
            'visual_review': {'status': 'accepted', 'execution_receipt_sha256': 'd' * 64,
                              'content_artifact_sha256': 'e' * 64,
                              'geometry_precondition_sha256': 'f' * 64},
        }
        self.receipt_path = self.run / 'creative-run.json'
        self.receipt_path.write_text(json.dumps(self.receipt, indent=2) + '\n')
        self.export = self.run / 'accepted-media-0123abcd'; self.export.mkdir()
        self.probe_rows = {'representative.mp4': {'duration_seconds': 20.0, 'width': 640, 'height': 480},
                           'representative.gif': {'duration_seconds': 20.02, 'width': 480, 'height': 360}}
        artifacts = {}
        for name, row in self.probe_rows.items():
            path = self.export / name
            path.write_bytes(('encoded ' + name).encode())
            artifacts[name] = {'path': str(path), 'sha256': sha(path.read_bytes()), **row}
        self.sidecar = {
            'schema': 1, 'run_dir': str(self.run),
            'source_video': dict(self.receipt['media']['continuous']),
            'source_geometry': {'duration_seconds': 234.6, 'width': 1024, 'height': 768},
            'accepted_execution_sha256': 'd' * 64,
            'accepted_receipt_sha256': sha(self.receipt_path.read_bytes()),
            'selected_route_sha256': ROUTE, 'selected_ffprobe_sha256': FFPROBE_SHA,
            'selected_cleanup_ledger_sha256': LEDGER,
            'accepted_content_artifact_sha256': 'e' * 64,
            'accepted_geometry_precondition_sha256': 'f' * 64,
            'start_seconds': 204.0, 'end_seconds': 224.0, 'duration_seconds': 20.0,
            'selection': 'explicit reviewed interval',
            'settings': {'gif_fps': 25, 'gif_width': 480, 'mp4_width': 640,
                         'mp4_cadence': 'preserve source timestamps; no interpolation',
                         'ffmpeg': 'ffmpeg', 'ffprobe': 'ffprobe'},
            'artifacts': artifacts,
            'scope': 'accepted master derivatives; review output readability and GIF smoothness',
        }
        self.write_sidecar(self.sidecar)
        self.accepts = mock.patch.object(V, 'verify_acceptance', return_value=True)
        self.accept_mock = self.accepts.start(); self.addCleanup(self.accepts.stop)
        self.probe = mock.patch.object(V, 'probe_video', side_effect=self.fake_probe)
        self.probe.start(); self.addCleanup(self.probe.stop)

    def fake_probe(self, path, ffprobe):
        self.assertEqual(ffprobe, str(self.ffprobe.resolve()))
        return dict(self.probe_rows[Path(path).name])

    def write_sidecar(self, value):
        (self.export / 'export.json').write_text(json.dumps(value, indent=2) + '\n')

    def verify(self, export=None, **overrides):
        values = dict(route_sha256=ROUTE, ffprobe_sha256=FFPROBE_SHA,
                      cleanup_ledger_sha256=LEDGER, ffprobe=str(self.ffprobe))
        values.update(overrides)
        return V.verify_export(export or self.export, **values)

    def mutate(self, change):
        value = copy.deepcopy(self.sidecar); change(value); self.write_sidecar(value)

    def assert_refused(self, pattern=None):
        with self.assertRaisesRegex(ValueError, pattern or '.'):
            self.verify()

    def test_untampered_export_passes_and_flags_local_paths(self):
        report = self.verify()
        self.assertTrue(report['ok'])
        self.assertEqual(report['sidecar_schema'], 1)
        self.assertFalse(report['shareable'])
        self.assertIn('run_dir', report['local_path_fields'])
        self.assertIn('artifacts.representative.mp4.path', report['local_path_fields'])
        receipt = self.accept_mock.call_args
        self.assertEqual(receipt.kwargs, {'route_sha256': ROUTE, 'ffprobe_sha256': FFPROBE_SHA,
                                          'cleanup_ledger_sha256': LEDGER})

    def test_relative_artifact_paths_pass_and_are_shareable_when_run_dir_absent(self):
        def relative(value):
            del value['run_dir']
            # source_video copies the receipt's absolute master path; it leaks too.
            value['source_video']['path'] = 'continuous.mp4'
            for name, item in value['artifacts'].items():
                item['path'] = name
        self.mutate(relative)
        report = self.verify()
        self.assertTrue(report['ok'])
        self.assertTrue(report['shareable'], report['local_path_fields'])

    def test_acceptance_that_no_longer_verifies_is_refused(self):
        self.accept_mock.return_value = False
        self.assert_refused('acceptance')

    def test_supplied_hashes_must_match_the_sidecar(self):
        for key in ('route_sha256', 'ffprobe_sha256', 'cleanup_ledger_sha256'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                self.verify(**{key: '0' * 64})

    def test_each_sidecar_field_tamper_is_refused(self):
        cases = {
            'schema': lambda v: v.update(schema=2),
            'source video hash': lambda v: v['source_video'].update(sha256='0' * 64),
            'receipt hash': lambda v: v.update(accepted_receipt_sha256='0' * 64),
            'execution hash': lambda v: v.update(accepted_execution_sha256='0' * 64),
            'content hash': lambda v: v.update(accepted_content_artifact_sha256='0' * 64),
            'geometry hash': lambda v: v.update(accepted_geometry_precondition_sha256='0' * 64),
            'interval': lambda v: v.update(end_seconds=230.0),
            'reversed interval': lambda v: v.update(start_seconds=230.0, end_seconds=224.0),
            'artifact hash': lambda v: v['artifacts']['representative.mp4'].update(sha256='0' * 64),
            'artifact duration': lambda v: v['artifacts']['representative.gif'].update(duration_seconds=19.0),
            'artifact width': lambda v: v['artifacts']['representative.mp4'].update(width=320),
            'missing artifact': lambda v: v['artifacts'].pop('representative.gif'),
            'outside path': lambda v: v['artifacts']['representative.mp4'].update(path=str(self.master)),
            'parent path': lambda v: v['artifacts']['representative.mp4'].update(path='../continuous.mp4'),
            'gif fps': lambda v: v['settings'].update(gif_fps=0),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.mutate(change)
                self.assert_refused()
                self.write_sidecar(self.sidecar)
        self.assertTrue(self.verify()['ok'])

    def test_changed_receipt_bytes_are_refused(self):
        self.receipt_path.write_text(json.dumps(self.receipt) + '\n')
        self.assert_refused('creative-run.json')

    def test_changed_master_is_refused(self):
        self.master.write_bytes(b'different frames')
        self.assert_refused('master')

    def test_changed_artifact_bytes_are_refused(self):
        (self.export / 'representative.gif').write_bytes(b'other gif')
        self.assert_refused('representative.gif')

    def test_reprobed_duration_outside_interval_is_refused(self):
        self.probe_rows['representative.mp4']['duration_seconds'] = 18.0
        self.mutate(lambda v: v['artifacts']['representative.mp4'].update(duration_seconds=18.0))
        self.assert_refused('interval')

    def test_reprobe_that_disagrees_with_sidecar_is_refused(self):
        self.probe_rows['representative.mp4']['duration_seconds'] = 20.05
        self.assert_refused('representative.mp4')

    def test_extra_file_in_export_folder_is_refused(self):
        (self.export / 'notes.txt').write_text('extra')
        self.assert_refused('unexpected')

    def test_linked_artifact_or_sidecar_is_refused(self):
        gif = self.export / 'representative.gif'
        real = self.root / 'real.gif'; real.write_bytes(gif.read_bytes())
        gif.unlink(); gif.symlink_to(real)
        self.assert_refused('representative.gif')

    def test_folder_outside_a_run_is_refused(self):
        stray = self.root / 'loose'; stray.mkdir()
        (stray / 'export.json').write_text(json.dumps(self.sidecar))
        with self.assertRaises(ValueError):
            self.verify(export=stray)

    def test_ffprobe_script_is_refused_before_probing(self):
        self.ffprobe.write_text('#!/bin/sh\n')
        with mock.patch.object(V, 'probe_video') as probe:
            self.assert_refused('ELF')
            probe.assert_not_called()

    def test_main_reports_json_and_exit_code(self):
        args = [str(self.export), '--route-sha256', ROUTE, '--ffprobe-sha256', FFPROBE_SHA,
                '--cleanup-ledger-sha256', LEDGER, '--ffprobe', str(self.ffprobe)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(V.main(args), 0)
        self.assertTrue(json.loads(out.getvalue())['ok'])
        self.accept_mock.return_value = False
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(V.main(args), 1)
        self.assertFalse(json.loads(out.getvalue())['ok'])


if __name__ == '__main__':
    unittest.main()
