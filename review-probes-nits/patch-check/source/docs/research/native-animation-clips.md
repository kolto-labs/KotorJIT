# Installed K1 named animation clip evidence

Read-only asset extraction on 2026-09-22. No game launch or live-state access. Root: `/home/brunner56/krayt/tmp/k1_harness`.

## Effective model chain

`data/templates.bif` resource `g_sithtroop01` (UTC type2027), file offset975267 size3334, SHA256 `f0db5405e9627d257f21f6c9558dbf09a9b6354dc8242bb3b6de5b2b9c40fcbe`: GFF Appearance_Type WORD =28. No same-named Override UTC found.

Installed `Override/appearance.2da`, SHA256 `08b929ee218a70d2ae40669e8c0525af9335adcfa3065964c020d879b41ce038`: row28 label Sith_Soldier_01, modeltype F, race/modela N_SithSoldier.

`data/models.bif` N_SithSoldier MDL resource offset916294576 size233515 SHA256 `e2e30b21dbc0903bde844b4c0d6d180560e9a4611a29b11139aada70db9fd4bd`: supermodel S_Female02; own clips only pause1 (8.33333sec),pause2(4sec). No Override N_SithSoldier.mdl found.

Effective installed chain (these Override files differ from corresponding BIF models):

| File under Override | SHA256 | Supermodel | Clip count |
|---|---|---|---|
| S_Female02.mdl | ef8249d8aab9a1f83a82cce2fde045a335960878bbd971ecacec366220a10b49 | S_Female01 |43|
| S_Female01.mdl | a97907e86f14a65a1d3f478d1ba6c53c46067eff1d890ebf914a1f444d37a8ef | S_Male02 |48|
| S_Male02.mdl | 3c67f81220b988db36d76209c0f3496883d146dff8caf72c4ff064a8ed674faa | S_Male01 |166|
| S_Male01.mdl | 9fa30ec0c4a4ebf6e1bd292ff21fbb7e87b97aa5612edf4e8c72f4d69a9e3266 | NULL |12|

## Candidate clips in effective S_Male02.mdl

These names are actual NUL-terminated animation-header names, not inferred NWScript constants. They are absent from nearer N_SithSoldier/S_Female02/S_Female01 clip arrays, so no nearer same-name override was found.

| Name | Duration seconds | Header transition seconds | Animation header offset relative to MDL payload |
|---|---:|---:|---:|
| dance |2.0666699409484863|1.0|1016323|
| bow |1.966670036315918|1.0|290167|
| salute |1.63332998752594|1.0|182911|
| taunt |1.399999976158142|1.0|673023|
| victory |1.3333300352096558|1.0|204419|
| dance1 |1.6666699647903442|1.0|1034315|

No literal cower, wave, or fear clip appeared in this chain. This does not rule out equivalent motion under unrelated names.

Recommended first comparison: dance vs bow, with salute as fallback. They are strong gesture candidates based on asset names, but full-body appearance and visually useful mid-clip poses require live observation. Use rate0.5 if supported by the native implementation to stretch those first two clips to about4.13/3.93 wall seconds. Asset transition1.0sec means very early freezes may capture blending rather than the intended distinct pose; native time query plus screenshot/video should establish useful freeze points. Do not claim seamless looping or guaranteed engine-controller noninterference from resource metadata alone.

## How extracted / exact byte interpretation

KEY index selected UTC2027 and MDL2002 resrefs; BIF resource records supplied offsets and sizes. GFF field tables identified Appearance_Type. Binary2DA tab columns/row labels and ushort string offsets supplied appearance row28. MDL has a12-byte file prefix; payload-relative offset88 contains animation array offset/count/count. Payload+136 is the32-byte supermodel name (terminate at first NUL, not last: padding contains junk). Animation pointer array is uint32. Each animation header has name+8 (32-byte field terminated at first NUL), float duration+80, float transition+84. Thus absolute MDL file header offsets are table values+12; duration is table value+92. All arrays were bounds-readable and plausible across five chain assets. BIF originals independently have the same candidate names and durations, but different offsets/hashes.

## Required live acceptance

Fresh resolve owned creature and model each time. Query each literal clip with native GetAnimation: positive finite duration matching expected approximate asset duration and valid inactive/active semantics. Play once, verify time advances across several frames, pause same run and verify time stable, resume and verify advance; also record the distinct visible pose. Stop on normal animation-driver overwrite; repeated restarts are not evidence of control. Module/local resource precedence or loaded model substitutions still require the live native query. Use owned NPC destruction for definitive cleanup unless narrower reset has separately been proved. No negative rates, invented cower aliases, or whole-world timescale are justified by this extraction.
