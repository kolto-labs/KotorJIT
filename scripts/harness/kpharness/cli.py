"""kpharness: boot a headless game, ask it things, run scenarios, tear down.

  kpharness boot   --target k1            stage, boot, connect, leave running
  kpharness status [--target k1]          discovery facts, or `status` if booted
  kpharness state  [--target k1]          the engine state snapshot
  kpharness reply  --target k1 INDEX      choose one current dialog reply
  kpharness exec   [--target k1] CODE     run a Lua chunk over the channel
  kpharness events [--target k1]          events since a cursor
  kpharness shots  [--target k1]          take one screenshot now
  kpharness run    SCENARIO [--target k1] boot, execute, tear down, report
  kpharness down   [--target k1]          tear a booted session down

  kpharness pioneer init   --out R.toml --target k1 --name "..."
  kpharness pioneer step   --out R.toml '{"do": "lua", "code": "..."}'
  kpharness pioneer commit --out R.toml
  kpharness pioneer discard --out R.toml
  kpharness pioneer status --out R.toml
    A CLI TAS: pioneer a route on a booted session one verified step at a
    time. `step` runs the given step body now over the real dispatch path a
    scenario run uses and prints the result; `commit` appends exactly that
    already-inspected step to R.toml. Nothing is written to the route file
    on a whim -- only what was just executed and looked at.

A booted session leaves tmp/<target>_harness/session.json behind; the
other commands find the port there. `run` does the whole cycle itself.
Exit status: 0 on success, 1 on a scenario or command failure, 2 on a boot
failure, 3 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from . import discover, pioneer as P, scenario as S, targets as T
from .checkpoints import Checkpoints
from .client import Channel, ChannelError, summarise_state
from .session import channel_timeout, BootFailure, GameSession, LockHeld, SessionInfo, teardown_from_info
from .shots import Shooter


def _info(target: str) -> Optional[SessionInfo]:
    t = T.get(target)
    root = discover.repo_root() / "tmp"
    for name in (f"{t.name}_harness", f"{t.game}_harness"):
        p = GameSession.session_info_path(root / name)
        if p.is_file():
            try:
                return SessionInfo.from_dict(json.loads(p.read_text()))
            except (OSError, ValueError, TypeError):
                continue
    return None


def _channel(target: str) -> Channel:
    info = _info(target)
    if info is None:
        raise SystemExit(f"no booted session for {target}; run `kpharness boot --target {target}`")
    ch = Channel("127.0.0.1", info.port, timeout=channel_timeout())
    ch.connect()
    return ch


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, default=str))


# ------------------------------------------------------------- commands --

def cmd_boot(a: argparse.Namespace) -> int:
    s = GameSession(a.target, build_dir=a.build_dir, display=a.display, port=a.port,
                    boot_timeout=a.boot_timeout, force=a.force, wine_debug=a.wine_debug,
                    staged=a.staged, wineprefix=a.wineprefix, persistent=True)
    try:
        ch = s.boot()
    except (BootFailure, LockHeld, FileNotFoundError) as e:
        print(f"boot failed: {e}", file=sys.stderr)
        return 2
    _print({"port": s.port, "display": s.display, "run_dir": str(s.run_dir),
            "status": ch.status()})
    ch.close()
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    info = _info(a.target)
    if info is None:
        _print(discover.describe(T.get(a.target)))
        return 0
    try:
        with _channel(a.target) as ch:
            _print({"session": info.to_dict(), "status": ch.status()})
    except (OSError, ChannelError) as e:
        _print({"session": info.to_dict(), "error": str(e)})
        return 1
    return 0


def cmd_state(a: argparse.Namespace) -> int:
    with _channel(a.target) as ch:
        _print(ch.state())
    return 0


def cmd_reply(a: argparse.Namespace) -> int:
    with _channel(a.target) as ch:
        _print(ch.request("reply", index=a.index, timeout=a.timeout))
    return 0


def cmd_exec(a: argparse.Namespace) -> int:
    code = " ".join(a.code)
    with _channel(a.target) as ch:
        try:
            _print(ch.lua(code, timeout=a.timeout))
        except ChannelError as e:
            print(f"error: {e.error}", file=sys.stderr)
            return 1
    return 0


def cmd_events(a: argparse.Namespace) -> int:
    with _channel(a.target) as ch:
        _print(ch.events(since=a.since, limit=a.limit))
    return 0


def cmd_shots(a: argparse.Namespace) -> int:
    info = _info(a.target)
    if info is None:
        raise SystemExit(f"no booted session for {a.target}")
    with _channel(a.target) as ch:
        sh = Shooter(ch, Path(info.game_dir), Path(info.run_dir), interval=0, log=print)
        p = sh.take(a.label or "manual")
        print(p or "no screenshot")
    return 0 if p else 1


def cmd_down(a: argparse.Namespace) -> int:
    info = _info(a.target)
    if info is None:
        print(f"no booted session for {a.target}")
        return 0
    teardown_from_info(info)
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    try:
        path = S.find_scenario(a.scenario)
        sc = S.Scenario.load(path)
    except S.ScenarioError as e:
        print(f"scenario: {e}", file=sys.stderr)
        return 3
    target = a.target or sc.target
    s = GameSession(target, build_dir=a.build_dir, display=a.display, port=a.port,
                    boot_timeout=a.boot_timeout, force=a.force, wine_debug=a.wine_debug,
                    staged=a.staged, wineprefix=a.wineprefix, reset_saves=True)
    try:
        ch = s.boot(resources=list(sc.resources.values()))
    except (BootFailure, LockHeld, FileNotFoundError) as e:
        print(f"boot failed: {e}", file=sys.stderr)
        return 2
    try:
        cps = Checkpoints(s.target, s.save_dir) if s.save_dir else None
        runner = S.ScenarioRunner(sc, s, ch, log=s.log, checkpoints=cps)
        rep = runner.run()
    finally:
        s.teardown()
    print(f"{sc.name}: {'PASS' if rep.ok else 'FAIL'} "
          f"({sum(1 for x in rep.steps if x.status == 'ok')} ok, "
          f"{sum(1 for x in rep.steps if x.status == 'skipped')} skipped, "
          f"{sum(1 for x in rep.steps if x.status == 'expected_failure')} expected failures, "
          f"{sum(1 for x in rep.steps if x.status == 'failed')} failed) -> {rep.run_dir}/report.json")
    if rep.verdict:
        print(f"verdict: {rep.verdict.get('kind')}: {rep.verdict.get('reason')}")
    if rep.error:
        print(f"error: {rep.error}")
    return 0 if rep.ok else 1


def cmd_pioneer_init(a: argparse.Namespace) -> int:
    barks = json.loads(a.authored_barks) if a.authored_barks else None
    try:
        P.init_route(Path(a.out), target=a.target, name=a.name or Path(a.out).stem,
                    authored_barks=barks, force=a.force)
    except P.PioneerError as e:
        print(f"pioneer init: {e}", file=sys.stderr)
        return 1
    print(f"{a.out}: initialised for {a.target}")
    return 0


def cmd_pioneer_step(a: argparse.Namespace) -> int:
    try:
        step_body = json.loads(a.step)
    except json.JSONDecodeError as e:
        print(f"pioneer step: step body is not valid JSON: {e}", file=sys.stderr)
        return 3
    if not isinstance(step_body, dict):
        print("pioneer step: step body must be a JSON object", file=sys.stderr)
        return 3
    out = Path(a.out)
    info = _info(a.target)
    if info is None:
        raise SystemExit(f"no booted session for {a.target}; run `kpharness boot --target {a.target}`")
    try:
        with Channel("127.0.0.1", info.port, timeout=channel_timeout()) as ch:
            result = P.run_one_step(out, ch, info, step_body, log=print)
    except P.PioneerError as e:
        print(f"pioneer step: {e}", file=sys.stderr)
        return 1
    _print(result.to_dict())
    P.save_pending(out, P.Pending(target=a.target, step=step_body,
                                   result=result.to_dict(), recorded_at=time.time()))
    if result.status == "ok":
        print(f"pending: `pioneer commit --out {a.out}` to append this step, "
              f"or `pioneer discard --out {a.out}` to drop it.")
    else:
        print(f"step did not succeed (status={result.status}); nothing will be committed "
              "unless you commit it deliberately.")
    return 0 if result.status == "ok" else 1


def cmd_pioneer_commit(a: argparse.Namespace) -> int:
    out = Path(a.out)
    pending = P.load_pending(out)
    if pending is None:
        print(f"pioneer commit: no pending step for {out} (run `pioneer step` first)",
              file=sys.stderr)
        return 1
    # run_step already distinguishes a declared-expected failure
    # (status="expected_failure", from expect_error/expect_verdict) from a
    # genuine one ("failed"); only a genuine failure needs --force. The whole
    # point of pioneering is never baking in a step that was not actually
    # verified to do what the route now claims it does.
    status = pending.result.get("status")
    if status == "failed" and not a.force:
        print(f"pioneer commit: refusing to commit a step whose last run failed; "
              "rerun `pioneer step` until it succeeds, or pass --force to commit it anyway",
              file=sys.stderr)
        return 1
    try:
        P.append_step(out, pending.step)
    except P.PioneerError as e:
        print(f"pioneer commit: {e}", file=sys.stderr)
        return 1
    P.clear_pending(out)
    print(f"{out}: appended {pending.step.get('do') or pending.step.get('wait') or 'step'}")
    return 0


def cmd_pioneer_discard(a: argparse.Namespace) -> int:
    out = Path(a.out)
    if P.load_pending(out) is None:
        print(f"pioneer discard: no pending step for {out}")
        return 0
    P.clear_pending(out)
    print(f"{out}: pending step discarded")
    return 0


def cmd_pioneer_status(a: argparse.Namespace) -> int:
    out = Path(a.out)
    pending = P.load_pending(out)
    info = _info(a.target)
    live_state = None
    if info is not None:
        try:
            with Channel("127.0.0.1", info.port, timeout=channel_timeout()) as ch:
                live_state = summarise_state(ch.state())
        except (OSError, ChannelError):
            live_state = None
    _print({"route": str(out), "pending": pending.to_dict() if pending else None,
            "live_state": live_state})
    return 0


def cmd_pioneer_transport(a: argparse.Namespace) -> int:
    """Live pause/play/ff/rewind; optionally hold as a pending pioneer step."""
    verb = a.pioneer_cmd
    try:
        step_body = P.transport_step(verb, scale=getattr(a, "scale", None),
                                     checkpoint=getattr(a, "checkpoint", None))
    except P.PioneerError as e:
        print(f"pioneer {verb}: {e}", file=sys.stderr)
        return 1
    info = _info(a.target)
    if info is None:
        raise SystemExit(f"no booted session for {a.target}; run `kpharness boot --target {a.target}`")
    out = Path(a.out) if a.out else None
    try:
        with Channel("127.0.0.1", info.port, timeout=channel_timeout()) as ch:
            if out is not None:
                result = P.run_one_step(out, ch, info, step_body, log=print)
            else:
                # No route file: still go through ScenarioRunner via a throwaway
                # in-memory step so verb dispatch stays singular.
                import tempfile
                tmp = Path(tempfile.mkdtemp(prefix="kp_transport_")) / "route.toml"
                P.init_route(tmp, target=a.target, name=f"transport-{verb}")
                try:
                    result = P.run_one_step(tmp, ch, info, step_body, log=print)
                finally:
                    import shutil
                    shutil.rmtree(tmp.parent, ignore_errors=True)
    except P.PioneerError as e:
        print(f"pioneer {verb}: {e}", file=sys.stderr)
        return 1
    _print(result.to_dict())
    if out is not None:
        P.save_pending(out, P.Pending(target=a.target, step=step_body,
                                       result=result.to_dict(), recorded_at=time.time()))
        if result.status == "ok":
            print(f"pending: `pioneer commit --out {a.out}` to append this step")
    return 0 if result.status == "ok" else 1


def cmd_list(_: argparse.Namespace) -> int:
    for p in S.list_scenarios():
        name = p.relative_to(S.scenario_dir()).with_suffix("").as_posix()
        try:
            sc = S.Scenario.load(p)
            print(f"{name:24} {sc.target:10} {sc.name}")
        except S.ScenarioError as e:
            print(f"{name:24} (invalid: {e})")
    return 0


# ----------------------------------------------------------------- main --

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kpharness", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def target_arg(p: argparse.ArgumentParser, required: bool = False, default: Optional[str] = "k1"):
        p.add_argument("--target", "-t", choices=T.names() + ["k2"], required=required,
                       default=default, help="k1, k2-wine, or k2-native (k2 is k2-native)")

    def boot_args(p: argparse.ArgumentParser):
        p.add_argument("--build-dir", help="where kphasor.dll / libkphasor.so were built")
        p.add_argument("--staged", help="harness staging tree; KP_STAGED_DIR when omitted")
        p.add_argument("--wineprefix", help="dedicated Wine prefix; KP_WINEPREFIX when omitted")
        p.add_argument("--display", type=int, help="X display number; default: first free")
        p.add_argument("--port", type=int, help="listener port; default: a free one")
        p.add_argument("--boot-timeout", type=float, default=300.0,
                       help="ceiling for the channel to answer status")
        p.add_argument("--force", action="store_true", help="take a held display lock")
        p.add_argument("--wine-debug", help="WINEDEBUG value; default -all")

    p = sub.add_parser("boot", help="stage, boot, connect, leave running")
    target_arg(p); boot_args(p); p.set_defaults(fn=cmd_boot)

    p = sub.add_parser("status", help="discovery facts, or status if booted")
    target_arg(p); p.set_defaults(fn=cmd_status)

    p = sub.add_parser("state", help="the engine state snapshot")
    target_arg(p); p.set_defaults(fn=cmd_state)

    p = sub.add_parser("reply", help="choose one current dialog reply")
    target_arg(p); p.add_argument("index", type=int)
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(fn=cmd_reply)

    p = sub.add_parser("exec", help="run a Lua chunk over the channel")
    target_arg(p)
    p.add_argument("code", nargs="+", help="Lua source; use `return ...` for a value")
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(fn=cmd_exec)

    p = sub.add_parser("events", help="events since a cursor")
    target_arg(p)
    p.add_argument("--since", type=int, default=0)
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(fn=cmd_events)

    p = sub.add_parser("shots", help="take one screenshot now")
    target_arg(p)
    p.add_argument("--label", default="")
    p.set_defaults(fn=cmd_shots)

    p = sub.add_parser("run", help="boot, run a scenario, tear down")
    p.add_argument("scenario", help="name under scripts/harness/scenarios or a path")
    target_arg(p, default=None); boot_args(p); p.set_defaults(fn=cmd_run)

    p = sub.add_parser("down", help="tear a booted session down")
    target_arg(p); p.set_defaults(fn=cmd_down)

    p = sub.add_parser("list", help="scenarios available")
    p.set_defaults(fn=cmd_list)

    pio = sub.add_parser("pioneer", help="pioneer a route interactively, one verified step at a time")
    pio_sub = pio.add_subparsers(dest="pioneer_cmd", required=True)

    p = pio_sub.add_parser("init", help="create a new route file")
    target_arg(p, required=True)
    p.add_argument("--out", required=True, help="route TOML to create")
    p.add_argument("--name", help="scenario name; defaults to the file stem")
    p.add_argument("--authored-barks", help="JSON list of dialog entry ints, e.g. [37,48]")
    p.add_argument("--force", action="store_true", help="overwrite an existing route file")
    p.set_defaults(fn=cmd_pioneer_init)

    p = pio_sub.add_parser("step", help="execute one step body live and hold it pending")
    target_arg(p)
    p.add_argument("--out", required=True, help="route TOML being pioneered")
    p.add_argument("step", help='step body as JSON, e.g. \'{"do":"lua","code":"..."}\'')
    p.set_defaults(fn=cmd_pioneer_step)

    p = pio_sub.add_parser("commit", help="append the pending step to the route file")
    p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true",
                   help="commit even though the pending step's last run failed")
    p.set_defaults(fn=cmd_pioneer_commit)

    p = pio_sub.add_parser("discard", help="drop the pending step without writing it")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pioneer_discard)

    p = pio_sub.add_parser("status", help="show the pending step and live engine state")
    target_arg(p)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pioneer_status)

    for verb, help_text in (
        ("pause", "near-freeze via harness speed (default scale 0.001)"),
        ("play", "resume at 1x and clear auto-pause / timers"),
        ("ff", "fast-forward (default scale 4)"),
        ("rewind", "restore a named checkpoint and load_save"),
    ):
        p = pio_sub.add_parser(verb, help=help_text)
        target_arg(p)
        p.add_argument("--out", help="optional route TOML; when set, holds a pending step")
        if verb in ("pause", "play", "ff"):
            p.add_argument("--scale", type=float, default=None,
                           help="speed scale in (0, 16]")
        if verb == "rewind":
            p.add_argument("--checkpoint", required=True, help="checkpoint name to restore")
        p.set_defaults(fn=cmd_pioneer_transport, pioneer_cmd=verb)

    return ap


def main(argv: Optional[list] = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        return int(a.fn(a))
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 3
        raise
    except (KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except (OSError, ChannelError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
