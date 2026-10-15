# Hook manifest loader (`agentdecompile.hookmanifest/v1`)

Status: gap 3 of the 2026-10-15 hook export spec is implemented. Gaps 1 and 2
are planned only (below). Spec: `agentdecompile_projects/corpus_work/hook-export-spec-20261015/SPEC.md`.

## What the loader does now

`AddressTable::load_manifest()` reads a hook manifest one `functions[]` entry at
a time (a K1 GOG manifest is 51 MB) and builds a **scan-only** table:

- Every code site starts at `addr = 0`. `entry_va`, `entry_rva`, `file_offset`
  and `va_hint` fallbacks are never read.
- Locator per site, in order: `locate.primary` (`pattern` + per-byte `mask`,
  anchor `entry`, offset 0) if it passes SPEC §3.3's validity rule (first byte
  concrete, ≥ 50 % concrete, mask/`??` agree); else `expected_bytes` when the
  generator proved them unique (`expected_bytes_unmasked_count == 1`); else
  `no_locator`.
- `resolve_from_signatures()` scans all patterns in **one pass** over the bound
  executable regions (`api::memory::scan_masked`). Exactly one hit binds;
  0 hits → `locate_error = "missing"`, ≥ 2 → `"ambiguous"`. Both leave the site
  unresolved with `addr = 0`. Required refusals abort the whole install before
  any byte is written (existing `HookSet` rule), and the runtime failure
  message names each site with its reason.
- Kind: `callable.safe` → `call`, else `reference`. Only the KP overlay
  (`data/addresses/<build>.json`) can make a site `detour`/`required`, and it
  cannot detour a site whose manifest `hook.safe` is `refuse`. The overlay
  never contributes an address in scan-only mode; an overlay row that carries
  `expected_bytes` gets them as an exact, unique-or-refuse pattern.
- Overloaded ids get `#2`, `#3`… suffixes; the first keeps the bare name.

Runtime lookup order: `KOTORPHASOR_HOOKMANIFEST`, then
`<game>/kotorphasor/hookmanifest.json`, then `$KOTORPHASOR_ADDRESSES/hookmanifest.json`;
if none exists, the existing hook pack / address table path is unchanged.

## Checks

- `kp_manifesttest selftest` (CTest `kp_manifesttest.selftest`): synthetic
  regions; unique/ambiguous/missing/no-locator, bogus `entry_va` ignored, overlay
  cannot inject an address or detour a refused prologue, wrong build/format
  refuse, install refuses with nothing patched.
- `tools/manifest_resolve_check.py` + `kp_manifesttest image`: maps the real
  K1 GOG `swkotor.exe` (sha256 `9c10e045…1435`) at a non-image-base address and
  resolves the manifest with `k1_gog_103.json` as overlay. 2026-10-15 result:
  10,779 sites → 10,146 pattern-bound, 152 fields, 474 no_locator, 3 ambiguous,
  4 missing (overlay vtable rows: data, not code). All 10,146 equal the
  manifest `entry_va`; all 124 KP-table rows that bound equal KP's address.
  One required site refuses: `vm.stack_push_integer` — its 16 exact bytes
  (`8b09e939080000909090…`) occur at both 0x5D0FE0 and 0x5D1010, so the loader
  correctly refuses rather than guessing. A K1 GOG install from a manifest
  therefore fails closed until the generator emits a longer/contextual
  locator (e.g. `call_site` / `thunk_target` fallbacks) for it.

## Plan: gap 1 — Lua pre/post hooks with arg rewrite and return override

Not implemented. Prerequisites: this loader (sites + `abi`), plus parsing the
manifest `abi`, `hook` and `lua` blocks into `Site` (today they are skipped).

1. **Parse ABI into a compact per-site record** (`convention`, `stack_arg_bytes`,
   `cleanup.ret_imm16`, param storages, `ret.storage`, `abi_confidence`,
   `struct_return`, `variadic`). Admit a site for Lua hooking only when
   `abi_confidence ∈ {proven, consistent}`, `hook.safe == static_ok`,
   `kp_engine_would_accept`, not variadic, and for stdcall/thiscall
   `stack_arg_bytes == ret_imm16`.
2. **Generic stub emitter (SPEC §4.2)** in `src/hooks/`: per site, a small
   executable thunk that saves EAX/ECX/EDX + the arg window into a `HookCtx`
   on the stack, calls cdecl `kp_hook_pre(site_id, ctx)`; if it returns 1,
   load `ctx.ret` into EAX/EDX (or ST0) and `ret imm16` with the site's own
   count; else replay the call into the trampoline with the (possibly
   rewritten) args/`this`, then call `kp_hook_post(site_id, ctx)` and return
   `ctx.ret`. Unit-test it in `kp_hooktool` against local thiscall/stdcall/
   cdecl functions with known `ret imm16`, as the existing detour tests do.
3. **Lua surface**: `kp.hook.pre(id, fn)`, `kp.hook.post(id, fn)`, returning a
   handle with `:remove()`. `ctx.this`, `ctx.args[i]` (typed by `abi.params[i].lua`;
   writes range-checked against `c_type` size), `ctx:skip(ret)` (pre only),
   `ctx.ret` (post may replace). Install is lazy and atomic per site through
   the existing `HookSet`; refused sites raise a Lua error naming the reason.
4. **Safety**: per-site recursion guard (handler calling the same function goes
   straight to the trampoline), run only while the Lua state is live, under
   `KP_HOOK_GUARD` so a fault poisons the site, no yields, game-main-thread
   only (`callable.thread`). Errors in a handler run the original unmodified.
5. **Acceptance**: offline stub tests + `kp_luatest` fixture; live proof only
   through the normal harness lock, never a concurrent session.

## Plan: gap 2 — Lua calls thiscall functions with `this` validation

Not implemented.

1. **Gate**: `kp.native.call(id, this, ...)` exists only for sites with kind
   `call` (manifest `callable.safe`) and an admitted ABI as above. Today the
   manifest sets `callable.safe = false` for every thiscall because the DB
   has no vtable/RTTI facts (`this_check: none`); so step 2 is a hard
   prerequisite, not optional.
2. **`this` validation** (fail closed, in order): pointer non-null and
   4-aligned; `platform::is_readable(this, 4)`; first dword is a vtable
   pointer inside the image's `.rdata`; that vtable equals one of the
   `requires_this` class's known vtables (to be emitted by the generator from
   RTTI `??_7Class@@6B@` / COL records, or from KP's own adjudicated
   `*.vtable` overlay rows, which this loader already binds by bytes). Classes
   without a known vtable stay uncallable. Optionally resolve through
   `kp.obj` ids (`object_id` → server object) so scripts pass ids, not raw
   pointers.
3. **Marshalling**: args by `abi.params[i].lua` tag (`integer`, `bool_int`,
   `float` via stack slot, `object_id`, `cexostring_ptr` via a scoped
   temporary `CExoString`); reject `out_ptr`/`struct_view`/`struct_return`
   until specced. Call through a single assembly thunk that loads ECX, pushes
   args right-to-left, calls, and verifies ESP after return equals the
   pre-push value (mismatch → poison the site, raise).
4. **Context limits**: game main thread only, not from inside a pre hook of
   the same site, bounded call depth; side-effecting functions require an
   explicit allowlist entry (`callable.side_effects`).
5. **Acceptance**: offline tests against local thiscall functions with fake
   vtables (valid, wrong class, unreadable, null), then the curated ~50
   callable set from SPEC §6.3.
