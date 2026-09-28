# Win K1 GOG camera audit

Read-only original binary audit, 2026-09-22. Authoritative image `/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image`; SHA256 `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`; PE32 preferred base0x400000. All addresses below preferred VAs, relocate by modulebase−0x400000. No Mac claim. Disassembly: `/tmp/kp-camera-win-k1-disassembly.txt`; bounded extraction helper `/tmp/kp_camera_dis.py`.

## Exact findings

GetFacing0x537fe0 reads serverobject direction vector+0x9c, normalizes, uses fpatan0x538097, multiplies by57.295780181884766 at0x538099; conditionally adds360. Degree output proved. Constant0x742ef8 hex e12e6542 =57.295780181884766; 0x741868 hex0000b443=360.

SetCameraFacing0x542530 pops float then MULTIPLIES by same57.29578 at0x542560. It checks commandscontext+4==1, resolves context+8 caller object, requires creature conversionvirtual+0x30 and creature+0xe8nonnull. It queues action0x16 using AddAction0x4cea20. This is caller-sensitive and asynchronous, not direct camera write. Explicit PC caller is necessary for a reliable attempted action. Mere routine success can be a no-op.

AddActionParameter0x4cac30 type2 branch0x4cacd6 copies pointed DWORD to actionparameter array+0x38 without conversion. AIActionOrientCamera0x5137c0 pulls action fields+0x38/+0x3c etc and sends0x56c610 to controlling player. WriteFLOAT0x4d6920 and ReadFLOAT0x4d67b0 copy raw float without conversion.

Client HandleServerToPlayerCamera0x64b8e0, heading branch0x64b9c9..fc, SUBTRACTS pi/2 (0x741bb8 db0fc93f=1.5707963705062866), then MULTIPLIES57.29578 AGAIN. Formats literal `yaw %f` (0x74fc28) and invokes camera virtual+0x60.

Thus, through the proven queue/message arithmetic, raw NW argument x becomes command numeric yaw=(x*57.29578−pi/2)*57.29578. Do NOT promote one radians conversion as the proved correct full-path fix. To emit conventional yaw desiredHeadingDegrees−90, algebra suggests x=desiredHeadingDegrees/(57.29578²). This is an unvalidated calibration candidate, not a supported general API contract.

The command may be ignored: camera constructor0x45d846 assigns vtable0x741b20; slot+0x60 stored0x45c160. Camera::BehaviorMessage adjusts this+4 and jumps Gob::BehaviorMessage0x43f5a0; that fetches activebehavior+0x188 and calls behaviorvirtual+0xc. CAurBehaviorCameraFollow::Message0x49ee00 checks literal yaw at0x49eea8..cf and parses into behavior+0x3c; parser0x4635c0 uses sscanf `%f`, no numeric conversion. However CSWCameraOnAStick::Message0x637a30 handles four m_f...property commands and returns, with NO yaw branch and NO parent Message call. Active runtime behavior was not inspected; whether chase mode2 uses this ignoring behavior is a concrete unresolved gate. This is consistent with several headings having no visible effect but does not prove observed run's cause.

SetCameraMode0x542640 IS implemented: pops object+integer; GetClientObjectByObjectId0x4ae910 resolves explicit recipient; GetSWSMessage0x4aedb0; SendServerToPlayerCamera_SetMode0x56c6d0. Client0x64ba67..a3 reads mode byte and calls CClientOptions::SetCameraMode0x61b6f0. Setter writes byte+0x6d; mode0/1 also updates+0x6e, mode2 does not. Not an NWN placeholder. Camera framing/collision and actual active behavior remain downstream qualifications.

## Operational conclusion

Use explicit PC caller and permit action queue processing, but do not spend repeated live cycles guessing a single units conversion as guaranteed fix. Controller-owned formation quadrant probe can identify visible staging direction without relying on broken/ignored camera requests. A completed action/gate alone does not prove actual camera heading. Capture runtime behavior identity/heading only if a later independent native audit is authorized. No new native API proposed here.

## Exact 32-byte entry guards

- 0x537fe0: `83ec248b0d003a7a008d44240450c7442404000080bfc744241000000000c744`

- 0x542530: `83ec18568d4424048bf18b0d003a7a0050e8daea080085c0750cb82ff8ffff5e`

- 0x542640: `8b0d003a7a0083ec088d44240050e86dea080085c074148d4c2404518b0d003a`

- 0x5137c0: `518b4424088b50448b4904538b583c558b684056578b78388b4048895424108b`

- 0x56c610: `83ec0853566a016aff68000100008bf1e87ba2f6ff8b5c24186a08538bcee88d`

- 0x64b8e0: `83ec50566a018bf1e843a9e8ff85c00f85af0100008a4424583c01530f856501`

- 0x637a30: `568b74240857568bf9e8f2bae2ff5068dc377400e866320d0083c40c85c07513`

- 0x49ee00: `568b74240857568bf9e82247fcff5068bc377400e896be260083c40c85c07510`
