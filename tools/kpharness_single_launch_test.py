#!/usr/bin/env python3
"""Single-launch mode for GameSession boot: one launch per authorized attempt.

Launch and connect are stubbed; nothing here starts Wine, Xvfb or the game.
Run: python3 tools/kpharness_single_launch_test.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "harness"))

from kpharness import session as S  # noqa: E402
from kpharness.session import BootFailure, GameSession  # noqa: E402

ENV = "KP_MAX_BOOT_ATTEMPTS"


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k != ENV}
    env.update(extra)
    return mock.patch.dict(os.environ, env, clear=True)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kp_single_launch_"))
        self.settle = S.BOOT_RETRY_SETTLE
        S.BOOT_RETRY_SETTLE = 0.0

    def tearDown(self):
        S.BOOT_RETRY_SETTLE = self.settle
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _session(self, outcomes, max_boot_attempts=None):
        """A GameSession with launch/connect stubbed. `max_boot_attempts`
        None leaves resolution to the environment, as __new__-built sessions
        in the offline suite do."""
        s = GameSession.__new__(GameSession)
        s.launcher = None
        s.launches = 0
        s.kills = 0
        s.log = lambda _msg: None
        s.run_dir = self.tmp / "run"
        if max_boot_attempts is not None:
            s.max_boot_attempts = max_boot_attempts
            s.max_boot_attempts_source = "kwarg"

        def launch():
            s.launches += 1

        def connect():
            outcome = outcomes[s.launches - 1]
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        s.launch = launch
        s.connect = connect
        s._kill_game = lambda: setattr(s, "kills", s.kills + 1)
        return s

    def _evidence(self):
        return json.loads((self.tmp / "run" / "boot-attempts.json").read_text())


class TestSingleLaunch(_Base):
    def test_one_attempt_crash_launches_once_and_does_not_relaunch(self):
        crash = BootFailure("crash", "swkotor.exe is not running")
        s = self._session([crash, "channel"], max_boot_attempts=1)
        with self.assertRaises(BootFailure) as caught:
            s._launch_and_connect()
        self.assertIs(caught.exception, crash)
        self.assertEqual(s.launches, 1)
        self.assertEqual(s.kills, 0)
        self.assertEqual(caught.exception.launch_count, 1)
        self.assertEqual(caught.exception.max_boot_attempts, 1)
        self.assertEqual(Path(caught.exception.evidence_path),
                         self.tmp / "run" / "boot-attempts.json")

    def test_one_attempt_boot_timeout_launches_once(self):
        timeout = BootFailure("boot timeout", "no status reply in 300s")
        s = self._session([timeout, "channel"], max_boot_attempts=1)
        with self.assertRaises(BootFailure) as caught:
            s._launch_and_connect()
        self.assertEqual(caught.exception.reason, "boot timeout")
        self.assertEqual(s.launches, 1)
        self.assertEqual(s.kills, 0)

    def test_env_one_forces_single_launch(self):
        with _clean_env(**{ENV: "1"}):
            s = self._session([BootFailure("crash", "x"), "channel"])
            with self.assertRaises(BootFailure):
                s._launch_and_connect()
        self.assertEqual(s.launches, 1)
        self.assertEqual(self._evidence()["max_boot_attempts_source"], "env")

    def test_one_attempt_success_records_one_launch(self):
        s = self._session(["channel"], max_boot_attempts=1)
        self.assertEqual(s._launch_and_connect(), "channel")
        ev = self._evidence()
        self.assertEqual(ev["launch_count"], 1)
        self.assertEqual(ev["outcome"], "channel")
        self.assertEqual(ev["attempts"][0]["outcome"], "channel")

    def test_non_bootfailure_from_launch_is_still_counted(self):
        s = self._session([], max_boot_attempts=1)

        def launch():
            s.launches += 1
            raise OSError("exec failed")

        s.launch = launch
        with self.assertRaises(OSError):
            s._launch_and_connect()
        ev = self._evidence()
        self.assertEqual(ev["launch_count"], 1)
        self.assertEqual(ev["attempts"][0]["reason"], "OSError")


class TestDefaultAndEvidence(_Base):
    def test_default_keeps_five_attempts(self):
        self.assertEqual(S.BOOT_ATTEMPTS, 5)
        failures = [BootFailure("boot timeout", f"attempt {i}") for i in range(5)]
        with _clean_env():
            s = self._session(failures)
            with self.assertRaises(BootFailure) as caught:
                s._launch_and_connect()
        self.assertIs(caught.exception, failures[-1])
        self.assertEqual(s.launches, 5)
        self.assertEqual(s.kills, 4)
        ev = self._evidence()
        self.assertEqual(ev["max_boot_attempts"], 5)
        self.assertEqual(ev["max_boot_attempts_source"], "default")

    def test_every_attempt_is_recorded_with_count_and_reasons(self):
        with _clean_env():
            s = self._session([BootFailure("crash", "first"),
                               BootFailure("boot timeout", "second"), "channel"])
            self.assertEqual(s._launch_and_connect(), "channel")
        ev = self._evidence()
        self.assertEqual(ev["launch_count"], 3)
        self.assertEqual(ev["outcome"], "channel")
        self.assertEqual([a["attempt"] for a in ev["attempts"]], [1, 2, 3])
        self.assertEqual([a["reason"] for a in ev["attempts"]], ["crash", "boot timeout", None])
        self.assertEqual([a["detail"] for a in ev["attempts"]], ["first", "second", None])
        self.assertEqual(s.boot_attempts, ev["attempts"])

    def test_failed_evidence_names_final_failure(self):
        s = self._session([BootFailure("crash", "dead")], max_boot_attempts=1)
        with self.assertRaises(BootFailure):
            s._launch_and_connect()
        ev = self._evidence()
        self.assertEqual(ev["outcome"], "failed")
        self.assertEqual(ev["launch_count"], 1)
        self.assertEqual(ev["attempts"], [{"attempt": 1, "outcome": "failed",
                                           "reason": "crash", "detail": "dead",
                                           "started": ev["attempts"][0]["started"],
                                           "ended": ev["attempts"][0]["ended"]}])

    def test_unwritable_receipt_does_not_mask_boot_failure(self):
        crash = BootFailure("crash", "dead")
        s = self._session([crash], max_boot_attempts=1)
        blocker = self.tmp / "not_a_dir"
        blocker.write_text("x")
        s.run_dir = blocker  # mkdir/write under a regular file raises OSError
        with self.assertRaises(BootFailure) as caught:
            s._launch_and_connect()
        self.assertIs(caught.exception, crash)
        self.assertIsNone(caught.exception.evidence_path)
        self.assertEqual(caught.exception.launch_count, 1)
        self.assertEqual(s.launches, 1)

    def test_refusal_is_still_not_retried_under_default(self):
        with _clean_env():
            s = self._session([BootFailure("refusal", "refusing to install"), "channel"])
            with self.assertRaises(BootFailure):
                s._launch_and_connect()
        self.assertEqual(s.launches, 1)


class TestInvalidValues(_Base):
    BAD = ["0", "6", "-1", "", " ", "one", "1.0", "2.5", "0x2", "5 "]

    def test_resolver_accepts_one_to_five(self):
        for n in range(1, 6):
            with _clean_env(**{ENV: str(n)}):
                self.assertEqual(S.resolve_max_boot_attempts(), (n, "env"))
            self.assertEqual(S.resolve_max_boot_attempts(n), (n, "kwarg"))
        with _clean_env():
            self.assertEqual(S.resolve_max_boot_attempts(), (5, "default"))

    def test_invalid_env_is_refused(self):
        for bad in self.BAD:
            with self.subTest(value=bad), _clean_env(**{ENV: bad}):
                with self.assertRaises(S.InvalidBootAttempts):
                    S.resolve_max_boot_attempts()

    def test_invalid_kwarg_is_refused(self):
        for bad in (0, 6, -1, True, False, 1.0, "1", "abc"):
            with self.subTest(value=bad), _clean_env():
                with self.assertRaises(S.InvalidBootAttempts):
                    S.resolve_max_boot_attempts(bad)

    def test_invalid_env_refuses_before_any_launch(self):
        with _clean_env(**{ENV: "9"}):
            s = self._session(["channel"])
            with self.assertRaises(S.InvalidBootAttempts):
                s._launch_and_connect()
        self.assertEqual(s.launches, 0)

    def test_constructor_refuses_invalid_env(self):
        with _clean_env(**{ENV: "0"}):
            with self.assertRaises(S.InvalidBootAttempts):
                GameSession("k1", staged=str(self.tmp / "stage"), log=lambda _m: None)

    def test_constructor_refuses_invalid_kwarg(self):
        with _clean_env():
            with self.assertRaises(S.InvalidBootAttempts):
                GameSession("k1", staged=str(self.tmp / "stage"), log=lambda _m: None,
                            max_boot_attempts=6)

    def test_constructor_kwarg_wins_over_env(self):
        with _clean_env(**{ENV: "3"}):
            s = GameSession("k1", staged=str(self.tmp / "stage"), log=lambda _m: None,
                            max_boot_attempts=1)
        self.assertEqual((s.max_boot_attempts, s.max_boot_attempts_source), (1, "kwarg"))

    def test_invalid_env_is_refused_by_value_error_catchers(self):
        self.assertTrue(issubclass(S.InvalidBootAttempts, ValueError))



class TestCreativeRefusesBeforeClaims(_Base):
    """run_creative validates the boot budget before lock, run dir, ledger or stage claims."""

    def _refuse(self, backend, argv_extra=(), env=None):
        from kpharness import creative as C
        options = C.parser().parse_args(["--backend", backend, "--script", "unused.lua",
                                         "--route", "unused", *argv_extra])
        options.cleanup_commitment_log = str(self.tmp / "commit.log")
        session_type, recorder_type, claim = mock.Mock(), mock.Mock(), mock.Mock()
        adapter = mock.Mock(return_value=(session_type, recorder_type, claim, mock.Mock(), mock.Mock()))
        with _clean_env(**(env or {})), \
             mock.patch.object(C.discover, "repo_root", return_value=ROOT), \
             mock.patch.object(C.discover, "data_dir") as data, \
             mock.patch.object(C, "script_inputs") as scripts, \
             mock.patch.object(C, "find_scenario") as route, \
             mock.patch.object(C, "live_lock") as lock, \
             mock.patch.object(C.Path, "mkdir") as mkdir, \
             mock.patch("kpharness.creative_accept.validate_commitment_log") as commit_check, \
             mock.patch("kpharness.creative_accept.initialize_cleanup_ledger") as ledger:
            with self.assertRaises(S.InvalidBootAttempts):
                C.run_creative(options, adapter_factory=adapter)
            for called in (data, scripts, route, lock, mkdir, commit_check, ledger,
                           session_type, recorder_type, claim):
                called.assert_not_called()

    def test_invalid_env_refused_before_any_claim(self):
        for backend in ("linux-wine-k1", "linux-wine-k1-gamescope"):
            for bad in ("0", "6", "", "one"):
                with self.subTest(backend=backend, value=bad):
                    self._refuse(backend, env={ENV: bad})

    def test_invalid_env_refused_even_with_valid_dev_flag(self):
        self._refuse("linux-wine-k1", ["--dev-max-boot-attempts", "2"], env={ENV: "9"})

    def test_invalid_dev_flag_refused_before_any_claim(self):
        for bad in ("0", "6", "-1"):
            with self.subTest(value=bad):
                self._refuse("linux-wine-k1-gamescope", ["--dev-max-boot-attempts", bad])

    def test_resolved_budget(self):
        from kpharness import creative as C
        cases = [({}, None, (1, "default_single")), ({ENV: "1"}, None, (1, "default_single")),
                 ({ENV: "4"}, None, (1, "default_single")), ({}, 3, (3, "dev_override")),
                 ({ENV: "1"}, 2, (2, "dev_override"))]
        for env, dev, expected in cases:
            with self.subTest(env=env, dev=dev), _clean_env(**env):
                budget = C.boot_budget(dev)
                self.assertEqual((budget["max_boot_attempts"], budget["budget_source"]), expected)
                self.assertEqual(budget["env"], env.get(ENV))

    def test_boot_evidence_judgement(self):
        from kpharness import creative as C
        single = {"max_boot_attempts": 1, "budget_source": "default_single", "env": None}
        run = self.tmp / "run"; run.mkdir()
        path = run / "boot-attempts.json"
        cases = [({"max_boot_attempts": 1, "launch_count": 1}, single, True),
                 ({"max_boot_attempts": 1, "launch_count": 2}, single, False),
                 ({"max_boot_attempts": 1, "launch_count": True}, single, False),
                 ({"max_boot_attempts": 5, "launch_count": 1}, single, False),
                 ({"max_boot_attempts": 1, "launch_count": 1},
                  {**single, "budget_source": "dev_override"}, False),
                 ([1, 1], single, False), ("not json", single, False), (None, single, False)]
        for record, budget, eligible in cases:
            with self.subTest(record=record, budget=budget["budget_source"]):
                if path.exists():
                    path.unlink()
                if record == "not json":
                    path.write_text("{")
                elif record is not None:
                    path.write_text(json.dumps(record))
                result = C.boot_evidence(run, budget)
                self.assertIs(result["acceptance_eligible"], eligible)
                self.assertEqual(result["refusal"] is None, eligible)


class TestCliBootBudget(_Base):
    """kpharness boot/run: --max-boot-attempts, and a bad value is one line, nonzero, no launch."""

    def _args(self, cmd, *extra):
        from kpharness import cli
        argv = [cmd] + (["unused-scenario"] if cmd == "run" else []) + list(extra)
        return cli, cli.build_parser().parse_args(argv)

    def _call(self, cmd, *extra, env=None, session=None):
        import contextlib, io
        cli, a = self._args(cmd, *extra)
        err = io.StringIO()
        with _clean_env(**(env or {})), \
             mock.patch.object(cli, "GameSession", session or mock.Mock()) as gs, \
             mock.patch.object(cli.S, "find_scenario") as find, \
             mock.patch.object(cli.S.Scenario, "load") as load, \
             contextlib.redirect_stderr(err):
            load.return_value = mock.Mock(target="k1", resources={})
            rc = a.fn(a)
        return rc, gs, err.getvalue(), find

    def test_flag_is_parsed_on_boot_and_run(self):
        for cmd in ("boot", "run"):
            _, a = self._args(cmd, "--max-boot-attempts", "1")
            self.assertEqual(a.max_boot_attempts, 1)
            _, a = self._args(cmd)
            self.assertIsNone(a.max_boot_attempts)

    def test_invalid_env_is_one_line_nonzero_without_session(self):
        for cmd in ("boot", "run"):
            for extra in ((), ("--max-boot-attempts", "1")):
                with self.subTest(cmd=cmd, extra=extra):
                    rc, gs, err, find = self._call(cmd, *extra, env={ENV: "0"})
                    self.assertEqual(rc, 3)
                    gs.assert_not_called(); find.assert_not_called()
                    self.assertEqual(len(err.strip().splitlines()), 1, err)
                    self.assertIn(ENV, err)

    def test_invalid_flag_is_one_line_nonzero_without_session(self):
        for cmd in ("boot", "run"):
            for bad in ("0", "6"):
                with self.subTest(cmd=cmd, value=bad):
                    rc, gs, err, _ = self._call(cmd, "--max-boot-attempts", bad)
                    self.assertEqual(rc, 3)
                    gs.assert_not_called()
                    self.assertEqual(len(err.strip().splitlines()), 1, err)

    def test_flag_reaches_session_and_failure_prints_evidence(self):
        failure = BootFailure("crash", "wine: Unhandled")
        failure.launch_count, failure.max_boot_attempts = 1, 1
        failure.evidence_path = str(self.tmp / "boot-attempts.json")
        session = mock.Mock()
        session.return_value.boot.side_effect = failure
        for cmd in ("boot", "run"):
            with self.subTest(cmd=cmd):
                session.reset_mock()
                rc, gs, err, _ = self._call(cmd, "--max-boot-attempts", "1", session=session)
                self.assertEqual(rc, 2)
                self.assertEqual(gs.call_args.kwargs["max_boot_attempts"], 1)
                self.assertIn("launch_count=1", err)
                self.assertIn("max_boot_attempts=1", err)
                self.assertIn("boot-attempts.json", err)

    def test_constructor_refusal_is_also_one_line(self):
        # Second guard: if the environment changes between checks, the
        # constructor's own refusal is caught inside the command, not a traceback.
        session = mock.Mock(side_effect=S.InvalidBootAttempts("KP_MAX_BOOT_ATTEMPTS must be in 1..5, got 0"))
        for cmd in ("boot", "run"):
            with self.subTest(cmd=cmd):
                rc, gs, err, _ = self._call(cmd, session=session)
                self.assertEqual(rc, 3)
                self.assertEqual(len(err.strip().splitlines()), 1, err)
                gs.return_value.boot.assert_not_called()

    def test_no_flag_leaves_env_to_the_session(self):
        session = mock.Mock()
        session.return_value.boot.side_effect = BootFailure("crash")
        rc, gs, _, _ = self._call("boot", env={ENV: "1"}, session=session)
        self.assertEqual(rc, 2)
        self.assertIsNone(gs.call_args.kwargs["max_boot_attempts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
