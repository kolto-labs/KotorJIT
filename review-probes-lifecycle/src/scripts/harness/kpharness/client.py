"""Channel: the wire protocol client.

Newline-delimited JSON over loopback TCP, one request per line, one reply per
line, event frames interleaved only after `subscribe`. Every request carries
an id and every reply echoes it, so a late reply for an earlier timed-out
request is recognised and dropped rather than mistaken for the current one.

The client keeps an event cursor: the highest `seq` it has seen, from either
an event frame or an `events` reply. Waits use the cursor to ask "did X
happen after the point I started watching", which is the only sound way to
assert ordering across a channel that batches.

Nothing here blocks without a deadline. A reply that does not arrive inside
the per-call timeout raises ChannelTimeout, and the caller decides whether
that is a hang (the oracle) or a slow load (a wait with a longer ceiling).
"""
from __future__ import annotations

import json
import socket
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Sequence


class ChannelError(Exception):
    """The runtime answered ok=false. `error` is its text."""

    def __init__(self, error: str, cmd: str = "", request_id: int = 0):
        super().__init__(error)
        self.error = error
        self.cmd = cmd
        self.request_id = request_id

    @property
    def unsupported(self) -> bool:
        """The build cannot honour the command: a skipped step, not a crash."""
        return self.error.startswith("unsupported on")


class ChannelTimeout(ChannelError):
    """No reply inside the per-call timeout. The connection is left as is."""


class ChannelClosed(ChannelError):
    """The peer closed the connection or the socket failed."""


class Channel:
    """One connection to the harness listener.

    `timeout` is the default per-call ceiling in seconds. `request()` takes a
    per-call override. `events_seen` keeps the last `event_keep` frames that
    arrived while subscribed, so a wait can look at what happened without
    another round trip.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0,
                 timeout: float = 10.0, event_keep: int = 4096):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._buf = b""
        self._next_id = 1
        self.cursor = 0                       # highest event seq seen
        self.events_seen: Deque[dict] = deque(maxlen=event_keep)
        self.subscribed = False
        self.last_status: Optional[dict] = None
        self.last_state: Optional[dict] = None
        # Set by the session which owns the game process.  Generic requests
        # never use this: retrying a command after a broken socket could run a
        # state-changing command twice.  Waits use the dedicated read helpers
        # below for state and event snapshots only.
        self._wait_reconnector: Optional[Callable[["Channel"], object]] = None

    # ------------------------------------------------------------ connect --
    def connect(self, connect_timeout: float = 2.0) -> None:
        self.close()
        s = socket.create_connection((self.host, self.port), timeout=connect_timeout)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = s
        self._buf = b""

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self.subscribed = False

    def set_wait_reconnector(self, reconnect: Optional[Callable[["Channel"], object]]) -> None:
        """Install the session-owned reconnect operation used only by waits.

        The callback must reconnect *this* channel and may return ``False`` to
        decline recovery.  Any other return value means success, provided the
        channel is connected afterwards.  Keeping ownership in ``GameSession``
        lets it check process liveness and use its boot/session policy instead
        of making the wire client silently relaunch a game.
        """
        self._wait_reconnector = reconnect

    def _reconnect_for_wait(self, resume_subscription: bool) -> bool:
        """Reconnect a dropped read-only wait, without replaying a mutation."""
        reconnect = self._wait_reconnector
        if reconnect is None:
            return False
        try:
            result = reconnect(self)
            if result is False or not self.connected:
                self.close()
                return False
            if resume_subscription:
                # `cursor` deliberately survives connect(), so subsequent
                # event reads resume from the same observed boundary.
                self.subscribe()
            return True
        except (OSError, ChannelError):
            self.close()
            return False

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def __enter__(self) -> "Channel":
        if not self.connected:
            self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------ framing --
    def _send_line(self, obj: dict) -> None:
        if self._sock is None:
            raise ChannelClosed("not connected", obj.get("cmd", ""))
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            self._sock.sendall(data)
        except OSError as e:
            self.close()
            raise ChannelClosed(f"send failed: {e}", obj.get("cmd", "")) from e

    def _read_frame(self, deadline: float) -> dict:
        """One complete JSON line, or ChannelTimeout at the deadline."""
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line, self._buf = self._buf[:nl], self._buf[nl + 1:]
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    # A torn line is the peer's bug, not a reason to hang.
                    return {"malformed": line.decode("utf-8", "replace")}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ChannelTimeout("no reply before deadline")
            if self._sock is None:
                raise ChannelClosed("not connected")
            self._sock.settimeout(min(remaining, 1.0))
            try:
                chunk = self._sock.recv(65536)
            except socket.timeout:
                continue
            except OSError as e:
                self.close()
                raise ChannelClosed(f"recv failed: {e}") from e
            if not chunk:
                self.close()
                raise ChannelClosed("peer closed the connection")
            self._buf += chunk

    def _note_event(self, frame: dict) -> None:
        seq = frame.get("seq")
        if isinstance(seq, int) and seq > self.cursor:
            self.cursor = seq
        self.events_seen.append(frame)

    # ------------------------------------------------------------ request --
    def request(self, cmd: str, timeout: Optional[float] = None, **args: Any) -> Any:
        """Send `cmd` with `args`, return `result`, raise ChannelError on ok=false."""
        rid = self._next_id
        self._next_id += 1
        req = {"id": rid, "cmd": cmd}
        req.update({k: v for k, v in args.items() if v is not None})
        self._send_line(req)
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            try:
                frame = self._read_frame(deadline)
            except ChannelTimeout:
                raise ChannelTimeout(f"{cmd}: no reply in "
                                     f"{(self.timeout if timeout is None else timeout):.1f}s",
                                     cmd, rid) from None
            if "event" in frame:
                self._note_event(frame)
                continue
            if "malformed" in frame:
                continue
            if frame.get("id") != rid:
                # A stale reply from a call that timed out earlier. Drop it.
                continue
            if frame.get("ok") is True:
                result = frame.get("result")
                if cmd == "status" and isinstance(result, dict):
                    self.last_status = result
                elif cmd == "state" and isinstance(result, dict):
                    self.last_state = result
                return result
            raise ChannelError(str(frame.get("error", "unknown error")), cmd, rid)

    def drain_events(self, budget: float = 0.0) -> List[dict]:
        """Read whatever event frames are already queued, without a request."""
        got: List[dict] = []
        deadline = time.monotonic() + budget
        while True:
            try:
                frame = self._read_frame(deadline)
            except ChannelTimeout:
                break
            except ChannelClosed:
                break
            if "event" in frame:
                self._note_event(frame)
                got.append(frame)
        return got

    # ------------------------------------------------------------ helpers --
    def ping(self) -> dict:
        return self.request("ping")

    def status(self) -> dict:
        return self.request("status")

    def state(self) -> dict:
        return self.request("state")

    def state_for_wait(self) -> dict:
        """Read state for ``wait_until`` and recover one closed connection.

        This is intentionally separate from :meth:`state`: callers issuing a
        one-off request retain the existing explicit failure behavior.
        """
        resume_subscription = self.subscribed
        try:
            return self.state()
        except ChannelClosed:
            if not self._reconnect_for_wait(resume_subscription):
                raise
            return self.state()

    def lua(self, code: str, timeout: Optional[float] = None,
            facing_ids: Optional[Sequence[int]] = None) -> Any:
        """Run a chunk in the harness lua_State.

        ``facing_ids`` is optional request provenance for bounded world probes.
        The Lua chunk remains the enforcement point; carrying the same resolved
        ids over the wire lets a peer/test verify that provenance without
        changing ordinary Lua callers.
        """
        if facing_ids is None:
            return self.request("lua", timeout=timeout, code=code)
        ids = tuple(facing_ids)
        if any(isinstance(value, bool) or not isinstance(value, int)
               or not 0 <= value <= 0xffffffff for value in ids):
            raise ValueError("facing_ids must contain unsigned object ids")
        return self.request("lua", timeout=timeout, code=code, facing_ids=list(ids))

    def events(self, since: Optional[int] = None, limit: int = 200) -> List[dict]:
        """Events after `since` (default: the cursor). Advances the cursor."""
        start = self.cursor if since is None else since
        reply = self.request("events", since=start, limit=limit)
        return self._note_events_reply(reply)

    def _note_events_reply(self, reply: Any) -> List[dict]:
        items = list(reply.get("items", [])) if isinstance(reply, dict) else []
        last = reply.get("seq") if isinstance(reply, dict) else None
        for it in items:
            self._note_event(it)
        if isinstance(last, int) and last > self.cursor:
            self.cursor = last
        return items

    def events_for_wait(self, since: Optional[int] = None, limit: int = 200) -> List[dict]:
        """Read the event ring for a wait and recover one closed connection.

        ``events`` is idempotent for a fixed ``since`` cursor, so retrying it
        cannot duplicate a game action.  The normal public ``events`` helper
        deliberately does not reconnect.
        """
        start = self.cursor if since is None else since
        resume_subscription = self.subscribed
        try:
            reply = self.request("events", since=start, limit=limit)
        except ChannelClosed:
            if not self._reconnect_for_wait(resume_subscription):
                raise
            reply = self.request("events", since=start, limit=limit)
        return self._note_events_reply(reply)

    def subscribe(self) -> None:
        self.request("subscribe")
        self.subscribed = True

    def unsubscribe(self) -> None:
        try:
            self.request("unsubscribe")
        finally:
            self.subscribed = False

    def recent_events(self, n: int = 200) -> List[dict]:
        return list(self.events_seen)[-n:]

    def screenshot(self, path: str, timeout: Optional[float] = None) -> Any:
        return self.request("screenshot", timeout=timeout, path=path)

    def equipment_screen(self, visible: bool) -> Any:
        return self.request("equipment_screen", visible=visible)

    def quit(self) -> None:
        try:
            self.request("quit", timeout=5.0)
        except ChannelClosed:
            pass
        finally:
            self.close()


def events_after(items: Iterable[dict], seq: int) -> List[dict]:
    return [e for e in items if isinstance(e.get("seq"), int) and e["seq"] > seq]


def event_names(items: Iterable[dict]) -> List[str]:
    return [str(e.get("event", "")) for e in items]


def summarise_state(state: Optional[Dict[str, Any]]) -> str:
    """One line for logs: phase, module, ticks, pc position."""
    if not state:
        return "(no state)"
    pc = state.get("pc") or {}
    pos = ""
    if pc:
        pos = " pc=({:.1f},{:.1f},{:.1f}) hp={}/{}".format(
            float(pc.get("x", 0.0)), float(pc.get("y", 0.0)), float(pc.get("z", 0.0)),
            pc.get("hp"), pc.get("max_hp"))
    return "phase={} module={} server_tick={} client_tick={}{}".format(
        state.get("phase"), state.get("module"), state.get("server_tick"),
        state.get("client_tick"), pos)
