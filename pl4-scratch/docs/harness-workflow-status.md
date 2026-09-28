# GitHub and Steam harness execution

The portable driver is the execution contract. Platform provisioning obtains the selected game and runtime, supplies private staging/checkpoint/output paths, invokes the same driver, and retains its behavior and media receipts. Workflow YAML, Steam acquisition and TOML driver configuration do not belong in the Lua or NWScript engines.

The user requested GitHub workflows with SteamCMD authentication as the eventual normal execution path. Inspection and an actual retry on 2026-09-22 found:

- GitHub CLI authentication can access the private repository.
- No repository secrets, variables, environments or self-hosted runners are configured.
- Existing workflow run35491392460 attempt2 was rejected before executing any step, with the account billing/spending-limit annotation. This is a runner prerequisite failure, not a code-test failure.
- Local SteamCMD is installed. Public app metadata was successfully fetched without game credentials. The existing gameplay harness normally reuses an authenticated Steam desktop client; portable SteamCMD authentication has not yet been established.
- No Steam credential environment variables were present in this task. Credential values were not printed or placed in reports.

## Current Mac acquisition facts

SteamCMD public app metadata for K1 (`32370`) reports `osextended=macos64`, public build4143502, code depot32376 manifest4316506090271122130 (23,397,122 bytes), and separate content depot32377 manifest1245077958602529903 (3,392,632,945 bytes). This is current metadata, not an acquired executable identity. The older K1 i386 corpus profile must not be reused for this build.

The official SteamCMD macOS installer archive was inspected without execution. Its `steamcmd` is a thin x86-64 Mach-O executable (CPU type0x01000007). Thus native SteamCMD provisioning on a modern Intel Mac is a viable candidate; it need not be replaced by a Windows/Wine launcher. Exact game acquisition and authentication still need verification.

The known K2 corpus includes a separate x86-64 `KOTOR2sub` game slice. Launcher and game slices have distinct identities. Modern hosted Mac runners cannot execute the old i386 corpus binaries. Use the actual acquired game's architecture and hash to select a profile; an application name or Steam platform label alone is insufficient.

## Workflow boundaries

A live workflow should be explicitly dispatched with game, scenario, build identity and capture settings. Keep one live session per runner through both workflow concurrency and the driver's process lock. Keep credentials in the runner's authentication mechanism or narrowly scoped GitHub secrets, never in command-line arguments, logged command files, ordinary TOML, source control or output artifacts. Interactive Steam Guard challenges must be reported as an acquisition prerequisite rather than bypassed or mistaken for a game failure.

Use a modern Intel Mac hosted runner when its graphics, storage, acquisition and runtime requirements are verified; a dedicated Mac runner can reuse an existing authenticated installation. Neither choice is currently established by a passing gameplay run. Preserve the existing Ubuntu host tests while adding Mac build/static checks. Upload selected reports, executable/runtime hashes and recorded media, with an explicit artifact allowlist rather than archiving a whole Steam directory or home folder.

The remaining native Mac prerequisites are a verified current game image, Darwin runtime startup/image-slide handling, the relevant architecture's hook/VM adapters, and native GUI control/capture. The native model module can reuse its verified Mac calling adapters once that runtime supplies its binding contract. Profile tests and Wine recordings do not establish those prerequisites.

Sources: [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), [Apple 32-bit compatibility](https://support.apple.com/en-ie/103076), [Valve SteamCMD documentation](https://developer.valvesoftware.com/wiki/SteamCMD), [Steam K1 listing](https://store.steampowered.com/app/32370/STAR_WARS_Knights_of_the_Old_Republic/). Local machine-readable acquisition metadata and the rejected-run receipt are retained in the controller's run directory; no credential or game payload is included here.
