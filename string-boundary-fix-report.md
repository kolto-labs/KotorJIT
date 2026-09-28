# Native string bridge fix — source handback

Source FROZEN for independent review. Exactly two owned files in lua-boundary-validation worktree:

- src/api/routines.cpp SHA256 ab6c23d85bdd71f990af3cdd061cafdc95ba8eeac1e70821e88b6f8d0f25f3b2
- tools/kp_routinetest.cpp SHA256 abfc638ac327a046022f02e4d0553b5235d36617ab9d171a9d8ac105b0c7bdff

Native return conversion now treats CExoString's extent as allocation capacity. It validates the readable extent, finds the first terminating NUL, and pushes only logical bytes. Malformed nonnull/zero, unreadable and unterminated outputs release the owned pop before luaL_error. Existing null-output empty behavior is preserved. Input string arguments are all validated before any native pushes, rejecting embedded NUL and unrepresentable capacity; accepted borrowed headers include the terminating byte. No generic Lua binary-string conversion is changed. No new native profiles/calls or unrelated product files.

Tests use real Lua and the actual routine bridge. Fake native output now has correct terminated capacity. Assertions measure byte length rather than strcmp alone; cover tags, spare capacity after terminator, empty/null, invalid/unreadable/unterminated output, destructor calls, input empty/text/UTF8, and embedded-NUL rejection before either native push or ExecuteCommand. A plain Lua byte-string check retains interior NUL. Existing routine-local GetLastConversation success handling still passes.

Validation: cmake build targets kp_routinetest, kphasor, kphasor_dll passed, with TMPDIR=/home/brunner56/kp-validation-20260922-build. Log string-boundary-build.log in that directory. One initial test-only compile declaration-order error was corrected before final successful build.

CTest kp_routinetest PASSED. Optional unchanged kp_consoletest FAILED its io.output file-target check, whose implementation uses Lua io.tmpfile. Global /tmp quota independently reproduced with tempfile.TemporaryFile(dir='/tmp') writing file-write: OSError122 Disk quota exceeded. TMPDIR does not redirect that libc tmpfile path. Do not report2/2 PASS or treat this as a Console source regression. Log string-boundary-tests.log in build directory. No Console source changes were made.

The current-tree DLL contains other in-progress work and is NOT the shipping artifact. Parent assigned the independent reviewer/release builder to copy only these two files onto clean ca329e5 in /home/brunner56/kp-release-20260922/source and produce the isolated shipping DLL/package. No index/commit/game operations performed by this writer. No further source mutations planned. Native evidence and scope limits are in lua-string-boundary-audit.md alongside this report.


## Reviewer overflow correction — final source freeze

Reviewer identified Win32 platform readable-range end arithmetic could wrap. Added an explicit capacity <= UINTPTR_MAX - pointer guard before platform::is_readable and memchr, using the existing destructor-safe malformed-header error path. Added a header(pointer UINTPTR_MAX-1,capacity4) regression verifying rejection and exactly one destroy. No platform or other source files changed.

Final source hashes supersede those above:
- src/api/routines.cpp:59f8441cbba02d8ec32f6c21d8a136140abea6280d1b95ca159e1d1065178a40
- tools/kp_routinetest.cpp:9879b960cb716f5d76e80eee6d7aea1ddb79f0f5feca1ef98d02c8f5725807ba

Native32 rebuild passed; focused kp_routinetest passed1/1 in0.01s. Logs string-boundary-overflow-build.log and string-boundary-overflow-tests.log under /home/brunner56/kp-validation-20260922-build. Clean release builder/reviewer received final hashes and owns Windows shipping build. Source ownership released again; no further edits planned.
