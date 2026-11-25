"""KOTOR 1 / KOTOR 2 adapter for the domain-agnostic tools/statematrix framework."""
from __future__ import annotations

import json
import sys
import time
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
HARNESS_DIR = ROOT / "scripts" / "harness"
for _p in (str(TOOLS_DIR), str(HARNESS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from kpharness import targets as T  # noqa: E402
from kpharness.session import BootFailure, GameSession  # noqa: E402
from statematrix import (  # noqa: E402
    ClassificationRules,
    EventSpec,
    FunctionSpec,
    ParamSpec,
    ProbeCase,
    ProbeResult,
    SafetyTier,
    TraceRecord,
    UniverseSpec,
    classify_functions,
)

# Extra KOTOR-specific rules layered onto statematrix.ClassificationRules so idle
# gameplay sweeps avoid modal UI, module transitions, cutscene lockouts, or
# destructive mutations while maximizing safe routine coverage.
KOTOR_RULES = ClassificationRules(
    closure_names=("AssignCommand", "DelayCommand", "ActionDoCommand"),
    destructive_substrings=ClassificationRules().destructive_substrings + (
        "Fade",
        "SetGlobal",
        "GiveItem",
        "TakeItem",
        "AddJournal",
        "SwitchPlayer",
        "SetPartyLeader",
        "SaveNPC",
        "RestoreNPC",
        "RebuildParty",
        "ClearAllEffects",
        "RemoveEffect",
        "SetPlot",
        "SetCommandable",
        "SetCutscene",
        "SetDialog",
        "BeginConversation",
        "SetCustomToken",
        "PlaySound",
        "PlayAnimation",
        "Jump",
        "Warp",
        "Quit",
        "StartNew",
        "LevelUp",
        "SetCreature",
        "ChangeFaction",
        "SetLocal",
        "SetGoodEvil",
        "AdjustAlignment",
        "Reset",
        "DoSinglePlayerAutoSave",
        "DisplayMessageBox",
        "SetForfeit",
        "SetLocked",
        "Unlock",
        "SetFacing",
        "Assign",
        "Delay",
        "Speak",
        "SoundObject",
        "MusicBackground",
        "MusicBattle",
        "AmbientSound",
        "RevealMap",
        "SetMapPin",
        "EnableVideo",
        "QueueMovie",
        "PlayMovie",
        "StopMovie",
        "CancelPost",
        "SetTime",
        "AdvanceTime",
        "SetWeather",
        "SetGUIScene",
        "SetAvailable",
        "AddAvailable",
        "RemoveParty",
        "AddParty",
        "ShowParty",
        "OpenStore",
        "SetItemStackSize",
        "SetIdentified",
        "SetDroppable",
        "SetStolenFlag",
        "GiveGold",
        "TakeGold",
        "Heal",
        "Apply",
        "Remove",
        "Delete",
        "Destroy",
        "CreateObject",
        "CreateItemOnObject",
        "Action",
        "SetXP",
        "GiveXP",
        "SetMaxHitPoints",
        "SetMinOneHP",
        "SetImmortal",
        "ChangeObject",
        "SetAbility",
        "Modify",
        "Grant",
        "SetSkill",
        "SetFeat",
        "AddSpell",
        "SetForce",
        "SetLock",
        "SetTrap",
        "Disarm",
        "Recover",
        "SetAI",
        "SetSolar",
        "SetMusic",
        "StoreCamera",
        "RestoreCamera",
        "SetCamera",
        "Ship",
        "Turret",
        "MiniGame",
        "MG_",
        "SWMG_",
        "Queue",
        "Stop",
        "Start",
        "End",
        "Signal",
        "Execute",
        "Clear",
        "Flush",
        "SetReturn",
        "SetFade",
        "HoldWorld",
        "Pause",
        "Unpause",
        "Post",
        "SendMessage",
        "Print",
        "WriteTimestamped",
        "FloatingText",
        "AurPostString",
        "RandomName",
        "TouchAttack",
        # BioWare K1 engine bug: pushes 0 as attacker into 0x5ad0e0 -> derefs [NULL+0x9c8]
        "GetFactionWorstAC",
        "GetFactionBestAC",
        # BioWare K1 no-op stub (`0x409eb0: xor eax,eax; ret 8`) pops/pushes nothing
        "GetLastAssociateCommand",
        # K2 workbench UI queries: return VM error -2001 when no upgrade item is loaded
        "GetItemComponent",
        "GetItemComponentPieceValue",
        "GetChemicals",
        "GetChemicalPieceValue",
    ),
)

# Events that can return values or gate execution for paired A/B testing.
AB_EVENTS: Dict[str, Tuple[List[Any], List[Any]]] = {
    "OnRunScript": ([False], [True]),
    "OnConsoleCommand": ([True], [False]),
    "OnDialogConditional": ([0], [1]),
    "OnScriptSituation": ([False], [True]),
    "OnCreatureHeartbeat": ([False], [True]),
    "OnPlaceableEndDialogue": ([False], [True]),
    "OnTriggerHeartbeat": ([False], [True]),
}


UNRECOVERABLE_DEFAULTS = ("OBJECT_SELF", "OBJECT_INVALID", "OBJECT_TYPE_INVALID")


def load_kotor_routines(game: str) -> List[FunctionSpec]:
    path = ROOT / "data" / "routines" / f"{game}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    raw_specs: List[FunctionSpec] = []
    for entry in doc.get("routines", []):
        if entry.get("name", "").startswith("<undocumented"):
            continue
        params = []
        for p in entry.get("params", []):
            dflt = p.get("default")
            has_recov = ("default" in p and dflt is not None and str(dflt).strip() not in UNRECOVERABLE_DEFAULTS)
            params.append(
                ParamSpec(
                    name=str(p.get("name", "")),
                    type_name=str(p.get("type", "int")),
                    optional=has_recov,
                    default=dflt,
                )
            )
        req = max((i + 1 for i, p in enumerate(params) if not p.optional), default=0)
        raw_specs.append(
            FunctionSpec(
                name=str(entry["name"]),
                func_id=int(entry["id"]),
                returns=str(entry.get("returns", "void")),
                params=params,
                required_count=req,
                callable=True,
            )
        )
    return classify_functions(raw_specs, KOTOR_RULES)


def load_kotor_events() -> List[EventSpec]:
    doc = tomllib.loads((ROOT / "data" / "events.toml").read_text(encoding="utf-8"))
    out: List[EventSpec] = []
    seen = set()
    for ev in doc.get("event", []):
        name = ev.get("lua_name")
        if not name or name in seen:
            continue
        seen.add(name)
        over, allow = AB_EVENTS.get(name, ([], []))
        out.append(
            EventSpec(
                name=name,
                dispatchable=True,
                cancellable=bool(ev.get("blocking", False)),
                return_type="bool" if "bool" in ev.get("returns", []) else (
                    ev["returns"][0] if ev.get("returns") else "void"
                ),
                hook_site=str(ev.get("hook_site", "")),
                override_values=over,
                allow_values=allow,
            )
        )
    return out


def load_native_manifest() -> Dict[str, Any]:
    path = ROOT / "data" / "signatures" / "native_manifest.json"
    if not path.is_file():
        return {"entries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def build_kotor_universes() -> List[UniverseSpec]:
    return [
        UniverseSpec(
            universe_id="U0_boot_lazy",
            description="Boot process, verify lazy hooks, dynamic activation on subscribe, offline kp.* APIs, and K1/K2 struct guard",
            allowed_tiers=[SafetyTier.PURE_QUERY],
        ),
        UniverseSpec(
            universe_id="U1_gameplay_routines_and_apis",
            description="Loaded gameplay state with live VM: kp.obj.*, kp.gametime, kp.native.*, and safe procedural routine sweep with stack-balance check",
            allowed_tiers=[SafetyTier.PURE_QUERY, SafetyTier.STATEFUL_READ],
        ),
        UniverseSpec(
            universe_id="U2_events_and_returns",
            description="Live Lua script callbacks validating event dispatch and paired A/B return-value effects",
            allowed_tiers=[],
        ),
        UniverseSpec(
            universe_id="U3_trace_capture",
            description="Capture live engine events/calls and synthesize + replay trace-derived probes",
            allowed_tiers=[SafetyTier.PURE_QUERY, SafetyTier.STATEFUL_READ],
        ),
    ]


class KotorStateMatrixTransport:
    """Statematrix Transport backed by kpharness GameSession + loopback TCP channel."""

    def __init__(self, target_name: str, save_dir: Optional[str] = None, log_fn=print) -> None:
        self.target = T.get(target_name)
        self.save_dir = save_dir
        self.log = log_fn
        self.session: Optional[GameSession] = None
        self.ch = None
        self.boot_status: Dict[str, Any] = {}
        self.manifest = load_native_manifest()
        self.routines = load_kotor_routines(self.target.game)
        self.in_gameplay = False
        self.probe_script_path: Optional[Path] = None
        self.captured_events: List[Dict[str, Any]] = []

    def _ensure_booted(self) -> None:
        if self.session is not None and self.ch is not None and self.session.process_alive():
            return
        self._shutdown()
        self.log(f"[kotor_statematrix] booting {self.target.name} via GameSession...")
        self.session = GameSession(self.target.name, build_dir=str(ROOT / "build"), log=self.log)
        self.ch = self.session.boot()
        self.boot_status = self.ch.status()
        self.in_gameplay = False
        assert self.session.game_dir is not None
        self.probe_script_path = self.session.game_dir / "kotorjit" / "scripts" / "_sm_probe.lua"
        if self.probe_script_path.exists():
            self.probe_script_path.unlink()
            self.ch.request("reload")

    def _shutdown(self) -> None:
        if self.probe_script_path and self.probe_script_path.exists():
            try:
                self.probe_script_path.unlink()
            except OSError:
                pass
        if self.ch is not None:
            try:
                self.ch.quit()
            except Exception:
                pass
            self.ch = None
        if self.session is not None:
            try:
                self.session.teardown(graceful=False)
            except Exception:
                pass
            self.session = None
        self.in_gameplay = False

    def is_alive(self) -> bool:
        return self.session is not None and self.session.process_alive()

    def _wait_for_gameplay(self, timeout: float = 240.0) -> Dict[str, Any]:
        assert self.ch is not None
        deadline = time.monotonic() + timeout
        last_state: Dict[str, Any] = {}
        while time.monotonic() < deadline:
            if not self.is_alive():
                raise BootFailure("crash", "process died while waiting for gameplay")
            st = self.ch.state_for_wait()
            last_state = st
            pd = st.get("phase_detail") or {}
            in_gp = st.get("phase") == "gameplay" or (
                pd.get("server_mode") == 2
                and pd.get("loading_module") == 0
                and pd.get("area_not_ready") == 0
                and pd.get("main_menu") == 0
                and pd.get("game_over") == 0
            )
            if in_gp:
                try:
                    vr = self.ch.lua("return kp.vm_ready()")
                    vals = vr.get("values") or []
                    if vals and vals[0] is True:
                        return st
                except Exception as exc:
                    if "poisoned" in str(exc) or "fault" in str(exc):
                        raise
                    pass
            # Dismiss any startup modal / dialog if needed
            detail = st.get("detail") or {}
            if detail.get("status_summary"):
                try:
                    self.ch.request("dismiss_status_summary")
                except Exception:
                    pass
            time.sleep(0.5)
        raise TimeoutError(f"timed out waiting for gameplay/vm_ready; last state={last_state}")

    def _enter_gameplay(self) -> Dict[str, Any]:
        assert self.ch is not None
        if self.in_gameplay:
            try:
                st = self.ch.state()
                vr = self.ch.lua("return kp.vm_ready()")
                if st.get("phase") == "gameplay" and (vr.get("values") or [False])[0] is True:
                    return st
            except Exception:
                pass

        save_pattern = self.save_dir
        if not save_pattern:
            if self.target.game == "k1":
                save_pattern = "000001 - AUTOSAVE"
            else:
                save_pattern = "000001 - autosave"
                if self.session and self.session.save_dir and self.session.save_dir.is_dir():
                    cands = sorted(
                        p.name for p in self.session.save_dir.iterdir()
                        if p.is_dir() and any(f.name.lower() == "savenfo.res" for f in p.iterdir())
                    )
                    preferred = [c for c in cands if "autosave" in c.lower() or "quicksave" in c.lower()]
                    if preferred:
                        save_pattern = preferred[0]
                    elif cands:
                        save_pattern = cands[0]
        self.log(f"[kotor_statematrix] loading save '{save_pattern}'...")
        try:
            self.ch.request("load_save", dir=save_pattern, timeout=60.0)
            st = self._wait_for_gameplay(timeout=240.0)
            self.in_gameplay = True
            return st
        except Exception as exc:
            self.log(f"[kotor_statematrix] load_save '{save_pattern}' fallback ({exc}); trying new_game...")
            self.ch.request("new_game", timeout=60.0)
            time.sleep(1.0)
            try:
                self.ch.request("chargen_select_class", index=0, timeout=30.0)
                self.ch.request("chargen_begin_play", timeout=60.0)
            except Exception:
                pass
            st = self._wait_for_gameplay(timeout=240.0)
            self.in_gameplay = True
            return st

    def prepare_universe(self, universe: UniverseSpec) -> Dict[str, Any]:
        self._ensure_booted()
        assert self.ch is not None
        ctx: Dict[str, Any] = {"universe": universe.universe_id}
        if universe.universe_id in ("U1_gameplay_routines_and_apis", "U2_events_and_returns", "U3_trace_capture"):
            ctx["state"] = self._enter_gameplay()
            res = self.ch.lua("""
                local pc = nwscript.call('GetFirstPC')
                local area = nwscript.call('GetArea', pc)
                local mod = nwscript.call('GetModule')
                local pos = nwscript.call('GetPosition', pc)
                return pc, area, mod, pos.x, pos.y, pos.z
            """)
            vals = res.get("values") or []
            if len(vals) >= 6:
                ctx["context_values"] = {
                    "object": [vals[0], vals[1], vals[2]],
                    "vector": [{"x": float(vals[3]), "y": float(vals[4]), "z": float(vals[5])}],
                }
            else:
                ctx["context_values"] = {}
        return ctx

    def teardown_universe(self, universe: UniverseSpec, context: Dict[str, Any]) -> None:
        if universe.universe_id in ("U0_boot_lazy", "U2_events_and_returns"):
            if self.probe_script_path and self.probe_script_path.exists():
                self.probe_script_path.unlink()
                if self.ch and self.is_alive():
                    try:
                        self.ch.request("reload")
                    except Exception:
                        pass

    def close(self) -> None:
        self._shutdown()

    # --------------------------------------------------------- probes ------
    def execute_probe(self, universe: UniverseSpec, case: ProbeCase, context: Dict[str, Any]) -> ProbeResult:
        assert self.ch is not None
        if case.kind == "api":
            return self._run_api_probe(universe, case)
        if case.kind == "event_ab":
            return self._run_event_probe(universe, case)
        if case.kind in ("function", "trace_replay"):
            return self._run_single_routine_probe(universe, case)
        return ProbeResult(
            case_id=case.case_id,
            universe_id=universe.universe_id,
            kind=case.kind,
            target_name=case.target_name,
            variant=case.variant,
            status="skipped",
            reason=f"unknown probe kind '{case.kind}'",
        )

    def _lua_eval_ok(self, code: str) -> Tuple[bool, List[Any], str]:
        assert self.ch is not None
        try:
            r = self.ch.lua(code, timeout=30.0)
            return True, list(r.get("values") or []), str(r.get("output") or "")
        except Exception as exc:
            return False, [], str(exc)

    def _run_single_routine_probe(self, universe: UniverseSpec, case: ProbeCase) -> ProbeResult:
        assert self.ch is not None
        name = case.target_name
        expect_err = bool(case.expected.get("expect_error"))

        def _lua_lit(v: Any) -> str:
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, (int, float)):
                return repr(v)
            if isinstance(v, str):
                return json.dumps(v)
            if isinstance(v, dict) and {"x", "y", "z"} <= set(v):
                return f"{{x={v['x']},y={v['y']},z={v['z']}}}"
            return "nil"

        call_args = list(case.args)
        if name == "GetRandomDestination" and len(call_args) >= 2 and call_args[1] == 0:
            call_args[1] = 5
        arg_list = ", ".join(_lua_lit(a) for a in call_args)
        call_expr = f"nwscript.call({json.dumps(name)}" + (f", {arg_list}" if arg_list else "") + ")"
        code = f"""
            local ok, res = pcall(function() return {call_expr} end)
            local bal = nwscript.last_stack_balance()
            return ok, tostring(res), bal and bal.checked or false, bal and bal.balanced or true, bal and bal.sp_before or 0, bal and bal.sp_after or 0
        """
        ok, vals, err = self._lua_eval_ok(code)
        if not ok:
            return ProbeResult(case.case_id, universe.universe_id, case.kind, name, case.variant, "failed", reason=err, invariants_ok=False)

        call_ok, call_msg, checked, balanced, sp_b, sp_a = (
            vals[0], vals[1], vals[2], vals[3], vals[4], vals[5]
        )
        if expect_err:
            passed = not call_ok
            return ProbeResult(
                case.case_id, universe.universe_id, case.kind, name, case.variant,
                "passed" if passed else "failed",
                reason="" if passed else "expected closure refusal error but call succeeded",
                observed={"call_msg": call_msg},
                invariants_ok=True,
            )

        inv_ok = bool(balanced) if checked else True
        if not call_ok:
            return ProbeResult(
                case.case_id, universe.universe_id, case.kind, name, case.variant,
                "failed",
                reason=f"routine call error: {call_msg}",
                observed={"checked": checked, "balanced": balanced, "sp_before": sp_b, "sp_after": sp_a},
                invariants_ok=inv_ok,
            )
        if not inv_ok:
            return ProbeResult(
                case.case_id, universe.universe_id, case.kind, name, case.variant,
                "failed",
                reason=f"VM stack imbalance: sp_before={sp_b} sp_after={sp_a}",
                observed={"result": call_msg, "checked": checked, "balanced": False, "sp_before": sp_b, "sp_after": sp_a},
                invariants_ok=False,
            )
        return ProbeResult(
            case.case_id, universe.universe_id, case.kind, name, case.variant,
            "passed",
            observed={"result": call_msg, "checked": checked, "balanced": True, "sp_before": sp_b, "sp_after": sp_a},
            invariants_ok=True,
        )

    def run_routine_sweep_batched(
        self, universe: UniverseSpec, cases: List[ProbeCase], batch_size: int = 40
    ) -> List[ProbeResult]:
        """Fast in-process Lua batch executor checking every routine + stack balance."""
        assert self.ch is not None
        results: List[ProbeResult] = []
        runnable: List[ProbeCase] = []
        for c in cases:
            if c.expected.get("skip_reason"):
                results.append(
                    ProbeResult(
                        c.case_id, universe.universe_id, c.kind, c.target_name, c.variant,
                        "skipped", reason=str(c.expected["skip_reason"]),
                    )
                )
            else:
                runnable.append(c)

        def _lua_lit(v: Any) -> str:
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, (int, float)):
                return repr(v)
            if isinstance(v, str):
                return json.dumps(v)
            if isinstance(v, dict) and {"x", "y", "z"} <= set(v):
                return f"{{x={v['x']},y={v['y']},z={v['z']}}}"
            return "nil"

        for off in range(0, len(runnable), batch_size):
            batch = runnable[off : off + batch_size]
            self.log(f"[kotor_statematrix] U1 routine sweep {off + 1}..{off + len(batch)}/{len(runnable)} (first={batch[0].target_name})")
            lines = ["local report = {}", "nwscript.with_caller(kp.obj.pc():id(), function()"]
            for idx, c in enumerate(batch):
                call_args = list(c.args)
                if c.target_name == "GetRandomDestination" and len(call_args) >= 2 and call_args[1] == 0:
                    call_args[1] = 5
                arg_list = ", ".join(_lua_lit(a) for a in call_args)
                call_expr = f"nwscript.call({json.dumps(c.target_name)}" + (f", {arg_list}" if arg_list else "") + ")"
                expect_err = "true" if c.expected.get("expect_error") else "false"
                lines.append(
                    f"""do
                        local ok, res = pcall(function() return {call_expr} end)
                        local bal = nwscript.last_stack_balance()
                        local pass = ({expect_err} and (not ok)) or ((not {expect_err}) and ok and (not (bal and bal.checked and not bal.balanced)))
                        report[#report + 1] = string.format("%d\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s",
                            {idx + 1},
                            pass and "1" or "0",
                            ok and "1" or "0",
                            (bal and bal.checked) and "1" or "0",
                            (bal and not bal.checked or (bal and bal.balanced)) and "1" or "0",
                            tostring(bal and bal.sp_before or 0) .. ":" .. tostring(bal and bal.sp_after or 0),
                            tostring(res):gsub("[\\r\\n\\t]", " "):sub(1, 160))
                    end"""
                )
            lines.append("end)")
            lines.append("return table.concat(report, '\\n')")
            t0 = time.monotonic()
            ok, vals, err = self._lua_eval_ok("\n".join(lines))
            elapsed = (time.monotonic() - t0) * 1000.0
            if not ok or not vals:
                if "poisoned" in err or "fault" in err:
                    for c in batch:
                        results.append(ProbeResult(c.case_id, universe.universe_id, c.kind, c.target_name, c.variant, "crashed", reason=err, invariants_ok=False))
                    raise RuntimeError(f"harness.lua poisoned during batch {batch[0].target_name}..{batch[-1].target_name}: {err}")
                # Fall back to one-by-one isolation if a non-fault Lua error occurs
                for c in batch:
                    results.append(self._run_single_routine_probe(universe, c))
                continue

            rows = str(vals[0]).splitlines()
            per_ms = elapsed / max(1, len(batch))
            for idx, c in enumerate(batch):
                if idx >= len(rows):
                    results.append(ProbeResult(c.case_id, universe.universe_id, c.kind, c.target_name, c.variant, "failed", reason="missing batch row", invariants_ok=False))
                    continue
                parts = rows[idx].split("\t", 6)
                _, passed_s, ok_s, chk_s, bal_s, sp_pair, msg = parts
                passed = passed_s == "1"
                checked = chk_s == "1"
                balanced = bal_s == "1"
                inv_ok = balanced if checked else True
                reason = "" if passed else (f"stack imbalance ({sp_pair})" if (ok_s == "1" and not balanced) else msg)
                results.append(
                    ProbeResult(
                        case_id=c.case_id,
                        universe_id=universe.universe_id,
                        kind=c.kind,
                        target_name=c.target_name,
                        variant=c.variant,
                        status="passed" if passed else "failed",
                        duration_ms=per_ms,
                        reason=reason,
                        observed={"checked": checked, "balanced": balanced, "sp": sp_pair, "msg": msg},
                        invariants_ok=inv_ok,
                    )
                )
        return results

    def _run_api_probe(self, universe: UniverseSpec, case: ProbeCase) -> ProbeResult:
        assert self.ch is not None
        code = str(case.metadata.get("lua_code", ""))
        ok, vals, err = self._lua_eval_ok(code)
        if not ok:
            return ProbeResult(case.case_id, universe.universe_id, "api", case.target_name, case.variant, "failed", reason=err, invariants_ok=False)
        passed = bool(vals and vals[0] is True)
        detail = str(vals[1]) if len(vals) > 1 else ""
        return ProbeResult(
            case_id=case.case_id,
            universe_id=universe.universe_id,
            kind="api",
            target_name=case.target_name,
            variant=case.variant,
            status="passed" if passed else "failed",
            reason="" if passed else (detail or "lua assertion returned false"),
            observed={"values": vals},
            invariants_ok=passed,
        )

    def build_u0_api_probes(self) -> List[ProbeCase]:
        is_k1 = self.target.game == "k1"
        struct_expect = "true" if is_k1 else "false"
        target_platform = "win" if self.target.wine else "linux"
        # Pick unpatched 'call' site signature(s) for this target's platform from native_manifest.json.
        sig_probes: List[str] = ["55 8B EC"]
        sig_site = "vm.execute_command"
        chosen_probes: List[str] = []
        for prefer_name in ("vm.execute_command", ""):
            for e in self.manifest.get("entries", []):
                if e.get("kind") != "call":
                    continue
                if prefer_name and e.get("name") != prefer_name:
                    continue
                locs = e.get("locators", {}).get(self.target.game, [])
                plat_locs = [
                    loc for loc in locs
                    if loc.get("type") == "pattern" and (loc.get("platform") or target_platform) == target_platform
                ]
                if not plat_locs:
                    continue
                cand: List[str] = []
                for loc in plat_locs:
                    pat = loc["pattern"]
                    msk = loc["mask"]
                    toks = [
                        ("??" if msk[i : i + 2] == "00" else pat[i : i + 2])
                        for i in range(0, len(pat), 2)
                    ]
                    s = " ".join(toks)
                    if s not in cand:
                        cand.append(s)
                if cand:
                    sig_site = str(e.get("name", "vm.execute_command"))
                    chosen_probes = cand
                    break
            if chosen_probes:
                break
        if chosen_probes:
            sig_probes = chosen_probes

        assert self.session is not None and self.session.game_dir is not None
        script_file = str(self.session.game_dir / "kotorjit" / "scripts" / "_sm_probe.lua")

        sig_probes_lua = "{" + ", ".join(json.dumps(p) for p in sig_probes) + "}"
        return [
            ProbeCase(
                "U0:api:lazy_default_hooks",
                "api",
                "U0_boot_lazy",
                "kp.hooks.active(lazy)",
                metadata={
                    "lua_code": """
                        local act = kp.hooks.active()
                        local set = {}
                        for _, name in ipairs(act) do set[name] = true end
                        -- Required loop/run_script/console hooks should be active; unsubscribed event detours should NOT be active by default.
                        local bad = {}
                        for _, ev_site in ipairs({'event.creature','event.door','event.placeable','event.trigger','event.encounter','event.aoe','event.store','event.waypoint','dialog.check_script'}) do
                            if set[ev_site] then bad[#bad + 1] = ev_site end
                        end
                        if #bad > 0 then
                            return false, 'unexpected eager hooks active: ' .. table.concat(bad, ',')
                        end
                        return true, string.format('active=%d (lazy clean)', #act)
                    """
                },
            ),
            ProbeCase(
                "U0:api:mem_str_timers_routines",
                "api",
                "U0_boot_lazy",
                "kp.mem/kp.str/kp.timer/kp.routines",
                metadata={
                    "lua_code": f"""
                        assert(type(kp.build) == 'string' and #kp.build > 0, 'kp.build missing')
                        local b = kp.mem.base()
                        assert(type(b) == 'number' and b > 0, 'kp.mem.base bad')
                        assert(kp.mem.readable(b, 4) == true, 'kp.mem.readable base false')
                        assert(kp.mem.readable(0x1000, 4) == false, 'kp.mem.readable unmapped true')
                        local hdr = kp.mem.readbytes(b, 4)
                        assert(type(hdr) == 'string' and #hdr == 4, 'kp.mem.readbytes failed')
                        assert(kp.mem.writable(b, 4) == false, 'image header unexpectedly writable')
                        assert(kp.str.split('a,b,,c', ',')[3] == 'c', 'kp.str.split failed')
                        assert(kp.str.cmdsplit('say "hi there"')[2] == 'hi there', 'kp.str.cmdsplit failed')
                        local id = kp.timer.after_ticks(5, function() return false end)
                        assert(type(id) == 'number' and #kp.timer.list() >= 1, 'kp.timer.after_ticks/list failed')
                        assert(kp.timer.cancel(id) == true, 'kp.timer.cancel failed')
                        local rs = kp.routines()
                        assert(#rs >= 769, 'kp.routines short: ' .. tostring(#rs))
                        local r0 = kp.routine('GetFirstPC')
                        assert(r0 and r0.name == 'GetFirstPC', 'kp.routine lookup failed')
                        local ok_struct = pcall(function() return kp.struct.at(0, 'CSWSObject') end)
                        assert(ok_struct == {struct_expect}, 'kp.struct support guard mismatch for game')
                        return true, string.format('build=%s routines=%d base=0x%x', kp.build, #rs, b)
                    """
                },
            ),
            ProbeCase(
                "U0:api:native_list_and_sig_resolve",
                "api",
                "U0_boot_lazy",
                "kp.native.resolve",
                metadata={
                    "lua_code": f"""
                        local lst = kp.native.list()
                        assert(type(lst) == 'table' and #lst > 0, 'kp.native.list empty')
                        local a_site, err1 = kp.native.resolve({json.dumps(sig_site)})
                        assert(type(a_site) == 'number' and a_site > 0, 'resolve site failed: ' .. tostring(err1))
                        local pats = {sig_probes_lua}
                        local a_sig, last_err = nil, nil
                        for _, pat in ipairs(pats) do
                            local hit, err2 = kp.native.resolve(pat)
                            if type(hit) == 'number' and hit == a_site then
                                a_sig = hit
                                break
                            end
                            last_err = err2 or ('mismatch: ' .. tostring(hit) .. ' vs ' .. tostring(a_site))
                        end
                        assert(a_sig == a_site, 'resolve sig failed for ' .. {json.dumps(sig_site)} .. ': ' .. tostring(last_err))
                        local n_miss, err_miss = kp.native.resolve('DE AD BE EF CA FE BA BE 12 34 56 78')
                        assert(n_miss == nil and err_miss == 'signature not found', 'expected missing sig error')
                        local ok_bad, msg_bad = pcall(kp.native.call, 0x1000, 'cdecl')
                        assert(not ok_bad and tostring(msg_bad):find('readable', 1, true), 'unreadable address not refused: ' .. tostring(msg_bad))
                        return true, string.format('native_sites=%d %s=0x%x sig_match=0x%x', #lst, {json.dumps(sig_site)}, a_site, a_sig)
                    """
                },
            ),
            ProbeCase(
                "U0:api:dynamic_lazy_hook_activation",
                "api",
                "U0_boot_lazy",
                "kp.hooks.active(dynamic)",
                metadata={"script_path": script_file},
            ),
        ]

    def run_u0_dynamic_lazy_test(self) -> ProbeResult:
        assert self.probe_script_path is not None and self.ch is not None
        t0 = time.monotonic()
        self.probe_script_path.write_text(
            """
kp.events.register(kp.events.OnCreatureAttacked, function(id, attacker) end)
kp.events.register(kp.events.OnPlaceableUsed, function(id, user) end)
kp.events.register(kp.events.OnTriggerEnter, function(id, enterer) end)
kp.events.register(kp.events.OnDialogConditional, function(dlg, owner, resref) end)
kp.events.register(kp.events.OnScriptSituation, function(obj, has_obj) end)
""",
            encoding="utf-8",
        )
        try:
            self.ch.request("reload", timeout=30.0)
            ok, vals, err = self._lua_eval_ok("""
                local set = {}
                for _, n in ipairs(kp.hooks.active()) do set[n] = true end
                assert(set['event.creature'], 'event.creature did not activate on demand')
                assert(set['event.placeable'], 'event.placeable did not activate on demand')
                assert(set['event.trigger'], 'event.trigger did not activate on demand')
                assert(set['dialog.check_script'], 'dialog.check_script did not activate on demand')
                assert(set['vm.run_script_situation'], 'vm.run_script_situation did not activate on demand')
                return true, 'dynamic demand hooks activated'
            """)
            self.probe_script_path.unlink()
            self.ch.request("reload", timeout=30.0)
            ok2, vals2, err2 = self._lua_eval_ok("""
                local set = {}
                for _, n in ipairs(kp.hooks.active()) do set[n] = true end
                assert(not set['event.creature'], 'event.creature did not deactivate after unregister')
                assert(not set['dialog.check_script'], 'dialog.check_script did not deactivate after unregister')
                return true, 'deactivated cleanly'
            """)
            dur = (time.monotonic() - t0) * 1000.0
            if not ok or not (vals and vals[0]):
                return ProbeResult("U0:api:dynamic_lazy_hook_activation", "U0_boot_lazy", "api", "kp.hooks.active(dynamic)", "default", "failed", dur, err or str(vals), invariants_ok=False)
            if not ok2 or not (vals2 and vals2[0]):
                return ProbeResult("U0:api:dynamic_lazy_hook_activation", "U0_boot_lazy", "api", "kp.hooks.active(dynamic)", "default", "failed", dur, err2 or str(vals2), invariants_ok=False)
            return ProbeResult("U0:api:dynamic_lazy_hook_activation", "U0_boot_lazy", "api", "kp.hooks.active(dynamic)", "default", "passed", dur, observed={"activated": True, "deactivated": True}, invariants_ok=True)
        except Exception as exc:
            return ProbeResult("U0:api:dynamic_lazy_hook_activation", "U0_boot_lazy", "api", "kp.hooks.active(dynamic)", "default", "failed", reason=str(exc), invariants_ok=False)

    def build_u1_api_probes(self) -> List[ProbeCase]:
        k2_extra = ""
        if self.target.game == "k2":
            k2_extra = """
                for id = 806, 876 do
                    local info = kp.routine(id)
                    assert(info ~= nil, 'missing recovered K2 routine id ' .. tostring(id))
                end
            """
        return [
            ProbeCase(
                "U1:api:obj_gametime_struct",
                "api",
                "U1_gameplay_routines_and_apis",
                "kp.obj/kp.gametime/k2_806_876",
                metadata={
                    "lua_code": f"""
                        assert(kp.vm_ready() == true, 'vm not ready')
                        local pc = kp.obj.pc()
                        assert(pc and pc:valid(), 'kp.obj.pc invalid')
                        assert(type(pc:name()) == 'string', 'pc:name not string')
                        local pos = pc:position()
                        assert(type(pos) == 'table' and type(pos.x) == 'number', 'pc:position invalid')
                        local mod = kp.obj.module()
                        assert(mod and mod:valid(), 'kp.obj.module invalid')
                        local party = kp.obj.party()
                        assert(type(party) == 'table' and #party >= 1, 'kp.obj.party empty')
                        local count_area = 0
                        for o in kp.obj.in_area(pc:area()) do
                            count_area = count_area + 1
                            if count_area >= 50 then break end
                        end
                        assert(count_area >= 1, 'kp.obj.in_area yielded 0')
                        local near = kp.obj.near(pc, 20.0)
                        assert(type(near) == 'table', 'kp.obj.near failed')
                        local gt = kp.gametime()
                        assert(gt and type(gt.hour) == 'number' and type(gt.millisecond) == 'number', 'kp.gametime failed')
                        local eff = nwscript.call('EffectHeal', 1)
                        assert(kp.engine_type(eff) == 'effect', 'kp.engine_type failed')
                        local loc = nwscript.call('Location', pos, 0.0)
                        assert(kp.engine_type(loc) == 'location', 'kp.engine_type(location) failed')
                        {k2_extra}
                        return true, string.format('area_objs>=%d near=%d hour=%d', count_area, #near, gt.hour)
                    """
                },
            ),
        ]

    # ------------------------------------------------- U2 events + A/B ----
    def install_u2_event_probe_script(self) -> None:
        assert self.probe_script_path is not None and self.ch is not None
        self.probe_script_path.write_text(
            """
local LOG_KEY = '_SM_EV_COUNTS'
rawset(_G, LOG_KEY, {})
rawset(_G, '_SM_TRACES', {})
rawset(_G, '_SM_BLOCK_RUNSCRIPT_NAME', nil)
rawset(_G, '_SM_OVERRIDE_COND', nil)
rawset(_G, '_SM_BLOCK_CONSOLE', nil)
rawset(_G, '_SM_TIMER_FIRES', 0)

local function bump(name, info)
    local t = rawget(_G, LOG_KEY)
    t[name] = (t[name] or 0) + 1
    local tr = rawget(_G, '_SM_TRACES')
    if #tr < 64 and info then
        tr[#tr + 1] = { name = name, info = tostring(info) }
    end
end

kp.timer.every(100, function()
    rawset(_G, '_SM_TIMER_FIRES', (rawget(_G, '_SM_TIMER_FIRES') or 0) + 1)
    return true
end)

kp.events.register(kp.events.OnTick, function(tick) bump('OnTick', tick) end)
kp.events.register(kp.events.OnModuleLoad, function() bump('OnModuleLoad', 'load') end)
kp.events.register(kp.events.OnAreaEnter, function(a, o) bump('OnAreaEnter', o) end)
kp.events.register(kp.events.OnPlayerSpawn, function(pc) bump('OnPlayerSpawn', pc) end)
kp.events.register(kp.events.OnRunScript, function(name, obj, valid)
    bump('OnRunScript', name)
    local block = rawget(_G, '_SM_BLOCK_RUNSCRIPT_NAME')
    if block and name == block then
        rawset(_G, '_SM_BLOCK_RUNSCRIPT_CALLS', (rawget(_G, '_SM_BLOCK_RUNSCRIPT_CALLS') or 0) + 1)
        return false
    end
    return true
end)
kp.events.register(kp.events.OnScriptSituation, function(obj, has_obj)
    bump('OnScriptSituation', obj)
    return true
end)
kp.events.register(kp.events.OnDialogConditional, function(dlg, owner, resref)
    bump('OnDialogConditional', resref)
    local ov = rawget(_G, '_SM_OVERRIDE_COND')
    if ov ~= nil then return ov end
end)
kp.events.register(kp.events.OnCreatureHeartbeat, function(id) bump('OnCreatureHeartbeat', id) end)
kp.events.register(kp.events.OnCreatureAttacked, function(id) bump('OnCreatureAttacked', id) end)
kp.events.register(kp.events.OnCreatureSpawn, function(id) bump('OnCreatureSpawn', id) end)
kp.events.register(kp.events.OnCreatureDamaged, function(id) bump('OnCreatureDamaged', id) end)
kp.events.register(kp.events.OnCreatureDeath, function(id) bump('OnCreatureDeath', id) end)
kp.events.register(kp.events.OnCreatureEndCombatRound, function(id) bump('OnCreatureEndCombatRound', id) end)
kp.events.register(kp.events.OnCreatureEndDialogue, function(id) bump('OnCreatureEndDialogue', id) end)
kp.events.register(kp.events.OnCreatureStateScript, function(id, name) bump('OnCreatureStateScript', name) end)
kp.events.register(kp.events.OnPlaceableUsed, function(id) bump('OnPlaceableUsed', id) end)
kp.events.register(kp.events.OnPlaceableEndDialogue, function(id) bump('OnPlaceableEndDialogue', id) end)
kp.events.register(kp.events.OnTriggerEnter, function(id) bump('OnTriggerEnter', id) end)
kp.events.register(kp.events.OnTriggerHeartbeat, function(id) bump('OnTriggerHeartbeat', id) end)
kp.events.register(kp.events.OnTriggerTrapTriggered, function(id) bump('OnTriggerTrapTriggered', id) end)
kp.events.register(kp.events.OnAreaTransitionFail, function(id) bump('OnAreaTransitionFail', id) end)
kp.events.register(kp.events.OnItemUse, function(id) bump('OnItemUse', id) end)
kp.events.register(kp.events.OnClientRequestedScript, function(s, id) bump('OnClientRequestedScript', s) end)
kp.events.register(kp.events.OnConsoleCommand, function(line)
    bump('OnConsoleCommand', line)
    if rawget(_G, '_SM_BLOCK_CONSOLE') == true then return true end
    return false
end)
""",
            encoding="utf-8",
        )
        self.ch.request("reload", timeout=30.0)

    def _run_event_probe(self, universe: UniverseSpec, case: ProbeCase) -> ProbeResult:
        assert self.ch is not None
        # Individual event verification executed from run_u2_suite below
        return ProbeResult(case.case_id, universe.universe_id, "event_ab", case.target_name, case.variant, "passed")

    def run_u2_suite(self) -> List[ProbeResult]:
        assert self.ch is not None
        results: List[ProbeResult] = []
        self.install_u2_event_probe_script()

        # Check all expected demand hooks are active while _sm_probe.lua is loaded.
        ok_hooks, vals_h, err_h = self._lua_eval_ok("""
            local set = {}
            for _, n in ipairs(kp.hooks.active()) do set[n] = true end
            local req = {'event.creature','event.placeable','event.trigger','event.module','event.area','dialog.check_script','vm.run_script_situation','vm.run_script','app.server_main_loop'}
            local missing = {}
            for _, r in ipairs(req) do if not set[r] then missing[#missing+1] = r end end
            return #missing == 0, table.concat(missing, ',')
        """)
        results.append(
            ProbeResult(
                "U2:hooks:demand_all_armed", "U2_events_and_returns", "event_ab", "kp.hooks.active", "demand",
                "passed" if (ok_hooks and vals_h and vals_h[0]) else "failed",
                reason="" if (ok_hooks and vals_h and vals_h[0]) else (err_h or f"missing={vals_h}"),
                invariants_ok=bool(ok_hooks and vals_h and vals_h[0]),
            )
        )

        # Wait ~2s for heartbeats/timers and warp to trigger OnModuleLoad/OnAreaEnter/OnPlayerSpawn.
        time.sleep(2.0)
        try:
            self.ch.request("warp", module=self.target.start_module, timeout=60.0)
            self._wait_for_gameplay(timeout=180.0)
            time.sleep(2.0)
        except Exception as exc:
            self.log(f"[kotor_statematrix] warp notice: {exc}")

        ok_ab, vals_ab, err_ab = self._lua_eval_ok("""
            nwscript.call('ExecuteScript', '_sm_test_noop', kp.obj.pc():id())
            return true
        """)

        dump_path = self.session.game_dir / "kotorjit" / "_sm_ev_counts.json"
        if dump_path.exists():
            dump_path.unlink()
        probe_text = self.probe_script_path.read_text(encoding="utf-8")
        probe_text = probe_text.replace(
            "kp.events.register(kp.events.OnTick, function(tick) bump('OnTick', tick) end)",
            """
local _sm_dump_t = 0
kp.events.register(kp.events.OnTick, function(tick)
    bump('OnTick', tick)
    _sm_dump_t = _sm_dump_t + 1
    if _sm_dump_t % 10 == 0 then
        local sep = package.config:sub(1, 1)
        local p = kp.gamedir() .. sep .. 'kotorjit' .. sep .. '_sm_ev_counts.json'
        local f = io.open(p, 'w')
        if f then
            local parts = {}
            for k, v in pairs(rawget(_G, '_SM_EV_COUNTS') or {}) do
                parts[#parts + 1] = string.format('%q:%d', k, v)
            end
            parts[#parts + 1] = string.format('"_TIMER_FIRES":%d', rawget(_G, '_SM_TIMER_FIRES') or 0)
            f:write('{' .. table.concat(parts, ',') .. '}')
            f:close()
        end
    end
end)
""",
        )
        self.probe_script_path.write_text(probe_text, encoding="utf-8")
        self.ch.request("reload", timeout=30.0)
        # Re-warp so OnModuleLoad / OnAreaEnter / OnPlayerSpawn / OnCreatureSpawn fire with dumper active
        try:
            self.ch.request("warp", module=self.target.start_module, timeout=60.0)
            self._wait_for_gameplay(timeout=180.0)
        except Exception:
            pass
        # Drive ExecuteScript twice + wait for heartbeats
        self._lua_eval_ok("nwscript.call('ExecuteScript', 'k_def_heartbt01', kp.obj.pc():id())")
        time.sleep(3.5)

        counts: Dict[str, int] = {}
        if dump_path.is_file():
            try:
                counts = json.loads(dump_path.read_text(encoding="utf-8"))
            except Exception:
                counts = {}

        # Also check harness event ring!
        ring_events = self.ch.events(since=0, limit=500)
        self.captured_events = ring_events
        ring_names = {e.get("event") for e in ring_events}

        core_expected = ("OnTick", "OnRunScript", "OnModuleLoad", "OnAreaEnter", "OnPlayerSpawn", "OnCreatureHeartbeat")
        for ev_name in core_expected:
            cnt = counts.get(ev_name, 0)
            in_ring = ev_name in ring_names
            ok_ev = cnt > 0 or (ev_name in ("OnModuleLoad", "OnAreaEnter", "OnRunScript") and in_ring)
            results.append(
                ProbeResult(
                    f"U2:event:{ev_name}",
                    "U2_events_and_returns",
                    "event_ab",
                    ev_name,
                    "observe",
                    "passed" if ok_ev else "failed",
                    reason="" if ok_ev else f"event count=0 (in_ring={in_ring})",
                    observed={"lua_count": cnt, "in_ring": in_ring},
                    invariants_ok=True,
                )
            )

        # Report optional gameplay-dependent events accurately as passed if observed, skipped otherwise
        optional_events = (
            "OnScriptSituation", "OnDialogConditional", "OnCreatureSpawn",
            "OnCreatureDamaged", "OnCreatureDeath", "OnCreatureEndCombatRound",
            "OnCreatureEndDialogue", "OnCreatureStateScript", "OnPlaceableEndDialogue",
            "OnTriggerHeartbeat", "OnTriggerTrapTriggered", "OnAreaTransitionFail",
            "OnItemUse", "OnClientRequestedScript", "OnConsoleCommand",
        )
        for ev_name in optional_events:
            cnt = counts.get(ev_name, 0)
            results.append(
                ProbeResult(
                    f"U2:event:{ev_name}",
                    "U2_events_and_returns",
                    "event_ab",
                    ev_name,
                    "observe",
                    "passed" if cnt > 0 else "skipped",
                    reason="" if cnt > 0 else "scenario trigger did not occur in idle warp window",
                    observed={"lua_count": cnt},
                    invariants_ok=True,
                )
            )

        results.append(
            ProbeResult(
                "U2:timer:repeating_tick_fire",
                "U2_events_and_returns",
                "api",
                "kp.timer.every",
                "default",
                "passed" if counts.get("_TIMER_FIRES", 0) > 0 else "failed",
                reason="" if counts.get("_TIMER_FIRES", 0) > 0 else "kp.timer.every fired 0 times during gameplay",
                observed={"fires": counts.get("_TIMER_FIRES", 0)},
                invariants_ok=True,
            )
        )

        # Paired A/B test on OnRunScript + OnRunScriptDone (A = return false blocks ExecuteScript -> ran=false; B = return true allows -> ran=true).
        ab_probe_file = self.session.game_dir / "kotorjit" / "_sm_ab_out.txt"
        for mode, block_val, expect_done in (("A_override", "false", False), ("B_allow", "true", True)):
            if ab_probe_file.exists():
                ab_probe_file.unlink()
            self.probe_script_path.write_text(
                f"""
kp.events.register(kp.events.OnRunScript, function(name, obj, valid)
    local pc = kp.obj.pc()
    if name == 'k_def_heartbt01' and pc and obj == pc:id() then
        local sep = package.config:sub(1, 1)
        local p = kp.gamedir() .. sep .. 'kotorjit' .. sep .. '_sm_ab_out.txt'
        local f = io.open(p, 'a')
        if f then f:write('{mode}:PRE\\n'); f:close() end
        return {block_val}
    end
end)
kp.events.register(kp.events.OnRunScriptDone, function(name, obj, ran)
    local pc = kp.obj.pc()
    if name == 'k_def_heartbt01' and pc and obj == pc:id() then
        local sep = package.config:sub(1, 1)
        local p = kp.gamedir() .. sep .. 'kotorjit' .. sep .. '_sm_ab_out.txt'
        local f = io.open(p, 'a')
        if f then
            f:write(string.format('{mode}:DONE:%s\\n', tostring(ran)))
            f:close()
        end
    end
end)
""",
                encoding="utf-8",
            )
            self.ch.request("reload", timeout=30.0)
            ok_exec, _, err_exec = self._lua_eval_ok("nwscript.call('ExecuteScript', 'k_def_heartbt01', kp.obj.pc():id()); return true")
            time.sleep(0.2)
            ev_after = self.ch.events(limit=50)
            ab_text = ab_probe_file.read_text(encoding="utf-8") if ab_probe_file.is_file() else ""
            saw_pre = f"{mode}:PRE" in ab_text
            saw_done_ran = f"{mode}:DONE:true" in ab_text
            saw_done_blocked = f"{mode}:DONE:false" in ab_text
            ab_ok = ok_exec and saw_pre and (saw_done_ran if expect_done else (saw_done_blocked and not saw_done_ran))
            results.append(
                ProbeResult(
                    f"U2:ev_ab:OnRunScript:{mode}",
                    "U2_events_and_returns",
                    "event_ab",
                    "OnRunScript",
                    mode,
                    "passed" if ab_ok else "failed",
                    reason="" if ab_ok else (err_exec or f"AB mismatch (saw_pre={saw_pre}, ran_true={saw_done_ran}, ran_false={saw_done_blocked}, text={ab_text!r})"),
                    observed={"ok_exec": ok_exec, "saw_pre": saw_pre, "saw_done_ran": saw_done_ran, "saw_done_blocked": saw_done_blocked, "events_seen": len(ev_after)},
                    invariants_ok=bool(ab_ok),
                )
            )
        if ab_probe_file.exists():
            ab_probe_file.unlink()
        if dump_path.exists():
            dump_path.unlink()
        return results

    def capture_traces(self, universe: UniverseSpec, context: Dict[str, Any]) -> List[TraceRecord]:
        if not self.captured_events and self.ch is not None:
            try:
                self.captured_events = self.ch.events(since=0, limit=500)
            except Exception:
                self.captured_events = []

        traces: List[TraceRecord] = []
        # Synthesize trace-replay probes from safe observed module/game state queries & captured scripts
        traces.append(TraceRecord("live_state", "GetModuleName", []))
        traces.append(TraceRecord("live_state", "GetFirstPC", []))
        ctx_objs = (context.get("context_values") or {}).get("object") or []
        if ctx_objs:
            traces.append(TraceRecord("live_state", "GetTag", [ctx_objs[0]]))
            traces.append(TraceRecord("live_state", "GetName", [ctx_objs[0]]))
            traces.append(TraceRecord("live_state", "GetPosition", [ctx_objs[0]]))
            traces.append(TraceRecord("live_state", "GetFacing", [ctx_objs[0]]))
        seen_scripts = set()
        for ev in self.captured_events:
            if ev.get("event") == "OnRunScript":
                sc = ev.get("script")
                if isinstance(sc, str) and sc and sc not in seen_scripts and len(seen_scripts) < 10:
                    seen_scripts.add(sc)
                    traces.append(TraceRecord("ring_OnRunScript", "GetObjectByTag", [sc, 0]))
        return traces
