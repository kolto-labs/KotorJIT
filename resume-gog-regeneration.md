# K1 GOG address regeneration review

Date: 2026-09-28
Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

## Verdict

**BLOCKED / not applied.** I ran only the authorized K1 GOG generator command,
then restored the pre-run generated table because its diff exceeded the
required seven accepted motion rows plus derived counts. No `--all` run,
shared build, runtime edit, test edit, or other address table edit was made.
The two proposed rows remained absent in both the pre-run table and generated
candidate.

## Exact pre-copy and command

Before running the generator, I copied the generated table and all relevant
inputs to `/home/brunner56/kp-live-20260922/gog-regen-pre-20260928/`.
Pre-copy hashes:

```text
65e7c2dd5c4c83cf02296a69f3c5d082b9e75d1c2bee5a1eeb497474c3f7fd66  data/addresses/k1_gog_103.json
c5572dc18a6ce40675f858771a4f2c2ae1ea29c329709507caf0f4ff0fb0b433  data/adjudication/k1_gog_103_motion_bindings.json
ec714287537b387670a0bbcf7d9fde85a79713a12932dbac960d084cefbe81be  data/adjudication/k1_gog_103_camera_bindings.json
ea4da891bda130d83cfe4a209f5881e63d0fabfe2686c419f46be063419eefa1  tools/gen_address_tables.py
ef6c77a452a74fdd867cbf48cdd87caa2e3e99a6bcb5c86c633fe67e57737f20  data/hooksites.toml
```

Command:

```text
python3 tools/gen_address_tables.py --build k1_gog_103
```

Generator output:

```text
k1_gog_103             283/283 resolved (func 59, identity 0, adjudicated 224)  ok
  sentinel         : 0x0052C0D0 8b54240481fa04030000
  fields           : 152 bound
generator_rc=0
```

Receipt: `/home/brunner56/kp-live-20260922/gog-regen-pre-20260928/generator.log`,
SHA-256 `2a224dd56a305d0d762cdcb59ff5e88f2746d1f6f08371a6685c1103e33e6cd0`.

## Candidate diff and blocker

The candidate added exactly the seven accepted motion site names:

```text
server_object.area_id
server_object.position
server_object.orientation
server_object.client_push_gate_unverified
server_object.dirty_bits
placeable.aabb_registered
placeable.quaternion_raw_order_unverified
```

It did not add either proposed row:

```text
server.get_placeable_by_object_id
placeable.vtable
```

Camera site values were unchanged. However, the candidate also changed the
existing `server_object.set_position` row metadata from the pre-copy function
record to the adjudicated record (`source=func, confidence=1.0,
method_detail=user_defined` became `source=adjudicated, confidence=0.95,
method_detail=hand-adjudicated; func row agrees`) and changed the generated
`reference_image` path. Derived counts changed from `adjudicated_bindings=219,
summary.total/resolved=276` to `adjudicated_bindings=229,
summary.total/resolved=283`, with `by_func` changing 60→59 and `by_field`
145→152. The seven new rows account for the site additions, but the existing
row metadata/reference-path changes violate the requested “only seven accepted
rows plus derived binding counts” gate.

The generated candidate was therefore not retained. The worktree table was
restored from the exact pre-copy; its final hash is again:

```text
65e7c2dd5c4c83cf02296a69f3c5d082b9e75d1c2bee5a1eeb497474c3f7fd66  data/addresses/k1_gog_103.json
```

The likely source of the extra change is current generator/adjudication input
state: the current motion overlay describes `server_object.set_position` as
an existing hooksites row, while the generator now prefers that adjudicated
record. The camera review’s older scratch regeneration reported the expected
seven-row result; its retained candidate is
`/home/brunner56/kp-live-20260922/review-probes-camera/regen/data/addresses/k1_gog_103.json`
and has hash `f53b7f33f45f61cc5df27ffb4036d5557b3640da3f034991288dd2960d7b9e46`.
That candidate preserves the function-form `server_object.set_position` row,
so it documents the exact input drift to settle before applying a generated
artifact.

## Static validation

The candidate passed `python3 tools/address_table_layout_test.py` with 26
 tests, exit `0`, but that is not sufficient to override the diff gate. No
candidate address table was left in the worktree. A future owner should settle
whether the accepted generator output includes the adjudicated
`server_object.set_position` metadata/reference path or whether the input
overlay must be reconciled to preserve the existing function record, then rerun
this same K1-only command and recheck the exact seven-row diff.

## Read-only reconciliation (2026-09-28)

The input drift is attributable to a newer motion adjudication overlay, not an
unreviewed address disagreement. The current worktree overlay
`data/adjudication/k1_gog_103_motion_bindings.json` has mtime 2026-09-27
18:13:07 and SHA-256 `c5572dc18a6ce40675f858771a4f2c2ae1ea29c329709507caf0f4ff0fb0b433`.
The retained camera scratch overlay has mtime 13:46:34 and SHA-256
`1fd54a32c009f9d3e57048425d18b2277e05679012b2b1d5fc7698a77ff240ce`.
The newer overlay adds an accepted `CSWSObject::SetPosition` function binding,
expands the M2 purpose/field-shape text, and adds six SetPosition guard spans.
It is the reason the current generator resolves the pre-existing
`server_object.set_position` manifest row as `source=adjudicated`,
`method_detail=hand-adjudicated; func row agrees`; the older scratch generator
left that existing row as `source=func`. The address and expected bytes are
identical (`0x004CD1A0`,
`538b5c240856578bf18dbe9000000053`). The newer overlay's accepted SetPosition
binding is supported by the M0 and independent-verification receipts named in
the overlay; there is no evidence that it is an accidental dirty address.

The `reference_image` difference is environmental path selection in
`tools/gen_address_tables.py`, whose K1 GOG `_ref()` candidates are tried in
order. At regeneration time the older candidate selected
`/home/brunner56/agentdecompile-nvme/agentdecompile_projects/extract/raw/K1__k1_win_gog_swkotor.exe`;
the current run selected
`/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image`.
Both existing files are 4,042,752 bytes and have the same accepted raw-image
SHA-256 `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`.
Thus this path change is not a binary-content change, but it is still outside
the requested seven-row table diff.

The minimally faithful integration is therefore a field-level merge, after
root review: start from the restored current table; copy only the seven
accepted motion field site objects from the saved candidate; retain the
current `server_object.set_position` object, all current camera rows, the
current reference path/digest, sentinel, known-text, and all unrelated rows;
leave `server.get_placeable_by_object_id` and `placeable.vtable` absent. The
resulting derived summary should be recomputed for the merged table as
`total=283`, `resolved=283`, `by_func=60`, `by_identity=0`,
`by_adjudication=223` (the seven new fields plus the current 216 overlay
bindings), and `by_field=152`, with all list-valued summary fields unchanged.
This preserves the current function-form SetPosition row while adding only the
seven accepted fields. It is a proposed merge, not an applied artifact; no
product file was changed during this reconciliation.

## Root-approved faithful regeneration (2026-09-28)

Root ruled that the newer accepted SetPosition overlay is the source authority,
so the faithful current generator output is retained. Before regeneration, the
current table was copied to
`/home/brunner56/kp-live-20260922/gog-regen-current-20260928/k1_gog_103.pre.json`.
The current reference image was explicitly pinned with `KP_K1_GOG_EXE` to:

`/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image`

It exists, is 4,042,752 bytes, and hashes to
`9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`.
The only generator command was:

```text
KP_K1_GOG_EXE=/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image python3 tools/gen_address_tables.py --build k1_gog_103
```

The command returned rc 0 and reported `283/283 resolved (func 59, identity 0,
adjudicated 224)`, sentinel `0x0052C0D0`, and 152 bound fields. The retained
semantic receipt is
`/home/brunner56/kp-live-20260922/gog-regen-current-20260928/semantic-diff.txt`.
It proves:

- exactly seven new site names were added;
- no site was removed;
- the only existing site changed is `server_object.set_position`, whose
  address and expected bytes are unchanged while source/confidence/method
  metadata change from `func/1.0/user_defined` to
  `adjudicated/0.95/hand-adjudicated; func row agrees`;
- reference path, reference digest, derived digest, sentinel, and known-text
  entries are identical before and after the pinned run;
- the proposed `server.get_placeable_by_object_id` and `placeable.vtable` rows
  remain absent.

The generated table is intentionally left applied at
`data/addresses/k1_gog_103.json`. Its post-generation SHA-256 is recorded in
`/home/brunner56/kp-live-20260922/gog-regen-current-20260928/generated-hash.txt`.
The focused `tools/address_table_layout_test.py` ran 26 tests and passed; its
receipt is `layout-test.log` in the same directory. No other generated table,
source file, runtime file, CMake file, or test file was edited by this slice.
