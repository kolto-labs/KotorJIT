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
import math
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
from kpharness import gamescope_socket as G
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
                            "--cleanup-commitment-log", str(self.log), "--ffprobe", str(self.tool)])
        self.assertEqual(code, 2)
        self.assertEqual(list(self.runs.iterdir()), [])
        self.assertIn("authorized", stdout.getvalue())

    def test_ffprobe_has_no_default_and_must_be_given_explicitly(self):
        # Publication: no host-specific FFprobe default ships; the operator names the ELF.
        self.assertFalse(hasattr(CD, "DEFAULT_FFPROBE"))
        stderr = io.StringIO()
        with mock.patch.object(CD, "supervise", side_effect=AssertionError("supervise")), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr), \
                self.assertRaises(SystemExit) as raised:
            CD.main(["run", "--run-root", str(self.runs), "--snapshot", str(self.base / "snap"),
                     "--cleanup-commitment-log", str(self.log), "--authorized-single-run"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--ffprobe", stderr.getvalue())
        self.assertEqual(list(self.runs.iterdir()), [])
        self.assertNotIn("linuxbrew", Path(CD.__file__).read_text())


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
        self.assertEqual(route["content_policy"], dict(D.CONTENT_POLICIES["animated-diagnostic-v2"]))
        result = json.loads((run / "diagnostic-result.json").read_text())
        self.assertEqual((result["launches"], result["verdict"]), (1, "FAIL"))
        # The recomputed separation (with its histogram) is part of the result; None without content.
        self.assertIn("content_separation", result)
        self.assertIsNone(result["content_separation"])
        self.assertIn("content_level_sequence", result)
        self.assertIsNone(result["content_level_sequence"])
        self.assertEqual(result["failing_criteria"], [name for name in CD.CRITERIA if not result["criteria"][name]])
        self.assertIn("no_driver_error", result["failing_criteria"])
        self.assertEqual(result["supervisor_threads_at_spawn"], 1)
        # The explicit FFprobe is recorded by resolved path and SHA-256.
        self.assertEqual((commitments["ffprobe_resolved_path"], commitments["ffprobe_sha256"]),
                         (str(self.tool), R.sha256(self.tool)))
        preflight = json.loads((run / "preflight.json").read_text())
        self.assertIn({"role": "ffprobe", "resolved_path": str(self.tool), "sha256": R.sha256(self.tool)},
                      preflight["tool_identities"])

    def test_a_multithreaded_supervisor_refuses_before_the_spawn(self):
        # The spawn-window signal block only holds for a single-threaded supervisor.
        import threading
        release = threading.Event(); worker = threading.Thread(target=release.wait); worker.start()
        self.addCleanup(worker.join); self.addCleanup(release.set)
        deps = self.deps()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CD.supervise(self.options(), deps), 1)
        deps.spawn_child.assert_not_called()
        run, = list(self.runs.iterdir())
        result = json.loads((run / "diagnostic-result.json").read_text())
        self.assertIn("single-threaded", " ".join(result["errors"]))

    def test_a_raw_native_thread_is_counted_and_the_supervisor_refuses(self):
        # R12-4 / R12C-m5b: a _thread thread is invisible to threading.active_count().
        import _thread
        import threading
        baseline = len(os.listdir("/proc/self/task"))
        started, release = threading.Event(), threading.Event()
        def worker():
            started.set(); release.wait(10)
        def stop_worker():
            release.set()
            deadline = time.monotonic() + 5
            while len(os.listdir("/proc/self/task")) > baseline and time.monotonic() < deadline:
                time.sleep(.01)
        _thread.start_new_thread(worker, ())
        self.addCleanup(stop_worker)
        self.assertTrue(started.wait(5))
        self.assertEqual(threading.active_count(), 1)
        deps = self.deps()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CD.supervise(self.options(), deps), 1)
        deps.spawn_child.assert_not_called()
        run, = list(self.runs.iterdir())
        result = json.loads((run / "diagnostic-result.json").read_text())
        self.assertIn("single-threaded", " ".join(result["errors"]))
        self.assertGreaterEqual(result["supervisor_threads_at_spawn"], 2)
        self.assertEqual(result["launches"], 0)

    def test_snapshot_child_lock_path_equals_the_supervisor_lock_path(self):
        # Pure paths: the child's manifest-derived lock must be the lock the supervisor takes.
        snapshot = self.base / "snapshot-lock"
        S.create_snapshot(ROOT / "scripts/harness", snapshot, entries=CD.SNAPSHOT_ENTRIES)
        module = snapshot / "runtime" / "kpharness" / "capture_diagnostic.py"
        self.assertEqual(G.canonical_lock_path_for(G.trusted_repository_root(module)), CD.canonical_lock_path())
        self.assertEqual(CD.trusted_lock_path(), CD.canonical_lock_path())

    def test_commitments_append_revalidates_the_log_before_the_single_launch(self):
        # R10-3 adversarial: the supervisor re-validates the operator log before appending.
        real_init = CD.initialize_cleanup_ledger
        def init_then_hard_link(run_dir, *, commitment_log):
            head = real_init(run_dir, commitment_log=commitment_log)
            os.link(commitment_log, self.operator / "backup.log")
            return head
        deps = self.deps()
        with mock.patch.object(CD, "initialize_cleanup_ledger", init_then_hard_link), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CD.supervise(self.options(), deps), 1)
        deps.spawn_child.assert_not_called()
        run, = list(self.runs.iterdir())
        result = json.loads((run / "diagnostic-result.json").read_text())
        self.assertEqual(result["launches"], 0)
        self.assertIn("unique regular", result["errors"][0])
        self.assertNotIn(CD.COMMITMENT_KIND, self.log.read_text())

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


class PatternTests(unittest.TestCase):
    """R11-C1 ruling: every fresh frame changes the whole frame, whatever the pattern speed."""

    @staticmethod
    def brightness(frame):
        expression = CD.PATTERN_STEP.split("brightness=", 1)[1].split(":", 1)[0]
        return eval(expression, {"floor": math.floor, "__builtins__": {}}, {"n": frame})

    def test_client_plays_the_stepped_pattern_from_one_graph(self):
        self.assertTrue(CD.PATTERN_GRAPH.startswith(
            f"testsrc2=size={CD.WIDTH}x{CD.HEIGHT}:rate={CD.FPS},{CD.PATTERN_STEP},"))
        self.assertTrue(CD.PATTERN_GRAPH.endswith(CD.PATTERN_INDEX_FILTERS))
        self.assertEqual(CD.client_command()[-1], "av://lavfi:" + CD.PATTERN_GRAPH)
        self.assertTrue(CD.PATTERN_STEP.startswith("eq="))
        self.assertIn(":eval=frame", CD.PATTERN_STEP)
        self.assertNotIn(",", CD.PATTERN_STEP)  # no filtergraph escaping needed in mpv's av://lavfi: URL
        route = CD.route_document("/usr/bin/ffmpeg")
        self.assertEqual(route["pattern"]["graph"], CD.PATTERN_GRAPH)
        self.assertEqual(route["pattern"]["step"]["period_frames"], CD.PATTERN_PERIOD_FRAMES)
        self.assertTrue(route["pattern"]["changes_every_frame"])

    def test_every_source_distance_inside_the_period_moves_the_whole_frame_a_level(self):
        period = CD.PATTERN_PERIOD_FRAMES
        levels = [round(self.brightness(frame) / CD.PATTERN_LEVEL_STEP) for frame in range(4 * period)]
        self.assertEqual(sorted(set(levels)), list(range(-(period // 2), period // 2 + 1)))
        for distance in range(1, period):
            for frame in range(3 * period):
                self.assertGreaterEqual(abs(levels[frame + distance] - levels[frame]), 1, (distance, frame))
        # Adjacent frames move at least three levels.
        self.assertGreaterEqual(min(abs(levels[f + 1] - levels[f]) for f in range(3 * period)), 3)
        # Blind spot: a skip of exactly one period repeats the level. The cadence gate's
        # maximum gap (50 ms, 3 frame intervals at 60 FPS) rejects any capture that skips that far.
        self.assertEqual(levels[period], levels[0])
        self.assertLess(math.ceil(D.CADENCE_POLICY["maximum_gap_seconds"] * CD.FPS), period)


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
        self.assertEqual(events[3][1:], ("/usr/bin/ffmpeg", "/brew/ffprobe", "animated-diagnostic-v2",
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
            receipt["cadence"]["whole_capture"]["included_pts_seconds"], policy="animated-diagnostic-v2")
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

    def with_content_rows(self, value, rows, *, claim=None):
        cadence = value["recorder"]["cadence"]
        path = Path(cadence["content"]["artifact"]["path"])
        artifact = json.loads(path.read_text()); artifact["frames"] = rows; artifact["frame_count"] = len(rows)
        path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n")
        policy = D.CONTENT_POLICIES["animated-diagnostic-v2"]
        pts = value["recorder"]["cadence"]["whole_capture"]["included_pts_seconds"]
        cadence["content"] = {"artifact": {**cadence["content"]["artifact"], "sha256": R.sha256(path),
                                           "frame_count": len(rows)},
                              **D.evaluate_content(claim or rows, pts, 1.0, 2.0, policy)}
        return value

    def rows(self, change, fresh=lambda index: True, yavg=None, count=121):
        """Fixture rows with the given differences; yavg follows the pattern ladder over ``fresh`` frames."""
        base = B.fixture_content_probe(None, None)
        base = (base * ((count + len(base) - 1) // len(base)))[:count]
        base = B.with_index_fields(base)
        levels = B.ladder_yavg([fresh(index) for index in range(len(base))]) if yavg is None else yavg
        return [{**row, "yavg": levels[index], "ydif": 0.0 if index == 0 else change(index), "udif": 0.0,
                 "vdif": 0.0} for index, row in enumerate(base)]

    def ambiguous(self):
        floor = D.CONTENT_POLICIES["animated-diagnostic-v2"]["distinct_noise_floor"]
        return self.with_content_rows(self.observation(), self.rows(lambda index: floor))

    def test_guard_band_content_is_calibration_ambiguous_whatever_else_passes(self):
        floor = D.CONTENT_POLICIES["animated-diagnostic-v2"]["distinct_noise_floor"]
        value = self.with_content_rows(self.observation(), self.rows(lambda index: floor))
        result = CD.evaluate(value)
        self.assertEqual(result["verdict"], "calibration_ambiguous")
        self.assertEqual(result["content_separation"]["status"], "ambiguous")
        self.assertGreater(result["content_separation"]["inside_band"], 0)
        self.assertEqual(sum(item["count"] for item in result["content_separation"]["histogram"]),
                         result["content_separation"]["below_band"] + result["content_separation"]["inside_band"]
                         + result["content_separation"]["above_band"])
        self.assertFalse(result["criteria"]["content_gate"])
        # Only the content-derived criteria fail (the recomputed cadence verdict includes the content gate).
        self.assertEqual([name for name, passed in result["criteria"].items() if not passed],
                         ["content_gate", "cadence_evidence_recomputed"])
        self.assertEqual(result["failing_criteria"], ["content_gate", "cadence_evidence_recomputed"])
        self.assertTrue(result["cadence_recomputed_apart_from_content"])
        self.assertEqual(result["content_level_sequence"]["status"], "passed")
        self.assertEqual(set(result["criteria"]), set(CD.CRITERIA))

    def test_any_failed_non_content_criterion_makes_ambiguous_content_a_fail(self):
        # R12-3 / R12C-m5a: calibration_ambiguous only when every non-content criterion passes.
        mutations = self.criterion_mutations()
        non_content = [name for name in CD.CRITERIA if name != "content_gate"]
        self.assertEqual(set(non_content), set(mutations) - {"content_gate"})
        for name in non_content:
            with self.subTest(criterion=name):
                value = copy.deepcopy(self.ambiguous()); mutations[name](value)
                result = CD.evaluate(value)
                if name != "canonical_pts_binding":  # an unbound PTS artifact recomputes no content
                    self.assertEqual(result["content_separation"]["status"], "ambiguous")
                self.assertFalse(result["criteria"][name])
                self.assertEqual(result["verdict"], "FAIL")
                self.assertIn(name, result["failing_criteria"])
                self.assertIn("content_gate", result["failing_criteria"])
                self.assertEqual(result["failing_criteria"],
                                 [item for item in CD.CRITERIA if not result["criteria"][item]])

    def test_a_content_sequence_failure_is_a_fail_even_when_separation_is_ambiguous(self):
        floor = D.CONTENT_POLICIES["animated-diagnostic-v2"]["distinct_noise_floor"]
        # The step did not render: yavg barely moves while the differences sit in the band.
        drift = [120.0 + 0.3 * math.sin(index / 9.0) for index in range(121)]
        value = self.with_content_rows(self.observation(), self.rows(lambda index: floor * 0.9, yavg=drift))
        result = CD.evaluate(value)
        self.assertEqual(result["content_separation"]["status"], "ambiguous")
        self.assertEqual(result["content_level_sequence"]["status"], "failed")
        self.assertEqual(result["verdict"], "FAIL")
        content = value["recorder"]["cadence"]["content"]
        self.assertTrue(any(item.startswith("capture_content_sequence") for item in content["failures"]))
        # A two-frame stale loop with clean differences is also a FAIL, not a pass.
        loop = [B.pattern_yavg(index % 2) for index in range(121)]
        value = self.with_content_rows(self.observation(), self.rows(lambda index: 20.0, yavg=loop))
        result = CD.evaluate(value)
        self.assertEqual((result["verdict"], result["content_separation"]["status"]), ("FAIL", "separated"))
        self.assertGreater(result["content_level_sequence"]["violation_count"], 0)

    def test_within_policy_source_drop_keeps_level_and_index_gates_green(self):
        policy = dict(D.CONTENT_POLICIES["animated-diagnostic-v2"])
        source = [0]
        for row in range(1, 361):
            source.append(source[-1] + (2 if row == 61 else 1))
        rows = B.with_index_fields([{key: value for key, value in row.items()
                                     if key not in ("index_top", "index_bottom")}
                                    for row in self.rows(lambda index: 20.0, count=361)], source)
        rows = [{**row, "yavg": B.pattern_yavg(source[index])} for index, row in enumerate(rows)]
        pts = [index / 60 for index in range(len(rows))]
        result = D.evaluate_content(rows, pts, 1.0, 7.0, policy)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["index_sequence"]["estimated_dropped_source_frames"], 1)
        self.assertEqual(result["level_sequence"]["status"], "passed")

    def test_duplicate_then_skip_accepts_ffprobe_microsecond_pts(self):
        policy = dict(D.CONTENT_POLICIES["animated-diagnostic-v2"])
        source = list(range(361))
        source[61] = source[60]
        rows = B.with_index_fields([{key: value for key, value in row.items()
                                     if key not in ("index_top", "index_bottom")}
                                    for row in self.rows(lambda index: 20.0, count=361)], source)
        rows = [{**row, "yavg": B.pattern_yavg(source[index]),
                 "ydif": 0.0 if index == 61 else 20.0}
                for index, row in enumerate(rows)]
        # best_effort_timestamp_time is emitted at six decimal places.
        pts = [float(f"{index / 60:.6f}") for index in range(len(rows))]
        result = D.evaluate_content(rows, pts, 1.0, 7.0, policy)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["index_sequence"]["estimated_dropped_source_frames"], 1)
        # An actual timing mismatch larger than the serialization uncertainty
        # must still fail, even though the total source-drop budget is valid.
        pts[62] -= 0.00001
        result = D.evaluate_content(rows, pts, 1.0, 7.0, policy)
        self.assertTrue(any(v["kind"] == "index_step_disagrees_with_elapsed_time"
                            for v in result["index_sequence"]["violations"]), result)

    def test_sustained_delta_two_is_rejected_by_accumulated_source_drop_ratio(self):
        policy = dict(D.CONTENT_POLICIES["animated-diagnostic-v2"])
        source = list(range(0, 720, 2))
        rows = B.with_index_fields([{key: value for key, value in row.items()
                                     if key not in ("index_top", "index_bottom")}
                                    for row in self.rows(lambda index: 20.0, count=360)], source)
        rows = [{**row, "yavg": B.pattern_yavg(source[index])} for index, row in enumerate(rows)]
        pts = [index / 60 for index in range(len(rows))]
        result = D.evaluate_content(rows, pts, 1.0, 7.0, policy)
        self.assertEqual(result["index_sequence"]["status"], "failed")
        self.assertTrue(any(v["kind"] == "source_drop_ratio"
                            for v in result["index_sequence"]["violations"]))

    def test_single_large_source_gap_is_rejected_even_under_total_drop_budget(self):
        policy = dict(D.CONTENT_POLICIES["animated-diagnostic-v2"])
        source = list(range(2001))
        source[601:] = [value + 7 for value in source[601:]]
        rows = B.with_index_fields([{key: value for key, value in row.items()
                                     if key not in ("index_top", "index_bottom")}
                                    for row in self.rows(lambda index: 20.0, count=2001)], source)
        rows = [{**row, "yavg": B.pattern_yavg(source[index])} for index, row in enumerate(rows)]
        pts = [index / 60 for index in range(len(rows))]
        result = D.evaluate_content(rows, pts, 1.0, 30.0, policy)
        index_result = result["index_sequence"]
        self.assertEqual(index_result["status"], "failed")
        self.assertLess(index_result["source_drop_ratio"], D.CADENCE_POLICY["maximum_drop_ratio"])
        self.assertGreater(index_result["maximum_source_gap_seconds"], D.CADENCE_POLICY["maximum_gap_seconds"])
        self.assertTrue(any(v["kind"] == "source_gap" for v in index_result["violations"]))

    def test_pure_duplicate_and_duplicate_then_single_skip_within_policy_pass(self):
        policy = dict(D.CONTENT_POLICIES["animated-diagnostic-v2"])
        source = []
        value = 0
        for row in range(361):
            source.append(value)
            if row != 60:
                value += 1
        rows = B.with_index_fields([{key: value for key, value in row.items()
                                     if key not in ("index_top", "index_bottom")}
                                    for row in self.rows(lambda index: 0.0, count=361)], source)
        rows = [{**row, "yavg": B.pattern_yavg(source[index]),
                 "ydif": 20.0 if index and source[index] != source[index - 1] else 0.0}
                for index, row in enumerate(rows)]
        pts = [index / 60 for index in range(len(rows))]
        result = D.evaluate_content(rows, pts, 1.0, 7.0, policy)
        self.assertEqual(result["status"], "passed", result)

    def test_separated_stale_content_is_a_capture_failure(self):
        value = self.with_content_rows(self.observation(), self.rows(lambda index: 20.0 if index % 2 else 0.1,
                                                                     fresh=lambda index: index % 2 == 1))
        result = CD.evaluate(value)
        self.assertEqual((result["verdict"], result["content_separation"]["status"]), ("FAIL", "separated"))
        self.assertFalse(result["criteria"]["content_gate"])

    def test_a_receipt_cannot_claim_separation_the_artifact_does_not_show(self):
        floor = D.CONTENT_POLICIES["animated-diagnostic-v2"]["distinct_noise_floor"]
        ambiguous = self.rows(lambda index: floor)
        # The receipt claims a clean pass computed from other rows; the hashed artifact is ambiguous.
        value = self.with_content_rows(self.observation(), ambiguous, claim=self.rows(lambda index: 20.0))
        result = CD.evaluate(value)
        self.assertEqual(result["verdict"], "calibration_ambiguous")
        self.assertFalse(result["criteria"]["content_gate"])
        # And a forged ambiguity cannot excuse a separated artifact.
        value = self.with_content_rows(self.observation(), self.rows(lambda index: 20.0 if index % 2 else 0.1,
                                                                     fresh=lambda index: index % 2 == 1),
                                       claim=ambiguous)
        self.assertEqual(CD.evaluate(value)["verdict"], "FAIL")
        # A receipt that loosens the separation factor fails the content gate.
        value = self.observation()
        value["recorder"]["cadence"]["content"]["policy"]["separation_factor"] = 1.0
        self.assertFalse(CD.evaluate(value)["criteria"]["content_gate"])

    def test_complete_observation_passes_every_criterion(self):
        result = CD.evaluate(self.observation())
        self.assertEqual(result["verdict"], "PASS", {k: v for k, v in result["criteria"].items() if not v})
        self.assertEqual(set(result["criteria"]), set(CD.CRITERIA))

    def test_each_criterion_fails_independently(self):
        cases = self.criterion_mutations()
        self.assertEqual(set(cases), set(CD.CRITERIA))
        for name, mutate in cases.items():
            with self.subTest(criterion=name):
                value = copy.deepcopy(self.observation()); mutate(value)
                result = CD.evaluate(value)
                self.assertFalse(result["criteria"][name])
                self.assertEqual(result["verdict"], "FAIL")
                self.assertIn(name, result["failing_criteria"])

    @staticmethod
    def criterion_mutations():
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
        return cases



SUPERVISOR_SCRIPT = r"""
import subprocess, sys, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from kpharness import capture_diagnostic as CD
base = Path(sys.argv[2]); mode = sys.argv[3]; budget = float(sys.argv[4])
def spawn(command, **kwargs):
    kwargs.pop('cwd', None)
    if mode.startswith('spawnwindow-'):
        child = subprocess.Popen([sys.executable, str(base / 'dummy_child.py'), sys.argv[1], command[-1], mode],
                                 **kwargs)
        (base / 'spawned-child-pid').write_text(str(child.pid))
        import os, signal
        os.kill(os.getpid(), getattr(signal, mode.split('-', 1)[1]))  # after fork, before Popen returns
        return child
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
import json, os, signal, subprocess, sys, time, types
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
        def blocked(pid):
            for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                if line.startswith('SigBlk:'):
                    return int(line.split()[1], 16)
        owned = json.loads((run / CD.OWNED_FILE).read_text())
        (run / 'sigblk.json').write_text(json.dumps(
            {'child': blocked(os.getpid()), **{item['role']: blocked(item['pid']) for item in owned}}))
        if mode in ('stubborn', 'survivor'):
            for number in CD.INTERRUPT_SIGNALS:
                signal.signal(number, signal.SIG_IGN)  # a child that never cleans up
        (run / 'child-ready').write_text('ready')
        if mode == 'crash':
            time.sleep(1.0); os._exit(3)  # dies without any ordered cleanup
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
sleep = (lambda seconds: time.sleep(min(seconds, .2))) if mode == 'quiet' else time.sleep
CD.run_child(config, lease_factory=Lease, popen=popen, discover=lambda lease, pids, **kwargs: window,
             verifier_factory=lambda lease, **kwargs: (lambda value: value), recorder_factory=Recorder,
             sleep=sleep, monotonic=time.monotonic, start_reader=start_of)
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

    def test_a_child_that_dies_without_cleanup_has_its_owned_processes_killed(self):
        code, result, run, owned, _ = self.run_supervisor("crash", 60, [])
        self.assertEqual(code, 1)
        self.assertEqual(result["child_returncode"], 3)
        self.assertFalse(result["cleanup_budget"]["exhausted"])
        self.assertEqual({item["role"] for item in result["owned_alive_after_child"]},
                         {"display:gamescope", "client"})
        self.assertIn("kill", result["cleanup_budget"])
        self.assertEqual(result["owned_survivors"], [])
        for identity in owned:
            self.assertFalse(CD.process_alive(identity["pid"], identity["start"]), identity)

    def test_a_survivor_after_the_budget_is_listed_exactly(self):
        code, result, run, owned, _ = self.run_supervisor("survivor", 2, [signal.SIGINT])
        self.assertEqual(code, 1)
        client = next(item for item in owned if item["role"] == "client")
        self.assertTrue(CD.process_alive(client["pid"], client["start"]))
        self.assertEqual(result["owned_survivors"], [client])
        self.assertEqual(result["cleanup_budget"]["kill"]["kill_failures"],
                         [{**client, "error": "kill refused or failed"}])

    def test_an_uninterrupted_run_is_never_cut_short_by_the_run_deadline(self):
        # The child's own normal cleanup runs both frame-scaled probes, so the run
        # bound must cover every pre-cleanup phase plus the full cleanup budget.
        pre_cleanup = float(sum(CD.CHILD_PRE_CLEANUP_COMPONENTS.values()))
        self.assertGreaterEqual(CD.CHILD_RUN_SECONDS, pre_cleanup + CD.CLEANUP_BUDGET_SECONDS)
        clock = [0.0]; sent = []
        finish = pre_cleanup + CD.CLEANUP_BUDGET_SECONDS - 1
        child = types.SimpleNamespace(pid=1, poll=lambda: 1 if clock[0] >= finish else None,
                                      send_signal=lambda number: sent.append(number))
        signals = CD._SupervisorSignals(); signals.child = child
        deps = types.SimpleNamespace(child_run_seconds=CD.CHILD_RUN_SECONDS, cleanup_budget=CD.CLEANUP_BUDGET_SECONDS)
        def sleep(seconds):
            clock[0] += 5.0
        wait = CD._wait_for_child(child, signals, deps, monotonic=lambda: clock[0], sleep=sleep)
        self.assertEqual(wait, {"returncode": 1, "budget_exhausted": False})
        self.assertEqual((signals.received, sent), ([], []))
        # An overrun past that bound is forwarded once, then given the cleanup budget.
        clock[0] = 0.0; finish = CD.CHILD_RUN_SECONDS + CD.CLEANUP_BUDGET_SECONDS + 100
        wait = CD._wait_for_child(child, signals, deps, monotonic=lambda: clock[0], sleep=sleep)
        self.assertEqual(wait, {"returncode": None, "budget_exhausted": True})
        self.assertEqual((signals.received, sent), (["run_deadline"], [signal.SIGINT]))

    def test_quiet_run_records_no_interrupt(self):
        code, result, run, owned, _ = self.run_supervisor("quiet", 60, [])
        self.assertEqual(code, 1)
        self.assertEqual(result["interrupts"], [])
        self.assertFalse(any("interrupted" in error for error in result["errors"]), result["errors"])
        self.assertFalse(result["cleanup_budget"]["exhausted"])
        self.assertEqual((run / "cleanup-steps.log").read_text().splitlines(), list(CD.CLEANUP_ORDER))
        self.assertEqual(json.loads((run / "diagnostic-run.json").read_text())["interrupts"], [])
        self.assertEqual(result["owned_survivors"], [])

    def run_spawn_window(self, name):
        supervisor = subprocess.Popen(
            [sys.executable, str(self.base / "supervisor.py"), str(ROOT / "scripts/harness"), str(self.base),
             "spawnwindow-" + name, "60"], start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = supervisor.communicate(timeout=120)[0].decode(errors="replace")
        run, = list((self.base / "runs").iterdir())
        child = int((self.base / "spawned-child-pid").read_text())
        return supervisor.returncode, json.loads((run / "diagnostic-result.json").read_text()), run, child, output

    def test_a_signal_between_fork_and_popen_return_still_supervises_the_child(self):
        # R11-C2 / R11-1 (p11b): the interrupt lands after the child exists but before
        # spawn returns. The supervisor blocks it, registers the child, then forwards it.
        for name in ("SIGINT", "SIGHUP", "SIGTERM"):
            with self.subTest(signal=name):
                shutil.rmtree(self.base / "runs"); (self.base / "runs").mkdir()
                code, result, run, child, output = self.run_spawn_window(name)
                self.assertEqual(code, 1, output)
                self.assertEqual(result["launches"], 1)
                self.assertEqual(result["interrupts"], [name])
                self.assertNotIn("interrupted before launch: " + name, result["errors"])
                self.assertEqual(result["child"]["pid"], child)
                self.assertIsNotNone(result["child_returncode"])
                self.assertFalse(Path(f"/proc/{child}").exists() and CD.process_alive(child, result["child"]["start"]))
                evidence = json.loads((run / "diagnostic-run.json").read_text())
                self.assertEqual(evidence["interrupts"], ["SIGINT"])  # exactly one forward
                self.assertIn("DiagnosticInterrupted", evidence["error"])
                self.assertEqual(result["owned_survivors"], [])

    def test_the_spawn_mask_never_reaches_the_child_or_its_owned_processes(self):
        code, result, run, owned, _ = self.run_supervisor("quiet", 60, [])
        masks = json.loads((run / "sigblk.json").read_text())
        interrupt_bits = sum(1 << (int(number) - 1) for number in CD.INTERRUPT_SIGNALS)
        self.assertEqual(set(masks), {"child", "display:gamescope", "client"})
        for role, mask in masks.items():
            self.assertEqual(mask & interrupt_bits, 0, role)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, []) & set(CD.INTERRUPT_SIGNALS), set())

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

    def trusted_root(self, name="repo"):
        """A temporary repository root standing in for the trusted one; the canonical lock is never touched."""
        root = self.base / name; (root / "tmp/harness-locks").mkdir(parents=True); (root / ".git").mkdir()
        lock = root / "tmp/harness-locks/live-game.lock"; lock.touch()
        return root, lock

    def test_production_check_admits_only_the_passed_descriptor_holding_the_trusted_lock(self):
        root, lock = self.trusted_root()
        held = os.open(lock, os.O_RDWR); self.addCleanup(os.close, held)
        fcntl.flock(held, fcntl.LOCK_EX)
        config = self.authority_fixture(); config["lock_fd"] = held
        self.assertEqual(CD.verify_child_authority(config, repository_root=root)["fd"], held)
        # Another descriptor of the same file, without the flock, is refused even though this process holds it.
        other = os.open(lock, os.O_RDONLY); self.addCleanup(os.close, other)
        config = self.authority_fixture(); config["lock_fd"] = other
        with self.assertRaisesRegex(CD.DiagnosticRefused, "lock"):
            CD.verify_child_authority(config, repository_root=root)
        fcntl.flock(held, fcntl.LOCK_UN)
        config = self.authority_fixture(); config["lock_fd"] = held
        with self.assertRaisesRegex(CD.DiagnosticRefused, "lock"):
            CD.verify_child_authority(config, repository_root=root)
        config = self.authority_fixture(); config["lock_fd"] = 987  # not open
        with self.assertRaisesRegex(CD.DiagnosticRefused, "lock"):
            CD.verify_child_authority(config, repository_root=root)

    def test_environment_redirected_private_lock_is_refused(self):
        # R11-C3 / R11-2 (p12): own pipe, own commitments, and KP_GAMESCOPE_REPO_ROOT
        # pointed at a private root whose lock this process holds.
        root, _ = self.trusted_root()
        fake, fake_lock = self.trusted_root("fake-repo")
        held = os.open(fake_lock, os.O_RDWR); self.addCleanup(os.close, held)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with mock.patch.dict(os.environ, {"KP_GAMESCOPE_REPO_ROOT": str(fake)}):
            config = self.authority_fixture(); config["lock_fd"] = held
            with self.assertRaisesRegex(CD.DiagnosticRefused, "canonical lock"):
                CD.verify_child_authority(config, repository_root=root)
            # The production root never reads the environment.
            self.assertEqual(G.trusted_repository_root(), ROOT)
            self.assertEqual(G.trusted_repository_root(CD.__file__), ROOT)

    def test_snapshot_child_takes_its_root_from_the_verified_manifest(self):
        snapshot = self.base / "snapshot-root"
        S.create_snapshot(ROOT / "scripts/harness", snapshot, entries=CD.SNAPSHOT_ENTRIES)
        module = snapshot / "runtime" / "kpharness" / "capture_diagnostic.py"
        fake, _ = self.trusted_root("fake-env-root")
        with mock.patch.dict(os.environ, {"KP_GAMESCOPE_REPO_ROOT": str(fake)}):
            self.assertEqual(G.trusted_repository_root(module), ROOT)
        manifest = snapshot / S.MANIFEST
        value = json.loads(manifest.read_text()); value["repository_root"] = str(fake)
        manifest.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        with self.assertRaises((RuntimeError, ValueError)):
            G.trusted_repository_root(module)
        manifest.unlink()
        with self.assertRaises((RuntimeError, ValueError)):
            G.trusted_repository_root(module)

    def test_admitted_child_pins_the_trusted_root_for_every_later_lock_check(self):
        run = self.base / "pinned"; run.mkdir()
        config = run / "diagnostic-config.json"
        config.write_text(json.dumps(CD.child_config(run, ffmpeg="f", ffprobe="p", lock_fd=77)))
        seen = {}
        def fake_run_child(value, **kwargs):
            seen["root"] = os.environ.get("KP_GAMESCOPE_REPO_ROOT")
            return {"error": None, "cleanup": {"status": "passed"}}
        with mock.patch.dict(os.environ, {"KP_GAMESCOPE_REPO_ROOT": "/elsewhere"}), \
                mock.patch.object(CD, "verify_child_authority", return_value={"fd": 77}), \
                mock.patch.object(CD, "run_child", fake_run_child):
            self.assertEqual(CD.main(["--child", str(config)]), 0)
        self.assertEqual(seen["root"], str(ROOT))

    def test_child_entry_refuses_before_any_lease_without_the_token(self):
        run = self.base / "manual-child"; run.mkdir()
        config = run / "diagnostic-config.json"
        config.write_text(json.dumps(CD.child_config(run, ffmpeg="f", ffprobe="p", lock_fd=77)))
        from kpharness import gamescope_xwayland as G
        stdout = io.StringIO()
        with mock.patch.object(G, "GamescopeXwaylandLease", side_effect=AssertionError("lease")), \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(CD.main(["--child", str(config)]), 2)
        self.assertIn("refusing --child", stdout.getvalue())
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

    def test_unreadable_exe_alone_is_evidence_not_a_refusal(self):
        # Non-dumpable processes of this user hide /proc/PID/exe; comm and argv still classify them.
        write_proc(self.proc, 601, "kwin_wayland", ["/usr/bin/kwin_wayland"])
        (self.proc / "601" / "exe").mkdir()  # readlink fails with an error other than ENOENT
        rows = CD.process_inventory(self.proc)
        row, = rows
        self.assertNotIn("unreadable", row)
        self.assertIn("exe_unreadable", row)
        run = self.base / "run-exe"; run.mkdir()
        self.assertFalse(CD.preflight(self.proc, run, self_pid=1)["refused"])

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


class PreflightExeIdentityTests(DiagnosticCase):
    """R11-3 adversarial: a renamed copy of the configured FFmpeg/FFprobe is found by content."""

    def tools(self):
        return [{"role": "ffmpeg", **CD.native_elf_identity(str(self.tool))}]

    def exe_row(self, pid, comm, target):
        write_proc(self.proc, pid, comm, [f"/tmp/{comm}"])
        os.symlink(target, self.proc / str(pid) / "exe")

    def test_renamed_copy_or_hard_link_of_a_configured_tool_is_detected_by_exe_sha256(self):
        copy_path = self.base / "enc"; shutil.copyfile(self.tool, copy_path); copy_path.chmod(0o755)
        same_size = self.base / "other"
        same_size.write_bytes(b"\x7fELF" + b"\0" * (self.tool.stat().st_size - 4))
        link = self.base / "linked"
        try:
            os.link(self.tool, link)
        except OSError:
            shutil.copyfile(self.tool, link)
        self.exe_row(701, "enc", copy_path)
        self.exe_row(702, "other", same_size)
        self.exe_row(703, "linked", link)
        self.exe_row(704, "gone", self.base / "missing")
        rows = CD.process_inventory(self.proc, tools=self.tools())
        by_pid = {row["pid"]: row for row in rows}
        self.assertEqual(by_pid[701]["exe_tool_match"], "ffmpeg")
        self.assertEqual(by_pid[703]["exe_tool_match"], "ffmpeg")
        self.assertNotIn("exe_tool_match", by_pid[702])
        self.assertNotIn("exe_tool_match", by_pid[704])
        self.assertEqual(sorted(row["pid"] for row in CD.forbidden_processes(rows)), [701, 703])
        # Without configured identities the same rows are names only, as before.
        self.assertEqual(CD.forbidden_processes(CD.process_inventory(self.proc)), [])

    def test_exe_hashing_is_size_filtered_and_cached_by_inode(self):
        copy_path = self.base / "enc"; shutil.copyfile(self.tool, copy_path)
        small = self.base / "small"; small.write_bytes(b"\x7fELF tiny")
        for pid in (801, 802, 803):
            self.exe_row(pid, f"enc{pid}", copy_path)
        self.exe_row(804, "small", small)
        with mock.patch.object(CD, "_exe_sha256", wraps=CD._exe_sha256) as digest:
            rows = CD.process_inventory(self.proc, tools=self.tools())
        self.assertEqual(digest.call_count, 1)
        self.assertEqual(sorted(row["pid"] for row in CD.forbidden_processes(rows)), [801, 802, 803])

    def test_supervisor_refuses_a_renamed_tool_copy_before_any_launch(self):
        copy_path = self.base / "enc"; shutil.copyfile(self.tool, copy_path)
        self.exe_row(901, "enc", copy_path)
        deps = self.deps()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(CD.supervise(self.options(), deps), 1)
        deps.spawn_child.assert_not_called()
        run, = list(self.runs.iterdir())
        evidence = json.loads((run / "preflight.json").read_text())
        self.assertEqual([(row["pid"], row["exe_tool_match"]) for row in evidence["forbidden"]], [(901, "ffmpeg")])


LOADER = next((path for path in ("/lib64/ld-linux-x86-64.so.2", "/usr/lib64/ld-linux-x86-64.so.2",
                                  "/lib/ld-linux-aarch64.so.1") if os.path.exists(path)), None)


class LoaderLaunchTests(DiagnosticCase):
    """R12-1 / R12C-m4: a configured tool started through the dynamic loader is still found."""

    def loader_row(self, pid, argv, *, comm="ld-linux-x86-64", exe=None, cwd=None):
        write_proc(self.proc, pid, comm, argv)
        if exe is not None:
            os.symlink(exe, self.proc / str(pid) / "exe")
        if cwd is not None:
            os.symlink(cwd, self.proc / str(pid) / "cwd")

    def test_loader_launch_is_detected_by_the_program_argument_name(self):
        self.loader_row(1001, ["/lib64/ld-linux-x86-64.so.2", "/usr/bin/ffmpeg", "-i", "x"])
        # Homebrew's interpreter is named ld.so; options with a value are skipped.
        self.loader_row(1002, ["/home/linuxbrew/.linuxbrew/lib/ld.so", "--library-path", "/opt/lib",
                               "--argv0", "enc", "/opt/x/ffprobe", "-v"], comm="ld.so")
        # exec -a: argv[0] lies, but the loader is still the executable.
        self.loader_row(1003, ["innocent", "--inhibit-cache", "/usr/bin/ffmpeg"], comm="innocent",
                        exe="/usr/lib64/ld-linux-x86-64.so.2")
        # A 15-character comm of a longer loader name.
        self.loader_row(1004, ["/lib/ld-linux-aarch64.so.1", "/usr/local/bin/ffprobe"], comm="ld-linux-aarch6")
        # Not targets: an option value naming an ffmpeg directory, and an editor on a file called ld.so.
        self.loader_row(1005, ["/lib64/ld-linux-x86-64.so.2", "--library-path", "/opt/ffmpeg", "/usr/bin/true"])
        write_proc(self.proc, 1006, "vim", ["vim", "ld.so", "ffmpeg.txt"])
        rows = CD.process_inventory(self.proc)
        by_pid = {row["pid"]: row for row in rows}
        self.assertEqual(by_pid[1002]["loader_program"], "/opt/x/ffprobe")
        self.assertEqual(by_pid[1005]["loader_program"], "/usr/bin/true")
        self.assertNotIn("loader_program", by_pid[1006])
        self.assertEqual(sorted(row["pid"] for row in CD.forbidden_processes(rows)), [1001, 1002, 1003, 1004])

    def test_loader_launch_of_a_renamed_copy_is_detected_by_content(self):
        tools = [{"role": "ffprobe", **CD.native_elf_identity(str(self.tool))}]
        work = self.base / "work"; work.mkdir()
        shutil.copyfile(self.tool, work / "enc")
        self.loader_row(1101, ["/lib64/ld-linux-x86-64.so.2", "--preload", "/x/ffmpeg.so", "enc", "-q"],
                        exe=LOADER or "/lib64/ld-linux-x86-64.so.2", cwd=work)
        self.loader_row(1102, ["/lib64/ld-linux-x86-64.so.2", str(self.tool)])
        self.loader_row(1103, ["/lib64/ld-linux-x86-64.so.2", str(work / "absent")])
        rows = CD.process_inventory(self.proc, tools=tools)
        by_pid = {row["pid"]: row for row in rows}
        self.assertEqual((by_pid[1101]["loader_tool_match"], by_pid[1101]["loader_match_by"]), ("ffprobe", "sha256"))
        self.assertEqual((by_pid[1102]["loader_tool_match"], by_pid[1102]["loader_match_by"]), ("ffprobe", "inode"))
        self.assertNotIn("loader_tool_match", by_pid[1103])
        self.assertIn("loader_program_unreadable", by_pid[1103])
        self.assertEqual(sorted(row["pid"] for row in CD.forbidden_processes(rows)), [1101, 1102])

    @unittest.skipUnless(LOADER, "no x86-64 or aarch64 dynamic loader on this host")
    def test_a_real_loader_invocation_of_a_renamed_tool_copy_is_refused(self):
        # A dummy tree: /bin/sleep stands in for the configured tool; nothing else is signalled.
        tool = self.base / "toolbin"; shutil.copy2("/bin/sleep", tool)
        renamed = self.base / "enc"; shutil.copy2(tool, renamed)
        tools = [{"role": "ffmpeg", **CD.native_elf_identity(str(tool))}]
        child = subprocess.Popen([LOADER, str(renamed), "30"])
        def stop():
            child.terminate(); child.wait(10)
        self.addCleanup(stop)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                if Path(f"/proc/{child.pid}/cmdline").read_bytes().startswith(LOADER.encode()):
                    break
            except OSError:
                pass
            time.sleep(.02)
        rows = {row["pid"]: row for row in CD.process_inventory(Path("/proc"), tools=tools)}
        row = rows[child.pid]
        self.assertTrue(row["comm"].startswith("ld-"))
        self.assertEqual(row["loader_tool_match"], "ffmpeg")
        blocked = CD.forbidden_processes(list(rows.values()), exclude=CD._launch_chain(Path("/proc"), os.getpid()))
        self.assertIn(child.pid, [item["pid"] for item in blocked])


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
