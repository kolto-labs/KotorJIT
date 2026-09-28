# Package readiness audit — 2026-09-22

Fastest defensible deliverable: a **K1 GOG Windows runtime preview, live-tested under Wine**, using the frozen input-round2 DLL pair. This is not K2 or Mac acceptance. No builds, installs, game runs, product edits or Git index changes were performed for this audit.

## Exact accepted artifact and allowlist

- `/home/brunner56/kp-live-20260922/frozen-console-inputround2/kphasor.dll`: SHA256 `713aa3ac0b967a61089cf5f3a947fe102c8dd74aceccde6940d067630a0cca61`.
- Matching `binkw32.dll` in that directory (99,978 bytes).
- Address data from input-fix commit `3c570b1`; use only `data/addresses/k1_gog_103.json` for a deliberately K1 GOG-only package.
- `docs/devtools-console.md`, `docs/devtools-protocol.md`, LICENSE, ImGui license/pin, LuaJIT COPYRIGHT, accurate preview install/readme, checksum manifest.
- A source archive at that commit, plus the exact LuaJIT source/dependency identity used for the binary. The moving LuaJIT branch is not reproducible provenance; settle the actual dependency commit before external distribution.
- Private live-acceptance.json proves runs 133724 (26/26 rapid recall), 133825 (39/39 full console), 133930 (28/28 held key/draft/restoration), all source unchanged. Its absolute private paths should be summarized, not published verbatim.
- `provenance.json` is older and still says "review candidate; no live acceptance"; supersede its status in package manifest using live-acceptance.json, without rewriting the original receipt.

Do not package current mutable build/kphasor.dll as this accepted artifact. It contains subsequent projectile work. Do not bundle private projectile fixtures, unaccepted examples, unfinished Pioneer/harness scripts, browser/WASM claims, or claim knockback/tumbling. Source archive can preserve historical source transparently without advertising every feature as accepted. Recent native string-bridge correction must pass its own gate before replacing this frozen binary; accepted713aa still has the known bridge string-capacity defect for some NWScript return strings.

## Runnable local staging command (no game mutation)

Run this from the isolated worktree. It creates a new directory and deliberately fails if it already exists. This creates a local preview candidate; the dependency-source receipt and concise package README remain required before publication.

```bash
python3 - <<'PY'
from pathlib import Path
import subprocess, shutil, hashlib, json
root = Path.cwd()
out = Path('/home/brunner56/kp-live-20260922/packages/kotorphasor-k1-gog-console-preview-3c570b1')
out.mkdir(parents=True, exist_ok=False)
frozen = Path('/home/brunner56/kp-live-20260922/frozen-console-inputround2')
for name in ('kphasor.dll', 'binkw32.dll'):
    shutil.copy2(frozen / name, out / name)
assert hashlib.sha256((out/'kphasor.dll').read_bytes()).hexdigest() == '713aa3ac0b967a61089cf5f3a947fe102c8dd74aceccde6940d067630a0cca61'
for path in ('LICENSE', 'docs/devtools-console.md', 'docs/devtools-protocol.md', 'data/addresses/k1_gog_103.json', 'third_party/imgui/LICENSE.txt', 'third_party/imgui/PIN.md'):
    dest = out / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(subprocess.check_output(['git','show',f'3c570b1:{path}'], cwd=root))
shutil.copy2(root/'third_party/luajit/COPYRIGHT', out/'LuaJIT-COPYRIGHT')
subprocess.run(['git','archive','--format=tar.gz',f'--output={out}/source-3c570b1.tar.gz','3c570b1'], cwd=root, check=True)
manifest = {'scope':'K1 GOG Windows preview; live-tested under Wine', 'source_commit':subprocess.check_output(['git','rev-parse','3c570b1'],cwd=root,text=True).strip(), 'files':{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}}
(out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(out)
PY
```

Manual installation must preserve original binkw32.dll as binkw32_real.dll, install both DLLs beside swkotor.exe, and put the address table under kotorphasor/addresses/. Refuse an ambiguous preexisting backup or foreign proxy; preserve user scripts/config. Current shell installer is not safe enough to silently use against arbitrary existing installations.

## Actual support matrix and blockers

| Target | Current code/build claim | Release evidence and blocker |
|---|---|---|
| K1 GOG Windows | MinGW i386 DLL + bink proxy; profile/address table | Frozen F12 artifact live under Wine. Fastest preview. Native Windows fresh install/runtime acceptance not established by Wine proof. |
| K2 GOG Windows | README/CONTRIBUTING claim runtime support; k2_gog_aspyr table | No current F12/input/native feature acceptance for this artifact. Require exact K2 executable installation and capability smoke. Do not infer from successful cross-build. |
| K1 Mac | Some native feature/profile references | No Darwin runtime packaging or accepted artifact. Linux platform fallback uses /proc and ELF; hook code assumes i386. Need Darwin loader/image/memory/backend and architecture decisions, then render/input and installation verification. |
| K2 Mac | Same partial profile-level references | Same fundamental blockers; profile existence does not deliver a Mac loader or console. Separate exact executable/build/ABI validation required. |

## Prioritized file-level follow-up

1. **Package now with honest scope:** add a deterministic allowlist staging script/manifest and concise preview install guide; consume frozen pair, not the mutable build directory. Ship corresponding source and dependency notices/provenance. Existing CMake has no install/CPack/archive target and CI uploads no artifacts.
2. **Fresh CI configure blocker:** `.github/workflows/cmake-multi-platform.yml` installs multilib and MinGW but not the `luajit` executable now REQUIRED by `CMakeLists.txt`. Install it; pin LuaJIT to immutable commit instead of shallow moving v2.1. CI only runs Ubuntu GCC/Clang despite multi-platform name, with no Windows/Mac install tests.
3. **Installer safety/native usability:** `scripts/install_to_game.sh` is GNU/Linux Bash (stat -c/install -D/date -Iseconds), accepts an existing binkw32_real.dll without validation, performs nontransactional copies, and uninstall overwrites the current proxy without ownership validation. Add executable/build preflight, original/installed hashes, rollback, and refusing conflicting backups. Provide native Windows instructions or installer entrypoint. No Mac entrypoint exists.
4. **Make missing products visible:** `src/runtime/runtime.cmake` and `src/proxy/proxy.cmake` warn and skip Windows artifacts when MinGW/LuaJIT absent; release builds should fail if requested artifact cannot be built. Inspect resulting pair and manifest, not just aggregate build success.
5. **Correct support/API docs:** README and CONTRIBUTING broadly claim K1/K2 runtime support; CONTRIBUTING still documents kotor.* aliases removed by API2. `docs/user/install.md` assumes downloadable releases, omits current luajit/Python prerequisites, and describes old cheat-console flow. Publish per-feature/per-platform evidence and F12 workflow.
6. **Mac prerequisites before promises:** `src/hooks/hooks.cmake` chooses platform_linux.cpp for all non-Windows builds; `src/platform/platform_linux.cpp` and runtime self-module discovery depend on /proc; runtime non-Windows entry is an ELF preload constructor. `src/runtime/runtime.cmake` builds LuaJIT TARGET_SYS=Linux under generic UNIX, and trampoline implementation is 32-bit. Parent separately audits executable profiles/signature abstractions. No quick archive wrapper fixes these boundaries.

Native32/Win builds and focused actual ImGui/Lua tests have passed for the frozen input candidate, and live receipts above establish its console behavior. Existing CTest logs are mutable and must not be relabeled as testing a newly assembled package. An installed-package smoke remains the release gate. No claim that all original examples or all current APIs are validated is justified.
