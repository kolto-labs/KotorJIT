---
artifact_contract: "ce-handoff/v1"
created_at: "2026-09-28T06:40:00Z"
title: "KotorPhasor lua-boundary-validation: cloud handoff after side audit, DLL rebuild and blocked display diagnostic"
summary: "All code is merged to main (PR #1); evidence extract is staged locally but not pushed; live display/game acceptance remains open and needs a Linux desktop host."
keywords: ["kotorphasor", "lua-boundary-validation", "cloud-handoff", "capture-diagnostic", "kphasor.dll", "evidence-branch", "live-acceptance"]
cwd: "repository root"
resume_focus: "Continue from repository state only; pick the next follow-up with the user before reopening implementation or live validation."
repository: "bodencrouch/KotorPhasor (private)"
repo_root_sha: "64c05e58fdfeba5cb730d524546b081de352245e"
branch: "codex/lua-boundary-validation"
worktree_path: "n/a (cloud)"
---

# Why this exists

The user asked (2026-09-28) to hand off to a cloud agent so that no local files
are required. Everything load-bearing is now in git:

- **Code + ledger:** branch `codex/lua-boundary-validation` (commit `7c9e700`),
  merged into `main` by PR #1 (`2401a07`). The main checkout's separate work
  (`codex/fix-softlock-recovery-oracle`, `e11c499`) is being merged via its own PR. The ledger is
  `.superpowers/sdd/lua-boundary-validation-plan/progress.md` (force-added past
  `.superpowers/sdd/.gitignore`). Final ledger sections record runtime
  integration, GOG/H0 closure and side-audit completion.
- **Evidence: NOT in git yet.** A redacted text-only extract (11,669 files,
  185 MB, 73 files redacted, zero token-shaped strings left) is staged as a
  local repo at `/run/media/brunner56/MyBook/Workspaces/KotorPhasor-evidence-branch`
  (machine-local), meant for orphan branch `evidence/kp-live-20260922`. The
  push was blocked by the agent safety check because the source logs held raw
  env dumps; it needs the user's explicit go-ahead. Until then, evidence
  paths cited as `/home/brunner56/kp-live-20260922/<path>` exist only on the
  user's machine (`~/kp-live-20260922` is now a symlink to
  `/run/media/brunner56/MyBook/nvme-offload/kp-live-20260922/`). A cloud
  agent should treat evidence-dependent claims as unverifiable and rely on
  the ledger plus the code.

# State (verified this session unless marked)

Complete, host-only (not live):
- Client/server side audit: evidence `side-audit/README.md` (index and
  interpretation boundary; read first). 201 Lua names, 111 events (14 dead),
  55 Lua files, 46 harness TCP commands, 806 native routine names with handler
  side unresolved.
- Runtime integration of vec/motion/scripts, ELF autostart opt-out
  (`KOTORPHASOR_NO_AUTOSTART=1`, Linux tests only), GOG table regen
  (`data/addresses/k1_gog_103.json`, sha256 `5749fbf0b3f90b71296319fd5bebf94aca7f2bfd5f27d110934eaaa1089ecbf3`,
  verified), H0 drain regression (`tools/kp_harnessdrain_test.cpp`), capture
  R15 PTS fix. Evidence per ledger; not rerun at handoff time.
- Fresh 32-bit Windows DLL from the exact tree committed in `7c9e700`:
  evidence `dll-build-20260928/` (report.md, manifest.json, build.sh; DLL
  sha256 `ed0a0dcf166ac060696caf3a1a51530ca0bc5865f434565038e61bc64851662c`).
  Built with Fedora host `i686-w64-mingw32-g++` 16.1.1 via
  `cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DKP_MINGW_CXX=<mingw g++>`
  then `cmake --build build --target kphasor_dll -j2` (target-scoped on purpose:
  building `all` runs `kp_structs_generated`, which writes into `src/generated/`,
  see `src/api/structs.cmake:33-40`). Integration literals `kp.motion.capture`
  / `kp.vec.meta` are present (absent in the 9/22 DLL). Not deployed anywhere.

Open (nothing here is accepted):
- **Live capture display diagnostic** (one authorized attempt, not yet run).
  Invocation: evidence `resume-diagnostic-prepared-invocation.md`. Driver:
  `scripts/harness/kpharness/capture_diagnostic.py` (docstring lines 1-25
  describe the run). Paths in the invocation are **Fedora host** paths
  (`/usr/bin/python3.14`, `/usr/bin/ffmpeg`, linuxbrew ffprobe); they exist on
  the host, not inside the `ubuntu-dev` distrobox. The user authorized one run
  on 2026-09-28. It was blocked before launch: the driver's preflight
  (`forbidden_processes`, `capture_diagnostic.py:361`) refuses while any
  `wineserver` exists, and the user's PotPlayer AutoHotkey helper kept one
  alive. A dry preflight showed that as the only blocker. The authorization was
  for that machine and session; a new agent must re-confirm with the user.
- **K1 acceptance** depends on the display/capture gate and on deploying the
  new DLL; L1-before-V1 receipt gating is in the ledger.
- Browser/external-client live proof; release-builder patch (proposed,
  unapplied); production pause R6 wiring (excluded from integration, see
  ledger "Resume pause R6 confirmed" section); native-handler side
  classification (needs real handler evidence).
- Evidence `acceptance-reconciliation-20260928.md` lists these obligations with
  dependency order; its "Root correction" section at the end overrides its
  claim that the diagnostic binaries are missing.

# Constraints a cloud agent inherits

- A cloud container cannot run the live diagnostic or K1 acceptance: they need
  the user's Linux desktop (Gamescope, Xwayland, Wine, the game install,
  protected displays :0/:94/:100 and the canonical lock at
  `tmp/harness-locks/live-game.lock`). Cloud work is limited to code, host
  tests, builds (MinGW is needed for the DLL) and document work.
- Never signal foreign processes; never clean-first a shared build; no PR,
  publish or merge without explicit approval in the current conversation.
- Subagents: Sonnet, with the prove-the-effort protocol block and the grill
  handshake (both in the user's `~/.claude/skills/prove-the-effort/PROTOCOL.md`
  and `~/kp-live-20260922/codex-runs/`, machine-local).

# Warnings

- A GitHub token appeared in raw env dumps inside local evidence logs; the
  user was told to rotate it.
- The machine-local evidence root moved during this session (another session's
  `rsync --remove-source-files`, finished and checksum-verified by this one).
