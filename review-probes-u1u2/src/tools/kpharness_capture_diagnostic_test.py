#!/usr/bin/env python3
"""Host-only tests for the animated-pattern capture diagnostic driver.

Every host effect is injected. No Gamescope, mpv, FFmpeg, FFprobe, Wine, game,
X server, or canonical live-game lock is touched.
"""
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
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/harness"))
sys.path.insert(0, str(ROOT / "tools"))

from kpharness import capture_diagnostic as CD
from kpharness import creative_accept as A
from kpharness import display_backends as D
from kpharness import gamescope_snapshot as S
from kpharness import recording as R
import kpharness_gamescope_backend_test as B

REAL_LOCK = (ROOT / "tmp/harness-locks/live-game.lock").resolve()


def write_proc(root: Path, pid: int, comm: str, argv: list[str], *, start: str = "4242") -> None:
    entry = root / str(pid)
    entry.mkdir(parents=True)
    (entry / "comm").write_text(comm + "\n")
    (entry / "cmdline").write_bytes(b"\0".join(item.encode() for item in argv) + b"\0")
    fields = ["S", "1", str(pid), str(pid)] + ["0"] * 15 + [start]
    (entry / "stat").write_text(f"{pid} ({comm}) " + " ".join(fields) + "\n")


class ExitedChild:
    """A spawned child that already exited; the supervisor only polls it."""
    pid = 2 ** 22 + 17  # beyond pid_max defaults, never a real process

    def __init__(self, returncode=1):
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def send_signal(self, number):
        raise AssertionError("an exited child is never signalled")


class DiagnosticCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.proc = self.base / "proc"; self.proc.mkdir()
        self.operator = self.base / "operator"; self.operator.mkdir()
        self.log = self.operator / "commitments.log"; self.log.touch()
        self.lock = self.base / "fake-live-game.lock"
        self.runs = self.base / "runs"; self.runs.mkdir()
        # A real native executable stands in for FFmpeg and FFprobe; nothing executes it.
        self.tool = Path(sys.executable).resolve()

    def options(self, **overrides):
        values = dict(run_root=self.runs, snapshot=self.base / "snapshot", source_root=ROOT / "scripts/harness",
                      commitment_log=self.log, ffmpeg=str(self.tool), ffprobe=str(self.tool),
                      authorized_single_run=True)
        values.update(overrides)
        return types.SimpleNamespace(**values)

    def deps(self, **overrides):
        values = dict(proc_root=self.proc, lock_path=lambda: self.lock,
                      create_snapshot=mock.Mock(side_effect=lambda source, snapshot, entries: snapshot),
                      verify_snapshot=mock.Mock(return_value={"files": []}),
                      manifest_sha256=mock.Mock(return_value="5" * 64),
                      spawn_child=mock.Mock(return_value=ExitedChild()),
                      protected_displays=mock.Mock(return_value={"0": {"exists": False}}),
                      alive=lambda pid, start: False)
        values.update(overrides)
        return CD.Dependencies(**values)


class PreflightTests(DiagnosticCase):
    def test_preflight_refuses_unowned_game_display_and_capture_processes_with_proc_evidence(self):
        write_proc(self.proc, 101, "wineserver", ["/usr/bin/wineserver", "-p"])
        write_proc(self.proc, 102, "swkotor.exe", ["C:\\swkotor.exe"])
        write_proc(self.proc, 103, "gamescope-wl", ["gamescope", "--backend", "headless"])
        write_proc(self.proc, 104, "ffprobe", ["ffprobe", "-v", "error"])
        write_proc(self.proc, 105, "ffmpeg", ["ffmpeg", "-i", "x"])
        write_proc(self.proc, 106, "bash", ["bash"])
        write_proc(self.proc, 107, "Xwayland", ["Xwayland", ":1", "-auth", "/secret/path"])
        rows = CD.process_inventory(self.proc)
        blocked = CD.forbidden_processes(rows)
        self.assertEqual(sorted(row["pid"] for row in blocked), [101, 102, 103, 104, 105])
        self.assertEqual([row["argv"] for row in blocked if row["pid"] == 101], [["/usr/bin/wineserver", "-p"]])
        self.assertEqual(CD.forbidden_processes(rows, owned={(103, "4242")}),
                         [row for row in blocked if row["pid"] != 103])
        xwayland = next(row for row in rows if row["pid"] == 107)
        self.assertNotIn("/secret/path", json.dumps(xwayland))
        run = self.base / "run"; run.mkdir()
        with self.assertRaisesRegex(CD.DiagnosticRefused, "preflight"):
            CD.preflight(self.proc, run)
        evidence = json.loads((run / "preflight.json").read_text())
        self.assertEqual(sorted(row["pid"] for row in evidence["forbidden"]), [101, 102, 103, 104, 105])
        self.assertTrue(evidence["refused"])

    def test_supervisor_refuses_before_snapshot_or_launch_and_never_touches_canonical_lock(self):
        write_proc(self.proc, 101, "wineserver", ["wineserver"])
        opened = []
        real_open = os.open
        def guarded_open(path, *args, **kwargs):
            opened.append(Path(path).resolve() if not isinstance(path, int) else path)
            return real_open(path, *args, **kwargs)
        deps = self.deps()
        with mock.patch.object(CD, "canonical_lock_path", side_effect=AssertionError("canonical lock")), \
                mock.patch.object(CD.os, "open", side_effect=guarded_open), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CD.supervise(self.options(), deps), 1)
        self.assertNotIn(REAL_LOCK, opened)
        deps.create_snapshot.assert_not_called(); deps.spawn_child.assert_not_called()
        run, = list(self.runs.iterdir())
        self.assertTrue(json.loads((run / "preflight.json").read_text())["refused"])
        result = json.loads((run / "diagnostic-result.json").read_text())
        self.assertEqual((result["verdict"], result["launches"]), ("FAIL", 0))

    def test_supervisor_refuses_a_held_lock_before_preflight_snapshot_or_launch(self):
        holder = os.open(self.lock, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, holder)
        fcntl.flock(holder, fcntl.LOCK_EX)
        deps = self.deps()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CD.supervise(self.options(), deps), 1)
        deps.create_snapshot.assert_not_called(); deps.spawn_child.assert_not_called()
        run, = list(self.runs.iterdir())
        self.assertIn("lock", json.loads((run / "diagnostic-result.json").read_text())["errors"][0])

    def test_commitment_log_inside_run_root_or_missing_refuses_before_any_run_directory(self):
        for log in (None, self.operator / "missing.log"):
            with self.subTest(log=log), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "commitment log"):
                    CD.supervise(self.options(commitment_log=log), self.deps())
        self.assertEqual(list(self.runs.iterdir()), [])

    def test_cli_refuses_without_single_run_authorization(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = CD.main(["run", "--run-root", str(self.runs), "--snapshot", str(self.base / "snap"),
                            "--cleanup-commitment-log", str(self.log)])
        self.assertEqual(code, 2)
        self.assertEqual(list(self.runs.iterdir()), [])
        self.assertIn("authorized", stdout.getvalue())


class SnapshotAndCommitmentTests(DiagnosticCase):
    def test_real_snapshot_closure_contains_the_diagnostic_driver_and_verifies_source_equal(self):
        snapshot = self.base / "snapshot"
        S.create_snapshot(ROOT / "scripts/harness", snapshot, entries=CD.SNAPSHOT_ENTRIES)
        manifest = S.verify_snapshot(snapshot, source_root=ROOT / "scripts/harness", entries=CD.SNAPSHOT_ENTRIES)
        paths = {entry["path"] for entry in manifest["files"]}
        self.assertIn("kpharness/capture_diagnostic.py", paths)
        self.assertIn("kpharness/creative_accept.py", paths)
        self.assertIn("kpharness/recording.py", paths)

    def test_supervisor_snapshots_then_prints_commitments_before_the_single_launch(self):
        order = []
        stdout = io.StringIO()
        def create(source, snapshot, entries):
            order.append(("create", tuple(entries))); return snapshot
        def verify(snapshot, source_root, entries):
            order.append(("verify", Path(source_root), tuple(entries))); return {"files": []}
        def spawn(command, **kwargs):
            printed = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith("{")]
            order.append(("spawn", [line.get("kind") for line in printed], kwargs.get("pass_fds"),
                          kwargs.get("start_new_session")))
            return ExitedChild()
        deps = self.deps(create_snapshot=create, verify_snapshot=verify, spawn_child=spawn)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CD.supervise(self.options(), deps), 1)
        self.assertEqual(order[0], ("create", CD.SNAPSHOT_ENTRIES))
        self.assertEqual(order[1], ("verify", ROOT / "scripts/harness", CD.SNAPSHOT_ENTRIES))
        spawns = [item for item in order if item[0] == "spawn"]
        self.assertEqual(len(spawns), 1)
        self.assertIn(CD.COMMITMENT_KIND, spawns[0][1])
        # The lock descriptor and the supervisor token pipe; the child leads its own session.
        self.assertEqual(len(spawns[0][2]), 2)
        self.assertIs(spawns[0][3], True)
        run, = list(self.runs.iterdir())
        commitments = json.loads((run / "commitments.json").read_text())
        self.assertEqual(commitments["route_sha256"], R.sha256(run / "diagnostic-route.json"))
        self.assertEqual(commitments["ffprobe_sha256"], R.sha256(self.tool))
        self.assertEqual(commitments["ffmpeg"]["sha256"], R.sha256(self.tool))
        logged = [json.loads(line) for line in self.log.read_text().splitlines()]
        heads = [line for line in logged if line.get("kind") == A.LEDGER_HEAD_KIND]
        self.assertEqual(heads[-1]["cleanup_ledger_sha256"], commitments["cleanup_ledger_sha256"])
        self.assertIn(commitments, [line for line in logged if line.get("kind") == CD.COMMITMENT_KIND])
        route = json.loads((run / "diagnostic-route.json").read_text())
        self.assertEqual(route["client"], CD.client_command())
        self.assertIn("--title=" + CD.CLIENT_TITLE, route["client"])
        self.assertEqual(route["durations"], {"lead_seconds": 3.0, "acceptance_seconds": 30.0, "tail_seconds": 1.0})
        self.assertEqual(route["content_policy"], dict(D.CONTENT_POLICIES["animated-diagnostic-v1"]))
        result = json.loads((run / "diagnostic-result.json").read_text())
        self.assertEqual((result["launches"], result["verdict"]), (1, "FAIL"))

    def test_wrapper_script_or_missing_capture_tool_is_refused_before_launch(self):
        wrapper = self.base / "ffmpeg"; wrapper.write_text("#!/bin/sh\nexec /usr/bin/ffmpeg \"$@\"\n")
        wrapper.chmod(0o755)
        for field, value in (("ffmpeg", str(wrapper)), ("ffprobe", str(wrapper)),
                             ("ffmpeg", str(self.base / "absent"))):
            with self.subTest(field=field, value=value):
                for child in self.runs.iterdir():
                    shutil.rmtree(child)
                deps = self.deps()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(CD.supervise(self.options(**{field: value}), deps), 1)
                deps.spawn_child.assert_not_called()


class CleanupTests(DiagnosticCase):
    def test_ordered_cleanup_attempts_every_component_in_recorder_client_display_order(self):
        for failing in ("recorder", "source_process", "display"):
            with self.subTest(failing=failing):
                calls = []
                def step(name):
                    def run():
                        calls.append(name)
                        if name == failing:
                            raise RuntimeError(name + " failed")
                    return run
                result = CD.ordered_cleanup([(name, step(name)) for name in CD.CLEANUP_ORDER])
                self.assertEqual(calls, list(CD.CLEANUP_ORDER))
                self.assertEqual(result["order"], list(CD.CLEANUP_ORDER))
                self.assertEqual(result[failing], "failed"); self.assertEqual(result["status"], "failed")
        result = CD.ordered_cleanup([("recorder", None), ("source_process", lambda: None), ("display", lambda: None)])
        self.assertEqual((result["recorder"], result["status"]), ("not_started", "failed"))

    def test_client_stop_interrupts_then_kills_only_the_owned_process_with_bounded_waits(self):
        process = mock.Mock(); process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("mpv", 2), 0]
        CD.stop_client(process)
        process.send_signal.assert_called_once_with(signal.SIGINT)
        process.kill.assert_called_once_with()
        self.assertEqual([call.kwargs["timeout"] for call in process.wait.call_args_list], [2, 2])
        survivor = mock.Mock(); survivor.poll.return_value = None
        survivor.wait.side_effect = subprocess.TimeoutExpired("mpv", 2)
        with self.assertRaisesRegex(RuntimeError, "survived"):
            CD.stop_client(survivor)

    def test_child_orders_launch_markers_and_cleanup_and_passes_the_lock(self):
        events = []
        class Lease:
            lease_id = "lease-1"; width = 1024; height = 768
            environment = {"DISPLAY": ":91"}
            def __init__(self, run_dir, width, height, **kwargs):
                events.append(("lease", kwargs["popen"] is not None))
            def start(self): events.append(("lease.start",))
            def game_environment(self, base): return {"DISPLAY": ":91", **base}
            def close(self): events.append(("lease.close",))
            def receipt(self): return {"lease_id": self.lease_id}
            def is_alive(self): return True
        client = mock.Mock(pid=4321); client.poll.return_value = None; client.wait.return_value = 0
        def popen(command, **kwargs):
            events.append(("popen", command[0], tuple(kwargs.get("pass_fds", ()))))
            return client
        window = types.SimpleNamespace(window_id="0x2a", receipt=lambda: {"id": "0x2a"})
        class Recorder:
            def __init__(self, run_dir, **kwargs):
                events.append(("recorder", kwargs["ffmpeg"], kwargs["ffprobe"], kwargs["content_policy"],
                               kwargs["cadence_start_marker"], kwargs["cadence_end_marker"]))
            def start(self, target, native_log): events.append(("recorder.start", target.window_id))
            def check(self): events.append(("recorder.check",))
            def stop(self): events.append(("recorder.stop",))
            def receipt(self): return {"capture": {}, "cadence": {}, "media": {}, "failure": None}
        def sleep(seconds): events.append(("sleep", seconds))
        run = self.base / "child-run"; run.mkdir()
        config = CD.child_config(run, ffmpeg="/usr/bin/ffmpeg", ffprobe="/brew/ffprobe", lock_fd=77)
        evidence = CD.run_child(config, lease_factory=Lease, popen=popen,
            discover=lambda lease, pids, **kwargs: window, verifier_factory=lambda lease, **kwargs: (lambda value: value),
            recorder_factory=Recorder, sleep=sleep, monotonic=lambda: 0.0, start_reader=lambda pid: "999")
        names = [event[0] for event in events]
        self.assertEqual(names, ["lease", "lease.start", "popen", "recorder", "recorder.start", "sleep",
                                 "sleep", "sleep", "recorder.check", "recorder.stop", "lease.close"])
        self.assertEqual(events[2][1:], (CD.CLIENT, (77,)))
        self.assertEqual(events[3][1:], ("/usr/bin/ffmpeg", "/brew/ffprobe", "animated-diagnostic-v1",
                                         "pattern_start", "pattern_end"))
        self.assertEqual([event[1] for event in events if event[0] == "sleep"], [3.0, 30.0, 1.0])
        client.send_signal.assert_called_once_with(signal.SIGINT)
        log = (run / "diagnostic-native.log").read_text().splitlines()
        self.assertEqual(log, [CD.MARKER_LINES["pattern_start"], CD.MARKER_LINES["pattern_end"]])
        self.assertEqual(evidence["cleanup"]["order"], list(CD.CLEANUP_ORDER))
        self.assertEqual(evidence["cleanup"]["status"], "passed")
        self.assertEqual(evidence["client"], {"pid": 4321, "start": "999"})
        self.assertEqual(json.loads((run / "diagnostic-run.json").read_text())["cleanup"], evidence["cleanup"])

    def test_child_failure_still_cleans_up_in_order_and_retains_error(self):
        events = []
        class Lease:
            lease_id = "lease-1"; width = 1024; height = 768; environment = {"DISPLAY": ":91"}
            def __init__(self, *args, **kwargs): pass
            def start(self): events.append("lease.start")
            def game_environment(self, base): return dict(base)
            def close(self): events.append("lease.close")
            def receipt(self): return {}
        client = mock.Mock(pid=4321); client.poll.return_value = None; client.wait.return_value = 0
        class Recorder:
            def __init__(self, *args, **kwargs): pass
            def start(self, target, native_log): raise RuntimeError("capture_geometry_precondition: refused")
            def stop(self): events.append("recorder.stop")
            def receipt(self): return {"failure": {"error_class": "capture_geometry_precondition"}}
        run = self.base / "child-fail"; run.mkdir()
        evidence = CD.run_child(CD.child_config(run, ffmpeg="f", ffprobe="p", lock_fd=77), lease_factory=Lease,
            popen=lambda *args, **kwargs: client, discover=lambda *args, **kwargs: types.SimpleNamespace(
                window_id="0x2a", receipt=lambda: {}),
            verifier_factory=lambda *args, **kwargs: None, recorder_factory=Recorder,
            sleep=lambda seconds: events.append(("sleep", seconds)), monotonic=lambda: 0.0,
            start_reader=lambda pid: "999")
        self.assertEqual(events, ["lease.start", "recorder.stop", "lease.close"])
        self.assertIn("capture_geometry_precondition", evidence["error"])
        self.assertEqual(evidence["cleanup"]["status"], "passed")


class CriteriaTests(DiagnosticCase):
    def observation(self):
        run = Path(tempfile.mkdtemp(prefix="observed-", dir=self.base))
        media = run / "continuous.mp4"; media.write_bytes(b"animated frames")
        receipt = B.completed_receipt(run)
        cadence = receipt["cadence"]
        # Rename the fixture's acceptance markers to the diagnostic pair.
        cadence["content"] = B.fixture_content_block(run, media, R.sha256(media), cadence["probe_tool"],
            receipt["cadence"]["whole_capture"]["included_pts_seconds"], policy="animated-diagnostic-v1")
        recorder = {"capture": receipt["capture"], "cadence": cadence, "media": receipt["media"], "failure": None}
        return {"recorder": recorder, "window": receipt["window"],
                "lease": {"lease_id": "lease-1", "display": ":91", "width": 1024, "height": 768},
                "ffmpeg_log": "Input #0, x11grab\n", "media_sha256": R.sha256(media),
                "cleanup": {"status": "passed", "order": list(CD.CLEANUP_ORDER),
                            "recorder": "passed", "source_process": "passed", "display": "passed"},
                "owned_survivors": [], "ledger_clear": True,
                "protected_before": {"0": {"exists": True, "ino": 1}, "94": {"exists": False}},
                "protected_after": {"0": {"exists": True, "ino": 1}, "94": {"exists": False}},
                "route": {"acceptance_pair": ["phase_1", "complete"], "acceptance_seconds": 1.0},
                "snapshot_unchanged": True, "error": None}

    def test_complete_observation_passes_every_criterion(self):
        result = CD.evaluate(self.observation())
        self.assertEqual(result["verdict"], "PASS", {k: v for k, v in result["criteria"].items() if not v})
        self.assertEqual(set(result["criteria"]), set(CD.CRITERIA))

    def test_each_criterion_fails_independently(self):
        def shm(value):
            value["ffmpeg_log"] += "Continuing without shared memory (using fallback)\n"
        def first_frame(value):
            value["recorder"]["capture"]["startup"]["status"] = "timeout"
        def geometry(value):
            value["recorder"]["capture"]["geometry_precondition"]["pre_exec"]["border_width"] = 1
        def content(value):
            value["recorder"]["cadence"]["content"]["policy"] = dict(D.CONTENT_POLICIES["game-capture-v1"])
        def binding(value):
            value["recorder"]["cadence"]["pts_artifact"]["master_sha256"] = "0" * 64
        def rate(value):
            value["recorder"]["cadence"]["intervals"][0]["effective_fps"] = 59.0
        def missing(value):
            value["recorder"]["cadence"]["intervals"][0]["missing_or_dropped_ratio"] = .006
        def gap(value):
            value["recorder"]["cadence"]["intervals"][0]["maximum_gap_seconds"] = .051
        def duplicates(value):
            value["recorder"]["cadence"]["terminal_progress"]["dup_frames"] = 1
        def recomputed(value):
            value["recorder"]["cadence"]["intervals"][0]["p95_gap_seconds"] = .02
        def cleanup(value):
            value["cleanup"]["display"] = "failed"
        def survivors(value):
            value["owned_survivors"] = [{"pid": 4321, "start": "999"}]
        def ledger(value):
            value["ledger_clear"] = False
        def protected(value):
            value["protected_after"]["0"]["ino"] = 2
        def media(value):
            value["media_sha256"] = None
        def snapshot(value):
            value["snapshot_unchanged"] = False
        def error(value):
            value["error"] = "RuntimeError: boom"
        def route(value):
            value["route"]["acceptance_pair"] = ["pattern_start", "pattern_end"]
        cases = {"no_shm_fallback": shm, "first_frame_admission": first_frame, "exact_geometry": geometry,
                 "content_gate": content, "canonical_pts_binding": binding, "rate_at_least_99_percent": rate,
                 "missing_or_dropped_at_most_half_percent": missing, "maximum_gap_50ms": gap,
                 "zero_ffmpeg_duplicates": duplicates, "cadence_evidence_recomputed": recomputed,
                 "cleanup_complete": cleanup, "no_owned_survivors": survivors, "ledger_clear": ledger,
                 "protected_displays_unchanged": protected, "media_sha256_recorded": media,
                 "snapshot_unchanged": snapshot, "no_driver_error": error,
                 "acceptance_interval_matches_route": route}
        self.assertEqual(set(cases), set(CD.CRITERIA))
        for name, mutate in cases.items():
            with self.subTest(criterion=name):
                value = copy.deepcopy(self.observation()); mutate(value)
                result = CD.evaluate(value)
                self.assertFalse(result["criteria"][name])
                self.assertEqual(result["verdict"], "FAIL")



SUPERVISOR_SCRIPT = r"""
import subprocess, sys, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from kpharness import capture_diagnostic as CD
base = Path(sys.argv[2]); mode = sys.argv[3]; budget = float(sys.argv[4])
def spawn(command, **kwargs):
    kwargs.pop('cwd', None)
    return subprocess.Popen([sys.executable, str(base / 'dummy_child.py'), sys.argv[1], command[-1], mode],
                            **kwargs)
def kill_owned(identity):
    if mode == 'survivor' and identity.get('role') == 'client':
        return False  # stands in for a kill that fails; the result must name this survivor
    return CD.kill_owned_identity(identity)
deps = CD.Dependencies(proc_root=base / 'proc', lock_path=lambda: base / 'lock',
    create_snapshot=lambda source, snapshot, entries: snapshot,
    verify_snapshot=lambda snapshot, source_root, entries: {'files': []},
    manifest_sha256=lambda snapshot: '5' * 64, spawn_child=spawn, protected_displays=lambda: {},
    alive=CD.process_alive, cleanup_budget=budget, kill_owned=kill_owned)
options = types.SimpleNamespace(run_root=base / 'runs', snapshot=base / 'snapshot', source_root=sys.argv[1],
    commitment_log=base / 'operator' / 'commitments.log', ffmpeg=sys.executable, ffprobe=sys.executable,
    authorized_single_run=True)
sys.exit(CD.supervise(options, deps))
"""

DUMMY_CHILD_SCRIPT = r"""
import json, signal, subprocess, sys, time, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from kpharness import capture_diagnostic as CD
config = json.loads(Path(sys.argv[2]).read_text()); mode = sys.argv[3]
run = Path(config['run_dir'])
def step(name):
    time.sleep(.3)
    with (run / 'cleanup-steps.log').open('a') as stream:
        stream.write(name + '\n')
def start_of(pid):
    raw = Path(f'/proc/{pid}/stat').read_text()
    return raw[raw.rindex(')') + 1:].split()[19]
def popen(command, **kwargs):
    if command and command[0] == CD.CLIENT:
        command = ['sleep', '300']  # never mpv: a dummy stands in for the client
    return subprocess.Popen(command, **kwargs)
class Lease:
    lease_id = 'lease-dummy'; width = 1024; height = 768
    def __init__(self, run_dir, width, height, *, popen):
        self.popen = popen; self.process = None
    def start(self):
        self.process = self.popen(['sleep', '300'])  # same process group, like Gamescope
    def receipt(self):
        return {'lease_id': self.lease_id,
                'owner': {'gamescope': {'pid': self.process.pid, 'start': start_of(self.process.pid)}}}
    def game_environment(self, base):
        return dict(base)
    def close(self):
        step('display'); self.process.terminate(); self.process.wait(5)
class Recorder:
    def __init__(self, run_dir, **kwargs):
        self.process = None
    def start(self, window, native_log):
        if mode in ('stubborn', 'survivor'):
            for number in CD.INTERRUPT_SIGNALS:
                signal.signal(number, signal.SIG_IGN)  # a child that never cleans up
        (run / 'child-ready').write_text('ready')
    def check(self):
        pass
    def stop(self):
        step('recorder')
    def receipt(self):
        return {}
real_stop_client = CD.stop_client
def stop_client(process):
    step('source_process'); real_stop_client(process)
CD.stop_client = stop_client
window = types.SimpleNamespace(window_id='0x2a', receipt=lambda: {'id': '0x2a'})
CD.run_child(config, lease_factory=Lease, popen=popen, discover=lambda lease, pids, **kwargs: window,
             verifier_factory=lambda lease, **kwargs: (lambda value: value), recorder_factory=Recorder,
             sleep=time.sleep, monotonic=time.monotonic, start_reader=start_of)
sys.exit(1)
"""


class InterruptTests(unittest.TestCase):
    """R10-2 adversarial: a real supervisor, a real child, and real dummy grandchildren (no display)."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        for name in ("proc", "runs", "operator"):
            (self.base / name).mkdir()
        (self.base / "operator" / "commitments.log").touch()
        (self.base / "supervisor.py").write_text(SUPERVISOR_SCRIPT)
        (self.base / "dummy_child.py").write_text(DUMMY_CHILD_SCRIPT)
        self.leftovers = []
        self.addCleanup(self.kill_leftovers)

    def kill_leftovers(self):
        for identity in self.leftovers:
            if CD.process_alive(identity["pid"], identity["start"]):
                CD.kill_owned_identity(identity)

    def run_supervisor(self, mode, budget, signals, *, gap=0.1):
        supervisor = subprocess.Popen(
            [sys.executable, str(self.base / "supervisor.py"), str(ROOT / "scripts/harness"), str(self.base),
             mode, str(budget)], start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 60
        while not list((self.base / "runs").glob("*/child-ready")):
            if time.monotonic() > deadline or supervisor.poll() is not None:
                supervisor.kill(); output = supervisor.communicate()[0].decode(errors="replace")
                self.fail("dummy child never became ready: " + output)
            time.sleep(.05)
        run, = list((self.base / "runs").iterdir())
        owned = json.loads((run / CD.OWNED_FILE).read_text())
        self.leftovers.extend(owned)
        for number in signals:
            # A terminal delivers Ctrl-C and hangup to the whole foreground group.
            os.killpg(supervisor.pid, number)
            time.sleep(gap)
        output = supervisor.communicate(timeout=120)[0].decode(errors="replace")
        result = json.loads((run / "diagnostic-result.json").read_text())
        return supervisor.returncode, result, run, owned, output

    def assert_ordered_cleanup_completed(self, code, result, run, owned, interrupts):
        self.assertEqual(code, 1)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["interrupts"], interrupts)
        self.assertFalse(result["cleanup_budget"]["exhausted"])
        self.assertNotIn("kill", result["cleanup_budget"])
        self.assertEqual((run / "cleanup-steps.log").read_text().splitlines(), list(CD.CLEANUP_ORDER))
        evidence = json.loads((run / "diagnostic-run.json").read_text())
        self.assertEqual(evidence["cleanup"]["status"], "passed")
        # Exactly one SIGINT was forwarded, however many the terminal sent.
        self.assertEqual(evidence["interrupts"], ["SIGINT"])
        self.assertIn("DiagnosticInterrupted", evidence["error"])
        self.assertEqual(result["owned_survivors"], [])
        self.assertEqual({item["role"] for item in owned}, {"display:gamescope", "client"})
        for identity in owned:
            self.assertFalse(CD.process_alive(identity["pid"], identity["start"]), identity)

    def test_sigint_runs_the_ordered_cleanup_before_the_supervisor_exits(self):
        code, result, run, owned, _ = self.run_supervisor("cooperative", 60, [signal.SIGINT])
        self.assert_ordered_cleanup_completed(code, result, run, owned, ["SIGINT"])

    def test_sighup_runs_the_ordered_cleanup_before_the_supervisor_exits(self):
        code, result, run, owned, _ = self.run_supervisor("cooperative", 60, [signal.SIGHUP])
        self.assert_ordered_cleanup_completed(code, result, run, owned, ["SIGHUP"])

    def test_repeated_sigint_never_cuts_the_ordered_cleanup_short(self):
        code, result, run, owned, _ = self.run_supervisor(
            "cooperative", 60, [signal.SIGINT, signal.SIGINT, signal.SIGINT], gap=.15)
        self.assert_ordered_cleanup_completed(code, result, run, owned, ["SIGINT", "SIGINT", "SIGINT"])

    def test_after_the_budget_only_owned_processes_are_killed(self):
        bystander = subprocess.Popen(["sleep", "300"], start_new_session=True)
        self.addCleanup(bystander.wait)
        self.addCleanup(bystander.kill)
        started = time.monotonic()
        code, result, run, owned, _ = self.run_supervisor("stubborn", 2, [signal.SIGINT])
        self.assertGreaterEqual(time.monotonic() - started, 2)
        self.assertEqual(code, 1)
        self.assertTrue(result["cleanup_budget"]["exhausted"])
        self.assertTrue(result["cleanup_budget"]["kill"]["child_group_killed"])
        self.assertFalse((run / "cleanup-steps.log").exists())
        self.assertEqual(result["owned_survivors"], [])
        for identity in owned:
            self.assertFalse(CD.process_alive(identity["pid"], identity["start"]), identity)
        self.assertIsNone(bystander.poll())

    def test_a_survivor_after_the_budget_is_listed_exactly(self):
        code, result, run, owned, _ = self.run_supervisor("survivor", 2, [signal.SIGINT])
        self.assertEqual(code, 1)
        client = next(item for item in owned if item["role"] == "client")
        self.assertTrue(CD.process_alive(client["pid"], client["start"]))
        self.assertEqual(result["owned_survivors"], [client])
        self.assertEqual(result["cleanup_budget"]["kill"]["kill_failures"],
                         [{**client, "error": "kill refused or failed"}])

    def test_cleanup_budget_is_the_sum_of_the_component_bounds(self):
        self.assertEqual(CD.CLEANUP_BUDGET_SECONDS, float(sum(CD.CLEANUP_BUDGET_COMPONENTS.values())))
        frames = CD._DIAGNOSTIC_FRAMES
        self.assertGreaterEqual(CD.CLEANUP_BUDGET_COMPONENTS["recorder"], 2 * R.probe_deadline_seconds(frames))
        self.assertEqual(CD.Dependencies.host().cleanup_budget, CD.CLEANUP_BUDGET_SECONDS)
        self.assertIs(CD.Dependencies.host().spawn_child, subprocess.Popen)


class ChildAuthorityTests(DiagnosticCase):
    """R10-4 adversarial: ``--child`` needs the supervisor's token pipe and the held lock."""

    def authority_fixture(self, *, token=None, committed=None, pipe=True):
        run = self.base / "authority-run"; run.mkdir(exist_ok=True)
        read_fd, sha = CD.create_child_token() if pipe else (os.open(self.log, os.O_RDONLY), "0" * 64)
        self.addCleanup(lambda: os.close(read_fd) if self.fd_open(read_fd) else None)
        (run / "commitments.json").write_text(json.dumps({"child_token_sha256": committed or sha}))
        config = CD.child_config(run, ffmpeg="f", ffprobe="p", lock_fd=77, token_fd=read_fd,
                                 token_sha256=token or sha)
        return config

    @staticmethod
    def fd_open(descriptor):
        try:
            os.fstat(descriptor); return True
        except OSError:
            return False

    def test_supervisor_started_child_with_the_held_lock_is_admitted(self):
        config = self.authority_fixture()
        held = CD.verify_child_authority(config, lock_guard=lambda: {"fd": 77, "exclusive": True})
        self.assertEqual(held["fd"], 77)
        self.assertFalse(self.fd_open(config["token_fd"]))

    def test_forged_or_missing_token_or_foreign_lock_is_refused(self):
        guard = lambda: {"fd": 77}
        cases = {
            "no_token_fd": lambda: {**self.authority_fixture(), "token_fd": None},
            "token_digest_forged": lambda: self.authority_fixture(token="a" * 64, committed="a" * 64),
            "commitment_differs": lambda: self.authority_fixture(committed="b" * 64),
            "not_a_pipe": lambda: self.authority_fixture(pipe=False),
        }
        for name, build in cases.items():
            with self.subTest(name=name), self.assertRaises(CD.DiagnosticRefused):
                CD.verify_child_authority(build(), lock_guard=guard)
        with self.assertRaisesRegex(CD.DiagnosticRefused, "lock"):
            CD.verify_child_authority(self.authority_fixture(), lock_guard=lambda: {"fd": 78})
        def unheld():
            raise RuntimeError("canonical live lock is not held by this controller")
        with self.assertRaisesRegex(CD.DiagnosticRefused, "lock"):
            CD.verify_child_authority(self.authority_fixture(), lock_guard=unheld)

    def test_child_entry_refuses_before_any_lease_without_the_token(self):
        run = self.base / "manual-child"; run.mkdir()
        config = run / "diagnostic-config.json"
        config.write_text(json.dumps(CD.child_config(run, ffmpeg="f", ffprobe="p", lock_fd=77)))
        from kpharness import gamescope_xwayland as G
        with mock.patch.object(G, "GamescopeXwaylandLease", side_effect=AssertionError("lease")), \
                self.assertRaises(CD.DiagnosticRefused):
            CD.main(["--child", str(config)])
        self.assertFalse((run / "diagnostic-run.json").exists())


class PreflightRound11Tests(DiagnosticCase):
    """R10-4 correctness / R10-5 adversarial."""

    def test_unreadable_proc_row_of_this_user_refuses(self):
        write_proc(self.proc, 201, "bash", ["bash"])
        (self.proc / "202").mkdir()
        (self.proc / "202" / "comm").write_text("wineserver\n")
        (self.proc / "202" / "cmdline").mkdir()  # reading it fails
        (self.proc / "202" / "stat").write_text("202 (wineserver) S 1 202 202" + " 0" * 16 + " 4242\n")
        run = self.base / "run-unreadable"; run.mkdir()
        with self.assertRaisesRegex(CD.DiagnosticRefused, "could not read"):
            CD.preflight(self.proc, run, self_pid=1)
        evidence = json.loads((run / "preflight.json").read_text())
        self.assertEqual([row["pid"] for row in evidence["unreadable"]], [202])
        self.assertTrue(evidence["refused"])

    def test_wrapped_renamed_and_exe_targets_are_detected(self):
        write_proc(self.proc, 301, "bash", ["/bin/bash", "/home/u/.local/bin/ffmpeg", "-i", "x"])
        write_proc(self.proc, 302, "kworkerish", ["kworkerish"])
        os.symlink("/usr/bin/gamescope", self.proc / "302" / "exe")
        write_proc(self.proc, 303, "python3", ["python3", "/opt/tools/ffprobe", "-v"])
        write_proc(self.proc, 304, "env", ["env", "WINEPREFIX=/x", "wineserver", "-p"])
        write_proc(self.proc, 305, "bash", ["bash", "-c", "echo notes"])
        write_proc(self.proc, 306, "vim", ["vim", "notes/ffmpeg.txt"])
        rows = CD.process_inventory(self.proc)
        self.assertEqual(sorted(row["pid"] for row in CD.forbidden_processes(rows)), [301, 302, 303, 304])

    def test_env_wrapped_target_after_assignments_is_detected(self):
        write_proc(self.proc, 401, "env", ["/usr/bin/env", "wineserver", "-p"])
        rows = CD.process_inventory(self.proc)
        self.assertEqual([row["pid"] for row in CD.forbidden_processes(rows)], [401])

    def test_own_launch_chain_is_excluded_and_nothing_is_ever_signalled(self):
        write_proc(self.proc, 501, "sh", ["sh", "-c", "python3 -m kpharness.capture_diagnostic run --ffmpeg /usr/bin/ffmpeg"])
        entry = self.proc / "502"; entry.mkdir()
        (entry / "comm").write_text("python3\n")
        (entry / "cmdline").write_bytes(b"python3\0/x/capture_diagnostic.py\0--ffprobe\0/b/ffprobe\0")
        (entry / "stat").write_text("502 (python3) S 501 502 502" + " 0" * 16 + " 4242\n")
        write_proc(self.proc, 503, "ffmpeg", ["ffmpeg"])
        run = self.base / "run-chain"; run.mkdir()
        with mock.patch.object(CD.os, "kill", side_effect=AssertionError("kill")), \
                mock.patch.object(CD.os, "killpg", side_effect=AssertionError("killpg")), \
                self.assertRaisesRegex(CD.DiagnosticRefused, "preflight"):
            CD.preflight(self.proc, run, self_pid=502)
        evidence = json.loads((run / "preflight.json").read_text())
        self.assertEqual([row["pid"] for row in evidence["forbidden"]], [503])
        self.assertIn(502, evidence["launch_chain_excluded"])


class LockInheritanceTests(DiagnosticCase):
    """R10-3 correctness: FFprobe and xwininfo children inherit the lock descriptor."""

    def test_child_passes_the_lock_to_recorder_probes_and_every_query(self):
        seen = {}
        class Lease:
            lease_id = "lease-1"; width = 1024; height = 768
            def __init__(self, *args, **kwargs): pass
            def start(self): pass
            def game_environment(self, base): return dict(base)
            def close(self): pass
            def receipt(self): return {}
        client = mock.Mock(pid=4321); client.poll.return_value = None; client.wait.return_value = 0
        def discover(lease, pids, *, run, monotonic):
            run(["xwininfo", "-root"]); return types.SimpleNamespace(window_id="0x2a", receipt=lambda: {})
        class Recorder:
            def __init__(self, run_dir, **kwargs):
                seen["inherited_fds"] = kwargs["inherited_fds"]
                kwargs["run"](["xwininfo", "-id", "0x2a"])
            def start(self, *args): pass
            def check(self): pass
            def stop(self): pass
            def receipt(self): return {}
        queries = []
        run_dir = self.base / "lock-run"; run_dir.mkdir()
        CD.run_child(CD.child_config(run_dir, ffmpeg="f", ffprobe="p", lock_fd=77), lease_factory=Lease,
            popen=lambda *args, **kwargs: client, discover=discover,
            verifier_factory=lambda lease, **kwargs: None, recorder_factory=Recorder,
            sleep=lambda seconds: None, monotonic=lambda: 0.0, start_reader=lambda pid: "999",
            run=lambda command, **kwargs: queries.append((command[1], kwargs.get("pass_fds"))))
        self.assertEqual(seen["inherited_fds"], (77,))
        self.assertEqual(queries, [("-root", (77,)), ("-id", (77,))])

    def test_recorder_default_probes_and_queries_inherit_the_descriptor_with_scaled_deadlines(self):
        captured = []
        def fake_probe(name):
            def probe(path, executable, **kwargs):
                captured.append((name, kwargs["pass_fds"], kwargs["deadline_seconds"])); return []
            return probe
        lease = B.FakeLease()
        queries = []
        recorder = R.X11WindowRecorder(self.base, verifier=lambda value: value, lease=lease,
            inherited_fds=(77,), run=lambda command, **kwargs: queries.append(kwargs.get("pass_fds"))
            or B.geometry_query()(command, **kwargs))
        with mock.patch.object(R, "probe_frame_pts", fake_probe("pts")), \
                mock.patch.object(R, "probe_frame_content", fake_probe("content")):
            recorder._probe_frames = 36_000
            recorder._pts_probe(Path("/x"), "ffprobe")
            recorder._content_probe(Path("/proc/self/fd/41"), "ffprobe", pass_fds=(41,))
        self.assertEqual(captured[0], ("pts", (77,), R.probe_deadline_seconds(36_000)))
        self.assertEqual(captured[1], ("content", (41, 77), R.probe_deadline_seconds(36_000)))
        recorder._geometry(B.owned(width=1024, height=768))
        self.assertEqual(queries, [(77,), (77,)])
        with self.assertRaises(ValueError):
            R.X11WindowRecorder(self.base, verifier=lambda value: value, lease=lease, inherited_fds=(1,))


if __name__ == "__main__":
    unittest.main()
