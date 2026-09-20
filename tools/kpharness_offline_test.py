#!/usr/bin/env python3
"""Offline test of the harness driver against a fake in-process server.

No game, no Wine, no display. A small TCP server speaks the wire protocol
from docs/harness-design.md (ping, status, state, events, subscribe, lua,
load_save, warp, dialog, reply, screenshot, quit) with a state machine the
tests can push around: a load takes a few polls, ticks can be frozen, the
fingerprint can be pinned. That is enough to exercise the client, the
waits, every oracle, the checkpoint store and the scenario runner without
touching anything real.

    python3 tools/kpharness_offline_test.py
    python3 tools/kpharness_offline_test.py -v TestOracle
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "harness"))

from kpharness import waits as W  # noqa: E402
from kpharness import world as World  # noqa: E402
from kpharness import bwm as Bwm  # noqa: E402
from kpharness.checkpoints import Checkpoints  # noqa: E402
from kpharness.client import Channel, ChannelClosed, ChannelError, ChannelTimeout  # noqa: E402
from kpharness.oracle import OracleTrip, Watchdog, fingerprint  # noqa: E402
from kpharness.scenario import Scenario, ScenarioError, ScenarioRunner  # noqa: E402
from kpharness import pioneer as P  # noqa: E402
from kpharness import session as S  # noqa: E402
from kpharness.session import (BootFailure, GameSession, overlay_tree,  # noqa: E402
                               tune_ini, write_runtime_ini, pids_by_name, free_port)
from kpharness.shots import best_match, ppm_to_png, have_pillow  # noqa: E402
from kpharness import targets as T  # noqa: E402
from kpharness import discover as D  # noqa: E402


# ------------------------------------------------------------ fake server --

class FakeGame:
    """The engine as the wire sees it. One client at a time, like the real one."""

    def __init__(self, game_dir: Path):
        self.game_dir = game_dir
        self.lock = threading.Lock()
        self.phase = "menu"
        self.chargen_stage = "none"
        self.module = None
        self.server_tick = 0
        self.client_tick = 100
        self.freeze = False
        self.freeze_all = False
        self.pin_fingerprint = False
        self.load_polls_left = 0
        self.pending_module = None
        self.events = []            # [{"event", "seq", "server_tick", ...}]
        self.seq = 0
        self.globals = {}
        self.dialog = None
        self.dialog_replies = [{"index": 0, "link": 0, "text": "Who are you?", "active": True},
                               {"index": 1, "link": 1, "text": "Get away from me.", "active": False},
                               {"index": 2, "link": 2, "text": "Let's go.", "active": True}]
        self.globals_args = []
        self.slow_once = False
        self.slow_once_cmd = None
        self.drop_once_for = None
        self.error_once_cmd = None  # (cmd, message): refuse that command once
        self.auto_pause = 0
        self.subscribers = []
        self.pc = {"id": 0x80000001, "x": 15.4, "y": 20.1, "z": -1.2, "hp": 24, "max_hp": 24}
        self.build = "k1_steam_103_unpacked"
        self.requests = []
        self.lua_codes = []
        self.lua_requests = []
        self.lua_fail_substring = None
        self.door_requests = []     # every door_commit_open request as sent
        self.door_committed = False

    def push(self, name, **fields):
        self.seq += 1
        e = {"event": name, "seq": self.seq, "tick": self.server_tick, **fields}
        self.events.append(e)
        for s in list(self.subscribers):
            try:
                s.sendall((json.dumps(e) + "\n").encode())
            except OSError:
                pass

    def tick(self):
        if not self.freeze_all:
            self.server_tick += 1
        if not self.freeze:
            self.client_tick += 3
        if self.phase == "loading":
            self.load_polls_left -= 1
            if self.load_polls_left <= 0:
                self.phase = "gameplay"
                self.module = self.pending_module
                self.push("OnModuleLoad", module=self.module)
                self.push("OnAreaEnter", area=self.module)
                self.push("OnRunScript", script="k_pend_area01", object=0x80000002)
        if self.phase == "gameplay" and not self.pin_fingerprint:
            self.pc["x"] += 0.7

    def state(self):
        return {
            "phase": self.phase,
            "phase_detail": {"server_mode": 2 if self.phase != "menu" else 0,
                             "loading_module": 1 if self.phase == "loading" else 0,
                             "load_step": 0 if self.pin_fingerprint else self.load_polls_left},
            "chargen_stage": self.chargen_stage,
            "module": self.module, "server_tick": self.server_tick,
            "client_tick": self.client_tick, "pc": dict(self.pc) if self.module else None,
            "party": [{"id": 0x80000002, "tag": "trask"}] if self.module else [],
            "dialog": self.dialog, "globals_hash": "%08x" % hash(tuple(sorted(self.globals.items())) ) if self.globals else "0",
            "journal_hash": "0", "counts": {"globals": len(self.globals), "journal": 0},
            "live": True, "poisoned": [],
        }

    def handle(self, req, conn):
        cmd = req.get("cmd")
        self.requests.append(cmd)
        rid = req.get("id")
        if self.drop_once_for == cmd:
            self.drop_once_for = None
            return {"_drop": True}
        if self.slow_once and cmd == "ping":
            self.slow_once = False
            time.sleep(0.6)
        if self.slow_once_cmd == cmd:
            self.slow_once_cmd = None
            time.sleep(0.6)
        with self.lock:
            self.tick()
            if self.error_once_cmd and self.error_once_cmd[0] == cmd:
                _, message = self.error_once_cmd
                self.error_once_cmd = None
                return {"id": rid, "ok": False, "error": message}
            if cmd == "clear_auto_pause":
                self.auto_pause = 0
                return {"id": rid, "ok": True, "result": {"cleared": True}}
            if cmd == "door_commit_open":
                # The real command takes one exact unsigned 32-bit `door` id
                # and answers {door, committed}; it commits the pending open
                # state, so GetIsOpen flips on the next probe.
                self.door_requests.append(dict(req))
                door = req.get("door")
                if isinstance(door, bool) or not isinstance(door, int) or not 0 <= door <= 0xffffffff:
                    return {"id": rid, "ok": False,
                            "error": "door_commit_open: `door` must be an exact unsigned 32-bit object id"}
                self.door_committed = True
                return {"id": rid, "ok": True, "result": {"door": door, "committed": True}}
            if cmd == "ping":
                return {"id": rid, "ok": True, "result": {"pong": True, "tick": self.server_tick}}
            if cmd == "status":
                return {"id": rid, "ok": True, "result": {
                    "build": self.build, "game": "k1", "phase": "running", "live": True,
                    "poisoned": [], "hooks": 17, "client_tick": self.client_tick,
                    "server_tick": self.server_tick, "pid": os.getpid(), "uptime_ms": 1000}}
            if cmd == "state":
                return {"id": rid, "ok": True, "result": self.state()}
            if cmd == "events":
                since = int(req.get("since", 0))
                limit = int(req.get("limit", 200))
                items = [e for e in self.events if e["seq"] > since][:limit]
                return {"id": rid, "ok": True, "result": {"seq": self.seq, "items": items}}
            if cmd == "subscribe":
                self.subscribers.append(conn)
                return {"id": rid, "ok": True, "result": {"subscribed": True}}
            if cmd == "unsubscribe":
                if conn in self.subscribers:
                    self.subscribers.remove(conn)
                return {"id": rid, "ok": True, "result": {"subscribed": False}}
            if cmd == "load_save":
                d = str(req.get("dir", ""))
                if not (self.game_dir / "Saves" / d).is_dir():
                    return {"id": rid, "ok": False, "error": f"no such save: {d}"}
                self.phase, self.load_polls_left = "loading", 3
                self.pending_module = "end_m01aa"
                self.push("OnLoad", dir=d)
                return {"id": rid, "ok": True, "result": {"started": True}}
            if cmd == "warp":
                if self.phase != "gameplay":
                    return {"id": rid, "ok": False, "error": "warp needs gameplay"}
                self.phase, self.load_polls_left = "loading", 2
                self.pending_module = str(req.get("module"))
                return {"id": rid, "ok": True, "result": {"started": True}}
            if cmd == "lua":
                self.lua_requests.append(dict(req))
                return {"id": rid, **self.lua(str(req.get("code", "")))}
            if cmd == "globals":
                # The real command takes no arguments and answers with three
                # typed maps; a driver that sends `name` gets it ignored.
                self.globals_args.append(dict(req))
                return {"id": rid, "ok": True,
                        "result": {"bools": {}, "numbers": dict(self.globals), "strings": {}}}
            if cmd == "dialog":
                if self.dialog is None:
                    return {"id": rid, "ok": False, "error": "no conversation"}
                return {"id": rid, "ok": True, "result": self.dialog}
            if cmd == "reply":
                if self.dialog is None:
                    return {"id": rid, "ok": False, "error": "no conversation"}
                idx = int(req.get("index", -1))
                if idx == 2:
                    self.dialog, self.phase = None, "gameplay"
                else:
                    self.dialog = {"entry": 5 + idx, "reply": -1, "text": "Entry after reply",
                                   "replies": [{"index": 0, "link": 0, "text": "Ok.", "active": True}],
                                   "waiting_for_player": True, "waiting_on_sound": False}
                return {"id": rid, "ok": True, "result": {"picked": idx}}
            if cmd in ("dialog_skip", "dialog_abort", "dismiss_container", "take_all_container",
                       "accept_party_selection", "auto_levelup", "set_party_leader"):
                if self.dialog is not None and cmd == "dialog_abort":
                    self.dialog, self.phase = None, "gameplay"
                elif self.dialog is not None:
                    # The VO wait is over and the node now takes a pick.
                    self.dialog["waiting_on_sound"] = False
                    self.dialog["waiting_for_player"] = True
                return {"id": rid, "ok": True, "result": {}}
            if cmd == "screenshot":
                rel = str(req.get("path", ""))
                p = self.game_dir / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"P6\n4 2\n255\n" + bytes([10, 20, 30] * 8))
                return {"id": rid, "ok": True, "result": {"path": rel, "width": 4, "height": 2}}
            if cmd in ("new_game", "fixed_step"):
                return {"id": rid, "ok": False, "error": f"unsupported on {self.build}: site unresolved"}
            if cmd == "speed":
                return {"id": rid, "ok": True, "result": {"scale": req.get("scale")}}
            if cmd == "quit":
                return {"id": rid, "ok": True, "result": {"quitting": True}, "_close": True}
            return {"id": rid, "ok": False, "error": f"unknown command {cmd!r}"}

    def lua(self, code):
        self.lua_codes.append(code)
        if self.lua_fail_substring and self.lua_fail_substring in code:
            return {"ok": False, "error": "lua: target vanished"}
        if "GetModuleName" in code:
            return {"ok": True, "result": self.module}
        if "ActionStartConversation" in code:
            self.phase = "dialog"
            self.dialog = {"entry": 0, "reply": -1, "strref": 1234, "text": "Wake up!",
                           "replies": [dict(r) for r in self.dialog_replies],
                           "waiting_for_player": False, "waiting_on_sound": True}
            return {"ok": True, "result": None}
        if "SetGlobalNumber" in code or "SetGlobalBoolean" in code:
            import re
            m = re.search(r"SetGlobal(?:Number|Boolean)[\"'],\s*['\"]([^'\"]+)['\"],\s*(\d+)", code)
            if m:
                self.globals[m.group(1)] = int(m.group(2))
            return {"ok": True, "result": None}
        if "GetGlobalNumber" in code:
            import re
            m = re.search(r"local n = '([^']+)'", code)
            return {"ok": True, "result": self.globals.get(m.group(1), 0) if m else 0}
        if "nwscript.call" in code and self.module is None:
            return {"ok": False, "error": "vm not bound: no script has run yet"}
        if code.startswith("error"):
            return {"ok": False, "error": "lua: " + code}
        return {"ok": True, "result": code}


class FakeServer(threading.Thread):
    def __init__(self, game: FakeGame):
        super().__init__(daemon=True)
        self.game = game
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        # Configure this before the thread starts.  teardown closes the
        # listening socket to wake accept(), and doing settimeout() in run()
        # races that close on a fast test teardown.
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.stop = False
        self.client = None

    def run(self):
        while not self.stop:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if self.client is not None:
                try:
                    conn.sendall(b'{"ok": false, "error": "busy: one client at a time"}\n')
                finally:
                    conn.close()
                continue
            self.client = conn
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    def serve(self, conn):
        buf = b""
        conn.settimeout(0.2)
        try:
            while not self.stop:
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        req = json.loads(line)
                    except ValueError:
                        conn.sendall(b'{"ok": false, "error": "malformed request"}\n')
                        continue
                    reply = self.game.handle(req, conn)
                    close = reply.pop("_close", False)
                    drop = reply.pop("_drop", False)
                    if not drop:
                        conn.sendall((json.dumps(reply) + "\n").encode())
                    if close or drop:
                        raise ConnectionAbortedError
        except (ConnectionAbortedError, OSError):
            pass
        finally:
            if conn in self.game.subscribers:
                self.game.subscribers.remove(conn)
            conn.close()
            self.client = None

    def shutdown(self):
        self.stop = True
        try:
            self.sock.close()
        except OSError:
            pass
        self.join(timeout=1.0)


class FakeSession:
    """What the Watchdog and the runner need from a session."""

    def __init__(self, game: FakeGame, run_dir: Path, save_dir: Path):
        self.game = game
        self.run_dir = run_dir
        self.game_dir = game.game_dir
        self.save_dir = save_dir
        self.build = game.build
        self.alive = True
        self.stderr = ""
        self.rtlog = ""
        self.dumps = 0

    def process_alive(self):
        return self.alive

    def read_new_stderr(self):
        s, self.stderr = self.stderr, ""
        return s

    def read_new_runtime_log(self):
        s, self.rtlog = self.rtlog, ""
        return s

    def stack_dump(self):
        self.dumps += 1
        return "#0 fake frame"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kpharness_test_"))
        self.game_dir = self.tmp / "game"
        self.save_dir = self.game_dir / "Saves"
        (self.save_dir / "000001 - AUTOSAVE").mkdir(parents=True)
        (self.save_dir / "000001 - AUTOSAVE" / "SAVEGAME.sav").write_bytes(b"sav")
        (self.save_dir / "000001 - AUTOSAVE" / "savenfo.res").write_bytes(b"nfo")
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        self.game = FakeGame(self.game_dir)
        resource_dir = self.game_dir / "harness-resources"
        resource_dir.mkdir()
        self.door_wok = resource_dir / "test.wok"
        self.door_wok.write_bytes(self._door_mesh())
        self.door_route_toml = """walkmesh_resource = \"test/m01aa_01a.wok\"
walkmesh_file = \"harness-resources/test.wok\"
walkmesh_size = %d
walkmesh_sha256 = \"%s\"
walkmesh_path = [0, 1]
walkmesh_approach_face = 0
walkmesh_face = 1
""" % (self.door_wok.stat().st_size, hashlib.sha256(self.door_wok.read_bytes()).hexdigest())
        self.server = FakeServer(self.game)
        self.server.start()
        self.ch = Channel("127.0.0.1", self.server.port, timeout=2.0)
        self.ch.connect()
        self.session = FakeSession(self.game, self.run_dir, self.save_dir)

    @staticmethod
    def _door_mesh():
        # Face centroids are the route's declared approach/far points and
        # share edge (p0,p1), so the scenario exercises real BWM validation.
        a = (19.914662679036457, 20.194860458374023, -1.274999976158142)
        b = (20.32586733500163, 21.70310910542806, -1.274999976158142)
        p0, p1 = (21., 20., -1.275), (20., 20., -1.275)
        p2 = tuple(3 * a[i] - p0[i] - p1[i] for i in range(3))
        p3 = tuple(3 * b[i] - p0[i] - p1[i] for i in range(3))
        vertices, faces = [p0, p1, p2, p3], [(0, 1, 2), (1, 0, 3)]
        vo, io, ao = 136, 184, 208
        data = bytearray(232)
        data[:8] = b"BWM V1.0"
        struct.pack_into("<16I", data, 72, 4, vo, 2, io, 0, 0, 0, 0, 0, 0, 2, ao, 0, 0, 0, 0)
        for i, point in enumerate(vertices): struct.pack_into("<3f", data, vo + i * 12, *point)
        for i, face in enumerate(faces): struct.pack_into("<3I", data, io + i * 12, *face)
        return bytes(data)

    def tearDown(self):
        self.ch.close()
        self.server.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)


# ------------------------------------------------------------------ tests --

class TestClient(Base):
    def test_ping_and_ids(self):
        r1 = self.ch.ping()
        r2 = self.ch.ping()
        self.assertTrue(r1["pong"])
        self.assertGreater(r2["tick"], r1["tick"])
        self.assertEqual(self.ch._next_id, 3)

    def test_world_facing_ids_cross_channel_and_bound_emitted_probe(self):
        """The resolved id reaches the wire and only it is eligible for facing."""
        real_lua = self.game.lua

        def lua(code):
            if "local MAX_OBJECTS" in code:
                return {"ok": True, "result": {"values": [_world(locked=False, open_=False)]}}
            return real_lua(code)

        self.game.lua = lua
        world = World.observe_world(self.ch, facing_ids=(0x80000010,))
        self.assertEqual(world["objects"][0]["facing"], 180.0)
        request = self.game.lua_requests[-1]
        self.assertEqual(request["facing_ids"], [0x80000010])
        self.assertIn("local FACING = {[2147483664]=true}", request["code"])
        self.assertIn("kind == DOOR and FACING[object]", request["code"])

    def test_world_facing_missing_from_actual_channel_reply_fails_with_bounded_identity(self):
        """A live-shaped missing field must fail before scenario indexing it."""
        real_lua = self.game.lua

        def lua(code):
            if "local MAX_OBJECTS" in code:
                world = _world(locked=False, open_=False)
                del world["objects"][0]["facing"]
                return {"ok": True, "result": {"values": [world]}}
            return real_lua(code)

        self.game.lua = lua
        with self.assertRaises(World.WorldProbeError) as caught:
            World.observe_world(self.ch, facing_ids=(0x80000010,))
        detail = str(caught.exception)
        self.assertIn("requested_facing_ids=[2147483664]", detail)
        self.assertIn("id=2147483664", detail)
        self.assertIn("tag='end_door01'", detail)
        self.assertIn("type=8", detail)
        self.assertIn("keys=[", detail)
        request = self.game.lua_requests[-1]
        self.assertEqual(request["facing_ids"], [0x80000010])

    def test_status_state(self):
        st = self.ch.status()
        self.assertEqual(st["build"], "k1_steam_103_unpacked")
        s = self.ch.state()
        self.assertEqual(s["phase"], "menu")
        self.assertIs(self.ch.last_state, s)

    def test_error_and_unsupported(self):
        with self.assertRaises(ChannelError) as cm:
            self.ch.request("nonsense")
        self.assertIn("unknown command", cm.exception.error)
        self.assertFalse(cm.exception.unsupported)
        with self.assertRaises(ChannelError) as cm:
            self.ch.request("new_game")
        self.assertTrue(cm.exception.unsupported)

    def test_lua_helper_and_vm_error(self):
        with self.assertRaises(ChannelError) as cm:
            self.ch.lua("return nwscript.call(\"GetFirstPC\")")
        self.assertIn("vm not bound", cm.exception.error)
        self.assertEqual(self.ch.lua("return 1"), "return 1")

    def test_timeout_then_recovery(self):
        self.game.slow_once = True
        with self.assertRaises(ChannelTimeout):
            self.ch.request("ping", timeout=0.2)
        # The late reply carries the old id and is dropped; the next call works.
        r = self.ch.ping()
        self.assertTrue(r["pong"])

    def test_generic_mutation_does_not_use_wait_reconnector(self):
        """A lost reply to a mutating command stays explicit, never replayed."""
        reconnects = []
        self.ch.set_wait_reconnector(lambda _: reconnects.append("called"))
        self.game.drop_once_for = "speed"
        with self.assertRaises(ChannelClosed):
            self.ch.request("speed", scale=2.0)
        self.assertEqual(reconnects, [])

    def test_malformed_line_does_not_kill_connection(self):
        self.ch._send_line({"id": 999, "cmd": "state"})  # consumed below as stale
        self.ch._sock.sendall(b"this is not json\n")
        self.assertTrue(self.ch.ping()["pong"])

    def test_events_cursor_and_subscribe(self):
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        self.assertEqual(self.ch.cursor, 0)
        items = self.ch.events()
        self.assertEqual([e["event"] for e in items], ["OnLoad"])
        self.assertEqual(self.ch.cursor, 1)
        self.ch.subscribe()
        for _ in range(4):
            self.ch.state()
        self.ch.drain_events(0.2)
        names = [e["event"] for e in self.ch.events_seen]
        self.assertIn("OnModuleLoad", names)
        self.assertIn("OnAreaEnter", names)
        self.assertGreater(self.ch.cursor, 1)
        self.ch.unsubscribe()

    def test_second_client_refused(self):
        other = Channel("127.0.0.1", self.server.port, timeout=1.0)
        other.connect()
        with self.assertRaises(ChannelError):
            other.ping()
        other.close()


class TestWaits(Base):
    def _wait_reconnector(self, calls):
        """Fake the session-owned operation after the server has retired the peer."""
        def reconnect(channel):
            calls.append(channel.cursor)
            deadline = time.monotonic() + 1.0
            while self.server.client is not None and time.monotonic() < deadline:
                time.sleep(0.005)
            channel.connect(connect_timeout=0.5)
        return reconnect

    def test_wait_reconnects_closed_state_and_restores_subscription(self):
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        self.assertEqual(len(self.ch.events()), 1)
        self.assertEqual(self.ch.cursor, 1)
        self.ch.subscribe()
        calls = []
        self.ch.set_wait_reconnector(self._wait_reconnector(calls))
        self.game.drop_once_for = "state"

        st = W.wait_until(self.ch, W.phase_is("gameplay"), 3.0, poll=0.01)

        self.assertEqual(st["module"], "end_m01aa")
        self.assertEqual(calls, [1])
        self.assertTrue(self.ch.subscribed)
        # The reconnect does not rewind the already-observed OnLoad boundary.
        self.assertEqual(self.ch.cursor, 1)
        self.assertGreaterEqual(self.game.requests.count("subscribe"), 2)

    def test_wait_event_read_reconnects_from_its_existing_cursor(self):
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        calls = []
        self.ch.set_wait_reconnector(self._wait_reconnector(calls))
        self.game.drop_once_for = "events"

        self.assertTrue(W.event_seen("OnLoad", 0)({}, self.ch))

        self.assertEqual(calls, [0])
        self.assertEqual(self.ch.cursor, 1)

    def test_wait_timeout_does_not_reconnect(self):
        reconnects = []
        self.ch.set_wait_reconnector(lambda _: reconnects.append("called"))
        self.ch.timeout = 0.03
        self.game.slow_once_cmd = "state"

        with self.assertRaises(W.WaitTimeout):
            W.wait_until(self.ch, W.phase_is("gameplay"), 0.08, poll=0.01)

        self.assertEqual(reconnects, [])

    def test_chargen_open_is_an_engine_state_predicate(self):
        pred = W.chargen_open()
        self.assertTrue(pred({"phase_detail": {"chargen": 1}}, self.ch))
        self.assertFalse(pred({"phase_detail": {"chargen": 0}}, self.ch))
        self.assertFalse(pred({"phase_detail": {}}, self.ch))

    def test_chargen_stage_is_a_state_predicate(self):
        self.assertTrue(W.chargen_stage_is("class")({"chargen_stage": "class"}, self.ch))
        self.assertFalse(W.chargen_stage_is("route")({"chargen_stage": "class"}, self.ch))

    def test_phase_any_accepts_only_declared_live_phases(self):
        pred = W.phase_is_any(["gameplay", "dialog"])
        self.assertTrue(pred({"phase": "gameplay"}, self.ch))
        self.assertTrue(pred({"phase": "dialog"}, self.ch))
        self.assertFalse(pred({"phase": "unknown"}, self.ch))
        self.assertFalse(pred({"phase": "loading"}, self.ch))

    def test_emitted_chargen_class_controls_match_the_recovered_layout(self):
        for build in ("k1_gog_103", "k1_steam_103_unpacked"):
            sites = json.loads((ROOT / "data" / "addresses" / f"{build}.json").read_text())["sites"]
            self.assertEqual(sites["chargen.class_controls"]["offset"], 0x6C)
            self.assertEqual(sites["chargen.class_control"]["size"], 604)
            set_visible = sites["gui.main_chargen_set_visible_panel"]
            self.assertEqual(set_visible["addr"], 0x006EA760)
            # The generator emits EXPECT_LEN (16) bytes of the recovered
            # 20-byte prologue; any prefix of at least 16 bytes is the same site.
            recovered = "538b5c2408568bf13b9ec82200000f848b000000"
            self.assertGreaterEqual(len(set_visible["expected_bytes"]), 32)
            self.assertTrue(recovered.startswith(set_visible["expected_bytes"]),
                            set_visible["expected_bytes"])
            self.assertEqual(sites["chargen.main_quick_panel"]["offset"], 0x70)
            self.assertEqual(sites["chargen.child_main_panel"]["offset"], 0x68)
            self.assertEqual(sites["chargen.main_visible_panel"]["offset"], 0x22C8)
            accept_party = sites["gui.party_selection_accept_party"]
            self.assertEqual(accept_party["addr"], 0x006BE560)
            self.assertGreaterEqual(len(accept_party["expected_bytes"]), 32)
            self.assertTrue("81ecc4000000a1fc397a00535556c744240c00000000c744".startswith(accept_party["expected_bytes"]), accept_party["expected_bytes"])
            self.assertEqual(sites["gui.party_selection_vtable"]["addr"], 0x00756D28)
            self.assertEqual(sites["gui.initialized"]["offset"], 0x108)
            self.assertEqual(sites["gui.party_selection_selected_count"]["offset"], 0x68)
            self.assertEqual(sites["gui.party_selection_mode"]["offset"], 0x6C)
            self.assertEqual(sites["gui.party_selection_entry0_flags"]["offset"], 0x4C4)
        # The encrypted Steam table borrows the deciphered twin's adjudications
        # (same .text once unpacked), so it carries the chargen sites too.
        encrypted = json.loads(
            (ROOT / "data/addresses/k1_steam_103.json").read_text())["sites"]
        self.assertEqual(encrypted["gui.main_chargen_set_visible_panel"]["addr"], 0x006EA760)
        self.assertEqual(encrypted["gui.party_selection_accept_party"]["addr"], 0x006BE560)

    def test_chargen_select_failure_has_bounded_structural_diagnostics(self):
        """A live mismatch names only the manager delta, membership, and route links."""
        source = (ROOT / "src" / "harness" / "engine_k1.cpp").read_text()
        self.assertIn("before_count=", source)
        self.assertIn("after_count=", source)
        self.assertIn("class_listed=", source)
        self.assertIn("route=%08x", source)
        self.assertIn("i < 4", source)

    def test_wait_phase_after_load(self):
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        st = W.wait_until(self.ch, W.phase_is("gameplay"), 5.0, poll=0.01)
        self.assertEqual(st["module"], "end_m01aa")

    def test_wait_timeout_dumps_state(self):
        with self.assertRaises(W.WaitTimeout) as cm:
            W.wait_until(self.ch, W.phase_is("gameplay"), 0.2, poll=0.02)
        self.assertEqual(cm.exception.state["phase"], "menu")
        self.assertIn("phase=menu", str(cm.exception))

    def test_event_seen_and_order_with_field_glob(self):
        mark = self.ch.cursor
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        W.wait_until(self.ch, W.phase_is("gameplay"), 5.0, poll=0.01)
        self.assertTrue(W.event_seen("OnAreaEnter", mark)({}, self.ch))
        self.assertFalse(W.event_seen("OnAreaEnter", self.ch.cursor)({}, self.ch))
        pred = W.events_in_order(["OnModuleLoad", "OnAreaEnter",
                                  {"event": "OnRunScript", "script": "k_pend_*"}], mark)
        self.assertTrue(pred({}, self.ch))
        bad = W.events_in_order(["OnAreaEnter", "OnModuleLoad"], mark)
        self.assertFalse(bad({}, self.ch))

    def test_global_equals_command_and_lua_fallback(self):
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        W.wait_until(self.ch, W.phase_is("gameplay"), 5.0, poll=0.01)
        self.assertFalse(W.global_equals("END_TRASK_TALK", 1)({}, self.ch))  # lua fallback -> 0
        self.ch.lua("nwscript.call(\"SetGlobalNumber\",'END_TRASK_TALK', 1)")
        self.assertTrue(W.global_equals("END_TRASK_TALK", 1)({}, self.ch))   # globals command
        self.assertTrue(W.global_equals("END_TRASK_TALK", True)({}, self.ch))

    def test_globals_result_is_read_as_typed_maps(self):
        """`globals` answers {bools, numbers, strings} and takes no argument."""
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        W.wait_until(self.ch, W.phase_is("gameplay"), 5.0, poll=0.01)
        self.ch.lua("nwscript.call(\"SetGlobalNumber\",'END_TRASK_TALK', 1)")
        self.game.globals_args.clear()
        self.assertEqual(W.read_global(self.ch, "END_TRASK_TALK"), 1)
        self.assertEqual(W.read_global(self.ch, "end_trask_talk"), 1)   # matched without case
        self.assertTrue(self.game.globals_args)
        for sent in self.game.globals_args:
            self.assertNotIn("name", sent)

    def test_dialog_waiting_and_auto_skip(self):
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        W.wait_until(self.ch, W.phase_is("gameplay"), 5.0, poll=0.01)
        self.ch.lua("kp.as(pc, function() nwscript.call(\"ActionStartConversation\",x, '') end)")
        st = self.ch.state()
        self.assertEqual(st["phase"], "dialog")
        # The runtime spells these `waiting_on_sound` and `waiting_for_player`;
        # a driver reading anything else sees a ready dialog too early.
        self.assertTrue(st["dialog"]["waiting_on_sound"])
        self.assertFalse(W.dialog_waiting()(st, self.ch))       # waiting on sound
        # The wait sends dialog_skip on its own while the node waits on VO;
        # only that clears the fake's sound flag.
        st = W.wait_until(self.ch, W.dialog_waiting(), 2.0, poll=0.01)
        self.assertTrue(W.dialog_waiting()(st, self.ch))
        self.assertIn("dialog_skip", self.game.requests)

    def test_dialog_waiting_does_not_need_waiting_for_player(self):
        """An owner chain that does not resolve leaves both flags false. The
        wait must still see a reply list: on such a build `reply` refuses by
        name, and the scenario skips instead of timing out here first."""
        st = {"dialog": {"replies": [{"index": 0, "link": 0, "text": "Ok.", "active": True}],
                         "waiting_for_player": False, "waiting_on_sound": False}}
        self.assertTrue(W.dialog_waiting()(st, self.ch))
        st["dialog"]["waiting_on_sound"] = True
        self.assertFalse(W.dialog_waiting()(st, self.ch))

    def test_dialog_replies_carry_the_active_flag(self):
        """Every reply row carries `active`, so the driver filters on a field
        the protocol provides instead of defaulting a missing key to true."""
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        W.wait_until(self.ch, W.phase_is("gameplay"), 5.0, poll=0.01)
        self.ch.lua("kp.as(pc, function() nwscript.call(\"ActionStartConversation\",x, '') end)")
        d = self.ch.request("dialog")
        self.assertTrue(all("active" in r for r in d["replies"]))
        self.assertEqual([r["index"] for r in d["replies"] if r["active"]], [0, 2])


class TestOracle(Base):
    def test_hang(self):
        self.game.freeze = True
        wd = Watchdog(self.session, self.ch, hang_seconds=0.3)
        with self.assertRaises(OracleTrip) as cm:
            W.wait_until(self.ch, W.phase_is("gameplay"), 3.0, poll=0.05, watchdog=wd)
        v = cm.exception.verdict
        self.assertEqual(v.kind, "hang")
        self.assertIn("#0 fake frame", v.stack_dump)
        self.assertEqual(self.session.dumps, 1)

    def test_crash_process_gone(self):
        wd = Watchdog(self.session, self.ch)
        self.session.alive = False
        v = wd.check(self.ch.state())
        self.assertEqual(v.kind, "crash")

    def test_crash_from_wine_stderr_and_refusal(self):
        wd = Watchdog(self.session, self.ch)
        self.session.stderr = "wine: Unhandled page fault on read access to 00000000 at address 00401000\n"
        v = wd.check(self.ch.state())
        self.assertEqual(v.kind, "crash")
        self.assertIn("Unhandled page fault", v.reason)
        wd2 = Watchdog(self.session, self.ch)
        self.session.rtlog = "[12:00:00] refusing to install: PlaintextMismatch\n"
        v = wd2.check(None)
        self.assertEqual(v.kind, "refusal")
        wd3 = Watchdog(self.session, self.ch)
        self.session.rtlog = 'fault in hook body "vm.run_script": address 0x0, pc 0x0, code 0xc0000005\n'
        self.assertEqual(wd3.check(None).kind, "crash")

    def test_softlock_only_while_waiting_on_progress(self):
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        W.wait_until(self.ch, W.phase_is("gameplay"), 5.0, poll=0.01)
        self.ch.lua("nwscript.call(\"SetGlobalNumber\",'X', 1)")
        self.game.pin_fingerprint = True
        wd = Watchdog(self.session, self.ch, stagnation_seconds=0.3)
        # Not a progress wait: no softlock, only the ceiling.
        with self.assertRaises(W.WaitTimeout):
            W.wait_until(self.ch, W.module_is("end_m01ab"), 0.6, poll=0.05, watchdog=wd)
        with self.assertRaises(OracleTrip) as cm:
            W.wait_until(self.ch, W.module_is("end_m01ab"), 3.0, poll=0.05, watchdog=wd,
                         progress=True)
        v = cm.exception.verdict
        self.assertEqual(v.kind, "softlock")
        self.assertTrue(v.events)
        self.assertEqual(v.state["module"], "end_m01aa")
        self.assertEqual(v.detail["fingerprint"][0], "end_m01aa")

    def test_fingerprint_quantises_position(self):
        a = {"module": "m", "pc": {"x": 1.01, "y": 2.2, "z": 0}, "globals_hash": "h"}
        b = {"module": "m", "pc": {"x": 1.24, "y": 2.2, "z": 0}, "globals_hash": "h"}
        c = {"module": "m", "pc": {"x": 1.8, "y": 2.2, "z": 0}, "globals_hash": "h"}
        self.assertEqual(fingerprint(a), fingerprint(b))
        self.assertNotEqual(fingerprint(a), fingerprint(c))

    def test_load_stuck(self):
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        self.game.load_polls_left = 10 ** 6
        self.game.pin_fingerprint = True
        wd = Watchdog(self.session, self.ch, load_seconds=0.3)
        with self.assertRaises(OracleTrip) as cm:
            W.wait_until(self.ch, W.phase_is("gameplay"), 3.0, poll=0.05, watchdog=wd)
        self.assertEqual(cm.exception.verdict.kind, "load_stuck")

    def test_loading_server_tick_stall_trips_before_load_detail_ceiling(self):
        """A responsive channel cannot hide a stopped server MainLoop behind
        a 300s phase timeout.  Client frames are intentionally not the signal:
        they can pause in the nested loading loop."""
        self.ch.request("load_save", dir="000001 - AUTOSAVE")
        self.game.load_polls_left = 10 ** 6
        self.game.freeze_all = True
        wd = Watchdog(self.session, self.ch, load_seconds=30.0, load_tick_seconds=0.3)
        with self.assertRaises(OracleTrip) as cm:
            W.wait_until(self.ch, W.phase_is("gameplay"), 3.0, poll=0.05, watchdog=wd)
        v = cm.exception.verdict
        self.assertEqual(v.kind, "load_stuck")
        self.assertIn("server_tick", v.reason)
        self.assertEqual(v.detail["server_tick"], 1)

    def test_a_silent_load_is_given_the_load_ceiling(self):
        """A frame during a load runs 8 to 30 seconds under llvmpipe, so the
        client loop does not return and the channel says nothing. That is what
        a load looks like from outside, not a hang: the load ceiling governs
        it, and load_stuck is the verdict that can still trip."""
        wd = Watchdog(self.session, self.ch, hang_seconds=0.2, load_seconds=30.0)
        wd.check({"phase": "loading", "client_tick": 7})
        self.assertIsNone(wd.note_unresponsive())
        time.sleep(0.25)
        self.assertIsNone(wd.note_unresponsive())
        # The same silence once the game is out of the load is a hang again.
        wd.check({"phase": "gameplay", "client_tick": 8})
        self.assertIsNone(wd.note_unresponsive())
        time.sleep(0.25)
        self.assertEqual(wd.note_unresponsive().kind, "hang")

    def test_a_still_tick_during_a_load_is_not_a_hang(self):
        wd = Watchdog(self.session, self.ch, hang_seconds=0.2, load_seconds=30.0)
        self.assertIsNone(wd.check({"phase": "loading", "client_tick": 7}))
        time.sleep(0.25)
        self.assertIsNone(wd.check({"phase": "loading", "client_tick": 7}))
        self.assertEqual(self.session.dumps, 0)
        # Out of the load, a tick that stays put is the hang it always was.
        wd2 = Watchdog(self.session, self.ch, hang_seconds=0.2, load_seconds=30.0)
        self.assertIsNone(wd2.check({"phase": "gameplay", "client_tick": 7}))
        time.sleep(0.25)
        self.assertEqual(wd2.check({"phase": "gameplay", "client_tick": 7}).kind, "hang")

    def test_unresponsive_channel_becomes_hang(self):
        wd = Watchdog(self.session, self.ch, hang_seconds=0.2)
        self.assertIsNone(wd.note_unresponsive())
        time.sleep(0.25)
        v = wd.note_unresponsive()
        self.assertEqual(v.kind, "hang")


class TestScenario(Base):
    SPEC = '''
name = "k1 endar spire: events and dialog"
target = "k1"
[[step]]
do = "load_checkpoint"; name = "endar_start"
[[step]]
wait = "phase"; equals = "gameplay"; timeout = 300
[[step]]
expect_events = ["OnModuleLoad", "OnAreaEnter"]
[[step]]
do = "warp"; module = "end_m01aa"
[[step]]
wait = "module"; equals = "end_m01aa"
[[step]]
do = "reply"; pick = "first_active"
[[step]]
wait = "global"; name = "END_TRASK_TALK"; equals = 1
[[step]]
screenshot = true
'''

    def test_parse_spec_example(self):
        sc = Scenario.parse(self.SPEC)
        self.assertEqual(sc.target, "k1")
        self.assertEqual(sc.settings["game_speed"], 16.0)
        self.assertEqual(len(sc.steps), 8)
        self.assertEqual([s.kind for s in sc.steps],
                         ["do", "wait", "expect_events", "do", "wait", "do", "wait", "screenshot"])
        self.assertIn("load_checkpoint", sc.steps[0].describe())

    def test_game_speed_setting_is_typed_and_bounded(self):
        base = 'name="speed"\ntarget="k1"\n%s\n[[step]]\ndo="sleep"\nseconds=0\n'
        self.assertEqual(Scenario.parse(base % '[settings]\ngame_speed=4').settings["game_speed"], 4.0)
        for value in ('0', '-1', '16.01', '"fast"', 'true', 'nan'):
            with self.subTest(value=value), self.assertRaises(ScenarioError):
                Scenario.parse(base % f'[settings]\ngame_speed={value}')

    def test_runner_applies_fastest_speed_before_first_step_and_reports_it(self):
        text = '''
name = "speed policy"
target = "k1"
[[step]]
do = "sleep"; seconds = 0
'''
        r, _ = self._runner(text)
        before = len(self.game.requests)
        rep = r.run()
        self.assertTrue(rep.ok)
        requests = self.game.requests[before:]
        self.assertEqual(requests[0], "speed")
        self.assertEqual(requests[1:], ["events"])
        self.assertEqual(rep.execution, {
            "game_speed_requested": 16.0,
            "game_speed_effective": 16.0,
        })

    def test_retail_speed_opt_out_needs_no_speed_binding(self):
        text = '''
name = "retail policy"
target = "k1"
[settings]
game_speed = 1.0
[[step]]
do = "sleep"; seconds = 0
'''
        r, _ = self._runner(text)
        before = len(self.game.requests)
        rep = r.run()
        self.assertTrue(rep.ok)
        self.assertEqual(self.game.requests[before:], ["events"])
        self.assertEqual(rep.execution["game_speed_effective"], 1.0)

    def test_semicolon_shorthand(self):
        from kpharness.scenario import expand_semicolons
        text = 'a = "x; y"; b = 1 # c; d\n[[step]]\ncode = """\nx; y\n"""\n'
        out = expand_semicolons(text)
        self.assertIn('a = "x; y"\nb = 1 # c; d', out)
        self.assertIn('code = """\nx; y\n"""', out)

    def test_parse_errors(self):
        with self.assertRaises(ScenarioError):
            Scenario.parse('name = "x"\n[[step]]\ndo = "quit"\n')      # no target
        with self.assertRaises(ScenarioError):
            Scenario.parse('name = "x"\ntarget = "k1"\n')              # no steps
        with self.assertRaises(ScenarioError):
            Scenario.parse('target = "k1"\n[[step]]\nlabel = "?"\n')   # step without action

    def test_shipped_scenarios_parse(self):
        d = ROOT / "scripts" / "harness" / "scenarios"
        from kpharness.scenario import list_scenarios, find_scenario
        paths = sorted(d.rglob("*.toml"))
        self.assertEqual(list_scenarios(), paths)
        self.assertEqual(len([p for p in paths if p.parent.name == "cursed"]), 10)
        for p in paths:
            self.assertEqual(find_scenario(str(p)), p)
            self.assertEqual(find_scenario(p.relative_to(d).with_suffix("").as_posix()), p)
            sc = Scenario.load(p)
            self.assertIn(sc.target, T.names())
            for s in sc.steps:
                s.kind

    def _runner(self, text, **settings):
        sc = Scenario.parse(text)
        sc.settings.update(settings)
        cps = Checkpoints(T.get("k1"), self.save_dir, self.tmp / "checkpoints")
        logs = []
        r = ScenarioRunner(sc, self.session, self.ch, log=logs.append, checkpoints=cps)
        r.watchdog.hang_seconds = 5.0
        return r, logs

    def test_runner_end_to_end_pass(self):
        text = '''
name = "offline"
target = "k1"
[settings]
shot_interval = 0
[[step]]
do = "load_save"; dir = "000001 - AUTOSAVE"
[[step]]
do = "sleep"; seconds = 0
[[step]]
wait = "phase"; equals = "gameplay"; timeout = 5
[[step]]
expect_events = ["OnModuleLoad", "OnAreaEnter", {event = "OnRunScript", script = "k_pend_*"}]; timeout = 2
[[step]]
do = "warp"; module = "end_m01ab"
[[step]]
wait = "module"; equals = "end_m01ab"; timeout = 5
[[step]]
do = "lua"; code = "return nwscript.call('GetModuleName')"
[[step]]
do = "new_game"
[[step]]
do = "fixed_step"; hz = 30; expect_error = "unsupported"
[[step]]
do = "set_global"; name = "END_TRASK_TALK"; value = 1
[[step]]
wait = "global"; name = "END_TRASK_TALK"; equals = 1; timeout = 2
[[step]]
do = "lua"; code = "kp.as(nwscript.call('GetFirstPC'), function() nwscript.call('ActionStartConversation',nwscript.call('GetObjectByTag','end_trask',0), '') end)"
[[step]]
wait = "phase"; equals = "dialog"; timeout = 2
[[step]]
wait = "dialog"; timeout = 2
[[step]]
screenshot = true; expect_screen = "dialog"
[[step]]
do = "reply"; pick = "first_active"
[[step]]
do = "dialog_abort"
[[step]]
do = "save"; slot = 7; name = "kp"; checkpoint = "after_dialog"; timeout = 2
'''
        # The fake `save` command is unknown: prove the unsupported/skip path
        # is distinct from a real failure by teaching the fake about it.
        orig = self.game.handle

        def handle(req, conn):
            if req.get("cmd") == "save":
                folder = self.save_dir / f"{int(req['slot']):06d} - {req['name']}"
                folder.mkdir(exist_ok=True)
                (folder / "SAVEGAME.sav").write_bytes(b"x")
                return {"id": req["id"], "ok": True, "result": {"started": True}}
            return orig(req, conn)
        self.game.handle = handle
        real_observe = World.observe_world
        World.observe_world = lambda *_a, **_kw: _world(locked=False, open_=False)
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))

        r, logs = self._runner(text, default_timeout=2.0, load_timeout=5.0)
        rep = r.run()
        by = {s.index: s for s in rep.steps}
        self.assertEqual(by[8].status, "skipped", by[8].detail)      # new_game unsupported
        self.assertEqual(by[9].status, "ok")                          # expected unsupported
        self.assertEqual(by[15].status, "ok")
        self.assertIsNotNone(by[15].screen)
        self.assertTrue(rep.ok, json.dumps(rep.to_dict(), indent=1, default=str)[:3000])
        self.assertTrue((self.run_dir / "report.json").is_file())
        self.assertTrue((self.tmp / "checkpoints" / "after_dialog" / "meta.json").is_file())
        shots = list((self.run_dir / "shots").iterdir())
        self.assertTrue(any(p.suffix in (".png", ".ppm") for p in shots))

    def test_runner_chargen_select_class(self):
        text = '''
name = "chargen"
target = "k1"
[[step]]
do = "new_game"
[[step]]
wait = "chargen_stage"; equals = "class"; timeout = 2
[[step]]
do = "chargen_select_class"; index = 1; timeout = 2
[[step]]
wait = "chargen_stage"; equals = "route"; timeout = 2
'''
        orig = self.game.handle
        def handle(req, conn):
            if req.get("cmd") == "new_game":
                self.game.chargen_stage = "class"
                return {"id": req["id"], "ok": True, "result": {}}
            if req.get("cmd") == "chargen_select_class":
                self.assertEqual(req.get("index"), 1)
                self.game.chargen_stage = "route"
                return {"id": req["id"], "ok": True, "result": {}}
            return orig(req, conn)
        self.game.handle = handle
        report = self._runner(text, default_timeout=2.0)[0].run()
        self.assertTrue(report.ok, [s.detail for s in report.steps])

    def test_runner_take_all_container_uses_explicit_native_verb(self):
        text = '''
name = "take all container"
target = "k1"
[settings]
game_speed = 1.0
[[step]]
do = "take_all_container"
'''
        before = len(self.game.requests)
        report = self._runner(text, default_timeout=2.0)[0].run()
        self.assertTrue(report.ok, [s.detail for s in report.steps])
        self.assertEqual(self.game.requests[before:], ["events", "take_all_container"])

    def test_runner_accept_party_selection_uses_explicit_native_verb(self):
        text = '''
name = "accept party selection"
target = "k1"
[settings]
game_speed = 1.0
[[step]]
do = "accept_party_selection"
'''
        before = len(self.game.requests)
        report = self._runner(text, default_timeout=2.0)[0].run()
        self.assertTrue(report.ok, [s.detail for s in report.steps])
        self.assertEqual(self.game.requests[before:], ["events", "accept_party_selection"])

    def test_runner_auto_levelup_uses_deferred_native_verb(self):
        text = '''
name = "auto level"
target = "k1"
[settings]
game_speed = 1.0
[[step]]
do = "auto_levelup"
'''
        before = len(self.game.requests)
        report = self._runner(text, default_timeout=2.0)[0].run()
        self.assertTrue(report.ok, [s.detail for s in report.steps])
        self.assertEqual(self.game.requests[before:], ["events", "auto_levelup"])

    def test_runner_set_party_leader_uses_native_index(self):
        text = '''
name = "set party leader"
target = "k1"
[settings]
game_speed = 1.0
[[step]]
do = "set_party_leader"
index = 1
'''
        before = len(self.game.requests)
        report = self._runner(text, default_timeout=2.0)[0].run()
        self.assertTrue(report.ok, [s.detail for s in report.steps])
        self.assertEqual(self.game.requests[before:], ["events", "set_party_leader"])

    def test_runner_assert_lua_is_typed_and_does_not_fake_game_semantics(self):
        ok = '''
name = "typed lua assertion"
target = "k1"
[settings]
game_speed = 1.0
[[step]]
do = "assert_lua"
code = "return 7"
equals = 7
'''
        original = self.game.lua

        def one_value(code):
            if code == "return 7":
                return {"ok": True, "result": {"values": [7]}}
            return original(code)

        self.game.lua = one_value
        report = self._runner(ok, default_timeout=2.0)[0].run()
        self.assertTrue(report.ok, [s.detail for s in report.steps])

        wrong_type = ok.replace("equals = 7", "equals = true")
        report = self._runner(wrong_type, default_timeout=2.0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("assert_lua mismatch", report.steps[0].detail)

        self.game.lua = lambda code: {"ok": True, "result": {"values": [7, 8]}}
        report = self._runner(ok, default_timeout=2.0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("exactly one Lua return value", report.steps[0].detail)

    def test_runner_expected_softlock_then_continue(self):
        text = '''
name = "softlock"
target = "k1"
[settings]
stagnation_seconds = 0.3
[[step]]
do = "load_save"; dir = "000001 - AUTOSAVE"
[[step]]
wait = "phase"; equals = "gameplay"; timeout = 5
[[step]]
do = "lua"; code = "pin"
[[step]]
wait = "module"; equals = "end_m01ab"; timeout = 5; expect_verdict = "softlock"
[[step]]
do = "warp"; module = "end_m01ab"
[[step]]
wait = "module"; equals = "end_m01ab"; timeout = 5
'''
        orig = self.game.lua

        def lua(code):
            if code == "pin":
                self.game.pin_fingerprint = True
                return {"ok": True, "result": None}
            return orig(code)
        self.game.lua = lua
        r, logs = self._runner(text, load_timeout=5.0, shot_interval=0)
        rep = r.run()
        statuses = [s.status for s in rep.steps]
        self.assertEqual(statuses, ["ok", "ok", "ok", "expected_failure", "ok", "ok"], statuses)
        self.assertEqual(rep.steps[3].verdict["kind"], "softlock")
        self.assertTrue(rep.ok)

    def test_runner_failure_stops_and_reports(self):
        text = '''
name = "fail"
target = "k1"
[[step]]
do = "warp"; module = "end_m01ab"
[[step]]
do = "quit"
'''
        r, logs = self._runner(text, shot_interval=0)
        rep = r.run()
        self.assertFalse(rep.ok)
        self.assertEqual(len(rep.steps), 1)
        self.assertEqual(rep.steps[0].status, "failed")
        self.assertIn("warp needs gameplay", rep.steps[0].detail)
        self.assertEqual(json.loads((self.run_dir / "report.json").read_text())["ok"], False)

    def test_runner_hang_is_fatal(self):
        text = '''
name = "hang"
target = "k1"
[[step]]
do = "load_save"; dir = "000001 - AUTOSAVE"
[[step]]
wait = "phase"; equals = "gameplay"; timeout = 5
[[step]]
do = "lua"; code = "return 1"
'''
        r, logs = self._runner(text, hang_seconds=0.3, shot_interval=0, load_timeout=5.0)
        r.watchdog.hang_seconds = 0.3
        self.game.freeze = True
        rep = r.run()
        self.assertFalse(rep.ok)
        self.assertEqual(rep.verdict["kind"], "hang")

    def test_walk_dialog(self):
        text = '''
name = "walk"
target = "k1"
[[step]]
do = "load_save"; dir = "000001 - AUTOSAVE"
[[step]]
wait = "phase"; equals = "gameplay"; timeout = 5
[[step]]
do = "walk_dialog"; save = "000001 - AUTOSAVE"; start = "kp.as(pc, function() nwscript.call('ActionStartConversation',t, '') end)"; timeout = 3
'''
        r, logs = self._runner(text, load_timeout=5.0, shot_interval=0)
        rep = r.run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertIn("walked 2 replies", rep.steps[2].detail)
        self.assertIn("ended", rep.steps[2].detail)

    def test_advance_dialog_survives_refused_dialog_skip(self):
        text = '''
name = "skip refused"
target = "k1"
[settings]
dialog_grace = 0
[[step]]
do = "advance_dialog"; until = "gameplay"; timeout = 16
'''
        self.game.phase, self.game.module, self.game.server_tick = "dialog", "end_m01aa", 1
        self.game.dialog = {"active": True, "entry": 3, "reply": -1, "text": "strref:-1",
                            "replies": [{"index": 2, "link": 2, "text": "Let's go.", "active": True}],
                            "waiting_for_player": False, "waiting_on_sound": True}
        # A conversation still initializing refuses the skip; the ladder must
        # keep polling rather than fail the step on the first refusal.
        self.game.error_once_cmd = ("dialog_skip", "dialog_skip: dialog owner has no game object")
        r, logs = self._runner(text, shot_interval=0)
        rep = r.run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertIn("after 1 picks", rep.steps[0].detail)
        self.assertEqual(self.game.requests.count("dialog_skip"), 2)
        self.assertEqual(self.game.requests.count("reply"), 1)
        self.assertTrue(any("dialog_skip refused" in line for line in logs), logs)

    def _script_probe_loop(self, probes, *, probe_marker, issue_marker, pause_first=False):
        """Fake the engine side of a probe/issue verb (clear_room, move_to).

        Probe chunks (containing ``probe_marker``) answer from ``probes`` in
        order (the last one repeats), issue chunks (containing
        ``issue_marker``) are recorded and returned, and autopause is shown
        on the first state read until clear_auto_pause is requested.
        """
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        self.game.auto_pause = 1 if pause_first else 0
        queue = list(probes)
        orig_lua = self.game.lua
        issued = []

        def lua(code):
            if issue_marker in code:
                self.game.lua_codes.append(code)
                issued.append(code)
                return {"ok": True, "result": {"values": [{"issued": 1}]}}
            if probe_marker in code:
                self.game.lua_codes.append(code)
                probe = queue.pop(0) if len(queue) > 1 else queue[0]
                return {"ok": True, "result": {"values": [probe]}}
            return orig_lua(code)
        self.game.lua = lua
        real_state = self.ch.state

        def state():
            s = real_state()
            s["phase_detail"]["pause"] = self.game.auto_pause
            if self.game.auto_pause:
                s["phase"] = "paused"
            return s
        self.ch.state = state
        self.addCleanup(lambda: setattr(self.ch, "state", real_state))
        return issued

    def _script_clear_room(self, probes, pause_first=False):
        return self._script_probe_loop(probes, probe_marker="GetFirstObjectInArea",
                                       issue_marker="ActionAttack", pause_first=pause_first)

    def _script_move_to(self, probes, pause_first=False):
        return self._script_probe_loop(probes, probe_marker="GetCurrentAction",
                                       issue_marker="ActionMoveTo", pause_first=pause_first)

    def _script_door(self, door_id, opens_on_its_own):
        """Fake a scripted-only door: the self-command chunk returns its id,
        the GetIsOpen probe answers False until either the engine (``opens_on_its_own``)
        or a door_commit_open request has committed the open state."""
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        orig_lua = self.game.lua

        def lua(code):
            self.game.lua_codes.append(code)
            if "ActionOpenDoor" in code or "return d" in code:
                return {"ok": True, "result": {"values": [door_id]}}
            if "GetIsOpen" in code:
                return {"ok": True, "result": {"values": [opens_on_its_own or self.game.door_committed]}}
            return orig_lua(code)
        self.game.lua = lua

    def test_scripted_door_open_commits_stuck_door_once(self):
        text = '''
name = "stuck door"
target = "k1"
[[step]]
do = "scripted_door_open"; tag = "end_door05"; timeout = 10
'''
        self._script_door(0x80000010, opens_on_its_own=False)
        runner = self._runner(text, shot_interval=0)[0]
        runner._DOOR_COMMIT_AFTER = 0.4   # the live 2.5 s grace, shortened
        rep = runner.run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertEqual(rep.steps[0].detail, "scripted_door_open end_door05 open (committed)")
        self.assertEqual(len(self.game.door_requests), 1, self.game.door_requests)
        request = self.game.door_requests[0]
        self.assertEqual(request["cmd"], "door_commit_open")
        self.assertEqual(request["door"], 0x80000010)
        self.assertEqual(set(request) - {"id"}, {"cmd", "door"})
        # The self-command went first and at least one probe saw the door
        # still closed before the commit was issued.
        self.assertIn("kp.as(d,function() nwscript.call(\"ActionOpenDoor\",d) end)", self.game.lua_codes[0])
        self.assertGreaterEqual(sum(1 for c in self.game.lua_codes if "GetIsOpen" in c), 2)

    def test_scripted_door_open_does_not_commit_a_door_that_opens(self):
        text = '''
name = "door opens"
target = "k1"
[[step]]
do = "scripted_door_open"; tag = "end_door02"; timeout = 10
'''
        self._script_door(0x80000011, opens_on_its_own=True)
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertEqual(rep.steps[0].detail, "scripted_door_open end_door02 open")
        self.assertNotIn("door_commit_open", self.game.requests)

    def test_door_commit_open_verb_resolves_tag_and_sends_exact_id(self):
        text = '''
name = "commit by tag"
target = "k1"
[[step]]
do = "door_commit_open"; tag = "end_door04"
[[step]]
do = "door_commit_open"; door = 74
'''
        self._script_door(0x80000012, opens_on_its_own=False)
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertEqual(rep.steps[0].detail, "door_commit_open 2147483666 ok")
        self.assertEqual(rep.steps[1].detail, "door_commit_open 74 ok")
        self.assertEqual([r["door"] for r in self.game.door_requests], [0x80000012, 74])
        self.assertIn('nwscript.call("GetObjectByTag","end_door04",0)', self.game.lua_codes[0])

    def test_clear_room_clears_autopause_and_ends_on_global(self):
        text = '''
name = "clear room"
target = "k1"
[[step]]
do = "clear_room"; radius = 30; until_global = "END_ROOM3_DEAD"; until_value = 2; grace = 1; timeout = 10
'''
        two = [{"id": 11, "tag": "end_sith2", "hp": 20, "dist": 9.0},
               {"id": 10, "tag": "end_sith1", "hp": 20, "dist": 5.0}]
        attacks = self._script_clear_room([
            {"hostiles": two, "global": 0, "act": 65534},        # idle: attack the nearest (10)
            {"hostiles": two, "global": 0, "act": 39},           # mid combat round: no re-issue
            {"hostiles": two[:1], "global": 1, "act": 65534},    # 10 died: retarget 11
            {"hostiles": [], "global": 2, "act": 65534},         # counter reached
        ], pause_first=True)
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        detail = rep.steps[0].detail
        self.assertIn("clear_room: 2 hostiles down in", detail)
        self.assertIn("END_ROOM3_DEAD=2", detail)
        self.assertIn("clear_auto_pause", self.game.requests)
        self.assertEqual(len(attacks), 2, attacks)
        self.assertIn("local t=10;", attacks[0])
        self.assertIn("local t=11;", attacks[1])
        self.assertIn("kp.as(pc,function() nwscript.call(\"ClearAllActions\"); nwscript.call(\"ActionAttack\",t,0) end)", attacks[0])
        probe = next(c for c in self.game.lua_codes if "GetFirstObjectInArea" in c)
        self.assertIn('nwscript.call("GetGlobalNumber","END_ROOM3_DEAD")', probe)
        self.assertIn("d<=30.0", probe)
        self.assertIn('nwscript.call("GetCurrentAction",pc)', probe)

    def test_clear_room_fails_after_grace_when_global_never_reached(self):
        text = '''
name = "clear room grace"
target = "k1"
[[step]]
do = "clear_room"; until_global = "END_ROOM3_DEAD"; grace = 0.6; timeout = 10
'''
        attacks = self._script_clear_room([{"hostiles": [], "global": 0, "act": 65534}])
        t0 = time.monotonic()
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(rep.ok)
        self.assertLess(time.monotonic() - t0, 5.0)     # grace, not the 10s ceiling
        self.assertIn("no hostile within 40 for 0.6s", rep.steps[0].detail)
        self.assertIn("END_ROOM3_DEAD=0 < 1", rep.steps[0].detail)
        self.assertEqual(attacks, [])

    def test_clear_room_without_global_ends_when_no_hostile_and_keeps_round(self):
        text = '''
name = "clear room radius"
target = "k1"
[[step]]
do = "clear_room"; timeout = 10
'''
        one = [{"id": 10, "tag": "end_sith1", "hp": 20, "dist": 5.0}]
        attacks = self._script_clear_room([
            {"hostiles": one, "global": -1, "act": 65534},
            {"hostiles": one, "global": -1, "act": 39},
            {"hostiles": one, "global": -1, "act": 39},
            {"hostiles": [], "global": -1, "act": 65534},
        ])
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertIn("clear_room: 1 hostiles down in", rep.steps[0].detail)
        self.assertNotIn("=", rep.steps[0].detail)
        self.assertEqual(len(attacks), 1, attacks)
        self.assertNotIn("clear_auto_pause", self.game.requests)
        probe = next(c for c in self.game.lua_codes if "GetFirstObjectInArea" in c)
        self.assertNotIn("GetGlobalNumber", probe)
        self.assertIn("d<=40.0", probe)

    def test_move_to_tag_ends_when_within_range(self):
        text = '''
name = "move to tag"
target = "k1"
[[step]]
do = "move_to"; tag = "end_door10_cut2"; timeout = 10
'''
        moves = self._script_move_to([
            {"dist": 9.0, "act": 65534, "x": 1.0, "y": 1.0},    # idle: issue the walk
            {"dist": 6.0, "act": 0, "x": 2.0, "y": 1.0},        # moving
            {"dist": 3.0, "act": 0, "x": 3.0, "y": 1.0},
            {"dist": 1.6, "act": 0, "x": 4.0, "y": 1.0},        # <= 1.5 + 0.5
        ])
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertIn("move_to end_door10_cut2: dist 1.6 in", rep.steps[0].detail)
        self.assertEqual(len(moves), 1, moves)
        self.assertIn('nwscript.call(\"GetObjectByTag\","end_door10_cut2",0)', moves[0])
        self.assertIn("kp.as(pc,function() nwscript.call(\"ClearAllActions\"); nwscript.call(\"ActionMoveToObject\",t,1,1.5) end)",
                      moves[0])
        probe = next(c for c in self.game.lua_codes if "GetCurrentAction" in c)
        self.assertIn("nwscript.call(\"GetDistanceBetween\",pc,t)", probe)
        self.assertNotIn("clear_auto_pause", self.game.requests)

    def test_move_to_blocked_reissues_once_then_fails_on_no_progress(self):
        text = '''
name = "move to blocked"
target = "k1"
[[step]]
do = "move_to"; tag = "end_door10_cut2"; stall = 0.5; stall_ticks = 0; timeout = 10
'''
        # A closed door: the move action stays queued but the distance never improves.
        moves = self._script_move_to([{"dist": 18.0, "act": 0, "x": 1.0, "y": 1.0}])
        t0 = time.monotonic()
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(rep.ok)
        self.assertLess(time.monotonic() - t0, 5.0)     # two stalls, not the 10s ceiling
        self.assertIn("move_to end_door10_cut2: no progress for 0.5s at dist 18.0 (blocked?)",
                      rep.steps[0].detail)
        self.assertEqual(len(moves), 2, moves)

    def test_move_to_position_clears_autopause(self):
        text = '''
name = "move to position"
target = "k1"
[[step]]
do = "move_to"; position = [10.0, 20.0, -1.2]; run = false; timeout = 10
'''
        moves = self._script_move_to([
            {"dist": 4.0, "act": 65534, "x": 1.0, "y": 1.0},
            {"dist": 1.0, "act": 0, "x": 9.5, "y": 20.0},       # <= 0.75 + 0.5
        ], pause_first=True)
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertIn("move_to (10.0,20.0,-1.2): dist 1.0 in", rep.steps[0].detail)
        self.assertIn("clear_auto_pause", self.game.requests)
        self.assertEqual(len(moves), 1, moves)
        self.assertIn("nwscript.call(\"ActionMoveToLocation\",nwscript.call(\"Location\",nwscript.call(\"Vector\",10.0,20.0,-1.2),0.0),0)",
                      moves[0])
        probe = next(c for c in self.game.lua_codes if "GetCurrentAction" in c)
        self.assertIn("nwscript.call(\"GetPosition\",pc)", probe)
        self.assertIn("p.x-(10.0),p.y-(20.0),p.z-(-1.2)", probe)
        self.assertIn("math.sqrt(dx*dx+dy*dy+dz*dz)", probe)
        self.assertNotIn("GetObjectByTag", probe)

    def _script_use_item(self, hp_probes, *, item_id=0):
        """Fake the engine side of use_item.

        Hit-point probe chunks (``GetCurrentHitPoints``) answer from
        ``hp_probes`` in order (the last one repeats), the inventory walk
        (``GetFirstItemInInventory``) resolves any tag to ``item_id`` (0 =
        not carried), and the raw ``use_item`` request -- unknown to the
        plain fake -- is answered and its wire dict recorded.
        """
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        queue = list(hp_probes)
        orig_lua = self.game.lua
        orig_handle = self.game.handle
        used = []

        def lua(code):
            if "GetCurrentHitPoints" in code:
                self.game.lua_codes.append(code)
                probe = queue.pop(0) if len(queue) > 1 else queue[0]
                return {"ok": True, "result": {"values": [probe]}}
            if "GetFirstItemInInventory" in code:
                self.game.lua_codes.append(code)
                return {"ok": True, "result": {"values": [item_id]}}
            return orig_lua(code)

        def handle(req, conn):
            if req.get("cmd") == "use_item":
                self.game.requests.append("use_item")
                used.append(dict(req))
                return {"id": req["id"], "ok": True, "result": {"used": True}}
            return orig_handle(req, conn)
        self.game.lua = lua
        self.game.handle = handle
        return used

    def test_use_item_skipped_when_hp_not_below_threshold(self):
        text = '''
name = "use item skip"
target = "k1"
[[step]]
do = "use_item"; tag = "g_i_medeqpmnt01"; if_hp_below = 0.5; timeout = 5
'''
        used = self._script_use_item([{"hp": 24, "max": 24}], item_id=0x80000123)
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertEqual(rep.steps[0].detail, "use_item skipped: hp 24/24 is not below 0.5")
        self.assertEqual(used, [])
        self.assertNotIn("use_item", self.game.requests)
        # The gate is decided from the single readback: no inventory walk either.
        self.assertFalse(any("GetFirstItemInInventory" in c for c in self.game.lua_codes))
        self.assertEqual(sum("GetCurrentHitPoints" in c for c in self.game.lua_codes), 1)

    def test_use_item_skipped_at_exact_threshold(self):
        text = '''
name = "use item boundary"
target = "k1"
[[step]]
do = "use_item"; tag = "g_i_medeqpmnt01"; if_hp_below = 0.5; timeout = 5
'''
        # 12/24 is not *below* half: the gate is >=, so a route that heals at
        # "half health" does not burn a medpac when sitting exactly on it.
        used = self._script_use_item([{"hp": 12, "max": 24}], item_id=0x80000123)
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertIn("use_item skipped: hp 12/24", rep.steps[0].detail)
        self.assertEqual(used, [])

    def test_use_item_resolves_tag_sends_id_and_waits_for_hp_rise(self):
        text = '''
name = "use item"
target = "k1"
[[step]]
do = "use_item"; tag = "g_i_medeqpmnt01"; if_hp_below = 0.5; timeout = 5
'''
        used = self._script_use_item([
            {"hp": 1, "max": 24},      # gate readback: hurt, so proceed
            {"hp": 1, "max": 24},      # first poll: heal not applied yet
            {"hp": 6, "max": 24},      # second poll: risen
        ], item_id=0x80000123)
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertEqual(rep.steps[0].detail, "use_item g_i_medeqpmnt01: hp 1 -> 6/24")
        self.assertEqual(len(used), 1, used)
        self.assertEqual(used[0]["item"], 0x80000123)
        self.assertNotIn("target", used[0])
        walk = next(c for c in self.game.lua_codes if "GetFirstItemInInventory" in c)
        self.assertIn('local want="g_i_medeqpmnt01"', walk)
        self.assertIn("nwscript.call(\"GetNextItemInInventory\",pc)", walk)
        # Readback, then resolve, then the request; the rise took two polls.
        first_hp = next(i for i, c in enumerate(self.game.lua_codes) if "GetCurrentHitPoints" in c)
        self.assertLess(first_hp, self.game.lua_codes.index(walk))
        self.assertEqual(sum("GetCurrentHitPoints" in c for c in self.game.lua_codes), 3)

    def test_use_item_by_id_skips_inventory_walk(self):
        text = '''
name = "use item id"
target = "k1"
[[step]]
do = "use_item"; item = 2147484067; timeout = 5
'''
        used = self._script_use_item([{"hp": 1, "max": 24}, {"hp": 24, "max": 24}])
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertEqual(rep.steps[0].detail, "use_item 2147484067: hp 1 -> 24/24")
        self.assertEqual([u["item"] for u in used], [2147484067])
        self.assertFalse(any("GetFirstItemInInventory" in c for c in self.game.lua_codes))

    def test_use_item_unknown_tag_fails_without_sending(self):
        text = '''
name = "use item missing"
target = "k1"
[[step]]
do = "use_item"; tag = "g_i_nope"; timeout = 5
'''
        used = self._script_use_item([{"hp": 1, "max": 24}], item_id=0)
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(rep.ok)
        self.assertEqual(rep.steps[0].status, "failed")
        self.assertIn("use_item: no inventory item tagged 'g_i_nope'", rep.steps[0].detail)
        self.assertEqual(used, [])
        self.assertNotIn("use_item", self.game.requests)

    def test_use_item_fails_when_hp_never_rises(self):
        text = '''
name = "use item stayed"
target = "k1"
[[step]]
do = "use_item"; tag = "g_i_medeqpmnt01"; timeout = 1
'''
        used = self._script_use_item([{"hp": 1, "max": 24}], item_id=0x80000123)
        t0 = time.monotonic()
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(rep.ok)
        self.assertLess(time.monotonic() - t0, 4.0)
        self.assertEqual(rep.steps[0].status, "failed")
        self.assertIn("use_item g_i_medeqpmnt01: hp stayed 1/24", rep.steps[0].detail)
        self.assertEqual(len(used), 1, used)       # sent once, never re-sent

    def test_run_script_with_tag_executes_on_that_object(self):
        text = '''
name = "run script tag"
target = "k1"
[[step]]
do = "run_script"; script = "k_pend_door20"; tag = "end_door08"; timeout = 5
'''
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertEqual(rep.steps[0].detail, "run_script k_pend_door20 on end_door08")
        sent = [r["code"] for r in self.game.lua_requests if "ExecuteScript" in r["code"]]
        self.assertEqual(len(sent), 1, sent)
        self.assertIn('nwscript.call(\"GetObjectByTag\","end_door08",0)', sent[0])
        self.assertIn('nwscript.call(\"ExecuteScript\","k_pend_door20",o)', sent[0])
        self.assertIn("error('no object tagged '..\"end_door08\")", sent[0])
        self.assertNotIn("GetArea", sent[0])

    def test_run_script_missing_tag_object_fails_step(self):
        text = '''
name = "run script missing"
target = "k1"
[[step]]
do = "run_script"; script = "k_pend_door20"; tag = "end_door99"; timeout = 5
'''
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        # The chunk errors in-engine when the tag resolves to nothing; the
        # channel refusal must fail the step rather than report "on end_door99".
        self.game.lua_fail_substring = "no object tagged"
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(rep.ok)
        self.assertEqual(rep.steps[0].status, "failed")
        self.assertNotIn("run_script k_pend_door20 on", rep.steps[0].detail)

    def test_run_script_area_and_pc_defaults(self):
        text = '''
name = "run script area"
target = "k1"
[[step]]
do = "run_script"; script = "k_pend_area01"; area = true; timeout = 5
[[step]]
do = "run_script"; script = "k_pend_pc01"; timeout = 5
'''
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        rep = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(rep.ok, [s.detail for s in rep.steps])
        self.assertEqual(rep.steps[0].detail, "run_script k_pend_area01 on area")
        self.assertEqual(rep.steps[1].detail, "run_script k_pend_pc01 on pc")
        sent = [r["code"] for r in self.game.lua_requests if "ExecuteScript" in r["code"]]
        self.assertEqual(len(sent), 2, sent)
        self.assertIn('nwscript.call(\"ExecuteScript\","k_pend_area01",nwscript.call(\"GetArea\",pc))', sent[0])
        self.assertNotIn("GetObjectByTag", sent[0])
        self.assertIn('nwscript.call(\"ExecuteScript\","k_pend_pc01",pc)', sent[1])
        self.assertNotIn("GetArea", sent[1])

    def test_door_transaction_uses_checked_instance_and_state_readback(self):
        text = '''
name = "door"
target = "k1"
[[step]]
do = "door_transaction"; module = "end_m01aa"; type = 8; tag = "end_door01"
position = [21.1225, 20.7130, -1.3158]; position_tolerance = 0.25; timeout = 2
destination = [20.32586733500163, 21.70310910542806, -1.275]; destination_tolerance = 0.75
walkmesh_approach_centroid = [19.914662679036457, 20.194860458374023, -1.274999976158142]
walkmesh_far_centroid = [20.32586733500163, 21.70310910542806, -1.275]
'''
        text += self.door_route_toml
        before = _world(locked=False, open_=False, action=2)
        after = _world(locked=False, open_=True, action=0, pc_position=(20.32586733500163, 21.70310910542806, -1.275))
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        real_observe, real_state = World.observe_world, self.ch.state
        snapshots = iter((before, before, after))
        World.observe_world = lambda *_a, **_kw: next(snapshots)
        def state():
            s = real_state()
            s["pc"] = {"id": 0x80000001, "x": 21.0, "y": 20.6, "z": -1.3}
            return s
        self.ch.state = state
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        self.addCleanup(lambda: setattr(self.ch, "state", real_state))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(report.ok, [s.detail for s in report.steps])
        self.assertIn("open/unlocked", report.steps[0].detail)
        emitted = "\n".join(self.game.lua_codes)
        self.assertIn("local door=2147483664", emitted)
        self.assertIn("door identity changed", emitted)
        self.assertIn("kp.as", emitted)
        self.assertIn("ActionMoveToObject", emitted)
        self.assertIn("ActionOpenDoor", emitted)
        self.assertIn("ActionMoveToLocation", emitted)

    def test_placeable_transaction_uses_checked_instance_and_open_readback(self):
        text = '''
name = "placeable"
target = "k1"
[[step]]
do = "placeable_transaction"; module = "end_m01aa"; type = 64; tag = "end_locker01"
position = [10.795940399169922, 21.870288848876953, -1.1049995422363281]
position_tolerance = 0.25; interaction_range = 1.0; pre_open = false; timeout = 2
'''
        before = _placeable_world(open_=False, action=2)
        arrived = _placeable_world(open_=False, action=0,
                                   pc_position=(10.9, 21.7, -1.105))
        after = _placeable_world(open_=True, action=0,
                                 pc_position=(10.9, 21.7, -1.105))
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        real_observe = World.observe_world
        snapshots = iter((before, arrived, after))
        def observe(*_a, **_kw):
            world = next(snapshots)
            if world is arrived:
                emitted = "\n".join(self.game.lua_codes)
                self.assertIn("ActionMoveToObject", emitted)
                self.assertNotIn("ActionInteractObject", emitted)
            return world
        World.observe_world = observe
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertTrue(report.ok, [s.detail for s in report.steps])
        self.assertIn("open", report.steps[0].detail)
        self.assertIn("interaction range 1", report.steps[0].detail)
        emitted = "\n".join(self.game.lua_codes)
        self.assertIn("local placeable=198", emitted)
        self.assertIn("placeable identity changed", emitted)
        self.assertIn("placeable position changed", emitted)
        self.assertIn("ActionMoveToObject", emitted)
        self.assertIn("ActionInteractObject", emitted)
        move_index = next(i for i, code in enumerate(self.game.lua_codes)
                          if "ActionMoveToObject" in code)
        interact_index = next(i for i, code in enumerate(self.game.lua_codes)
                              if "ActionInteractObject" in code)
        self.assertLess(move_index, interact_index)
        self.assertNotIn("ActionInteractObject", self.game.lua_codes[move_index])
        self.assertNotIn("ActionMoveToObject", self.game.lua_codes[interact_index])
        self.assertNotIn("ActionOpenDoor", emitted)
        self.assertNotIn("ActionMoveToLocation", emitted)

    def test_placeable_transaction_rejects_wrong_declared_preopen_state(self):
        text = '''
name = "placeable pre-open"
target = "k1"
[[step]]
do = "placeable_transaction"; module = "end_m01aa"; type = 64; tag = "end_locker01"
position = [10.795940399169922, 21.870288848876953, -1.1049995422363281]
interaction_range = 1.0; pre_open = false; timeout = 2
'''
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        real_observe = World.observe_world
        World.observe_world = lambda *_a, **_kw: _placeable_world(open_=True)
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("pre-open state mismatch", report.steps[0].detail)
        self.assertNotIn("ActionInteractObject", "\n".join(self.game.lua_codes))

    def test_placeable_transaction_rejects_identity_reuse_after_queue(self):
        text = '''
name = "placeable reuse"
target = "k1"
[[step]]
do = "placeable_transaction"; module = "end_m01aa"; type = 64; tag = "end_locker01"
position = [10.795940399169922, 21.870288848876953, -1.1049995422363281]
interaction_range = 1.0; pre_open = false; timeout = 2
'''
        before = _placeable_world(open_=False)
        reused = _placeable_world(open_=True)
        reused["objects"][0]["tag"] = "replacement_locker"
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        real_observe = World.observe_world
        snapshots = iter((before, reused))
        World.observe_world = lambda *_a, **_kw: next(snapshots)
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("placeable target identity changed during move", report.steps[0].detail)
        self.assertIn("ActionMoveToObject", "\n".join(self.game.lua_codes))
        self.assertNotIn("ActionInteractObject", "\n".join(self.game.lua_codes))

    def test_placeable_transaction_does_not_count_range_without_open(self):
        text = '''
name = "placeable closed"
target = "k1"
[[step]]
do = "placeable_transaction"; module = "end_m01aa"; type = 64; tag = "end_locker01"
position = [10.795940399169922, 21.870288848876953, -1.1049995422363281]
interaction_range = 1.0; pre_open = false; timeout = 0.25
'''
        closed = _placeable_world(open_=False, pc_position=(10.9, 21.7, -1.105))
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        real_observe = World.observe_world
        World.observe_world = lambda *_a, **_kw: closed
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("interaction did not reach open/range/stable state", report.steps[0].detail)
        self.assertIn("ActionInteractObject", "\n".join(self.game.lua_codes))

    def test_door_transaction_refuses_rounded_approach_centroid_before_action(self):
        """Route declarations must carry the parser's centroid, not a display-rounded value."""
        text = '''
name = "door rounded centroid"
target = "k1"
[[step]]
do = "door_transaction"; module = "end_m01aa"; type = 8; tag = "end_door01"
position = [21.1225, 20.7130, -1.3158]; destination = [20.32586733500163, 21.70310910542806, -1.275]
walkmesh_approach_centroid = [19.915, 20.195, -1.275]
walkmesh_far_centroid = [20.32586733500163, 21.70310910542806, -1.275]
'''
        text += self.door_route_toml
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("walkmesh approach centroid mismatch", report.steps[0].detail)
        self.assertNotIn("ActionMoveToObject", "\n".join(self.game.lua_codes))

    def test_door_transaction_target_vanish_or_reuse_fails_before_far_side_move(self):
        text = '''
name = "door vanished"
target = "k1"
[[step]]
do = "door_transaction"; module = "end_m01aa"; type = 8; tag = "end_door01"
position = [21.1225, 20.7130, -1.3158]; destination = [20.32586733500163, 21.70310910542806, -1.275]
walkmesh_approach_centroid = [19.914662679036457, 20.194860458374023, -1.274999976158142]
walkmesh_far_centroid = [20.32586733500163, 21.70310910542806, -1.275]
'''
        text += self.door_route_toml
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        self.game.lua_fail_substring = "door identity changed"
        real_observe = World.observe_world
        World.observe_world = lambda *_a, **_kw: _world(locked=False, open_=False)
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("target vanished", report.steps[0].detail)
        self.assertNotIn("ActionMoveToLocation", "\n".join(self.game.lua_codes))

    def test_door_transaction_rejects_same_id_wrong_identity_after_queue(self):
        text = '''
name = "door id reuse after queue"
target = "k1"
[[step]]
do = "door_transaction"; module = "end_m01aa"; type = 8; tag = "end_door01"
position = [21.1225, 20.7130, -1.3158]; destination = [20.32586733500163, 21.70310910542806, -1.275]
walkmesh_approach_centroid = [19.914662679036457, 20.194860458374023, -1.274999976158142]
walkmesh_far_centroid = [20.32586733500163, 21.70310910542806, -1.275]
'''
        text += self.door_route_toml
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        before, facing, reused = _world(locked=False, open_=False), _world(locked=False, open_=False), _world(locked=False, open_=True)
        reused["objects"][0]["tag"] = "replacement_door"
        real_observe = World.observe_world
        snapshots = iter((before, facing, reused))
        World.observe_world = lambda *_a, **_kw: next(snapshots)
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("missing", report.steps[0].detail)
        emitted = "\n".join(self.game.lua_codes)
        self.assertIn("ActionOpenDoor", emitted)
        self.assertNotIn("ActionMoveToLocation", emitted)

    def test_door_transaction_refuses_unmaterialized_or_mismatched_wok_before_action(self):
        text = '''
name = "door missing wok"
target = "k1"
[[step]]
do = "door_transaction"; module = "end_m01aa"; type = 8; tag = "end_door01"
position = [21.1225, 20.7130, -1.3158]; destination = [20.32586733500163, 21.70310910542806, -1.275]
walkmesh_approach_centroid = [19.914662679036457, 20.194860458374023, -1.274999976158142]
walkmesh_far_centroid = [20.32586733500163, 21.70310910542806, -1.275]
walkmesh_resource = "test/m01aa_01a.wok"; walkmesh_file = "harness-resources/missing.wok"
walkmesh_size = 1; walkmesh_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"; walkmesh_path = [0, 1]; walkmesh_approach_face = 0; walkmesh_face = 1
'''
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("not materialized", report.steps[0].detail)
        self.assertNotIn("ActionMoveToObject", "\n".join(self.game.lua_codes))

    def test_door_transaction_refuses_invalid_or_mismatched_live_facing_before_action(self):
        text = '''
name = "door facing"
target = "k1"
[[step]]
do = "door_transaction"; module = "end_m01aa"; type = 8; tag = "end_door01"
position = [21.1225, 20.7130, -1.3158]; destination = [20.32586733500163, 21.70310910542806, -1.275]
walkmesh_approach_centroid = [19.914662679036457, 20.194860458374023, -1.274999976158142]
walkmesh_far_centroid = [20.32586733500163, 21.70310910542806, -1.275]
'''
        text += self.door_route_toml
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        real_observe = World.observe_world
        for facing in (float("nan"), None, -1.5707963267948966):
            self.game.lua_codes.clear()
            first, resolved = _world(locked=False, open_=False), _world(locked=False, open_=False, facing=facing)
            snapshots = iter((first, resolved))
            World.observe_world = lambda *_a, **_kw: next(snapshots)
            report = self._runner(text, shot_interval=0)[0].run()
            self.assertFalse(report.ok)
            self.assertIn("door target resolution failed", report.steps[0].detail)
            self.assertNotIn("ActionMoveToObject", "\n".join(self.game.lua_codes))
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))

    def test_checkpoint_rejects_incomplete_or_unstable_world_before_save(self):
        text = '''
name = "unsafe checkpoint"
target = "k1"
[[step]]
do = "save"; slot = 7; name = "kp"; checkpoint = "unsafe"
'''
        self.game.phase, self.game.module, self.game.server_tick = "gameplay", "end_m01aa", 1
        real_observe = World.observe_world
        incomplete = _world(locked=False, open_=False)
        incomplete["truncated"] = True
        World.observe_world = lambda *_a, **_kw: incomplete
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("checkpoint requires", report.steps[0].detail)
        self.assertNotIn("save", self.game.requests)

    def test_checkpoint_rejects_no_tick_progress_before_save(self):
        text = '''
name = "stalled checkpoint"
target = "k1"
[[step]]
do = "save"; slot = 7; name = "kp"; checkpoint = "stalled"
'''
        state = {"phase": "gameplay", "pc": {"id": 0x80000001}, "server_tick": 1,
                 "client_tick": 1, "dialog": None}
        real_observe, real_state = World.observe_world, self.ch.state
        World.observe_world = lambda *_a, **_kw: _world(locked=False, open_=False)
        self.ch.state = lambda: dict(state)
        self.addCleanup(lambda: setattr(World, "observe_world", real_observe))
        self.addCleanup(lambda: setattr(self.ch, "state", real_state))
        report = self._runner(text, shot_interval=0)[0].run()
        self.assertFalse(report.ok)
        self.assertIn("tick progress", report.steps[0].detail)
        self.assertNotIn("save", self.game.requests)


def _placeable_world(*, open_, action=0,
                     pc_position=(10.9, 21.7, -1.105)):
    world = _world(locked=False, open_=False, action=action, pc_position=pc_position)
    world["objects"] = [{"id": 198, "tag": "end_locker01", "type": 64,
                         "position": {"x": 10.795940399169922,
                                      "y": 21.870288848876953,
                                      "z": -1.1049995422363281},
                         "locked": False, "open": open_}]
    return world


def _world(*, locked, open_, action=0, duplicate=False, facing=180.0,
           pc_position=(21.0, 20.6, -1.3)):
    door = {"id": 0x80000010, "tag": "end_door01", "type": 8,
            "position": {"x": 21.1225, "y": 20.7130, "z": -1.3158},
            "locked": locked, "open": open_, "facing": facing}
    rows = [door]
    if duplicate:
        rows.append(dict(door, id=0x80000011))
    return {"module": "end_m01aa", "module_raw": "end_m01aa", "pc": {
        "id": 0x80000001, "tag": "player", "tag_raw": "player", "type": 1,
        "position": {"x": pc_position[0], "y": pc_position[1], "z": pc_position[2]}, "current_action": action,
        "in_combat": False}, "area": {"id": 0x80000002, "tag": "area", "tag_raw": "area"},
        "objects": rows, "inventory": [], "truncated": False, "errors": [],
        "invalid_objects": 0, "work_used": 1, "work_limit": 10}


class TestWorld(unittest.TestCase):
    def test_route_selector_requires_module_position_and_unambiguous_instance(self):
        world = _world(locked=False, open_=False)
        target = World.select_route_object(world, module="end_m01aa", tag="end_door01", object_type=8,
                                           position=(21.1225, 20.7130, -1.3158))
        self.assertEqual(target["id"], 0x80000010)
        self.assertTrue(World.within_object_distance(world, target, 1.0))
        with self.assertRaises(World.WorldProbeError):
            World.select_route_object(_world(locked=False, open_=False, duplicate=True),
                                      module="end_m01aa", tag="end_door01", object_type=8,
                                      position=(21.1225, 20.7130, -1.3158))

    def test_route_selector_module_match_is_case_insensitive(self):
        world = _world(locked=False, open_=False)
        world["module"] = "END_M01AA"
        target = World.select_route_object(world, module="end_m01aa", tag="end_door01", object_type=8,
                                           position=(21.1225, 20.7130, -1.3158))
        self.assertEqual(target["id"], 0x80000010)

    def test_requested_door_facing_is_bounded_and_finite(self):
        world = _world(locked=False, open_=False)
        response = {"values": [world]}
        self.assertEqual(World._normalise_response(response, facing_ids=(0x80000010,))
                         ["objects"][0]["facing"], world["objects"][0]["facing"])
        del world["objects"][0]["facing"]
        with self.assertRaises(World.WorldProbeError):
            World._normalise_response(response, facing_ids=(0x80000010,))
        world["objects"][0]["facing"] = float("nan")
        with self.assertRaises(World.WorldProbeError):
            World._normalise_response(response, facing_ids=(0x80000010,))
        with self.assertRaises(World.WorldProbeError):
            World.select_route_object(world, module="other", tag="end_door01", object_type=8,
                                      position=(21.1225, 20.7130, -1.3158))

    def test_open_readback_and_stable_gate_require_all_independent_facts(self):
        world = _world(locked=False, open_=True)
        target = world["objects"][0]
        state = {"phase": "gameplay", "pc": {"id": 0x80000001}, "server_tick": 1,
                 "client_tick": 1, "dialog": None}
        self.assertTrue(World.door_open_unlocked(world, target))
        self.assertTrue(World.stable_gameplay(state, world))
        world["pc"]["current_action"] = 0xfffe
        self.assertTrue(World.stable_gameplay(state, world))
        world["pc"]["current_action"] = 1
        self.assertFalse(World.stable_gameplay(state, world))
        world["pc"]["current_action"] = 0
        world["pc"]["in_combat"] = True
        self.assertFalse(World.stable_gameplay(state, world))


class TestCheckpoints(Base):
    def _spy_requests(self):
        """Record (cmd, timeout) for every request the driver makes."""
        seen = []
        real = self.ch.request

        def spy(cmd, **kw):
            seen.append((cmd, kw.get("timeout")))
            return real(cmd, **kw)

        self.ch.request = spy
        self.addCleanup(lambda: setattr(self.ch, "request", real))
        return seen

    def test_load_passes_the_configured_timeout_to_the_request(self):
        """A load runs an archive export and a call sequence, so the request
        carries the load ceiling; the channel default would time it out."""
        cps = Checkpoints(T.get("k1"), self.save_dir, self.tmp / "cp_timeout")
        cps.store("endar_start", "000001 - AUTOSAVE")
        seen = self._spy_requests()
        cps.load("endar_start", self.ch, timeout=7.0)
        self.assertIn(("load_save", 7.0), seen)
        seen.clear()
        cps.load_folder("000001 - AUTOSAVE", self.ch, timeout=6.0)
        self.assertIn(("load_save", 6.0), seen)

    def test_store_restore_and_load(self):
        cps = Checkpoints(T.get("k1"), self.save_dir, self.tmp / "cp")
        cps.store("endar_start", "000001 - AUTOSAVE")
        self.assertEqual(cps.names(), ["endar_start"])
        shutil.rmtree(self.save_dir / "000001 - AUTOSAVE")
        folder = cps.restore("endar_start")
        self.assertEqual(folder, "000001 - AUTOSAVE")
        self.assertTrue((self.save_dir / folder / "SAVEGAME.sav").is_file())
        st = cps.load("endar_start", self.ch, timeout=5.0)
        self.assertEqual(st["phase"], "gameplay")


class TestSessionUtilities(unittest.TestCase):
    def test_human_size_parses_quota_quantities(self):
        self.assertEqual(S._human_size("12769M"), 12769 * 1024 * 1024)
        self.assertEqual(S._human_size("1.5G*"), int(1.5 * 1024 ** 3))
        self.assertIsNone(S._human_size("none"))

    def test_display_in_use_rejects_xorg_temporary_lock(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_xlock_") as tmp:
            root = Path(tmp)
            self.assertFalse(S.display_in_use(105, root))
            (root / ".tX105-lock").touch()
            self.assertTrue(S.display_in_use(105, root))

    def test_game_environment_uses_harness_owned_temp_directory(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_env_") as tmp:
            root = Path(tmp)
            session = S.GameSession("k1", staged=root / "stage")
            session.game_dir = root / "stage"
            session.game_dir.mkdir()
            session.port = 12345
            session.display = 100
            with mock.patch.object(S.shutil, "which", return_value=None):
                env = session._build_env()
            self.assertEqual(Path(env["TMPDIR"]), session.game_dir / "Temp")
            self.assertTrue(Path(env["TMPDIR"]).is_dir())

    def test_wine_commands_share_a_runtime_backing_directory(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_wine_tmp_") as tmp:
            root = Path(tmp)
            game_dir = root / "game"
            prefix = root / "prefix"
            runtime = root / "runtime"
            game_dir.mkdir()
            prefix.mkdir()
            runtime.mkdir()
            with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}), \
                 mock.patch.object(S.shutil, "which", return_value="/usr/bin/bwrap"), \
                 mock.patch.object(S.Path, "is_dir", return_value=True):
                launch = S.wine_command(["wine", "swkotor.exe"], game_dir, prefix)
                temp = S.wine_tmp_backing(game_dir, prefix)
                marker = temp / ".wine-test"
                marker.write_text("socket")
                cleanup = S.wine_command(["wineserver", "-k"], game_dir, prefix)
            self.assertIn(["--bind", str(temp), "/tmp"],
                          [launch[i:i + 3] for i in range(len(launch) - 2)])
            self.assertTrue(temp.is_relative_to(runtime))
            self.assertNotEqual(temp, game_dir / "Temp")
            self.assertNotIn("--tmpfs", launch)
            self.assertTrue(marker.is_file())
            self.assertEqual(launch[:launch.index("--")], cleanup[:cleanup.index("--")])
            self.assertIn("--dev-bind", launch)
            self.assertIn("/tmp/.X11-unix", launch)

    def test_wine_runtime_fallback_uses_a_second_runtime_filesystem(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_wine_tmp_") as tmp:
            root = Path(tmp)
            game_dir, prefix = root / "game", root / "prefix"
            game_dir.mkdir()
            prefix.mkdir()
            shm = root / "shm"
            shm.mkdir()
            with mock.patch.object(S, "wine_tmp_roots", return_value=[root / "missing" / "kpharness",
                                                                         shm / "kpharness-1000"]):
                backing = S.wine_tmp_backing(game_dir, prefix)
            self.assertTrue(backing.is_relative_to(shm))
            self.assertNotEqual(backing, game_dir / "Temp")

    def test_wine_runtime_failure_does_not_fall_back_to_the_game_disk(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_wine_tmp_") as tmp:
            root = Path(tmp)
            game_dir, prefix = root / "game", root / "prefix"
            game_dir.mkdir()
            prefix.mkdir()
            with mock.patch.object(S, "wine_tmp_roots", return_value=[root / "missing-a" / "kpharness",
                                                                         root / "missing-b" / "kpharness"]):
                with self.assertRaises(S.BootFailure) as caught:
                    S.wine_tmp_backing(game_dir, prefix)
            self.assertEqual(caught.exception.reason, "wine tmp")

    def test_wine_command_falls_back_without_bwrap_or_isolation(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_wine_tmp_") as tmp:
            game_dir = Path(tmp) / "game"
            prefix = Path(tmp) / "prefix"
            game_dir.mkdir()
            prefix.mkdir()
            with mock.patch.object(S.shutil, "which", return_value=None):
                self.assertEqual(S.wine_command(["wineserver", "-k"], game_dir, prefix),
                                 ["wineserver", "-k"])

    def test_wine_command_preserves_tmpfs_game_and_prefix_after_private_tmp_bind(self):
        """A /tmp bind must precede its game/prefix child mounts in bwrap."""
        with tempfile.TemporaryDirectory(dir="/tmp", prefix="kpharness_wine_tmpfs_") as tmp:
            root = Path(tmp)
            game_dir, prefix, private_tmp = root / "game", root / "prefix", root / "private"
            for path in (game_dir, prefix, private_tmp):
                path.mkdir()
            with mock.patch.object(S.shutil, "which", return_value="/usr/bin/bwrap"):
                command = S.wine_command(["wine", "swkotor.exe"], game_dir, prefix,
                                         tmp_dir=private_tmp, isolate=True)
            triples = [command[i:i + 3] for i in range(len(command) - 2)]
            tmp_index = triples.index(["--bind", str(private_tmp), "/tmp"])
            game_index = triples.index(["--bind", str(game_dir), str(game_dir)])
            prefix_index = triples.index(["--bind", str(prefix), str(prefix)])
            self.assertLess(tmp_index, game_index)
            self.assertLess(tmp_index, prefix_index)
            with mock.patch.dict(os.environ, {"KP_WINE_TMP_ISOLATE": "0"}):
                self.assertEqual(S.wine_command(["wineserver", "-k"], game_dir, prefix),
                                 ["wineserver", "-k"])

    def test_down_uses_the_recorded_wine_wrapper_when_environment_changes(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_wine_tmp_") as tmp:
            root = Path(tmp)
            game_dir = root / "game"
            prefix = root / "prefix"
            recorded_tmp = root / "runtime" / "kpharness" / "wine-recorded"
            game_dir.mkdir()
            prefix.mkdir()
            info = S.SessionInfo(target="k1", staged=str(root / "stage"),
                                 game_dir=str(game_dir), save_dir="", run_dir=str(root),
                                 display=100, port=0, xvfb_pid=0, launcher_pid=0,
                                 lock_path="", wineprefix=str(prefix), wine_tmp_dir=str(recorded_tmp),
                                 wine_tmp_isolated=True, process_name="none")
            with mock.patch.dict(os.environ, {"KP_WINE_TMP_ISOLATE": "0"}), \
                 mock.patch.object(S, "pids_by_name", return_value=[]), \
                 mock.patch.object(S.shutil, "which", return_value="/usr/bin/bwrap"), \
                 mock.patch.object(S.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
                S.teardown_from_info(info, log=lambda _msg: None)
            command = run.call_args.args[0]
            self.assertEqual(run.call_count, 1)
            self.assertEqual(command[-3:], ["--", "wineserver", "-k"])
            self.assertIn(["--bind", str(recorded_tmp), "/tmp"],
                          [command[i:i + 3] for i in range(len(command) - 2)])

    def test_down_skips_recorded_private_namespace_without_bwrap(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_wine_tmp_") as tmp:
            root = Path(tmp)
            game_dir, prefix = root / "game", root / "prefix"
            game_dir.mkdir()
            prefix.mkdir()
            info = S.SessionInfo(target="k1", staged=str(root / "stage"),
                                 game_dir=str(game_dir), save_dir="", run_dir=str(root),
                                 display=100, port=0, xvfb_pid=0, launcher_pid=0,
                                 lock_path="", wineprefix=str(prefix),
                                 wine_tmp_dir=str(root / "runtime" / "wine-recorded"),
                                 wine_tmp_isolated=True, process_name="none")
            logs = []
            with mock.patch.object(S, "pids_by_name", return_value=[]), \
                 mock.patch.object(S.shutil, "which", return_value=None), \
                 mock.patch.object(S.subprocess, "run") as run:
                S.teardown_from_info(info, log=logs.append)
            run.assert_not_called()
            self.assertTrue(any("recorded Wine namespace" in message for message in logs))

    def test_old_session_info_uses_current_isolation_selection(self):
        old = S.SessionInfo.from_dict({"target": "k1", "staged": "stage", "game_dir": "game",
                                       "save_dir": "", "run_dir": "run", "display": 100,
                                       "port": 0, "xvfb_pid": 0, "launcher_pid": 0, "lock_path": ""})
        self.assertIsNone(old.wine_tmp_isolated)
        self.assertEqual(old.wine_tmp_dir, "")

    def test_legacy_down_probes_host_and_game_temp_namespaces(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_wine_tmp_") as tmp:
            root = Path(tmp)
            game_dir, prefix = root / "game", root / "prefix"
            game_dir.mkdir()
            prefix.mkdir()
            info = S.SessionInfo(target="k1", staged=str(root / "stage"), game_dir=str(game_dir),
                                 save_dir="", run_dir=str(root), display=100, port=0, xvfb_pid=0,
                                 launcher_pid=0, lock_path="", wineprefix=str(prefix), process_name="none")
            with mock.patch.object(S, "pids_by_name", return_value=[]), \
                 mock.patch.object(S.shutil, "which", return_value="/usr/bin/bwrap"), \
                 mock.patch.object(S.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
                S.teardown_from_info(info, log=lambda _msg: None)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[0], ["wineserver", "-k"])
            wrapped = run.call_args_list[1].args[0]
            self.assertIn(["--bind", str(game_dir / "Temp"), "/tmp"],
                          [wrapped[i:i + 3] for i in range(len(wrapped) - 2)])
            self.assertEqual(run.call_args_list[0].kwargs["timeout"], 5)
            self.assertEqual(run.call_args_list[1].kwargs["timeout"], 5)

    def test_session_info_persists_wine_namespace_identity(self):
        with tempfile.TemporaryDirectory(prefix="kpharness_wine_tmp_") as tmp:
            root = Path(tmp)
            session = S.GameSession("k1", staged=root / "stage")
            session.staged.mkdir()
            session.game_dir = root / "game"
            session.game_dir.mkdir()
            session.save_dir = root / "saves"
            session.save_dir.mkdir()
            session.run_dir = root / "run"
            session.run_dir.mkdir()
            session.display, session.port = 100, 27015
            session._wine_tmp_isolated = True
            session._wine_tmp_dir = root / "runtime" / "kpharness" / "wine-stable"
            info = S.SessionInfo.from_dict(json.loads(session.write_session_info().read_text()))
            self.assertTrue(info.wine_tmp_isolated)
            self.assertEqual(info.wine_tmp_dir, str(session._wine_tmp_dir))

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kpharness_su_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tune_ini_sets_every_occurrence_and_adds_missing(self):
        ini = self.tmp / "swkotor2.ini"
        ini.write_bytes(b"[Display Options]\r\nFullScreen=1\r\nDisable Movies=0\r\n\r\n"
                        b"[Graphics Options]\r\nFullScreen=1\r\nFrame Buffer=1\r\n"
                        b"DisableVertexBufferObjects=1\r\n")
        tune_ini(ini, T.K2_WINE.ini_keys)
        text = ini.read_bytes().decode()
        self.assertIn("\r\n", text)
        self.assertEqual(text.count("FullScreen=0"), 2)
        self.assertNotIn("FullScreen=1", text)
        self.assertIn("Disable Vertex Buffer Objects=1", text)
        self.assertIn("[Game Options]", text)
        self.assertIn("EnableCheats=1", text)
        self.assertIn("Disable Movies=1", text)
        self.assertIn("Width=1024", text)

    def test_tune_ini_populates_requested_section_despite_stale_global_key(self):
        ini = self.tmp / "swkotor.ini"
        ini.write_text("[Graphics Options]\nFullScreen=1\n\n[Keymapping]\n"
                       "Width=640\nHeight=480\n")
        tune_ini(ini, T.K1.ini_keys)
        lines = ini.read_text().splitlines()
        graphics = lines.index("[Graphics Options]")
        keymapping = lines.index("[Keymapping]")
        graphics_lines = lines[graphics + 1:keymapping]
        self.assertIn("Width=1024", graphics_lines)
        self.assertIn("Height=768", graphics_lines)
        # Compatibility behavior remains: pre-existing copies are still
        # normalized rather than silently left stale.
        self.assertIn("Width=1024", lines[keymapping + 1:])
        self.assertIn("Height=768", lines[keymapping + 1:])

    def test_write_runtime_ini_keeps_other_keys(self):
        gd = self.tmp
        (gd / "kotorphasor.ini").write_text("error_budget = 3\nharness_port = 1\n")
        write_runtime_ini(gd, 27015)
        text = (gd / "kotorphasor.ini").read_text()
        self.assertIn("error_budget = 3", text)
        self.assertEqual(text.count("harness_port"), 1)
        self.assertIn("harness_port = 27015", text)
        self.assertIn("harness_bind = 127.0.0.1", text)

    def test_overlay_tree(self):
        src = self.tmp / "src"
        (src / "modules").mkdir(parents=True)
        (src / "modules" / "a.rim").write_bytes(b"x")
        (src / "Saves" / "000001 - AUTOSAVE").mkdir(parents=True)
        (src / "Saves" / "000001 - AUTOSAVE" / "SAVEGAME.sav").write_bytes(b"s")
        (src / "swkotor.exe").write_bytes(b"MZ")
        (src / "swkotor.ini").write_text("[Game Options]\n")
        dst = self.tmp / "dst"
        overlay_tree(src, dst, ["Saves"], copy_files=False)
        self.assertTrue((dst / "modules").is_symlink())
        self.assertFalse((dst / "Saves").is_symlink())
        self.assertTrue((dst / "Saves" / "000001 - AUTOSAVE" / "SAVEGAME.sav").is_file())
        self.assertTrue((dst / "swkotor.exe").is_symlink())
        self.assertFalse((dst / "swkotor.ini").is_symlink())   # inis are always real

    def test_pids_by_name_and_free_port(self):
        self.assertIn(os.getpid(), pids_by_name(Path(f"/proc/{os.getpid()}/comm").read_text().strip()))
        self.assertEqual(pids_by_name("no-such-process-name-xyz"), [])
        p = free_port()
        self.assertTrue(1024 < p < 65536)

    def test_targets(self):
        self.assertEqual(T.get("k2").name, "k2-native")
        self.assertFalse(T.get("k2-native").exe_in_data_dir)
        self.assertTrue(T.get("k1").wine)
        with self.assertRaises(KeyError):
            T.get("k3")


class TestBootRetry(unittest.TestCase):
    """GameSession._launch_and_connect, with the launch and the channel stubbed.

    The first launch after `pkill swkotor.exe; wineserver -k` dies without
    writing a line and the next one works, twice out of two. These cases pin
    which failures earn a second launch and which are reported at once.
    """

    def setUp(self):
        self.settle = S.BOOT_RETRY_SETTLE
        S.BOOT_RETRY_SETTLE = 0.0

    def tearDown(self):
        S.BOOT_RETRY_SETTLE = self.settle

    @staticmethod
    def _session(outcomes):
        s = GameSession.__new__(GameSession)
        s.launcher = None
        s.launches = 0
        s.kills = 0
        s.log = lambda _msg: None

        def launch():
            s.launches += 1

        def connect():
            outcome = outcomes[s.launches - 1]
            if isinstance(outcome, BootFailure):
                raise outcome
            return outcome

        s.launch = launch
        s.connect = connect
        s._kill_game = lambda: setattr(s, "kills", s.kills + 1)
        return s

    def test_a_dead_first_launch_is_retried_once(self):
        s = self._session([BootFailure("crash", "swkotor.exe is not running"), "channel"])
        self.assertEqual(s._launch_and_connect(), "channel")
        self.assertEqual(s.launches, 2)
        self.assertEqual(s.kills, 1)

    def test_a_refusal_is_reported_without_a_second_launch(self):
        s = self._session([BootFailure("refusal", "refusing to install"), "channel"])
        with self.assertRaises(BootFailure) as caught:
            s._launch_and_connect()
        self.assertEqual(caught.exception.reason, "refusal")
        self.assertEqual(s.launches, 1)

    def test_exhausted_launches_raise_the_last_failure(self):
        failures = [BootFailure("boot timeout", f"attempt {i}")
                    for i in range(S.BOOT_ATTEMPTS)]
        s = self._session(failures)
        with self.assertRaises(BootFailure) as caught:
            s._launch_and_connect()
        self.assertIs(caught.exception, failures[-1])
        self.assertEqual(s.launches, S.BOOT_ATTEMPTS)
        self.assertEqual(s.kills, S.BOOT_ATTEMPTS - 1)

    def test_last_allowed_launch_can_succeed(self):
        s = self._session([BootFailure("crash", "not running")
                           for _ in range(S.BOOT_ATTEMPTS - 1)] + ["channel"])
        self.assertEqual(s._launch_and_connect(), "channel")
        self.assertEqual(s.launches, S.BOOT_ATTEMPTS)
        self.assertEqual(s.kills, S.BOOT_ATTEMPTS - 1)


class TestStaging(unittest.TestCase):
    """stage() against a synthetic K1 install and build dir, in a temp root."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kpharness_stage_"))
        inst = self.tmp / "install"
        (inst / "modules").mkdir(parents=True)
        (inst / "modules" / "end_m01aa.rim").write_bytes(b"rim")
        (inst / "Saves" / "000001 - AUTOSAVE").mkdir(parents=True)
        (inst / "Saves" / "000001 - AUTOSAVE" / "SAVEGAME.sav").write_bytes(b"s")
        (inst / "Saves" / "000001 - AUTOSAVE" / "SAVENFO.res").write_bytes(b"source-info")
        (inst / "chitin.key").write_bytes(b"KEY V1  ")
        (inst / "swkotor.exe").write_bytes(b"MZ")
        (inst / "binkw32.dll").write_bytes(b"\0" * 300000)     # the real codec, by size
        (inst / "swkotor.ini").write_text("[Game Options]\nEnableCheats=0\n"
                                          "[Graphics Options]\nFullScreen=1\nFrame Buffer=1\n")
        build = self.tmp / "build"
        build.mkdir()
        (build / "kphasor.dll").write_bytes(b"dll")
        (build / "binkw32.dll").write_bytes(b"proxy kphasor.dll")
        self.inst, self.build = inst, build
        self.saved_env = {k: os.environ.get(k) for k in ("KOTOR1_DIR", "KP_BUILD_DIR")}
        os.environ["KOTOR1_DIR"] = str(inst)
        os.environ["KP_BUILD_DIR"] = str(build)

    def tearDown(self):
        for k, v in self.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_k1(self):
        from kpharness.session import GameSession, proxy_is_ours
        staged = self.tmp / "k1_harness"
        logs = []
        s = GameSession("k1", staged=str(staged), log=logs.append)
        s.stage()
        s.port = 27015
        write_runtime_ini(s.game_dir, s.port)
        s._session_log.close()
        self.assertEqual(s.game_dir, staged)
        self.assertTrue((staged / "modules").is_symlink())
        self.assertFalse((staged / "Saves").is_symlink())
        self.assertTrue((staged / "Saves" / "000001 - AUTOSAVE" / "SAVEGAME.sav").is_file())
        self.assertTrue((staged / "binkw32_real.dll").is_file())
        self.assertEqual((staged / "binkw32_real.dll").stat().st_size, 300000)
        self.assertTrue(proxy_is_ours(staged / "binkw32.dll"))
        self.assertTrue((staged / "kphasor.dll").is_file())
        self.assertTrue((staged / "kotorphasor" / "addresses" / "k1_steam_103_unpacked.json").is_file())
        self.assertTrue((staged / "kotorphasor" / "scripts").is_dir())
        self.assertTrue((staged / "steam_appid.txt").is_file())
        ini = (staged / "swkotor.ini").read_text()
        self.assertIn("EnableCheats=1", ini)
        self.assertIn("FullScreen=0", ini)
        self.assertIn("Frame Buffer=0", ini)
        self.assertIn("Disable Movies=1", ini)
        self.assertIn("harness_port = 27015", (staged / "kotorphasor.ini").read_text())
        self.assertEqual((self.inst / "swkotor.ini").read_text().count("EnableCheats=1"), 0)
        self.assertTrue((s.run_dir / "session.log").is_file())
        # A second stage() on the same tree is a no-op for the overlay and
        # re-installs the runtime without complaint.
        s2 = GameSession("k1", staged=str(staged), log=logs.append)
        s2.stage()
        s2._session_log.close()
        self.assertEqual((staged / "binkw32_real.dll").stat().st_size, 300000)

    def test_reset_saves_restores_k1_source_baseline(self):
        staged = self.tmp / "k1_reset_harness"
        original = self.inst / "Saves" / "000001 - AUTOSAVE"
        initial = GameSession("k1", staged=str(staged), log=lambda _: None)
        initial.stage()
        initial._session_log.close()
        staged_save = staged / "Saves" / "000001 - AUTOSAVE"
        (staged_save / "SAVEGAME.sav").write_bytes(b"mutated")
        (staged / "Saves" / "999999 - GENERATED").mkdir()
        (staged / "Saves" / "999999 - GENERATED" / "SAVEGAME.sav").write_bytes(b"generated")

        reset = GameSession("k1", staged=str(staged), log=lambda _: None, reset_saves=True)
        # Staging tests are hermetic: exercise the reset's own process guard
        # without allowing an unrelated real Wine session to influence it.
        with mock.patch.object(S, "pids_by_name", return_value=[]):
            reset.stage()
        reset._session_log.close()

        self.assertEqual((staged_save / "SAVEGAME.sav").read_bytes(), b"s")
        self.assertEqual((staged_save / "SAVENFO.res").read_bytes(), b"source-info")
        self.assertFalse((staged / "Saves" / "999999 - GENERATED").exists())
        self.assertEqual((original / "SAVEGAME.sav").read_bytes(), b"s")
        self.assertEqual((original / "SAVENFO.res").read_bytes(), b"source-info")

    def test_reset_saves_replaces_legacy_staged_link(self):
        staged = self.tmp / "k1_legacy_link_harness"
        initial = GameSession("k1", staged=str(staged), log=lambda _: None)
        initial.stage()
        initial._session_log.close()
        shutil.rmtree(staged / "Saves")
        (staged / "Saves").symlink_to(self.inst / "Saves")

        reset = GameSession("k1", staged=str(staged), log=lambda _: None, reset_saves=True)
        with mock.patch.object(S, "pids_by_name", return_value=[]):
            reset.stage()
        reset._session_log.close()

        self.assertFalse((staged / "Saves").is_symlink())
        self.assertEqual((staged / "Saves" / "000001 - AUTOSAVE" / "SAVENFO.res").read_bytes(),
                         b"source-info")

    def test_stage_and_wineprefix_overrides_are_opt_in_and_precedence_ordered(self):
        """Explicit constructor paths win; environment paths make CLI runs portable."""
        from kpharness.session import GameSession
        env_stage = self.tmp / "env-stage"
        env_prefix = self.tmp / "env-prefix"
        explicit_stage = self.tmp / "explicit-stage"
        explicit_prefix = self.tmp / "explicit-prefix"
        with mock.patch.dict(os.environ, {"KP_STAGED_DIR": str(env_stage),
                                          "KP_WINEPREFIX": str(env_prefix)}):
            inherited = GameSession("k1")
            self.assertEqual(inherited.staged, env_stage.resolve())
            self.assertEqual(inherited.wineprefix, env_prefix.resolve())
            explicit = GameSession("k1", staged=str(explicit_stage), wineprefix=str(explicit_prefix))
            self.assertEqual(explicit.staged, explicit_stage.resolve())
            self.assertEqual(explicit.wineprefix, explicit_prefix.resolve())

    def test_stage_declared_wok_uses_kq_bytes_and_reuses_verified_content(self):
        from kpharness.resources import Resource
        staged = self.tmp / "k1_resource_harness"
        data = b"BWM V1.0" + b"\0" * 24
        declaration = {"walkmesh_resource": "data/models.bif/m01aa_01a.wok",
                       "walkmesh_file": "harness-resources/m01aa_01a.wok",
                       "walkmesh_size": len(data),
                       "walkmesh_sha256": hashlib.sha256(data).hexdigest()}
        completed = subprocess.CompletedProcess(["kq"], 0, stdout=data, stderr=b"")
        with mock.patch.object(S.subprocess, "run", return_value=completed) as run:
            s = GameSession("k1", staged=str(staged))
            s.stage([Resource.from_legacy(declaration)])
            s._session_log.close()
        self.assertEqual((staged / "harness-resources" / "m01aa_01a.wok").read_bytes(), data)
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--install") + 1], str(self.inst))
        self.assertEqual(args[args.index("--from") + 1], "data/models.bif")
        self.assertIn("m01aa_01a.wok", args)
        # A matching content-addressed overlay artifact is reusable: this
        # avoids reopening the external game archive on every live iteration.
        staged_wok = staged / "harness-resources" / "m01aa_01a.wok"
        with mock.patch.object(S.subprocess, "run", return_value=completed) as rerun:
            again = GameSession("k1", staged=str(staged))
            again.stage([declaration])
            again._session_log.close()
        self.assertEqual(rerun.call_count, 0)
        self.assertEqual(staged_wok.read_bytes(), data)
        # An arbitrary stale file fails the same byte proof and is replaced by
        # kq output before it can influence a route.
        staged_wok.write_bytes(b"host artifact")
        with mock.patch.object(S.subprocess, "run", return_value=completed) as rerun:
            again = GameSession("k1", staged=str(staged))
            again.stage([declaration])
            again._session_log.close()
        self.assertEqual(rerun.call_count, 1)
        self.assertEqual(staged_wok.read_bytes(), data)
        declaration["walkmesh_sha256"] = "0" * 64
        bad = GameSession("k1", staged=str(self.tmp / "bad_resource"))
        try:
            with self.assertRaises(BootFailure):
                bad.stage([declaration])
        finally:
            if bad._session_log is not None:
                bad._session_log.close()


class TestStagingK2Native(unittest.TestCase):
    """stage() against a synthetic k2-native install: the case-matching
    Miles symlinks the ELF needs, wired in scripts/harness/kpharness/session.py."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kpharness_stage_k2n_"))
        inst = self.tmp / "install"
        sa = inst / "steamassets"
        sa.mkdir(parents=True)
        (sa / "chitin.key").write_bytes(b"KEY V1  ")
        (sa / "swkotor2.ini").write_text("[Game Options]\nEnableCheats=0\n"
                                         "[Graphics Options]\nFullScreen=1\nFrame Buffer=1\n")
        (inst / "kotor2").write_bytes(b"\x7fELF")
        # The real depot ships these lowercase; the ELF's DT_NEEDED entries
        # are capitalised (libMiles.so, libMilesMidi.so).
        (inst / "libmiles.so").write_bytes(b"miles")
        (inst / "libmilesmidi.so").write_bytes(b"milesmidi")
        build = self.tmp / "build"
        build.mkdir()
        (build / "libkphasor.so").write_bytes(b"so")
        self.inst, self.build = inst, build
        self.saved_env = {k: os.environ.get(k) for k in ("KOTOR2_DIR", "KP_BUILD_DIR")}
        os.environ["KOTOR2_DIR"] = str(sa)
        os.environ["KP_BUILD_DIR"] = str(build)

    def tearDown(self):
        for k, v in self.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_k2_native_adds_miles_case_symlinks(self):
        staged = self.tmp / "k2-native_harness"
        logs = []
        s = GameSession("k2-native", staged=str(staged), log=logs.append)
        s.stage()
        s._session_log.close()
        self.assertTrue((staged / "libMiles.so").is_symlink())
        self.assertEqual(os.readlink(staged / "libMiles.so"), "libmiles.so")
        self.assertTrue((staged / "libMiles.so").is_file())
        self.assertTrue((staged / "libMilesMidi.so").is_symlink())
        self.assertEqual(os.readlink(staged / "libMilesMidi.so"), "libmilesmidi.so")
        self.assertTrue((staged / "libMilesMidi.so").is_file())
        # Idempotent: staging again does not fail or replace the link.
        s2 = GameSession("k2-native", staged=str(staged), log=logs.append)
        s2.stage()
        s2._session_log.close()
        self.assertTrue((staged / "libMiles.so").is_symlink())

    def test_stage_k2_native_skips_quietly_without_lowercase_source(self):
        (self.inst / "libmiles.so").unlink()
        (self.inst / "libmilesmidi.so").unlink()
        staged = self.tmp / "k2-native_harness_nolibs"
        logs = []
        s = GameSession("k2-native", staged=str(staged), log=logs.append)
        s.stage()
        s._session_log.close()
        self.assertFalse((staged / "libMiles.so").exists())
        self.assertFalse((staged / "libMilesMidi.so").exists())
        self.assertTrue(any("skipping libMiles.so" in m for m in logs))


class TestLibGluDirs(unittest.TestCase):
    """discover.libglu_dirs() only returns directories that actually have a
    resolvable libGLU.so.1, not merely a directory that might hold a
    versioned .so with no un-versioned SONAME symlink."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kpharness_libglu_"))
        self.saved_env = os.environ.get("KP_LIBGLU_DIR")

    def tearDown(self):
        if self.saved_env is None:
            os.environ.pop("KP_LIBGLU_DIR", None)
        else:
            os.environ["KP_LIBGLU_DIR"] = self.saved_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_versioned_only_directory_is_rejected(self):
        bad = self.tmp / "versioned-only"
        bad.mkdir()
        (bad / "libGLU.so.1.3.1").write_bytes(b"so")
        self.assertFalse(D._has_libglu(bad))

    def test_directory_with_soname_symlink_is_accepted(self):
        good = self.tmp / "with-symlink"
        good.mkdir()
        (good / "libGLU.so.1.3.08004").write_bytes(b"so")
        (good / "libGLU.so.1").symlink_to("libGLU.so.1.3.08004")
        self.assertTrue(D._has_libglu(good))

    def test_dangling_symlink_is_rejected(self):
        dangling = self.tmp / "dangling"
        dangling.mkdir()
        (dangling / "libGLU.so.1").symlink_to("libGLU.so.1.3.99999")  # never created
        self.assertFalse(D._has_libglu(dangling))

    def test_explicit_kp_libglu_dir_is_validated_not_just_trusted(self):
        bad = self.tmp / "override-versioned-only"
        bad.mkdir()
        (bad / "libGLU.so.1.3.1").write_bytes(b"so")
        os.environ["KP_LIBGLU_DIR"] = str(bad)
        self.assertNotIn(bad.resolve(), [p.resolve() for p in D.libglu_dirs()])


class TestBwm(unittest.TestCase):
    @staticmethod
    def _mesh() -> bytes:
        """Two walkable triangles sharing one edge, with valid BWM V1.0 tables."""
        vertices = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (0.0, 0.0, 0.0), (1.0, 2.0, 0.0)]
        faces = [(0, 1, 2), (1, 3, 2)]
        vo, io, ao = 136, 136 + 12 * len(vertices), 136 + 12 * len(vertices) + 12 * len(faces)
        data = bytearray(ao + 24)
        data[:8] = b"BWM V1.0"
        struct.pack_into("<16I", data, 72, len(vertices), vo, len(faces), io,
                         0, 0, 0, 0, 0, 0, len(faces), ao, 0, 0, 0, 0)
        for i, point in enumerate(vertices):
            struct.pack_into("<3f", data, vo + i * 12, *point)
        for i, face in enumerate(faces):
            struct.pack_into("<3I", data, io + i * 12, *face)
        return bytes(data)

    def test_selects_connected_opposite_side_with_path(self):
        result = Bwm.select_far_side(Bwm.parse(self._mesh()), door=(0, 0, 0),
                                     approach=(0, -1, 0), normal_xy=(0, 1), min_projection=.1)
        self.assertEqual(result["face"], 1)
        self.assertEqual(result["path"], [0, 1])
        self.assertGreater(result["far_projection"], 0)

    def test_rejects_truncated_overflow_and_bad_indices(self):
        mesh = self._mesh()
        with self.assertRaises(Bwm.BwmError):
            Bwm.parse(mesh[:135])
        overflow = bytearray(mesh)
        struct.pack_into("<I", overflow, 76, 0xfffffff0)
        with self.assertRaises(Bwm.BwmError):
            Bwm.parse(bytes(overflow))
        bad_index = bytearray(mesh)
        struct.pack_into("<I", bad_index, 136 + 48, 99)
        with self.assertRaises(Bwm.BwmError):
            Bwm.parse(bytes(bad_index))

    def test_refuses_unproven_approach_side(self):
        with self.assertRaises(Bwm.BwmError):
            Bwm.select_far_side(Bwm.parse(self._mesh()), door=(0, 0, 0),
                                approach=(0, 0, 0), normal_xy=(0, 1))

    def test_endar_route_keeps_mesh_provenance_with_destination(self):
        scenario = Scenario.load(ROOT / "scripts/harness/scenarios/k1_endar_door01.toml")
        step = scenario.steps[2].raw
        resource = scenario.resources[step["resource"]]
        self.assertEqual(resource.source, "data/models.bif/m01aa_01a.wok")
        self.assertEqual(resource.sha256, "afd30f4154e5761bcd41223bc000b21422650928c7a5e56691bc2dffad4c88ba")
        self.assertEqual(step["walkmesh_path"], [12, 13])
        self.assertEqual(step["walkmesh_face"], 13)
        self.assertEqual(step["walkmesh_approach_face"], 12)
        self.assertEqual(step["walkmesh_approach_centroid"],
                         [19.914662679036457, 20.194860458374023, -1.274999976158142])
        self.assertEqual(len(step["walkmesh_far_centroid"]), 3)
        self.assertNotIn("walkmesh_door_normal_xy", step)
        self.assertEqual(len(step["destination"]), 3)


class TestConfigurationContracts(unittest.TestCase):
    def test_workspace_reader_selection_relative_paths_and_consumers(self):
        reader = D.kpdiscover()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            nested = base / "nested"
            nested.mkdir()
            install = base / "game"
            install.mkdir()
            (install / "chitin.key").touch()
            (install / "swkotor.exe").touch()
            (base / "kotorphasor.toml").write_text(
                '[paths]\nk1="game"\n[harness]\nbuild_dir="build"\n')
            with mock.patch.object(Path, "cwd", return_value=nested), mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(D.harness_config(), reader.read_workspace_config()["harness"])
                self.assertEqual(reader.find_app("k1"), install)
                self.assertEqual(D.build_dir(), base / "build")
                with mock.patch.dict(os.environ, {"KP_BUILD_DIR": str(base / "env")}):
                    self.assertEqual(D.build_dir(), base / "env")
                    self.assertEqual(D.build_dir(str(base / "explicit")), base / "explicit")
                config = nested / "kotorphasor.toml"
                config.write_text('[harness]\nlibglu_dir="glu"\n')
                self.assertEqual(reader.read_workspace_config(), {"harness": {"libglu_dir": str(nested / "glu")}})
                for text in ('[broken', 'paths=3', '[harness]\nbuild_dir=false', '[harness]\nport=123'):
                    config.write_text(text)
                    with self.subTest(text=text), self.assertRaisesRegex(ValueError, "kotorphasor.toml"):
                        D.harness_config()
            # Outside the checkout, both consumers still use the same checkout fallback.
            config.unlink()
            (base / "kotorphasor.toml").unlink()
            checkout = base / "checkout"
            checkout.mkdir()
            (checkout / "kotorphasor.toml").write_text('[harness]\nbuild_dir="build"\n')
            with mock.patch.object(Path, "cwd", return_value=nested), \
                    mock.patch.object(reader, "__file__", str(checkout / "tools" / "kpdiscover.py")):
                self.assertEqual(D.harness_config()["build_dir"], str(checkout / "build"))

    def test_cli_stages_declared_resources_and_rejects_invalid_routes_before_session(self):
        import contextlib
        import io
        from kpharness import cli
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.toml"
            path.write_text('target="k1"\n[resources.mesh]\nkind="walkmesh"\n'
                            'source="data/test.wok"\nfile="harness-resources/test.wok"\n'
                            'size=8\nsha256="' + 'a' * 64 + '"\n[[step]]\ndo="quit"\n')
            with mock.patch.object(cli, "GameSession") as session, contextlib.redirect_stderr(io.StringIO()):
                session.return_value.boot.side_effect = BootFailure("test stop before launch")
                self.assertEqual(cli.main(["run", str(path)]), 2)
                self.assertEqual(session.return_value.boot.call_args.kwargs["resources"],
                                 list(Scenario.load(path).resources.values()))
                session.reset_mock()
                path.write_text('target="k1"\n[execution]\ngame_speed=false\n[[step]]\ndo="quit"\n')
                self.assertEqual(cli.main(["run", str(path)]), 3)
                session.assert_not_called()

    def test_shared_header_validation_including_empty_pioneer_route(self):
        with tempfile.TemporaryDirectory() as directory:
            route = Path(directory) / "route.toml"
            for text in ('target="k1"\n[execution]\ngame_speed=0',
                         'target="k1"\n[settings]\nauthored_barks=[true]',
                         'target="k1"\n[execution]\nload_timeout="slow"',
                         'target="k1"\n[settings]\nunknown=1',
                         'target="k1"\n[settings]\n[execution]',
                         'target="k9"', 'target="k1"\nschema_version=true',
                         'target="k1"\nstep=[1]', 'target="k1"\nresources=[]'):
                route.write_text(text)
                with self.subTest(text=text):
                    with self.assertRaises(ScenarioError):
                        Scenario.parse(text, allow_empty=True)
                    with self.assertRaises(P.PioneerError):
                        P._load_header_only(route)
            P.init_route(route, target="k1", name='quote " and newline\n', force=True)
            self.assertEqual(P._load_header_only(route).name, 'quote " and newline\n')
            route.write_text('target="k1"\n[execution]\ngame_speed=4\nauthored_barks=[2,3]\n')
            replay = Scenario.parse(route.read_text() + '[[step]]\ndo="quit"\n')
            self.assertEqual(P._load_header_only(route).settings, replay.settings)

    def test_resource_normalization_preserves_shipped_step_semantics(self):
        from dataclasses import asdict
        from kpharness.scenario import list_scenarios
        for path in list_scenarios():
            canonical = Scenario.load(path)
            if not canonical.resources:
                continue
            # Reconstruct the old unversioned, inline form. Normalization must
            # retain every execution value, action, predicate and artifact byte.
            text = f'name={json.dumps(canonical.name)}\ntarget={json.dumps(canonical.target)}\n[settings]\n'
            text += '\n'.join(f'{k}={P._toml_value(v)}' for k, v in canonical.settings.items()) + '\n'
            for step in canonical.steps:
                raw = dict(step.raw)
                if "resource" in raw:
                    r = canonical.resources[raw.pop("resource")]
                    raw.update(walkmesh_resource=r.source, walkmesh_file=r.file,
                               walkmesh_size=r.size, walkmesh_sha256=r.sha256)
                text += '\n' + P.render_step(raw)
            legacy = Scenario.parse(text)
            self.assertEqual(legacy.settings, canonical.settings)
            self.assertEqual(list(legacy.resources.values()), list(canonical.resources.values()))
            for old, new in zip(legacy.steps, canonical.steps):
                old_raw, new_raw = dict(old.raw), dict(new.raw)
                if "resource" in old_raw:
                    old_raw["resource"] = asdict(legacy.resources[old_raw["resource"]])
                    new_raw["resource"] = asdict(canonical.resources[new_raw["resource"]])
                self.assertEqual(old_raw, new_raw)

    def test_resources_validate_before_boot(self):
        from kpharness.resources import Resource
        valid = dict(kind="walkmesh", source="data/models.bif/test.wok",
                     file="harness-resources/test.wok", size=8, sha256="a" * 64)
        for key, value in (("kind", "exe"), ("source", "../test.wok"),
                           ("source", "C:/test.wok"), ("file", "elsewhere/test.wok"),
                           ("file", "harness-resources/../escape.wok"),
                           ("size", True), ("size", -1), ("sha256", "00")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                Resource.parse(dict(valid, **{key: value}))
        declaration = '[resources.mesh]\n' + '\n'.join(f'{k}={P._toml_value(v)}' for k, v in valid.items())
        text = 'target="k1"\n' + declaration + '\n[[step]]\ndo="door_transaction"\nresource="mesh"\n'
        self.assertEqual(Scenario.parse(text).resources["mesh"], Resource.parse(valid))
        for invalid in (text.replace('resource="mesh"', 'resource="missing"'),
                        text + 'walkmesh_size=8\n',
                        text.replace('do="door_transaction"', 'do="quit"'),
                        text + 'wait="phase"\n',
                        'target="k1"\n' + declaration + '\n' + declaration.replace('[resources.mesh]', '[resources.other]').replace('size=8', 'size=9') + '\n[[step]]\ndo="quit"\n'):
            with self.subTest(text=invalid), self.assertRaises(ScenarioError):
                Scenario.parse(invalid)
        for body in ('do=true', 'wait=123', 'expect_events=true', 'screenshot="yes"'):
            with self.subTest(body=body), self.assertRaises(ScenarioError):
                Scenario.parse('target="k1"\n[[step]]\n' + body)


class TestShots(unittest.TestCase):
    def test_ppm_conversion_degrades(self):
        tmp = Path(tempfile.mkdtemp(prefix="kpharness_shots_"))
        try:
            src = tmp / "a.ppm"
            src.write_bytes(b"P6\n2 1\n255\n" + bytes([255, 0, 0, 0, 255, 0]))
            out = ppm_to_png(src, tmp / "a.png")
            if have_pillow():
                self.assertEqual(out.suffix, ".png")
                self.assertTrue(out.read_bytes().startswith(b"\x89PNG"))
            else:
                self.assertEqual(out.suffix, ".ppm")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_best_match_is_fuzzy(self):
        ratio, which = best_match("WH0 ARE Y0U?\nlets go\n", ["Who are you?", "Get away from me."])
        self.assertEqual(which, "Who are you?")
        self.assertGreater(ratio, 0.6)
        ratio, _ = best_match("nothing alike here", ["Who are you?"])
        self.assertLess(ratio, 0.6)


class TestPioneer(unittest.TestCase):
    """The CLI-TAS route file: only what got a live "ok" result is ever
    written, and the appended text has to be exactly what Scenario.parse
    replays -- these cover the string/file-shape half; live `step` execution
    is exercised by the pioneer smoke test against a real session."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kpharness_pioneer_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = self.tmp / "route.toml"

    def test_render_step_matches_hand_written_route_style(self):
        text = P.render_step({"do": "lua", "code": 'return 1+1; -- "quoted"', "timeout": 20})
        self.assertEqual(text, '[[step]]\ndo = "lua"\ncode = "return 1+1; -- \\"quoted\\""\ntimeout = 20\n')

    def test_render_step_covers_bool_float_list(self):
        text = P.render_step({"wait": "phase_any", "equals": ["gameplay", "dialog"],
                              "progress": True, "timeout": 12.5})
        self.assertIn('equals = ["gameplay", "dialog"]', text)
        self.assertIn("progress = true", text)
        self.assertIn("timeout = 12.5", text)

    def test_render_step_rejects_non_finite_float(self):
        with self.assertRaises(P.PioneerError):
            P.render_step({"do": "sleep", "seconds": float("nan")})

    def test_init_then_append_round_trips_through_scenario_parse(self):
        P.init_route(self.out, target="k1", name="pioneer test", authored_barks=[37, 48])
        P.append_step(self.out, {"do": "lua", "code": "return 1"})
        P.append_step(self.out, {"wait": "phase", "equals": "gameplay", "timeout": 30})
        sc = Scenario.load(self.out)
        self.assertEqual(sc.name, "pioneer test")
        self.assertEqual(sc.target, "k1")
        self.assertEqual(sc.settings["authored_barks"], [37, 48])
        self.assertEqual(len(sc.steps), 2)
        self.assertEqual(sc.steps[0].raw["do"], "lua")
        self.assertEqual(sc.steps[1].raw["wait"], "phase")

    def test_init_refuses_to_clobber_without_force(self):
        P.init_route(self.out, target="k1", name="a")
        with self.assertRaises(P.PioneerError):
            P.init_route(self.out, target="k1", name="b")
        P.init_route(self.out, target="k1", name="b", force=True)
        self.assertIn('name = "b"', self.out.read_text())

    def test_append_requires_an_initialised_route(self):
        with self.assertRaises(P.PioneerError):
            P.append_step(self.out, {"do": "lua", "code": "return 1"})

    def test_pending_round_trips_and_clears(self):
        self.assertIsNone(P.load_pending(self.out))
        pending = P.Pending(target="k1", step={"do": "lua", "code": "return 1"},
                            result={"status": "ok"}, recorded_at=1.0)
        P.save_pending(self.out, pending)
        loaded = P.load_pending(self.out)
        self.assertEqual(loaded.step, pending.step)
        self.assertEqual(loaded.result, pending.result)
        P.clear_pending(self.out)
        self.assertIsNone(P.load_pending(self.out))


if __name__ == "__main__":
    unittest.main(verbosity=1)
