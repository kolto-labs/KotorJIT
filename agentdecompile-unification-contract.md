# AgentDecompile current unification export contract

Read-only source assessment, 2026-09-22. No tests, exports, builds, corpus jobs, or runtime operations performed. Scope shortened for immediate packaging decisions.

Authority inspected: `/home/brunner56/Workspaces/ai-projects/AgentDecompile` resolves to `/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile`. Repository AGENTS.md applies. No Unity engine dependency is proposed.

## Implemented producer

`src/agentdecompile_recovery/corpus/export_hookpack.py`, `export_hookpack()`, emits `agentdecompile.hookpack/v1` from `logical_function`, `identity`, `func`, and `binary`. Current code is newer than the September20 implementation table in `docs/RUNTIME_REUSE.md`.

- Top-level `format`, deterministic `basis`, `binaries`, `sites`; optional `policy_hashes` and unmatched-policy diagnostics.
- Binary rows: `slug`, `game`, `platform`, `format`, `arch`, `bits`; `image_base` when known; `sha256` plus stored/computed origin when available. Referenced identities require stored content hashes for deterministic ordering.
- Site rows: `logical_id`, class/method, signature agreement, `kind`, `required`, `instances`, `instance_windows`; optional shared expected bytes, byte agreement, adapter key, aliases and field offset/size.
- Instance rows: build slug, recorded VA (`addr`), name, identity confidence/method, source-file provenance; expected bytes when a raw-image unique 8–24-byte window exists. Otherwise explicit `not_unique` or `no_image` window status.
- Address-to-file translation calls `exact_universal.mapper_for(image, load_base)`. This supersedes the older documentation claim that this exporter only uses a PE mapper; this bounded audit did not establish every mapper's actual platform coverage.
- Signature agreement counts and raw-file unique windows do not establish ABI compatibility, semantic identity, live executable-region uniqueness, or behavior.

`src/agentdecompile_recovery/corpus/hookpack_policy.py` implements external host policy. Site policy shape is `{default:{kind,required},sites:{siteKey:{kind,required,field:{offset,size}}}}`; kinds are call/detour/field/reference. Adapter map is `{keys:{siteKey:adapterKey},aliases:{siteKey:[alias]}}`. Unknown keys, malformed fields, and duplicate adapter keys refuse. Policy files are hashed into the export. Field extent is site-wide metadata supplied by policy, not automatically recovered per-build structure layout.

Existing test source/fixtures: `tests/test_corpus_export_hookpack.py`, `tests/fixtures/hookpack/site_policy.json`, `tests/fixtures/hookpack/adapter_map.json`. Test execution and test coverage were not verified in this urgent bounded pass.

## Not established by this current export

The exporter inspected still enumerates logical functions, not a unified all-entity export. It does not emit structured argument register/stack/return ABI, per-build object layouts, object lifetime/root recipes, independent readable/callable/writable/detourable capabilities, or live behavior receipts. A source prototype string is not a typed calling contract. All-build discovery ladders, generated Lua field bindings and autonomous callable coverage in the September21 portable-signatures plan must not be advertised as delivered by this schema. Other implementation modules were not exhaustively audited.

The portable-signatures plan explicitly records mixed landed and pending units. `docs/RUNTIME_REUSE.md` labels its expanded readiness/capability contract as required work and distinguishes resolution from typed calls, installation and observed behavior. Its older implementation table must be reconciled with current exporter code rather than copied unchanged.

## Smallest KotorPhasor integration

Reuse AgentDecompile v1 export unchanged as the producer contract. Supply a small KotorPhasor-owned adapter-key map and site policy, linking logical sites to existing native adapter keys. Teach only the existing KotorPhasor pack consumer any currently missing fields; parent is auditing that consumer independently. Do not create another recovery/matching engine or dynamically synthesize C calls from prototype strings.

At use time bind exact executable hash and architecture, recorded base/VA rebasing, expected live bytes and independently established target identity. Retain explicit compiled per-build ABI/layout adapters for WinK1GOG and each proven Mac build. Missing fields/guards/ABI or unsupported runtime should refuse only the dependent capability. Do not infer present Mac support from architecture metadata or a matching signature.

Ship only a deliberately selected runtime metadata allowlist after publication review: this producer contains original instruction windows and source-path provenance, so copying whole corpus exports is not equivalent to a clean redistributable runtime bundle. No public export was created here.

Next minimal check: one existing native capability, one exact build, current v1 fixture -> existing registry -> typed adapter, with mismatch and missing-ABI refusals. Expand build rows only after separately proven adapter readiness. This preserves AgentDecompile as binary-unification authority and KotorPhasor as runtime consumer.
