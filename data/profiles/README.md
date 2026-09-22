# Platform profiles (AgentDecompile-aligned)

KotorPhasor selects a game binary by **content identity** (code-section hash /
portable signatures), not by path or store shelf name. That matches AgentDecompile's
**portable signature** and **hook pack** ideas: logical site names are stable;
per-build addresses are a cache.

This directory is the human- and machine-readable registry of those build
profiles. It is **not** related to the Unity game engine.

| Field | Meaning |
|---|---|
| `id` | Stable profile id (`k1_gog_103`, `k1_mac`, …) |
| `game` | `K1` or `K2` |
| `platform` | `win` / `mac` / `linux` / … |
| `format` | `pe` / `elf` / `macho` / … |
| `status` | `supported` (hooks install today), `registered` (identified but not installable), `static_only` (signature tables only; no loader) |
| `address_table` | Path under `data/addresses/`, or empty when not shipped |
| `note` | Operator-facing caveat |

Mac profiles are `static_only` until the runtime image parser gains Mach-O
(`src/image` is PE/ELF today). Windows GOG/Steam PE profiles that resolve every
required hook site are `supported`.

List profiles:

```sh
python3 tools/list_profiles.py
```
