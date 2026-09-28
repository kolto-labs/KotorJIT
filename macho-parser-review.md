# Mach-O metadata parser independent review

**PASS — no actionable correctness/bounds finding in this bounded parser foundation.** This is not Darwin runtime support or loader admission.

Reviewed macho.hpp/.cpp, kp_machotest.cpp, parser-only CMake additions and macho-parser-report.md. Unrelated projectile CMake changes were excluded from scope.

Explicit little-endian reads occur after header/command/table bounds validation. Region checks use subtraction rather than overflowing addition; command traversal stays within sizeofcmds, and count/table multiplications use wide arithmetic or are bounded before pointer arithmetic. Segment and section extents, relocation spans, command/header bitness and command alignment are checked. Local Headers publication keeps caller output unchanged on refusal. uint64_t fields preserve wide image addresses on i386 hosts. Unknown bounded commands are intentionally skipped and unsupported endian/fat formats explicitly rejected.

Tests meaningfully exercise truncation, malformed extents/command counts, zero-fill, selected metadata, wide addresses and unsupported formats. Failure-preservation assertions only compare bits rather than the entire previous Headers value; implementation is nevertheless structurally transactional because out is assigned only after all parsing succeeds. This is a nonblocking test-strength observation, not a correctness finding.

Do not interpret success as validating CPU execution support, dyld commands, executable protections, overlapping mappings, entry points, ASLR, symbol binding or section-to-segment mapping equivalence. Those loader constraints are beyond the documented metadata parser. CMake adds parser source and a standalone metadata test without enabling runtime format dispatch.

Author report records1095 synthetic checks, CTest1/1 and1099 checks with supplied private K1/K2 images; sanitizers unavailable and not claimed. Reviewer did not rerun builds/tests or inspect retail image bytes. No source/index changes or games; only this requested review report written.

Reviewed file hashes:
- src/image/macho.hpp f3ed2c7b33e73c1e4bff6651af5624d45c26b2b563e2fc78dcd13e0122162c85
- src/image/macho.cpp b96f26331e20d45d1848f269af87787c640a0c16486e907d2464122b35307e81
- tools/kp_machotest.cpp 8aabfe61d902ef73bde3cf47f7e2a819e97c4026482345020cbaa3442186316a
