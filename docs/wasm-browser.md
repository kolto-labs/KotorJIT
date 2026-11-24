# Browser / WASM embed (low priority)

Hyperstim will eventually embed playable KotOR in a browser the way
[KotOR.js](https://github.com/KobaltBlu/KotOR.js) does, but as a first-party
target of this repo — not a fork of game assets.

## Non-negotiables

1. **No game IP in git or deploy artifacts.** The site ships the player +
   tooling; the user supplies a local legal install (Steam/GOG/disc) that the
   browser reads via File System Access / drag-drop / local HTTP bridge.
2. **Shared tooling with F12.** The in-game ImGui Lua console
   (`docs/devtools-console.md`) and any Chrome DevTools-style panel in the
   browser talk to the **same** command/result pipeline (`devtools` harness
   ops + `kp.*` / `nwscript.call` separation).
3. **Reuse across builds.** Portable signatures / AgentDecompile hook packs
   identify K1/K2 Win/Mac/Linux images; WASM is another delivery of the same
   logical sites, not a one-off port.

## Suggested layout (when implemented)

```text
wasm/
  README.md           # how to build with emscripten; no assets
  shell/              # HTML/JS host: asset picker, iframe, DevTools panel
  bridge/             # JS ↔ Lua/devtools message protocol (mirrors harness JSON)
native/               # optional: thin PE/ELF host reused by wasm glue
```

## Phasing

| Phase | Deliverable |
|---|---|
| 0 (now) | This stub + F12 console shared protocol documented |
| 1 | Asset-picker shell that refuses to run without user-provided files |
| 2 | Minimal Odyssey loop in WASM (boot → module load) against user files |
| 3 | Wire `devtools` submit/status/output to the browser panel |
| 4 | Full gameplay parity is out of scope until 1–3 are proven |

This track must not block footlocker demos, harness routes, Mac Mach-O loader
work, or native packaging.
