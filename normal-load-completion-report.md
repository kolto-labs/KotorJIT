# Normal load completion fix

SOURCE FROZEN. Scope: engine_k1.cpp, fields.hpp, kp_harnesstest.cpp only. No index/commit/game/DLL build.

Problem: Armed only handled stuck loads requiring injected AreaLoaded; K2 native completion therefore never reached menu retirement. Fix records load_from_savegame=1 after the request's setters and before SendLoadGameRequest, with server-internal identity. Armed normal completion requires that observed flag, same nonzero server identity, server_mode2, actual GetModule nonzero, area_not_ready0 and load_from_savegame0. It then calls existing native menu retirement once and becomes Done only on verified PanelExists absence; otherwise GaveUp. Existing Sent/Placed repair sequence remains; Placed now likewise honors the absence result rather than falsely reporting Done.

retire_main_menu now returns bool: missing bindings/pointers or unreadable PanelExists refuse, already absent succeeds, otherwise RemovePanel followed by PanelExists validates absence. No repeated removal attempts after terminal failure, no raw panel flag writes. Researcher independently confirmed exact K2 RemovePanel0x90eaf0 thiscall(manager,panel), int return, ret4 and normal HideLoadScreen callshape; existing native call unchanged.

Validation: cmake build target kp_harnesstest -j2 PASS; native host kp_harnesstest zero failures. Added normal-completion positives and negative missing-observed-flag, foreign-server, missingmodule, unknown/pending client/server flags and nonrunning server modes; existing stuck-load predicates continue passing. Scoped diffcheck PASS. Logs /tmp/kp-normal-load-host-{build,test}.log. Host predicate tests do not execute GameAdapter native calls; controller clean DLL build, independent review and live screen acceptance remain required. No live outcome claimed here.

Phase oracle correction: after Error/Loading/Movie priority, main_menu==1 reports Menu regardless running server. Removed unsupported claim that a listed menu cannot own the frame when a server runs. Added running-module/menu negative gameplay and Loading/Movie priority regressions; repeated host suite zero failures.

Known-null menu pointer now proves absence before requiring manager or panel functions; unreadable pointer refuses. A nonnull but unlisted panel succeeds without requiring RemovePanel. Added null/unknown/nonnull pointer predicate regressions; final host suite zero failures.

Frozen SHA256:
6d3c79de3eb38bacd2e7b6826d65589e1e6aa5456157f53b32aa3b8c34d28821 src/harness/engine_k1.cpp
37cf59e1a1482fb272157c6983b3ec6129be89ea9ed7c525fa04981a25f4d760 src/harness/fields.hpp
20fb675528368cab9116725f65bba52b7cf32480fafbb7be0644391b94996cd2 tools/kp_harnesstest.cpp
