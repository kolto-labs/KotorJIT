# K1 new-game control path

This is a read-only corpus trace for the GOG K1 binary. It is not a live
proof and it does not authorize calling any of the recovered GUI functions
directly. The recovered source is readable Ghidra output and every address
below still needs a raw-image prologue/signature before it can become a
harness site.

## Proven call chain

The ordinary game path is concrete and supplies the required object ownership:

```text
CSWGuiMainMenu::OnNewGamePicked
  -> new CSWGuiClassSelection(manager, "END_M01AA")
  -> CSWGuiManager::AddPanel(...)
  -> CSWGuiClassSelection::OnSelectButton(selected class control)
  -> new CSWGuiMainCharGen(manager, selected class creature, class panel)
  -> CSWGuiManager::AddPanel(...)
  -> CSWGuiMainCharGen::BeginPlayGame
  -> CSWGuiClassSelection::BeginPlayGame
  -> CAppManager::CreateServer
  -> CSWCCreature::SaveCharGenCreature(char_gen_creature)
  -> CNetLayer::StartConnectToSession(...)
  -> CSWCMessage::SendPlayerToServerStatus_RequestStatus
  -> SendMessageToPlayer("sModule.Load END_M01AA")
  -> CClientExoApp::SetPlayerCharacterName("temp")
  -> load screen/input setup
```

The menu handler is `0x67afb0` (487 bytes). It resets the current session,
loads the `END_M01AA` resources and constructs the class-selection panel.
`CSWGuiClassSelection::OnSelectButton` is `0x6db9b0` (192 bytes); it finds the
selected control by identity, takes that control's already-created creature,
constructs the main character-generation panel, and adds it to the manager.
The class-selection constructor is `0x6dc3c0` (2683 bytes). It constructs six
`CSWCCreature` instances at `operator_new(0x44c)` and initializes gender,
class, sound set, appearance and the class-selection controls from the
`PORTRAITS` 2DA. This is the default character source; no save or teleport is
being synthesized.

`CSWGuiMainCharGen::BeginPlayGame` is `0x6eb320` (17 bytes). It only removes
its child panels and delegates to class-selection `BeginPlayGame`,
`0x6dbdf0` (564 bytes). The latter is the minimum useful endpoint: it creates
the server, serializes the selected creature as a `BIC V2.0` GFF, connects the
client/server session, requests status, asks the server to load the selected
start module, and sets the temporary player character name. The serializer is
`CSWCCreature::SaveCharGenCreature` at `0x6123e0` (3276 bytes). Its body writes
the name, race, class/level, stats, skills, feats, appearance, inventory and
standard player scripts into the BIC object before the network start.

## Name, portrait and default construction

The main chargen constructor is `0x6eb420` (2746 bytes), with prototype
`(manager, creature, class_selection)`. It stores the two non-owning links,
calls `DetermineClass`, loads the `MAINCG` layout, and creates quick/custom
child panels. The default creature has already been built by the class
selection constructor, so a caller that skips those constructors has no valid
`this->char_gen_creature` or panel manager.

The name path is a genuine GUI operation. `CSWGuiNameChargen` constructor
`0x6f9e70` (708 bytes) stores the creature pointer and creates the `NAME`
layout. `HandleRandomName` at `0x6f9bf0` (217 bytes) calls `CSWNameGen` and
places the result into the edit box. `HandleDoneButton` at `0x6f9cd0` (403
bytes) validates/trims it, calls `CSWCCreature::SetName`, then reports child
completion. A deterministic TAS should eventually provide a name through a
legitimate control event or a safe wrapper around the name setter; it must not
invent the edit-box object or write its fields.

Portrait selection is performed by `CSWGuiMainCharGen::PortraitChanged` at
`0x6ea9f0` (568 bytes). It reads the selected creature appearance, updates
the portrait/scene and calls the creature appearance setter. This is a
preview/update operation, not the character serialization endpoint.

## Existing signed candidates and missing bindings

The K1 GOG adjudication already accepts the lower-level session calls used by
the final chain:

| Operation | Site | Status |
| --- | --- | --- |
| `CAppManager::CreateServer` | `0x401380` | accepted, expected bytes present |
| `CNetLayer::StartConnectToSession` | `0x5d5040` | accepted, expected bytes present |
| `CSWCMessage::SendPlayerToServerStatus_RequestStatus` | `0x6775e0` | accepted, expected bytes present |
| `CClientExoApp::SetPlayerCharacterName` | `0x5edaa0` | accepted, expected bytes present |
| `CClientExoApp::SetInputClass` | `0x5eda60` | accepted, expected bytes present |
| `CClientExoApp::DisableInput` | `0x5edbe0` | accepted, expected bytes present |
| `CServerExoApp::SetLoadFromSaveGame` | `0x4af060` | accepted, expected bytes present |

The GUI constructors, event handlers, `SaveCharGenCreature`, class-selection
`BeginPlayGame`, and the exact menu input dispatch are absent from the current
K1 harness table. Their decompiler addresses are useful identity candidates
only. Before adding a site, require the target binary's function row, a raw
prologue/disassembly establishing calling convention and displaced bytes, and
an independent body/call-graph check. For cross-binary support, retain a
signature with wildcards around relocations and accept a site only after the
signature resolves uniquely and its expected bytes match.

## Readiness stages

1. **Corpus ready:** the chain and constructor ownership above are documented;
   this is the current stage.
2. **Call-site ready:** independently sign `OnNewGamePicked`, class selection
   selection, the main chargen transition, and `SaveCharGenCreature` for each
   binary. Do not call a decompiler address directly.
3. **Object-control ready:** add a control-plane operation that finds the live
   GUI panel/control through an engine-owned registry or dispatches the same
   event callback the panel uses. The current harness has no safe GUI object
   handle API, so a raw `this` pointer cannot be manufactured.
4. **New-game ready:** run the normal chain with a default class, deterministic
   name/portrait, and the engine's own serialization/network handshake. Prove
   a new save/BIC provenance, `module=end_m01aa`, a valid first PC and the
   rendered gameplay screen. This replaces the advanced AUTOSAVE fixture.
5. **TAS route ready:** checkpoint after the new-game handshake, then drive
   door/NPC/placeable actions with tag lookup and state predicates. NPCs must
   use `ActionStartConversation`; `ActionInteractObject` is placeable-only.

The practical next implementation slice is stage 2 plus a narrow, signed
panel-event bridge. Wrapping `SaveCharGenCreature` alone is insufficient: its
`this` is the selected creature owned by the class-selection panel, and the
normal server setup and status handshake still have to run in order.
