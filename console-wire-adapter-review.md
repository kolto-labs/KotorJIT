# Independent kp.console.v1 adapter review

Verdict: PASS for the frozen seven-path slice. No actionable blocking finding or schema mismatch identified.

Read adapter implementation/header, actual Console protocol contracts, command delegation diff, test source, scoped CMake wiring, implementation report and build log. Independently verified all seven SHA256 values match the report. No source edit, build or game performed.

The protocol-presence gate refuses malformed opt-ins without entering legacy cancellation; the remaining legacy command body is unchanged in the diff. All versioned operations use the same Console object and introduce no evaluation/pump/reset path. Nonstatus operations enforce runtime identity and canonical nonzero session strings; exact request and cursor validation rejects overflow, signs, leading zeros and numeric JSON. Runtime mismatch returns before mutation. Entropy exceptions are caught and versioned availability fails explicitly; no pointer-based identity fallback is present.

Serialization matches the documented schema: uint64/counts are decimal strings, raw Lua/output/error/completion bytes use base64 and retained byte lengths, strings carry original length and truncation, nil preserves tuple position, false remains boolean, negative zero/nonfinite numbers use explicit tags, and opaque values have no expansion handle. Finite doubles use the existing 17-digit JSON serializer. Lookup/submit/cancel statuses remain distinct, and output cursor/drop metadata is forwarded separately from outcome retention. Completion checks epoch both before and after retrieving names.

The test target links the real Console, real LuaJIT, adapter and JSON implementation. Cases exercise actual pending/success/failure/cancel/reset/eviction/binary-data behavior rather than substituting a fake evaluator. Wire counters above2^53 and UINT64_MAX are tested; existing Console tests cover the deeper cancellation concurrency behavior. Adapter test does not claim concurrent RPC preemption. Its scheduling limitation is explicitly documented: the wire command waits for the engine owner to service it.

CMake includes the new source through KP_HARNESS_SOURCES, consumed by runtime Windows and native configurations; the focused test target is registered under the existing Unix test block. Unrelated pre-existing CMake additions were excluded from this review.

Remaining validation gates are correctly reported as controller work: Windows/runtime command integration build, legacy live compatibility, and supported physical-console acceptance. The standalone adapter tests do not establish these gates. Runtime nonce portability still needs the intended Windows build/live status check; this review does not elevate native-host success to Windows proof.
