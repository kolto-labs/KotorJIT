// The __thiscall bridge: how a plain C++ handler receives `this` as a normal
// first parameter and still forwards to the original correctly.
//
// WHO POPS WHAT -- the whole point of this file
// ============================================
// MSVC __thiscall on x86, which is what every Aurora engine method uses:
//
//   ECX          holds `this`
//   the stack    holds the remaining arguments, pushed RIGHT TO LEFT
//   EAX          holds the return value
//   ECX, EDX     are scratch; EBX, ESI, EDI, EBP are preserved
//   THE CALLEE   pops the stack arguments, with `ret imm16`
//
// That last line is the one that corrupts a game when it is wrong. The caller
// does NOT adjust ESP after the call, because the callee already did. A hook
// that pops a different number of bytes than the function it replaced leaves ESP
// skewed by that difference, forever, on that thread. The symptom is not a crash
// at the hook -- it is a crash somewhere else entirely, later.
//
// So the rule is: our hook must pop EXACTLY what the original popped. Since the
// hook is declared with the same parameter list as the original, the compiler
// computes the same `ret imm16` and the discipline holds by construction. It
// stops holding the moment someone changes the hook's signature without changing
// the prototype it was derived from -- which is why hook prototypes come from
// the recovered C for that specific function, one per site, and are not shared
// between differently-shaped EventHandler overloads.
//
// HOW WE SPELL IT
// ===============
// GCC (both g++ -m32 and i686-w64-mingw32-g++) implements MSVC's convention
// directly as __attribute__((thiscall)): first integral/pointer argument in ECX,
// the rest on the stack, callee-cleans. Verified by disassembly on both
// toolchains -- a two-argument method compiles to `ret $0x8` under each, which
// is exactly what MSVC emits.
//
// The fallback, if a future toolchain drops the attribute, is
// __attribute__((fastcall)) with a dummy second parameter to absorb EDX:
//
//     int __attribute__((fastcall)) hook(void* ecx, void* /*edx*/, int a);
//
// fastcall passes arg1 in ECX, arg2 in EDX, the rest on the stack, and the
// callee cleans -- identical stack layout and identical cleanup once the dummy
// swallows EDX. Swapping to it is a one-line change to KP_THISCALL plus a dummy
// parameter per hook, which is why the macro exists rather than the attribute
// being written out at every site.
//
// NOT SUPPORTED, on purpose
// =========================
//   * Returning a struct or class by value. MSVC passes the hidden return
//     pointer as the first STACK argument and the callee pops it; the System V
//     rules GCC applies to a struct return differ. Use an out-parameter.
//   * Variadic methods. MSVC compiles those as __cdecl, not __thiscall, so the
//     cleanup side flips. None of the M1 hook sites are variadic.
//   * 64-bit __thiscall. There is none on x86-64; see the x86_64 branch below.
//
// WHY NOT LUAJIT FFI
// ==================
// Because it cannot express any of the above. FFI callbacks do not support
// __thiscall at all, cannot infer __stdcall on x86, are capped at a few hundred
// live callbacks with implicit ones never reclaimed, and PANIC the VM when a
// JIT-compiled call re-enters Lua -- which is precisely the shape of a MainLoop
// or EventHandler hook. Hook bodies are native C++ and call into Lua through the
// C API. This is a correctness constraint, not a preference.
#pragma once

#include <exception>

#include "platform/platform.hpp"

namespace kp::hooks {

#if defined(__i386__) || defined(_M_IX86)
#define KP_THISCALL __attribute__((thiscall))
#elif defined(__x86_64__) || defined(_M_X64)
// System V x86-64 (the macOS builds): `this` is simply the first integer
// argument in RDI and the caller cleans, so a plain function pointer with
// `void* self` first IS the method's ABI. There is nothing to spell; the macro
// exists so every hook prototype stays one declaration for both targets.
//
// What does NOT carry over from i386 is the argument widths. Declare each
// parameter with the width the x86_64 method really has (see
// platform/target.hpp): a 32-bit parameter where the engine passes a 64-bit
// object id receives the right low half but garbage in the high half of the
// register when it is forwarded, and a 32-bit out-parameter where it writes
// 64 bits is a stack overwrite.
#define KP_THISCALL
#else
#error "the __thiscall bridge supports x86-32 and x86-64 only"
#endif

// A pointer to a game method. `this` is an ordinary first parameter here; the
// attribute is what routes it to ECX.
//
//     using RunScriptFn = ThiscallFn<int, const CExoString*, unsigned long, int>;
//
template <typename Ret, typename... Args>
using ThiscallFn = Ret(KP_THISCALL*)(void*, Args...);

// Native engine C++ member convention for the running binary: MSVC __thiscall
// on Windows i386 builds, SysV i386 cdecl (`this` as first stack arg) on
// GCC-compiled Linux i386 builds, and System V / MS x64 on 64-bit targets.
#if defined(_WIN32) && (defined(__i386__) || defined(_M_IX86))
#define KP_ENGINE_METHOD_CALL __attribute__((thiscall))
#elif defined(__i386__)
#define KP_ENGINE_METHOD_CALL __attribute__((cdecl))
#else
#define KP_ENGINE_METHOD_CALL
#endif

template <typename Ret, typename... Args>
using EngineMethodFn = Ret(KP_ENGINE_METHOD_CALL*)(void*, Args...);

#if defined(__i386__) || defined(_M_IX86)
// The documented fallback spelling, kept declared so the alternative is visible
// rather than buried in a comment. The second parameter absorbs EDX and is
// never read.
template <typename Ret, typename... Args>
using FastcallThisFn = Ret(__attribute__((fastcall)) *)(void*, void*, Args...);
#endif

// Invariant 1, at the boundary: no fault crosses back into game code.
//
// A hook body runs on the game's own thread, inside a call the engine believes
// is one of its own methods. If it throws, unwinding runs through frames the
// game compiled without unwind information and the process dies with no useful
// diagnostic. So every hook body is wrapped, and a throwing body yields the
// stated fallback value -- the engine sees a normal return.
//
// LIMIT, stated rather than implied: this catches C++ exceptions. It does not
// catch an access violation or a divide-by-zero, because those are hardware
// faults and not C++ exceptions. MSVC would use __try/__except; MinGW GCC has no
// equivalent. Covering hardware faults needs AddVectoredExceptionHandler on
// Windows and a SIGSEGV handler on Linux, which is follow-up work, not something
// this template silently pretends to do.
template <typename Ret, typename Body>
Ret guard(Ret on_error, Body&& body) noexcept {
    try {
        return body();
    } catch (const std::exception& e) {
        platform::log(platform::LogLevel::Error, "hook body threw: %s", e.what());
    } catch (...) {
        platform::log(platform::LogLevel::Error, "hook body threw a non-exception");
    }
    return on_error;
}

template <typename Body>
void guard_void(Body&& body) noexcept {
    try {
        body();
    } catch (const std::exception& e) {
        platform::log(platform::LogLevel::Error, "hook body threw: %s", e.what());
    } catch (...) {
        platform::log(platform::LogLevel::Error, "hook body threw a non-exception");
    }
}

}  // namespace kp::hooks
