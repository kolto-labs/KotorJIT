# Independent narrow string-boundary review

PASS after one requested correction, 2026-09-22.

Reviewed only src/api/routines.cpp and tools/kp_routinetest.cpp against the existing native ABI audit. Final hashes: routines59f8441cbba02d8ec32f6c21d8a136140abea6280d1b95ca159e1d1065178a40; test9879b960cb716f5d76e80eee6d7aea1ddb79f0f5feca1ef98d02c8f5725807ba.

The implementation obtains logical native text with first-NUL semantics within the declared readable allocation, preserves null-output behavior, and destroys the owned output before raising each newly introduced malformed-header error. Supplied/default native strings are prevalidated before the reverse push loop; embedded NUL and unrepresentable capacity fail without any native argument pushes. General Lua binary strings remain unchanged. Existing unrelated pop-failure and Lua allocation-failure ownership behavior is unchanged.

Initial review found that platform::is_readable did not itself reject address+capacity overflow. Requested explicit UINTPTR_MAX-address guard before that call; the final source includes it and a wrapping-header regression. No remaining P0/P1/P2 finding in this narrow diff. Writer reports native32 focused routine test1/1 PASS; independent reviewer did not rerun it. Clean release Windows build and controller-owned exact-artifact live gate remain separate.

Exact underlying native ABI evidence is K1 GOG. This review does not certify K2 or Mac string ABI or runtime support.
