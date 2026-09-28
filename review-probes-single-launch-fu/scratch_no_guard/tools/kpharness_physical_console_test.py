#!/usr/bin/env python3
"""Host-only proof matrix for the supported physical F12 console boundary.

No game, Wine, X server, or Lua evaluator is involved.  The fake protocol has
only status/outcome/output; a direct wire submit is structurally unavailable.
"""
from __future__ import annotations

import base64
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "harness"))

from kpharness.physical_console import (PhysicalConsoleDriver,  # noqa: E402
                                        PhysicalConsoleFailure)
from kpharness.owned_x11 import OwnedX11Input, UnsupportedOwnedInput  # noqa: E402
from kpharness.console_steps import (ConsoleStepError, _evidence_strings,  # noqa: E402
                                     _expect_values, execute_console_step)
from kpharness.session import GameSession  # noqa: E402


def byte(text: str) -> dict:
    data = text.encode()
    return {"encoding": "base64", "data": base64.b64encode(data).decode(),
            "byte_length": str(len(data))}


@dataclass
class FakeClock:
    now: float = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ScriptedConsoleProtocolPort:
    """A narrow protocol port whose transcript exposes every observation."""

    def __init__(self, case: str, *, opened: bool = False):
        self.case, self.opened, self.entered = case, opened, 0
        self.calls: list[tuple] = []

    def _status(self, runtime="A", session="7", submitted="40", status="Found"):
        return {"protocol": "kp.console.v1", "runtime": runtime, "status": status,
                "session": session, "submitted": submitted, "completed": "999",
                "last_line": "100", "open": self.opened, "input_calls": "0"}

    def status(self, runtime=None):
        self.calls.append(("status", runtime))
        if self.entered:
            if self.case == "stale_runtime":
                return self._status(status="StaleRuntime")
            if self.case == "stale_session":
                return self._status(session="8", submitted="41")
            if self.case == "duplicate":
                return self._status(submitted="42")
            if self.case == "regression":
                return self._status(submitted="39")
            if self.case == "malformed_status":
                response = self._status(submitted="41")
                response.pop("session")
                return response
            if self.case == "submission_timeout":
                return self._status(submitted="40")
            return self._status(submitted="41")
        return self._status()

    def outcome(self, runtime, session, request):
        self.calls.append(("outcome", runtime, session, request))
        common = {"protocol": "kp.console.v1", "runtime": "A"}
        if self.case == "expired":
            return {**common, "status": "Expired"}
        if self.case == "unavailable":
            return {**common, "status": "Unavailable"}
        if self.case == "stale_outcome":
            return {**common, "status": "StaleSession"}
        if self.case == "malformed_outcome":
            return {**common, "status": "Found", "outcome": {"session": "7", "state": "Succeeded"}}
        state = "Succeeded"
        if self.case == "failed":
            state = "Failed"
        elif self.case == "cancelled":
            state = "Cancelled"
        elif self.case == "outcome_timeout":
            state = "Pending"
        outcome = {"session": "7", "request": "41", "state": state,
                   "values": [{"type": "Nil"}, {"type": "Boolean", "value": False},
                              {"type": "Number", "kind": "Finite", "value": 42}],
                   "return_count": "3", "returns_truncated": False,
                   "error": {"code": "lua_runtime", "text": byte("intentional"), "truncated": False},
                   "first_line": "101", "last_line": "102"}
        return {**common, "status": "Found", "outcome": outcome}

    def output(self, runtime, session, after_sequence):
        self.calls.append(("output", runtime, session, after_sequence))
        common = {"protocol": "kp.console.v1", "runtime": "A", "status": "Found",
                  "session": "7", "last_sequence": "102", "dropped_lines": "0",
                  "dropped_through": "101" if self.case == "dropped" else "0"}
        if self.case == "missing":
            lines = []
        elif self.case == "input_only":
            lines = [self._line("7", "41", "input", "input: return 21*2")]
        elif self.case == "result_only":
            lines = [self._line("7", "41", "result", "number: 42")]
        elif self.case == "foreign":
            lines = [self._line("8", "41", "input", "input: return 21*2"),
                     self._line("7", "42", "result", "number: 42")]
        else:
            lines = [self._line("7", "41", "input", "input: return 21*2"),
                     self._line("7", "41", "result", "number: 42")]
        response = {**common, "lines": lines}
        if self.case == "malformed_output":
            response["lines"][0]["kind"] = {"encoding": "base64", "data": "aW5wdXQ="}
        return response

    @staticmethod
    def _line(session: str, request: str, kind: str, text: str) -> dict:
        return {"session": session, "request": request, "sequence": "101",
                "kind": byte(kind), "text": byte(text)}


class ScriptedOwnedInputPort:
    def __init__(self, protocol: ScriptedConsoleProtocolPort):
        self.protocol = protocol
        self.calls: list[tuple] = []

    def focus_owned_game_window(self) -> None:
        self.calls.append(("focus",))

    def press_f12(self) -> None:
        self.calls.append(("F12",))
        self.protocol.opened = True

    def select_all(self) -> None:
        self.calls.append(("select_all",))

    def type_text(self, source: str) -> None:
        self.calls.append(("type", source))

    def press_enter(self) -> None:
        self.calls.append(("Enter",))
        self.protocol.entered += 1


class FailingOwnedInputPort(ScriptedOwnedInputPort):
    def __init__(self, protocol, fail_at):
        super().__init__(protocol)
        self.fail_at = fail_at

    def _fail(self, name):
        if self.fail_at == name:
            raise RuntimeError(name + " failed")

    def focus_owned_game_window(self):
        self._fail("focus")
        super().focus_owned_game_window()

    def press_f12(self):
        self._fail("F12")
        super().press_f12()

    def select_all(self):
        self._fail("select_all")
        super().select_all()

    def type_text(self, source):
        self._fail("type")
        super().type_text(source)

    def press_enter(self):
        self._fail("Enter")
        super().press_enter()


class LargeIdentifierProtocol(ScriptedConsoleProtocolPort):
    def __init__(self, submitted):
        super().__init__("clean", opened=True)
        self.base = submitted
        self.expected = str(int(submitted) + 1)

    def _status(self, runtime="A", session="7", submitted=None, status="Found"):
        return super()._status(runtime=runtime, session="18446744073709551615",
                               submitted=submitted or self.base, status=status) | {"last_line": "9007199254740993"}

    def status(self, runtime=None):
        self.calls.append(("status", runtime))
        return self._status(submitted=self.expected if self.entered else self.base)

    def outcome(self, runtime, session, request):
        reply = super().outcome(runtime, session, request)
        reply["outcome"]["session"] = "18446744073709551615"
        reply["outcome"]["request"] = self.expected
        return reply

    def output(self, runtime, session, after_sequence):
        reply = super().output(runtime, session, after_sequence)
        reply["session"] = "18446744073709551615"
        for row in reply["lines"]:
            row["session"] = "18446744073709551615"
            row["request"] = self.expected
        return reply


class TickChannel:
    def __init__(self, values):
        self.values = iter(values)
        self.last_state = None
    def state(self):
        self.last_state = next(self.values)
        return self.last_state


class NoVerdict:
    def check(self, state):
        return None


class ScenarioChannel:
    """Adapts the read-only scripted port to the production channel shape."""

    def __init__(self, protocol):
        self.protocol = protocol

    def request(self, service, *, protocol, op, **fields):
        if service != "devtools" or protocol != "kp.console.v1":
            raise AssertionError("unexpected console channel request")
        return getattr(self.protocol, op)(**fields)


class PhysicalConsoleTests(unittest.TestCase):
    def drive(self, case="clean", *, opened=False, timeout=0.3):
        protocol = ScriptedConsoleProtocolPort(case, opened=opened)
        input_port = ScriptedOwnedInputPort(protocol)
        clock = FakeClock()
        driver = PhysicalConsoleDriver(protocol, input_port, clock)
        return driver, protocol, input_port

    def assert_failure(self, case: str, code: str, *, opened=True, timeout=0.3):
        driver, protocol, input_port = self.drive(case, opened=opened, timeout=timeout)
        with self.assertRaises(PhysicalConsoleFailure) as caught:
            driver.execute("return 21*2", timeout=timeout,
                           input_evidence=("input:",), result_evidence=("number: 42",))
        self.assertEqual(caught.exception.code, code)
        self.assertIsNotNone(caught.exception.baseline)
        self.assertIsNotNone(caught.exception.last)
        self.assertEqual(input_port.calls.count(("Enter",)), 1)
        self.assertFalse(any(call[0] == "submit" for call in protocol.calls))
        expected = [("status", None), ("status", "A"), ("status", "A")]
        if case in {"expired", "unavailable", "failed", "cancelled", "stale_outcome", "malformed_outcome", "outcome_timeout"}:
            expected.append(("outcome", "A", "7", "41"))
        if case in {"dropped", "missing", "foreign", "input_only", "result_only", "malformed_output"}:
            expected.extend([("outcome", "A", "7", "41"), ("output", "A", "7", "100")])
        if case == "submission_timeout":
            expected.extend([("status", "A"), ("status", "A")])
        if case == "outcome_timeout":
            expected.extend([("outcome", "A", "7", "41"), ("outcome", "A", "7", "41")])
        self.assertEqual(protocol.calls, expected)
        self.assertEqual(input_port.calls, [("focus",), ("select_all",),
                                            ("type", "return 21*2"), ("Enter",)])
        return caught.exception, protocol, input_port

    def test_clean_closed_overlay_has_exact_identity_and_one_physical_entry(self):
        driver, protocol, input_port = self.drive()
        receipt = driver.execute("return 21*2", input_evidence=("input:",), result_evidence=("number: 42",))
        self.assertEqual((receipt.identity.runtime, receipt.identity.session, receipt.request), ("A", "7", "41"))
        self.assertEqual(receipt.outcome["values"][1], {"type": "Boolean", "value": False})
        self.assertEqual(input_port.calls, [("focus",), ("F12",), ("select_all",),
                                            ("type", "return 21*2"), ("Enter",)])
        self.assertFalse(any(call[0] == "submit" for call in protocol.calls))
        self.assertEqual(protocol.calls, [
            ("status", None), ("status", "A"), ("status", "A"), ("status", "A"),
            ("outcome", "A", "7", "41"), ("output", "A", "7", "100"),
        ])

    def test_already_open_does_not_toggle_f12(self):
        driver, protocol, input_port = self.drive(opened=True)
        receipt = driver.execute("return 21*2", input_evidence=("input:",), result_evidence=("number: 42",))
        self.assertEqual(receipt.request, "41")
        self.assertNotIn(("F12",), input_port.calls)
        self.assertEqual(protocol.calls, [
            ("status", None), ("status", "A"), ("status", "A"),
            ("outcome", "A", "7", "41"), ("output", "A", "7", "100"),
        ])

    def test_stale_runtime_stops_before_outcome_or_replay(self):
        failure, protocol, _ = self.assert_failure("stale_runtime", "StaleRuntime")
        self.assertEqual(failure.baseline.runtime, "A")
        self.assertFalse(any(call[0] in ("outcome", "output") for call in protocol.calls))

    def test_reset_and_stale_outcome_are_distinct_session_failures(self):
        self.assert_failure("stale_session", "StaleSession")
        failure, _, _ = self.assert_failure("stale_outcome", "StaleSession")
        self.assertIsNotNone(failure.last)

    def test_duplicate_does_not_promote_highest_completed_or_later_request(self):
        _, protocol, _ = self.assert_failure("duplicate", "DuplicateSubmission")
        self.assertFalse(any(call[0] in ("outcome", "output") for call in protocol.calls))
        self.assertIn(("status", "A"), protocol.calls)

    def test_submitted_counter_regression_refuses_without_lookup_or_replay(self):
        _, protocol, _ = self.assert_failure("regression", "SubmittedRegression")
        self.assertEqual(protocol.calls, [("status", None), ("status", "A"), ("status", "A")])
        self.assertFalse(any(call[0] in ("outcome", "output") for call in protocol.calls))

    def test_expired_and_unavailable_reject_high_completed_watermark(self):
        self.assert_failure("expired", "Expired")
        self.assert_failure("unavailable", "Unavailable")

    def test_failed_and_cancelled_preserve_exact_terminal_refusal(self):
        failed, _, _ = self.assert_failure("failed", "Failed")
        self.assertEqual(failed.last["outcome"]["error"]["code"], "lua_runtime")
        self.assert_failure("cancelled", "Cancelled")

    def test_dropped_missing_and_foreign_output_are_not_success(self):
        self.assert_failure("dropped", "DroppedOutput")
        self.assert_failure("missing", "MissingOutput")
        self.assert_failure("foreign", "MissingOutput")

    def test_input_and_result_evidence_require_distinct_native_kinds(self):
        self.assert_failure("input_only", "MissingResultOutput")
        self.assert_failure("result_only", "MissingInputOutput")

    def test_submission_and_outcome_timeouts_never_replay(self):
        self.assert_failure("submission_timeout", "SubmissionTimeout", timeout=0.2)
        self.assert_failure("outcome_timeout", "OutcomeTimeout", timeout=0.2)

    def test_malformed_status_outcome_and_output_keep_baseline_and_last_response(self):
        self.assert_failure("malformed_status", "MalformedProtocol")
        self.assert_failure("malformed_outcome", "MalformedProtocol")
        self.assert_failure("malformed_output", "MalformedProtocol")

    def test_every_post_baseline_input_failure_keeps_baseline_and_last_observation(self):
        expected_protocol = {
            "focus": [("status", None)],
            "F12": [("status", None)],
            "select_all": [("status", None), ("status", "A")],
            "type": [("status", None), ("status", "A")],
            "Enter": [("status", None), ("status", "A")],
        }
        expected_input = {
            "focus": [],
            "F12": [("focus",)],
            "select_all": [("focus",)],
            "type": [("focus",), ("select_all",)],
            "Enter": [("focus",), ("select_all",), ("type", "return 21*2")],
        }
        for fail_at in ("focus", "F12", "select_all", "type", "Enter"):
            protocol = ScriptedConsoleProtocolPort("clean", opened=(fail_at != "F12"))
            input_port = FailingOwnedInputPort(protocol, fail_at)
            with self.subTest(fail_at=fail_at), self.assertRaises(PhysicalConsoleFailure) as caught:
                PhysicalConsoleDriver(protocol, input_port, FakeClock()).execute(
                    "return 21*2", input_evidence=("input:",), result_evidence=("number: 42",))
            self.assertEqual(caught.exception.code, "InputFailure")
            self.assertIsNotNone(caught.exception.baseline)
            self.assertIsNotNone(caught.exception.last)
            self.assertEqual(protocol.calls, expected_protocol[fail_at])
            self.assertEqual(input_port.calls, expected_input[fail_at])

    def test_multiline_history_and_suffix_stay_inside_one_entry_phase(self):
        commands = []
        base = OwnedX11Input(SimpleNamespace(window="0x10", env={"DISPLAY": ":97"}),
                             runner=lambda args, **kwargs: commands.append(tuple(args)))
        entry = base.console_entry(keys_before_submit=("ctrl+Up", "Tab"), suffix="(81)")
        entry.type_text("function f()\nreturn 21*2\nend")
        entry.press_enter()
        self.assertEqual(sum(command == ("xdotool", "key", "Return") for command in commands), 1)
        self.assertIn(("xdotool", "key", "ctrl+Return"), commands)
        self.assertIn(("xdotool", "key", "ctrl+Up"), commands)
        self.assertIn(("xdotool", "key", "Tab"), commands)

    def test_non_linux_owned_input_is_explicitly_unsupported(self):
        session = SimpleNamespace(env={"DISPLAY": ":97"}, capture_window="0x10",
                                  xvfb=SimpleNamespace(poll=lambda: None), display=97)
        with mock.patch("kpharness.owned_x11.sys.platform", "darwin"):
            with self.assertRaises(UnsupportedOwnedInput):
                OwnedX11Input.from_session(session)

    def test_display_identity_and_key_input_rejections(self):
        alive = SimpleNamespace(poll=lambda: None)
        good = SimpleNamespace(env={"DISPLAY": ":97.0"}, capture_window="0x10", xvfb=alive, display=97)
        self.assertEqual(OwnedX11Input.from_session(good).target.window, "0x10")
        for display, number in ((":97", 9), (":970", 97), ("localhost:97", 97)):
            bad = SimpleNamespace(env={"DISPLAY": display}, capture_window="0x10", xvfb=alive, display=number)
            with self.subTest(display=display, number=number), self.assertRaises(Exception):
                OwnedX11Input.from_session(bad)
        base = OwnedX11Input(SimpleNamespace(window="0x10", env={"DISPLAY": ":97"}), runner=lambda *a, **k: None)
        with self.assertRaises(Exception):
            base.console_entry(keys_before_submit="ctrl+Up")

    def test_checked_in_owned_session_window_producer_rejects_reuse_and_replacement(self):
        live = SimpleNamespace(poll=lambda: None)
        session = SimpleNamespace(xvfb=live, env={"DISPLAY": ":97"}, display=97,
                                  launcher=SimpleNamespace(pid=42, poll=lambda: None),
                                  capture_window=None, _capture_window_pid=None,
                                  game_pids=lambda: [42], log=lambda _: None)
        search = SimpleNamespace(returncode=0, stdout="99\n")
        def query(args, **kwargs):
            if args[1] == "getwindowpid":
                return "42\n"
            return "WIDTH=1024\nHEIGHT=768\n"
        with mock.patch("kpharness.session.subprocess.run", return_value=search), \
             mock.patch("kpharness.session.subprocess.check_output", side_effect=query):
            self.assertEqual(GameSession.capture_owned_game_window(session), "0x63")
            self.assertEqual(GameSession.capture_owned_game_window(session), "0x63")
        with mock.patch("kpharness.session.subprocess.check_output", side_effect=["43\n", "WIDTH=1024\nHEIGHT=768\n"]):
            with self.assertRaises(RuntimeError):
                GameSession.capture_owned_game_window(session)
        session.xvfb = None
        with self.assertRaises(RuntimeError):
            GameSession.capture_owned_game_window(session)

    def test_receipt_is_deeply_immutable_and_ids_remain_canonical_strings(self):
        for submitted in ("9007199254740993", "18446744073709551614"):
            protocol = LargeIdentifierProtocol(submitted)
            receipt = PhysicalConsoleDriver(protocol, ScriptedOwnedInputPort(protocol), FakeClock()).execute(
                "return 21*2", input_evidence=("input:",), result_evidence=("number: 42",))
            self.assertEqual(receipt.identity.submitted, submitted)
            self.assertEqual(receipt.request, str(int(submitted) + 1))
            self.assertIsInstance(receipt.identity.session, str)
            with self.assertRaises(TypeError):
                receipt.outcome["state"] = "Failed"
            with self.assertRaises(TypeError):
                receipt.outcome["values"][0]["type"] = "Boolean"
            outcome = receipt.outcome
            nested = receipt.outcome["values"][0]
            with self.assertRaises(TypeError):
                outcome |= {"state": "Failed"}
            with self.assertRaises(TypeError):
                dict.__setitem__(outcome, "state", "Failed")
            with self.assertRaises(TypeError):
                nested |= {"type": "Boolean"}
            with self.assertRaises(TypeError):
                dict.__setitem__(nested, "type", "Boolean")

    def test_console_evidence_refuses_empty_and_non_string_items(self):
        for field in ("input_contains", "contains"):
            for invalid in ([], [""], ["result", ""], [42], {"result"}):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ConsoleStepError):
                    _evidence_strings(invalid, field)
        self.assertEqual(_evidence_strings(["input:", "return 21*2"], "input_contains"),
                         ("input:", "return 21*2"))

    def test_toml_expect_values_matches_frozen_typed_values_and_rejects_change(self):
        driver, protocol, input_port = self.drive(opened=True)
        receipt = driver.execute("return 21*2", input_evidence=("input:",),
                                 result_evidence=("number: 42",))
        expected = [
            {"type": "Nil"},
            {"type": "Boolean", "value": False},
            {"type": "Number", "kind": "Finite", "value": 42},
        ]
        _expect_values({"expect_values": expected}, receipt.outcome)
        changed = [dict(value) for value in expected]
        changed[2]["value"] = 43
        with self.assertRaises(ConsoleStepError):
            _expect_values({"expect_values": changed}, receipt.outcome)
        self.assertEqual(protocol.calls, [
            ("status", None), ("status", "A"), ("status", "A"),
            ("outcome", "A", "7", "41"), ("output", "A", "7", "100"),
        ])
        self.assertEqual(input_port.calls, [("focus",), ("select_all",),
                                            ("type", "return 21*2"), ("Enter",)])

    def test_console_command_receipt_round_trips_structured_output_lines(self):
        protocol = ScriptedConsoleProtocolPort("clean", opened=True)
        input_port = ScriptedOwnedInputPort(protocol)
        adapter = SimpleNamespace(console_entry=mock.Mock(return_value=input_port))
        with TemporaryDirectory() as directory:
            runner = SimpleNamespace(session=SimpleNamespace(), ch=ScenarioChannel(protocol),
                                     run_dir=directory)
            step = SimpleNamespace(index=4, raw={
                "do": "console_command", "code": "return 21*2",
                "input_contains": ["input:"], "contains": ["number: 42"],
            })
            with mock.patch("kpharness.console_steps.OwnedX11Input.from_session",
                            return_value=adapter):
                self.assertEqual(execute_console_step(runner, step),
                                 "physical console request 41 Succeeded")
            body = json.loads((Path(directory) / "console-command-4.json").read_text())
        self.assertEqual(len(body["lines"]), 2)
        for line in body["lines"]:
            self.assertIsInstance(line, dict)
            self.assertEqual((line["session"], line["request"], line["sequence"]),
                             ("7", "41", "101"))
            self.assertIsInstance(line["kind"], dict)
            self.assertIsInstance(line["text"], dict)
            self.assertEqual(line["kind"]["encoding"], "base64")
            self.assertEqual(line["text"]["encoding"], "base64")

    def test_advance_ticks_requires_bounded_positive_progress_and_detects_reset(self):
        def step(ticks):
            return SimpleNamespace(index=1, raw={"do": "advance_ticks", "ticks": ticks, "timeout": 1})
        runner = SimpleNamespace(ch=TickChannel([{"server_tick": 10}, {"server_tick": 15}]), watchdog=NoVerdict())
        self.assertIn("10 -> 15", execute_console_step(runner, step(5)))
        for ticks in (0, -1, 100001):
            with self.subTest(ticks=ticks), self.assertRaises(ConsoleStepError):
                execute_console_step(SimpleNamespace(ch=TickChannel([{"server_tick": 10}]), watchdog=NoVerdict()), step(ticks))
        with self.assertRaises(ConsoleStepError) as reset:
            execute_console_step(SimpleNamespace(ch=TickChannel([{"server_tick": 10}, {"server_tick": 9}]), watchdog=NoVerdict()), step(1))
        self.assertIn("reset", str(reset.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
