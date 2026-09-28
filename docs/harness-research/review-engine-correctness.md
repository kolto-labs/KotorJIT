# Review findings: review-engine-correctness

Independent read-only review of the harness, run 2026-09-09 against the
implementation in src/harness/ and scripts/harness/kpharness/. Findings are
ranked most severe first. Items already fixed are noted in the repository
history; the rest stand as known issues.

1. **`src/harness/engine_k1.cpp:549-553, 667-675` — major.** `client.set_player_character_name` is treated as required and called unconditionally. The later correction says it is optional for save loads; the player comes from `Module.ifo` (`docs/harness-research/critic-re.md:34-38`). Remove it from `require()` and guard the call with `have()`.

2. **`scripts/harness/kpharness/waits.py:48-63, 97, 209-216` — major.** The driver reads nonexistent `waiting`, while C++ emits `waiting_for_player` (`src/harness/commands.cpp:468-481`). It can report a dialog ready prematurely and never auto-skip voice waits. Use `waiting_for_player`, and expose/consume an explicit sound-wait field for VO skipping; the RE fact says VO waits do not scale (`docs/harness-research/fill-time-scale.md:63`).

3. **`scripts/harness/kpharness/waits.py:220-243` — major.** `globals` ignores the actual C++ result `{bools, numbers, strings}` (`src/harness/commands.cpp:796-813`), sends an ignored `name` argument, then falls back to Lua. Parse the three typed maps by name and issue `globals` without pretending it is a scalar lookup. The design says `globals` pulls table values (`docs/harness-design.md:194-197`).

4. **`src/harness/commands.cpp:468-482`, `scripts/harness/kpharness/scenario.py:444-457, 492-497` — major.** The documented dialog result includes per-reply `active`, but C++ emits only `index`, `link`, and `text`; the Python driver therefore treats inactive rows as active. This contradicts the dialog contract (`docs/harness-design.md:138`) and the active/inactive reply construction described in `docs/harness-research/fill-Reply_choice_by_engine_call_t.md:32-35`. Emit active status or stop filtering on a field the protocol does not provide.

5. **`scripts/harness/kpharness/scenario.py:428-435`, `checkpoints.py:92-106` — major.** These rollback/load paths call `load_save` with the channel’s default 10-second timeout instead of the configured load timeout. The load path includes archive extraction and the multi-call engine sequence (`docs/harness-research/critic-re.md:5-6`). Pass `timeout=load_timeout` in both locations.

6. **`src/harness/engine_k2.cpp:76-77`, `src/harness/engine_k1.cpp:1018-1023` — major.** K2 hardcodes K1 `timer_paused +0x24` even though `timer.paused` is unresolved in the K2 bindings. The shared code then assumes the timer was unpaused and can unpause an already-paused timer. Fixed-step must bracket every timer while preserving its prior pause state (`docs/harness-research/critic-re.md:8`; `docs/harness-design.md:567-573`). Leave the K2 offset unknown and return unsupported or use a verified K2 field.

**Verified correct:** K1 PE `ret N` cleanup matched every adapter call; `CreateServer` correctly passes its required `0` argument. Calling-convention selection, CExoString pointer layout, corrected K1 offsets, global/journal walks, nullable journal handling, module setters, reply vtable slot `+0x6c`, reply acceptance predicate, corrected phase classifier, abort via `-2`/`StopDialog`, screenshot/events shapes, and the `"unsupported on"` prefix all match the cited facts.


