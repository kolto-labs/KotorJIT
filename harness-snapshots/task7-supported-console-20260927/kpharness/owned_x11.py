"""Linux-only physical keyboard input for a newly owned X11 game display."""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


class OwnedInputError(RuntimeError):
    pass


class UnsupportedOwnedInput(OwnedInputError):
    pass


_WINDOW = re.compile(r"^0x[0-9a-fA-F]+$")
_DISPLAY = re.compile(r"^:(?P<number>0|[1-9][0-9]*)(?:\.(?P<screen>0|[1-9][0-9]*))?$")


@dataclass(frozen=True)
class OwnedX11Target:
    window: str
    env: Mapping[str, str]


class OwnedX11Input:
    """Input adapter anchored to the session's freshly owned display/window.

    Routes never supply a window or DISPLAY.  The adapter obtains both from the
    booted session and refuses when it cannot prove that a live harness display
    owns them, which prevents accidental input to a user's desktop.
    """

    def __init__(self, target: OwnedX11Target, *, runner: Callable[..., Any] = subprocess.run):
        self.target = target
        self._run = runner

    @classmethod
    def from_session(cls, session: Any, *, runner: Callable[..., Any] = subprocess.run) -> "OwnedX11Input":
        if not sys.platform.startswith("linux"):
            raise UnsupportedOwnedInput("physical console input is supported only on Linux owned X11")
        env = getattr(session, "env", None)
        capture = getattr(session, "capture_owned_game_window", None)
        if callable(capture):
            capture()
        window = getattr(session, "capture_window", None)
        display = env.get("DISPLAY") if isinstance(env, Mapping) else None
        server = getattr(session, "xvfb", None)
        parsed = _DISPLAY.fullmatch(display) if isinstance(display, str) else None
        if parsed is None:
            raise OwnedInputError("refusing input: session has no owned X11 DISPLAY")
        if not isinstance(window, str) or not _WINDOW.fullmatch(window):
            raise OwnedInputError("refusing input: session has no verified owned game window")
        if server is None or not hasattr(server, "poll") or server.poll() is not None:
            raise OwnedInputError("refusing input: session owned display is not live")
        expected_display = getattr(session, "display", None)
        if not isinstance(expected_display, int) or int(parsed.group("number")) != expected_display:
            raise OwnedInputError("refusing input: window display differs from session-owned display")
        return cls(OwnedX11Target(window=window, env=dict(env)), runner=runner)

    def _command(self, args: Sequence[str], *, timeout: float = 5.0) -> None:
        try:
            self._run(list(args), env=dict(self.target.env), check=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as error:
            raise OwnedInputError(f"owned X11 input failed: {error}") from error

    def focus(self) -> None:
        self._command(("xdotool", "windowfocus", "--sync", self.target.window))

    def key(self, key: str) -> None:
        if not isinstance(key, str) or not key:
            raise OwnedInputError("owned input key must be non-empty")
        self._command(("xdotool", "key", key))

    def type(self, text: str, *, delay_ms: int = 2) -> None:
        if not isinstance(text, str) or len(text) > 16000:
            raise OwnedInputError("owned input text must be a string of at most 16000 characters")
        if isinstance(delay_ms, bool) or not isinstance(delay_ms, int) or not 0 <= delay_ms <= 1000:
            raise OwnedInputError("owned input delay_ms must be an integer from 0 to 1000")
        self._command(("xdotool", "type", "--clearmodifiers", "--delay", str(delay_ms), "--", text), timeout=60)

    def action(self, action: str, raw: Mapping[str, Any]) -> None:
        self.focus()
        if action == "type":
            self.type(str(raw.get("text", "")), delay_ms=int(raw.get("delay_ms", 8)))
        elif action in ("key", "keydown", "keyup"):
            self.key(str(raw.get("key", raw.get("button", "Return")))) if action == "key" else \
                self._command(("xdotool", action, str(raw.get("key", raw.get("button", "Return")))))
        elif action == "mousemove":
            self._command(("xdotool", "mousemove", "--window", self.target.window,
                           str(int(raw["x"])), str(int(raw["y"]))))
        elif action == "click":
            self._command(("xdotool", "click", str(int(raw.get("button", 1)))))
        else:
            raise OwnedInputError(f"unsupported owned input action {action!r}")

    def submit_console(self, code: str, *, keys_before_submit: Sequence[str] = (),
                       suffix: str = "", delay_ms: int = 2) -> None:
        if not isinstance(code, str):
            raise OwnedInputError("console code must be a string")
        self.focus()
        self.key("ctrl+a")
        for index, part in enumerate(code.split("\n")):
            if index:
                self.key("ctrl+Return")
            if part:
                self.type(part, delay_ms=delay_ms)
        for key in keys_before_submit:
            self.key(str(key))
        if suffix:
            self.type(suffix, delay_ms=5)
        self.key("Return")

    # The physical-console boundary depends only on these narrow operations.
    # Its one type_text call may internally preserve the overlay's Ctrl+Enter
    # multiline convention; it still has exactly one later Enter submission.
    def focus_owned_game_window(self) -> None:
        self.focus()

    def press_f12(self) -> None:
        self.key("F12")

    def select_all(self) -> None:
        self.key("ctrl+a")

    def type_text(self, source: str) -> None:
        if not isinstance(source, str):
            raise OwnedInputError("console source must be a string")
        for index, part in enumerate(source.split("\n")):
            if index:
                self.key("ctrl+Return")
            if part:
                self.type(part, delay_ms=2)

    def press_enter(self) -> None:
        self.key("Return")

    def console_entry(self, *, keys_before_submit: Sequence[str] = (), suffix: str = "") -> "ConsoleEntryInput":
        """Return immutable per-command editing behavior for history/completion.

        The physical driver still has one ``type_text`` phase and one Enter;
        this wrapper merely makes real overlay editing keys part of that phase.
        """
        if not isinstance(suffix, str):
            raise OwnedInputError("console suffix must be a string")
        if isinstance(keys_before_submit, str) or not isinstance(keys_before_submit, (list, tuple)):
            raise OwnedInputError("keys_before_submit must be an array of non-empty key names")
        if len(keys_before_submit) > 64 or any(not isinstance(key, str) or not key for key in keys_before_submit):
            raise OwnedInputError("keys_before_submit must contain at most 64 non-empty key names")
        return ConsoleEntryInput(self, tuple(keys_before_submit), suffix)


@dataclass(frozen=True)
class ConsoleEntryInput:
    """One command's editing modifiers; it does not mutate session state."""
    base: OwnedX11Input
    keys_before_submit: tuple[str, ...]
    suffix: str

    def focus_owned_game_window(self) -> None:
        self.base.focus_owned_game_window()

    def press_f12(self) -> None:
        self.base.press_f12()

    def select_all(self) -> None:
        self.base.select_all()

    def type_text(self, source: str) -> None:
        self.base.type_text(source)
        for key in self.keys_before_submit:
            self.base.key(key)
        if self.suffix:
            self.base.type(self.suffix, delay_ms=5)

    def press_enter(self) -> None:
        self.base.press_enter()
