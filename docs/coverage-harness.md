# Coverage harness: soft-locks without a playthrough

A change can make the game unwinnable. Modders need that fact before they
walk the module. Keystrokes cannot do that. KOTOR has no nav points, no
accessibility tree, and the LOADING splash accepts no console. The
harness has three layers. Only the first is required for the
"under a minute" loop.

## Layer 1: static graph (this repo, now)

`scripts/harness/coverage.sh [module]`

Reads the install through `kq` (winning copies only). For every `.dlg`
in the module it walks `StartingList` / `EntryList` / `ReplyList`,
collects `Active` (Shown-when) and `Script` (On-fire) resrefs, and
checks that a winning `.ncs` exists. It then pulls CONSTS strings out
of those NCS files.

**Findings a modder can act on immediately**

- Missing NCS: a node names a script the game will not load. The
  option never appears, or the action never runs.
- Unlinked nodes: an entry/reply index that nothing points at.
  Dead content, or a broken Index after a DLG merge.
- Conditional-only strings: a name that appears in an `Active` script
  and in no `Script` script in this module. Often a `GetGlobal*` with
  no in-module `Set*`. Cross-module writes are the usual false
  positive. The report is a suspect list, not a verdict.

That is the "parse every logic gate and ask how it is set" step. It
does not need Wine, Xvfb, or a save.

## Layer 2: API director (Lua, not WASD)

`scripts/examples/coverage/10_cover.lua`

Console lines that call engine routines:

| command | routine |
|---|---|
| `cover setb/setn` | `SetGlobalBoolean` / `SetGlobalNumber` |
| `cover talk <tag>` | `ActionStartConversation` |
| `cover jump <tag>` | `JumpToObject` |
| `cover module` | `StartNewModule` |
| `cover fade0` | `SetGlobalFadeIn(0,…)` |
| `cover autosave` | `DoSinglePlayerAutoSave` |

Movement and menus stay out of xdotool. The console is still how a
headless session *injects* the line (DirectInput). The game is not
being steered by arrow keys.

`kp.as(object, fn)` retargets OBJECT_SELF so `cover talk` / `cover jump`
queue on the PC. `kp.speed(n)` extra-calls MainLoop's original (capped
at 16). `tools/coverage_walk.py` turns a scan JSON into `cover …` lines.

**Reply pick:** `cover pick N` records the visible-option index. A
conversation-manager cave will write that index. Until it lands the
harness may type the digit while `GetIsConversationActive`.
NWScript has no `ChooseReply`. That is a conversation-manager cave,
queued after the graph exists so the walker knows which index to
write. Until then, `GetIsConversationActive` + a single digit is the
honest fallback. One key, not a playthrough.

Checkpoint/rollback: `cover autosave` plus the existing OnSave/OnLoad
sidecar. A full "fork every reply" runner loads that slot, picks, and
restores.

## Layer 3: campaign walker + speed (later)

Start-to-finish × every reply in "a few minutes" is not a speedhack
of `swkotor.exe` alone. Under llvmpipe a module load is tens of
seconds. A campaign has dozens of modules. The minutes-scale path is:

1. Static prune: do not live-walk nodes the graph already proves
   unreachable or whose writers are missing.
2. Skip presentation: fade 0, skip movies (a `PlayMovie` no-op
   cave), skip VO delay (`DelayEntry` / `DelayReply` are already in
   the DLG).
3. Tick scale: MainLoop already detours. A multiplier is a small
   follow-up, not the first lever.
4. Render-off server tick: the real speedup, and a separate cave.

## What "test everything" means here

Not a playthrough. The closure is:

- every dialog node is either reachable under some assignment of
  globals/journal/items the player can actually produce, or reported;
- every `Active` script's reads have a writer on a path the player
  can take, or reported;
- a live director can put the game on that path without touching the
  GUI.

Endar (`end_m01aa`) is the first module the scanner is run against.
A second, later module (e.g. `danm13`) is the check that the
heuristic survives a different designer.

## Non-goals

Replacing the retail GUI for blind players. That frustration is real.
This harness does not make the shipped game speakable. It makes
*mods* fail in a log file instead of in a 20-hour save.
