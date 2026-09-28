# K2 native load: main-menu completion gap

Read-only diagnosis, 2026-09-27. Scope: exact K2 GOG Aspyr PE SHA256 777bee235a9e8bdd9863f6741bc3ac54bb6a113b62b1d2e4d12bbe6db963a914; existing load state machine and bound native GUI methods. No game or build performed.

## Finding and minimum correction

The pre-fix `src/harness/engine_k1.cpp` Armed branch only progressed through synthetic AreaLoaded injection. `retire_main_menu()` was reached only from Placed, itself reached through Sent. When the native load completed without injection, Armed saw area-not-ready=0 and `area_loaded_due` correctly refused injection, leaving the menu indefinitely. Missing K2 `client.player_creature_id` also prevents that synthetic predicate; it does not prove the native player is missing.

Add an independent owned-request natural-completion path: capture successful readback of load-from-save=1 after setting it and before sending this request, record the issuing server identity, and accept only same server, mode=2, module present, area-not-ready=0 and load-from-save=0. Then use existing native menu retirement. Do not manufacture an AreaLoaded message just to advance state. Without the observed transition, a reload's pre-existing ready module could be mistaken for completion. Unknown/unreadable fields must refuse completion. A failed/remaining panel should not be reported as visually complete.

## Exact original-byte evidence

- `CServerExoApp::SetLoadFromSaveGame` 0x64c820: ECX is app; loads app+4 into internal; at 0x64c838 `89 82 c4 00 01 00` stores the caller argument to internal+0x100c4; returns `ret 4` at 0x64c841. This directly confirms the 4-byte `server.load_from_savegame` field and existing adjudication. No K1 offset inference.
- `CSWGuiManager::RemovePanel` 0x90eaf0: thiscall(manager,panel), null/not-found return 0; calls panel virtual+0x4c, updates manager membership and state; returns 1 on success and `ret 4` at 0x90ebf7. Existing `gui.remove_panel` matches this ABI.
- Native internal HideLoadScreen 0x444a00 reads its panel at internal+0x278 and manager at internal+0x274, calling RemovePanel at 0x444a8c. This independently corroborates the manager field/method combination already used by `retire_main_menu`.
- `PanelExists` 0x90ec80 is bound; root's private observation already reports main_menu=1. Existing retirement performs membership checks before and after removal.
- Exact K2 `CSWGuiMainMenu::OnLoadSaveGame` 0x53d240 adds the save/load GUI, sets the old menu removal bits, and calls `ClearMainMenuPointer` at 0x53d3b5. `ClearMainMenuPointer` 0x40e820 is a thiscall app wrapper: null-check app+4, write zero to internal+0x280 at 0x40e83e, return. This establishes native GUI bookkeeping, but is not grounds for raw guessed flag writes or invoking a click handler with fabricated controls. Minimal fix can use the already-bound manager removal path and its membership readback. Pointer bookkeeping can be assessed separately if actual repeated-load behavior exposes a problem.

The corpus binary22 identities and exact PE agree on these functions. Existing table binds manager+0x274, menu+0x280, area-not-ready+0x288, mode+0x10008 (2 bytes), load-from-save+0x100c4 (4 bytes), RemovePanel0x90eaf0 and PanelExists0x90ec80.

## Acceptance and limits

Focused tests should cover native completion without synthetic injection, pre-existing ready module without observed arming rejected, changed-server rejected, unreadable/unknown values rejected, loading still in progress rejected, and existing synthetic path retained. A pure predicate test does not prove retirement scheduling: the state branch must visibly invoke existing retirement. Live acceptance must show main_menu=0 and a screenshot of the loaded world while F12 still works; VM-bound/PC-ready and console success alone were insufficient. User-selected physical Load Game UI is a valid separate fallback, not proof the native replay transition is repaired.

This report verifies the exact setter and GUI ABI and identifies the control-flow gap; it does not independently claim every possible server-reset/load-cancellation sequence is covered by the bounded completion predicate. No new profile fields are needed for the minimum correction.
