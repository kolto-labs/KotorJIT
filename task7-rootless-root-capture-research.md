# Task 7: rootless Xwayland root capture research

Date: 2026-09-27. Read-only. No Gamescope, Xwayland, Wine, game, or FFmpeg capture was started. The worktree and the live-game lock were not touched.

Upstream sources were fetched into `/tmp/t7src/` (scratch space, not the worktree):

- xserver `master` at `0da4d2480066fb2c783325e7594902aacc23413e` (2026-02-08)
- FFmpeg `n8.1.2` (`libavdevice/xcbgrab.c`)
- gamescope `master` (`src/steamcompmgr.cpp`)
- wlroots `master` (`xwayland/server.c`)

Line numbers below refer to those files. The Xwayland version on the host could not be read from this sandbox, so it is `unverified`. Every behaviour the verdict depends on was introduced between 2009 and 2016 (git blame below), so any current Fedora 44 Xwayland should have it.

## Verdict: **root capture black** (derived from source; no empirical capture exists)

The planned private-root command is `x11grab -draw_mouse 0 -i :N.0` with no `-window_id`. On Gamescope's rootless Xwayland it is expected to:

1. **Keep MIT-SHM.** No `Continuing without shared memory` line appears, so the new `capture_shm_fallback` gate passes.
2. **Return all-zero (black) 1024x768 frames at full cadence.** The cadence gates pass too.

The current brief's diagnostic criteria would therefore accept a black recording.

## Source chain

1. **Gamescope starts Xwayland rootless.** wlroots `xwayland/server.c:50-53` adds `-rootless -core -terminate`, and `:94` adds `-force-xrandr-emulation`. This matches the admitted cmdline in `display-only-runs/20260927-100845-8cd691c3/gamescope-lease.json`: `Xwayland :1 -rootless -core -terminate ... -force-xrandr-emulation`.
2. **Gamescope redirects every top-level window manually and never paints them back to the root.** `steamcompmgr.cpp:9079` calls `XCompositeRedirectSubwindows(ctx->dpy, ctx->root, CompositeRedirectManual)`. Xwayland creates an `xwl_window` only for manually redirected windows when rootless (`xwayland-window.c:1501-1503`), and it redirects them itself too (`:1548`). Automatic-redirect damage is the only path that paints children into a parent: `compalloc.c:213` registers damage only for `CompositeRedirectAutomatic`, and `compReportDamage` at `:73-87` feeds `compPaintChildrenToWindow` (`compwindow.c:734-760`).
3. **The root has no storage.** In rootless mode the screen pixmap is created 0x0:
   - `xwayland-glamor.c:154-156`: `fbCreatePixmap(screen, 0, 0, ...)`
   - the same in `xwayland-shm.c:364-366`
   - `xwayland-screen.c:1010-1013` comments "In rootless mode, we don't have any screen storage".

   The root window's pixmap is the screen pixmap (`fb/fbwindow.c:30-35`; `dix/main.c:211-228` creates screen resources before the root window).
4. **The root's visible region is empty.** `xwayland-screen.c:1013` sets `ROOT_CLIP_INPUT_ONLY`. `dix/window.c:3690-3697` then empties the root `borderClip` ("so no rendering will ever be attempted to the screen pixmap"). `xwayland-window.c:1621-1623` also sets the root `clipList` and `borderClip` to `RegionNull` on realize.
5. **ShmGetImage on the root succeeds but is fully censored.** `Xext/shm.c:638-658`: the root passes the realized, on-screen and in-border checks, because the root is screen-sized at 0,0. `pVisibleRegion = &root->borderClip`, which is empty. After `GetImage`, `XaceCensorImage` (`Xext/xace.c:183-266`) computes image minus visible region, which is the whole frame. It then fills that area with a scratch GC whose `fgPixel = 0` (`dix/gc.c:1059`), or `memset(0)` if that fails. Result: **every SHM frame is black and no error is raised.**
   - `unverified`: the underlying `fbGetImage` read from the 0x0 pixmap (via `glamor_image.c:115-117` → `:147-152`) reads out of bounds. That could return garbage (which is then censored) or, less likely, crash Xwayland.
6. **Plain GetImage on the root fails with BadMatch.** `dix/dispatch.c:2195-2200` bounds the request by the window's backing pixmap, and `:2225-2231` returns `BadMatch` when the rectangle falls outside it. Because the root pixmap is 0x0, every root `xcb_get_image` gets BadMatch. If SHM ever fell back on the root, FFmpeg's `xcbgrab_frame` would fail every frame with `AVERROR(EACCES)` (`xcbgrab.c:169-181`) rather than silently degrading.
7. **The Composite overlay window is not an option.** `xwayland-window.c:1606-1610` forces it unmapped in rootless mode ("We do not want the COW to be mapped").

Git blame on these lines (GitLab API):

| Change | Commit | Date |
|---|---|---|
| Empty-clip root mode (`dix/window.c`) | `e957a2e5dd` | 2016-02-22 |
| Rootless glamor root handling | `51a4399b94` | 2015-11-30 |
| Rootless glamor root handling | `2f113d68f6` | 2014-06-24 |
| GetImage bounds check, "Bug #22804" (`dix/dispatch.c`) | `587c3a2d19` | 2009-07-22 |

## Why the child-window capture lost SHM

- The failure fired on the very first frame (`ffmpeg.log:11`, sequence 10), and `xcbgrab.c:468-471` then sets `has_shm = 0` permanently. A transient condition at startup was therefore enough to lose SHM for the whole run.
- `resource_id:14680064` = `0xe00000` is FFmpeg's SHM segment XID (`xcbgrab.c:251`, `xcb_generate_id`), not the window. `dixLookupResourceByType` sets `client->errorValue = id` unconditionally (`dix/resource.c:1218-1219`) inside `VERIFY_SHMPTR` (`shm.c:132,638`). The segment lookup succeeded, since the error was not BadShmSeg.
- `error_code 8` (BadMatch) is therefore produced only by the window-check block at `shm.c:639-652`.
- The non-SHM `DoGetImage` on the same window succeeded and produced real game frames for 234 s. So the child passed viewable, in-border and backing-pixmap bounds (`dispatch.c:2184-2200,2229`).
- The only checks unique to ShmGetImage are `realized` and **absolute on-screen bounds against `pScreen->width/height`** (`shm.c:640-646`). That test predates Composite; `DoGetImage` was relaxed to use backing-pixmap bounds instead (`dispatch.c:2218-2231`, comment "We relax the window case...").
- **Most likely cause:** at the first grab, the child's absolute rectangle (x, y, 1024x768) was not inside `pScreen` (rootless screen size = output extent, `xwayland-output.c:221-245`). **`unverified`:** the run recorded only `geometry_at_start [1024,768]`, not absolute X/Y or root dimensions. The new recorder does record `xdotool` X/Y and root size (`recording.py:707-722`).
- Settling it takes one `xwininfo -id <win>` plus `xwininfo -root` at FFmpeg start.

Because the child is a manually redirected window with a real backing pixmap and non-empty clip, ShmGetImage on it would return content once the bounds condition holds. That is inferred from item 5 plus the non-SHM success; it is `unverified` empirically.

## Did the current design address this?

No. The brief (`task7-capture-cadence-fix-brief.md`) has no content check:

- Distinct frames are "a reported observation, not a cadence pass condition" (line 268).
- The diagnostic pass list (lines 437-448) checks SHM absence, cadence, gaps, drops and duplicates only.
- The only planned branch to PipeWire is on `capture_shm_fallback` (lines 17, 450). A black root would never take that branch.

`recording.py` builds the root command (`:935-941`) and gates only on the fallback string (`:876-877, 1026-1027, 1114-1115`). `distinct_game_frames` stays `unvalidated` (`:568`). `display_backends.py:_root_capture_matches` (`:616-677`) checks command shape and `shm.status == no_fallback_observed` only.

## Implications for the single animated diagnostic

1. **Add a content hard stop before any cadence verdict.** Without it the diagnostic passes on black.
   - First frame (and a sample every N s): not all-zero, e.g. `signalstats` YMAX > 16 or luma variance > 0 on the lossless/raw path.
   - Over the animated interval: distinct decoded frames (`framemd5`) ≥ the pattern's known change count × 0.99.
   - A frame-counter pattern with pixel-exact expectations is stronger than variance alone.
   - Keep it adapter-neutral: a `content` block next to `cadence`, typed failure `capture_content_black` or `capture_content_static`.
2. **Expect the private-root diagnostic to fail that stop.** Run it anyway only if the parent wants empirical confirmation. It is cheap: it needs no game, just any animated X client on the private display plus a 5 s capture. Otherwise skip straight to one of the alternatives below.
3. **Ruled out:**
   - Composite overlay window: forced unmapped in rootless mode (item 7).
   - Root capture in any form: the root has no content.
4. **`XCompositeNameWindowPixmap` plus ShmGetImage on the pixmap would work in principle.** The pixmap branch at `shm.c:660-665` has only size checks and no censoring (`pVisibleRegion` stays NULL). But it needs a custom grabber, because FFmpeg `-window_id` calls `xcb_translate_coordinates` on the drawable every frame and aborts if that fails (`xcbgrab.c:447-455`); a pixmap XID would fail there (`unverified` empirically). The helper would also have to handle pixmap lifetime across resize and client disconnect. That is a transport change of similar size to PipeWire.
5. **PipeWire via gamescope does not need `-e`.** The stream is already published without `-e`: `gamescope.log` in the display-only run says `pipewire: stream available on node ID: 248`, and the audited run published node 208. `-e` is Steam integration and unrelated. This is the brief's planned follow-up adapter (`pipewiresrc path=<node>` in GStreamer). Its cadence behaviour is `unverified`.

## Cheapest alternative that keeps MIT-SHM and full cadence

**Go back to child-window capture (`-window_id <verified game window>`) and remove the cause of the SHM BadMatch.** Do not use root capture.

- It keeps FFmpeg x11grab, MIT-SHM and the existing encoder, with no new transport.
- The window already carries real content (234 s of real frames via the non-SHM path in the audited run).
- ShmGetImage on it only needs the window's absolute rectangle inside `pScreen` at the first grab (`shm.c:640-646`), because SHM loss is latched from frame 1 (`xcbgrab.c:468-471`).

Concretely:

1. Before starting FFmpeg, require that `xwininfo -id` absolute X/Y = 0,0 and width/height ≤ the `xwininfo -root` dimensions, and that both equal the lease geometry. The new code already does the X/Y and root-extent checks (`recording.py:707-722`). Reuse them as the precondition for `-window_id` instead of switching the drawable.
2. Keep the fail-closed `capture_shm_fallback` gate. Record `xwininfo` output at FFmpeg start so a future BadMatch can be attributed.
3. Add the content hard stop anyway.

If the bounded diagnostic still shows BadMatch with verified 0,0 / in-screen geometry, the cause is something else (for example `realized`, or an Xwayland/Gamescope `-force-xrandr-emulation` size mismatch; `unverified`). In that case, go to the PipeWire node adapter, not root capture.

## Claims (prove-the-effort format)

claim: Root ShmGetImage on rootless Xwayland returns all-black frames without an error.
referent: `Xext/shm.c:639-658`; `Xext/xace.c:183-266`; `dix/window.c:3690-3697`; `xwayland-screen.c:1010-1013`; `xwayland-window.c:1621-1623`; `dix/gc.c:1059`
checked: source read at xserver master 0da4d24; blame shows 2015-2016 origin
verdict: holds (source-derived)
confidence: medium-high. A single private-display capture with a nonzero first-frame YMAX would overturn it.

claim: Root non-SHM GetImage returns BadMatch in rootless mode.
referent: `xwayland-glamor.c:154-156` / `xwayland-shm.c:364-366` (0x0 screen pixmap); `fb/fbwindow.c:30-35`; `dix/dispatch.c:2195-2231`
checked: source read
verdict: holds
confidence: high for source; not run empirically.

claim: Gamescope composites via manual redirect and nothing paints to the root.
referent: `steamcompmgr.cpp:9079`; `compalloc.c:73-87,213`; `compwindow.c:734-760`
checked: source read
verdict: holds
confidence: high.

claim: The child-window SHM loss came from the SHM-only absolute on-screen check, not from the segment or a transport fault.
referent: `ffmpeg.log:11` (error 8, resource 0xe00000 = SHM segment); `dix/resource.c:1218-1219`; `shm.c:638-652` vs `dispatch.c:2184-2231`; non-SHM success over 234 s
checked: source read plus preserved log
verdict: unresolved (narrowed to `realized` or screen-bounds; geometry at first grab was not recorded)
confidence: medium. `xwininfo -id` / `xwininfo -root` at FFmpeg start would settle it.

claim: The current brief and code would accept a black root recording.
referent: brief lines 268, 437-450; `recording.py:568, 876-877, 935-941`; `display_backends.py:616-677`
checked: grep and read of the worktree
verdict: holds
confidence: high.

claim: Gamescope publishes a PipeWire node without `-e`.
referent: `display-only-runs/20260927-100845-8cd691c3/gamescope.log` ("stream available on node ID: 248"), launched without `-e` (lease `command`)
checked: log read
verdict: holds
confidence: high. Cadence through PipeWire is `unverified`.
