#!/usr/bin/env python3
"""Host-only Gamescope backend contract tests; starts no display, game or recorder."""
from __future__ import annotations

import contextlib
import copy
import fcntl
import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/harness"))

from kpharness import display_backends as D
from kpharness import gamescope_xwayland as G
from kpharness import recording as R
from kpharness import creative_export as E
from kpharness import creative_accept as A
from kpharness import session as HS
from kpharness import creative as C
from kpharness import creative_wine as W
from kpharness import gamescope_snapshot as S
from kpharness.creative_accept import (accept as _accept_visual, verify_acceptance as _verify_acceptance,
    execution_receipt_sha256, acceptance_receipt_sha256)
from kpharness.creative_steps import CreativeRunner
from kpharness.owned_x11 import OwnedX11Input


# Operator-owned commitment log outside every fixture run directory.
_COMMITMENT_DIRECTORY = tempfile.TemporaryDirectory(prefix='kp-ledger-commitments-')
COMMIT_LOG = Path(_COMMITMENT_DIRECTORY.name) / 'commitments.log'
COMMIT_LOG.touch()
HEAD_KIND = 'kpharness.cleanup-ledger-head.v1'


def head_lines(text):
    """Parse only machine-readable ledger-head lines emitted by the tools."""
    lines = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get('kind') == HEAD_KIND:
            lines.append(value)
    return lines


def init_ledger(run_dir, log=None):
    with contextlib.redirect_stderr(io.StringIO()):
        return A.initialize_cleanup_ledger(Path(run_dir), commitment_log=log or COMMIT_LOG)


def accept_visual(run_dir, **kwargs):
    receipt = json.loads((Path(run_dir) / 'creative-run.json').read_text())
    kwargs.setdefault('route_sha256', receipt.get('route_source', {}).get('sha256', 'missing'))
    kwargs.setdefault('ffprobe_sha256', receipt.get('cadence', {}).get('probe_tool', {}).get('sha256', 'missing'))
    if not (Path(run_dir) / A.CLEANUP_LEDGER).exists():
        init_ledger(run_dir)
    kwargs.setdefault('cleanup_ledger_sha256', A.cleanup_ledger_sha256(Path(run_dir)))
    kwargs.setdefault('commitment_log', COMMIT_LOG)
    kwargs.setdefault('content_probe', fixture_content_probe)
    with contextlib.redirect_stderr(io.StringIO()):
        return _accept_visual(run_dir, **kwargs)


def verify_acceptance(receipt):
    route_sha = receipt.get('visual_review', {}).get('route_sha256',
        receipt.get('route_source', {}).get('sha256'))
    probe_sha = receipt.get('visual_review', {}).get('ffprobe_sha256',
        receipt.get('cadence', {}).get('probe_tool', {}).get('sha256'))
    cleanup_sha = receipt.get('visual_review', {}).get('cleanup_ledger_sha256')
    return _verify_acceptance(receipt, route_sha256=route_sha, ffprobe_sha256=probe_sha,
                              cleanup_ledger_sha256=cleanup_sha)


def fixture_pts_probe(path, executable, *, pass_fds=()):
    descriptor = int(str(path).rsplit('/', 1)[-1])
    tool_descriptor = int(str(executable).rsplit('/', 1)[-1])
    if pass_fds != (descriptor, tool_descriptor):
        raise ValueError('acceptance probe did not inherit stable media and tool descriptors')
    return [index / 60 for index in range(121)]


def fixture_content_probe(path, executable, *, pass_fds=()):
    """Deterministic non-black, fully changing signalstats rows aligned to fixture PTS."""
    return [{'ymin': 16.0, 'ymax': 235.0, 'yavg': 120.0 + index % 7,
             'ydif': 0.0 if index == 0 else 3.5, 'udif': 0.0 if index == 0 else 1.0,
             'vdif': 0.0 if index == 0 else 1.0} for index in range(121)]


def write_cleanup_failure(run, identifier, *, pid=4242, start='fixture-start'):
    if not (Path(run) / A.CLEANUP_LEDGER).exists():
        init_ledger(run)
    tool = {'command': 'ffprobe', 'resolved_path': '/usr/bin/ffprobe', 'sha256': '1' * 64}
    host = A._host_identity()
    payload = {'failure_type': 'ffprobe_cleanup_failed', 'identity': 'exact', 'pid': pid,
        'pid_start': start, 'boot_id': host['boot_id'], 'pid_namespace': host['pid_namespace'],
        'command': ['ffprobe'], 'tool': tool, 'bounded_wait_seconds': [2, 2],
        'signal_errors': [], 'recovery': A.RECOVERY_REQUIREMENT}
    with contextlib.redirect_stderr(io.StringIO()):
        return A._append_cleanup_record(Path(run), 'failure', payload, identifier=identifier,
            expected_head=A.cleanup_ledger_sha256(Path(run)), commitment_log=COMMIT_LOG,
            event='acceptance_failure')[0]


def pidfd_safe_close(fake_pidfd):
    """Close real descriptors while swallowing the synthetic pidfd number."""
    real_close = os.close
    return lambda fd: None if fd == fake_pidfd else real_close(fd)


def host_lease(*args, **kwargs):
    kwargs.setdefault("pid_reader", lambda: [])
    kwargs.setdefault("controller_factory", lambda: None)
    lease = G.GamescopeXwaylandLease(*args, **kwargs)
    lease.candidate_display = ':9191'
    return lease


def facts(**overrides):
    values = dict(os_family="linux", os_version="test", architecture="x86_64",
        session_type="wayland", desktop="KDE", container=None, crostini=False,
        executables={name: True for name in D.GAMESCOPE_TOOLS}, probes={"dri_present": True})
    values.update(overrides)
    return D.HostFacts(**values)


class FakeLease:
    adapter_id = D.GAMESCOPE_BACKEND
    lease_id = "lease-1"
    width, height = 1024, 768
    environment = {"DISPLAY": ":91", "XAUTHORITY": "[REDACTED]"}
    live = True
    def is_alive(self): return self.live
    def close(self): self.live = False
    def receipt(self): return {"lease_id": self.lease_id}


def owned(*, width=800, height=600, window="0x2a"):
    return D.OwnedWindow(window, D.ProcessIdentity(77, "1234"), width, height,
        "KotOR", "lease-1", ":91", {"DISPLAY": ":91", "XAUTHORITY": "[REDACTED]"},
        12.5, frozenset({"x11_window_capture"}), frozenset({"x11_input"}))


def xwininfo_output(window_id='0x2a', *, x=0, y=0, width=1024, height=768, border=0,
                    state='IsViewable'):
    return (f'\nxwininfo: Window id: {window_id} "KotOR"\n\n'
            f'  Absolute upper-left X:  {x}\n  Absolute upper-left Y:  {y}\n'
            f'  Relative upper-left X:  {x}\n  Relative upper-left Y:  {y}\n'
            f'  Width: {width}\n  Height: {height}\n  Depth: 24\n  Visual: 0x21\n'
            f'  Border width: {border}\n  Class: InputOutput\n  Map State: {state}\n'
            f'  Override Redirect State: no\n')


def root_output(width=1024, height=768):
    return (f'\nxwininfo: Window id: 0x3ec (the root window) (has no name)\n\n'
            f'  Absolute upper-left X:  0\n  Absolute upper-left Y:  0\n'
            f'  Width: {width}\n  Height: {height}\n  Depth: 24\n  Border width: 0\n'
            f'  Map State: IsViewable\n')


def geometry_query(root=(1024, 768), **window):
    """Answer only the two xwininfo queries the geometry precondition may issue."""
    def query(command, **kwargs):
        if list(command[:2]) == ['xwininfo', '-root']:
            return types.SimpleNamespace(returncode=0, stdout=root_output(*root))
        if list(command[:2]) == ['xwininfo', '-id']:
            return types.SimpleNamespace(returncode=0, stdout=xwininfo_output(command[2], **window))
        raise AssertionError(f'unexpected geometry query {command}')
    return query


def fixture_geometry_evidence():
    evidence = R.parse_xwininfo_geometry(xwininfo_output(), root_output(),
                                         window_id='0x2a', lease_extent=(1024, 768))
    return {'status': 'verified', 'initial': evidence, 'pre_exec': copy.deepcopy(evidence)}


def fixture_content_block(run, media, digest, probe_tool, canonical_pts, policy='game-capture-v1'):
    rows = fixture_content_probe(None, None)
    path = run / 'ffprobe-content.json'
    path.write_text(json.dumps({'schema': 1, 'master': {'path': str(media.resolve()), 'sha256': digest},
        'probe': {**probe_tool, 'method': 'ffprobe-lavfi-signalstats-v1'},
        'frame_count': len(rows), 'frames': rows}, sort_keys=True, separators=(',', ':')) + '\n')
    evaluation = D.evaluate_content(rows, canonical_pts, 1.0, 2.0, D.CONTENT_POLICIES[policy])
    return {'artifact': {'path': str(path.resolve()), 'sha256': R.sha256(path),
                         'master_sha256': digest, 'frame_count': len(rows)}, **evaluation}


def rewrite_content_probe(receipt, run, identity):
    """Coherently rebind the content artifact to a substituted probe-tool identity."""
    path = run / 'ffprobe-content.json'; artifact = json.loads(path.read_text())
    artifact['probe'] = {**identity, 'method': 'ffprobe-lavfi-signalstats-v1'}
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(',', ':')) + '\n')
    receipt['cadence']['content']['artifact']['sha256'] = R.sha256(path)


def completed_receipt(run):
    if not (run / A.CLEANUP_LEDGER).exists():
        init_ledger(run)
    media = run / "continuous.mp4"
    digest = R.sha256(media)
    canonical_pts = [index / 60 for index in range(121)]
    pts = [value for value in canonical_pts if 1 <= value <= 2]
    whole = R.analyze_pts(canonical_pts, requested_fps=60, interval_start=canonical_pts[0],
                          interval_end=canonical_pts[-1], thresholds=R.CadenceThresholds())
    pts_path = run / "ffprobe-cadence.json"
    probe_tool = {"command": sys.executable, "resolved_path": str(Path(sys.executable).resolve()),
                  "sha256": R.sha256(Path(sys.executable).resolve())}
    pts_path.write_text(json.dumps({"schema": 1,
        "master": {"path": str(media.resolve()), "sha256": digest},
        "probe": {**probe_tool, "method": "ffprobe-best-effort-timestamp-time-v1"},
        "frame_count": len(canonical_pts), "pts_seconds": canonical_pts},
        sort_keys=True, separators=(",", ":")) + "\n")
    route_path = run / 'executed-route.toml'
    route_path.write_text('schema_version = 1\nname = "fixture"\ntarget = "k1"\n[[step]]\ndo = "fixture"\n')
    route_info = route_path.stat()
    route_source = {**R.artifact(route_path), 'identity': {
        'device': route_info.st_dev, 'inode': route_info.st_ino, 'size': route_info.st_size,
        'mtime_ns': route_info.st_mtime_ns, 'ctime_ns': route_info.st_ctime_ns,
        'links': route_info.st_nlink}}
    runtime = {}
    for name in ('kphasor.dll', 'binkw32.dll'):
        runtime_path = run / name; runtime_path.write_bytes(('runtime-' + name).encode())
        runtime[name] = R.artifact(runtime_path)
    route_steps = [{"index": 1, "step": "do fixture", "status": "ok",
                    "seconds": 0.1, "detail": "fixture passed"}]
    report_path = run / 'report.json'
    report_path.write_text(json.dumps({"scenario": "fixture", "target": "k1", "build": "fixture-build",
        "run_dir": str(run), "started": 1.0, "finished": 2.0, "seconds": 1.0,
        "ok": True, "error": "", "verdict": None,
        "execution": {"game_speed_requested": 16.0, "game_speed_effective": 16.0},
        "steps": route_steps},
        sort_keys=True, separators=(',', ':')))
    receipt = {
        "schema": 2, "backend": D.GAMESCOPE_BACKEND, "run_dir": str(run),
        "target": "k1", "build": "fixture-build", "runtime": runtime,
        "route_source": route_source,
        "started_utc": "2026-09-27T00:00:00+00:00", "finished_utc": "2026-09-27T00:01:00+00:00",
        "platform": {"detected": {"os": "linux"}, "admission": {"status": "admitted", "reason": "owned"}},
        "display": {"kind": "gamescope-xwayland", "lease_id": "lease-1", "requested_geometry": [1024, 768],
            "owner": {"gamescope": {"pid": 10, "start": "a"}, "ready_child": {"pid": 11, "start": "b"}},
            "process_group": {"pgid": 10, "session": 10, "child_descends_from_gamescope": True},
            "x11": {"display": ":91", "xauthority_present": True},
            "readiness": {"status": "passed"}, "renderer": {"status": "accelerated", "direct": True}},
        "window": {"status": "verified", "id": "0x2a", "pid": 77, "pid_start": "1234",
            "geometry": [1024, 768], "lease_id": "lease-1"},
        "capture": {"status": "passed", "adapter": "linux-gamescope-x11-window-v1",
            "source": {"kind": "x11-window", "input": ":91.0", "window_id": "0x2a",
                "source_extent": [1024, 768], "drawable": "window",
                "details": {"screen": 0, "draw_mouse": False}},
            "geometry_precondition": fixture_geometry_evidence(),
            "authorization": {"lease_id": "lease-1", "private_display": True,
                "caller_display_reused": False,
                "authorized_surface": {"id": "0x2a", "pid": 77, "pid_start": "1234", "extent": [1024, 768]},
                "coverage": {"status": "exact", "surface_origin": [0, 0],
                    "surface_extent": [1024, 768], "source_extent": [1024, 768]}},
            "startup": {"status": "passed", "timeout_seconds": 5.0, "started_monotonic": 10.0,
                "first_frame": 1, "first_frame_monotonic": 10.1,
                "shm": {"status": "no_fallback_observed",
                    "method": "absence-of-fallback-through-first-frame-and-continuous-log-watch",
                    "forbidden_matches": []}},
            "diagnostics": {"status": "complete", "terminal": {"frame": 600,
                "out_time_us": 10_000_000, "dup_frames": 0, "drop_frames": 0}},
            "markers": [
                {"name": "phase_1", "pattern": "phase=1", "line": "phase=1", "native_log_byte_end": 10,
                 "detected_monotonic": 11.0, "capture_seconds": 1.0, "poll_interval_ms": 100,
                 "uncertainty_ms": 100, "sequence": 1},
                {"name": "complete", "pattern": "complete", "line": "complete", "native_log_byte_end": 20,
                 "detected_monotonic": 12.0, "capture_seconds": 2.0, "poll_interval_ms": 100,
                 "uncertainty_ms": 100, "sequence": 2}],
            "marker_order": {"status": "ordered",
                "basis": "strict native-log byte end and sequence; nondecreasing monotonic detection time"},
            "capture_sampling_fps_requested": 60,
            "transport": {"version": 1,
                "progress": {"fd": 8, "role": "regular-progress-file"},
                "output": {"directory_fd": 9, "role": "private-output-directory",
                           "name": "continuous.mp4"}},
            "command": ["ffmpeg", "-nostdin", "-y", "-threads", "2", "-nostats",
                        "-stats_period", "0.25", "-progress", "/proc/self/fd/8", "-f", "x11grab",
                        "-draw_mouse", "0", "-framerate", "60", "-window_id", "0x2a",
                        "-video_size", "1024x768", "-i", ":91.0", "-an", "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "28", "-pix_fmt", "yuv420p", "-threads", "2",
                        "/proc/self/fd/9/continuous.mp4"]},
        "cadence": {"status": "passed", "requested_fps": 60, "probe_tool": probe_tool,
            "policy": {"id": "gamescope-cadence-v1", "requested_fps": 60,
                       "minimum_rate_ratio": .99, "maximum_drop_ratio": .005,
                       "maximum_gap_seconds": .05},
            "terminal_progress": {"frame": 600, "out_time_us": 10_000_000,
                                  "dup_frames": 0, "drop_frames": 0},
            "thresholds": {"minimum_rate_ratio": .99, "maximum_drop_ratio": .005, "maximum_gap_seconds": .05},
            "policy_scope": {"rate_gap_missing": "acceptance_interval",
                "ffmpeg_drop_delta": "acceptance_interval", "ffmpeg_duplicates": "whole_capture"},
            "pts_artifact": {"path": str(pts_path.resolve()), "sha256": R.sha256(pts_path),
                             "master_sha256": digest, "frame_count": len(canonical_pts)},
            "marker_configuration": {"version": 1, "required_order": ["phase_1", "complete"],
                "patterns": {"phase_1": "phase=1", "complete": "complete"},
                "optional_markers": ["effect_start"],
                "acceptance_pair": ["phase_1", "complete"]},
            "acceptance_interval": {"start_marker": "phase_1", "end_marker": "complete"},
            "whole_capture": whole,
            "intervals": [{"start_marker": "phase_1", "end_marker": "complete", "status": "passed",
                "start_capture_seconds": 1.0, "end_capture_seconds": 2.0,
                "first_included_pts": 1.0, "last_included_pts": 2.0,
                "frame_count": 61, "inter_frame_count": 60, "span_seconds": 1.0,
                "effective_fps": 60.0, "requested_slot_count": 60, "missing_slots": 0,
                "missing_or_dropped_slots": 0, "missing_or_dropped_ratio": 0.0,
                "interval_histogram_ticks": {"1": 60}, "p95_gap_seconds": 1/60,
                "p99_gap_seconds": 1/60, "maximum_gap_seconds": 1/60,
                "gaps_above_ms": {"25": 0, "50": 0, "100": 0},
                "thresholds": {"minimum_rate_ratio": .99, "maximum_drop_ratio": .005,
                               "maximum_gap_seconds": .05},
                "included_pts_seconds": pts,
                "ffmpeg": {"status": "bounded", "dup_frames": 0, "drop_frames": 0,
                    "start_sample": {"capture_seconds": .9, "frame": 50, "out_time_us": 900000,
                                     "dup_frames": 0, "drop_frames": 0},
                    "end_sample": {"capture_seconds": 2.1, "frame": 122, "out_time_us": 2100000,
                                   "dup_frames": 0, "drop_frames": 0}}}],
            "content": fixture_content_block(run, media, digest, probe_tool, canonical_pts),
            "failures": [], "distinct_game_frames": {"status": "unvalidated"}},
        "route": {"status": "passed", "predicates_passed": True,
                  "steps": route_steps, "physical_console_correlated": True,
                  "execution_identity": {"scenario": "fixture", "target": "k1",
                      "build": "fixture-build", "route_source_sha256": R.sha256(route_path),
                      "runtime_sha256": {name: value['sha256'] for name, value in runtime.items()}},
                  "report": {"path": str(report_path), "sha256": R.sha256(report_path)}},
        "capture_gate": {"status": "passed"},
        "media": {"status": "retained_for_visual_review",
                  "continuous": {"path": str(media), "sha256": digest}},
        "preservation": {"source_unchanged": True, "inputs_unchanged": True},
        "cleanup": {"status": "passed", "order": ["recorder", "game_wine", "display"],
                    "recorder": "passed", "game_wine": "passed", "display": "passed"},
        "visual_review": {"status": "pending"}, "acceptance_ready": False, "ok": False}
    return receipt


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.run = Path(temporary.name)
        self.master = self.run/'continuous.mp4'
        self.master.write_bytes(b'accepted master frames')
        self.receipt_path = self.run/'creative-run.json'
        self.receipt_path.write_text(json.dumps(completed_receipt(self.run)))
        self.accepted = accept_visual(self.run, reviewer='visual reviewer', media_sha256=R.sha256(self.master), pts_probe=fixture_pts_probe)
        self.original = self.receipt_path.read_bytes()
        self.source_info = {'duration_seconds': 234.666667, 'width': 1024, 'height': 768}

    def export(self, **kwargs):
        return E.export(self.run, route_sha256=self.accepted['visual_review']['route_sha256'],
                        ffprobe_sha256=self.accepted['visual_review']['ffprobe_sha256'],
                        cleanup_ledger_sha256=self.accepted['visual_review']['cleanup_ledger_sha256'], **kwargs)

    def write_receipt(self, receipt):
        self.receipt_path.write_text(json.dumps(receipt))

    def test_verify_and_export_require_independent_selected_route_digest(self):
        wrong = '0' * 64
        self.assertFalse(_verify_acceptance(self.accepted, route_sha256=wrong,
            ffprobe_sha256=self.accepted['visual_review']['ffprobe_sha256'],
            cleanup_ledger_sha256=self.accepted['visual_review']['cleanup_ledger_sha256']))
        with self.assertRaisesRegex(ValueError, 'accepted'):
            E.accepted_receipt(self.run, route_sha256=wrong,
                ffprobe_sha256=self.accepted['visual_review']['ffprobe_sha256'],
                cleanup_ledger_sha256=self.accepted['visual_review']['cleanup_ledger_sha256'])

    def test_verify_and_export_require_independent_configured_ffprobe_digest(self):
        wrong = '0' * 64
        self.assertFalse(_verify_acceptance(self.accepted,
            route_sha256=self.accepted['visual_review']['route_sha256'], ffprobe_sha256=wrong,
            cleanup_ledger_sha256=self.accepted['visual_review']['cleanup_ledger_sha256']))
        with self.assertRaisesRegex(ValueError, 'accepted'):
            E.accepted_receipt(self.run,
                route_sha256=self.accepted['visual_review']['route_sha256'], ffprobe_sha256=wrong,
                cleanup_ledger_sha256=self.accepted['visual_review']['cleanup_ledger_sha256'])

    def test_unresolved_or_malformed_cleanup_ledger_blocks_verify_and_export(self):
        write_cleanup_failure(self.run, 'a' * 32)
        self.assertFalse(verify_acceptance(self.accepted))
        with self.assertRaisesRegex(ValueError, 'accepted'):
            self.export(start_seconds=1, end_seconds=2)
        path = self.run / A.CLEANUP_LEDGER
        path.unlink(); path.symlink_to(self.receipt_path)
        self.assertFalse(verify_acceptance(self.accepted))

    def test_external_cleanup_head_rejects_delete_truncate_replace_and_wrong_digest(self):
        ledger = self.run / A.CLEANUP_LEDGER; original = ledger.read_bytes()
        for replacement in (None, b'{', b'{"schema":1,"records":[]}\n '):
            with self.subTest(replacement=replacement):
                ledger.unlink(missing_ok=True)
                if replacement is not None:
                    ledger.write_bytes(replacement)
                self.assertFalse(verify_acceptance(self.accepted))
                with self.assertRaisesRegex(ValueError, 'accepted'):
                    self.export(start_seconds=1, end_seconds=2)
                ledger.unlink(missing_ok=True); ledger.write_bytes(original)
        self.assertFalse(_verify_acceptance(self.accepted,
            route_sha256=self.accepted['visual_review']['route_sha256'],
            ffprobe_sha256=self.accepted['visual_review']['ffprobe_sha256'],
            cleanup_ledger_sha256='0' * 64))

    def test_verify_and_export_recompute_terminal_and_capture_gates_with_refreshed_digests(self):
        def terminal_regression(value):
            for terminal in (value["capture"]["diagnostics"]["terminal"],
                             value["cadence"]["terminal_progress"]):
                terminal["frame"] = 61
        def hidden_duplicates(value):
            ffmpeg = value["cadence"]["intervals"][0]["ffmpeg"]
            ffmpeg["start_sample"]["dup_frames"] = 100
            ffmpeg["end_sample"]["dup_frames"] = 100
        mutations = (
            lambda value: value.update(capture_gate={"status": "failed", "error": "capture_binding_changed"}),
            terminal_regression, hidden_duplicates,
        )
        for mutate in mutations:
            changed = json.loads(json.dumps(self.accepted)); mutate(changed)
            changed["visual_review"]["execution_receipt_sha256"] = execution_receipt_sha256(changed)
            changed["visual_review"]["acceptance_receipt_sha256"] = acceptance_receipt_sha256(changed)
            with self.subTest(mutate=mutate):
                self.assertFalse(verify_acceptance(changed))
                self.write_receipt(changed)
                with self.assertRaisesRegex(ValueError, "accepted"):
                    E.accepted_receipt(self.run, route_sha256=self.accepted['visual_review']['route_sha256'],
                        ffprobe_sha256=self.accepted['visual_review']['ffprobe_sha256'],
                        cleanup_ledger_sha256=self.accepted['visual_review']['cleanup_ledger_sha256'])

    def encode(self, command, **kwargs):
        Path(command[-1]).write_bytes(('encoded ' + Path(command[-1]).suffix).encode())

    def assert_unpublished(self):
        self.assertEqual(list(self.run.glob('accepted-media-*')), [])
        self.assertEqual(list(self.run.glob('.creative-export-*')), [])
        self.assertFalse((self.run/'media.json').exists())

    def test_reviewed_interval_includes_restoration_and_preserves_accepted_evidence(self):
        # Historical first-marker selection ended before restoration at 218.033333.
        old = R.clip_window(234.666667, {'capture_seconds': 207.117260618})
        self.assertLess(old['start_seconds'] + old['duration_seconds'], 218.033333)
        with mock.patch.object(E, 'probe_video', return_value=self.source_info), \
                mock.patch.object(R, 'probe_video', return_value={'duration_seconds': 20, 'width': 640, 'height': 480}), \
                mock.patch.object(R.subprocess, 'run', side_effect=self.encode) as encoder:
            result = self.export(start_seconds=204, end_seconds=224, gif_fps=24)
        self.assertEqual(result['selected_cleanup_ledger_sha256'],
                         self.accepted['visual_review']['cleanup_ledger_sha256'])
        self.assertEqual(result['accepted_content_artifact_sha256'],
                         self.accepted['cadence']['content']['artifact']['sha256'])
        self.assertEqual(result['accepted_geometry_precondition_sha256'],
                         self.accepted['visual_review']['geometry_precondition_sha256'])
        self.assertEqual(encoder.call_count, 2)
        for call in encoder.call_args_list:
            command = call.args[0]
            self.assertEqual(command[command.index('-ss')+1], '204')
            self.assertEqual(command[command.index('-t')+1], '20')
            encoded_source = Path(command[command.index('-i')+1])
            self.assertEqual(encoded_source.name, 'accepted-master.mp4')
            self.assertNotEqual(encoded_source, self.master)
        self.assertIn('fps=24,', encoder.call_args_list[1].args[0][-4])
        self.assertEqual(result['settings']['gif_fps'], 24)
        self.assertEqual(result['end_seconds'], 224)
        self.assertEqual(result['source_video']['sha256'], self.accepted['media']['continuous']['sha256'])
        self.assertEqual(result['accepted_execution_sha256'], self.accepted['visual_review']['execution_receipt_sha256'])
        self.assertEqual(self.receipt_path.read_bytes(), self.original)
        self.assertTrue(verify_acceptance(json.loads(self.original)))
        for artifact in result['artifacts'].values():
            self.assertEqual(R.sha256(Path(artifact['path'])), artifact['sha256'])
        sidecar = Path(result['artifacts']['representative.mp4']['path']).parent/'export.json'
        self.assertEqual(json.loads(sidecar.read_text()), result)

    def test_pending_rejected_or_tampered_acceptance_never_invokes_encoder(self):
        cases = {
            'pending': lambda value: value.update(ok=False, visual_review={'status': 'pending'}),
            'rejected': lambda value: value.update(ok=False, visual_review={'status': 'rejected'}),
            'execution tamper': lambda value: value['window'].update(pid_start='different'),
            'wrong directory': lambda value: value.update(run_dir=str(self.run/'other')),
            'malformed directory': lambda value: value.update(run_dir=None),
            'legacy': lambda value: value.update(schema=1, backend='linux-wine-k1'),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                value = json.loads(self.original); mutate(value); self.write_receipt(value)
                with mock.patch.object(E, 'probe_video') as probe, mock.patch.object(R.subprocess, 'run') as encoder:
                    with self.assertRaises(ValueError): self.export(start_seconds=204, end_seconds=224)
                    probe.assert_not_called(); encoder.assert_not_called()
                self.assert_unpublished()

    def test_replaced_or_missing_master_never_invokes_encoder(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                self.master.write_bytes(b'replaced')
                if missing: self.master.unlink()
                with mock.patch.object(R.subprocess, 'run') as encoder:
                    with self.assertRaises(ValueError): self.export(start_seconds=204, end_seconds=224)
                    encoder.assert_not_called()
                self.assert_unpublished()

    def test_bad_or_truncated_bounds_never_invoke_encoder(self):
        for start, end in [(-1, 20), (20, 20), (21, 20), (0, 235), (float('nan'), 20),
                           (0, float('inf')), (True, 20), ('204', 224)]:
            with self.subTest(start=start, end=end), mock.patch.object(E, 'probe_video', return_value=self.source_info), \
                    mock.patch.object(R.subprocess, 'run') as encoder:
                with self.assertRaises(ValueError): self.export(start_seconds=start, end_seconds=end)
                encoder.assert_not_called()
                self.assert_unpublished()

    def test_bad_gif_fps_never_invokes_encoder(self):
        for fps in (0, 61, True, 24.5, '25'):
            with self.subTest(fps=fps), mock.patch.object(R.subprocess, 'run') as encoder:
                with self.assertRaises(ValueError): self.export(start_seconds=204, end_seconds=224, gif_fps=fps)
                encoder.assert_not_called()

    def test_provenance_change_while_probing_is_rejected_before_encoding(self):
        def changed(*args):
            self.master.write_bytes(b'changed during probe')
            return self.source_info
        with mock.patch.object(E, 'probe_video', side_effect=changed), mock.patch.object(R.subprocess, 'run') as encoder:
            with self.assertRaises(ValueError): self.export(start_seconds=204, end_seconds=224)
            encoder.assert_not_called()
        self.assert_unpublished()

    def test_provenance_drift_during_render_never_publishes_sidecar(self):
        for change in ('master', 'execution', 'review'):
            with self.subTest(change=change):
                self.master.write_bytes(b'accepted master frames'); self.receipt_path.write_bytes(self.original)
                def encode_and_change(command, **kwargs):
                    self.encode(command)
                    if change == 'master': self.master.write_bytes(b'different frames')
                    else:
                        receipt = json.loads(self.original)
                        if change == 'execution': receipt['window']['pid_start'] = 'different'
                        else: receipt['visual_review']['reviewer'] = 'changed while encoding'
                        self.write_receipt(receipt)
                with mock.patch.object(E, 'probe_video', return_value=self.source_info), \
                        mock.patch.object(R, 'probe_video', return_value={'duration_seconds': 20}), \
                        mock.patch.object(R.subprocess, 'run', side_effect=encode_and_change):
                    with self.assertRaises(ValueError): self.export(start_seconds=204, end_seconds=224)
                self.assert_unpublished()

    def test_encoder_failure_does_not_modify_acceptance_or_publish_partial_output(self):
        with mock.patch.object(E, 'probe_video', return_value=self.source_info), \
                mock.patch.object(R.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'mock-encoder')):
            with self.assertRaises(subprocess.CalledProcessError): self.export(start_seconds=204, end_seconds=224)
        self.assertEqual(self.receipt_path.read_bytes(), self.original)
        self.assert_unpublished()

    def test_master_swap_and_restore_cannot_change_stable_encoder_input(self):
        seen = []
        def encode_with_swap(command, **kwargs):
            source = Path(command[command.index('-i') + 1])
            seen.append(source.read_bytes())
            self.master.write_bytes(b'temporary attacker bytes')
            self.master.write_bytes(b'accepted master frames')
            self.encode(command, **kwargs)
        with mock.patch.object(E, 'probe_video', return_value=self.source_info), \
                mock.patch.object(R, 'probe_video', return_value={'duration_seconds': 20}), \
                mock.patch.object(R.subprocess, 'run', side_effect=encode_with_swap):
            result = self.export(start_seconds=204, end_seconds=224)
        self.assertEqual(seen, [b'accepted master frames', b'accepted master frames'])
        self.assertEqual(result['source_video']['sha256'], R.sha256(self.master))

    def test_truncated_encoded_artifact_is_not_published(self):
        with mock.patch.object(E, 'probe_video', return_value=self.source_info), \
                mock.patch.object(R, 'probe_video', return_value={'duration_seconds': 19}), \
                mock.patch.object(R.subprocess, 'run', side_effect=self.encode):
            with self.assertRaisesRegex(ValueError, 'duration'): self.export(start_seconds=204, end_seconds=224)
        self.assertEqual(self.receipt_path.read_bytes(), self.original)
        self.assert_unpublished()


class BackendTests(unittest.TestCase):
    def test_admission_is_separate_from_host_desktop(self):
        for session, desktop in (("x11", "GNOME"), ("wayland", "KDE")):
            admitted = D.admit_backend(D.GAMESCOPE_BACKEND, facts(session_type=session, desktop=desktop))
            self.assertEqual(admitted.status, "admitted")
        self.assertEqual(admitted.exact_window_capture, "ffmpeg-x11grab-window-id-v1")
        self.assertEqual(D.admit_backend("windows-k1", facts()).status, "refused")
        self.assertEqual(D.admit_backend(D.GAMESCOPE_BACKEND, facts(crostini=True)).status, "refused")

    def test_missing_tool_renderer_or_display_reuse_refuses(self):
        missing = {name: True for name in D.GAMESCOPE_TOOLS}; missing["gamescope"] = False
        self.assertIn("gamescope", D.admit_backend(D.GAMESCOPE_BACKEND,
            facts(executables=missing)).reason)
        self.assertEqual(D.admit_backend(D.GAMESCOPE_BACKEND,
            facts(probes={"dri_present": False})).status, "refused")
        self.assertEqual(D.admit_backend(D.GAMESCOPE_BACKEND, facts(), reuse_display=True).status, "refused")

    def test_environment_drops_host_authority_and_software_overrides(self):
        result = G.isolated_environment({"PATH": "/bin", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0",
            "XAUTHORITY": "/host", "DBUS_SESSION_BUS_ADDRESS": "[REDACTED]", "LIBGL_ALWAYS_SOFTWARE": "1",
            "GALLIUM_DRIVER": "llvmpipe", "LP_NUM_THREADS": "4"},
            {"DISPLAY": ":91", "XAUTHORITY": "[REDACTED]"})
        self.assertEqual(dict(result), {"PATH": "/bin", "DISPLAY": ":91", "XAUTHORITY": "[REDACTED]"})
        with self.assertRaises(TypeError): result["DISPLAY"] = ":0"
        hostile = G.isolated_environment({"PATH": "/bin", "SSH_AUTH_SOCK": "[REDACTED]",
            "LD_PRELOAD": "/attack.so", "PYTHONPATH": "/inject", "XDG_DESKTOP_PORTAL_DIR": "/portal"}, {})
        self.assertEqual(dict(hostile), {"PATH": "/bin"})

    def test_proc_start_parser_handles_spaces_and_parentheses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); proc = root / "9"; proc.mkdir()
            proc.joinpath("stat").write_text("9 (name with ) spaces) S 1 9 9 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 4321 0\n")
            self.assertEqual(D.process_start(9, proc_root=root), "4321")

    def test_nested_host_facts_are_deeply_immutable(self):
        nested = {"renderer": {"names": ["AMD"]}}
        value = facts(probes=nested)
        nested["renderer"]["names"].append("mutated")
        self.assertEqual(value.probes["renderer"]["names"], ("AMD",))
        with self.assertRaises(TypeError): value.probes["renderer"]["new"] = True

    def test_renderer_requires_direct_accelerated_nonsoftware(self):
        good = G.parse_renderer("direct rendering: Yes\nAccelerated: yes\nOpenGL renderer string: AMD Radeon\n")
        self.assertEqual(good["status"], "accelerated")
        for text in ("direct rendering: No\nAccelerated: yes\nOpenGL renderer string: AMD\n",
                     "direct rendering: Yes\nAccelerated: yes\nOpenGL renderer string: llvmpipe\n"):
            with self.assertRaises(RuntimeError): G.parse_renderer(text)

    def test_discovery_freezes_exact_pid_geometry_title_and_authority(self):
        outputs = [types.SimpleNamespace(returncode=0, stdout="42\n"),
            types.SimpleNamespace(returncode=0, stdout="77\nX=1\nY=2\nWIDTH=800\nHEIGHT=600\nTITLE=KotOR\n")]
        target = D.discover_owned_x11_window(FakeLease(), [77], run=mock.Mock(side_effect=outputs),
            monotonic=lambda: 12.5, start_reader=lambda pid: "1234")
        self.assertEqual(target, owned())
        self.assertEqual(target.receipt()["geometry"], [800, 600])
        with self.assertRaises(TypeError): target.environment["DISPLAY"] = ":0"

    def test_discovery_refuses_zero_multiple_foreign_and_dead(self):
        lease = FakeLease()
        for text in ("", "42\n43\n"):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                D.discover_owned_x11_window(lease, [77], run=mock.Mock(return_value=types.SimpleNamespace(returncode=0, stdout=text)),
                    monotonic=lambda: 0, start_reader=lambda pid: "x")
        outputs = [types.SimpleNamespace(returncode=0, stdout="42\n"),
                   types.SimpleNamespace(returncode=0, stdout="88\nWIDTH=800\nHEIGHT=600\n")]
        with self.assertRaisesRegex(RuntimeError, "foreign"):
            D.discover_owned_x11_window(lease, [77], run=mock.Mock(side_effect=outputs),
                monotonic=lambda: 0, start_reader=lambda pid: "x")
        lease.live = False
        with self.assertRaisesRegex(RuntimeError, "not live"):
            D.discover_owned_x11_window(lease, [77], run=mock.Mock(), monotonic=lambda: 0)

    def test_owned_input_uses_same_target_and_authority(self):
        runner = mock.Mock(return_value=types.SimpleNamespace(returncode=0, stdout=""))
        port = OwnedX11Input.from_owned_window(owned(), runner=runner, verifier=lambda target: target)
        port.focus(); port.key("F12")
        self.assertEqual(runner.call_args_list[0].args[0], ["xdotool", "windowfocus", "--sync", "0x2a"])
        self.assertEqual(runner.call_args.kwargs["env"]["DISPLAY"], ":91")

    def test_lease_start_receipt_and_owned_group_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = mock.Mock(pid=200, returncode=0); process.poll.return_value = None
            lease = None
            def popen(command, **kwargs):
                lease.ready_path.write_text(json.dumps({"pid": 201, "start": "child",
                    "environment": {"DISPLAY": ":91",
                                    "WAYLAND_DISPLAY": "gamescope-0"}}))
                return process
            def run(command, **kwargs):
                if command[0] == "glxinfo":
                    return types.SimpleNamespace(returncode=0, stdout="direct rendering: Yes\nAccelerated: yes\nOpenGL renderer string: AMD Radeon\n", stderr="")
                return types.SimpleNamespace(returncode=0, stdout="1024 768\n", stderr="")
            starts = {200: "parent", 201: "child"}
            relationships = {200: (1, 200, 200, "parent"), 201: (200, 200, 200, "child")}
            lease = host_lease(root, 1024, 768, source_env={"PATH": "/bin", "DISPLAY": ":0"},
                popen=popen, run=run, start_reader=lambda pid: starts[pid],
                relationship_reader=lambda pid: relationships[pid], authority_exists=lambda path: True,
                authority_reader=lambda pid: {"DISPLAY": ":91",
                                              "WAYLAND_DISPLAY": "gamescope-0"},
                xwayland_verifier=mock.Mock(return_value={
                    "access_model": "owned-endpoint-host-local-no-cookie"}))
            with mock.patch.object(G, "signal_identity") as killpg:
                killpg.side_effect = lambda *args: relationships.clear()
                lease.start()
                receipt = lease.receipt()
                self.assertEqual(receipt["x11"]["display"], ":91")
                self.assertEqual(receipt["renderer"]["status"], "accelerated")
                self.assertNotIn("/private/auth", json.dumps(receipt))
                lease.close(); lease.close()
            self.assertEqual([(c.args[0].pid, c.args[1]) for c in killpg.call_args_list], [(200, signal.SIGTERM)])
            process.wait.assert_called_once_with(timeout=5)

    def test_early_boot_failure_keeps_atomic_lease_identity_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = mock.Mock(pid=200); process.poll.return_value = 1
            relationships = iter([(1, 200, 200, "parent")])
            def relationship(pid):
                try:
                    return next(relationships)
                except StopIteration as error:
                    raise FileNotFoundError(pid) from error
            lease = host_lease(root, 1024, 768, source_env={"PATH": "/bin"},
                popen=mock.Mock(return_value=process), start_reader=lambda pid: "parent",
                relationship_reader=relationship)
            with mock.patch.object(G, "signal_identity") as killpg, self.assertRaisesRegex(RuntimeError, "exited before readiness"):
                lease.start()
            receipt = json.loads((root / "gamescope-lease.json").read_text())
            self.assertEqual(receipt["boot_phase"], "failed")
            self.assertEqual({key: receipt["owner"]["gamescope"][key]
                              for key in ("pid", "start", "pgid", "session")},
                             {"pid": 200, "start": "parent", "pgid": 200, "session": 200})
            self.assertIsNone(receipt["owner"]["ready_child"])
            self.assertEqual(receipt["cleanup_phase"], "failed")
            self.assertEqual(receipt["socket_cleanup"]["status"], "unknown")
            self.assertEqual(receipt["run_id"], lease.lease_id)
            self.assertEqual([event["sequence"] for event in receipt["events"]], list(range(1, len(receipt["events"]) + 1)))
            killpg.assert_not_called()
            lease.log.close()

    def test_rejected_readiness_child_identity_is_retained_without_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); process = mock.Mock(pid=200); process.poll.return_value = None
            relationships = {200: (1, 200, 200, "parent")}
            lease = None
            def popen(command, **kwargs):
                lease.ready_path.write_text(json.dumps({"pid": 201, "start": "reported-old-start",
                    "environment": {"DISPLAY": ":91", "XAUTHORITY": "[REDACTED]"}}))
                return process
            lease = host_lease(root, 1024, 768, source_env={"PATH": "/bin"}, popen=popen,
                start_reader=lambda pid: "parent" if pid == 200 else "actual-new-start",
                relationship_reader=lambda pid: relationships[pid], authority_exists=lambda path: True)
            with mock.patch.object(G, "signal_identity", side_effect=lambda *_: relationships.clear()):
                with self.assertRaisesRegex(RuntimeError, "identity changed"):
                    lease.start()
            receipt = json.loads((root / "gamescope-lease.json").read_text())
            candidate = receipt["rejected_ready_child"]
            self.assertEqual(candidate["pid"], 201)
            self.assertEqual(candidate["start"], "reported-old-start")
            self.assertEqual(candidate["display"], ":91")
            self.assertNotIn("/private/auth", json.dumps(receipt))
            self.assertEqual(receipt["cleanup_phase"], "passed")

    def test_close_failure_publishes_terminal_failed_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            lease = host_lease(Path(temporary), 800, 600,
                start_reader=lambda pid: "reused", relationship_reader=lambda pid: (1, 200, 200, "reused"))
            lease.process = mock.Mock(pid=200); lease.process.poll.return_value = None
            lease.owner = D.ProcessIdentity(200, "original"); lease.pgid = lease.session_id = 200
            with mock.patch.object(G, "signal_identity") as killpg, self.assertRaisesRegex(RuntimeError, "identity changed"):
                lease.close()
            receipt = json.loads((Path(temporary) / "gamescope-lease.json").read_text())
            self.assertEqual(receipt["cleanup_phase"], "failed")
            self.assertEqual(receipt["events"][-1]["cleanup_phase"], "failed")
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                lease.close()
            self.assertEqual(json.loads(lease.evidence_path.read_text())["cleanup_phase"], "failed")
            killpg.assert_not_called()

    def test_snapshot_refuses_missing_module_and_changed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "harness"; package = source / "kpharness"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("")
            (package / "creative.py").write_text("from . import helper\n")
            (package / "helper.py").write_text("VALUE = 1\n")
            snapshot = S.create_snapshot(source, root / "snapshot", entries=("kpharness.creative",))
            manifest = S.verify_snapshot(snapshot, source_root=source, entries=("kpharness.creative",))
            self.assertEqual([entry["path"] for entry in manifest["files"]],
                             ["kpharness/__init__.py", "kpharness/creative.py", "kpharness/helper.py"])
            self.assertFalse(any(path.name == "retail.asset" for path in snapshot.rglob("*")))
            (package / "helper.py").write_text("VALUE = 2\n")
            with self.assertRaisesRegex(ValueError, "source mismatch"):
                S.verify_snapshot(snapshot, source_root=source, entries=("kpharness.creative",))
            (snapshot / "runtime/kpharness/helper.py").unlink()
            with self.assertRaisesRegex(ValueError, "module digest mismatch"):
                S.verify_snapshot(snapshot, entries=("kpharness.creative",))

    def test_snapshot_driver_uses_snapshot_as_only_harness_import_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "harness"; package = source / "kpharness"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("")
            (package / "creative.py").write_text("PASS = True\n")
            snapshot = S.create_snapshot(source, root / "snapshot", entries=("kpharness.creative",))
            with mock.patch.object(S.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as run:
                self.assertEqual(S.main(["driver", "--snapshot", str(snapshot), "--", "--backend",
                                         D.GAMESCOPE_BACKEND]), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[:4], [str(Path(sys.executable).resolve()), "-I", "-S", "-c"])
            self.assertIn("runpy.run_module('kpharness.creative'", command[4])
            self.assertEqual(command[5:], ["--backend", D.GAMESCOPE_BACKEND])
            self.assertEqual(run.call_args.kwargs["env"]["PYTHONPATH"], str(snapshot / "runtime"))
            self.assertEqual(run.call_args.kwargs["cwd"], str(snapshot))

    def test_snapshot_driver_ignores_injected_cwd_shadow_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "harness"; package = source / "kpharness"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("ORIGIN = 'snapshot'\n")
            (package / "creative.py").write_text(
                "import json, kpharness\nfrom pathlib import Path\n"
                "print(json.dumps({'package': str(Path(kpharness.__file__).resolve()), 'module': str(Path(__file__).resolve())}))\n")
            snapshot = S.create_snapshot(source, root / "snapshot", entries=("kpharness.creative",))
            shadow = root / "shadow" / "kpharness"; shadow.mkdir(parents=True)
            (shadow / "__init__.py").write_text("raise RuntimeError('shadow loaded')\n")
            completed = subprocess.run(S.driver_command(snapshot, []), cwd=shadow.parent,
                env={"PATH": __import__('os').environ["PATH"], "PYTHONPATH": str(shadow.parent)},
                text=True, capture_output=True, check=True)
            origins = json.loads(completed.stdout)
            self.assertTrue(origins["package"].startswith(str(snapshot / "runtime")))
            self.assertTrue(origins["module"].startswith(str(snapshot / "runtime")))

    def test_real_snapshot_resolves_repository_discovery_and_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(S.__file__).resolve().parents[1]
            snapshot = S.create_snapshot(source, Path(temporary) / "snapshot")
            command = S.driver_command(snapshot, [])
            command[4] = command[4].replace("runpy.run_module('kpharness.creative',run_name='__main__')",
                "from kpharness import discover,creative;discover.kpdiscover();creative.retired_script_paths(discover.repo_root());print(discover.repo_root())")
            result = subprocess.run(command, cwd=temporary, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), str(source.parents[1]))
            result = subprocess.run(S.driver_command(snapshot, ["--help"]), cwd=temporary,
                text=True, capture_output=True, check=True)
            self.assertIn("--backend", result.stdout)
            S.verify_snapshot(snapshot)

    def test_readiness_child_import_preserves_snapshot_and_ignores_shadow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = S.create_snapshot(Path(S.__file__).resolve().parents[1], root / "snapshot")
            before = S.verify_snapshot(snapshot)
            shadow = root / "shadow/kpharness"; shadow.mkdir(parents=True)
            (shadow / "__init__.py").write_text("raise RuntimeError('shadow loaded')")
            command = G.readiness_child_command(root / "unused-ready.json", runtime=snapshot / "runtime")
            # Execute the exact production bootstrap without --ready-child: it
            # imports its full closure then exits 2, without writing or waiting.
            result = subprocess.run(command[:-2], cwd=shadow.parent, text=True,
                capture_output=True, env={"PYTHONPATH": str(shadow.parent)})
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("shadow loaded", result.stderr)
            self.assertEqual(S.verify_snapshot(snapshot), before)
            self.assertFalse(list(snapshot.rglob("*.pyc")))

    def test_invalid_authority_retains_observed_candidate_without_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); process = mock.Mock(pid=200); process.poll.return_value = None
            relationships = {200: (1, 200, 200, "parent"), 201: (200, 200, 200, "child")}
            lease = None
            def popen(*args, **kwargs):
                lease.ready_path.write_text(json.dumps({"pid": 201, "start": "child",
                    "environment": {"DISPLAY": ":91"}}))
                return process
            lease = host_lease(root, 800, 600, source_env={}, popen=popen,
                start_reader=lambda pid: "parent" if pid == 200 else "child",
                relationship_reader=lambda pid: relationships[pid],
                authority_reader=lambda pid: {"DISPLAY": ":91"},
                xwayland_verifier=mock.Mock(side_effect=RuntimeError("invalid X11 authority")))
            with mock.patch.object(G, "signal_identity", side_effect=lambda *_: relationships.clear()):
                with self.assertRaisesRegex(RuntimeError, "invalid X11 authority"):
                    lease.start()
            receipt = json.loads(lease.evidence_path.read_text())
            self.assertIsNone(receipt["owner"]["ready_child"])
            self.assertEqual(receipt["rejected_ready_child"]["observed_start"], "child")
            self.assertEqual(receipt["rejected_ready_child"]["relationship"]["parent_pid"], 200)

    def test_snapshot_rejects_unlisted_data_and_special_files(self):
        import os
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); package = root / "source/kpharness"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("")
            (package / "creative.py").write_text("")
            snapshot = S.create_snapshot(root / "source", root / "snapshot", entries=("kpharness.creative",))
            extra = snapshot / "runtime/extra.bin"
            extra.write_bytes(b"unlisted")
            with self.assertRaisesRegex(ValueError, "file list"):
                S.verify_snapshot(snapshot)
            extra.unlink(); os.mkfifo(extra)
            with self.assertRaisesRegex(ValueError, "unexpected file type"):
                S.verify_snapshot(snapshot)

    def test_atomic_evidence_syncs_parent_directory(self):
        import os, stat
        with tempfile.TemporaryDirectory() as temporary:
            synced = []
            real_fsync = os.fsync
            def fsync(fd):
                synced.append(stat.S_ISDIR(os.fstat(fd).st_mode))
                real_fsync(fd)
            lease = host_lease(Path(temporary), 800, 600)
            with mock.patch.object(G.os, "fsync", side_effect=fsync):
                lease._write_evidence(boot_phase="prepared")
            self.assertEqual(synced, [False, True])

    def test_close_refuses_pid_reuse_without_signalling(self):
        with tempfile.TemporaryDirectory() as temporary:
            process = mock.Mock(pid=200); process.poll.return_value = None
            lease = host_lease(Path(temporary), 800, 600,
                start_reader=lambda pid: "reused",
                relationship_reader=lambda pid: (1, 200, 200, "reused"))
            lease.process = process; lease.owner = D.ProcessIdentity(200, "original")
            lease.pgid = lease.session_id = 200
            with mock.patch.object(G, "signal_identity") as killpg, self.assertRaisesRegex(RuntimeError, "identity changed"):
                lease.close()
            killpg.assert_not_called()

    def test_close_cleans_group_when_leader_dead_but_child_live(self):
        with tempfile.TemporaryDirectory() as temporary:
            process = mock.Mock(pid=200); process.poll.return_value = 0
            live = {"child": True}
            def relationship(pid):
                if pid == 200 or not live["child"]: raise FileNotFoundError(pid)
                return (200, 200, 200, "child")
            lease = host_lease(Path(temporary), 800, 600,
                relationship_reader=relationship)
            lease.process = process; lease.owner = D.ProcessIdentity(200, "parent")
            lease.ready_child = D.ProcessIdentity(201, "child")
            lease.pgid = lease.session_id = 200
            with mock.patch.object(G, "signal_identity") as killpg:
                killpg.side_effect = lambda *args: live.update(child=False)
                lease.close()
            self.assertEqual([(c.args[0].pid, c.args[1]) for c in killpg.call_args_list], [(201, signal.SIGTERM)])

    def test_close_retries_until_stubborn_group_is_verified_gone(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = {"value": True}; ticks = {"value": 0}
            def monotonic(): ticks["value"] += 1; return ticks["value"]
            def relationship(pid):
                if not live["value"]: raise FileNotFoundError(pid)
                return (200, 200, 200, "child")
            lease = host_lease(Path(temporary), 800, 600,
                monotonic=monotonic, sleep=lambda seconds: None, relationship_reader=relationship)
            lease.process = mock.Mock(pid=200); lease.process.poll.return_value = 0
            lease.owner = D.ProcessIdentity(200, "child")
            lease.ready_child = D.ProcessIdentity(201, "child"); lease.pgid = lease.session_id = 200
            with mock.patch.object(G, "signal_identity"):
                with self.assertRaisesRegex(RuntimeError, "survived SIGKILL"): lease.close()
                self.assertFalse(lease._closed)
            with mock.patch.object(G, "signal_identity", side_effect=lambda *args: live.update(value=False)):
                lease.close()
            self.assertTrue(lease._closed)

    def test_schema2_stays_false_until_visual_acceptance_and_copies_evidence(self):
        lease = FakeLease()
        lease.receipt = lambda: {"kind": "gamescope-xwayland", "lease_id": "lease-1"}
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        fixture_run = Path(temporary.name); (fixture_run / "continuous.mp4").write_bytes(b"fixture")
        fixture = completed_receipt(fixture_run)
        recorder = {"capture": fixture["capture"], "cadence": fixture["cadence"],
                    "media": fixture["media"],
                    "failure": None}
        kwargs = dict(facts=facts(), capabilities=D.admit_backend(D.GAMESCOPE_BACKEND, facts()),
            lease=lease, window=owned(width=1024, height=768), recorder=recorder, route_passed=True,
            console_correlated=True, cleanup={"status": "passed",
                "order": ["recorder", "game_wine", "display"],
                "recorder": "passed", "game_wine": "passed", "display": "passed"},
            source_unchanged=True, inputs_unchanged=True)
        kwargs.update(route_receipt=fixture["route"], capture_gate={"status": "passed"})
        pending = D.schema2_receipt(**kwargs)
        self.assertEqual(pending["schema"], 2); self.assertFalse(pending["ok"])
        accepted = D.schema2_receipt(**kwargs, visual_status="accepted")
        self.assertTrue(accepted["ok"])
        recorder["capture"]["command"].append("mutated")
        self.assertNotIn("mutated", accepted["capture"]["command"])
        for mutate in (
            lambda value: value["capture"]["authorization"].update(lease_id="other"),
            lambda value: value["capture"]["authorization"]["authorized_surface"].update(id="0xdead"),
            lambda value: value["capture"]["source"].update(input=":999.0"),
            lambda value: value["capture"]["authorization"]["coverage"].update(surface_origin=[1, 0]),
            lambda value: value["cadence"]["intervals"][0].update(effective_fps=10),
        ):
            broken = json.loads(json.dumps(recorder))
            mutate(broken)
            if broken["capture"]["command"][-1] == "mutated": broken["capture"]["command"].pop()
            self.assertFalse(D.schema2_receipt(**{**kwargs, "recorder": broken}, visual_status="accepted")["ok"])
        for command in (
            ["ffmpeg", "-f", "x11grab", "-draw_mouse", "0", "-framerate", "60", "-video_size", "1024x768", "-i", ":91.0"],
            ["ffmpeg", "-f", "x11grab", "-f", "lavfi", "-draw_mouse", "0", "-framerate", "60", "-video_size", "1024x768", "-i", ":91.0"],
            ["ffmpeg", "-f", "x11grab", "-draw_mouse", "0", "-framerate", "60", "-video_size", "1024x768", "-i", ":91.0", "-i", ":666"],
        ):
            broken = json.loads(json.dumps(recorder)); broken["capture"]["command"] = command
            broken["capture"]["command"] = [item for item in command if item != "mutated"]
            self.assertFalse(D.schema2_receipt(**{**kwargs, "recorder": broken}, visual_status="accepted")["ok"])

    def test_visual_acceptance_is_post_capture_and_digest_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / "continuous.mp4"; media.write_bytes(b"frames")
            digest = R.sha256(media)
            skeletal = {"schema": 2, "backend": D.GAMESCOPE_BACKEND, "run_dir": str(run),
                "ok": False, "acceptance_ready": True, "visual_review": {"status": "pending"},
                "media": {"continuous": {"path": str(media), "sha256": digest}}}
            (run / "creative-run.json").write_text(json.dumps(skeletal))
            with self.assertRaisesRegex(ValueError, "execution evidence"):
                accept_visual(run, reviewer="reviewer", media_sha256=digest, pts_probe=fixture_pts_probe)
            receipt = completed_receipt(run)
            (run / "creative-run.json").write_text(json.dumps(receipt))
            accepted = accept_visual(run, reviewer="reviewer", media_sha256=digest, pts_probe=fixture_pts_probe)
            self.assertTrue(verify_acceptance(accepted))
            self.assertEqual(accepted["visual_review"]["media_sha256"], digest)
            self.assertRegex(accepted["visual_review"]["execution_receipt_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(accepted["visual_review"]["acceptance_receipt_sha256"], r"^[0-9a-f]{64}$")
            tampered = json.loads(json.dumps(accepted)); tampered["window"]["pid_start"] = "changed"
            self.assertFalse(verify_acceptance(tampered))
            media.write_bytes(b"post-accept replacement")
            self.assertFalse(verify_acceptance(accepted))
            media.write_bytes(b"frames")
            self.assertTrue(verify_acceptance(accepted))
            for field, value in (("reviewer", "forged"), ("accepted_utc", "2030-01-01T00:00:00+00:00"),
                                 ("scope", "forged scope"), ("pts_artifact_sha256", "0" * 64)):
                tampered_review = json.loads(json.dumps(accepted))
                tampered_review["visual_review"][field] = value
                self.assertFalse(verify_acceptance(tampered_review), field)
            media.unlink()
            self.assertFalse(verify_acceptance(accepted))
            media.write_bytes(b"frames")
            for mutate in (lambda value: value["route"].update(status="failed"),
                           lambda value: value["cleanup"].update(display="failed"),
                           lambda value: value["capture"]["source"].update(input=":666.0"),
                           lambda value: value.pop("finished_utc")):
                broken = json.loads(json.dumps(receipt)); mutate(broken)
                (run / "creative-run.json").write_text(json.dumps(broken))
                with self.assertRaisesRegex(ValueError, "execution evidence"):
                    accept_visual(run, reviewer="reviewer", media_sha256=digest, pts_probe=fixture_pts_probe)
            media.write_bytes(b"changed")
            (run / "creative-run.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "execution evidence|digest"):
                accept_visual(run, reviewer="reviewer", media_sha256=digest, pts_probe=fixture_pts_probe)

    def test_acceptance_reprobes_master_and_rejects_alternative_valid_pts_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / "continuous.mp4"; media.write_bytes(b"frames")
            receipt = completed_receipt(run)
            (run / "creative-run.json").write_text(json.dumps(receipt))
            alternative = [value + .005 for value in
                           json.loads((run / "ffprobe-cadence.json").read_text())["pts_seconds"]]
            with self.assertRaisesRegex(ValueError, "fresh accepted-master probe"):
                accept_visual(run, reviewer="reviewer", media_sha256=R.sha256(media),
                              pts_probe=lambda path, executable, **kwargs: alternative)

            original = json.loads((run / "ffprobe-cadence.json").read_text())["pts_seconds"]
            alternative = [value + .005 for value in original]
            artifact_path = run / "ffprobe-cadence.json"
            artifact = json.loads(artifact_path.read_text()); artifact["pts_seconds"] = alternative
            artifact["frame_count"] = len(alternative)
            artifact_path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n")
            receipt = completed_receipt(run)
            # completed_receipt restored the original artifact; install the coherent alternative once more.
            artifact = json.loads(artifact_path.read_text()); artifact["pts_seconds"] = alternative
            artifact["frame_count"] = len(alternative)
            artifact_path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n")
            receipt["cadence"]["pts_artifact"]["sha256"] = R.sha256(artifact_path)
            receipt["cadence"]["whole_capture"] = R.analyze_pts(alternative, requested_fps=60,
                interval_start=alternative[0], interval_end=alternative[-1], thresholds=R.CadenceThresholds())
            selected = [value for value in alternative if 1 <= value <= 2]
            measured = R.analyze_pts(selected, requested_fps=60, interval_start=1,
                interval_end=2, thresholds=R.CadenceThresholds())
            prior = receipt["cadence"]["intervals"][0]
            measured.update(start_marker="phase_1", end_marker="complete",
                missing_or_dropped_slots=measured["missing_slots"],
                missing_or_dropped_ratio=measured["missing_slots"] / measured["requested_slot_count"],
                ffmpeg=prior["ffmpeg"])
            receipt["cadence"]["intervals"] = [measured]
            receipt["cadence"]["content"] = fixture_content_block(run, media, R.sha256(media),
                receipt["cadence"]["probe_tool"], alternative)
            (run / "creative-run.json").write_text(json.dumps(receipt))
            self.assertTrue(D.execution_evidence_ready(receipt))
            with self.assertRaisesRegex(ValueError, "fresh accepted-master probe"):
                accept_visual(run, reviewer="reviewer", media_sha256=R.sha256(media),
                              pts_probe=lambda path, executable, **kwargs: original)

    def test_acceptance_probe_uses_private_digest_verified_copy_during_public_swap_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / 'continuous.mp4'; media.write_bytes(b'original frames')
            receipt = completed_receipt(run)
            (run / 'creative-run.json').write_text(json.dumps(receipt))
            seen = []
            def probe(stable, executable, *, pass_fds=()):
                stable = Path(stable); seen.append((stable, stable.read_bytes()))
                media.write_bytes(b'attacker replacement')
                media.write_bytes(b'original frames')
                return fixture_pts_probe(stable, executable, pass_fds=pass_fds)
            with self.assertRaisesRegex(ValueError, 'public accepted master changed'):
                accept_visual(run, reviewer='reviewer', media_sha256=R.sha256(media), pts_probe=probe)
            self.assertNotEqual(seen[0][0], media)
            self.assertEqual(seen[0][1], b'original frames')

    def test_acceptance_probe_uses_unlinked_fd_and_detects_private_mutate_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / 'continuous.mp4'; media.write_bytes(b'original frames')
            receipt = completed_receipt(run); (run / 'creative-run.json').write_text(json.dumps(receipt))
            alternative = [value + .005 for value in receipt['cadence']['whole_capture']['included_pts_seconds']]
            observed = {}
            def probe(fd_path, executable, *, pass_fds=()):
                fd = pass_fds[0]; observed['path'] = str(fd_path); observed['nlink'] = os.fstat(fd).st_nlink
                original = Path(fd_path).read_bytes()
                Path(fd_path).write_bytes(b'alternate private bytes')
                Path(fd_path).write_bytes(original)
                return alternative
            with self.assertRaisesRegex(ValueError, 'descriptor changed'):
                accept_visual(run, reviewer='reviewer', media_sha256=R.sha256(media), pts_probe=probe)
            self.assertRegex(observed['path'], r'^/proc/self/fd/[0-9]+$')
            self.assertEqual(observed['nlink'], 0)

    def test_route_report_must_exist_match_digest_and_exact_step_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / 'continuous.mp4').write_bytes(b'frames')
            baseline = completed_receipt(run)
            self.assertTrue(D.execution_evidence_ready(baseline))
            missing = json.loads(json.dumps(baseline)); Path(missing['route']['report']['path']).unlink()
            self.assertFalse(D.execution_evidence_ready(missing))
            baseline = completed_receipt(run)
            fake_hash = json.loads(json.dumps(baseline)); fake_hash['route']['report']['sha256'] = '0' * 64
            self.assertFalse(D.execution_evidence_ready(fake_hash))
            malformed = json.loads(json.dumps(baseline)); malformed['route']['steps'][0]['nonsense'] = {'accepted': True}
            self.assertFalse(D.execution_evidence_ready(malformed))

    def test_route_report_is_bound_to_selected_route_build_target_runtime_and_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / 'continuous.mp4').write_bytes(b'frames')
            baseline = completed_receipt(run); self.assertTrue(D.execution_evidence_ready(baseline))
            report_path = run / 'report.json'
            for mutate in (
                lambda receipt, report: report.update(target='k2', scenario='different', build='different'),
                lambda receipt, report: report.update(steps=[{"index": 1, "step": "do unrelated",
                    "status": "ok", "seconds": .1, "detail": "fabricated"}]),
                lambda receipt, report: report.update(execution={'nonsense': {'accepted': True}}),
                lambda receipt, report: report.update(execution={
                    'game_speed_requested': True, 'game_speed_effective': 16.0}),
                lambda receipt, report: report.update(execution={
                    'game_speed_requested': float('nan'), 'game_speed_effective': 16.0}),
                lambda receipt, report: report.update(execution={
                    'game_speed_requested': 8.0, 'game_speed_effective': 16.0}),
            ):
                receipt = completed_receipt(run); report = json.loads(report_path.read_text())
                mutate(receipt, report); report_path.write_text(json.dumps(report, allow_nan=True))
                receipt['route']['steps'] = report['steps']
                receipt['route']['report']['sha256'] = R.sha256(report_path)
                self.assertFalse(D.execution_evidence_ready(receipt), report)

    def test_probe_tool_identity_cannot_be_selected_by_pts_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / 'continuous.mp4').write_bytes(b'frames')
            receipt = completed_receipt(run); artifact_path = run / 'ffprobe-cadence.json'
            artifact = json.loads(artifact_path.read_text())
            artifact['probe']['resolved_path'] = '/definitely/not/the/producer/tool'
            artifact_path.write_text(json.dumps(artifact))
            receipt['cadence']['pts_artifact']['sha256'] = R.sha256(artifact_path)
            self.assertFalse(D.execution_evidence_ready(receipt))

    def test_external_ffprobe_digest_rejects_coherent_run_local_tool_substitution(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / 'continuous.mp4'; media.write_bytes(b'frames')
            receipt = completed_receipt(run); expected = receipt['cadence']['probe_tool']['sha256']
            tool = run / 'alternate-ffprobe'; shutil.copyfile('/bin/false', tool); tool.chmod(0o700)
            identity = {'command': str(tool), 'resolved_path': str(tool.resolve()), 'sha256': R.sha256(tool)}
            receipt['cadence']['probe_tool'] = identity
            artifact_path = run / 'ffprobe-cadence.json'; artifact = json.loads(artifact_path.read_text())
            artifact['probe'] = {**identity, 'method': 'ffprobe-best-effort-timestamp-time-v1'}
            artifact_path.write_text(json.dumps(artifact)); receipt['cadence']['pts_artifact']['sha256'] = R.sha256(artifact_path)
            rewrite_content_probe(receipt, run, identity)
            self.assertTrue(D.execution_evidence_ready(receipt))
            (run / 'creative-run.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'selected FFprobe digest'):
                _accept_visual(run, commitment_log=COMMIT_LOG, content_probe=fixture_content_probe, reviewer='reviewer', media_sha256=R.sha256(media),
                    route_sha256=receipt['route_source']['sha256'], ffprobe_sha256=expected,
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                    pts_probe=fixture_pts_probe)

    def test_acceptance_executes_retained_native_tool_fd_during_path_swap_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / 'continuous.mp4'; media.write_bytes(b'frames')
            receipt = completed_receipt(run)
            tool = run / 'ffprobe-tool'; shutil.copyfile(Path(sys.executable).resolve(), tool); tool.chmod(0o700)
            identity = {'command': str(tool), 'resolved_path': str(tool.resolve()), 'sha256': R.sha256(tool)}
            receipt['cadence']['probe_tool'] = identity
            artifact_path = run / 'ffprobe-cadence.json'; artifact = json.loads(artifact_path.read_text())
            artifact['probe'] = {**identity, 'method': 'ffprobe-best-effort-timestamp-time-v1'}
            artifact_path.write_text(json.dumps(artifact, sort_keys=True, separators=(',', ':')) + '\n')
            receipt['cadence']['pts_artifact']['sha256'] = R.sha256(artifact_path)
            rewrite_content_probe(receipt, run, identity)
            (run / 'creative-run.json').write_text(json.dumps(receipt))
            seen = {}; original = tool.read_bytes()
            def probe(media_fd_path, tool_fd_path, *, pass_fds=()):
                seen['fds'] = pass_fds; seen['tool'] = Path(tool_fd_path).read_bytes()
                saved = run / 'saved-tool'; tool.rename(saved)
                shutil.copyfile('/bin/false', tool); tool.chmod(0o700)
                tool.unlink(); saved.rename(tool)
                return fixture_pts_probe(media_fd_path, tool_fd_path, pass_fds=pass_fds)
            with self.assertRaisesRegex(ValueError, 'FFprobe executable descriptor changed'):
                _accept_visual(run, commitment_log=COMMIT_LOG, content_probe=fixture_content_probe, reviewer='reviewer', media_sha256=R.sha256(media),
                    route_sha256=receipt['route_source']['sha256'],
                    ffprobe_sha256=identity['sha256'],
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run), pts_probe=probe)
            self.assertEqual(seen['tool'], original)
            for descriptor in seen['fds']:
                with self.assertRaises(OSError): os.fstat(descriptor)

    def test_external_route_digest_rejects_coherent_run_local_route_substitution(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / 'continuous.mp4'; media.write_bytes(b'frames')
            receipt = completed_receipt(run); expected = receipt['route_source']['sha256']
            route_path = run / 'executed-route.toml'
            route_path.write_text('schema_version = 1\nname = "substituted"\ntarget = "k1"\n[[step]]\ndo = "unrelated"\n')
            info = route_path.stat(); route_sha = R.sha256(route_path)
            receipt['route_source'] = {'path': str(route_path), 'sha256': route_sha, 'identity': {
                'device': info.st_dev, 'inode': info.st_ino, 'size': info.st_size,
                'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns, 'links': info.st_nlink}}
            steps = [{'index': 1, 'step': 'do unrelated', 'status': 'ok', 'seconds': .1,
                      'detail': 'substituted'}]
            report_path = run / 'report.json'; report = json.loads(report_path.read_text())
            report.update(scenario='substituted', steps=steps); report_path.write_text(json.dumps(report))
            receipt['route']['steps'] = steps; receipt['route']['report']['sha256'] = R.sha256(report_path)
            receipt['route']['execution_identity'].update(scenario='substituted',
                route_source_sha256=route_sha)
            self.assertTrue(D.execution_evidence_ready(receipt))
            (run / 'creative-run.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'selected route digest'):
                _accept_visual(run, commitment_log=COMMIT_LOG, content_probe=fixture_content_probe, reviewer='reviewer', media_sha256=R.sha256(media),
                    route_sha256=expected, ffprobe_sha256=receipt['cadence']['probe_tool']['sha256'],
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                    pts_probe=fixture_pts_probe)

    def test_route_speed_must_equal_parsed_scenario_setting(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / 'continuous.mp4').write_bytes(b'frames')
            receipt = completed_receipt(run); report_path = run / 'report.json'
            report = json.loads(report_path.read_text())
            report['execution'] = {'game_speed_requested': 8.0, 'game_speed_effective': 8.0}
            report_path.write_text(json.dumps(report)); receipt['route']['report']['sha256'] = R.sha256(report_path)
            self.assertFalse(D.execution_evidence_ready(receipt))

    def test_unreaped_probe_persists_typed_cleanup_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / 'continuous.mp4'; media.write_bytes(b'frames')
            receipt = completed_receipt(run); (run / 'creative-run.json').write_text(json.dumps(receipt))
            child = types.SimpleNamespace(pid=4242, pid_start='fixture-start')
            failure = R.ProbeCleanupError(child, ['/proc/self/fd/9', 'args'], 'survived')
            with self.assertRaisesRegex(ValueError, 'cleanup failed'):
                _accept_visual(run, commitment_log=COMMIT_LOG, content_probe=fixture_content_probe, reviewer='reviewer', media_sha256=R.sha256(media),
                    route_sha256=receipt['route_source']['sha256'],
                    ffprobe_sha256=receipt['cadence']['probe_tool']['sha256'],
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                    pts_probe=lambda *args, **kwargs: (_ for _ in ()).throw(failure))
            ledger, _, failures, resolutions = A._load_cleanup_ledger(run)
            self.assertEqual(len(failures), 1); self.assertEqual(resolutions, {})
            cleanup = next(iter(failures.values()))['payload']
            self.assertEqual((cleanup['pid'], cleanup['pid_start']), (4242, 'fixture-start'))
            self.assertEqual(cleanup['bounded_wait_seconds'], [2, 2])
            with self.assertRaisesRegex(ValueError, 'cleanup evidence blocks'):
                accept_visual(run, reviewer='reviewer', media_sha256=R.sha256(media),
                              pts_probe=fixture_pts_probe)
            second = R.ProbeCleanupError(types.SimpleNamespace(pid=4343, pid_start='second-start'),
                                         ['ffprobe'], 'survived')
            with contextlib.redirect_stderr(io.StringIO()):
                A._persist_probe_cleanup_failure(run, second, receipt['cadence']['probe_tool'],
                    expected_head=A.cleanup_ledger_sha256(run), commitment_log=COMMIT_LOG)
            self.assertEqual(len(A._load_cleanup_ledger(run)[2]), 2)

    def test_cleanup_recovery_is_identity_checked_bounded_and_append_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); identifier = 'b' * 32
            failure = write_cleanup_failure(run, identifier)
            signals = []; closed = []; real_close = os.close
            def close(fd):
                closed.append(fd)
                if fd != 91: real_close(fd)
            with mock.patch.object(A.os, 'close', side_effect=close):
                resolved = A.recover_cleanup(run, commitment_log=COMMIT_LOG, failure_id=identifier,
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                    identity_reader=lambda pid: {'state': 'present', 'start': 'fixture-start'},
                    pidfd_open=lambda pid, flags: 91,
                    pidfd_send_signal=lambda fd, sig, info, flags: signals.append((fd, sig)),
                    pidfd_wait=lambda fd, seconds: True)
            self.assertEqual(resolved['record']['payload']['outcome'], 'pidfd_reaped')
            self.assertEqual(signals, [(91, signal.SIGKILL)]); self.assertEqual(closed[-1], 91)
            self.assertEqual(A._load_cleanup_ledger(run)[2][identifier], failure)
            self.assertTrue(A.cleanup_state_clear(run, resolved['cleanup_ledger_sha256']))

    def test_cleanup_recovery_resolves_pid_reuse_without_signal_and_already_exited(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); mismatch = 'c' * 32
            write_cleanup_failure(run, mismatch)
            opened = mock.Mock(side_effect=AssertionError('reuse proof must not open a pidfd'))
            reused = A.recover_cleanup(run, commitment_log=COMMIT_LOG, failure_id=mismatch,
                cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                identity_reader=lambda pid: {'state': 'present', 'start': 'reused'},
                pidfd_open=opened, pidfd_send_signal=opened)
            opened.assert_not_called()
            self.assertEqual(reused['record']['payload']['outcome'], 'original_exited_pid_reused')
            self.assertEqual((reused['record']['payload']['signal'], reused['record']['payload']['wait']),
                             ('not_sent', 'start_mismatch'))
            self.assertTrue(A.cleanup_state_clear(run, reused['cleanup_ledger_sha256']))
            exited = 'd' * 32; write_cleanup_failure(run, exited, pid=5252, start='gone-start')
            result = A.recover_cleanup(run, commitment_log=COMMIT_LOG, failure_id=exited, cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                identity_reader=lambda pid: {'state': 'absent'})
            self.assertEqual(result['record']['payload']['outcome'], 'already_exited')

    def test_cleanup_ledger_rejects_malformed_symlink_and_orphan_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); init_ledger(run)
            victim = run / 'victim'; victim.write_text('{}'); ledger = run / A.CLEANUP_LEDGER
            ledger.unlink(); ledger.symlink_to(victim)
            self.assertFalse(A.cleanup_state_clear(run))
            ledger.unlink(); ledger.write_text(json.dumps({'schema': 1, 'records': [
                {'schema': 1, 'type': 'resolution'}]}))
            self.assertFalse(A.cleanup_state_clear(run))

    def test_cleanup_chain_rejects_reorder_digest_forgery_and_extra_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); init_ledger(run)
            write_cleanup_failure(run, '1' * 32); write_cleanup_failure(run, '2' * 32)
            path = run / A.CLEANUP_LEDGER; baseline = json.loads(path.read_text())
            mutations = []
            reordered = json.loads(json.dumps(baseline)); reordered['records'].reverse(); mutations.append(reordered)
            forged = json.loads(json.dumps(baseline)); forged['records'][0]['payload']['pid'] += 1; mutations.append(forged)
            extra = json.loads(json.dumps(baseline)); extra['records'][0]['payload']['extra'] = True
            extra['records'][0]['record_digest'] = A._record_digest(extra['records'][0]); mutations.append(extra)
            for value in mutations:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value))
                    self.assertFalse(A.cleanup_state_clear(run))

    def test_cleanup_recovery_refuses_unreadable_reuse_and_missing_pidfd(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); identifier = '3' * 32; write_cleanup_failure(run, identifier)
            head = A.cleanup_ledger_sha256(run)
            for state, message in (({'state': 'unreadable', 'error': 'PermissionError'}, 'unreadable'),
                                   ({'state': 'present', 'start': ''}, 'malformed'),
                                   ({'state': 'present'}, 'malformed')):
                with self.subTest(state=state), self.assertRaisesRegex(ValueError, message):
                    A.recover_cleanup(run, commitment_log=COMMIT_LOG, failure_id=identifier, cleanup_ledger_sha256=head,
                                      identity_reader=lambda pid, value=state: value)
                self.assertEqual(A.cleanup_ledger_sha256(run), head)
            with self.assertRaisesRegex(ValueError, 'pidfd recovery is unavailable'):
                A.recover_cleanup(run, commitment_log=COMMIT_LOG, failure_id=identifier, cleanup_ledger_sha256=head,
                    identity_reader=lambda pid: {'state': 'present', 'start': 'fixture-start'},
                    pidfd_open=None, pidfd_send_signal=None)

    def test_cleanup_identity_reader_distinguishes_absence_permission_and_malformed_stat(self):
        with mock.patch.object(A.os, 'open', side_effect=FileNotFoundError()):
            self.assertEqual(A._process_identity(42), {'state': 'absent'})
        with mock.patch.object(A.os, 'open', side_effect=PermissionError('denied')):
            state = A._process_identity(42)
            self.assertEqual(state['state'], 'unreadable'); self.assertIn('PermissionError', state['error'])
        descriptor = os.open('/dev/null', os.O_RDONLY)
        with mock.patch.object(A.os, 'open', return_value=descriptor), \
                mock.patch.object(A.os, 'read', return_value=b'truncated'):
            state = A._process_identity(42)
            self.assertEqual(state['state'], 'unreadable')

    def test_pidfd_recovery_handles_signal_exit_race_and_repeated_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); identifier = '4' * 32; write_cleanup_failure(run, identifier)
            with mock.patch.object(A.os, 'close', side_effect=pidfd_safe_close(77)):
                result = A.recover_cleanup(run, commitment_log=COMMIT_LOG, failure_id=identifier,
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                    identity_reader=lambda pid: {'state': 'present', 'start': 'fixture-start'},
                    pidfd_open=lambda pid, flags: 77,
                    pidfd_send_signal=lambda *args: (_ for _ in ()).throw(ProcessLookupError()),
                    pidfd_wait=lambda fd, seconds: True)
            self.assertEqual(result['record']['payload']['outcome'], 'signal_error_reaped')
            repeated = A.recover_cleanup(run, commitment_log=COMMIT_LOG, failure_id=identifier,
                cleanup_ledger_sha256=result['cleanup_ledger_sha256'],
                identity_reader=lambda pid: (_ for _ in ()).throw(AssertionError('must not reread')))
            self.assertEqual(repeated['record']['record_digest'], result['record']['record_digest'])

    def test_pidfd_recovery_rechecks_identity_after_open_before_signal(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); identifier = '5' * 32; write_cleanup_failure(run, identifier)
            states = iter(({'state': 'present', 'start': 'fixture-start'},
                           {'state': 'present', 'start': 'reused'}))
            signaler = mock.Mock()
            with mock.patch.object(A.os, 'close', side_effect=pidfd_safe_close(88)), \
                    self.assertRaisesRegex(ValueError, 'while pidfd held'):
                A.recover_cleanup(run, commitment_log=COMMIT_LOG, failure_id=identifier,
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                    identity_reader=lambda pid: next(states), pidfd_open=lambda pid, flags: 88,
                    pidfd_send_signal=signaler, pidfd_wait=lambda fd, seconds: True)
            signaler.assert_not_called(); self.assertFalse(A.cleanup_state_clear(run))

    def test_signal_error_with_bounded_reap_records_resolved_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / 'continuous.mp4'; media.write_bytes(b'frames')
            receipt = completed_receipt(run); (run / 'creative-run.json').write_text(json.dumps(receipt))
            failure = R.ProbeCleanupError(types.SimpleNamespace(pid=6262, pid_start='captured-start'),
                                          ['ffprobe'], 'signal failed then reaped')
            failure.signal_errors = ['PermissionError: denied']; failure.reaped = True
            with self.assertRaisesRegex(ValueError, 'cleanup failed'):
                _accept_visual(run, commitment_log=COMMIT_LOG, content_probe=fixture_content_probe, reviewer='reviewer', media_sha256=R.sha256(media),
                    route_sha256=receipt['route_source']['sha256'],
                    ffprobe_sha256=receipt['cadence']['probe_tool']['sha256'],
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run),
                    pts_probe=lambda *args, **kwargs: (_ for _ in ()).throw(failure))
            _, _, failures, resolutions = A._load_cleanup_ledger(run)
            self.assertEqual(set(failures), set(resolutions)); self.assertTrue(A.cleanup_state_clear(run))
            self.assertEqual(next(iter(resolutions.values()))['payload']['outcome'], 'signal_error_reaped')

    def test_pid_start_parser_handles_spaces_and_embedded_right_parenthesis(self):
        suffix = [str(index) for index in range(3, 22)] + ['424242']
        raw = '123 (worker name ) nested) ' + ' '.join(suffix)
        with mock.patch('builtins.open', mock.mock_open(read_data=raw.encode('latin-1'))):
            self.assertEqual(HS.pid_start(123), '424242')

    def test_probe_cleanup_handles_exit_race_and_signal_failure_with_bounded_wait(self):
        class Child:
            pid = 6262; pid_start = 'start'; stdout = None; returncode = None
            def __init__(self, signal_error): self.signal_error = signal_error; self.waits = []
            def poll(self): return None
            def kill(self): raise self.signal_error
            def wait(self, timeout=None): self.waits.append(timeout); return 0
        raced = Child(ProcessLookupError())
        with self.assertRaisesRegex(OSError, 'stdout pipe'):
            R.probe_frame_pts(Path('/unused'), popen=lambda *args, **kwargs: raced)
        self.assertEqual(raced.waits, [2])
        denied = Child(PermissionError('denied'))
        with self.assertRaises(R.ProbeCleanupError) as caught:
            R.probe_frame_pts(Path('/unused'), popen=lambda *args, **kwargs: denied)
        self.assertIs(caught.exception.process, denied); self.assertEqual(denied.waits, [2])

    def test_probe_frame_pts_caps_child_output_before_reading_it_into_memory(self):
        class FakeProcess:
            returncode = None
            def __init__(self, command, *, stdout, stderr, pass_fds):
                self.stdout = tempfile.TemporaryFile(); self.stdout.truncate(R.MAX_CANONICAL_PTS_BYTES + 1)
                self.stdout.seek(0); self.polls = 0; self.killed = False; self.waited = False
            def poll(self):
                self.polls += 1
                return None if not self.killed else -9
            def kill(self): self.killed = True; self.returncode = -9
            def wait(self, timeout=None): self.waited = True; return self.returncode
        made = []
        def spawn(*args, **kwargs):
            process = FakeProcess(*args, **kwargs); made.append(process); return process
        reads = []; real_read = os.read
        def bounded_read(fd, count):
            block = real_read(fd, count); reads.append((count, len(block))); return block
        with mock.patch.object(R.os, 'read', side_effect=bounded_read), \
                self.assertRaisesRegex(ValueError, 'bounded size'):
            R.probe_frame_pts(Path('/unused'), popen=spawn, sleep=lambda _: None)
        self.assertTrue(made[0].killed and made[0].waited)
        self.assertEqual(sum(size for _, size in reads), R.MAX_CANONICAL_PTS_BYTES + 1)
        self.assertEqual(reads[-1][0], 1)

    def test_probe_cleanup_never_uses_unbounded_wait_and_retains_exact_child(self):
        class Unkillable:
            stdout = None; returncode = None
            def __init__(self): self.kills = 0; self.waits = []
            def poll(self): return None
            def kill(self): self.kills += 1
            def wait(self, timeout=None):
                self.waits.append(timeout); raise subprocess.TimeoutExpired('ffprobe', timeout)
        child = Unkillable()
        with self.assertRaises(R.ProbeCleanupError) as caught:
            R.probe_frame_pts(Path('/unused'), popen=lambda *args, **kwargs: child)
        self.assertIs(caught.exception.process, child)
        self.assertEqual(child.kills, 2)
        self.assertEqual(child.waits, [2, 2])

    def test_probe_command_uses_inherited_native_tool_descriptor_path(self):
        media_fd = os.open(Path(sys.executable).resolve(), os.O_RDONLY)
        tool_fd = os.open(Path(sys.executable).resolve(), os.O_RDONLY)
        seen = {}
        class Done:
            returncode = 0
            def __init__(self, command, *, stdout, stderr, pass_fds):
                seen['command'] = command; seen['pass_fds'] = pass_fds
                self.stdout = tempfile.TemporaryFile()
                self.stdout.write(b'{"frames":[{"best_effort_timestamp_time":"0"},'
                                  b'{"best_effort_timestamp_time":"1"}]}')
                self.stdout.seek(0)
            def poll(self): return 0
        try:
            values = R.probe_frame_pts(Path(f'/proc/self/fd/{media_fd}'),
                str(Path(f'/proc/self/fd/{tool_fd}')), pass_fds=(media_fd, tool_fd), popen=Done)
        finally:
            os.close(media_fd); os.close(tool_fd)
        self.assertEqual(values, [0.0, 1.0])
        self.assertEqual(seen['command'][0], f'/proc/self/fd/{tool_fd}')
        self.assertEqual(seen['pass_fds'], (media_fd, tool_fd))

    def test_acceptance_replaces_hostile_temp_symlink_with_regular_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / "continuous.mp4"; media.write_bytes(b"frames")
            receipt = completed_receipt(run)
            path = run / "creative-run.json"; path.write_text(json.dumps(receipt))
            victim = run / "victim"; victim.write_text("unchanged")
            (run / "creative-run.json.tmp").symlink_to(victim)
            accepted = accept_visual(run, reviewer="reviewer", media_sha256=R.sha256(media), pts_probe=fixture_pts_probe)
            self.assertEqual(victim.read_text(), "unchanged")
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertTrue(verify_acceptance(json.loads(path.read_text())))
            self.assertTrue(verify_acceptance(accepted))

    def test_acceptance_and_export_reject_receipt_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); media = run / "continuous.mp4"; media.write_bytes(b"frames")
            pending = completed_receipt(run)
            real = run / "receipt-target"; real.write_text(json.dumps(pending))
            (run / "creative-run.json").symlink_to(real)
            with self.assertRaisesRegex(ValueError, "regular non-symlink"):
                accept_visual(run, reviewer="reviewer", media_sha256=R.sha256(media), pts_probe=fixture_pts_probe)
            with self.assertRaisesRegex(ValueError, "regular non-symlink"):
                E.accepted_receipt(run, route_sha256=pending['route_source']['sha256'],
                    ffprobe_sha256=pending['cadence']['probe_tool']['sha256'],
                    cleanup_ledger_sha256=A.cleanup_ledger_sha256(run))

    def test_execution_gate_recomputes_markers_command_counters_and_arithmetic(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / "continuous.mp4").write_bytes(b"frames")
            baseline = completed_receipt(run)
            self.assertTrue(D.execution_evidence_ready(baseline))
            mutations = (
                lambda value: value["capture"].update(markers=[]),
                lambda value: value["capture"].update(markers=list(reversed(value["capture"]["markers"]))),
                lambda value: value["capture"]["command"].extend(["-r", "1"]),
                lambda value: value["capture"]["diagnostics"]["terminal"].update(drop_frames=999),
                lambda value: value["cadence"]["intervals"][0].update(
                    frame_count=2, inter_frame_count=1, span_seconds=10.0,
                    requested_slot_count=600, missing_slots=599),
                lambda value: value["cadence"]["intervals"][0]["ffmpeg"].update(drop_frames=1),
            )
            for mutate in mutations:
                broken = json.loads(json.dumps(baseline)); mutate(broken)
                self.assertFalse(D.execution_evidence_ready(broken), broken)

    def test_execution_gate_rejects_failed_route_gate_command_and_unbounded_cadence(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / "continuous.mp4").write_bytes(b"frames")
            baseline = completed_receipt(run)
            mutations = (
                lambda value: value["capture_gate"].update(status="failed"),
                lambda value: value["route"].update(predicates_passed=False),
                lambda value: value["route"]["steps"][0].update(status="failed"),
                lambda value: value["route"].update(steps=[]),
                lambda value: value["capture"]["command"].pop(),
                lambda value: value["capture"]["command"].append("/tmp/evil.mp4"),
                lambda value: value["capture"]["command"].__setitem__(
                    value["capture"]["command"].index("-draw_mouse"), "-bad"),
                lambda value: value["cadence"]["terminal_progress"].update(dup_frames=1),
                lambda value: value["capture"]["diagnostics"]["terminal"].update(dup_frames=1),
                lambda value: value["cadence"]["intervals"][0].update(maximum_gap_seconds=-1),
                lambda value: value["cadence"]["intervals"][0].update(maximum_gap_seconds=float("nan")),
                lambda value: value["cadence"]["intervals"][0]["interval_histogram_ticks"].update({"1": 59}),
                lambda value: value["capture"]["markers"][0].update(detected_monotonic=200),
                lambda value: value["cadence"]["intervals"][0]["ffmpeg"]["start_sample"].update(capture_seconds=1.5),
                lambda value: value["cadence"]["intervals"][0]["ffmpeg"]["end_sample"].update(capture_seconds=.5),
                lambda value: value["cadence"]["intervals"][0]["ffmpeg"]["end_sample"].update(drop_frames=1),
            )
            self.assertTrue(D.execution_evidence_ready(baseline))
            outside_interval_drops = json.loads(json.dumps(baseline))
            outside_interval_drops["capture"]["diagnostics"]["terminal"]["drop_frames"] = 999
            outside_interval_drops["cadence"]["terminal_progress"]["drop_frames"] = 999
            self.assertTrue(D.execution_evidence_ready(outside_interval_drops))
            for mutate in mutations:
                broken = json.loads(json.dumps(baseline)); mutate(broken)
                with self.subTest(mutate=mutate):
                    self.assertFalse(D.execution_evidence_ready(broken), broken)

    def test_execution_gate_rejects_policy_pts_terminal_and_fd_role_contradictions(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / "continuous.mp4").write_bytes(b"frames")
            baseline = completed_receipt(run)

            def relaxed_bad_cadence(value):
                pts = [1 + index / 10 for index in range(11)]
                measured = R.analyze_pts(pts, requested_fps=60, interval_start=1,
                                         interval_end=2, thresholds=R.CadenceThresholds())
                measured.update(start_marker="phase_1", end_marker="complete", status="passed",
                    missing_or_dropped_slots=measured["missing_slots"],
                    missing_or_dropped_ratio=measured["missing_slots"] / measured["requested_slot_count"],
                    ffmpeg=value["cadence"]["intervals"][0]["ffmpeg"])
                value["cadence"]["intervals"] = [measured]
                value["cadence"]["thresholds"] = {
                    "minimum_rate_ratio": .1, "maximum_drop_ratio": 1.0, "maximum_gap_seconds": 1.0}
                value["cadence"]["policy"].update(
                    minimum_rate_ratio=.1, maximum_drop_ratio=1.0, maximum_gap_seconds=1.0)

            def displace_pts(value):
                interval = value["cadence"]["intervals"][0]
                interval["included_pts_seconds"] = [item + 100 for item in interval["included_pts_seconds"]]
                interval["first_included_pts"] += 100; interval["last_included_pts"] += 100

            def terminal_frame_regression(value):
                for terminal in (value["capture"]["diagnostics"]["terminal"],
                                 value["cadence"]["terminal_progress"]):
                    terminal["frame"] = 61

            def hidden_duplicates(value):
                ffmpeg = value["cadence"]["intervals"][0]["ffmpeg"]
                ffmpeg["start_sample"]["dup_frames"] = 100
                ffmpeg["end_sample"]["dup_frames"] = 100

            def alias_fds(value):
                value["capture"]["command"][-1] = "/proc/self/fd/8/continuous.mp4"
                value["capture"]["transport"]["output"]["directory_fd"] = 8

            def lowered_requested_rate(value):
                value["capture"]["capture_sampling_fps_requested"] = 30
                command = value["capture"]["command"]
                command[command.index("-framerate") + 1] = "30"
                value["cadence"]["requested_fps"] = 30
                value["cadence"]["policy"]["requested_fps"] = 30

            mutations = (
                relaxed_bad_cadence,
                lowered_requested_rate,
                displace_pts,
                lambda value: value["cadence"]["intervals"].append(
                    {**json.loads(json.dumps(value["cadence"]["intervals"][0])), "status": "failed"}),
                lambda value: value["cadence"].update(whole_capture={"status": "passed"}),
                lambda value: [terminal.update(out_time_us=0) for terminal in
                    (value["capture"]["diagnostics"]["terminal"], value["cadence"]["terminal_progress"])],
                terminal_frame_regression,
                hidden_duplicates,
                alias_fds,
                lambda value: (value["capture"]["command"].__setitem__(9, "/proc/self/fd/2"),
                               value["capture"]["transport"]["progress"].update(fd=2)),
                lambda value: value["capture"]["transport"]["progress"].update(fd=77),
            )
            self.assertTrue(D.execution_evidence_ready(baseline))
            with_route = json.loads(json.dumps(baseline))
            with_route["route"]["capture_interval"] = {"start_seconds": .5, "end_seconds": 1.5}
            canonical = json.loads(Path(with_route["cadence"]["pts_artifact"]["path"]).read_text())["pts_seconds"]
            with_route["cadence"]["route_interval"] = R.analyze_pts(canonical,
                requested_fps=60, interval_start=.5, interval_end=1.5,
                thresholds=R.CadenceThresholds())
            self.assertTrue(D.execution_evidence_ready(with_route))
            with_route["route"]["capture_interval"]["end_seconds"] = 1.6
            self.assertFalse(D.execution_evidence_ready(with_route))
            for mutate in mutations:
                broken = json.loads(json.dumps(baseline)); mutate(broken)
                with self.subTest(mutate=mutate):
                    self.assertFalse(D.execution_evidence_ready(broken), broken)

    def test_execution_gate_binds_canonical_probe_markers_progress_and_whole_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); (run / "continuous.mp4").write_bytes(b"frames")
            baseline = completed_receipt(run)
            def replace_whole(value):
                pts = [3 + index / 60 for index in range(61)]
                value["cadence"]["whole_capture"] = R.analyze_pts(pts, requested_fps=60,
                    interval_start=3, interval_end=4, thresholds=R.CadenceThresholds())
            def invent_marker(value):
                value["capture"]["markers"].append({"name": "post", "pattern": "post", "line": "post",
                    "native_log_byte_end": 30, "detected_monotonic": 12.5, "capture_seconds": 2.5,
                    "poll_interval_ms": 100, "uncertainty_ms": 100, "sequence": 3})
            def insufficient_terminal(value):
                pts = [index / 60 for index in range(1201)]
                value["cadence"]["whole_capture"] = R.analyze_pts(pts, requested_fps=60,
                    interval_start=0, interval_end=20, thresholds=R.CadenceThresholds())
                for terminal in (value["capture"]["diagnostics"]["terminal"],
                                 value["cadence"]["terminal_progress"]):
                    terminal.update(frame=600, out_time_us=20_000_000)
            mutations = (
                lambda value: value["cadence"]["whole_capture"].update(start_capture_seconds=-1),
                replace_whole,
                invent_marker,
                lambda value: value["cadence"].update(route_interval={"status": "passed", "nonsense": True}),
                lambda value: [sample.update(frame=0, out_time_us=0) for sample in
                    (value["cadence"]["intervals"][0]["ffmpeg"]["start_sample"],
                     value["cadence"]["intervals"][0]["ffmpeg"]["end_sample"])],
                insufficient_terminal,
                lambda value: value["cadence"]["pts_artifact"].update(sha256="0" * 64),
                lambda value: value["cadence"]["policy_scope"].update(ffmpeg_drop_delta="whole_capture"),
            )
            self.assertTrue(D.execution_evidence_ready(baseline))
            for mutate in mutations:
                broken = json.loads(json.dumps(baseline)); mutate(broken)
                with self.subTest(mutate=mutate):
                    self.assertFalse(D.execution_evidence_ready(broken), broken)


def canonical_ledger_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def rechain(ledger):
    """Recompute record digests and links, as a same-user forger would."""
    previous = ledger['records'][0]['prev_digest'] if ledger['records'] else None
    for record in ledger['records']:
        record['prev_digest'] = previous
        record['record_digest'] = A._record_digest(record)
        previous = record['record_digest']
    return ledger


class CleanupLedgerHeadTests(unittest.TestCase):
    """R9-1: the only head source is tool output or the operator commitment log."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.run = self.base / 'run'; self.run.mkdir()
        self.operator = self.base / 'operator'; self.operator.mkdir()
        self.log = self.operator / 'commitments.log'; self.log.touch()
        self.media = self.run / 'continuous.mp4'; self.media.write_bytes(b'frames')

    def initialize(self, run=None, log=None):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            A.initialize_cleanup_ledger(run or self.run, commitment_log=log or self.log)
        return head_lines(stderr.getvalue())

    def logged(self, run=None):
        run = str(Path(run or self.run).resolve())
        return [line for line in head_lines(self.log.read_text()) if line['run_dir'] == run]

    def receipt(self):
        receipt = completed_receipt(self.run)
        (self.run / 'creative-run.json').write_text(json.dumps(receipt))
        return receipt

    def cli_accept(self, head, probe):
        receipt = json.loads((self.run / 'creative-run.json').read_text())
        argv = [str(self.run), '--reviewer', 'reviewer', '--media-sha256', R.sha256(self.media),
                '--route-sha256', receipt['route_source']['sha256'],
                '--ffprobe-sha256', receipt['cadence']['probe_tool']['sha256'],
                '--cleanup-ledger-sha256', head, '--cleanup-commitment-log', str(self.log)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(A, 'probe_frame_pts', probe), \
                mock.patch.object(A, 'probe_frame_content', fixture_content_probe, create=True), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = A.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def fail_acceptance_through_cli(self):
        """Record one surviving child; return (launch line, failure line) from tool output only."""
        launch = self.initialize()
        self.assertEqual(len(launch), 1)
        self.receipt()
        survivor = R.ProbeCleanupError(types.SimpleNamespace(pid=4242, pid_start='fixture-start'),
                                       ['ffprobe'], 'survived')
        def probe(*args, **kwargs):
            raise survivor
        code, stdout, stderr = self.cli_accept(launch[0]['cleanup_ledger_sha256'], probe)
        self.assertNotEqual(code, 0)
        emitted = head_lines(stderr)
        self.assertEqual(len(emitted), 1, stderr)
        failure = emitted[0]
        self.assertEqual(failure['event'], 'acceptance_failure')
        self.assertRegex(failure['failure_id'], r'^[0-9a-f]{32}$')
        result = json.loads(stdout.strip().splitlines()[-1])
        self.assertFalse(result['ok'])
        self.assertEqual(result['failure_id'], failure['failure_id'])
        self.assertEqual(result['cleanup_ledger_sha256'], failure['cleanup_ledger_sha256'])
        self.assertIn(failure['failure_id'], result['error'])
        self.assertIn(failure['cleanup_ledger_sha256'], result['error'])
        self.assertEqual(self.logged()[-1], failure)
        return launch[0], failure

    def assert_refused_with_logged_head(self):
        head = self.logged()[-1]['cleanup_ledger_sha256']
        code, stdout, _ = self.cli_accept(head, fixture_pts_probe)
        self.assertNotEqual(code, 0)
        self.assertFalse(json.loads(stdout.strip().splitlines()[-1])['ok'])
        self.assertFalse(A.cleanup_state_clear(self.run, head))
        receipt = json.loads((self.run / 'creative-run.json').read_text())
        self.assertEqual(receipt['visual_review']['status'], 'pending')

    def test_launch_heads_are_unique_per_run_and_emitted_before_use(self):
        first = self.initialize()
        other = self.base / 'other-run'; other.mkdir()
        second = self.initialize(other)
        self.assertEqual((len(first), len(second)), (1, 1))
        self.assertNotEqual(first[0]['cleanup_ledger_sha256'], second[0]['cleanup_ledger_sha256'])
        self.assertNotEqual(first[0]['nonce'], second[0]['nonce'])
        self.assertEqual(first[0]['event'], 'run_initialized')
        self.assertEqual((first[0]['sequence'], first[0]['failure_id']), (0, None))
        self.assertEqual(self.logged(), first)
        self.assertEqual(self.logged(other), second)

    def test_commitment_log_must_exist_outside_run_and_never_link(self):
        inside = self.run / 'commitments.log'; inside.touch()
        linked = self.operator / 'linked.log'; linked.symlink_to(inside)
        hardlinked = self.operator / 'hardlinked.log'; os.link(inside, hardlinked)
        missing = self.operator / 'missing.log'
        for candidate in (inside, linked, hardlinked, missing, None):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(ValueError, 'commitment log'):
                    A.initialize_cleanup_ledger(self.run, commitment_log=candidate)
                self.assertFalse((self.run / A.CLEANUP_LEDGER).exists())
        self.assertEqual(inside.read_text(), '')

    def test_failed_acceptance_cli_prints_failure_id_and_head_and_exits_nonzero(self):
        launch, failure = self.fail_acceptance_through_cli()
        self.assertNotEqual(launch['cleanup_ledger_sha256'], failure['cleanup_ledger_sha256'])
        self.assertEqual(failure['sequence'], 1)
        self.assertFalse(A.cleanup_state_clear(self.run, failure['cleanup_ledger_sha256']))
        _, raw, failures, _ = A._load_cleanup_ledger(self.run)
        self.assertEqual(list(failures), [failure['failure_id']])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), failure['cleanup_ledger_sha256'])
        self.assertIsNotNone(A.CleanupLedgerChanged)

    def test_rollback_to_fresh_empty_ledger_is_refused_with_logged_head(self):
        launch, _ = self.fail_acceptance_through_cli()
        path = self.run / A.CLEANUP_LEDGER
        path.unlink()
        attacker_log = self.operator / 'attacker.log'; attacker_log.touch()
        with contextlib.redirect_stderr(io.StringIO()):
            fresh = A.initialize_cleanup_ledger(self.run, commitment_log=attacker_log)
        self.assertNotEqual(fresh, launch['cleanup_ledger_sha256'])
        self.assertTrue(A.cleanup_state_clear(self.run, fresh))
        self.assert_refused_with_logged_head()

    def test_reset_to_exact_launch_bytes_is_refused_with_logged_head(self):
        launch, failure = self.fail_acceptance_through_cli()
        path = self.run / A.CLEANUP_LEDGER
        ledger = json.loads(path.read_text())
        ledger['records'] = []
        path.write_bytes(canonical_ledger_bytes(ledger))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), launch['cleanup_ledger_sha256'])
        self.assert_refused_with_logged_head()
        self.assertTrue(A.cleanup_state_clear(self.run, launch['cleanup_ledger_sha256']))

    def test_forged_failure_resolution_pair_is_refused_with_logged_head(self):
        self.fail_acceptance_through_cli()
        path = self.run / A.CLEANUP_LEDGER
        ledger = json.loads(path.read_text())
        failure = ledger['records'][0]
        forged = {'schema': failure['schema'], 'type': 'resolution', 'sequence': 2,
                  'id': failure['id'], 'prev_digest': failure['record_digest'],
                  'timestamp_utc': failure['timestamp_utc'],
                  'payload': {'failure_id': failure['id'], 'failure_digest': failure['record_digest'],
                              'pid': failure['payload']['pid'], 'pid_start': failure['payload']['pid_start'],
                              'outcome': 'already_exited', 'pidfd': 'not_needed', 'signal': 'not_sent',
                              'wait': 'confirmed_absent'}}
        ledger['records'].append(forged)
        path.write_bytes(canonical_ledger_bytes(rechain(ledger)))
        forged_head = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertTrue(A.cleanup_state_clear(self.run, forged_head))
        self.assert_refused_with_logged_head()

    def test_deleted_ledger_is_refused_with_logged_head(self):
        self.fail_acceptance_through_cli()
        (self.run / A.CLEANUP_LEDGER).unlink()
        self.assert_refused_with_logged_head()

    def test_recovery_cli_emits_resolution_head_and_catches_refusal(self):
        _, failure = self.fail_acceptance_through_cli()
        argv = [str(self.run), '--recover-cleanup', failure['failure_id'],
                '--cleanup-ledger-sha256', '0' * 64, '--cleanup-commitment-log', str(self.log)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertNotEqual(A.main(argv), 0)
        self.assertFalse(json.loads(stdout.getvalue().strip().splitlines()[-1])['ok'])
        self.assertEqual(head_lines(stderr.getvalue()), [])
        argv[4] = failure['cleanup_ledger_sha256']
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(A, '_process_identity', return_value={'state': 'absent'}), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(A.main(argv), 0)
        emitted = head_lines(stderr.getvalue())
        self.assertEqual([line['event'] for line in emitted], ['recovery_resolution'])
        self.assertEqual(emitted[0]['failure_id'], failure['failure_id'])
        self.assertEqual(self.logged()[-1], emitted[0])
        self.assertTrue(A.cleanup_state_clear(self.run, emitted[0]['cleanup_ledger_sha256']))

    def resolved_ledger(self):
        launch = self.initialize()[0]
        identifier = 'e' * 32
        write = lambda: write_cleanup_failure(self.run, identifier)
        write()
        head = A.cleanup_ledger_sha256(self.run)
        with contextlib.redirect_stderr(io.StringIO()):
            resolved = A.recover_cleanup(self.run, identifier, cleanup_ledger_sha256=head,
                commitment_log=self.log, identity_reader=lambda pid: {'state': 'absent'})
        self.assertTrue(A.cleanup_state_clear(self.run, resolved['cleanup_ledger_sha256']))
        return json.loads((self.run / A.CLEANUP_LEDGER).read_text())

    def test_exact_schema_rejects_standins_nondicts_duplicates_noncanonical_and_time_order(self):
        baseline = self.resolved_ledger()
        path = self.run / A.CLEANUP_LEDGER
        def mutated(change, *, chain=True):
            value = json.loads(json.dumps(baseline)); change(value)
            return canonical_ledger_bytes(rechain(value) if chain else value)
        early = lambda value: value['records'][1].update(timestamp_utc='2000-01-01T00:00:00.000000+00:00')
        cases = {
            'ledger_schema_float': mutated(lambda value: value.update(schema=float(value['schema']))),
            'ledger_schema_bool': mutated(lambda value: value.update(schema=True)),
            'record_schema_bool': mutated(lambda value: value['records'][0].update(schema=True)),
            'record_schema_float': mutated(lambda value: value['records'][0].update(schema=1.0)),
            'sequence_bool': mutated(lambda value: value['records'][0].update(sequence=True)),
            'sequence_float': mutated(lambda value: value['records'][1].update(sequence=2.0)),
            'waits_float': mutated(lambda value: value['records'][0]['payload'].update(
                bounded_wait_seconds=[2.0, 2.0])),
            'failure_pid_float': mutated(lambda value: (value['records'][0]['payload'].update(pid=4242.0),
                value['records'][1]['payload'].update(pid=4242.0))),
            'resolution_pid_float': mutated(lambda value: value['records'][1]['payload'].update(pid=4242.0)),
            'resolution_payload_int': mutated(lambda value: value['records'][1].update(payload=5)),
            'failure_payload_list': mutated(lambda value: value['records'][0].update(payload=[])),
            'unhashable_failure_id': mutated(lambda value: value['records'][1]['payload'].update(
                failure_id=['e' * 32])),
            'zulu_timestamp': mutated(lambda value: value['records'][0].update(
                timestamp_utc=value['records'][0]['timestamp_utc'].replace('+00:00', 'Z'))),
            'no_microseconds': mutated(lambda value: value['records'][0].update(
                timestamp_utc=value['records'][0]['timestamp_utc'][:19] + '+00:00')),
            'resolution_before_failure': mutated(early),
            'noncanonical_whitespace': json.dumps(baseline, sort_keys=True, indent=1).encode() + b'\n',
            'noncanonical_key_order': (json.dumps(dict(reversed(list(baseline.items()))),
                                                  separators=(',', ':')) + '\n').encode(),
        }
        duplicate = canonical_ledger_bytes(baseline)
        cases['duplicate_keys'] = duplicate.replace(b'{"nonce"', b'{"schema":2,"nonce"', 1)
        self.assertNotEqual(cases['duplicate_keys'], duplicate)
        for name, raw in cases.items():
            with self.subTest(name=name):
                path.write_bytes(raw)
                head = hashlib.sha256(raw).hexdigest()
                self.assertIs(A.cleanup_state_clear(self.run, head), False)
                with self.assertRaises(ValueError):
                    A._load_cleanup_ledger(self.run)

    def test_append_is_serialized_by_lock_and_refuses_stale_supplied_head(self):
        launch = self.initialize()[0]['cleanup_ledger_sha256']
        payload = {'failure_type': 'ffprobe_cleanup_failed', 'identity': 'exact', 'pid': 4242,
            'pid_start': 'fixture-start', **A._host_identity(), 'command': ['ffprobe'],
            'tool': {'command': 'ffprobe', 'resolved_path': '/usr/bin/ffprobe', 'sha256': '1' * 64},
            'bounded_wait_seconds': [2, 2], 'signal_errors': [], 'recovery': A.RECOVERY_REQUIREMENT}
        append = lambda head: A._append_cleanup_record(self.run, 'failure', payload,
            expected_head=head, commitment_log=self.log, event='acceptance_failure')
        holder = os.open(self.run, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(holder, fcntl.LOCK_EX)
            with mock.patch.object(A, 'LEDGER_LOCK_TIMEOUT_SECONDS', .2), \
                    self.assertRaisesRegex(ValueError, 'lock'):
                append(launch)
        finally:
            os.close(holder)
        self.assertEqual(len(self.logged()), 1)
        with contextlib.redirect_stderr(io.StringIO()):
            record, head = append(launch)
        # A second concurrent caller that also read the launch head cannot extend
        # or overwrite the chain, so no record is silently lost.
        with self.assertRaisesRegex(ValueError, 'head'):
            append(launch)
        _, raw, failures, _ = A._load_cleanup_ledger(self.run)
        self.assertEqual(list(failures), [record['id']])
        self.assertEqual(self.logged()[-1]['cleanup_ledger_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(head, hashlib.sha256(raw).hexdigest())

    def test_surviving_child_without_start_identity_blocks_permanently(self):
        launch = self.initialize()[0]['cleanup_ledger_sha256']
        receipt = self.receipt()
        survivor = R.ProbeCleanupError(types.SimpleNamespace(pid=4242, pid_start=''), ['ffprobe'], 'survived')
        survivor.pid_start = ''
        with self.assertRaises(A.CleanupLedgerChanged) as caught, \
                contextlib.redirect_stderr(io.StringIO()):
            _accept_visual(self.run, commitment_log=self.log, content_probe=fixture_content_probe, reviewer='reviewer',
                media_sha256=R.sha256(self.media), route_sha256=receipt['route_source']['sha256'],
                ffprobe_sha256=receipt['cadence']['probe_tool']['sha256'],
                cleanup_ledger_sha256=launch,
                pts_probe=lambda *args, **kwargs: (_ for _ in ()).throw(survivor))
        head = self.logged()[-1]['cleanup_ledger_sha256']
        self.assertEqual(caught.exception.cleanup_ledger_sha256, head)
        _, _, failures, resolutions = A._load_cleanup_ledger(self.run)
        payload = failures[caught.exception.failure_id]['payload']
        self.assertEqual((payload['identity'], payload['pid_start']), ('unavailable', ''))
        self.assertEqual(resolutions, {})
        self.assertFalse(A.cleanup_state_clear(self.run, head))
        with self.assertRaisesRegex(ValueError, 'unrecoverable'):
            A.recover_cleanup(self.run, caught.exception.failure_id, cleanup_ledger_sha256=head,
                commitment_log=self.log, identity_reader=lambda pid: {'state': 'absent'})
        self.assertEqual(self.logged()[-1]['cleanup_ledger_sha256'], head)

    def test_recovery_refuses_other_boot_or_pid_namespace_before_concluding_absence(self):
        self.initialize(); identifier = 'f' * 32
        write_cleanup_failure(self.run, identifier)
        head = A.cleanup_ledger_sha256(self.run); host = A._host_identity()
        for field in ('boot_id', 'pid_namespace'):
            with self.subTest(field=field):
                other = {**host, field: host[field] + '-other'}
                reader = mock.Mock(return_value={'state': 'absent'})
                with self.assertRaisesRegex(ValueError, 'boot|namespace'):
                    A.recover_cleanup(self.run, identifier, cleanup_ledger_sha256=head,
                        commitment_log=self.log, identity_reader=reader, host_reader=lambda: other)
                reader.assert_not_called()
                self.assertEqual(A.cleanup_ledger_sha256(self.run), head)
        with self.assertRaisesRegex(ValueError, 'boot|namespace'):
            A.recover_cleanup(self.run, identifier, cleanup_ledger_sha256=head, commitment_log=self.log,
                identity_reader=lambda pid: {'state': 'absent'},
                host_reader=lambda: {'boot_id': '', 'pid_namespace': ''})


    # -- Round 11 (R10-1 adversarial / R10-2 correctness): a surviving FFprobe
    # child is always recorded, whatever happens to the commitment log.

    def survivor_during_probe(self, mutate):
        launch = self.initialize()[0]
        self.receipt()
        survivor = R.ProbeCleanupError(types.SimpleNamespace(pid=4242, pid_start='fixture-start'),
                                       ['ffprobe', '-v', 'error'], 'survived')
        def probe(*args, **kwargs):
            mutate()
            raise survivor
        code, stdout, stderr = self.cli_accept(launch['cleanup_ledger_sha256'], probe)
        return launch, code, json.loads(stdout.strip().splitlines()[-1]), stderr

    @staticmethod
    def survivor_lines(stderr):
        lines = []
        for line in stderr.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict) and value.get('kind') == 'kpharness.ffprobe-survivor.v1':
                lines.append(value)
        return lines

    def assert_survivor_blocks(self, launch, code, result, stderr, *, failures=1):
        self.assertNotEqual(code, 0)
        self.assertFalse(result['ok'])
        self.assertEqual((result['survivor']['pid'], result['survivor']['pid_start']), (4242, 'fixture-start'))
        survivors = self.survivor_lines(stderr)
        self.assertEqual(len(survivors), 1, stderr)
        self.assertEqual((survivors[0]['pid'], survivors[0]['pid_start']), (4242, 'fixture-start'))
        self.assertEqual(survivors[0]['command'], ['ffprobe', '-v', 'error'])
        self.assertIn('do not accept', survivors[0]['instruction'])
        # The ledger holds the failure and the gate is blocked under every head.
        self.assertFalse(A.cleanup_state_clear(self.run, launch['cleanup_ledger_sha256']))
        if survivors[0]['recorded_in_ledger']:
            heads = head_lines(stderr)
            self.assertEqual(heads[-1]['event'], 'acceptance_failure')
            self.assertEqual(survivors[0]['cleanup_ledger_sha256'], heads[-1]['cleanup_ledger_sha256'])
            self.assertEqual(result['cleanup_ledger_sha256'], heads[-1]['cleanup_ledger_sha256'])
            _, raw, recorded, _ = A._load_cleanup_ledger(self.run)
            self.assertEqual(len(recorded), failures)
            self.assertIn(survivors[0]['failure_id'], recorded)
            self.assertEqual(recorded[survivors[0]['failure_id']]['payload']['pid'], 4242)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), heads[-1]['cleanup_ledger_sha256'])
            self.assertFalse(A.cleanup_state_clear(self.run, heads[-1]['cleanup_ledger_sha256']))
        code, stdout, _ = self.cli_accept(launch['cleanup_ledger_sha256'], fixture_pts_probe)
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads((self.run / 'creative-run.json').read_text())['visual_review']['status'],
                         'pending')
        return survivors[0]

    def test_log_deleted_during_probe_still_records_survivor_and_blocks(self):
        launch, code, result, stderr = self.survivor_during_probe(self.log.unlink)
        survivor = self.assert_survivor_blocks(launch, code, result, stderr)
        self.assertTrue(survivor['recorded_in_ledger'])
        self.assertIn('commitment log', survivor['commitment_log_error'])

    def test_log_rotated_during_probe_still_records_survivor_and_blocks(self):
        rotated = self.operator / 'commitments.log.1'
        launch, code, result, stderr = self.survivor_during_probe(lambda: self.log.rename(rotated))
        survivor = self.assert_survivor_blocks(launch, code, result, stderr)
        self.assertTrue(survivor['recorded_in_ledger'])
        # Rotation with a fresh log at the old path: the head reaches the new file.
        self.run = self.base / 'run-2'; self.run.mkdir()
        self.media = self.run / 'continuous.mp4'; self.media.write_bytes(b'frames')
        self.log.touch()
        def rotate_and_recreate():
            self.log.rename(self.operator / 'commitments.log.2'); self.log.touch()
        launch, code, result, stderr = self.survivor_during_probe(rotate_and_recreate)
        survivor = self.assert_survivor_blocks(launch, code, result, stderr)
        self.assertIsNone(survivor['commitment_log_error'])
        self.assertEqual(self.logged()[-1]['cleanup_ledger_sha256'], survivor['cleanup_ledger_sha256'])

    def test_log_hard_linked_during_probe_still_records_survivor_and_blocks(self):
        backup = self.operator / 'backup.log'
        launch, code, result, stderr = self.survivor_during_probe(lambda: os.link(self.log, backup))
        survivor = self.assert_survivor_blocks(launch, code, result, stderr)
        self.assertTrue(survivor['recorded_in_ledger'])
        self.assertIn('unique regular', survivor['commitment_log_error'])

    def test_head_changed_during_probe_still_records_survivor_on_the_current_chain(self):
        launch, code, result, stderr = self.survivor_during_probe(
            lambda: write_cleanup_failure(self.run, 'a' * 32))
        survivor = self.assert_survivor_blocks(launch, code, result, stderr, failures=2)
        self.assertTrue(survivor['recorded_in_ledger'])
        self.assertTrue(survivor['head_changed_during_probe'])

    def test_ledger_lock_unavailable_during_probe_leaves_a_blocking_survivor_record(self):
        holder = []
        def hold():
            descriptor = os.open(self.run, os.O_RDONLY | os.O_DIRECTORY)
            fcntl.flock(descriptor, fcntl.LOCK_EX); holder.append(descriptor)
        try:
            with mock.patch.object(A, 'LEDGER_LOCK_TIMEOUT_SECONDS', .2):
                launch, code, result, stderr = self.survivor_during_probe(hold)
        finally:
            for descriptor in holder:
                os.close(descriptor)
        survivor = self.assert_survivor_blocks(launch, code, result, stderr)
        self.assertFalse(survivor['recorded_in_ledger'])
        self.assertIn('lock', survivor['ledger_error'])
        sidecars = sorted(self.run.glob('ffprobe-cleanup-unrecorded-*.json'))
        self.assertEqual(len(sidecars), 1)
        self.assertEqual(json.loads(sidecars[0].read_text())['pid'], 4242)
        # The ledger itself is still the launch chain, yet the gate stays blocked.
        self.assertEqual(A.cleanup_ledger_sha256(self.run), launch['cleanup_ledger_sha256'])
        self.assertFalse(A.cleanup_state_clear(self.run, launch['cleanup_ledger_sha256']))



def content_rows(count=61, *, black=False, flat=False, changes=None):
    rows = []
    for index in range(count):
        changed = index > 0 and (changes is None or index in changes)
        rows.append({'ymin': 128.0 if flat and index == 0 else 16.0,
                     'ymax': 16.0 if black and index == 0 else (128.0 if flat and index == 0 else 235.0),
                     'yavg': 100.0, 'ydif': 2.0 if changed else 0.0,
                     'udif': 0.0, 'vdif': 0.0})
    return rows


class CaptureTargetAndContentTests(unittest.TestCase):
    """Part B: rootless-root refusal, verified window geometry, and content gate."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.log = self.root / 'native.log'; self.log.write_text('')

    def finalize_with(self, rows, policy='game-capture-v1', pts_count=61):
        run = self.root / f'finalize-{len(list(self.root.iterdir()))}'; run.mkdir()
        recorder = R.X11WindowRecorder(run, verifier=lambda value: value, lease=FakeLease(),
            named_markers={'phase_1': 'one', 'complete': 'done'},
            cadence_start_marker='phase_1', cadence_end_marker='complete',
            ffprobe=sys.executable, content_policy=policy,
            pts_probe=lambda path, executable: [index / 60 for index in range(pts_count)],
            content_probe=lambda path, executable, *, pass_fds=(): copy.deepcopy(rows))
        recorder.markers = {
            'phase_1': {'name': 'phase_1', 'capture_seconds': 0, 'native_log_byte_end': 10, 'sequence': 1},
            'complete': {'name': 'complete', 'capture_seconds': 1, 'native_log_byte_end': 20, 'sequence': 2}}
        recorder._progress_samples = [
            {'capture_seconds': 0, 'progress': R.FFmpegProgress(1, 0, 0, 0, '1x', False)},
            {'capture_seconds': 1, 'progress': R.FFmpegProgress(61, 1_000_000, 0, 0, '1x', False)}]
        (run / 'continuous.mp4').write_bytes(b'frames')
        return run, recorder._finalize_cadence(R.FFmpegProgress(61, 1_000_000, 0, 0, '1x', True))

    def test_root_capture_is_refused_on_rootless_or_unknown_xwayland(self):
        cases = ((None, 'capture_target_rootless_root'),
                 ({'candidate': {'cmdline': ['Xwayland', ':1', '-rootless', '-core', '-terminate']}},
                  'capture_target_rootless_root'),
                 ({'candidate': {'cmdline': ['Xwayland', ':1', '-core']}}, 'capture_target_unsupported'))
        for index, (access, failure) in enumerate(cases):
            with self.subTest(access=access):
                run = self.root / f'root-{index}'
                lease = FakeLease(); lease.xwayland_access = access
                popen = mock.Mock(); query = mock.Mock(side_effect=AssertionError('no geometry query'))
                recorder = R.X11WindowRecorder(run, verifier=lambda value: value, lease=lease,
                    popen=popen, run=query, capture_target='root')
                with self.assertRaisesRegex(RuntimeError, failure):
                    recorder.start(owned(width=1024, height=768), self.log)
                popen.assert_not_called(); query.assert_not_called()
                self.assertEqual(json.loads((run / 'capture-failure.json').read_text())['error_class'], failure)
                self.assertFalse((run / 'continuous.mp4').exists())
        with self.assertRaisesRegex(ValueError, 'capture target'):
            R.X11WindowRecorder(self.root, verifier=lambda value: value, lease=FakeLease(),
                                capture_target='composite-overlay')

    def test_geometry_precondition_refuses_each_shm_condition_before_exec(self):
        cases = {'unviewable': {'state': 'IsUnviewable'}, 'unmapped': {'state': 'IsUnMapped'},
                 'left_of_screen': {'x': -1}, 'right_of_screen': {'x': 2}, 'above_screen': {'y': -2},
                 'below_screen': {'y': 4}, 'not_lease_size': {'width': 1022},
                 'border': {'border': 1}, 'root_differs': {'root': (1280, 720)}}
        for name, values in cases.items():
            with self.subTest(name=name):
                run = self.root / name; popen = mock.Mock()
                recorder = R.X11WindowRecorder(run, verifier=lambda value: value, lease=FakeLease(),
                    popen=popen, run=geometry_query(**values))
                with self.assertRaisesRegex(RuntimeError, 'capture_geometry_precondition'):
                    recorder.start(owned(width=1024, height=768), self.log)
                popen.assert_not_called()
                failure = json.loads((run / 'capture-failure.json').read_text())
                self.assertEqual(failure['error_class'], 'capture_geometry_precondition')
        def foreign(command, **kwargs):
            result = geometry_query()(command, **kwargs)
            if command[1] == '-id':
                result.stdout = xwininfo_output('0x99')
            return result
        broken = {'foreign_window': foreign,
                  'malformed': lambda command, **kwargs: types.SimpleNamespace(returncode=0, stdout='Width: x\n'),
                  'nonzero_exit': lambda command, **kwargs: types.SimpleNamespace(returncode=1, stdout='')}
        for name, query in broken.items():
            with self.subTest(name=name):
                run = self.root / name; popen = mock.Mock()
                recorder = R.X11WindowRecorder(run, verifier=lambda value: value, lease=FakeLease(),
                    popen=popen, run=query)
                with self.assertRaisesRegex(RuntimeError, 'capture_geometry_precondition'):
                    recorder.start(owned(width=1024, height=768), self.log)
                popen.assert_not_called()

    def test_geometry_is_reread_immediately_before_exec_and_change_refuses(self):
        events = []; base = geometry_query()
        def query(command, **kwargs):
            events.append(tuple(command[:2])); return base(command, **kwargs)
        process = mock.Mock(returncode=None); process.poll.return_value = None
        def launch(command, **kwargs):
            events.append(('popen',))
            Path(command[-1]).write_bytes(b'frame')
            (self.root / 'ok' / 'ffmpeg-progress.log').write_bytes(
                b'frame=1\nout_time_us=16667\ndup_frames=0\ndrop_frames=0\nprogress=continue\n')
            return process
        (self.root / 'ok').mkdir()
        recorder = R.X11WindowRecorder(self.root / 'ok', verifier=lambda value: value, lease=FakeLease(),
            popen=launch, run=query, sleep=lambda _: None)
        with mock.patch.object(R.threading, 'Thread'):
            recorder.start(owned(width=1024, height=768), self.log)
        popen_index = events.index(('popen',))
        self.assertEqual(sorted(events[popen_index - 2:popen_index]), [('xwininfo', '-id'), ('xwininfo', '-root')])
        self.assertGreaterEqual(events[:popen_index].count(('xwininfo', '-id')), 2)
        recorder.stop()
        reads = iter(('initial', 'changed'))
        def drifting(command, **kwargs):
            state = next(reads) if command[1] == '-id' else 'root'
            return geometry_query(x=2 if state == 'changed' else 0)(command, **kwargs)
        popen = mock.Mock()
        recorder = R.X11WindowRecorder(self.root / 'drift', verifier=lambda value: value, lease=FakeLease(),
            popen=popen, run=drifting)
        with self.assertRaisesRegex(RuntimeError, 'capture_geometry'):
            recorder.start(owned(width=1024, height=768), self.log)
        popen.assert_not_called()

    def test_content_gate_rejects_black_and_static_before_cadence_can_pass(self):
        run, passed = self.finalize_with(content_rows())
        self.assertEqual(passed['status'], 'passed', passed['failures'])
        self.assertEqual(passed['content']['status'], 'passed')
        self.assertEqual(passed['content']['acceptance']['distinct_ratio'], 1.0)
        artifact = json.loads((run / 'ffprobe-content.json').read_text())
        self.assertEqual(artifact['frames'], content_rows())
        self.assertEqual(passed['content']['artifact']['sha256'], R.sha256(run / 'ffprobe-content.json'))
        cases = {'black': (content_rows(black=True), 'game-capture-v1', 'capture_content_black'),
                 'flat_first_frame': (content_rows(flat=True), 'game-capture-v1', 'capture_content_black'),
                 'static': (content_rows(changes=set()), 'game-capture-v1', 'capture_content_static'),
                 'below_game_minimum': (content_rows(changes={5}), 'game-capture-v1', 'capture_content_static'),
                 'below_diagnostic_minimum': (content_rows(changes=set(range(1, 60))),
                                              'animated-diagnostic-v1', 'capture_content_static'),
                 'frame_count_mismatch': (content_rows(60), 'game-capture-v1', 'capture_content_failed')}
        for name, (rows, policy, failure) in cases.items():
            with self.subTest(name=name):
                _, cadence = self.finalize_with(rows, policy)
                self.assertEqual(cadence['status'], 'failed')
                self.assertTrue(any(item.startswith(failure) for item in cadence['failures']), cadence['failures'])
        _, diagnostic = self.finalize_with(content_rows(), 'animated-diagnostic-v1')
        self.assertEqual(diagnostic['status'], 'passed')
        _, game = self.finalize_with(content_rows(changes=set(range(1, 60))), 'game-capture-v1')
        self.assertEqual(game['status'], 'passed')
        with self.assertRaisesRegex(ValueError, 'content policy'):
            R.X11WindowRecorder(self.root, verifier=lambda value: value, lease=FakeLease(),
                                content_policy='lenient')

    def test_content_probe_uses_fd_signalstats_and_bounded_reader(self):
        seen = {}
        tags = ('YMIN', 'YMAX', 'YAVG', 'YDIF', 'UDIF', 'VDIF')
        frame = {'tags': {f'lavfi.signalstats.{tag}': '3.500000' for tag in tags}}
        class Process:
            returncode = 0; pid = 1
            def __init__(self, command, *, stdout, stderr, pass_fds):
                seen.update(command=command, pass_fds=pass_fds)
                self.stdout = tempfile.TemporaryFile()
                self.stdout.write(json.dumps({'frames': [frame, frame]}).encode()); self.stdout.seek(0)
                self.pid_start = '1'
            def poll(self): return 0
        rows = R.probe_frame_content(Path('/proc/self/fd/41'), '/proc/self/fd/42', pass_fds=(41, 42),
                                     popen=Process)
        self.assertEqual(rows, [{'ymin': 3.5, 'ymax': 3.5, 'yavg': 3.5, 'ydif': 3.5,
                                 'udif': 3.5, 'vdif': 3.5}] * 2)
        command = seen['command']
        self.assertEqual(command[command.index('-f') + 1], 'lavfi')
        self.assertEqual(command[command.index('-i') + 1], 'movie=/proc/self/fd/41,signalstats')
        self.assertEqual(seen['pass_fds'], (41, 42))
        popen = mock.Mock()
        for path in (Path('/tmp/a,b.mp4'), Path('/proc/self/fd/4x')):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'descriptor path'):
                R.probe_frame_content(path, 'ffprobe', pass_fds=(41,), popen=popen)
        popen.assert_not_called()
        frame['tags'].pop('lavfi.signalstats.VDIF')
        with self.assertRaisesRegex(ValueError, 'signalstats'):
            R.probe_frame_content(Path('/proc/self/fd/41'), 'ffprobe', pass_fds=(41,), popen=Process)

    def test_execution_gate_requires_exact_window_geometry_and_bound_content(self):
        run = self.root / 'gate'; run.mkdir(); media = run / 'continuous.mp4'; media.write_bytes(b'frames')
        baseline = completed_receipt(run)
        self.assertTrue(D.execution_evidence_ready(baseline))
        def root_form(value):
            capture = value['capture']
            capture['adapter'] = 'linux-gamescope-x11-private-root-v1'
            capture['source'] = {'kind': 'x11-private-root', 'input': ':91.0', 'source_extent': [1024, 768],
                                 'drawable': 'root', 'details': {'screen': 0, 'draw_mouse': False}}
            index = capture['command'].index('-window_id'); del capture['command'][index:index + 2]
        def forged_origin(value):
            for phase in ('initial', 'pre_exec'):
                value['capture']['geometry_precondition'][phase]['absolute_origin'] = [1, 0]
        def rewrite_content(value, rows):
            path = run / 'ffprobe-content.json'; artifact = json.loads(path.read_text())
            artifact['frames'] = rows; path.write_text(json.dumps(artifact, sort_keys=True, separators=(',', ':')) + '\n')
            value['cadence']['content']['artifact']['sha256'] = R.sha256(path)
        original = (run / 'ffprobe-content.json').read_bytes()
        mutations = {
            'root_form': root_form,
            'window_id_mismatch': lambda value: value['capture']['command'].__setitem__(
                value['capture']['command'].index('-window_id') + 1, '0x99'),
            'pre_exec_differs': lambda value: value['capture']['geometry_precondition']['pre_exec'].update(border_width=1),
            'forged_origin_conditions': forged_origin,
            'geometry_refused': lambda value: value['capture']['geometry_precondition'].update(status='refused'),
            'geometry_missing': lambda value: value['capture'].pop('geometry_precondition'),
            'content_policy_loosened': lambda value: value['cadence']['content']['policy'].update(black_luma_max=0),
            'content_noise_floor_loosened': lambda value: value['cadence']['content']['policy'].update(
                distinct_noise_floor=0.5),
            'content_policy_unknown': lambda value: value['cadence']['content']['policy'].update(id='lenient'),
            'content_missing': lambda value: value['cadence'].pop('content'),
            'content_acceptance_forged': lambda value: value['cadence']['content']['acceptance'].update(changed_frames=1),
            'content_black_artifact': lambda value: rewrite_content(
                value, fixture_content_probe(None, None)[:1] and
                [{**row, 'ymax': 10.0} if index == 0 else row
                 for index, row in enumerate(fixture_content_probe(None, None))]),
            'content_static_artifact': lambda value: rewrite_content(
                value, [{**row, 'ydif': 0.0, 'udif': 0.0, 'vdif': 0.0} for row in fixture_content_probe(None, None)]),
            'content_short_artifact': lambda value: rewrite_content(value, fixture_content_probe(None, None)[:-1]),
            'content_sha_mismatch': lambda value: value['cadence']['content']['artifact'].update(sha256='0' * 64),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                broken = json.loads(json.dumps(baseline)); mutate(broken)
                self.assertFalse(D.execution_evidence_ready(broken))
                (run / 'ffprobe-content.json').write_bytes(original)
        self.assertTrue(D.execution_evidence_ready(baseline))

    def test_acceptance_reprobes_content_and_records_surviving_content_probe(self):
        run = self.root / 'accept'; run.mkdir(); media = run / 'continuous.mp4'; media.write_bytes(b'frames')
        receipt = completed_receipt(run); (run / 'creative-run.json').write_text(json.dumps(receipt))
        black = [{**row, 'ymax': 10.0} if index == 0 else row
                 for index, row in enumerate(fixture_content_probe(None, None))]
        with self.assertRaisesRegex(ValueError, 'content'):
            accept_visual(run, reviewer='reviewer', media_sha256=R.sha256(media),
                          pts_probe=fixture_pts_probe,
                          content_probe=lambda path, executable, *, pass_fds=(): black)
        seen = {}
        def probe(path, executable, *, pass_fds=()):
            seen['fds'] = pass_fds; seen['path'] = str(path)
            return fixture_content_probe(path, executable)
        accepted = accept_visual(run, reviewer='reviewer', media_sha256=R.sha256(media),
                                 pts_probe=fixture_pts_probe, content_probe=probe)
        self.assertRegex(seen['path'], r'^/proc/self/fd/[0-9]+$'); self.assertEqual(len(seen['fds']), 2)
        review = accepted['visual_review']
        self.assertEqual(review['content_artifact_sha256'], receipt['cadence']['content']['artifact']['sha256'])
        self.assertEqual(review['geometry_precondition_sha256'], hashlib.sha256(
            json.dumps(receipt['capture']['geometry_precondition'], sort_keys=True,
                       separators=(',', ':')).encode()).hexdigest())
        self.assertTrue(verify_acceptance(accepted))
        for field in ('content_artifact_sha256', 'geometry_precondition_sha256'):
            with self.subTest(field=field):
                tampered = json.loads(json.dumps(accepted)); tampered['visual_review'][field] = '0' * 64
                tampered['visual_review']['acceptance_receipt_sha256'] = acceptance_receipt_sha256(tampered)
                self.assertFalse(verify_acceptance(tampered))
        run2 = self.root / 'accept-survivor'; run2.mkdir(); media2 = run2 / 'continuous.mp4'
        media2.write_bytes(b'frames'); receipt2 = completed_receipt(run2)
        (run2 / 'creative-run.json').write_text(json.dumps(receipt2))
        survivor = R.ProbeCleanupError(types.SimpleNamespace(pid=4242, pid_start='fixture-start'),
                                       ['ffprobe'], 'content probe survived')
        with self.assertRaises(A.CleanupLedgerChanged):
            accept_visual(run2, reviewer='reviewer', media_sha256=R.sha256(media2),
                          pts_probe=fixture_pts_probe,
                          content_probe=lambda *args, **kwargs: (_ for _ in ()).throw(survivor))
        self.assertEqual(len(A._load_cleanup_ledger(run2)[2]), 1)


# Round 11 calibration (production probes over synthetic encodes with the
# recorder's exact codec; see docs/creative-runner.md "Content gate"):
# max(YDIF, UDIF, VDIF) of a duplicate frame reached 0.7596, and of a fresh
# testsrc2 60 FPS frame never fell below 1.8907.
CALIBRATED_DUPLICATE_MAX = 0.7596
CALIBRATED_FRESH_MIN = 1.8907
_DUP_NOISE = (0.07, 0.12, 0.18, 0.54, 0.7596)
_FRESH = (1.8907, 2.45, 3.6)


def encoded_rows(count=601, *, fresh=lambda index: True, noise=lambda index: _DUP_NOISE[index % 5],
                 black_before=0):
    """signalstats-shaped rows: duplicates carry encoder noise, fresh frames carry real change."""
    rows = []
    for index in range(count):
        value = 0.0 if index == 0 else (_FRESH[index % 3] if fresh(index) else noise(index))
        black = index < black_before
        rows.append({'ymin': 16.0, 'ymax': 16.0 if black else 235.0, 'yavg': 16.0 if black else 120.0,
                     'ydif': value * .7, 'udif': value * .6, 'vdif': value})
    return rows


PTS_601 = [index / 60 for index in range(601)]


class ContentNoiseFloorTests(unittest.TestCase):
    """R10-1 (Critical): encoder noise on a duplicate is not a pattern change."""

    def evaluate(self, rows, policy, start=1.0, end=9.0):
        return D.evaluate_content(rows, PTS_601, start, end, D.CONTENT_POLICIES[policy])

    def test_policy_floor_sits_inside_the_calibrated_gap_with_margin_on_both_sides(self):
        floor = D.CONTENT_POLICIES['animated-diagnostic-v1']['distinct_noise_floor']
        self.assertGreaterEqual(floor, 1.5 * CALIBRATED_DUPLICATE_MAX)
        self.assertLessEqual(floor, CALIBRATED_FRESH_MIN / 1.5)
        self.assertEqual(D.CONTENT_POLICIES['game-capture-v1']['distinct_noise_floor'], 0.0)
        for policy in D.CONTENT_POLICIES.values():
            with self.assertRaises(TypeError):
                policy['distinct_noise_floor'] = 0  # the table is immutable

    def test_calibration_shaped_clips_separate_duplicates_from_fresh_frames(self):
        cases = {
            # name: (rows, animated-diagnostic-v1, game-capture-v1)
            'half_duplicate_30_to_60': (encoded_rows(fresh=lambda i: i % 2 == 0), 'failed', 'passed'),
            'one_in_ten_fresh': (encoded_rows(fresh=lambda i: i % 10 == 0), 'failed', 'passed'),
            'static_still': (encoded_rows(fresh=lambda i: False,
                                          noise=lambda i: 0.05 if i % 480 == 0 else 0.0), 'failed', 'failed'),
            'textured_static': (encoded_rows(fresh=lambda i: False,
                                             noise=lambda i: 0.11 if i % 45 == 0 else 0.0), 'failed', 'failed'),
            # An 8x8 box on a still frame, toggled twice a second, with encoder refinement after it.
            'blink_8x8': (encoded_rows(fresh=lambda i: False,
                                       noise=lambda i: 0.02 if i % 30 == 0 else (0.01 if i % 30 == 1 else 0.0)),
                          'failed', 'passed'),
            'full_animated_60': (encoded_rows(), 'passed', 'passed'),
        }
        for name, (rows, diagnostic, game) in cases.items():
            with self.subTest(name=name):
                result = self.evaluate(rows, 'animated-diagnostic-v1')
                self.assertEqual(result['status'], diagnostic, result['failures'])
                self.assertEqual(result['acceptance']['distinct_noise_floor'], 1.2)
                self.assertEqual(self.evaluate(rows, 'game-capture-v1')['status'], game)
        half = self.evaluate(cases['half_duplicate_30_to_60'][0], 'animated-diagnostic-v1')['acceptance']
        self.assertAlmostEqual(half['distinct_ratio'], .5, places=2)
        tenth = self.evaluate(cases['one_in_ten_fresh'][0], 'animated-diagnostic-v1')['acceptance']
        self.assertAlmostEqual(tenth['distinct_ratio'], .1, places=2)

    def test_black_check_uses_the_first_frame_at_the_acceptance_start(self):
        startup_black = encoded_rows(black_before=30)  # 0.5 s of black before the 1.0 s marker
        result = self.evaluate(startup_black, 'animated-diagnostic-v1')
        self.assertEqual(result['status'], 'passed', result['failures'])
        self.assertEqual(result['first_frame']['index'], 60)
        self.assertEqual(result['startup']['black_frames_before_acceptance'], 30)
        self.assertEqual(result['startup']['capture_first_frame'], {'ymin': 16.0, 'ymax': 16.0})
        black_at_marker = encoded_rows(black_before=61)
        result = self.evaluate(black_at_marker, 'animated-diagnostic-v1')
        self.assertIn('capture_content_black', ' '.join(result['failures']))
        self.assertEqual(result['first_frame']['index'], 60)
        result = self.evaluate(encoded_rows(), 'game-capture-v1', start=11.0, end=12.0)
        self.assertIn('capture_content_black: no frame', ' '.join(result['failures']))

    def test_receipt_cannot_loosen_the_noise_floor(self):
        run = Path(tempfile.mkdtemp(prefix='kp-floor-')); self.addCleanup(shutil.rmtree, run)
        (run / 'continuous.mp4').write_bytes(b'frames')
        receipt = completed_receipt(run)
        self.assertTrue(D.execution_evidence_ready(receipt))
        for forged in (0.5, -1.0, None):
            tampered = copy.deepcopy(receipt)
            tampered['cadence']['content']['policy']['distinct_noise_floor'] = forged
            self.assertFalse(D.execution_evidence_ready(tampered))
        tampered = copy.deepcopy(receipt)
        tampered['cadence']['content']['policy'].pop('distinct_noise_floor')
        self.assertFalse(D.execution_evidence_ready(tampered))


class ProbeDeadlineTests(unittest.TestCase):
    """FFprobe deadlines scale with the frames decoded, within a hard maximum."""

    def test_deadline_scales_with_frame_count_and_is_bounded(self):
        self.assertEqual(R.probe_deadline_seconds(0), R.PROBE_DEADLINE_BASE_SECONDS)
        self.assertGreater(R.probe_deadline_seconds(2_100), 30)
        self.assertLess(R.probe_deadline_seconds(2_100), R.probe_deadline_seconds(36_000))
        self.assertEqual(R.probe_deadline_seconds(R.MAX_CANONICAL_PTS_FRAMES), R.PROBE_DEADLINE_MAX_SECONDS)
        for bad in (-1, 1.5, True, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                R.probe_deadline_seconds(bad)
        with self.assertRaisesRegex(ValueError, 'deadline'):
            R.probe_frame_pts(Path('/x'), 'ffprobe', popen=mock.Mock(),
                              deadline_seconds=R.PROBE_DEADLINE_MAX_SECONDS + 1)

    def slow_probe(self, finish_at):
        """A real pipe whose FFprobe stand-in answers only after ``finish_at`` fake seconds."""
        clock = [0.0]
        read_fd, write_fd = os.pipe()
        payload = json.dumps({'frames': [{'best_effort_timestamp_time': '0.0'},
                                         {'best_effort_timestamp_time': '0.016667'}]}).encode()
        state = {'written': False}
        class Process:
            pid = 1; pid_start = '1'; returncode = None
            def __init__(self, command, **kwargs):
                self.stdout = os.fdopen(read_fd, 'rb')
            def poll(self):
                return 0 if state['written'] else None
            def kill(self):
                pass
            def wait(self, timeout=None):
                return 0
        def sleep(seconds):
            clock[0] += 1.0
            if clock[0] >= finish_at and not state['written']:
                os.write(write_fd, payload); os.close(write_fd); state['written'] = True
        def cleanup():
            if not state['written']:
                os.close(write_fd)
        self.addCleanup(cleanup)
        return Process, (lambda: clock[0]), sleep

    def test_a_long_clip_outlives_the_old_fixed_bound_and_the_scaled_bound_still_holds(self):
        frames = 36_000  # ten minutes at 60 FPS
        popen, monotonic, sleep = self.slow_probe(finish_at=45)
        pts = R.probe_frame_pts(Path('/x'), 'ffprobe', popen=popen, monotonic=monotonic, sleep=sleep,
                                deadline_seconds=R.probe_deadline_seconds(frames))
        self.assertEqual(len(pts), 2)
        popen, monotonic, sleep = self.slow_probe(finish_at=45)
        with self.assertRaises(subprocess.TimeoutExpired):
            R.probe_frame_pts(Path('/x'), 'ffprobe', popen=popen, monotonic=monotonic, sleep=sleep)
        popen, monotonic, sleep = self.slow_probe(finish_at=R.PROBE_DEADLINE_MAX_SECONDS + 5)
        with self.assertRaises(subprocess.TimeoutExpired):
            R.probe_frame_pts(Path('/x'), 'ffprobe', popen=popen, monotonic=monotonic, sleep=sleep,
                              deadline_seconds=R.probe_deadline_seconds(R.MAX_CANONICAL_PTS_FRAMES))

    def test_acceptance_reprobes_use_the_recorded_frame_count(self):
        base = Path(tempfile.mkdtemp(prefix='kp-deadline-')); self.addCleanup(shutil.rmtree, base)
        run = base / 'run'; run.mkdir(); media = run / 'continuous.mp4'; media.write_bytes(b'frames')
        receipt = completed_receipt(run); (run / 'creative-run.json').write_text(json.dumps(receipt))
        frames = json.loads(Path(receipt['cadence']['pts_artifact']['path']).read_text())['frame_count']
        seen = []
        def pts(path, tool, *, pass_fds, deadline_seconds):
            seen.append(('pts', deadline_seconds)); return fixture_pts_probe(path, tool, pass_fds=pass_fds)
        def content(path, tool, *, pass_fds, deadline_seconds):
            seen.append(('content', deadline_seconds)); return fixture_content_probe(path, tool)
        head = (A.cleanup_ledger_sha256(run) if (run / A.CLEANUP_LEDGER).exists() else init_ledger(run))
        with mock.patch.object(A, 'probe_frame_pts', pts), mock.patch.object(A, 'probe_frame_content', content):
            _accept_visual(run, reviewer='reviewer', media_sha256=R.sha256(media),
                           route_sha256=receipt['route_source']['sha256'],
                           ffprobe_sha256=receipt['cadence']['probe_tool']['sha256'],
                           cleanup_ledger_sha256=head, commitment_log=COMMIT_LOG)
        expected = R.probe_deadline_seconds(frames)
        self.assertEqual(seen, [('pts', expected), ('content', expected)])


class CommitmentLogPlacementTests(unittest.TestCase):
    """R10-3 adversarial: refuse a log that aliases the run tree by device and inode."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.run = self.base / 'run'; (self.run / 'sub').mkdir(parents=True)
        self.alias = self.base / 'alias'; self.alias.mkdir()
        self.log = self.alias / 'commitments.log'; self.log.touch()

    def aliased(self, target):
        """Make ``alias`` report ``target``'s device and inode, as a bind mount would."""
        real_stat = os.stat
        def fake(path, *args, **kwargs):
            if Path(path) == self.alias:
                return real_stat(target, *args, **kwargs)
            return real_stat(path, *args, **kwargs)
        return mock.patch.object(A.os, 'stat', fake)

    def test_bind_mount_alias_of_the_run_dir_or_a_subdirectory_is_refused(self):
        self.assertEqual(A.validate_commitment_log(self.log, self.run)[0], self.log.resolve())
        for target in (self.run, self.run / 'sub'):
            with self.subTest(target=target), self.aliased(target), \
                    self.assertRaisesRegex(ValueError, 'aliases the run tree'):
                A.validate_commitment_log(self.log, self.run)

    def test_bind_mounted_log_file_from_the_run_tree_is_refused(self):
        inside = self.run / 'sub' / 'x.log'; inside.touch()
        real_lstat = os.lstat
        def fake(path, *args, **kwargs):
            if Path(path) == self.log:
                return real_lstat(inside, *args, **kwargs)
            return real_lstat(path, *args, **kwargs)
        with mock.patch.object(A.os, 'lstat', fake), self.assertRaisesRegex(ValueError, 'aliases the run tree'):
            A.validate_commitment_log(self.log, self.run)


REAL_FFMPEG = Path('/usr/bin/ffmpeg')
REAL_FFPROBE = Path('/home/linuxbrew/.linuxbrew/bin/ffprobe')


@unittest.skipUnless(os.environ.get('KP_R11_REAL_ENCODES') == '1' and REAL_FFMPEG.is_file()
                     and REAL_FFPROBE.is_file(), 'host-only: set KP_R11_REAL_ENCODES=1 with host FFmpeg/FFprobe')
class RealEncodeContentTests(unittest.TestCase):
    """Synthetic lavfi encodes through the recorder's codec, then the production probes."""
    CODEC = ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p',
             '-threads', '2']

    def encode_and_probe(self, graph, seconds=4):
        directory = Path(tempfile.mkdtemp(prefix='kp-r11-enc-')); self.addCleanup(shutil.rmtree, directory)
        out = directory / 'continuous.mp4'
        source = subprocess.Popen([str(REAL_FFMPEG), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', graph,
            '-t', str(seconds), '-pix_fmt', 'bgr0', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
        subprocess.run([str(REAL_FFMPEG), '-nostdin', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr0',
            '-video_size', '1024x768', '-framerate', '60', '-i', '-', *self.CODEC, str(out)],
            stdin=source.stdout, check=True, timeout=600)
        source.stdout.close(); self.assertEqual(source.wait(timeout=60), 0)
        descriptor = os.open(out, os.O_RDONLY); self.addCleanup(os.close, descriptor)
        path = Path(f'/proc/self/fd/{descriptor}')
        frames = int(seconds * 60)
        deadline = R.probe_deadline_seconds(frames)
        rows = R.probe_frame_content(path, str(REAL_FFPROBE), pass_fds=(descriptor,), deadline_seconds=deadline)
        pts = R.probe_frame_pts(path, str(REAL_FFPROBE), pass_fds=(descriptor,), deadline_seconds=deadline)
        return rows, pts

    def test_real_encodes_fail_duplicates_and_pass_full_animation(self):
        still = 'testsrc2=size=1024x768:rate=60,trim=end_frame=1,loop=loop=-1:size=1,setpts=N/60/TB'
        cases = {
            'half_duplicate_30_to_60': ('testsrc2=size=1024x768:rate=30,fps=60', 'failed', 'passed'),
            'one_in_ten_fresh': ('testsrc2=size=1024x768:rate=6,fps=60', 'failed', 'passed'),
            'static_still': (still, 'failed', 'failed'),
            'textured_static': (still + ',noise=alls=40:allf=0', 'failed', 'failed'),
            'blink_8x8': (still + ',drawbox=x=10:y=10:w=8:h=8:c=white:t=fill:enable=lt(mod(t\\,1)\\,0.5)',
                          'failed', 'passed'),
            'full_animated_60': ('testsrc2=size=1024x768:rate=60', 'passed', 'passed'),
        }
        for name, (graph, diagnostic, game) in cases.items():
            with self.subTest(name=name):
                rows, pts = self.encode_and_probe(graph)
                verdicts = {policy: D.evaluate_content(rows, pts, .5, pts[-1] - .25, D.CONTENT_POLICIES[policy])
                            for policy in ('animated-diagnostic-v1', 'game-capture-v1')}
                print(name, {policy: (value['status'], round(value['acceptance']['distinct_ratio'], 4))
                             for policy, value in verdicts.items()}, flush=True)
                self.assertEqual(verdicts['animated-diagnostic-v1']['status'], diagnostic)
                self.assertEqual(verdicts['game-capture-v1']['status'], game)


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.log = self.root / "native.log"; self.log.write_text("")

    def test_gamescope_recorder_requires_versioned_60_fps_policy(self):
        with self.assertRaisesRegex(ValueError, "60 FPS"):
            R.X11WindowRecorder(self.root, verifier=lambda value: value,
                                lease=FakeLease(), fps=30)

    def exact_geometry(self, command, **kwargs):
        return geometry_query()(command, **kwargs)

    def admitted_launch(self, process):
        def launch(command, **kwargs):
            Path(command[-1]).write_bytes(b"frame")
            (self.root / "ffmpeg-progress.log").write_bytes(
                b"frame=1\nout_time_us=16667\ndup_frames=0\ndrop_frames=0\nprogress=continue\n"
                b"frame=2\nout_time_us=33334\ndup_frames=0\ndrop_frames=0\nprogress=end\n")
            return process
        return launch

    def test_progress_parser_requires_complete_canonical_monotonic_blocks(self):
        raw = (b"frame=1\nout_time_us=16667\ndup_frames=0\ndrop_frames=0\nspeed=1.0x\n"
               b"progress=continue\nframe=2\nout_time_us=33334\ndup_frames=0\n")
        blocks, suffix = R.parse_progress_blocks(raw)
        self.assertEqual(blocks, [R.FFmpegProgress(1, 16667, 0, 0, "1.0x", False)])
        self.assertEqual(suffix, b"frame=2\nout_time_us=33334\ndup_frames=0\n")
        invalid = (
            b"frame=01\ndup_frames=0\ndrop_frames=0\nprogress=continue\n",
            b"frame=1\nframe=2\ndup_frames=0\ndrop_frames=0\nprogress=continue\n",
            b"frame=1\ndup_frames=0\ndrop_frames=0\nprogress=unknown\n",
            b"frame=2\ndup_frames=0\ndrop_frames=0\nprogress=end\nframe=3\n",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                R.parse_progress_blocks(value)

    def test_diagnostic_reads_are_bounded_and_reject_truncation_or_replacement(self):
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value, lease=FakeLease())
        path = self.root / "diagnostic"; path.write_bytes(b"abcdef")
        info = path.stat(); recorder._diagnostic_identity[path] = (info.st_dev, info.st_ino)
        self.assertEqual(recorder._read_diagnostic(path, 0), (b"abcdef", 6))
        path.write_bytes(b"x")
        with self.assertRaises(OSError): recorder._read_diagnostic(path, 6)
        path.unlink(); path.write_bytes(b"replacement")
        with self.assertRaises(OSError): recorder._read_diagnostic(path, 0)
        large = self.root / "large"; large.touch()
        with large.open('r+b') as stream: stream.truncate(R.MAX_DIAGNOSTIC_READ + 1)
        info = large.stat(); recorder._diagnostic_identity[large] = (info.st_dev, info.st_ino)
        with self.assertRaises(OSError): recorder._read_diagnostic(large, 0)

    def test_pts_analyzer_reports_portable_slot_and_gap_evidence(self):
        perfect = [index / 60 for index in range(61)]
        result = R.analyze_pts(perfect, requested_fps=60, interval_start=0,
                               interval_end=1, thresholds=R.CadenceThresholds())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["frame_count"], 61)
        self.assertEqual(result["missing_slots"], 0)
        self.assertAlmostEqual(result["effective_fps"], 60)
        self.assertEqual(result["gaps_above_ms"], {"25": 0, "50": 0, "100": 0})
        failed = R.analyze_pts([0, 1 / 60, 2 / 60, .65, 2 / 3], requested_fps=60,
                               interval_start=0, interval_end=2 / 3,
                               thresholds=R.CadenceThresholds())
        self.assertEqual(failed["status"], "failed")
        self.assertGreater(failed["maximum_gap_seconds"], .6)
        for pts in ([0], [0, 0], [0, float("nan")], [0.1, 0.05]):
            with self.subTest(pts=pts), self.assertRaises(ValueError):
                R.analyze_pts(pts, requested_fps=60, interval_start=0,
                              interval_end=1, thresholds=R.CadenceThresholds())

    def test_pts_analyzer_accepts_perfect_cadence_between_frame_boundaries(self):
        pts = [index / 60 for index in range(121)]
        for start in (.005, .016):
            result = R.analyze_pts(pts, requested_fps=60, interval_start=start,
                                   interval_end=start + 1, thresholds=R.CadenceThresholds())
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["missing_slots"], 0)

    def test_named_markers_preserve_first_complete_line_and_portable_clock(self):
        recorder = R.X11Recorder(self.root, named_markers={"phase_1": r"phase=1",
            "complete": r"complete phases=3"}, cadence_start_marker="phase_1",
            cadence_end_marker="complete")
        recorder.started = 100
        self.log.write_bytes(b"phase=")
        recorder.observe(self.log, 101)
        self.assertEqual(recorder.markers, {})
        with self.log.open("ab") as stream:
            stream.write(b"1 actor=1\ncomplete phases=3 restored=1\n")
        recorder.observe(self.log, 102)
        self.assertEqual(list(recorder.markers), ["phase_1", "complete"])
        self.assertEqual(recorder.markers["phase_1"]["capture_seconds"], 2)
        self.assertEqual(recorder.markers["phase_1"]["poll_interval_ms"], 100)
        self.assertGreater(recorder.markers["complete"]["native_log_byte_end"],
                           recorder.markers["phase_1"]["native_log_byte_end"])

    def test_cli_named_marker_configuration_validates_before_execution(self):
        options = C.parser().parse_args(["--backend", D.GAMESCOPE_BACKEND, "--script", "x",
            "--route", "r", "--capture-marker", "phase_1=phase=1",
            "--capture-marker", "complete=done", "--cadence-start-marker", "phase_1",
            "--cadence-end-marker", "complete"])
        markers, start, end = C.marker_configuration(options)
        self.assertEqual(markers, {"effect_start": R.CREATIVE_MARKER,
                                  "phase_1": "phase=1", "complete": "done"})
        self.assertEqual((start, end), ("phase_1", "complete"))
        for values in (["Bad=x"], ["a=x", "a=y"], ["a=["]):
            options.capture_marker = values
            with self.subTest(values=values), self.assertRaises(ValueError):
                C.marker_configuration(options)

    def test_marker_bounded_cadence_recomputes_terminal_duplication(self):
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value, lease=FakeLease(),
            named_markers={"phase_1": "one", "complete": "done"},
            cadence_start_marker="phase_1", cadence_end_marker="complete",
            # Hermetic: an always-present native executable stands in for FFprobe.
            ffprobe=sys.executable, content_probe=lambda path, executable, *, pass_fds=(): content_rows(),
            pts_probe=lambda path, executable: [index / 60 for index in range(61)])
        recorder.markers = {
            "phase_1": {"name": "phase_1", "capture_seconds": 0,
                        "native_log_byte_end": 10, "sequence": 1},
            "complete": {"name": "complete", "capture_seconds": 1,
                         "native_log_byte_end": 20, "sequence": 2},
        }
        recorder._progress_samples = [
            {"capture_seconds": 0, "progress": R.FFmpegProgress(1, 0, 0, 0, "1x", False)},
            {"capture_seconds": 1, "progress": R.FFmpegProgress(61, 1_000_000, 0, 0, "1x", False)},
        ]
        (self.root / "continuous.mp4").write_bytes(b"frames")
        passed = recorder._finalize_cadence(R.FFmpegProgress(61, 1_000_000, 0, 0, "1x", True))
        self.assertEqual(passed["status"], "passed")
        self.assertEqual(passed["intervals"][0]["name"], "phase_1_to_complete")
        failed = recorder._finalize_cadence(R.FFmpegProgress(61, 1_000_000, 1, 0, "1x", True))
        self.assertEqual(failed["status"], "failed")

    def test_same_poll_markers_keep_byte_order_without_claiming_reverse_time(self):
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value, lease=FakeLease(),
            named_markers={"phase_1": "start", "complete": "end"},
            cadence_start_marker="phase_1", cadence_end_marker="complete",
            # Hermetic: an always-present native executable stands in for FFprobe.
            ffprobe=sys.executable, content_probe=lambda path, executable, *, pass_fds=(): content_rows(),
            pts_probe=lambda path, executable: [index / 60 for index in range(61)])
        recorder.started = 100
        self.log.write_text("start\nend\n")
        recorder.observe(self.log, 100.25)
        markers = list(recorder.markers.values())
        self.assertLess(markers[0]["native_log_byte_end"], markers[1]["native_log_byte_end"])
        self.assertLess(markers[0]["sequence"], markers[1]["sequence"])
        self.assertLessEqual(markers[0]["capture_seconds"], markers[1]["capture_seconds"])
        self.assertEqual(recorder._marker_order_status(), "ordered")
        progress_left = R.FFmpegProgress(6, 100000, 0, 0, "1x", False)
        progress_right = R.FFmpegProgress(19, 300000, 0, 0, "1x", False)
        recorder._progress_samples = [
            {"capture_seconds": .1, "progress": progress_left},
            {"capture_seconds": .3, "progress": progress_right},
        ]
        (self.root / "continuous.mp4").write_bytes(b"frames")
        cadence = recorder._finalize_cadence(R.FFmpegProgress(61, 1_000_000, 0, 0, "1x", True))
        self.assertEqual(cadence["status"], "passed", cadence)
        self.assertLess(cadence["intervals"][0]["start_capture_seconds"],
                        cadence["intervals"][0]["end_capture_seconds"])

    def test_gamescope_recorder_captures_verified_window_after_geometry_precondition(self):
        process = mock.Mock(returncode=None)
        process.poll.return_value = None
        def launch(command, **kwargs):
            Path(command[-1]).write_bytes(b"frame")
            (self.root / "ffmpeg-progress.log").write_bytes(
                b"frame=1\nout_time_us=16667\ndup_frames=0\ndrop_frames=0\nspeed=1x\nprogress=continue\n")
            return process
        query = geometry_query()
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=launch, run=query, sleep=lambda _: None)
        with mock.patch.object(R.threading, "Thread"):
            recorder.start(owned(width=1024, height=768), self.log)
        command = recorder.capture["command"]
        self.assertEqual(command[command.index("-window_id") + 1], "0x2a")
        self.assertEqual(command[command.index("-i") + 1], ":91.0")
        self.assertEqual(command[command.index("-draw_mouse") + 1], "0")
        self.assertEqual(recorder.capture["source"]["kind"], "x11-window")
        geometry = recorder.capture["geometry_precondition"]
        self.assertEqual(geometry["status"], "verified")
        self.assertEqual(geometry["initial"], geometry["pre_exec"])
        self.assertTrue(all(geometry["pre_exec"]["conditions"].values()))
        self.assertEqual(recorder.capture["authorization"]["coverage"]["status"], "exact")
        self.assertEqual(recorder.capture["startup"]["shm"]["status"], "no_fallback_observed")
        recorder.stop()

    def test_gamescope_recorder_refuses_offscreen_window_before_process_creation(self):
        popen = mock.Mock()
        query = geometry_query(x=1)
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=popen, run=query)
        with self.assertRaisesRegex(RuntimeError, "capture_geometry_precondition"):
            recorder.start(owned(width=1024, height=768), self.log)
        popen.assert_not_called()

    def test_startup_fallback_is_typed_and_cleans_only_owned_recorder(self):
        process = mock.Mock(returncode=255)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("ffmpeg", 2), 255]
        def launch(command, **kwargs):
            Path(command[-1]).write_bytes(b"partial")
            (self.root / "ffmpeg.log").write_bytes(b"Continuing without shared memory (using fallback)\n")
            return process
        query = geometry_query()
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=launch, run=query, sleep=lambda _: None)
        with self.assertRaisesRegex(RuntimeError, "capture_shm_fallback"):
            recorder.start(owned(width=1024, height=768), self.log)
        self.assertEqual(recorder.failure["error_class"], "capture_shm_fallback")
        process.send_signal.assert_called_once_with(signal.SIGINT)
        process.kill.assert_called_once_with()
        self.assertTrue((self.root / "capture-failure.json").is_file())

    def test_spawn_failure_writes_typed_capture_failure(self):
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=mock.Mock(side_effect=OSError("spawn failed")),
            run=self.exact_geometry)
        with self.assertRaisesRegex(RuntimeError, "capture_process_exited"):
            recorder.start(owned(width=1024, height=768), self.log)
        self.assertEqual(recorder.failure["error_class"], "capture_process_exited")
        self.assertTrue((self.root / "capture-failure.json").is_file())

    def test_setup_collision_is_typed_and_stop_releases_partial_resources(self):
        R.X11WindowRecorder(self.root / "never-started", verifier=lambda value: value,
            lease=FakeLease()).stop()
        (self.root / "ffmpeg-progress.log").write_text("collision")
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=mock.Mock(), run=self.exact_geometry)
        with self.assertRaisesRegex(RuntimeError, "capture_setup_failed"):
            recorder.start(owned(width=1024, height=768), self.log)
        self.assertEqual(recorder.failure["error_class"], "capture_setup_failed")
        self.assertIsNone(recorder._run_dir_fd)
        self.assertIsNone(recorder._capture_stage_fd)
        self.assertIsNone(recorder._progress_fd)
        recorder.stop()

    def test_generic_pre_spawn_oserror_is_typed_as_setup_failure(self):
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=mock.Mock(), run=self.exact_geometry)
        with mock.patch.object(R.tempfile, "mkdtemp", side_effect=OSError("simulated setup I/O failure")):
            with self.assertRaisesRegex(RuntimeError, "capture_setup_failed"):
                recorder.start(owned(width=1024, height=768), self.log)
        recorder._popen.assert_not_called()
        self.assertEqual(recorder.failure["error_class"], "capture_setup_failed")
        self.assertIsNone(recorder._run_dir_fd)

    def test_subprocess_timeout_in_watcher_and_final_binding_is_typed(self):
        timeout = subprocess.TimeoutExpired("xdotool", 5)
        recorder = R.X11WindowRecorder(self.root, verifier=mock.Mock(side_effect=timeout),
            lease=FakeLease(), run=self.exact_geometry,
            monotonic=mock.Mock(side_effect=[1.0, 2.0, 3.0]))
        recorder.started = 1.0; recorder.target = owned(width=1024, height=768)
        recorder.process = mock.Mock(returncode=None); recorder.process.poll.return_value = None
        recorder.capture = {"status": "running", "startup": {"shm": {"forbidden_matches": []}},
                            "watch": {"checks": 0}}
        recorder._scan_ffmpeg_log = mock.Mock(return_value=[])
        recorder._read_progress = mock.Mock(return_value=[])
        recorder._stop.wait = mock.Mock(side_effect=[False, True])
        recorder._watch_window(self.log)
        self.assertEqual(recorder.failure["error_class"], "capture_binding_changed")

    def test_subprocess_timeout_in_final_binding_is_typed(self):
        process = mock.Mock(returncode=255); process.poll.return_value = None
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=self.admitted_launch(process), run=self.exact_geometry)
        with mock.patch.object(R.threading, "Thread"):
            recorder.start(owned(width=1024, height=768), self.log)
        recorder._verifier = mock.Mock(side_effect=subprocess.TimeoutExpired("xdotool", 5))
        recorder.stop()
        self.assertEqual(recorder.failure["error_class"], "capture_binding_changed")

    def test_stop_drains_final_marker_and_revalidates_binding(self):
        process = mock.Mock(returncode=255); process.poll.return_value = None
        verifier = mock.Mock(side_effect=lambda value: value)
        recorder = R.X11WindowRecorder(self.root, verifier=verifier, lease=FakeLease(),
            popen=self.admitted_launch(process), run=self.exact_geometry,
            named_markers={"phase_1": "start", "complete": "complete"},
            cadence_start_marker="phase_1", cadence_end_marker="complete",
            pts_probe=lambda path, executable: [index / 60 for index in range(121)])
        with mock.patch.object(R.threading, "Thread"):
            recorder.start(owned(width=1024, height=768), self.log)
        with self.log.open("a") as stream: stream.write("start\n")
        recorder.observe(self.log, recorder.started + .5)
        with self.log.open("a") as stream: stream.write("complete\n")
        recorder.stop()
        self.assertIn("complete", recorder.markers)
        self.assertGreaterEqual(verifier.call_count, 3)  # pre-start plus pre/post-finalize

    def test_stop_raises_and_retains_handle_when_owned_ffmpeg_survives_kill(self):
        process = mock.Mock(returncode=None); process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired("ffmpeg", 15)
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=self.admitted_launch(process), run=self.exact_geometry)
        with mock.patch.object(R.threading, "Thread"):
            recorder.start(owned(width=1024, height=768), self.log)
        with self.assertRaisesRegex(RuntimeError, "survived"):
            recorder.stop()
        self.assertIs(recorder.process, process)
        self.assertEqual(recorder.failure["error_class"], "capture_finalize_timeout")
        self.assertEqual(recorder.failure["cleanup"]["status"], "failed")
        process.poll.return_value = 255; process.returncode = 255
        process.wait.side_effect = None
        recorder.stop()  # retry proves death and releases retained handles

    def test_capture_output_never_follows_existing_publication_symlink(self):
        victim = self.root / "victim"; victim.write_bytes(b"ORIGINAL")
        (self.root / "continuous.mp4").symlink_to(victim)
        process = mock.Mock(returncode=255); process.poll.return_value = None
        def launch(command, **kwargs):
            Path(command[-1]).write_bytes(b"CAPTURE")
            (self.root / "ffmpeg-progress.log").write_bytes(
                b"frame=1\ndup_frames=0\ndrop_frames=0\nprogress=continue\n"
                b"frame=2\ndup_frames=0\ndrop_frames=0\nprogress=end\n")
            return process
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=launch, run=self.exact_geometry)
        with mock.patch.object(R.threading, "Thread"):
            with self.assertRaisesRegex(RuntimeError, "publication"):
                recorder.start(owned(width=1024, height=768), self.log)
        self.assertEqual(victim.read_bytes(), b"ORIGINAL")

    def test_progress_destination_is_inherited_fd_and_never_follows_raced_symlink(self):
        victim = self.root / "victim-progress"; victim.write_bytes(b"ORIGINAL")
        process = mock.Mock(returncode=255); process.poll.side_effect = [None, None, 255, 255]
        process.wait.return_value = 255
        def launch(command, **kwargs):
            progress_path = self.root / "ffmpeg-progress.log"
            progress_path.unlink(); progress_path.symlink_to(victim)
            progress_target = command[command.index("-progress") + 1]
            self.assertRegex(progress_target, r"^/proc/self/fd/[0-9]+$")
            with open(progress_target, "wb", buffering=0) as stream:
                stream.write(b"frame=1\ndup_frames=0\ndrop_frames=0\nprogress=continue\n")
            Path(command[-1]).write_bytes(b"frame")
            self.assertIn(int(progress_target.rsplit('/', 1)[1]), kwargs["pass_fds"])
            return process
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=launch, run=self.exact_geometry, sleep=lambda _: None)
        with self.assertRaisesRegex(RuntimeError, "capture_log_read_failed"):
            recorder.start(owned(width=1024, height=768), self.log)
        self.assertEqual(victim.read_bytes(), b"ORIGINAL")

    def test_exact_window_command_and_schema2_fragments(self):
        process = mock.Mock(returncode=255); process.poll.return_value = None
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=self.admitted_launch(process), run=self.exact_geometry)
        with mock.patch.object(R.threading, "Thread"):
            recorder.start(owned(width=1024, height=768), self.log)
            command = recorder.capture["command"]
            self.assertEqual(command[command.index("-window_id") + 1], "0x2a")
            self.assertEqual(command[command.index("-video_size") + 1], "1024x768")
            self.assertEqual(command[command.index("-i") + 1], ":91.0")
            recorder.stop()
        receipt = recorder.receipt()
        self.assertEqual(receipt["cadence"]["distinct_game_frames"]["status"], "unvalidated")
        process.send_signal.assert_called_once_with(signal.SIGINT)

    def test_root_odd_and_changed_targets_refuse(self):
        with self.assertRaises(ValueError): owned(window="0x1")
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value, lease=FakeLease())
        with self.assertRaises(ValueError): recorder.start(owned(width=801), self.log)
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: owned(width=1024), lease=FakeLease())
        with self.assertRaisesRegex(RuntimeError, "changed"):
            recorder.start(owned(), self.log)

    def test_cross_lease_and_stop_time_exit_zero_fail(self):
        foreign = FakeLease(); foreign.lease_id = "other"
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value, lease=foreign)
        with self.assertRaisesRegex(RuntimeError, "another display lease"):
            recorder.start(owned(), self.log)
        process = mock.Mock(returncode=0); process.poll.return_value = 0
        recorder = R.X11WindowRecorder(self.root, verifier=lambda value: value,
            lease=FakeLease(), popen=self.admitted_launch(process), run=self.exact_geometry)
        with self.assertRaisesRegex(RuntimeError, "capture_process_exited"):
            recorder.start(owned(width=1024, height=768), self.log)
        self.assertEqual(recorder.failure["error_class"], "capture_process_exited")

    def test_input_revalidates_before_focus(self):
        verifier = mock.Mock(side_effect=RuntimeError("replaced"))
        port = OwnedX11Input.from_owned_window(owned(), runner=mock.Mock(), verifier=verifier)
        with self.assertRaisesRegex(RuntimeError, "replaced"): port.focus()

    def test_resize_and_early_exit_are_terminal_failure_evidence(self):
        for failure, process, verifier in (
            ("capture_binding_changed", mock.Mock(returncode=None), lambda value: owned(width=1024)),
            ("capture_process_exited", mock.Mock(returncode=0), lambda value: value),
        ):
            process.poll.return_value = None
            ticks = iter((0.0, .3, .4, .5))
            recorder = R.X11WindowRecorder(self.root, verifier=verifier, lease=FakeLease(),
                popen=mock.Mock(return_value=process), monotonic=lambda: next(ticks))
            recorder.target = owned(); recorder.process = process; recorder.started = 0.0
            recorder._scan_ffmpeg_log = mock.Mock(return_value=[])
            recorder._read_progress = mock.Mock(return_value=[])
            if failure == "capture_process_exited": process.poll.return_value = 0
            else:
                recorder.observe = mock.Mock()
                recorder._stop.wait = mock.Mock(side_effect=[False, True])
            if failure == "capture_process_exited": recorder._stop.wait = mock.Mock(side_effect=[False, True])
            recorder._watch_window(self.log)
            self.assertEqual(recorder.failure["error_class"], failure)
            evidence = json.loads((self.root / "capture-failure.json").read_text())
            self.assertEqual(evidence["initial_identity"]["id"], "0x2a")
            (self.root / "capture-failure.json").unlink()


class IntegratedLifecycleTests(unittest.TestCase):
    def test_explicit_backend_selection_returns_distinct_session(self):
        admitted = D.BackendCapabilities(D.GAMESCOPE_BACKEND, ("k1",), True,
            "xdotool-visible-pid", "ffmpeg-x11grab-window-id", "x11-xdotool",
            "glxinfo-B", "admitted", "test")
        with mock.patch.object(D, "detect_host", return_value=facts()), \
             mock.patch.object(D, "admit_backend", return_value=admitted):
            session, recorder, *_ = C.backend(D.GAMESCOPE_BACKEND)
        self.assertIs(session, W.LinuxWineGamescopeCreativeSession)
        self.assertIs(recorder, W.DeferredGamescopeRecorder)

    def test_gamescope_teardown_order_is_recorder_game_display(self):
        calls = []
        session = object.__new__(W.LinuxWineGamescopeCreativeSession)
        session.recorder = types.SimpleNamespace(stop=lambda: calls.append("recorder"))
        session.lease = types.SimpleNamespace(close=lambda: calls.append("display"))
        session._recorder_closed = session._session_closed = session._lease_closed = False
        session._cleanup_errors = []
        session.cleanup_receipt = {"status": "not_started", "order": [], "recorder": "not_started",
                                   "game_wine": "not_started", "display": "not_started"}
        with mock.patch.object(W.GameSession, "teardown", side_effect=lambda *a, **k: calls.append("game")):
            session.teardown()
        self.assertEqual(calls, ["recorder", "game", "display"])
        self.assertEqual(session.cleanup_receipt["status"], "passed")

    def test_every_cleanup_component_is_attempted_and_recorded_on_failure(self):
        for failed in ("recorder", "game_wine", "display"):
            with self.subTest(failed=failed):
                calls = []
                session = object.__new__(W.LinuxWineGamescopeCreativeSession)
                def component(name):
                    calls.append(name)
                    if name == failed: raise RuntimeError(name + " failed")
                session.recorder = types.SimpleNamespace(stop=lambda: component("recorder"))
                session.lease = types.SimpleNamespace(close=lambda: component("display"))
                session._recorder_closed = session._session_closed = session._lease_closed = False
                session._cleanup_errors = []
                session.cleanup_receipt = {"status": "not_started", "order": [],
                    "recorder": "not_started", "game_wine": "not_started", "display": "not_started"}
                with mock.patch.object(W.GameSession, "teardown", side_effect=lambda *a, **k: component("game_wine")):
                    with self.assertRaisesRegex(RuntimeError, "cleanup failed"): session.teardown()
                self.assertEqual(calls, ["recorder", "game_wine", "display"])
                self.assertEqual(session.cleanup_receipt[failed], "failed")
                self.assertEqual(session.cleanup_receipt["status"], "failed")

    def test_capture_monitor_wraps_non_do_step_and_interrupts_helper_wait(self):
        runner = object.__new__(CreativeRunner)
        runner.session = types.SimpleNamespace(check_capture=mock.Mock())
        step = types.SimpleNamespace(raw={"screenshot": True})
        with mock.patch("kpharness.creative_steps.ScenarioRunner.run_step", return_value="ok"):
            self.assertEqual(runner.run_step(step), "ok")
        self.assertEqual(runner.session.check_capture.call_count, 2)

        runner.session = types.SimpleNamespace(runtime_log=Path("/absent"),
            check_capture=mock.Mock(side_effect=[None, RuntimeError("capture lost")]))
        runner.ch = mock.Mock(); runner.ch.state.return_value = {"server_tick": 1}
        runner.watchdog = mock.Mock(); runner.run_dir = Path(tempfile.gettempdir())
        helper = types.SimpleNamespace(raw={"do": "advance_ticks", "ticks": 2, "timeout": 5})
        with self.assertRaisesRegex(RuntimeError, "capture lost"): runner._do(helper)

if __name__ == "__main__":
    unittest.main()
