# Lua/NWScript native string boundary audit

2026-09-22, bounded read-only investigation. **Confirmed bridge defect on exact K1 GOG: the native CExoString allocation extent is exposed as Lua string length, including the terminator.** This is not expected user-facing GetTag behavior and not a JSON encoder defect. No source edits, builds, live calls or index operations were performed.

## Observed result and source

Recorded evidence: `stage-k1/runs/20260922-142626/console-command-13.json` under this private directory. The fixture prints escaped tags such as `g_w_blstrpstl001\0`, including inventory/equipped objects and other tags. It is a Lua diagnostic string containing an escaped NUL representation; the renderer need not be blamed for the native string conversion defect.

`src/api/routines.cpp:295-312` zero-initializes ExoString, calls vm.pop_string, then calls `lua_pushlstring(L, s.text, s.length)` for a nonnull pointer. Lua faithfully retains exactly that many bytes. The optional native destructor runs afterward. `src/api/enginestruct.hpp:70` names the second DWORD `length` but does not distinguish capacity from logical content length. That naming and direct length use are incorrect for the verified native return path.

## Exact native evidence

Input `/home/brunner56/kp-live-20260922/stage-k1/swkotor.exe`, SHA256 previously independently verified in this research session as `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`. Original PE disassembly was inspected again at the following exact sites; read-only corpus binary8 corroborated symbol identities.

- CExoString(char*) constructor0x5e5a90: scans to first NUL; at0x5e5abe increments strlen by1, stores that value into this+4 at0x5e5ac0, allocates that many bytes, then copies through the NUL. Null/empty input stores pointer0/extent0. ABI thiscall(this,char*), ret4.
- CExoString::GetLength0x5e5790: returns0 for a null pointer; otherwise scans the pointed-to bytes to the FIRST NUL and returns the byte count before it. It never reads this+4. Thus native logical string length excludes the terminator and is not the allocation field.
- CVirtualMachineInternal::StackPopString0x5d25e0: validates stack type5, calls CExoString::operator=(CExoString&)0x5e5c50 at0x5d2617 into the caller-provided output, then pops the VM slot. ABI thiscall(internal,CExoString*), ret4. Wrapper StackPopString0x5d1080 is the existing resolved VM accessor.
- Assignment0x5e5c50 scans source using C-string semantics. For an empty destination (as used by this bridge),0x5e5cb5 increments logical length by1;0x5e5cb7 stores that allocated extent into destination+4; copy0x5e5cd0..d8 includes the terminator. For a reused destination, it can retain a larger allocation when the new string fits (0x5e5c78..80), so universally subtracting one from this+4 is not a correct logical-length algorithm.
- Explicit-length constructor0x5e5b70 allocates requested count+1 and writes a terminator at that count. Nevertheless GetLength and the VM-pop assignment use first-NUL semantics. Bytes after an interior NUL are not retained as logical content by this verified VM-pop path.

The fresh zeroed return object is why ordinary GetTag returns consistently show exactly one extra NUL. The broader native field represents capacity/allocation extent, so simply removing every trailing NUL, or assuming extent-1 is always content length, would misstate the contract.

## Narrow future correction

Limit the correction to the native NWScript string-result conversion. For the verified CExoString contract, find the FIRST terminator within the declared readable allocation extent and push only the preceding bytes. Preserve all preceding bytes unchanged: no whitespace trimming, case changes, character-set conversion, deletion of arbitrary NUL bytes from Lua data, or JSON-wide cleanup. A bounded memchr/scan follows native GetLength semantics without adding an unbounded strlen native-memory read. Null pointer continues to yield the documented existing empty result unless a separately chosen malformed-header policy changes that behavior.

Reject an inconsistent nonnull/zero-extent or unterminated header explicitly rather than silently truncating real text or scanning beyond the allocation. Use the project's appropriate validated/native-memory read mechanism and a documented size bound if required; do not silently clip legitimate long return values to an arbitrary cap. Release the popped engine allocation exactly once before reporting any newly detected conversion error; luaL_error can longjmp, so do not rely on a C++ destructor running afterward. Preserve original stack-pop failure behavior and destructor ownership.

For minimal deployment, keep the allocation layout unchanged and clarify the field/helper contract instead of changing every ExoString user at once. The source is shared by multiple bindings; exact native evidence here is K1 GOG only. Check existing supported variant contracts before globally asserting that all VM bindings use this capacity convention, or select the native conversion policy at binding time. Do not change Lua's general byte-string contract: direct Console/Lua values such as `string.char(65,0,66)` must still preserve the interior NUL through typed output and JSON serialization.

Input direction is related but separate: routines.cpp:187 currently constructs a borrowed ExoString using strlen from luaL_checkstring, so embedded-NUL Lua input already has C-string behavior. Do not silently redesign that input contract in the return-value fix. Likewise raw `kp.struct` views and hook-specific readers have separate existing behavior; audit them separately rather than expanding this slice.

## Existing precedent and misleading test

`src/runtime/hook_bodies.cpp:71-95` already removes one trailing NUL from RunScript names after a similar live mismatch. Its comments claim other strings are length-delimited and this name is exceptional. The exact native constructor/assignment/GetLength evidence above is stronger for this VM return path: capacity is not logical length. Do not blindly reuse the hook reader's trailing-byte rule as a universal CExoString decoder.

`tools/kp_routinetest.cpp:56-62` fake pop_string supplies pointer"last" with length4. A real fresh K1 output has allocation extent5. Its current string assertion around:294 uses strcmp, which cannot detect a trailing embedded Lua NUL. Both choices mask the live defect.

## Meaningful focused tests

1. Make the native-result fixture supply a terminated allocation of5 bytes for"last". Assert `lua_tolstring` returned length4 (or Lua `#value==4`), exact byte equality and value=="last". Do not rely on strcmp alone.
2. Exercise a tag-shaped value and verify Lua equality/length plus escaped/JSON output have no extra terminator. The current GetLastConversation routine-local status exception must remain intact.
3. Test empty/null output, terminated empty allocation, and a larger retained allocation containing `abc\0` plus nonzero tail bytes: logical result must be exactlyabc with no allocation-tail leak.
4. Test unterminated/inconsistent headers according to the chosen explicit error contract, without out-of-bound reads; check native destruction once on successful conversion and each new error path. Preserve no-pop behavior for failed ExecuteCommand and pop failure diagnostics.
5. Separate genuine Lua binary-string regression: `A\0B` remains3 bytes through the Console value/output path. If testing interior NUL inside native CExoString capacity, expect native first-NUL semantics for this verified VM output, not concatenation/removal of zero bytes.
6. Controller-owned later live check: `local s=nwscript.call('GetTag',item); return #s,s==expected,s:byte(-1)` for a known owned item, plus representative empty/localized/dialog strings. Offline tests do not by themselves establish all supported variants.

This finding explains string equality/length corruption only. It does not establish that the recorded weapon equip failure was caused by the NUL: that receipt also shows different object identities and stack splitting. Keep that independent native equip diagnosis intact.


## Input-direction follow-up — exact StackPushString behavior

Original CVirtualMachineInternal::StackPushString0x5d1930 (wrapper0x5d1090), thiscall(vm,CExoString*), ret4, allocates a new8-byte native CExoString. It invokes CExoString::CStr0x5e5670 at0x5d1969 on the supplied header, then invokes char* constructor0x5e5a90 at0x5d1971. CStr reads only the pointer field and substitutes a static empty string for null; it never reads+4. Constructor then scans to the first NUL, allocates strlen+1 and copies through the terminator as already proved.

Thus routines.cpp:190's borrowed `{v, strlen(v)}` header is inconsistent with the capacity interpretation, but it does NOT make this exact native push omit a terminator: the native push ignores that field and obtains a terminated copy from Lua's terminated storage. This is a metadata correctness issue alongside the confirmed output defect, not evidence of actual missing-terminator input corruption. Copy constructor0x5e5b00 likewise scans the source C string and allocates logical length+1 rather than treating source+4 as payload length.

**Embedded input NUL is already silently lossy.** luaL_checkstring exposes Lua storage, strlen obtains only the prefix, and native CStr/constructor copy only that prefix. NWScript's native string path cannot preserve an arbitrary Lua byte string with an interior NUL. Correct handling is an explicit bridge error identifying that unsupported argument, not deleting zero bytes or silently truncating. General Lua and Console binary-string output remains untouched.

### Narrow both-directions implementation boundary

- Prevalidate every declared supplied string argument with luaL_checklstring to obtain its actual Lua byte count. Reject any NUL within that count and any size that cannot represent count+1 in the native DWORD. Defaults are known terminated native text; validate/size them consistently. **Do this before the reverse VM push loop**, not just inside push_argument: an invalid earlier declared string encountered after later parameters have already been pushed would leave a partially modified native VM stack. This fix need not refactor all unrelated argument types.
- For accepted strings, preserve exact non-NUL bytes, supply borrowed pointer plus allocation extent=count+1, including an empty Lua string with its valid one-byte terminator extent1. The native constructor may normalize its owned empty result to null/0. Do not destroy the borrowed Lua header.
- Decode native string results by the first terminator within the validated allocation span; never send the allocation terminator/tail to lua_pushlstring. Keep allocation release on the owned output path exactly once.
- No new native binding/site is necessary: CStr and ctor inspection justify the existing StackPushString ABI, not a request to call additional native constructors from the bridge.

Additional focused tests: a real bridge routine signature with a string before another parameter proves embedded-NUL rejection occurs with zero pushes/zero ExecuteCommand calls; accepted nonempty and empty argument headers include a valid terminator extent and preserve non-ASCII bytes; default empty string follows the same borrowed contract. Include a K1-semantic fake native push that reads via CStr/first NUL and makes its own terminated copy, rather than encoding the original incorrect length assumption into a fake. Output tests must measure Lua byte lengths so trailing zero cannot hide behind strcmp. Keep the existing GetLastConversation return-status exception and raw Lua binary-string regressions intact.

Source remains read-only pending explicit implementation ownership handback. The current equip failure still has independent identity/stack-splitting evidence; no causation claim is inferred from fixing tags.
