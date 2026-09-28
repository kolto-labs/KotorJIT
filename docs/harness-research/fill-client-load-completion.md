# Why the client never finishes a load headless

K1 GOG / Steam-unpacked, image base 0x400000. Corpus root:
/home/brunner56/biodecompwarehouse/kotorxid/output/kotor_readable/K1__k1_win_gog_swkotor.exe

## The answer

`CClientExoAppInternal::area_not_ready_to_display` (+0x288) is the field the
harness polls to decide a load finished. It has exactly one clearing site in
the binary: clientexoappinternal.cpp:10988. Reaching it needs the local flag
set at :10556, which sits inside `if (renderWindowActive != 0)` opened at
:10491. So with the render window inactive and no movie playing, nothing can
clear the flag and `HideLoadScreen` never runs. Flag pinned at 1, load screen
on screen, game still ticking: exactly the observed failure.

`renderWindowActive` is the global at **0x007A3A38**. Only
`ActivateRenderWindow` @ **0x00401E00** (__stdcall, no arguments, no `this`)
sets it, and `WinMessageHandler` calls that only on WM_ACTIVATEAPP with
wParam != 0 and hWnd == the render window. Under a bare virtual display with
no window manager that message never arrives, so the flag stays 0 for the
life of the process. A static scan found 8 references to the address and no
unaccounted writer. `DeactivateRenderWindow` @ 0x00401D90 zeroes it again and
also pauses server state 2 and deactivates input.

## The gate chain into the completion block

clientexoappinternal.cpp:10440-10558, all must hold:

1. `+0x288 != 0` and `+0x18` (client module) `!= 0`
2. `GetCreatureByGameObjectID(client, +0x20 player_creature_id) != 0`
3. `CSWCModule::GetMiniGame(module) == 0`
4. `+0x338 future_leader == 0x7F000000` (constructor default, so normally fine)
5. `renderWindowActive != 0`

## What to do about it

Preferred: call `ActivateRenderWindow()` (0x00401E00) from the client
main-loop detour before delegating, and re-assert every frame because it
self-guards and an incoming deactivate would undo it. That is the engine's
own path, so all fourteen side effects of the completion block then happen in
their intended order: `HideLoadScreen(1,1)`, the timer pause/reset/unpause
block, `StartSounds`, `StartGlobalFade`, `SetCanSendDialog(1)`,
`SetSoundMode(0)`, and finally the clear at :10988.

Fallback if that faults: write `*(u32*)0x007A3A38 = 1` each frame. It opens
the same gate and skips a gamma call made through the Aurora internal vtable,
but the server does not get the `SetPauseState(2, 0)` and input stays
inactive.

Do NOT "fix" this with `CClientExoApp::SetAreaNotReadyToDisplay`
(0x005EDAE0). It satisfies the harness poll while skipping the load-screen
teardown, the timer unpause, and the input and dialog enabling. That is a
green light on a client that is not actually in gameplay.

## Related facts recovered

- `loggedIn` is the global at **0x008328FC**, written only at
  nwchandlemessage.cpp:2272 (`HandleServerToPlayerLogin` @0x0064EC00, case 5,
  Login_Confirm). The only thing the client refuses while it is 0 is
  Module_Info: `HandleServerToPlayerModule` @0x006684F0 case 1 returns early
  without creating or loading the client module.
- Server-side, `CServerExoAppInternal::LoadCharacterFinish` @0x004B5C50 sends
  both Login_Confirm and Module_Info, guarded by the player's `+0x24` state.
- `CClientExoAppInternal::HideLoadScreen` @0x005F6E20, wrapper
  `CClientExoApp::HideLoadScreen` @0x005EDA90 `(this, doFade, doUpdateScreen)`,
  `ret 8`. Safe to call directly; no waits.
- `CClientExoApp::GetAreaNotReadyToDisplay` @0x005EDAD0 is the reader.
- Client module pointer is `CClientExoAppInternal+0x18`; the struct layout was
  re-derived from types.h with every self-anchored field offset matching.

## Still open

Whether gate 5 is the only one failing. One read settles it: with the load
stuck, `module != 0` together with `renderWindowActive == 0` confirms it;
`module == 0` points instead at `loggedIn` and the message chain.

## SUPERSEDED by live measurement (2026-09-09)
The renderWindowActive theory above is WRONG at runtime. Measured on two boots:
0x007A3A38 reads 1 at the main menu before any load and stays 1 throughout the
stall, and writing 1 to it while stuck changed nothing over 60s. Under this
Xvfb setup the game does receive its activate message. The static reading of
the code path is correct; the premise that the flag is 0 is not.

The real cause is a three-way deadlock. Gate 2 of the completion block is what
fails: CClientExoAppInternal+0x20 (player_creature_id) is 0x7F000000, so the
client has no control object.

  client clears +0x288   <- needs ControlObject (CreatureUpdate subtype 2)
  ControlObject sent     <- needs MovePlayerToArea, i.e. CSWSPlayer+0x24 == 2
  +0x24 becomes 2        <- needs PlayerToServer Area subtype 3 (AreaLoaded)
  AreaLoaded sent        <- only from HandleServerToPlayerUpdate_WorkRemaining
                            (nwchandlemessage.cpp:1553) when progress == total
  WorkRemaining written  <- only inside SendServerToPlayerGameObjUpdate
  that send              <- UpdateClientGameObjectsForPlayer early-returns  <== BREAK

Why the harness diverges from the GUI path is recorded in critic-re.md under
SECOND CORRECTION: RunModule's placement loop runs before LoadPrimaryPlayer and
skips a player whose +0x24 is still 0.

Live values while stuck: +0x288 = 1, ci+0x20 = 0x7F000000, s.load_from_savegame
= 1 (MovePlayerToArea clears it, so it never ran), CSWSPlayer+0x24 = 1 (not 2),
+0x2c/+0x30 = 0 (no GameObjUpdate ever sent), stats all idle, load_game_error 0.

Ruled out by measurement, do not revisit: paused world timers, renderWindowActive,
movies and fades, a load error, and dead client message processing.

Routes out, cheapest first:
1. Send CSWCMessage::SendPlayerToServerArea_AreaLoaded (__stdcall, no arguments,
   UN/_0067.cpp:1827) once server_mode == 2 and CSWSPlayer+0x24 == 1. Skips the
   engine's readiness accounting, so the load bar never reaches 100%.
2. Call MovePlayerToArea server-side after LoadPrimaryPlayer, replaying what
   RunModule would have done had the ordering been right.
3. Supply a real login so +0x24 is 1 before RunModule's loop. Needs the BIC
   fixture the corpus notes as missing.
Any route that bypasses the completion block must unpause the world timers
itself, because load_save pauses both and only that block unpauses them.
