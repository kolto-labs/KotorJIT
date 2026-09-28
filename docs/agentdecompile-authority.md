# Where reverse-engineering work lives

**Start:** [`~/agentdecompile-nvme/AIO/README.md`](/home/brunner56/agentdecompile-nvme/AIO/README.md)

## Canonical rule

**One program → one package folder** under `AIO/programs/<SLUG>/`, which is a
symlink into the kotorxid binary collection:

`/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/<SLUG>/`

That store holds **49** programs (**22** complete Odyssey assembler+verified_c
packages — the set that used to feel like “~12 KotOR builds” plus siblings).

| Need | Path |
|---|---|
| Browse by game | `AIO/programs/_by_game/K1` or `K2` |
| Full program table | `AIO/catalogs/PROGRAMS.md` |
| Openable CMake project | `AIO/reconstructed/` |
| Identity DB | `AIO/databases/kotorxid.sqlite` |
| Live corpus DB | `AIO/databases/corpus_live.sqlite` |
| Experiments / zips | `AIO/sessions/` (not packages) |
| Organization rules | `AIO/CANON.md` |

`data/corpus.sqlite` in this repo is empty — not the corpus. Runtime binding
uses `data/addresses/` and `data/profiles/` only.
