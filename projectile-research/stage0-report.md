# Object blaster Stage 0 report (host prep only)

Date: 2026-09-27. Scope: private files under this directory only. No repository,
live-game lock, Wine, game, Gamescope or FFmpeg was touched.

## Diff summary

- `blaster_fixture.lua`: adds `F.restore_report()` after `F.restored()` (66 added lines, nothing else changed).
  - Reports the five `restored()` / step-20 conditions separately against the `begin()` snapshot:
    `target_invalid`, `slot4_restored`, `slot5_restored`, `min_one_hp_restored`, `inventory_unchanged`.
  - Id lists: `missing`, `new`, `stack_changed` (shown as `id:before->after`). It also lists `other_changed`
    (base, possessor or tag differs), so a false `inventory_unchanged` always names an id.
  - Raw values next to each boolean: slot 4 and 5 now and expected, `borrowed_in_slot4`, target id and
    validity, MinOneHP now and expected, `context_ok`, and `errors`.
  - Returns `(string, table)`. The string always starts with `restore_report:`. The console shows a
    table only as an opaque value, so the string carries the data.
  - Read-only: calls only `GetIsObjectValid`, `GetItemInSlot`, `GetMinOneHP`, `GetBaseItemType`,
    `GetItemStackSize`, `GetItemPossessor`, `GetTag`, `GetFirst/NextItemInInventory`, `GetArea`,
    `GetModuleFileName`, and `kp.model.matches`. All go through `nwscript.call`. No new Lua names
    shadow NWScript functions.
  - Never raises. Each query runs under `pcall`, a failed condition reports `nil`, and the error text
    goes into `errors=[...]`. With no state it returns `restore_report: state=nil`.
- `blaster-fixture-baseline.toml`: inserts a `console_open` true, `console_command`, `console_open`
  false triple right before the step-20 assert.
  - The command is `code = "return blaster_fixture.restore_report()"`.
  - `contains = ["restore_report:"]` is only the fixed marker. `console_steps.py` rejects an empty
    `contains`, so the marker is needed. It asserts nothing about the result.
  - The harness writes the result to the `console-command-21.json` receipt.
  - The route grows from 21 to 24 steps. The restoration assert moves from step 20 to step 23.
  - Loaded with the worktree harness parser (`kpharness.scenario.Scenario.load`, import only):
    24 steps, and step 21 is `console_command`.
- `borrowed-fixture-test.lua`: the mock gains `tags` and `possessor` overrides. The existing borrow
  case is unchanged. There are 17 new `restore_report` cases:
  - all five pass;
  - each single condition failing: target still valid; slot 4 holds the borrowed gun; slot 4 empty;
    slot 5 empty; MinOneHP left set; plus the inventory condition;
  - inventory: stack change; missing id; new ids; missing, new and stack change together; tag change;
    possessor change; base change;
  - all pass again after reverting;
  - a query error is reported, not raised;
  - an inventory error keeps the other four conditions;
  - `state=nil` before `begin()`.
  - Every case runs `restore_report` under a wrapper that errors on any non-query routine. It
    deep-compares the mock state before and after. It asserts that exactly the expected condition is
    false, and that `all_pass == f.restored()`.

## Hashes (sha256)

| File | sha256 |
| --- | --- |
| `blaster_fixture.lua` | `6acfba47d21578b57834044e718faa4a830ed344aba9adba8283a9f11642f43c` |
| `blaster-fixture-baseline.toml` | `ff476d4edf211abfb3ae058464a387981c95989b22bc9a3b287466a1972d7c21` |
| `borrowed-fixture-test.lua` | `d825af90a3cede23493b250c766829a397f2da3df8bca5f38253f3ae08599e53` |
| `blaster_fixture.lua.pre-stage0` | `a9a0b3394aea170178e54fa0e2d3f6dba4bdeb35e4cc7243e7b4b438a1b1e153` |
| `blaster-fixture-baseline.toml.pre-stage0` | `054e429a2b0426b01d8835a51ddbd081d0c50a913c9d3450e895f627d641d9e8` |
| `borrowed-fixture-test.lua.pre-stage0` | `496aba52fc7b8801016bf175c99c96a567a746ed500cd042c01eddd97cbf5474` |

The `.pre-stage0` hashes match the prior receipt in `borrowed-fixture-change.json` (`a9a0b339…`, `054e429a…`) and the pre-edit test (`496aba52…`).

## Test command and output

The prior receipt ran `lua borrowed-fixture-test.lua` on the host. This session runs in a
container, so the same command goes through `host-spawn`. It was run under host Lua 5.4.8, and
under the 32-bit LuaJIT build to match the in-game VM. The two outputs are identical once the
line numbers in the mock error text are normalized.

```
$ host-spawn lua /home/brunner56/kp-live-20260922/projectile-research/borrowed-fixture-test.lua   # exit 0
borrow selection, exact identity, no inventory deletion, equipment and inventory restoration passed
restore_report case passed: all five pass -> restore_report: all_pass=true failing=[] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=true missing=[] new=[] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: target still valid -> restore_report: all_pass=false failing=[target_invalid] target_invalid=false slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=true missing=[] new=[] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=true min_one_hp=0/want=0 context_ok=true
restore_report case passed: slot 4 still holds borrowed gun -> restore_report: all_pass=false failing=[slot4_restored] target_invalid=true slot4_restored=false slot5_restored=true min_one_hp_restored=true inventory_unchanged=true missing=[] new=[] stack_changed=[] other_changed=[] slot4=513/want=440,borrowed_in_slot4=true slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: slot 4 empty, right item back in inventory -> restore_report: all_pass=false failing=[slot4_restored] target_invalid=true slot4_restored=false slot5_restored=true min_one_hp_restored=true inventory_unchanged=true missing=[] new=[] stack_changed=[] other_changed=[] slot4=2130706432/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: slot 5 empty, left item back in inventory -> restore_report: all_pass=false failing=[slot5_restored] target_invalid=true slot4_restored=true slot5_restored=false min_one_hp_restored=true inventory_unchanged=true missing=[] new=[] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=2130706432/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: min-one-HP left set -> restore_report: all_pass=false failing=[min_one_hp_restored] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=false inventory_unchanged=true missing=[] new=[] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=1/want=0 context_ok=true
restore_report case passed: stack change -> restore_report: all_pass=false failing=[inventory_unchanged] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=false missing=[] new=[] stack_changed=[510:4->5] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: missing id -> restore_report: all_pass=false failing=[inventory_unchanged] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=false missing=[514] new=[] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: new ids -> restore_report: all_pass=false failing=[inventory_unchanged] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=false missing=[] new=[552,999] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: missing, new and stack change together -> restore_report: all_pass=false failing=[inventory_unchanged] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=false missing=[514] new=[552] stack_changed=[510:4->3] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: tag change -> restore_report: all_pass=false failing=[inventory_unchanged] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=false missing=[] new=[] stack_changed=[] other_changed=[513] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: possessor change -> restore_report: all_pass=false failing=[inventory_unchanged] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=false missing=[] new=[] stack_changed=[] other_changed=[441] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: base change -> restore_report: all_pass=false failing=[inventory_unchanged] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=false missing=[] new=[] stack_changed=[] other_changed=[440] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: all five pass after reverting -> restore_report: all_pass=true failing=[] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=true missing=[] new=[] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true
restore_report case passed: query error is reported, not raised -> restore_report: all_pass=false failing=[min_one_hp_restored] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=nil inventory_unchanged=true missing=[] new=[] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=nil/want=0 context_ok=true errors=[min_one_hp=borrowed-fixture-test.lua:43: mock GetMinOneHP failure]
restore_report case passed: inventory error keeps other conditions -> restore_report: all_pass=false failing=[inventory_unchanged] target_invalid=true slot4_restored=true slot5_restored=true min_one_hp_restored=true inventory_unchanged=nil missing=[] new=[] stack_changed=[] other_changed=[] slot4=440/want=440,borrowed_in_slot4=false slot5=441/want=441 target=900,target_valid=false min_one_hp=0/want=0 context_ok=true errors=[inventory=borrowed-fixture-test.lua:43: mock GetNextItemInInventory failure]
restore_report case passed: state=nil before begin -> restore_report: state=nil
restore_report host cases passed: 17
```

```
$ host-spawn /home/brunner56/kp-validation-20260922-build/luajit32/src/luajit /home/brunner56/kp-live-20260922/projectile-research/borrowed-fixture-test.lua   # exit 0
restore_report host cases passed: 17
(17 'case passed' lines; full output identical to the Lua 5.4 run after line-number normalization)
```

## Caveats for the live run

1. **Staging required.** The TOML `dofile`s `kotorphasor/console-examples/blaster_fixture.lua`. The
   staged copy at `stage-k1/kotorphasor/console-examples/blaster_fixture.lua` is still `a9a0b339…`
   (old). The live run must stage `6acfba47…` first. Otherwise `restore_report` is nil and step 21
   fails before the assert.
2. **One snapshot, taken before settling.** `cleanup()` only queues the equip actions, and
   `DestroyObject` is deferred. The report is taken once, at the start of step 23's 30 s poll. A
   false slot or target condition may only mean "not settled yet". The raw values (`slot4=…/want=…`,
   `borrowed_in_slot4`, `target_valid`) show which state it was in. A settled capture needs another
   report after step 23. That would be a new orchestrator decision; nothing was added here.
3. **Baseline difference.** The report compares against the fixture's `begin()` snapshot. Step 23
   compares against the harness step-6 globals (`oldright`, `oldleft`, `oldmin`, `beforeitems`).
   Those are taken 120 ticks earlier, before `begin()`. They should match, but that is not proven.
4. Tags are compared but never printed, because of the trailing-NUL `GetTag` bridge issue.

## Status

Host prep complete. Live run pending capture diagnostic PASS.
