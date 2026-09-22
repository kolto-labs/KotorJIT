"""wait_until and the named predicates over engine state.

A wait polls `state` (and `events` for the event predicate) until the
predicate says yes. The timeout is a ceiling: when it expires the wait
fails with the last state and the recent events attached, so a slow load
and a real hang look different in the report. The watchdog is consulted on
every poll and its verdict pre-empts the ceiling.

Predicates are plain callables `fn(state, channel) -> bool`, so a scenario
step and a Python caller use the same ones:

  phase_is("gameplay")           state.phase
  module_is("end_m01aa")         state.module, case-insensitive
  event_seen("OnAreaEnter", seq) an event after cursor `seq`
  dialog_waiting()               a reply list is up and nothing is pending
  chargen_stage_is("class")      character generation's verified engine route
  global_equals("NAME", 1)       via the `globals` command, else nwscript.call
  journal_state("tag", 10)       via the `journal` command, else nwscript.call

Voice-over waits do not scale with game speed, so while a wait polls in the
dialog phase and the node reports waiting on sound, the wait sends
`dialog_skip`. That is the one command a wait issues on its own.
"""
from __future__ import annotations

import fnmatch
import time
from typing import Any, Callable, Dict, List, Optional

from .client import Channel, ChannelError, ChannelTimeout, ChannelClosed, summarise_state
from .oracle import OracleTrip, Watchdog

Predicate = Callable[[Dict[str, Any], Channel], bool]


class WaitTimeout(Exception):
    def __init__(self, what: str, timeout: float, state: Optional[dict], events: List[dict]):
        super().__init__(f"timeout after {timeout:.0f}s waiting for {what}: {summarise_state(state)}")
        self.what = what
        self.timeout = timeout
        self.state = state
        self.events = events


def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _waiting_on_sound(dialog: Dict[str, Any]) -> bool:
    """The node is still playing its line, so a reply cannot be picked yet.

    The runtime emits this as `waiting_on_sound`: the dialog owner is
    mid-send, which is the engine's VO / node-delay wait. There was never a
    `waiting` field on the wire.
    """
    return bool(dialog.get("waiting_on_sound"))


def _waiting_for_player(dialog: Dict[str, Any]) -> bool:
    """A reply pick would be accepted right now (`waiting_for_player`)."""
    return bool(dialog.get("waiting_for_player"))


def wait_until(channel: Channel, fn: Predicate, timeout: float, *, poll: float = 0.25,
               what: str = "predicate", watchdog: Optional[Watchdog] = None,
               progress: bool = False, on_poll: Optional[Callable[[dict], None]] = None,
               auto_skip_vo: bool = True) -> Dict[str, Any]:
    """Poll until fn(state, channel) is true. Returns the state that satisfied it."""
    deadline = time.monotonic() + timeout
    last: Optional[dict] = None
    if watchdog is not None:
        watchdog.reset_progress()
    while True:
        try:
            state = channel.state_for_wait()
        except ChannelTimeout:
            # Silence may be a slow engine load.  Do not reconnect: the peer
            # has not said the connection is gone, and a second request could
            # only make an in-flight reply stale.
            if watchdog is not None:
                v = watchdog.note_unresponsive()
                if v is not None:
                    raise OracleTrip(v)
            if time.monotonic() >= deadline:
                raise WaitTimeout(what, timeout, last, channel.recent_events(200))
            time.sleep(poll)
            continue
        except ChannelClosed:
            # state_for_wait already made one session-owned reconnect attempt.
            # A persistent close follows the old bounded wait/oracle path;
            # unlike a timeout it never triggers a hidden reconnect here.
            if watchdog is not None:
                v = watchdog.note_unresponsive()
                if v is not None:
                    raise OracleTrip(v)
            if time.monotonic() >= deadline:
                raise WaitTimeout(what, timeout, last, channel.recent_events(200))
            time.sleep(poll)
            continue
        last = state
        if on_poll is not None:
            on_poll(state)
        if watchdog is not None:
            v = watchdog.check(state, waiting_on_progress=progress)
            if v is not None:
                raise OracleTrip(v)
        if fn(state, channel):
            return state
        dialog = _as_dict(state.get("dialog"))
        if auto_skip_vo and state.get("phase") == "dialog" and dialog and _waiting_on_sound(dialog):
            try:
                channel.request("dialog_skip", timeout=5.0)
            except ChannelError:
                pass
        if time.monotonic() >= deadline:
            raise WaitTimeout(what, timeout, last, channel.recent_events(200))
        time.sleep(poll)


# ------------------------------------------------------------ predicates --

def phase_is(name: str) -> Predicate:
    def fn(state: Dict[str, Any], _: Channel) -> bool:
        return state.get("phase") == name
    fn.__name__ = f"phase_is({name})"
    return fn

def phase_is_any(names: Sequence[str]) -> Predicate:
    # A fresh module can legitimately enter its opening conversation before a
    # polling interval observes free gameplay. Both states prove a live module;
    # callers still make dialogue-specific assertions before selecting replies.
    wanted = {str(name).lower() for name in names}
    def fn(state: Dict[str, Any], _: Channel) -> bool:
        return str(state.get("phase") or "").lower() in wanted
    fn.__name__ = f"phase_is_any({','.join(sorted(wanted))})"
    return fn


def chargen_open() -> Predicate:
    """True when the engine-owned panel created by ``new_game`` is still listed."""
    def fn(state: Dict[str, Any], _: Channel) -> bool:
        detail = _as_dict(state.get("phase_detail"))
        return detail.get("chargen") == 1
    fn.__name__ = "chargen_open()"
    return fn


def chargen_stage_is(stage: str) -> Predicate:
    """True when the verified character-generation panel route is at ``stage``."""
    def fn(state: Dict[str, Any], _: Channel) -> bool:
        return state.get("chargen_stage") == stage
    fn.__name__ = f"chargen_stage_is({stage})"
    return fn


def module_is(name: str) -> Predicate:
    want = name.lower()
    def fn(state: Dict[str, Any], _: Channel) -> bool:
        return str(state.get("module") or "").lower() == want
    fn.__name__ = f"module_is({name})"
    return fn


def event_seen(name: str, after_seq: int) -> Predicate:
    """True once an event named `name` with seq > after_seq has been seen.

    Pulls the ring through `events` so it does not depend on `subscribe`.
    """
    def fn(_: Dict[str, Any], channel: Channel) -> bool:
        for e in channel.events_seen:
            if e.get("event") == name and isinstance(e.get("seq"), int) and e["seq"] > after_seq:
                return True
        since = after_seq
        while True:
            items = channel.events_for_wait(since=since, limit=500)
            if not items:
                return False
            for e in items:
                if e.get("event") == name and isinstance(e.get("seq"), int) and e["seq"] > after_seq:
                    return True
            last = max((e.get("seq", since) for e in items if isinstance(e.get("seq"), int)),
                       default=since)
            if last <= since:
                return False
            since = last
    fn.__name__ = f"event_seen({name}, >{after_seq})"
    return fn


EventSpec = Any  # a name, or {"event": name, "<field>": glob, ...}


def event_matches(spec: EventSpec, e: Dict[str, Any]) -> bool:
    """A name matches on `event`; a table matches every field it names,
    with shell-style globs, so {"event": "OnRunScript", "script": "k_pend_*"}
    is "any Endar Spire script"."""
    if isinstance(spec, str):
        return e.get("event") == spec
    if not isinstance(spec, dict):
        return False
    for k, want in spec.items():
        have = e.get(k)
        if isinstance(want, str):
            if not fnmatch.fnmatchcase(str(have if have is not None else ""), want):
                return False
        elif have != want:
            return False
    return True


def spec_name(spec: EventSpec) -> str:
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        return " ".join(f"{k}={v}" for k, v in spec.items())
    return str(spec)


def events_in_order(names: List[EventSpec], after_seq: int) -> Predicate:
    """True once `names` appear as a subsequence of events after `after_seq`."""
    def fn(_: Dict[str, Any], channel: Channel) -> bool:
        seen = [e for e in channel.events_seen
                if isinstance(e.get("seq"), int) and e["seq"] > after_seq]
        if not seen or seen[0]["seq"] > after_seq + 1:
            # The local ring may have gaps; refill from the runtime's ring.
            since = after_seq
            pulled: List[dict] = []
            while True:
                items = channel.events_for_wait(since=since, limit=500)
                if not items:
                    break
                pulled += items
                last = max((e.get("seq", since) for e in items if isinstance(e.get("seq"), int)),
                           default=since)
                if last <= since:
                    break
                since = last
            seen = sorted({e.get("seq"): e for e in seen + pulled}.values(),
                          key=lambda e: e.get("seq", 0))
        i = 0
        for e in seen:
            if i < len(names) and event_matches(names[i], e):
                i += 1
        return i == len(names)
    fn.__name__ = "events_in_order(" + ", ".join(spec_name(n) for n in names) + ")"
    return fn


def dialog_entry_is(entry: int) -> Predicate:
    def fn(state: Dict[str, Any], _: Channel) -> bool:
        dialog = _as_dict(state.get("dialog"))
        return bool(dialog) and int(dialog.get("entry", -1)) == entry
    fn.__name__ = f"dialog_entry_is({entry})"
    return fn


def dialog_waiting() -> Predicate:
    def fn(state: Dict[str, Any], _: Channel) -> bool:
        d = _as_dict(state.get("dialog"))
        if not d:
            return False
        replies = d.get("replies") or []
        # Not gated on waiting_for_player: that is reply_accepted(), which is
        # false whenever any of its seven reads is unknown. A build whose owner
        # chain does not resolve should skip `reply` by name, not time out in
        # the wait before it.
        return len(replies) > 0 and not _waiting_on_sound(d)
    fn.__name__ = "dialog_waiting()"
    return fn


def read_global(channel: Channel, name: str) -> Any:
    """Value of a global by name: the `globals` command, else the routine bridge.

    `globals` walks the whole table and answers with three typed maps,
    `{bools, numbers, strings}`, keyed by name. It takes no arguments. Names
    are matched without case, because the table stores them as the scripts
    wrote them.
    """
    try:
        r = channel.request("globals")
        if isinstance(r, dict):
            want = name.lower()
            for kind in ("bools", "numbers", "strings"):
                table = r.get(kind)
                if isinstance(table, dict):
                    for key, value in table.items():
                        if str(key).lower() == want:
                            return value
    except ChannelError as e:
        if not (e.unsupported or "unknown" in e.error or "no such" in e.error):
            raise
    code = ("local n = %r; local ok, v = pcall(nwscript.call, 'GetGlobalNumber', n); "
            "local ok2, b = pcall(nwscript.call, 'GetGlobalBoolean', n); "
            "if ok and v ~= nil and v ~= 0 then return v end; "
            "if ok2 and b ~= nil then return b end; return v") % name
    return channel.lua(code)


def _loose_equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def global_equals(name: str, value: Any) -> Predicate:
    def fn(_: Dict[str, Any], channel: Channel) -> bool:
        return _loose_equal(read_global(channel, name), value)
    fn.__name__ = f"global_equals({name}, {value!r})"
    return fn


def read_journal_state(channel: Channel, tag: str) -> Any:
    try:
        r = channel.request("journal")
        entries = r.get("items", r.get("entries", [])) if isinstance(r, dict) else r
        if isinstance(entries, list):
            for e in entries:
                if isinstance(e, dict) and str(e.get("tag", "")).lower() == tag.lower():
                    return e.get("state")
            return None
    except ChannelError as e:
        if not (e.unsupported or "unknown" in e.error or "no such" in e.error):
            raise
    code = ("local t = %r; local ok, v = pcall(function() return nwscript.call(\"GetJournalEntry\",t) end); "
            "if ok then return v end; return nil") % tag
    return channel.lua(code)


def journal_state(tag: str, state: Any) -> Predicate:
    def fn(_: Dict[str, Any], channel: Channel) -> bool:
        return _loose_equal(read_journal_state(channel, tag), state)
    fn.__name__ = f"journal_state({tag}, {state!r})"
    return fn


def all_of(*preds: Predicate) -> Predicate:
    def fn(state: Dict[str, Any], channel: Channel) -> bool:
        return all(p(state, channel) for p in preds)
    fn.__name__ = "all_of(" + ", ".join(getattr(p, "__name__", "?") for p in preds) + ")"
    return fn
