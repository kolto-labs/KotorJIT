# K2 GOG save-load blocker: bounded read-only audit

**The only unresolved entry in GameAdapter::load_save's required list is client.net_layer. Exact original-image accessor proves CClientExoAppInternal+0x10, pointer size4.** Adding this single evidence-backed field to the authoritative adjudication input and regenerating the K2 table is the shortest native unblock; it is not proof that a full private save load completes.

Exact input `/home/brunner56/swkotor-multiplayer-investigation/artifacts/k2_gog_aspyr_20260917/swkotor2-client.exe`; independently hashed SHA256 `777bee235a9e8bdd9863f6741bc3ac54bb6a113b62b1d2e4d12bbe6db963a914`. Corpus read-only binary22 `TSL__k2_win_gog_aspyr_swkotor2.exe` identifies GetNetLayer0x40ccb0. No binaries executed.

## Required table sites

Current data/addresses/k2_gog_aspyr.json resolves g.app_manager0xA11C04; app.create_server0x401B80; net.start_connect_to_session0x640150; msg.request_status0x505E10; app.set_load_from_savegame0x64C820; client.set_loading_savegame0x40E0C0; client.send_load_game_request0x40CBE0; client.message_handler field+0x150,size4. client.net_layer alone is unresolved. Table summary missing_required=[] concerns global required-site flags, not the load_save operation's runtime require list; the field is globally optional but operationally mandatory.

## Direct field evidence

GetNetLayer0x40ccb0 is thiscall(ECX=CClientExoApp*, no arguments), pointer returnEAX, plain ret0x40cccb. Original instructions:
-0x40ccbc `8b4804`: internal=[app+4].
-0x40ccbf `8b5110`: net=[internal+0x10].
-0x40ccc2..c5 copy net toEAX;0x40cccb ret.
Full accessor bytes: `558bec83ec08894df88b45f88b48048b51108955fc8b45fc8be55dc3`.

Neighbor GetSWCMessage0x40ccd0 independently confirms the existing handler field:0x40ccdc loads app+4;0x40ccdf `8b9150010000` loads internal+0x150; return pointerEAX. This corroborates both the app/internal convention and the existing field-owner model.

Original GUI CSWGuiSaveLoad::LoadGame0x5d33b0 uses CreateServer(0) at0x5d370f/0x5d3a0f, calls StartConnectToSession at0x5d37b1/0x5d3aae via client virtual getter slot+0x10, and calls GetSWCMessage0x40ccd0 followed by RequestStatus0x505e10 at0x5d37db/0x5d3ad5. It calls SetLoadFromSaveGame(1)0x64c820, SetLoadingSaveGame(1)0x40e0c0, then SendLoadGameRequest0x40cbe0 at0x5d3b78 and0x5d3dcd. This is concrete K2 save-flow evidence supporting the shared adapter sequence; the virtual getter's vtable target was not separately expanded in this bounded audit.

## Authoritative input and minimal implementation ownership

Do not patch generated addresses alone. Site declaration already exists at data/hooksites.toml:1551, name client.net_layer,class CClientExoAppInternal,method net_layer,kind field. Add the logical binding `CClientExoAppInternal::net_layer` to `data/adjudication/k2_gog_aspyr_harness_bindings.json` (or a narrowly named `k2_gog_aspyr_*_bindings.json` concern file). Required shape: kind field,owner CClientExoAppInternal,addr0,offset0x10,size4,accept verdict and exact-image/accessor evidence. No native method binding or ABI guess is needed.

`tools/gen_address_tables.py:582` load_overlay loads all matching alias concern files; accepted bindings carry addr0 legally, field offset/size/owner, and outrank automatic corpus matching. Duplicate logical binding definitions are rejected. Generated output is data/addresses/k2_gog_aspyr.json. Existing message_handler record in the harness adjudication file is the relevant format example. The file's accept_rule requests multiple evidence signals; preserve actual provenance rather than invent a types.h read: this audit established corpus function identity plus exact raw accessor/body and neighboring owner getter, not a fresh recovered type declaration. Additional source-type corroboration can be scoped if that rule requires it before acceptance.

## Practical path and limits

1. Apply only the authoritative field and regenerated table; require the exact image identity and confirm status no longer lists client.net_layer missing.
2. In the controller-owned private stage, invoke ordinary load_save with a save FOLDER NAME, using copied private save and separate gameinprogress output. The adapter reads savenfo.res/LASTMODULE, unpacks SAVEGAME.sav and drives native load. It must retain normal callable/pointer checks; no hardcoded+0x10 fallback in C++.
3. Treat request success as issued, then independently verify module/PC/world readiness. The unresolved K2 stats fields, module.name, timer.paused and some UI fields can limit observation or post-load completion even after this gate is removed. Do not clear auto-pause or reuse guessed K1 offsets to force progress.

The inspected GUI StartConnect call pushes five arguments matching the adapter's general shape, but its last flags byte comes from ds:0x998984 rather than this audit establishing a literal0x10. Complete K1/K2 save-flow parity, optional completion paths and all argument semantics are not claimed here. Existing field resolution alone is not runtime execution proof.

If the native path remains unresolved or trips another capability, use the game's normal visible Load Game menu on the private copied save; it owns its GUI panel, unpacking and K2-specific transition sequence. Do not call CSWGuiSaveLoad::LoadGame with a fabricated/null this pointer. UI interaction remains controller-owned and was not performed by this audit.

No source/index changes, builds, games, broad corpus scans or recovery jobs. Only this requested private report written.
