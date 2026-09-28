# Versioned Console harness adapter

SOURCE FROZEN. Seven owned paths below; preserve unrelated pre-existing CMake additions (only new kp_consoleprotocoltest target belongs to this slice). runtime/runtime.cmake and Console core unchanged. No DLL/game/index/commit.

Thin opt-in delegation in cmd_devtools uses protocol=kp.console.v1. Legacy no-protocol body verified byte-identical to HEAD. New adapter serializes existing Console service only; no interpreter, pump, reset or waits. Runtime nonce generated once with standard random_device; entropy failure yields explicit versioned unavailability without native-pointer fallback or legacy interference. All nonstatus operations require exact runtime and canonical decimal session, outcome/cancel exact nonzero request, output cursor accepts0. StaleRuntime checked before mutation. Source remains JSON string. Output/error/completion/return raw bytes all base64 with decimal retained byte_length. Typed values preserve nil/false/opaque/finite/nonfinite/negativezero; original counts/truncation and independent outcome/output eviction metadata retained. No globalcancel in versioned path.

Wire schema docs/devtools-protocol.md is the acceptance authority. status result carries current epoch, decimal counters and overlay observations. All versioned results echo protocol/runtime, use status for explicit service acceptance/lookup/cancel states. Found outcome nested under outcome. Native command transport is engine-thread serviced: not preemption of blocking native calls. No engine bypass introduced.

Validation:
- cmake configure + kp_consoleprotocoltest and kp_consoletest native32 build PASS.
- CTest regex ^kp_console(protocol)?test$ PASS2/2,0.07sec.
- Actual Console/Lua adapter tests: pending/success, nil versus emptytuple,false,binaryNUL/invalidUTF8 strings,opaque noninspectable,negativezero/NaN/infinities,syntax/runtime/instructionbudget failures,queued exactcancel/no spill,terminal cancellation,stale runtime no mutation,reset/stalesession,expired outcomes,output attribution0/rawbytes/dropcursors,response<1MiB,truncatedstrings,completion,queue/source bounds,invalid IDs/cursors/protocol,decimal >2^53 and uint64max. Existing Console suite also retains service concurrency/legacy coverage.
- Original cmd_devtools legacy branch text exactly equals HEAD; no direct live legacy-wire test in this slice.
- scoped gitdiffcheck PASS; new source formatted via clang-format.
- Early test caught Json::set returning child rather than container; removed all chained setters and reran to passing. No core Json semantics changed.

Logs /tmp/kp-console-wire-configure.log and /tmp/kp-console-wire-build.log. Runtime commands integration and WinDLL compilation/live acceptance remain controller gates. Host service concurrency tests are not RPC preemption proof. New adapter is standardC++ with no platform SDK/external dependency.

Frozen SHA256:
04672437550986c48ade315b4c0a0b2cbb8ba40b85dd9b2baff78f47c0821fa2 src/harness/console_protocol.hpp
a67cb4baabcfc2d92881104ad9399dcb2bff68dcd134fc32050e15b0ad462cd0 src/harness/console_protocol.cpp
b7e8fb5bba5bac2c7b9d85ab3d2d98e714170abfdc3907a743ff08f1178aea01 src/harness/commands.cpp
a9ed1917dd4092accd9dd46f20044e61dfc45e83091feec20f5899a50d81b0ec src/harness/harness.cmake
a671fa7ea4beeafd829f531f0064ebd93ab83648752894aabf17df4ea5d4375b tools/kp_consoleprotocoltest.cpp
05a9b35c9b29e50cca65f1e1f8b8f71995ddb143f1b009e471d0e912fef20111 CMakeLists.txt
8923a497e2c52ca4f617a677d68b0d6d3f5c8c7a0d619bde9aced2fcce69e4a4 docs/devtools-protocol.md
