# Mach-O offline CLI integration

SOURCE FROZEN, 2026-09-27. Read progress.md ledger, user-directive-audit.md latest scope, release-platform-status.md and previous macho-parser-report.md before finalizing.

Changed only tools/kp_imagetool.cpp, tools/kp_imagetool_macho_test.py (new), CMakeLists.txt (one focused test registration). No runtime Format/build-record/loader changes, no retail fixtures, index actions, games or commits.

kp_imagetool identify/sections detect Mach-O container magic and delegate all metadata decoding/validation to the existing macho::read_file parser. Output includes actual SHA256, existing lookup_build alias when available (currently unrecognised for private Mac files), architecture/raw CPU/subtype/container bitness, explicit metadata-only/no-runtime-admission/no-ASLR wording. sections prints segment/section preferred VA and file offset/size, virtual size, segment protections, and zero-fill/no-file-bytes distinction. uint64_t plus PRIx64 preserves addresses over4GiB in the existing32bit tool. Successful valid Mach-O metadata inspection returns0 even when runtime build is unrecognised; malformed/unsupported returns2. Existing PE/ELF identity exit semantics remain unchanged. Mach-O --mapped, classify and dump explicitly refuse before any output file creation. Fat/bigendian identify/sections receive the parser's explicit refusal.

Validation completed:
- cmake configure existing private native build; build target kp_imagetool -j2 PASS.
- ctest -R ^kp_imagetool_macho_test$ --output-on-failure PASS1/1,0.18sec finalrun.
- Synthetic subprocess tests thin32/64, expected hashes, address widths/file extents, unsupported modes/no dump output, malformed/truncated image, fat/bigendian refusal, unknown legacy identity exit1, and minimalELF32 sections in offline and mapped modes.
- Both provided private K1/K2 Mac raw images: identify and sections exit0. Original private K1 GOG swkotor.exe: sections exit0 withPE32 output. No game process opened. Private output /tmp/kp-macho-cli-private.log; build /tmp/kp-macho-cli-build.log.
- scoped git diff --check PASS.

Frozen hashes:
98265b67429a23dc0d9ad80a0a08d504ce462bdfd5d3ba9c9757f89c0842d429 tools/kp_imagetool.cpp
521e3cc1b80aaa710cd8e567e4a153b03e9a1ece233d4e8ab84714a25cc25cc4 tools/kp_imagetool_macho_test.py
5b5b94ed1ac0ec788e9440beb3687d4f0bfc95052b96a26b7cdaab1349cec3be CMakeLists.txt

Next: independent review. This exposes useful static inspection only; Darwin loader/ASLR/native adapters remain separate missing capabilities.

## Independent CLI review — 2026-09-27

Spec PASS; quality PASS. No actionable P0/P1/P2 findings in this bounded CLI slice. Reviewer did not implement this slice or change product source. Frozen hashes above independently match all three files; CMake's unrelated pending projectile/parser additions were excluded from the CLI review scope.

The CLI delegates decoding to the existing bounded Mach-O parser, uses uint64_t/PRIx64 without narrowing through host uintptr_t for preferred addresses and spans, prints metadata-only/no-ASLR/no-runtime-admission explicitly, and refuses mapped/classify/dump before output creation. Only the CLI dispatch path recognizes Mach-O; no runtime Format/build-table admission is added here. PE/ELF command implementations remain unchanged.

Independently executed tools/kp_imagetool_macho_test.py against the existing built kp_imagetool: PASS. `file` confirms that tool is an i386 32-bit ELF executable, so the test's expected 0x0000000100001100 output actually exercises >4GiB metadata on a 32-bit host binary. Tests assert exact file hashes, typed bitness, file extents, unsupported status2, no dump output, malformed/fat/big-endian refusal, legacy unknown identify status1 and ELF32 file/mapped routes.

Nonblocking coverage opportunity: the CLI subprocess test does not itself check zero-fill presentation, protections/architecture labels, or a valid PE fixture. The underlying parser test covers zero-fill and the implementer's recorded private PE sections check is separate evidence. Adding synthetic checks for these output fields would strengthen future regression coverage; this is not a current correctness defect and does not block the slice.

No game, loader, Mac runtime, or retail fixture was launched or packaged by this review. Static inspection success remains separate from Mac runtime support.
