# Where reverse-engineering work lives

KotorPhasor does **not** store the Odyssey corpus. The months of cross-build
identity and byte-exact reconstruction live outside this repo.

**Start here (NVMe AIO index):**

[`/home/brunner56/agentdecompile-nvme/AIO/AUTHORITY.md`](/home/brunner56/agentdecompile-nvme/AIO/AUTHORITY.md)

| Need | Go to |
|---|---|
| Single index of every store | `…/AIO/AUTHORITY.md` + `MANIFEST.json` |
| Warehouse + kotorxid pipeline | `/home/brunner56/biodecompwarehouse/` |
| Identity DB | `…/kotorxid/db/kotorxid.sqlite` |
| Live expanded corpus DB | `…/agentdecompile-nvme/corpus-work/corpus.sqlite` |
| Openable byte-exact CMake project | `…/kotorxid/output/kotor_reconstructed/` (with `src/` → asm) |
| K1 GOG readable-C package | `…/AIO/packages/k1gog_byteaccurate_build/` |
| AgentDecompile product | `/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile` |

`data/corpus.sqlite` in this repo is intentionally unused / empty — do not
treat it as the corpus. Runtime binding for live games uses
`data/addresses/` and `data/profiles/` only.
