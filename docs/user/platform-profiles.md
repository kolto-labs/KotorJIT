# Platform profiles

ScriptForge treats each shipped binary as a **profile**: a logical id bound by
content identity (code-section hash / portable signatures), never by store shelf
name or file path alone. That is the same separation AgentDecompile uses for
**portable signatures** and **hook packs** — logical site names stay stable;
per-build addresses are a cache. This is unrelated to the Unity game engine.

## Registry

| Artifact | Role |
|---|---|
| [`data/profiles/builds.toml`](../../data/profiles/builds.toml) | Machine-readable profile table |
| [`data/profiles/README.md`](../../data/profiles/README.md) | Field definitions |
| [`data/addresses/*.json`](../../data/addresses/) | Per-build address caches for installable PE/ELF profiles |
| `python3 tools/list_profiles.py` | Dump id / game / platform / format / status |

## Status values

- **supported** — required hook sites resolve; `install_to_game.sh` works today (Windows GOG/Steam K1, GOG Aspyr K2, …).
- **registered** — binary is identified but not fully installable yet.
- **static_only** — signature / corpus tables only. The 32-bit Mac K1/K2 corpus images stay here; the x86_64 Steam macOS builds are now **supported** (`src/image` has a Mach-O loader and the runtime builds as a dylib — see [`macos-install.md`](macos-install.md)).

## Packaging

`scripts/package_release.sh` ships the currently supported PE/ELF runtime plus
address tables. Mac profiles travel in the registry so the same logical sites
can be bound once a Mac loader exists — no Unity, no game assets in the zip.
